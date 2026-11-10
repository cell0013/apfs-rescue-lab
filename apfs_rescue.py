#!/usr/bin/env python3
"""APFS Rescue Lab: experimental automatic checkpoint candidate nomination.

This does not constitute full APFS validation or a guaranteed repair.
Run on an OFFLINE GPT whole-disk RAW image only. Never on original disk.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

BLOCK = 4096
GUID = bytes.fromhex("ef57347c0000aa11aa1100306543ecac")
MAX_SCAN_GIB = 1024  # --scan-gib 0 scans the full APFS partition

def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]

def u64(b, o):
    return struct.unpack_from("<Q", b, o)[0]

def checksum_ok(b):
    if len(b) != BLOCK:
        return False
    mod = 0xffffffff
    s1 = s2 = 0
    for pos in range(8, BLOCK, 4):
        s1 = (s1 + u32(b, pos)) % mod
        s2 = (s2 + s1) % mod
    c1 = (mod - ((s1 + s2) % mod)) % mod
    c2 = (mod - ((s1 + c1) % mod)) % mod
    return u64(b, 0) == ((c2 << 32) | c1)

def apfs_bounds(fp):
    fp.seek(0, 2)
    size = fp.tell()
    if size % BLOCK:
        raise ValueError("Whole-disk RAW size must be 4096-byte aligned")
    fp.seek(512)
    h = fp.read(512)
    if len(h) != 512 or h[:8] != b"EFI PART":
        raise ValueError("GPT not found")
    table_lba, n, item_size = u64(h, 72), u32(h, 80), u32(h, 84)
    if not (1 <= n <= 4096 and 128 <= item_size <= 1024):
        raise ValueError("Unsupported GPT table")
    if table_lba * 512 + n * item_size > size:
        raise ValueError("GPT table out of image bounds")
    found = []
    for i in range(n):
        fp.seek(table_lba * 512 + i * item_size)
        item = fp.read(item_size)
        if item[:16] != GUID:
            continue
        a, b = u64(item, 32) * 512, (u64(item, 40) + 1) * 512
        if not (0 < a < b <= size and a % BLOCK == 0):
            raise ValueError("Malformed APFS partition bounds")
        found.append((a, b))
    if len(found) != 1:
        raise ValueError("Exactly one GPT APFS partition required")
    return found[0]

def block_read(fp, begin, end, phys):
    at = begin + phys * BLOCK
    if phys < 0 or at + BLOCK > end:
        raise ValueError("APFS physical block outside partition")
    fp.seek(at)
    data = fp.read(BLOCK)
    if len(data) != BLOCK:
        raise IOError("Short APFS block read")
    return data

def parse_checkpoints(fp, begin, end):
    nx = block_read(fp, begin, end, 0)
    if nx[32:36] != b"NXSB" or not checksum_ok(nx) or u32(nx, 36) != BLOCK:
        raise ValueError("Primary NXSB invalid")
    desc_count, base = u32(nx, 104), u64(nx, 112)
    if desc_count & 0x80000000 or not (1 <= desc_count <= 65536):
        raise ValueError("Noncontiguous or unsupported checkpoint descriptor area")
    found = []
    for idx in range(desc_count):
        b = block_read(fp, begin, end, base + idx)
        if b[32:36] == b"NXSB" and checksum_ok(b) and u64(b, 8) == 1:
            found.append({"xid": u64(b, 16), "block": base + idx})
    return sorted(found, key=lambda c: c["xid"], reverse=True)

def volume_superblocks(fp, begin, end, scan_gib):
    max_blocks = min((end - begin) // BLOCK, scan_gib * (1024 ** 3 // BLOCK)) if scan_gib else (end - begin) // BLOCK
    found = {}
    per_read = 4 * 1024 * 1024 // BLOCK
    for off in range(0, max_blocks, per_read):
        count = min(per_read, max_blocks - off)
        fp.seek(begin + off * BLOCK)
        data = fp.read(count * BLOCK)
        if len(data) != count * BLOCK:
            raise IOError("Short read while scanning volume headers")
        for j in range(count):
            b = data[j * BLOCK:(j + 1) * BLOCK]
            if b[32:36] != b"APSB":
                continue
            if u32(b, 24) & 0xffff != 13 or not checksum_ok(b):
                continue
            role = struct.unpack_from("<H", b, 0x3c4)[0]
            fs_flags = u64(b, 256)
            if role != 0x40 or not (fs_flags & 1):
                continue  # only unencrypted Data volumes
            oid, xid = u64(b, 8), u64(b, 16)
            uuid = b[240:256].hex()
            found.setdefault((oid, uuid), []).append({
                "oid": oid, "uuid": uuid, "xid": xid,
                "block": off + j, "omap": u64(b, 128)
            })
    return found

def candidate_omap_check(fp, begin, end, entry):
    limit = (end - begin) // BLOCK
    addr = entry["omap"]
    if not 0 < addr < limit:
        return False, "OMAP address out of range"
    om = block_read(fp, begin, end, addr)
    if not checksum_ok(om) or (u32(om, 24) & 0xffff) != 11 or u32(om, 28) != 0:
        return False, "OMAP header/checksum invalid"
    if u64(om, 16) > entry["xid"]:
        return False, "OMAP newer than volume"
    root = u64(om, 48)
    if not 0 < root < limit:
        return False, "OMAP root out of bounds"
    tree = block_read(fp, begin, end, root)
    if not checksum_ok(tree) or (u32(tree, 24) & 0xffff) != 2 or u32(tree, 28) != 11:
        return False, "OMAP root B-tree header/checksum invalid"
    if u64(tree, 16) > entry["xid"]:
        return False, "OMAP tree newer than volume"
    return True, "plausible header chain ONLY; B-tree descendants not validated"

def nominate(source, scan_gib):
    with source.open("rb") as fp:
        begin, end = apfs_bounds(fp)
        scan_bytes = min(end - begin, scan_gib * 1024 ** 3) if scan_gib else end - begin
        checkpoints = parse_checkpoints(fp, begin, end)
        gids = {c["xid"] for c in checkpoints}
        groups = volume_superblocks(fp, begin, end, scan_gib)
        possibilities = []
        for (oid, uuid), entries in groups.items():
            entries.sort(key=lambda e: (e["xid"], e["block"]), reverse=True)
            latest = entries[0]
            # The original case had a broken latest Data volume Object Map.
            ok, reason = candidate_omap_check(fp, begin, end, latest)
            if ok:
                continue
            for old in entries[1:]:
                if old["xid"] >= latest["xid"] or old["xid"] not in gids:
                    continue
                candidate_ok, candidate_reason = candidate_omap_check(fp, begin, end, old)
                if candidate_ok:
                    possibilities.append({
                        "oid": hex(oid), "uuid": uuid, "latest_xid": hex(latest["xid"]),
                        "selected_xid": hex(old["xid"]), "latest_failure": reason,
                        "selected_block": hex(old["block"]),
                        "evidence": candidate_reason,
                    })
                    break
    # Refuse if several volumes provide equally plausible but conflicting options.
    selected = possibilities[0] if len(possibilities) == 1 else None
    return {
        "image_bytes": source.stat().st_size,
        "apfs_partition_start": begin,
        "scanned_apfs_bytes": scan_bytes,
        "scan_complete": scan_bytes >= (end - begin),
        "checkpoints": [hex(c["xid"]) for c in checkpoints[:32]],
        "possible_targets": possibilities,
        "nomination": selected,
        "status": "candidate_nominated" if selected else "manual_review_required",
        "warning": "Heuristic candidate only. Not a complete APFS metadata or bootability validation."
    }

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["analyze", "recover"])
    p.add_argument("--source", required=True, help="Offline whole-disk RAW; NEVER the only copy")
    p.add_argument("--output", help="New candidate RAW (recover only)")
    p.add_argument("--scan-gib", type=int, default=0, help="0=complete APFS scan; positive number=GiB cap")
    p.add_argument("--report", help="New JSON report, optional")
    p.add_argument("--i-understand-this-can-destroy-data", action="store_true")
    p.add_argument("--allow-partial-scan", action="store_true", help="EXPERT: permit a candidate from an incomplete scan")
    args = p.parse_args()
    if not (0 <= args.scan_gib <= MAX_SCAN_GIB):
        p.error("--scan-gib must be between 0 (full) and %d" % MAX_SCAN_GIB)
    source = Path(args.source).expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != ".raw":
        p.error("Source must be existing whole-disk RAW file")
    report = nominate(source, args.scan_gib)
    print("Checkpoint candidates:", ", ".join(report["checkpoints"][:12]))
    if report["nomination"]:
        print("Nominated:", report["nomination"]["selected_xid"], "for volume", report["nomination"]["oid"])
    else:
        print("No unique plausible checkpoint found; refusing automated changes")
    if args.report:
        destination = Path(args.report).expanduser().absolute()
        if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
            p.error("Report must be a new path in an existing directory")
        destination.write_text(json.dumps(report, indent=2) + "\n")
        print("Report:", destination)
    if args.mode == "analyze":
        print("Read-only analysis complete; no images changed")
        return
    if not args.output or not args.i_understand_this_can_destroy_data:
        p.error("recover needs --output and --i-understand-this-can-destroy-data")
    if report["nomination"] is None:
        p.error("Ambiguous or unsupported APFS metadata; no image created")
    if not report["scan_complete"] and not args.allow_partial_scan:
        p.error("Incomplete APFS scan; use --allow-partial-scan only with full awareness of the risk")
    if sys.platform != "darwin":
        p.error("Candidate creation requires macOS APFS clonefile support")
    # Import published, separately maintained checkpoint selector.
    from experimental import checkpoint_select
    out = Path(args.output).expanduser().absolute()
    checkpoint_select.build(source, out, int(report["nomination"]["selected_xid"], 16), True)
    print("Experimental candidate created. Do not boot or write before independent checks.")

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(2)

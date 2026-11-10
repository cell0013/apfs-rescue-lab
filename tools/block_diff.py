#!/usr/bin/env python3
"""Read-only, byte-for-byte comparison of two offline whole-disk RAW images."""
import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

BLOCK = 4096
CHUNK = 4 * 1024 * 1024
GUID = bytes.fromhex("ef57347c0000aa11aa1100306543ecac")

def u32(b, i):
    return struct.unpack_from("<I", b, i)[0]

def u64(b, i):
    return struct.unpack_from("<Q", b, i)[0]

def apfs_range(fp, size):
    fp.seek(512)
    hdr = fp.read(512)
    if len(hdr) != 512 or hdr[:8] != b"EFI PART":
        raise ValueError("GPT header missing")
    lba, n, entry_size = u64(hdr, 72), u32(hdr, 80), u32(hdr, 84)
    if not (1 <= n <= 4096 and 128 <= entry_size <= 1024):
        raise ValueError("Unsupported GPT table")
    if lba * 512 + n * entry_size > size:
        raise ValueError("GPT table outside disk")
    fp.seek(lba * 512)
    table = fp.read(n * entry_size)
    matches = []
    for i in range(n):
        ent = table[i * entry_size:(i + 1) * entry_size]
        if ent[:16] == GUID:
            start, end = u64(ent, 32) * 512, (u64(ent, 40) + 1) * 512
            if not (0 <= start < end <= size and start % BLOCK == 0):
                raise ValueError("Invalid APFS partition range")
            matches.append((start, end))
    if len(matches) != 1:
        raise ValueError("Expected one APFS partition")
    return matches[0]

def checksum(block):
    mod, s1, s2 = 0xffffffff, 0, 0
    for i in range(8, BLOCK, 4):
        s1 = (s1 + u32(block, i)) % mod
        s2 = (s2 + s1) % mod
    c1 = (mod - ((s1 + s2) % mod)) % mod
    c2 = (mod - ((s1 + c1) % mod)) % mod
    return (c2 << 32) | c1

def describe(b):
    if len(b) != BLOCK:
        return None
    typ, oid, xid = u32(b, 24), u64(b, 8), u64(b, 16)
    basetype = typ & 0xffff
    if not oid or not xid or basetype not in (1, 2, 3, 11, 13):
        return None
    if checksum(b) != u64(b, 0):
        return None
    return {"oid": hex(oid), "xid": hex(xid), "type": hex(typ),
            "subtype": hex(u32(b, 28)), "checksum_valid": True}

def run(source, compare, output):
    if source == compare or os.path.samefile(source, compare):
        raise ValueError("Input files are identical")
    size = source.stat().st_size
    if size != compare.stat().st_size or size % BLOCK:
        raise ValueError("RAW images must have equal, 4096-aligned lengths")
    if output.exists():
        raise ValueError("Output directory exists: refusing overwrite")
    output.mkdir(parents=False)
    changes, ranges, blocks = 0, 0, 0
    active = None
    try:
        with source.open("rb") as fa, compare.open("rb") as fb, \
             (output / "changed-blocks.jsonl").open("x") as records, \
             (output / "changed-ranges.jsonl").open("x") as rangefile:
            pa, pb = apfs_range(fa, size), apfs_range(fb, size)
            if pa != pb:
                raise ValueError("Source and comparison GPT APFS ranges differ")
            fa.seek(0)
            fb.seek(0)
            start, end = pa
            offset = 0
            while offset < size:
                want = min(CHUNK, size - offset)
                left, right = fa.read(want), fb.read(want)
                if len(left) != want or len(right) != want:
                    raise IOError("Unexpected EOF")
                if left == right:
                    blocks += want // BLOCK
                    if active is not None:
                        rangefile.write(json.dumps(active) + "\n")
                        ranges += 1
                        active = None
                else:
                    for j in range(0, want, BLOCK):
                        index = offset + j
                        a, b = left[j:j + BLOCK], right[j:j + BLOCK]
                        if a == b:
                            blocks += 1
                            if active is not None:
                                rangefile.write(json.dumps(active) + "\n")
                                ranges += 1
                                active = None
                            continue
                        changes += 1
                        inside = start <= index < end
                        rec = {
                            "disk_offset": index,
                            "apfs_block": (index - start) // BLOCK if inside else None,
                            "sha256_before": hashlib.sha256(a).hexdigest(),
                            "sha256_after": hashlib.sha256(b).hexdigest(),
                            "before": describe(a) if inside else None,
                            "after": describe(b) if inside else None,
                        }
                        records.write(json.dumps(rec) + "\n")
                        if active and active["end_disk_offset_exclusive"] == index and active["inside_apfs"] == inside:
                            active["end_disk_offset_exclusive"] += BLOCK
                            active["blocks"] += 1
                        else:
                            if active:
                                rangefile.write(json.dumps(active) + "\n")
                                ranges += 1
                            active = {"start_disk_offset": index,
                                      "end_disk_offset_exclusive": index + BLOCK,
                                      "blocks": 1, "inside_apfs": inside}
                offset += want
                if offset % (2 * 1024 ** 3) == 0 or offset == size:
                    print("%d/%d GiB scanned; changed blocks: %d" %
                          (offset // 1024 ** 3, size // 1024 ** 3, changes), flush=True)
            if active:
                rangefile.write(json.dumps(active) + "\n")
                ranges += 1
        summary = {
            "source_size_bytes": size,
            "apfs_start_bytes": start,
            "apfs_end_exclusive": end,
            "changed_blocks": changes,
            "unchanged_blocks": blocks,
            "changed_ranges": ranges,
            "warning": "Comparison only. No input file was modified.",
        }
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print("Report directory:", output)
    except Exception:
        # Keep diagnostic output rather than silently destroying it.
        raise

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True)
    p.add_argument("--compare", required=True)
    p.add_argument("--out-dir", required=True)
    args = p.parse_args()
    source = Path(args.source).expanduser().resolve(strict=True)
    compare = Path(args.compare).expanduser().resolve(strict=True)
    output = Path(args.out_dir).expanduser().absolute()
    if source.suffix.lower() != ".raw" or compare.suffix.lower() != ".raw":
        p.error("Both input files must be RAW images")
    if not source.is_file() or not compare.is_file():
        p.error("Inputs must be regular files")
    if output.is_symlink() or not output.parent.is_dir():
        p.error("Output directory must not be a symlink and parent must exist")
    run(source, compare, output)

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(2)

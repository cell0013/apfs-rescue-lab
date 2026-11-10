#!/usr/bin/env python3
"""Read-only GPT/APFS checkpoint inventory for offline whole-disk RAW images."""
import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

BLOCK = 4096
SECTOR = 512
APFS_GUID_LE = bytes.fromhex("ef57347c0000aa11aa1100306543ecac")

def u32(buf, off):
    return struct.unpack_from("<I", buf, off)[0]

def u64(buf, off):
    return struct.unpack_from("<Q", buf, off)[0]

def fletcher64(block):
    if len(block) != BLOCK:
        raise ValueError("APFS block must be 4096 bytes")
    mod, s1, s2 = 0xffffffff, 0, 0
    for i in range(8, BLOCK, 4):
        s1 = (s1 + u32(block, i)) % mod
        s2 = (s2 + s1) % mod
    c1 = (mod - ((s1 + s2) % mod)) % mod
    c2 = (mod - ((s1 + c1) % mod)) % mod
    return (c2 << 32) | c1

def object_header(block):
    return {
        "oid": hex(u64(block, 8)),
        "xid": hex(u64(block, 16)),
        "type": hex(u32(block, 24)),
        "subtype": hex(u32(block, 28)),
        "checksum_valid": u64(block, 0) == fletcher64(block),
    }

def exact_read(fp, offset, size, file_size):
    if offset < 0 or size < 0 or offset + size > file_size:
        raise ValueError("Read outside image bounds")
    fp.seek(offset)
    data = fp.read(size)
    if len(data) != size:
        raise IOError("Short read from image")
    return data

def apfs_partition(fp, size):
    hdr = exact_read(fp, 512, 512, size)
    if hdr[:8] != b"EFI PART":
        raise ValueError("GPT header missing")
    lba, n, entry_size = u64(hdr, 72), u32(hdr, 80), u32(hdr, 84)
    if not (1 <= n <= 4096 and 128 <= entry_size <= 1024):
        raise ValueError("Unexpected GPT table dimensions")
    table = exact_read(fp, lba * SECTOR, n * entry_size, size)
    found = []
    for i in range(n):
        item = table[i * entry_size:(i + 1) * entry_size]
        if item[:16] != APFS_GUID_LE:
            continue
        first, last = u64(item, 32), u64(item, 40)
        start, end = first * SECTOR, (last + 1) * SECTOR
        if first > last or end > size or start % BLOCK:
            raise ValueError("Invalid APFS partition bounds")
        found.append({"gpt_partition": i + 1, "start": start, "end": end})
    if len(found) != 1:
        raise ValueError("Expected exactly one APFS partition; found %d" % len(found))
    return found[0]

def analyze(path):
    size = path.stat().st_size
    if size % BLOCK:
        raise ValueError("Expected an aligned whole-disk image")
    with path.open("rb") as fp:
        part = apfs_partition(fp, size)
        first = exact_read(fp, part["start"], BLOCK, size)
        if first[32:36] != b"NXSB" or u32(first, 36) != BLOCK:
            raise ValueError("APFS container superblock not found at GPT offset")
        count_field = u32(first, 0x68)
        if count_field & 0x80000000:
            raise ValueError("Noncontiguous checkpoint descriptor area unsupported")
        count = count_field & 0x7fffffff
        base = u64(first, 0x70)
        if not (1 <= count <= 65536):
            raise ValueError("Invalid checkpoint descriptor block count")
        checkpoints = []
        for index in range(count):
            block_num = base + index
            offset = part["start"] + block_num * BLOCK
            if offset + BLOCK > part["end"]:
                raise ValueError("Descriptor area outside APFS partition")
            b = exact_read(fp, offset, BLOCK, size)
            if b[32:36] != b"NXSB":
                continue
            h = object_header(b)
            h.update({
                "descriptor_index": index,
                "physical_block": hex(block_num),
                "container_omap": hex(u64(b, 0xa0)),
                "sha256": hashlib.sha256(b).hexdigest(),
            })
            checkpoints.append(h)
        checkpoints.sort(key=lambda item: int(item["xid"], 16), reverse=True)
        return {
            "image_size_bytes": size,
            "apfs_partition": part,
            "container_header": object_header(first),
            "checkpoint_count": len(checkpoints),
            "checkpoints": checkpoints,
            "warning": "Read-only structural inspection, not a full B-tree validation or repair.",
        }

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, help="Offline whole-disk RAW image")
    ap.add_argument("--out", required=True, help="New JSON report file")
    args = ap.parse_args()
    source = Path(args.source).expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != ".raw":
        ap.error("Source must be an existing RAW file")
    out = Path(args.out).expanduser().absolute()
    if out.exists():
        ap.error("Output already exists: refusing overwrite")
    if not out.parent.is_dir() or out.is_symlink():
        ap.error("Report directory must exist; symlink outputs are forbidden")
    result = analyze(source)
    with out.open("x", encoding="utf-8") as fp:
        json.dump(result, fp, indent=2)
        fp.write("\n")
    print("APFS offset:", result["apfs_partition"]["start"])
    print("Checkpoint candidates:", result["checkpoint_count"])
    for item in result["checkpoints"][:12]:
        print(item["xid"], item["physical_block"], "valid_checksum:", item["checksum_valid"])
    print("Report:", out)
    print("No input image modified.")

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(2)

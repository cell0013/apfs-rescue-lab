#!/usr/bin/env python3
"""Experimental checkpoint selector for an OFFLINE macOS APFS RAW image.

This does not perform a true APFS rollback. It clones the input via macOS
'cp -c' and invalidates newer NXSB checkpoint magic bytes on the CLONE.
Never run on your only copy; booting/writing is not guaranteed safe.
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
APFS_GUID = bytes.fromhex("ef57347c0000aa11aa1100306543ecac")

def u32(b, off):
    return struct.unpack_from("<I", b, off)[0]

def u64(b, off):
    return struct.unpack_from("<Q", b, off)[0]

def find_apfs(f):
    f.seek(512)
    hdr = f.read(512)
    if len(hdr) != 512 or hdr[:8] != b"EFI PART":
        raise ValueError("GPT header missing")
    lba, n, size = u64(hdr, 72), u32(hdr, 80), u32(hdr, 84)
    if not (1 <= n <= 4096 and 128 <= size <= 1024):
        raise ValueError("Unexpected GPT table")
    f.seek(0, os.SEEK_END)
    image_size = f.tell()
    if lba * 512 + n * size > image_size:
        raise ValueError("GPT table out of bounds")
    for i in range(n):
        f.seek(lba * 512 + i * size)
        entry = f.read(size)
        if entry[:16] == APFS_GUID:
            start = u64(entry, 32) * 512
            end = (u64(entry, 40) + 1) * 512
            if not (0 < start < end <= image_size and start % BLOCK == 0):
                raise ValueError("APFS partition bounds invalid")
            return start, end
    raise ValueError("APFS partition not found")

def read_block(f, start, end, num):
    off = start + num * BLOCK
    if num < 0 or off + BLOCK > end:
        raise ValueError("APFS block out of bounds")
    f.seek(off)
    b = f.read(BLOCK)
    if len(b) != BLOCK:
        raise ValueError("Truncated APFS block")
    return b

def checksum_ok(b):
    if len(b) != BLOCK:
        return False
    mod, s1, s2 = 0xffffffff, 0, 0
    for off in range(8, BLOCK, 4):
        s1 = (s1 + u32(b, off)) % mod
        s2 = (s2 + s1) % mod
    c1 = (mod - ((s1 + s2) % mod)) % mod
    c2 = (mod - ((s1 + c1) % mod)) % mod
    return u64(b, 0) == ((c2 << 32) | c1)

def valid_nxsb(b):
    return (checksum_ok(b) and b[32:36] == b"NXSB" and u64(b, 8) == 1
            and (u32(b, 24) & 0xffff) == 1 and u32(b, 36) == BLOCK)

def checkpoints(f):
    start, end = find_apfs(f)
    primary = read_block(f, start, end, 0)
    if not valid_nxsb(primary):
        raise ValueError("Unsupported primary APFS superblock")
    count, base = u32(primary, 104), u64(primary, 112)
    if count & 0x80000000 or not (1 <= count <= 65536) or base < 1:
        raise ValueError("Unsupported checkpoint descriptor layout")
    found = []
    for i in range(count):
        number = base + i
        b = read_block(f, start, end, number)
        if valid_nxsb(b):
            found.append({
                "physical_block": number, "xid": u64(b, 16),
                "sha256": hashlib.sha256(b).hexdigest()
            })
    return start, end, found

def scan(path):
    with path.open("rb") as f:
        _, _, items = checkpoints(f)
    print("Checkpoint superblock candidates:", len(items))
    for item in sorted(items, key=lambda x: x["xid"], reverse=True)[:20]:
        print(hex(item["xid"]), "@", hex(item["physical_block"]))

def build(source, output, target, acknowledged):
    if not acknowledged:
        raise ValueError("Read DISCLAIMER.md and explicitly acknowledge the risk")
    if sys.platform != "darwin":
        raise ValueError("Requires macOS and an APFS filesystem supporting cp -c")
    if not source.is_file() or source.is_symlink() or source.suffix.lower() != ".raw":
        raise ValueError("Source must be an unmounted whole-disk RAW regular file")
    if output.exists() or output.is_symlink() or source == output:
        raise ValueError("Output must be a NEW, different filename")
    if not output.parent.is_dir() or output.parent.is_symlink() or output.suffix.lower() != ".raw":
        raise ValueError("Output must be a NEW RAW file in an existing directory")
    report_path = output.with_suffix(".raw.json")
    if report_path.exists() or report_path.is_symlink():
        raise ValueError("Candidate report already exists; refusing to overwrite it")
    with source.open("rb") as f:
        start, end, items = checkpoints(f)
    newer = sorted((x for x in items if x["xid"] > target),
                   key=lambda x: x["xid"], reverse=True)
    if sum(x["xid"] == target for x in items) != 1:
        raise ValueError("Target checkpoint does not exist uniquely")
    if not (1 <= len(newer) <= 20):
        raise ValueError("Refusing to invalidate 0 or more than 20 checkpoint headers")
    print("EXPERIMENTAL; NOT a true rollback; no warranty.")
    print("Candidate XID:", hex(target), "Newer headers to invalidate:", len(newer))
    subprocess.run(["/bin/cp", "-c", str(source), str(output)], check=True)
    try:
        if output.stat().st_size != source.stat().st_size:
            raise ValueError("Clone has unexpected size")
        with output.open("r+b") as f:
            for item in newer:
                number = item["physical_block"]
                b = read_block(f, start, end, number)
                if hashlib.sha256(b).hexdigest() != item["sha256"]:
                    raise ValueError("Clone checkpoint differs from source")
                f.seek(start + number * BLOCK + 32)
                f.write(bytes(4))
            f.flush()
            os.fsync(f.fileno())
        with output.open("rb") as f:
            _, _, remaining = checkpoints(f)
        if any(x["xid"] > target for x in remaining) or not any(x["xid"] == target for x in remaining):
            raise ValueError("Post-write verification failed")
        report = {"target_xid": hex(target), "modified_blocks":
                  [{"xid": hex(x["xid"]), "block": hex(x["physical_block"])} for x in newer],
                  "warning": "EXPERIMENTAL; not a true rollback. Never trust this for continued writes."}
        with report_path.open("x", encoding="utf-8") as report_file:
            report_file.write(json.dumps(report, indent=2) + "\n")
        print("Created:", output)
        print("Read-only fsck and file validation required BEFORE any VM test.")
    except Exception:
        print("Unverified test candidate remains at:", output, file=sys.stderr)
        raise

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["scan", "build"])
    p.add_argument("--source", required=True)
    p.add_argument("--output")
    p.add_argument("--xid", type=lambda x: int(x, 0))
    p.add_argument("--i-understand-this-can-destroy-data", action="store_true")
    a = p.parse_args()
    source = Path(a.source).expanduser().resolve(strict=True)
    if a.mode == "scan":
        scan(source)
        return
    if not a.output or a.xid is None:
        p.error("build requires --output and explicit --xid")
    build(source, Path(a.output).expanduser().absolute(), a.xid,
          a.i_understand_this_can_destroy_data)

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        print("ERROR:", e, file=sys.stderr)
        sys.exit(2)

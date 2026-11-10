"""Synthetic regression tests for automatic checkpoint nomination.

Creates tiny fake GPT/APFS images; no personal disk data or macOS installation.
"""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("apfs_rescue", ROOT / "apfs_rescue.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

BLOCK = 4096
START = 1024 * 1024
PART_BLOCKS = 2048
SIZE = 16 * 1024 * 1024
GUID = bytes.fromhex("ef57347c0000aa11aa1100306543ecac")

def pack_u32(buf, off, v):
    struct.pack_into("<I", buf, off, v)

def pack_u64(buf, off, v):
    struct.pack_into("<Q", buf, off, v)

def obj(oid, xid, typ, sub=0):
    b = bytearray(BLOCK)
    pack_u64(b, 8, oid)
    pack_u64(b, 16, xid)
    pack_u32(b, 24, typ)
    pack_u32(b, 28, sub)
    return b

def signed(b):
    mod, s1, s2 = 0xffffffff, 0, 0
    for i in range(8, BLOCK, 4):
        s1 = (s1 + struct.unpack_from("<I", b, i)[0]) % mod
        s2 = (s2 + s1) % mod
    c1 = (mod - (s1 + s2) % mod) % mod
    c2 = (mod - (s1 + c1) % mod) % mod
    pack_u64(b, 0, (c2 << 32) | c1)
    return b

def make_image(path, multiple=False):
    with path.open("wb") as f:
        f.truncate(SIZE)
    with path.open("r+b") as f:
        def write_block(n, b):
            f.seek(START + n * BLOCK)
            f.write(signed(b))
        h = bytearray(512)
        h[:8] = b"EFI PART"
        pack_u64(h, 72, 2)
        pack_u32(h, 80, 1)
        pack_u32(h, 84, 128)
        f.seek(512)
        f.write(h)
        ent = bytearray(128)
        ent[:16] = GUID
        pack_u64(ent, 32, START // 512)
        pack_u64(ent, 40, START // 512 + PART_BLOCKS * BLOCK // 512 - 1)
        f.seek(1024)
        f.write(ent)
        nx = obj(1, 1, 0x80000001)
        nx[32:36] = b"NXSB"
        pack_u32(nx, 36, BLOCK)
        pack_u32(nx, 104, 4)
        pack_u64(nx, 112, 10)
        write_block(0, nx)
        for i, xid in enumerate((0x104, 0x103)):
            cp = bytearray(nx)
            pack_u64(cp, 16, xid)
            write_block(10 + i, cp)
        for volume_oid in ([0x403, 0x406] if multiple else [0x403]):
            delta = (volume_oid - 0x403) * 30
            # Latest volume header has invalid OMAP pointer.
            latest = obj(volume_oid, 0x104, 13)
            latest[32:36] = b"APSB"
            latest[240:256] = (volume_oid.to_bytes(4, "little") * 4)
            pack_u64(latest, 256, 1)  # APFS_FS_UNENCRYPTED
            struct.pack_into("<H", latest, 0x3c4, 0x40)  # APFS_VOL_ROLE_DATA
            pack_u64(latest, 128, 500 + delta)
            write_block(100 + delta, latest)
            old = obj(volume_oid, 0x103, 13)
            old[32:36] = b"APSB"
            old[240:256] = latest[240:256]
            pack_u64(old, 256, 1)
            struct.pack_into("<H", old, 0x3c4, 0x40)
            pack_u64(old, 128, 501 + delta)
            write_block(101 + delta, old)
            om = obj(501 + delta, 0x103, 0x4000000b)
            pack_u64(om, 48, 502 + delta)
            write_block(501 + delta, om)
            tree = obj(502 + delta, 0x103, 0x40000002, 11)
            write_block(502 + delta, tree)

class TestAutomaticRecovery(unittest.TestCase):
    def test_nominates_one_older_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.raw"
            make_image(path)
            report = app.nominate(path, 1)
            self.assertEqual(report["status"], "candidate_nominated")
            self.assertEqual(report["nomination"]["selected_xid"], "0x103")

    def test_refuses_ambiguous_volumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.raw"
            make_image(path, multiple=True)
            report = app.nominate(path, 1)
            self.assertEqual(report["status"], "manual_review_required")
            self.assertIsNone(report["nomination"])

    def test_rejects_encrypted_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "encrypted.raw"
            make_image(path)
            with path.open("r+b") as f:
                # Set latest Data volume flags to encrypted and repair checksum.
                f.seek(START + 100 * BLOCK)
                block = bytearray(f.read(BLOCK))
                pack_u64(block, 256, 0)
                f.seek(START + 100 * BLOCK)
                f.write(signed(block))
                f.seek(START + 101 * BLOCK)
                block = bytearray(f.read(BLOCK))
                pack_u64(block, 256, 0)
                f.seek(START + 101 * BLOCK)
                f.write(signed(block))
            report = app.nominate(path, 1)
            self.assertIsNone(report["nomination"])

if __name__ == "__main__":
    unittest.main()

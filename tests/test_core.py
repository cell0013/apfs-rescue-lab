"""Small synthetic checks for the public read-only tools."""
import importlib.util
import struct
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"

def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

analyzer = load("apfs_analyzer")
diff = load("block_diff")

class TestAPFS(unittest.TestCase):
    def test_fletcher_agreement(self):
        b = bytearray(4096)
        struct.pack_into("<Q", b, 8, 0x403)
        struct.pack_into("<Q", b, 16, 0x100)
        struct.pack_into("<I", b, 24, 0x4000000b)
        self.assertEqual(analyzer.fletcher64(b), diff.checksum(b))

    def test_known_checksum(self):
        b = bytearray(4096)
        struct.pack_into("<Q", b, 8, 0x403)
        struct.pack_into("<Q", b, 16, 0x100)
        struct.pack_into("<I", b, 24, 0x4000000b)
        struct.pack_into("<Q", b, 0, analyzer.fletcher64(b))
        self.assertTrue(analyzer.object_header(b)["checksum_valid"])
        b[51] ^= 1
        self.assertFalse(analyzer.object_header(b)["checksum_valid"])

if __name__ == "__main__":
    unittest.main()

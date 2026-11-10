"""Integration checks for checkpoint cloning using a synthetic RAW image.

These tests never use user disks, VM images, or confidential data.
They run the high-risk code only on a 16 MiB generated throwaway image.
"""
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from test_autoselect import make_image, START, BLOCK
from experimental import checkpoint_select

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(sys.platform == "darwin", "macOS APFS clonefile required")
class TestCloneOnly(unittest.TestCase):
    def test_only_target_header_modified_on_new_clone(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "fixture.raw"
            candidate = Path(tmp) / "candidate.raw"
            make_image(original)
            original_bytes = original.read_bytes()
            expected = bytearray(original_bytes)
            # Newest NXSB descriptor resides at APFS physical block 10.
            expected[START + 10 * BLOCK + 32:START + 10 * BLOCK + 36] = b"\0\0\0\0"
            result = subprocess.run([sys.executable, str(ROOT / 'apfs_rescue.py'),
                'recover', '--source', str(original), '--output', str(candidate),
                '--i-understand-this-can-destroy-data'],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + '\n' + result.stderr)
            self.assertEqual(original.read_bytes(), original_bytes)
            self.assertEqual(candidate.read_bytes(), bytes(expected))
            self.assertTrue(candidate.with_suffix(".raw.json").exists())
            with candidate.open("rb") as f:
                _, _, cks = checkpoint_select.checkpoints(f)
            self.assertEqual([i["xid"] for i in cks], [0x103])

    def test_refuses_existing_report_without_writing_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "fixture.raw"
            candidate = Path(tmp) / "candidate.raw"
            make_image(original)
            report = candidate.with_suffix(".raw.json")
            report.write_text("do not change\n")
            before = original.read_bytes()
            with self.assertRaises(ValueError):
                checkpoint_select.build(original, candidate, 0x103, True)
            self.assertFalse(candidate.exists())
            self.assertEqual(original.read_bytes(), before)
            self.assertEqual(report.read_text(), "do not change\n")

    def test_requires_risk_acknowledgment(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "fixture.raw"
            candidate = Path(tmp) / "candidate.raw"
            make_image(original)
            with self.assertRaises(ValueError):
                checkpoint_select.build(original, candidate, 0x103, False)
            self.assertFalse(candidate.exists())

if __name__ == "__main__":
    unittest.main()

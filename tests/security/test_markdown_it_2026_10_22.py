"""HRMS markdown-it 14.3.3 security lock regression (2026-10-22)."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
LOCKS = ROOT / "tools" / "foundation" / "hrms-locks"


class HrmsMarkdownItLockTests(unittest.TestCase):
    def test_frontend_and_roster_pin_patched_markdown_it(self):
        for tree in ("frontend", "roster"):
            with self.subTest(tree=tree):
                package = json.loads((LOCKS / tree / "package.json").read_text(encoding="utf-8"))
                self.assertEqual(package["resolutions"]["markdown-it"], "14.3.3")
                lock = (LOCKS / tree / "yarn.lock").read_text(encoding="utf-8")
                self.assertIn('markdown-it@14.3.3, markdown-it@^14.0.0:', lock)
                self.assertIn('version "14.3.3"', lock)
                self.assertNotIn('version "14.3.2"', lock)

    def test_manifest_records_the_security_reason(self):
        manifest = json.loads((LOCKS / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("GHSA-vfgh-jcmw-g37q", manifest["purpose"])
        self.assertIn("GHSA-gfr2-rv44-r23c", manifest["purpose"])


if __name__ == "__main__":
    unittest.main()

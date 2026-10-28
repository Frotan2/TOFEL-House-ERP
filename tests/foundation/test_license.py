"""The product license is MIT (owner decision D11): LICENSE and app metadata agree."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class LicenseTests(unittest.TestCase):
    def test_license_file_is_mit(self):
        self.assertTrue((ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License"))

    def test_every_owned_app_declares_mit(self):
        hooks = sorted(ROOT.glob("apps/*/*/hooks.py"))
        self.assertEqual(len(hooks), 2)
        for path in hooks:
            self.assertIn('app_license = "MIT"', path.read_text(encoding="utf-8"), path)


if __name__ == "__main__":
    unittest.main()

"""Integrity/transport helper tests, not Education functional tests."""
import base64
import hashlib
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mirror", ROOT / "tools/foundation/seed_yarn_mirror.py")
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)


class MirrorTests(unittest.TestCase):
    def test_scoped_filename_and_npm_transport(self):
        lock = '''"@example/lib@1":
  version "1.0.0"
  resolved "https://registry.yarnpkg.com/@example/lib/-/lib-1.0.0.tgz#abc"
  integrity sha512-example
'''
        row = mirror.entries_from_lock(lock)[0]
        self.assertEqual(row["filename"], "@example-lib-1.0.0.tgz")
        self.assertEqual(row["url"], "https://registry.npmjs.org/@example/lib/-/lib-1.0.0.tgz")

    def test_unknown_origin_and_missing_integrity_rejected(self):
        for text in [
            'x:\n  version "1"\n  resolved "https://example.invalid/x.tgz"\n  integrity sha512-x',
            'x:\n  version "1"\n  resolved "https://registry.yarnpkg.com/x/-/x.tgz"',
            'x:\n  version "1"',
        ]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                mirror.entries_from_lock(text)

    def test_integrity_mismatch_rejected(self):
        good = "sha512-" + base64.b64encode(hashlib.sha512(b"expected").digest()).decode()
        mirror.verify(b"expected", good)
        with self.assertRaises(ValueError):
            mirror.verify(b"tampered", good)

    def test_strongest_hash_required(self):
        weak = "sha1-" + base64.b64encode(hashlib.sha1(b"data").digest()).decode()
        with self.assertRaises(ValueError):
            mirror.verify(b"data", weak + " sha512-invalid")


if __name__ == "__main__":
    unittest.main()

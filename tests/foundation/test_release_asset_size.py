"""The actual customer ZIP must fit the host's release-asset boundary."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.release import create_customer_package as packaging


class ReleaseAssetSizeTests(unittest.TestCase):
    def test_zip_limit_is_strict_and_sidecar_hashes_the_zip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def package(case):
                directory = root / case / "kit"
                directory.mkdir(parents=True)
                (directory / "asset.txt").write_bytes(b"provider package test payload")
                return directory

            reference = packaging.make_zip(package("reference"))
            size = reference.stat().st_size
            self.assertEqual(reference.with_suffix(".zip.sha256").read_text().split()[0], packaging.sha256(reference))
            with patch.object(packaging, "MAX_RELEASE_ASSET_BYTES", size + 1):
                self.assertTrue(packaging.make_zip(package("below")).is_file())
            for label, limit in (("at", size), ("above", size - 1)):
                with self.subTest(label=label), patch.object(packaging, "MAX_RELEASE_ASSET_BYTES", limit):
                    with self.assertRaisesRegex(ValueError, "2 GiB asset limit"):
                        packaging.make_zip(package(label))
                    self.assertFalse((root / label / "kit.zip.sha256").exists())


if __name__ == "__main__":
    unittest.main()

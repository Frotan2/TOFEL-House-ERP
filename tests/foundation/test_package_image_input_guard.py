"""Regression tests for source-side customer image archive path safety.

The packaging tool must refuse an image supplied via a symbolic link before
reading CI gate evidence or creating any output. These tests never build a
Docker image or touch customer data.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.release import create_customer_package as packager


class PrebuiltImagePathTests(unittest.TestCase):
    def test_existing_image_symlink_is_refused_before_other_inputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            target = root / "real-image.tar"
            target.write_bytes(b"not an actual image; this test must reject early")
            linked_image = root / "linked-image.tar"
            linked_image.symlink_to(target)
            output = root / "out"

            with patch.object(
                packager, "load_gate_evidence",
                side_effect=AssertionError("CI gates must not be touched"),
            ):
                with self.assertRaisesRegex(ValueError, "regular prebuilt image archive"):
                    packager.create_package(
                        source=source,
                        output=output,
                        image_archive=linked_image,
                        image_labels={
                            "org.toefl-house.source-eol": "lf-v1",
                            "org.toefl-house.source-revision": "a" * 40,
                            "org.toefl-house.release-version": "test-1",
                        },
                        version="test-1",
                        source_revision="a" * 40,
                        gate_evidence=root / "not-read.json",
                        provider_attestation="TEST ONLY",
                    )
            self.assertFalse(output.exists())
            self.assertTrue(target.is_file())
            self.assertTrue(linked_image.is_symlink())

    def test_original_symlink_path_not_masked_by_resolve(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "image.tar"
            target.write_bytes(b"opaque image bytes")
            path = root / "alias.tar"
            path.symlink_to(target)
            self.assertTrue(path.is_symlink())
            self.assertFalse(path.resolve().is_symlink())
            # A path-based input guard must run BEFORE Path.resolve().
            self.assertNotEqual(path, path.resolve())


if __name__ == "__main__":
    unittest.main()

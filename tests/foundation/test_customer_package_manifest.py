"""Provider-side customer package identity and allowlist contracts."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.release.create_customer_package import create_package


ROOT = Path(__file__).resolve().parents[2]


class CustomerPackageManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="customer-package-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.revision = "a" * 40
        self.version = "ci-test-20261023"
        self.image = self.tmp / "image.tar"
        self.image.write_bytes(b"synthetic prebuilt image archive")
        self.labels = {
            "org.toefl-house.source-eol": "lf-v1",
            "org.toefl-house.source-revision": self.revision,
            "org.toefl-house.release-version": self.version,
        }

    def test_package_binds_image_source_and_dependency_matrix(self):
        package, archive, manifest = create_package(
            source=ROOT,
            output=self.tmp / "out",
            image_archive=self.image,
            image_labels=self.labels,
            version=self.version,
            source_revision=self.revision,
            provider_attestation="synthetic-test-attestation",
        )
        release = package / "product" / "release"
        saved = json.loads((release / "release-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["source_revision"], self.revision)
        self.assertEqual(saved["version"], self.version)
        self.assertEqual(saved["image"]["sha256"], manifest["image"]["sha256"])
        self.assertEqual(saved["image"]["labels"], self.labels)
        self.assertTrue(archive.is_file())
        self.assertTrue((release / "release-manifest.json.sha256").is_file())
        self.assertFalse((package / "product" / "data").exists())
        self.assertFalse((package / "apps").exists())

    def test_image_identity_mismatch_fails_before_package_creation(self):
        with self.assertRaisesRegex(ValueError, "source revision"):
            create_package(
                source=ROOT,
                output=self.tmp / "out",
                image_archive=self.image,
                image_labels=self.labels,
                version=self.version,
                source_revision="b" * 40,
                provider_attestation="synthetic-test-attestation",
            )
        self.assertFalse((self.tmp / "out").exists())


if __name__ == "__main__":
    unittest.main()

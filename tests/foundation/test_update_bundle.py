"""Provider-side release signing for the Windows update channel (Issue #40).

The customer engine is only useful if the provider can produce documents it
accepts, and if a tampered download, a foreign key or a modified image is
refused by that same engine. These tests sign with a real RSA key through the
real CLI and then re-verify with the shipped engine, because a mock signer
would not prove anything about the trust boundary.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "release" / "create_update_bundle.py"
sys.path.insert(0, str(ROOT / "product"))
sys.path.insert(0, str(ROOT / "tests" / "foundation"))

import update_engine as engine  # noqa: E402
from test_customer_package_manifest import write_image_archive  # noqa: E402

VERSION = "2026.11.01"
NEXT_VERSION = "2026.11.02"
REVISION = "a" * 40
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def openssl(*arguments: str) -> bytes:
    return subprocess.run(["openssl", *arguments], check=True, capture_output=True).stdout


@unittest.skipUnless(shutil.which("openssl"), "openssl is required to sign and verify releases")
class UpdateBundleCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keyring = Path(tempfile.mkdtemp(prefix="update-bundle-keys-"))
        cls.private_key = cls.keyring / "provider.pem"
        cls.other_key = cls.keyring / "other.pem"
        openssl("genrsa", "-out", str(cls.private_key), "2048")
        openssl("genrsa", "-out", str(cls.other_key), "2048")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.keyring, ignore_errors=True)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="update-bundle-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.release = self.tmp / "release"
        self.release.mkdir()
        self.archive = self.release / "toefl-house-erp-app.tar"
        self.labels = {
            "org.toefl-house.source-eol": "lf-v1",
            "org.toefl-house.source-revision": REVISION,
            "org.toefl-house.release-version": VERSION,
        }
        self.config_digest = write_image_archive(self.archive, self.labels)
        self.out = self.tmp / "channel"
        self.trust_store = self.tmp / "trust" / "trust-store.json"
        self.write_manifest()

    def write_manifest(self, **overrides):
        import hashlib

        manifest = {
            "schema_version": 1,
            "product": "TOEFL House ERP",
            "version": VERSION,
            "release_status": "PRODUCTION RELEASE",
            "production_authorization": "AUTHORIZED",
            "source_revision": REVISION,
            "image": {
                "tag": "toefl-house-erp-app:local",
                "config_digest": self.config_digest,
                "archive": "product/release/toefl-house-erp-app.tar",
                "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
                "size_bytes": self.archive.stat().st_size,
                "labels": self.labels,
            },
            "provider_attestation": {"type": "synthetic test release", "required_for_delivery": True},
            "generated_utc": "2026-11-01T00:00:00Z",
        }
        manifest.update(overrides)
        (self.release / "release-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def run_tool(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(TOOL), *arguments],
                              capture_output=True, text=True, cwd=str(ROOT))

    def bundle(self, *extra: str, key: Path | None = None, out: Path | None = None):
        return self.run_tool(
            "bundle",
            "--release-dir", str(self.release),
            "--private-key", str(key or self.private_key),
            "--key-id", "provider-2026",
            "--out", str(out or self.out),
            "--trust-store-out", str(self.trust_store),
            "--target-schema-version", "frappe-v16-2026-11",
            *extra,
        )

    def stage_trust_store(self, out: Path | None = None) -> Path:
        """The engine resolves every path inside the product folder.

        On a customer PC the anchor lives at ``data/updates/trust-store.json``;
        for these checks it is copied next to the signed documents.
        """
        out = out or self.out
        staged = out / "trust-store.json"
        if not staged.exists():
            shutil.copy2(self.trust_store, staged)
        return staged

    def verify_published(self, *, out: Path | None = None, layers: bool = False) -> dict:
        out = out or self.out
        self.stage_trust_store(out)
        return engine.verify_release({
            "action": "verify-release",
            "product_root": str(out),
            "trust_store": "trust-store.json",
            "manifest": "update.json",
            "signature": "update.json.sig",
            "archive": "toefl-house-erp-app.tar",
            "verify_layers": layers,
        }, now=NOW)


class BundleTests(UpdateBundleCase):
    def test_a_signed_bundle_is_accepted_by_the_customer_engine(self):
        completed = self.bundle("--copy-archive")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertEqual(summary["status"], "signed")
        self.assertEqual(summary["version"], VERSION)
        self.assertEqual(summary["release_sequence"], engine.release_sequence(VERSION))
        self.assertEqual(summary["engine_verification"], "verified")
        self.assertEqual(summary["release_status"], "PRODUCTION RELEASE")
        self.assertEqual(summary["production_authorization"], "AUTHORIZED")
        self.assertEqual(summary["trust_store"], str(self.trust_store))
        for name in ("update.json", "update.json.sig", "index.json", "toefl-house-erp-app.tar"):
            self.assertIn(name, summary["files"])
        verified = self.verify_published(layers=True)
        self.assertEqual(verified["status"], "verified")
        self.assertEqual(verified["target"]["version"], VERSION)
        self.assertEqual(verified["target"]["image"]["config_digest"], self.config_digest)

    def test_the_manifest_keeps_every_protection_the_engine_signed_for(self):
        completed = self.bundle("--copy-archive")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        manifest = json.loads((self.out / "update.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["document_type"], engine.DOCUMENT_UPDATE)
        self.assertEqual(manifest["image"]["sha256"], engine.sha256_file(self.archive))
        self.assertEqual(manifest["image"]["labels"], self.labels)
        self.assertTrue(manifest["requirements"]["backup"]["required"])
        self.assertTrue(manifest["database"]["requires_verified_backup"])
        self.assertFalse(manifest["database"]["reversible"])
        self.assertTrue(manifest["requirements"]["recovery_authorization"]["required"])
        self.assertGreaterEqual(manifest["requirements"]["minimum_free_bytes"], engine.MIN_FREE_BYTES_FLOOR)
        self.assertEqual(manifest["signature"], {"key_id": "provider-2026",
                                                 "algorithm": "rsa-pkcs1v15-sha256"})

    def test_the_index_names_only_the_signed_package(self):
        completed = self.bundle("--copy-archive")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        index = json.loads((self.out / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["document_type"], "toefl-house-erp-update-index")
        self.assertEqual(index["channel"], "stable")
        latest = index["latest"]
        self.assertEqual(latest["manifest"], "update.json")
        self.assertEqual(latest["signature"], "update.json.sig")
        self.assertEqual(latest["archive"], "toefl-house-erp-app.tar")
        self.assertEqual(latest["archive_sha256"], engine.sha256_file(self.archive))
        self.assertEqual(latest["archive_size_bytes"], self.archive.stat().st_size)
        self.assertEqual(latest["release_sequence"], engine.release_sequence(VERSION))

    def test_a_test_package_can_be_signed_but_is_labelled_non_installable(self):
        self.write_manifest(release_status="TEST PACKAGE - NO REAL DATA", production_authorization="REJECT")
        completed = self.bundle("--copy-archive")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertEqual(summary["release_status"], "TEST PACKAGE - NO REAL DATA")
        self.assertEqual(summary["production_authorization"], "REJECT")
        self.assertEqual(summary["customer_policy"],
                         "every customer engine refuses this release until the provider "
                         "issues a production-authorized package")
        manifest = json.loads((self.out / "update.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["release_status"], "TEST PACKAGE - NO REAL DATA")
        self.assertEqual(manifest["production_authorization"], "REJECT")

    def test_a_version_without_a_date_derived_sequence_needs_an_explicit_one(self):
        # A synthetic CI version still has to be labelled consistently, so the
        # refusal that is tested here is the sequence rule, not a label drift.
        self.labels["org.toefl-house.release-version"] = "ci-windows-package"
        self.config_digest = write_image_archive(self.archive, self.labels)
        self.write_manifest(version="ci-windows-package")
        completed = self.bundle()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--sequence", completed.stderr)
        self.assertFalse(self.out.exists())


class BundleRefusalTests(UpdateBundleCase):
    def test_tampered_manifest_is_rejected_by_the_engine(self):
        completed = self.bundle("--copy-archive")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        # A trailing byte keeps the document valid JSON and the labels intact,
        # so the only protection left to catch it is the signature itself.
        with (self.out / "update.json").open("ab") as handle:
            handle.write(b" ")
        with self.assertRaises(engine.UpdateError) as caught:
            self.verify_published()
        self.assertEqual(caught.exception.code, "release.signature.invalid")

    def test_wrong_signing_key_is_rejected_by_the_engine(self):
        completed = self.bundle("--copy-archive")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        stolen = self.tmp / "attacker-channel"
        shutil.copytree(self.out, stolen)
        self.stage_trust_store(stolen)
        # Re-sign the same manifest with a key the customer does not trust.
        signature = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(self.other_key), str(stolen / "update.json")],
            check=True, capture_output=True).stdout
        import base64
        envelope = json.loads((stolen / "update.json.sig").read_text(encoding="utf-8"))
        envelope["signature_b64"] = base64.b64encode(signature).decode("ascii")
        (stolen / "update.json.sig").write_text(json.dumps(envelope) + "\n", encoding="utf-8")
        with self.assertRaises(engine.UpdateError) as caught:
            self.verify_published(out=stolen)
        self.assertEqual(caught.exception.code, "release.signature.invalid")

    def test_modified_archive_is_refused_before_any_import(self):
        completed = self.bundle("--copy-archive")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        archive = self.out / "toefl-house-erp-app.tar"
        raw = bytearray(archive.read_bytes())
        raw[-1] ^= 0xFF
        archive.write_bytes(bytes(raw))
        with self.assertRaises(engine.UpdateError) as caught:
            self.verify_published()
        self.assertEqual(caught.exception.code, "release.archive.hash_mismatch")

    def test_archive_that_does_not_match_the_package_manifest_is_refused(self):
        manifest_path = self.release / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["image"]["sha256"] = "b" * 64
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        completed = self.bundle()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("SHA-256", completed.stderr)

    def test_foreign_image_tag_is_refused(self):
        self.write_manifest()
        manifest_path = self.release / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["image"]["tag"] = "attacker/app:latest"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        completed = self.bundle()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("image tag", completed.stderr)

    def test_a_release_sequence_override_cannot_disagree_with_the_version(self):
        completed = self.bundle("--sequence", "7")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--sequence", completed.stderr)

    def test_an_existing_output_folder_is_never_overwritten(self):
        completed = self.bundle("--copy-archive")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        before = sorted(path.name for path in self.out.iterdir())
        again = self.bundle("--copy-archive")
        self.assertEqual(again.returncode, 2)
        self.assertIn("refusing to overwrite", again.stderr)
        self.assertEqual(sorted(path.name for path in self.out.iterdir()), before)

    def test_an_existing_trust_store_is_never_overwritten(self):
        self.assertEqual(self.bundle("--copy-archive").returncode, 0)
        fresh_out = self.tmp / "second-channel"
        completed = self.bundle("--copy-archive", out=fresh_out)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("refusing to overwrite an existing trust store", completed.stderr)

    def test_a_package_checksum_mismatch_is_refused(self):
        (self.release / "release-manifest.json.sha256").write_text(
            "0" * 64 + "  release-manifest.json\n", encoding="utf-8")
        completed = self.bundle()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("published checksum", completed.stderr)


class TrustStoreTests(UpdateBundleCase):
    def test_the_trust_anchor_loads_in_the_customer_engine(self):
        completed = self.run_tool("trust-store", "--private-key", str(self.private_key),
                                  "--key-id", "provider-2026", "--out", str(self.trust_store))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        store = engine.load_trust_store(self.trust_store, now=NOW)
        self.assertEqual(len(store["keys"]), 1)
        key = store["keys"][0]
        self.assertEqual(key["key_id"], "provider-2026")
        self.assertEqual(key["exponent"], 65537)
        self.assertIn("update-manifest", key["purposes"])
        self.assertIn("recovery-authorization", key["purposes"])

    def test_an_untrusted_key_id_is_refused(self):
        completed = self.run_tool("trust-store", "--private-key", str(self.private_key),
                                  "--key-id", "Provider Key!", "--out", str(self.trust_store))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("key id", completed.stderr)


class RecoveryAuthorizationTests(UpdateBundleCase):
    description = "synthetic owner recovery authorization"

    def authorization(self, **overrides):
        issued = NOW - timedelta(minutes=5)
        document = {
            "schema_version": 1,
            "document_type": engine.DOCUMENT_RECOVERY,
            "site": engine.SITE_NAME,
            "scope": "site-update",
            "issued_utc": issued.isoformat().replace("+00:00", "Z"),
            "expires_utc": (issued + timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
            "owner_key_custody_verified": True,
            "rehearsal_restore_verified": True,
            "backup_receipt_sha256": "c" * 64,
            "authorized_by": "owner",
            "attested_by": "toefl-house-support",
        }
        document.update(overrides)
        path = self.tmp / "recovery-authorization.json"
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def test_the_provider_can_sign_a_bound_recovery_authorization(self):
        self.assertEqual(self.run_tool(
            "trust-store", "--private-key", str(self.private_key),
            "--key-id", "provider-2026", "--out", str(self.trust_store)).returncode, 0)
        document = self.authorization()
        signature = self.tmp / "recovery-authorization.sig"
        completed = self.run_tool("sign", "--document", str(document),
                                  "--private-key", str(self.private_key),
                                  "--key-id", "provider-2026",
                                  "--document-type", "recovery-authorization",
                                  "--out", str(signature))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        store = engine.load_trust_store(self.trust_store, now=NOW)
        result = engine.validate_recovery_authorization(
            document, signature, store, site=engine.SITE_NAME,
            receipt_sha256="c" * 64, now=NOW, max_age_hours=72)
        self.assertEqual(result["sha256"], engine.sha256_file(document))

    def test_an_authorization_for_another_backup_is_refused(self):
        self.assertEqual(self.run_tool(
            "trust-store", "--private-key", str(self.private_key),
            "--key-id", "provider-2026", "--out", str(self.trust_store)).returncode, 0)
        document = self.authorization()
        signature = self.tmp / "recovery-authorization.sig"
        self.assertEqual(self.run_tool("sign", "--document", str(document),
                                       "--private-key", str(self.private_key),
                                       "--key-id", "provider-2026",
                                       "--document-type", "recovery-authorization",
                                       "--out", str(signature)).returncode, 0)
        store = engine.load_trust_store(self.trust_store, now=NOW)
        with self.assertRaises(engine.UpdateError) as caught:
            engine.validate_recovery_authorization(
                document, signature, store, site=engine.SITE_NAME,
                receipt_sha256="d" * 64, now=NOW, max_age_hours=72)
        self.assertEqual(caught.exception.code, "preflight.recovery.binding_mismatch")

    def test_unsigned_key_custody_is_never_signed(self):
        document = self.authorization(owner_key_custody_verified=False)
        completed = self.run_tool("sign", "--document", str(document),
                                  "--private-key", str(self.private_key),
                                  "--key-id", "provider-2026",
                                  "--document-type", "recovery-authorization",
                                  "--out", str(self.tmp / "recovery.sig"))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("key custody", completed.stderr)

    def test_a_rehearsal_restore_is_required(self):
        document = self.authorization(rehearsal_restore_verified=False)
        completed = self.run_tool("sign", "--document", str(document),
                                  "--private-key", str(self.private_key),
                                  "--key-id", "provider-2026",
                                  "--document-type", "recovery-authorization",
                                  "--out", str(self.tmp / "recovery.sig"))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("rehearsal", completed.stderr)


class PackagingTests(unittest.TestCase):
    def test_the_update_workflow_travels_in_the_verified_customer_package(self):
        allowed = (ROOT / "tools" / "release" / "create_customer_package.py").read_text(encoding="utf-8")
        powershell = (ROOT / "product" / "windows" / "Prepare Customer Package.ps1").read_text(encoding="utf-8")
        for name in ("product/windows/Update TOEFL House ERP.ps1",
                     "product/windows/updater-strings.json",
                     "product/updates/channel.json"):
            self.assertIn(name, allowed)
            self.assertIn(name, powershell)

    def test_the_shipped_channel_is_disabled_until_the_provider_authorizes_it(self):
        channel = json.loads((ROOT / "product" / "updates" / "channel.json").read_text(encoding="utf-8"))
        self.assertEqual(channel["document_type"], engine.DOCUMENT_CHANNEL)
        for entry in channel["channels"]:
            self.assertFalse(entry["enabled"])
            self.assertEqual(set(entry["required_assets"]),
                             {"update.json", "update.json.sig", "toefl-house-erp-app.tar"})
            self.assertTrue(entry["metadata_url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()

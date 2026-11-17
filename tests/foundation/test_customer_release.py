"""Customer simplicity must not turn test artifacts into live sites."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.foundation.test_update_engine import RsaKey, signature_envelope
from tests.foundation.test_product_activation import SITE, load_activate

import customer_release as release
from update_engine import DOCUMENT_TRUST, PRODUCT, UpdateError


class CustomerReleaseTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.instance = self.root / "instance"
        self.instance.mkdir()
        self.trust = self.root / "provider-trust.json"
        self.revision = self.root / "image-revision"
        self.signed = RsaKey(self.root, "provider-fixture")
        self.now = datetime.now(timezone.utc)
        self.grant = {
            "schema_version": 1,
            "document_type": release.GRANT_KIND,
            "product": PRODUCT,
            "release_id": "qualified-fixture",
            "source_revision": "f" * 40,
            "image_id": "sha256:" + "a" * 64,
            "windows_acceptance_sha256": "b" * 64,
            "production_authorization": "AUTHORIZED",
        }
        self.identity = {
            "schema_version": 1,
            "document_type": "toefl-house-erp-installed-image",
            "provenance": "factory",
            "source_revision": self.grant["source_revision"],
            "image_id": self.grant["image_id"],
        }
        for name, file in (("TRUST_PATH", self.trust), ("REVISION_PATH", self.revision)):
            change = patch.object(release, name, file)
            change.start()
            self.addCleanup(change.stop)
        self.revision.write_text(self.grant["source_revision"], encoding="ascii")
        self.write_trust(release.PURPOSE)
        self.write_identity()
        self.write_signed_grant()

    def write_identity(self):
        (self.instance / "installed-image-identity.json").write_text(
            json.dumps(self.identity), encoding="utf-8")

    def write_trust(self, *purposes):
        self.trust.write_text(json.dumps({
            "schema_version": 1,
            "document_type": DOCUMENT_TRUST,
            "product": PRODUCT,
            "provisioned": bool(purposes),
            "keys": [self.signed.trust_entry("provider", purposes)] if purposes else [],
        }), encoding="utf-8")

    def write_signed_grant(self):
        raw = json.dumps(self.grant).encode("utf-8")
        (self.instance / release.RELEASE_NAME).write_bytes(raw)
        (self.instance / release.SIGNATURE_NAME).write_text(json.dumps(
            signature_envelope(release.SIGNATURE_KIND, "provider", self.signed.sign(raw))),
            encoding="utf-8")

    def test_exact_provider_release(self):
        self.assertEqual(release.verify(self.instance, now=self.now), self.grant["release_id"])

    def test_no_provider_trust_stays_unapproved(self):
        self.write_trust()
        with self.assertRaisesRegex(UpdateError, "no provider release signing key"):
            release.verify(self.instance, now=self.now)

    def test_update_signing_key_cannot_authorize_factory_setup(self):
        self.write_trust("update-manifest")
        with self.assertRaisesRegex(UpdateError, "not trusted for customer-installation-release"):
            release.verify(self.instance, now=self.now)

    def test_different_factory_image_fails_even_for_a_valid_signature(self):
        self.identity["image_id"] = "sha256:" + "c" * 64
        self.write_identity()
        with self.assertRaisesRegex(UpdateError, "different factory image"):
            release.verify(self.instance, now=self.now)

    def test_modifying_a_signed_content_field_fails(self):
        self.grant["windows_acceptance_sha256"] = "e" * 64
        (self.instance / release.RELEASE_NAME).write_text(json.dumps(self.grant), encoding="utf-8")
        with self.assertRaisesRegex(UpdateError, "signature did not verify"):
            release.verify(self.instance, now=self.now)

    def test_signing_test_status_does_not_authorize_production(self):
        self.grant["production_authorization"] = "REJECT"
        self.write_signed_grant()
        with self.assertRaisesRegex(UpdateError, "production release authorization is invalid"):
            release.verify(self.instance, now=self.now)

    def test_expired_provider_key_cannot_authorize_a_new_site(self):
        with self.assertRaisesRegex(UpdateError, "outside its validity window"):
            release.verify(self.instance, now=self.now + timedelta(days=400))

    def test_provider_approval_cannot_substitute_for_a_fresh_verified_backup(self):
        activation = load_activate()
        with (
            patch.object(activation, "ACTIVATION_DIR", self.instance),
            patch.object(activation, "probe", return_value={"mode": "REFUSED"}),
            patch.object(activation, "internal_activation_context",
                         side_effect=activation.Refused("missing backup receipt")),
            patch.object(activation, "activate") as change_mode,
        ):
            with self.assertRaisesRegex(activation.Refused, "missing backup receipt"):
                activation.activate_customer(SITE)
        change_mode.assert_not_called()

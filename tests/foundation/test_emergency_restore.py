"""Emergency recovery gate for product/restore.py.

Production restores must be refused before any mutation without a distinct
pre-restore backup set and a two-approver emergency authorization bound to
the exact backup artifact hashes, with a single-use request_id. Disposable
restores are a separate, explicitly declared path that can never target the
production site. All tests use synthetic data in disposable directories and
mock the native Frappe restore itself; no live site is touched.
"""
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_PATH = ROOT / "product"
if str(PRODUCT_PATH) not in sys.path:
    sys.path.insert(0, str(PRODUCT_PATH))

OPENSSL = shutil.which("openssl")
SECRET_KEY = "synthetic-native-backup-key"
SECRET_DB = "synthetic-mariadb-root-password"
SECRET_ADMIN = "synthetic-owner-admin-password"


def load_restore():
    spec = importlib.util.spec_from_file_location(
        "product_restore_emergency_under_test", PRODUCT_PATH / "restore.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RsaKey:
    """Ephemeral RSA test key; the private half never enters the repository."""

    def __init__(self, directory: Path, name: str):
        if OPENSSL is None:  # pragma: no cover - CI images ship openssl
            raise unittest.SkipTest("openssl is required for restore tests")
        self.directory = directory
        self.private = directory / f"{name}.pem"
        subprocess.run([OPENSSL, "genpkey", "-algorithm", "RSA",
                        "-pkeyopt", "rsa_keygen_bits:2048",
                        "-out", str(self.private)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        result = subprocess.run([OPENSSL, "rsa", "-in", str(self.private),
                                 "-modulus", "-noout"], check=True,
                                capture_output=True, text=True)
        modulus_hex = result.stdout.strip().split("=", 1)[1]
        self.modulus = int(modulus_hex, 16)
        self.exponent = 65537

    def sign(self, payload: bytes) -> bytes:
        signature = self.directory / "signature.bin"
        subprocess.run([OPENSSL, "dgst", "-sha256", "-sign", str(self.private),
                        "-out", str(signature)], input=payload, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return signature.read_bytes()

    def trust_entry(self, key_id, purposes, identity, role):
        return {
            "key_id": key_id, "purposes": list(purposes),
            "modulus_b64": base64.b64encode(
                self.modulus.to_bytes((self.modulus.bit_length() + 7) // 8,
                                      "big")).decode("ascii"),
            "exponent_b64": base64.b64encode(
                self.exponent.to_bytes(3, "big")).decode("ascii"),
            "approver_identity": identity, "approver_role": role,
            "not_before_utc": "2026-01-01T00:00:00Z",
            "not_after_utc": "2030-01-01T00:00:00Z",
        }


class EmergencyRestoreTests(unittest.TestCase):
    def setUp(self):
        self.restore = load_restore()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sites = self.root / "sites"
        self.site = "toeflhouse.localhost"
        self.restore.SITES_DIR = self.sites
        self.restore.SITE_NAME = self.site
        self.restore.PRODUCTION_SITE = self.site
        self.state = self.root / "state"
        self.trust_path = self.root / "trust-store.json"
        self.env = patch.dict(os.environ, {
            "RESTORE_STATE_DIR": str(self.state),
            "RESTORE_TRUST_STORE": str(self.trust_path),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.keys = self.root / "keys"
        self.keys.mkdir()
        self.owner = RsaKey(self.keys, "owner")
        self.manager = RsaKey(self.keys, "manager")
        self.other = RsaKey(self.keys, "other")
        self.trust_path.write_text(json.dumps({
            "schema_version": 1,
            "document_type": "toefl-house-erp-update-trust-store",
            "provisioned": True,
            "keys": [
                self.owner.trust_entry(
                    "owner-2026a", ("emergency-restore",),
                    "course-owner", "course-owner"),
                self.manager.trust_entry(
                    "manager-2026a", ("emergency-restore",),
                    "general-manager", "general-manager"),
                self.other.trust_entry(
                    "other-2026a", ("update-manifest",),
                    "other-person", "general-manager"),
            ],
        }), encoding="utf-8")
        self.target_set = "20261028-target"
        self.current_set = "20261028-current"
        for backup_set in (self.target_set, self.current_set):
            backup_dir = self.sites / self.site / "private" / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            for role, suffix in self.restore.BACKUP_SUFFIXES.items():
                (backup_dir / f"{backup_set}{suffix}").write_bytes(
                    f"synthetic {backup_set} {role}".encode())

    def _hashes(self, backup_set):
        paths = self.restore._verified_backup_paths(self.site, backup_set)
        return self.restore._artifact_hashes(paths)

    def _authorization(self, *, request_id="a" * 32, approvals=None,
                       hashes=None, site=None, backup_set=None,
                       issued="2026-10-28T00:00:00Z",
                       expires="2026-11-28T00:00:00Z", signers=None):
        document = {
            "schema_version": 1, "document_type": "emergency-restore",
            "site": site or self.site, "target": "production",
            "backup_set": backup_set or self.target_set,
            "backup_sha256": hashes if hashes is not None
            else self._hashes(self.target_set),
            "request_id": request_id, "issued_utc": issued,
            "expires_utc": expires,
            "approvals": approvals if approvals is not None else [
                {"key_id": "owner-2026a", "approver_identity": "course-owner",
                 "approver_role": "course-owner"},
                {"key_id": "manager-2026a",
                 "approver_identity": "general-manager",
                 "approver_role": "general-manager"},
            ],
        }
        raw = self.restore._canonical_document_bytes(document)
        signers = signers if signers is not None else (self.owner, self.manager)
        signatures = [base64.b64encode(key.sign(raw)).decode("ascii")
                      for key in signers]
        return document, signatures[0], signatures[1]

    def _run_authorized(self, *, authorization_kwargs=None, mock=None,
                        pre_restore_backup_set=None, target="production"):
        document, sig1, sig2 = self._authorization(
            **(authorization_kwargs or {}))
        with patch.object(self.restore, "_run_native_restore") as native:
            if mock is not None:
                native.side_effect = mock
            self.restore._native_restore(
                self.site, self.target_set, SECRET_KEY, SECRET_DB, SECRET_ADMIN,
                target=target,
                pre_restore_backup_set=self.current_set
                if pre_restore_backup_set is None else pre_restore_backup_set,
                authorization=document, signature_1=sig1, signature_2=sig2)
            return native

    def _state_dir(self):
        return self.state / self.site

    def test_two_distinct_approvals_allow_a_production_restore(self):
        native = self._run_authorized()
        native.assert_called_once()
        self.assertTrue((self._state_dir() / ("a" * 32 + ".json")).exists())
        self.assertFalse((self._state_dir() / "in-progress.json").exists())
        audit = (self._state_dir() / "audit.jsonl").read_text()
        self.assertIn("completed", audit)
        self.assertIn("course-owner", audit)
        self.assertIn(self.target_set, audit)
        for secret in (SECRET_KEY, SECRET_DB, SECRET_ADMIN):
            self.assertNotIn(secret, audit)

    def test_production_restore_without_authorization_is_refused(self):
        with patch.object(self.restore, "_run_native_restore") as native:
            with self.assertRaises(self.restore.RestoreInputError):
                self.restore._native_restore(
                    self.site, self.target_set, SECRET_KEY, SECRET_DB,
                    SECRET_ADMIN, target="production",
                    pre_restore_backup_set=self.current_set)
        native.assert_not_called()

    def test_production_restore_without_a_pre_restore_backup_is_refused(self):
        document, sig1, sig2 = self._authorization()
        with patch.object(self.restore, "_run_native_restore") as native:
            with self.assertRaises(self.restore.RestoreInputError):
                self.restore._native_restore(
                    self.site, self.target_set, SECRET_KEY, SECRET_DB,
                    SECRET_ADMIN, target="production",
                    pre_restore_backup_set=None,
                    authorization=document, signature_1=sig1, signature_2=sig2)
        native.assert_not_called()

    def test_single_approver_is_refused(self):
        document, sig1, sig2 = self._authorization(
            approvals=[{"key_id": "owner-2026a",
                        "approver_identity": "course-owner",
                        "approver_role": "course-owner"}],
            signers=(self.owner, self.owner))
        with patch.object(self.restore, "_run_native_restore") as native:
            with self.assertRaises(self.restore.RestoreInputError):
                self.restore._native_restore(
                    self.site, self.target_set, SECRET_KEY, SECRET_DB,
                    SECRET_ADMIN, target="production",
                    pre_restore_backup_set=self.current_set,
                    authorization=document, signature_1=sig1, signature_2=sig2)
        native.assert_not_called()

    def test_two_owners_without_an_independent_second_approver_are_refused(self):
        document, sig1, sig2 = self._authorization(
            approvals=[
                {"key_id": "owner-2026a", "approver_identity": "course-owner",
                 "approver_role": "course-owner"},
                {"key_id": "manager-2026a",
                 "approver_identity": "second-owner",
                 "approver_role": "course-owner"}],
            signers=(self.owner, self.manager))
        with patch.object(self.restore, "_run_native_restore") as native:
            with self.assertRaises(self.restore.RestoreInputError):
                self.restore._native_restore(
                    self.site, self.target_set, SECRET_KEY, SECRET_DB,
                    SECRET_ADMIN, target="production",
                    pre_restore_backup_set=self.current_set,
                    authorization=document, signature_1=sig1, signature_2=sig2)
        native.assert_not_called()

    def test_self_approval_by_the_same_person_twice_is_refused(self):
        document, sig1, sig2 = self._authorization(
            approvals=[
                {"key_id": "owner-2026a", "approver_identity": "course-owner",
                 "approver_role": "course-owner"},
                {"key_id": "manager-2026a",
                 "approver_identity": "Course-Owner",
                 "approver_role": "general-manager"}],
            signers=(self.owner, self.manager))
        with patch.object(self.restore, "_run_native_restore") as native:
            with self.assertRaises(self.restore.RestoreInputError):
                self.restore._native_restore(
                    self.site, self.target_set, SECRET_KEY, SECRET_DB,
                    SECRET_ADMIN, target="production",
                    pre_restore_backup_set=self.current_set,
                    authorization=document, signature_1=sig1, signature_2=sig2)
        native.assert_not_called()

    def test_wrong_purpose_key_is_refused(self):
        document, sig1, sig2 = self._authorization(
            approvals=[
                {"key_id": "owner-2026a", "approver_identity": "course-owner",
                 "approver_role": "course-owner"},
                {"key_id": "other-2026a", "approver_identity": "other-person",
                 "approver_role": "general-manager"}],
            signers=(self.owner, self.other))
        with patch.object(self.restore, "_run_native_restore") as native:
            with self.assertRaises(self.restore.RestoreInputError):
                self.restore._native_restore(
                    self.site, self.target_set, SECRET_KEY, SECRET_DB,
                    SECRET_ADMIN, target="production",
                    pre_restore_backup_set=self.current_set,
                    authorization=document, signature_1=sig1, signature_2=sig2)
        native.assert_not_called()

    def test_expired_authorization_is_refused(self):
        with patch.object(self.restore, "_run_native_restore") as native:
            with self.assertRaises(self.restore.RestoreInputError):
                self._run_authorized(authorization_kwargs={
                    "issued": "2026-01-01T00:00:00Z",
                    "expires": "2026-01-02T00:00:00Z"})
        native.assert_not_called()

    def test_authorization_for_another_site_or_backup_is_refused(self):
        for kwargs in ({"site": "other-restore.localhost"},
                       {"backup_set": "20261028-other"}):
            with self.subTest(kwargs=kwargs):
                document, sig1, sig2 = self._authorization(**kwargs)
                with patch.object(self.restore, "_run_native_restore") as native:
                    with self.assertRaises(self.restore.RestoreInputError):
                        self.restore._native_restore(
                            self.site, self.target_set, SECRET_KEY, SECRET_DB,
                            SECRET_ADMIN, target="production",
                            pre_restore_backup_set=self.current_set,
                            authorization=document, signature_1=sig1,
                            signature_2=sig2)
                native.assert_not_called()

    def test_altered_backup_artifacts_invalidate_the_authorization(self):
        document, sig1, sig2 = self._authorization()
        backup_dir = self.sites / self.site / "private" / "backups"
        (backup_dir / f"{self.target_set}-database-enc.sql.gz").write_bytes(
            b"altered synthetic database")
        with patch.object(self.restore, "_run_native_restore") as native:
            with self.assertRaises(self.restore.RestoreInputError):
                self.restore._native_restore(
                    self.site, self.target_set, SECRET_KEY, SECRET_DB,
                    SECRET_ADMIN, target="production",
                    pre_restore_backup_set=self.current_set,
                    authorization=document, signature_1=sig1, signature_2=sig2)
        native.assert_not_called()

    def test_altered_authorization_document_invalidates_signatures(self):
        document, sig1, sig2 = self._authorization()
        document["expires_utc"] = "2027-01-01T00:00:00Z"
        with patch.object(self.restore, "_run_native_restore") as native:
            with self.assertRaises(self.restore.RestoreInputError):
                self.restore._native_restore(
                    self.site, self.target_set, SECRET_KEY, SECRET_DB,
                    SECRET_ADMIN, target="production",
                    pre_restore_backup_set=self.current_set,
                    authorization=document, signature_1=sig1, signature_2=sig2)
        native.assert_not_called()

    def test_replayed_request_id_is_refused_after_a_successful_restore(self):
        self._run_authorized()
        document, sig1, sig2 = self._authorization()
        with patch.object(self.restore, "_run_native_restore") as native:
            with self.assertRaises(self.restore.RestoreInputError):
                self.restore._native_restore(
                    self.site, self.target_set, SECRET_KEY, SECRET_DB,
                    SECRET_ADMIN, target="production",
                    pre_restore_backup_set=self.current_set,
                    authorization=document, signature_1=sig1, signature_2=sig2)
        native.assert_not_called()

    def test_failed_restore_still_consumes_the_request(self):
        def fail(*args, **kwargs):
            raise RuntimeError("synthetic native failure")
        with self.assertRaises(RuntimeError):
            self._run_authorized(mock=fail)
        self.assertTrue((self._state_dir() / ("a" * 32 + ".json")).exists())
        self.assertFalse((self._state_dir() / "in-progress.json").exists())
        audit = (self._state_dir() / "audit.jsonl").read_text()
        self.assertIn("failed", audit)
        for secret in (SECRET_KEY, SECRET_DB, SECRET_ADMIN):
            self.assertNotIn(secret, audit)

    def test_unfinished_restore_marker_blocks_the_next_production_restore(self):
        state_dir = self._state_dir()
        state_dir.mkdir(parents=True, mode=0o700)
        (state_dir / "in-progress.json").write_text("{}")
        document, sig1, sig2 = self._authorization(request_id="b" * 32)
        with patch.object(self.restore, "_run_native_restore") as native:
            with self.assertRaises(self.restore.RestoreInputError):
                self.restore._native_restore(
                    self.site, self.target_set, SECRET_KEY, SECRET_DB,
                    SECRET_ADMIN, target="production",
                    pre_restore_backup_set=self.current_set,
                    authorization=document, signature_1=sig1, signature_2=sig2)
        native.assert_not_called()

    def test_disposable_restore_is_isolated_from_the_production_site(self):
        disposable = "placement-restore.localhost"
        self.restore.SITE_NAME = disposable
        backup_dir = self.sites / disposable / "private" / "backups"
        backup_dir.mkdir(parents=True)
        for role, suffix in self.restore.BACKUP_SUFFIXES.items():
            (backup_dir / f"{self.target_set}{suffix}").write_bytes(
                b"synthetic disposable artifact")
        with patch.object(self.restore, "_run_native_restore") as native:
            self.restore._native_restore(
                disposable, self.target_set, SECRET_KEY, SECRET_DB,
                SECRET_ADMIN, target="disposable")
        native.assert_called_once()
        audit = (self.state / disposable / "audit.jsonl").read_text()
        self.assertIn("disposable", audit)
        for secret in (SECRET_KEY, SECRET_DB, SECRET_ADMIN):
            self.assertNotIn(secret, audit)
        # The production site's backups were never touched by the disposable run.
        prod_dir = self.sites / self.site / "private" / "backups"
        self.assertEqual(
            (prod_dir / f"{self.target_set}-database-enc.sql.gz").read_bytes(),
            f"synthetic {self.target_set} database".encode())

    def test_disposable_target_must_never_name_the_production_site(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        payload = {
            "site": self.site, "backup_set": self.target_set,
            "encryption_key": SECRET_KEY, "db_root_password": SECRET_DB,
            "admin_password": SECRET_ADMIN, "target": "disposable",
        }
        with patch.object(self.restore, "_run_native_restore") as native:
            status = self.restore.main(
                io.StringIO(json.dumps(payload)), stdout, stderr, argv=[])
        self.assertEqual(status, 2)
        native.assert_not_called()
        for secret in (SECRET_KEY, SECRET_DB, SECRET_ADMIN):
            self.assertNotIn(secret, stdout.getvalue() + stderr.getvalue())

    def test_main_refuses_a_production_restore_without_authorization(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        payload = {
            "site": self.site, "backup_set": self.target_set,
            "encryption_key": SECRET_KEY, "db_root_password": SECRET_DB,
            "admin_password": SECRET_ADMIN,
        }
        with patch.object(self.restore, "_run_native_restore") as native:
            status = self.restore.main(
                io.StringIO(json.dumps(payload)), stdout, stderr, argv=[])
        self.assertEqual(status, 2)
        native.assert_not_called()
        for secret in (SECRET_KEY, SECRET_DB, SECRET_ADMIN):
            self.assertNotIn(secret, stdout.getvalue() + stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

"""Owner site-mode activation (product/activate.py) preserves every hard gate.

The app's own security.site_mode resolver is loaded with a stubbed frappe
reading the on-disk site_config. Activation also requires a fresh, content-
verified encrypted backup receipt on a separate local drive, matching the
current Owner-configured schedule/retention policy. Release authorization stays
REJECT regardless of operational site mode.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from tests.foundation.test_production_activation import load_policy, load_security

ROOT = Path(__file__).resolve().parents[2]
SITE = "toeflhouse.localhost"
BACKUP_SET = "20261007-120000-toeflhouse_localhost"
POLICY = {
    "configured": True,
    "status": "CONFIGURED",
    "schedule_time": "02:30",
    "retention_versions": 3,
    "recovery_key_sha256": "b" * 64,
    "effective_from": "2026-10-07",
    "policy_hash": "a" * 64,
}


def load_activate():
    spec = importlib.util.spec_from_file_location("activate_under_test", ROOT / "product" / "activate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ActivationFlow(unittest.TestCase):
    def setUp(self):
        self.act = load_activate()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.act.SITES_DIR = Path(self.tmp.name)
        self.site_dir = self.act.SITES_DIR / SITE
        self.backup_dir = self.site_dir / "private" / "backups"
        self.backup_dir.mkdir(parents=True)
        self.receipt_path = self.act.SITES_DIR / "secrets" / "backup-receipt.json"
        self.act.BACKUP_RECEIPT_PATH = self.receipt_path
        self.write({"db_name": "x", "db_type": "mariadb"})
        self.mirror_ok = True
        self.policy = dict(POLICY)
        patcher = patch.object(self.act, "probe", side_effect=self.fake_probe)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, config):
        (self.site_dir / "site_config.json").write_text(json.dumps(config))

    def config(self):
        return json.loads((self.site_dir / "site_config.json").read_text())

    def fresh_backup(self, age=0, *, encrypted=True, same_drive=False):
        created = datetime.fromtimestamp(time.time() - age, timezone.utc)
        created_text = created.isoformat().replace("+00:00", "Z")
        artifacts = []
        suffixes = self.act.EXPECTED_BACKUP_ROLES
        for role, suffix in suffixes.items():
            name = BACKUP_SET + suffix
            payload = f"verified encrypted fixture for {role}".encode()
            path = self.backup_dir / name
            path.write_bytes(payload)
            artifacts.append({
                "role": role,
                "name": name,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            })
        manifest = {
            "schema_version": 2,
            "backup_set": BACKUP_SET,
            "encrypted": encrypted,
            "verified": True,
            "artifacts": artifacts,
        }
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
        receipt = {
            "schema_version": 1,
            "source_site": SITE,
            "source_drive": "C:",
            "backup_drive": "C:" if same_drive else "D:",
            "backup_set": BACKUP_SET,
            "created_utc": created_text,
            "encrypted": encrypted,
            "verified": True,
            "automation_ready": True,
            "task_name": "TOEFL House ERP Backup",
            "schedule_time": POLICY["schedule_time"],
            "retention_versions": POLICY["retention_versions"],
            "policy_hash": POLICY["policy_hash"],
            "recovery_key_sha256": POLICY["recovery_key_sha256"],
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "artifacts": artifacts,
        }
        self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
        self.receipt_path.write_text(json.dumps(receipt))
        return receipt

    def fake_probe(self, site, *extra):
        security = load_security(self.config(), site)
        result = {"mode": security.site_mode(), "backup_policy": dict(self.policy)}
        try:
            result["flag"] = security.record_synthetic_flag()
        except Exception:
            result["flag"] = None
        if result["mode"] == "PRODUCTION":
            policy = load_policy()
            try:
                policy.validate_family("SYN-PLACE-1", 1, production=True)
                result["mirror"] = False
            except ValueError:
                result["mirror"] = self.mirror_ok
        if extra:
            result["item"] = extra[0] == "PLACEMENT-FEE"
            result["rate"] = 500.0
        return result

    def test_refuses_without_a_fresh_verified_encrypted_backup(self):
        with self.assertRaises(self.act.Refused):
            self.act.activate(SITE, log=lambda *_: None)
        self.fresh_backup(age=2 * 24 * 3600)
        with self.assertRaises(self.act.Refused):
            self.act.activate(SITE, log=lambda *_: None)
        self.assertNotIn(self.act.ACTIVE_KEY, self.config())

    def test_activation_passes_original_mode_mirror_fixture_and_mixed_flag_gates(self):
        self.fresh_backup()
        self.act.activate(SITE, log=lambda *_: None)
        config = self.config()
        self.assertEqual(config[self.act.ACTIVE_KEY], 1)
        self.assertEqual(config[self.act.SITE_KEY], SITE)
        for key in self.act.SYNTHETIC_KEYS:
            self.assertNotIn(key, config)
        self.assertEqual(self.fake_probe(SITE)["mode"], "PRODUCTION")
        self.assertEqual(self.act.PRODUCTION_AUTHORIZATION, "REJECT")
        snapshots = list((self.site_dir / "private").glob("site_config.json.*.bak"))
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].stat().st_mode & 0o777, 0o600)

    def test_failed_site_mode_gate_restores_previous_settings(self):
        self.fresh_backup()
        self.mirror_ok = False
        before = self.config()
        with self.assertRaises(self.act.Refused):
            self.act.activate(SITE, log=lambda *_: None)
        self.assertEqual(self.config(), before)
        self.assertEqual(self.fake_probe(SITE)["mode"], "REFUSED")

    def test_stale_test_flags_block_activation_by_presence(self):
        self.fresh_backup()
        self.write({"db_type": "mariadb", "allow_tests": 0})
        with self.assertRaises(self.act.Refused):
            self.act.activate(SITE, log=lambda *_: None)

    def test_qualification_hostname_and_other_backends_refused(self):
        with self.assertRaises(self.act.Refused):
            self.act.check_preconditions("placement-test.localhost", {}, None, time.time())
        with self.assertRaises(self.act.Refused):
            self.act.check_preconditions(SITE, {"db_type": "postgres"}, None, time.time())

    def test_backup_must_be_encrypted_and_on_another_local_drive(self):
        receipt = self.fresh_backup(same_drive=True)
        with self.assertRaisesRegex(self.act.Refused, "separate local drive"):
            self.act.check_preconditions(SITE, self.config(), receipt, time.time(), self.backup_dir)
        receipt = self.fresh_backup(encrypted=False)
        with self.assertRaisesRegex(self.act.Refused, "does not prove encryption"):
            self.act.check_preconditions(SITE, self.config(), receipt, time.time(), self.backup_dir)

    def test_modified_or_missing_artifact_refuses(self):
        receipt = self.fresh_backup()
        artifact = self.backup_dir / receipt["artifacts"][0]["name"]
        artifact.write_bytes(b"tampered after verification")
        with self.assertRaisesRegex(self.act.Refused, "changed after receipt"):
            self.act.check_preconditions(SITE, self.config(), receipt, time.time(), self.backup_dir)
        artifact.unlink()
        with self.assertRaisesRegex(self.act.Refused, "missing or unsafe"):
            self.act.check_preconditions(SITE, self.config(), receipt, time.time(), self.backup_dir)

    def test_plaintext_native_site_config_sidecar_refuses_activation(self):
        receipt = self.fresh_backup()
        sidecar = self.backup_dir / f"{BACKUP_SET}-site_config_backup-enc.json"
        sidecar.write_text('{"db_password":"synthetic"}', encoding="utf-8")
        with self.assertRaisesRegex(self.act.Refused, "plaintext Frappe site-config backup sidecar"):
            self.act.check_preconditions(SITE, self.config(), receipt, time.time(), self.backup_dir)

    def test_missing_role_duplicate_traversal_and_retention_below_two_refuse(self):
        receipt = self.fresh_backup()
        receipt["artifacts"] = receipt["artifacts"][:-1]
        with self.assertRaisesRegex(self.act.Refused, "complete encrypted backup set"):
            self.act.check_preconditions(SITE, self.config(), receipt, time.time(), self.backup_dir)
        receipt = self.fresh_backup()
        receipt["retention_versions"] = 1
        with self.assertRaisesRegex(self.act.Refused, "multi-version retention"):
            self.act.check_preconditions(SITE, self.config(), receipt, time.time(), self.backup_dir)
        receipt = self.fresh_backup()
        receipt["backup_set"] = "../escape"
        with self.assertRaisesRegex(self.act.Refused, "invalid backup-set identity"):
            self.act.check_preconditions(SITE, self.config(), receipt, time.time(), self.backup_dir)

    def test_current_owner_backup_policy_must_match_receipt(self):
        self.fresh_backup()
        self.policy["policy_hash"] = "b" * 64
        with self.assertRaisesRegex(self.act.Refused, "does not match"):
            self.act.activate(SITE, log=lambda *_: None)
        self.assertNotIn(self.act.ACTIVE_KEY, self.config())

    def test_deactivate_returns_to_refused(self):
        self.fresh_backup()
        self.act.activate(SITE, log=lambda *_: None)
        self.act.deactivate(SITE, log=lambda *_: None)
        self.assertEqual(self.fake_probe(SITE)["mode"], "REFUSED")

    def test_failed_deactivation_verification_restores_previous_settings(self):
        self.fresh_backup()
        self.act.activate(SITE, log=lambda *_: None)
        before = self.config()
        self.assertIn(self.act.ACTIVE_KEY, before)

        def stale_probe(site, *extra):
            if self.act.ACTIVE_KEY not in self.config():
                return {"mode": "PRODUCTION", "backup_policy": dict(self.policy)}
            return self.fake_probe(site, *extra)

        with patch.object(self.act, "probe", side_effect=stale_probe):
            with self.assertRaises(self.act.Refused):
                self.act.deactivate(SITE, log=lambda *_: None)
        self.assertEqual(self.config(), before)
        self.assertEqual(self.fake_probe(SITE)["mode"], "PRODUCTION")

    def test_fee_item_requires_activation_existing_item_and_positive_native_price(self):
        with self.assertRaises(self.act.Refused):
            self.act.set_fee_item(SITE, "PLACEMENT-FEE", log=lambda *_: None)
        self.fresh_backup()
        self.act.activate(SITE, log=lambda *_: None)
        for bad in ("SYN-PLACEMENT-FEE", "SYNTHETIC-1", "", "MISSING"):
            with self.assertRaises(self.act.Refused):
                self.act.set_fee_item(SITE, bad, log=lambda *_: None)
        self.act.set_fee_item(SITE, "PLACEMENT-FEE", log=lambda *_: None)
        self.assertEqual(self.config()[self.act.FEE_ITEM_KEY], "PLACEMENT-FEE")

    def test_confirmation_must_name_the_site(self):
        with self.assertRaises(self.act.Refused):
            self.act.require_confirm(SITE, None)
        self.act.require_confirm(SITE, SITE)

    def test_quick_site_config_snapshots_are_unique_and_private(self):
        first = self.act.backup_config(SITE)
        second = self.act.backup_config(SITE)
        self.assertNotEqual(first, second)
        self.assertEqual(first.stat().st_mode & 0o777, 0o600)
        self.assertEqual(second.stat().st_mode & 0o777, 0o600)


class ActivationConstantsMatchApp(unittest.TestCase):
    def test_keys_hostnames_and_finance_contract_match_app(self):
        act = load_activate()
        security = load_security({}, SITE)
        self.assertEqual(act.ACTIVE_KEY, security.PRODUCTION_ACTIVE_CONF_KEY)
        self.assertEqual(act.SITE_KEY, security.PRODUCTION_SITE_CONF_KEY)
        self.assertEqual(act.SYNTHETIC_SITES, security.SYNTHETIC_SITES)
        finance = (ROOT / "apps/toefl_house/toefl_house/finance/__init__.py").read_text()
        self.assertIn(f'PLACEMENT_FEE_ITEM_CONF_KEY = "{act.FEE_ITEM_KEY}"', finance)
        self.assertIn(f'PRICE_LIST = "{act.PRICE_LIST}"', finance)

    def test_script_is_baked_into_the_image(self):
        self.assertIn("!product/activate.py", (ROOT / ".dockerignore").read_text())
        self.assertIn("COPY product/activate.py /product/activate.py",
                      (ROOT / "product/app.Dockerfile").read_text())


if __name__ == "__main__":
    unittest.main()

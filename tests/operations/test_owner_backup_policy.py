"""Offline business-rule tests for the Owner-controlled backup settings."""
import ast
import base64
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "apps/toefl_house/toefl_house/operations/owner_configuration.py"
TEST_PUBLIC_KEY = (
    "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
    "disposable synthetic public-key fixture\n"
    "-----END PGP PUBLIC KEY BLOCK-----")


def load_policy_helpers():
    source = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {"_int", "_bool", "_backup_schedule_time", "_backup_public_key",
             "validate_terms", "current_backup_policy",
             "current_backup_public_key_b64"}
    selected = [node for node in source.body
                if isinstance(node, ast.FunctionDef) and node.name in names]
    constants = [node for node in source.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id in {
                     "MIN_BACKUP_VERSIONS", "MAX_BACKUP_VERSIONS",
                     "MAX_BACKUP_PUBLIC_KEY", "MAX_CUSTODY"
                 } for target in node.targets)]
    module = ast.Module(body=constants + selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "datetime": datetime,
        "base64": base64,
        "hashlib": hashlib,
        "json": json,
        "re": re,
        "MIN_BACKUP_VERSIONS": 2,
        "MAX_BACKUP_VERSIONS": 10000,
        "MAX_BACKUP_PUBLIC_KEY": 65536,
        "MAX_CUSTODY": 2000,
        "foundation": SimpleNamespace(
            validate_change_reason=lambda value: value.strip() if value.strip()
            else (_ for _ in ()).throw(ValueError("Change reason is required"))),
    }
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace


def valid_terms(**updates):
    values = {
        "reporting_review_days": 30,
        "capacity_target": 20,
        "tax_enabled": False,
        "tax_rate": 0,
        "tax_inclusive": False,
        "transfer_allowed": False,
        "withdrawal_allowed": False,
        "calendar_notice_days": 0,
        "backup_schedule_time": "02:30",
        "backup_retention_versions": 3,
        "backup_recovery_public_key": TEST_PUBLIC_KEY,
        "custody_requirement": "Recovery custody documented outside the ERP",
        "recovery_quorum": 2,
        "reason": "Owner-approved version",
    }
    values.update(updates)
    return values


class BackupPolicyValidationTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy_helpers()

    def test_normalizes_native_time_values_without_defaulting(self):
        terms = self.policy["validate_terms"](valid_terms(backup_schedule_time="02:30:00"))
        self.assertEqual(terms["backup_schedule_time"], "02:30")
        self.assertEqual(terms["backup_retention_versions"], 3)

    def test_missing_or_invalid_time_and_retention_fail_closed(self):
        for update in (
            {"backup_schedule_time": ""},
            {"backup_schedule_time": "25:00"},
            {"backup_schedule_time": "2:30"},
            {"backup_retention_versions": None},
            {"backup_retention_versions": 1},
            {"backup_retention_versions": True},
            {"backup_retention_versions": 10001},
            {"backup_recovery_public_key": ""},
            {"backup_recovery_public_key": "-----BEGIN PGP PRIVATE KEY BLOCK-----"},
            {"backup_recovery_public_key": "not an armored key"},
            {"backup_recovery_public_key": TEST_PUBLIC_KEY + "\u2603"},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.policy["validate_terms"](valid_terms(**update))

    def test_preexisting_legacy_version_remains_saveable_but_unconfigured(self):
        legacy = valid_terms()
        legacy.pop("backup_schedule_time")
        legacy.pop("backup_retention_versions")
        legacy.pop("backup_recovery_public_key")
        normalized = self.policy["validate_terms"](legacy, allow_legacy_backup=True)
        self.assertEqual(normalized["backup_schedule_time"], "")
        self.assertIsNone(normalized["backup_retention_versions"])
        self.policy["governing_owner_operations"] = lambda _date=None: legacy
        result = self.policy["current_backup_policy"]()
        self.assertEqual(result, {"configured": False, "status": "NOT CONFIGURED"})

    def test_legacy_schedule_without_recovery_key_remains_saveable_but_unconfigured(self):
        legacy = valid_terms()
        legacy.pop("backup_recovery_public_key")
        normalized = self.policy["validate_terms"](legacy, allow_legacy_backup=True)
        self.assertEqual(normalized["backup_schedule_time"], "02:30")
        self.assertEqual(normalized["backup_retention_versions"], 3)
        self.policy["governing_owner_operations"] = lambda _date=None: legacy
        self.assertEqual(
            self.policy["current_backup_policy"](),
            {"configured": False, "status": "NOT CONFIGURED"},
        )

    def test_current_effective_terms_have_stable_non_secret_identity(self):
        terms = valid_terms()
        terms["effective_from"] = "2026-10-07"
        self.policy["governing_owner_operations"] = lambda _date=None: terms
        result = self.policy["current_backup_policy"]()
        identity = {
            "effective_from": "2026-10-07",
            "schedule_time": "02:30",
            "retention_versions": 3,
            "recovery_key_sha256": hashlib.sha256(
                TEST_PUBLIC_KEY.strip().encode("utf-8")).hexdigest(),
        }
        expected = hashlib.sha256(json.dumps(
            identity, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        self.assertTrue(result["configured"])
        self.assertEqual(result["status"], "CONFIGURED")
        self.assertEqual(result["policy_hash"], expected)
        self.assertEqual(set(result), {
            "configured", "status", "schedule_time", "retention_versions",
            "recovery_key_sha256", "effective_from", "policy_hash",
        })
        self.assertNotIn("custody_requirement", result)
        self.assertNotIn("reason", result)

    def test_public_key_export_is_ascii_base64_and_fails_closed(self):
        terms = valid_terms()
        terms["effective_from"] = "2026-10-07"
        self.policy["governing_owner_operations"] = lambda _date=None: terms
        encoded = self.policy["current_backup_public_key_b64"]()
        self.assertEqual(base64.b64decode(encoded).decode("ascii"), TEST_PUBLIC_KEY.strip())

        terms["backup_recovery_public_key"] = "-----BEGIN PGP PRIVATE KEY BLOCK-----"
        self.assertEqual(self.policy["current_backup_public_key_b64"](), "")

    def test_invalid_effective_terms_are_reported_not_repaired(self):
        terms = valid_terms(backup_retention_versions=1)
        terms["effective_from"] = "2026-10-07"
        self.policy["governing_owner_operations"] = lambda _date=None: terms
        self.assertEqual(
            self.policy["current_backup_policy"](),
            {"configured": False, "status": "NOT CONFIGURED"},
        )


if __name__ == "__main__":
    unittest.main()

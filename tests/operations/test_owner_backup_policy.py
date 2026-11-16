"""Offline business-rule tests for the Owner-controlled backup settings."""
import ast
import base64
import hashlib
import json
import re
import secrets
from datetime import datetime, time as _clock_time, timedelta
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
    names = {"_int", "_bool", "backup_switch_state", "_backup_schedule_time", "_backup_public_key",
             "_backup_retention_behavior", "_validate_backup_terms", "validate_terms",
             "configure_local_backup_policy", "_backup_snapshot_text", "validate_backup_policy_snapshot",
             "_validated_backup_terms", "_version_rows", "_governing_owner_terms",
             "_owner_policy_validation_is_current",
             "_validated_governing_owner_operations", "governing_owner_operations",
             "current_backup_policy", "current_backup_public_key_b64"}
    selected = [node for node in source.body
                if isinstance(node, ast.FunctionDef) and node.name in names]
    constants = [node for node in source.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id in {
                     "BACKUP_CONTROL", "BACKUP_POLICY", "BACKUP_POLICY_ACTION",
                     "MIN_BACKUP_VERSIONS", "MAX_BACKUP_VERSIONS",
                     "MAX_BACKUP_PUBLIC_KEY", "MAX_CUSTODY",
                     "RETENTION_PRESERVE_ALL", "RETENTION_DELETE_BEYOND_KEEP",
                     "BACKUP_RETENTION_BEHAVIORS"
                 } for target in node.targets)]
    module = ast.Module(body=constants + selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "datetime": datetime,
        "timedelta": timedelta,
        "_clock_time": _clock_time,
        "base64": base64,
        "hashlib": hashlib,
        "json": json,
        "math": __import__("math"),
        "re": re,
        "secrets": secrets,
        "digest": lambda value: hashlib.sha256(
            json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest(),
        "POLICY": "TH Owner Operations Policy",
        "GOVERNING_FIELDS": (
            "effective_from", "reporting_review_days", "capacity_target",
            "tax_enabled", "tax_rate", "tax_inclusive", "transfer_allowed",
            "withdrawal_allowed", "calendar_notice_days", "backup_schedule_time",
            "backup_retention_versions", "backup_retention_behavior",
            "backup_recovery_public_key",
            "custody_requirement", "recovery_quorum",
        ),
        "configuration_audit": SimpleNamespace(AUDIT="TH Configuration Audit Event"),
        "frappe": SimpleNamespace(
            whitelist=lambda **kwargs: (lambda func: func),
            ValidationError=ValueError,
            db=SimpleNamespace(
                get_all=lambda *args, **kwargs: [],
                get_singles_dict=lambda _dt: {},
                # Synthetic fixture explicitly switches backup On. Production
                # without a saved switch must stay Off.
                get_single_value=lambda _dt, field: "1" if field == "enabled"
                else "f" * 32,
            ),
            utils=SimpleNamespace(today=lambda: "2026-10-08"),
        ),
        "rules": SimpleNamespace(parse_date=lambda value: datetime.fromisoformat(value).date().isoformat()),
        "MIN_BACKUP_VERSIONS": 2,
        "MAX_BACKUP_VERSIONS": 10000,
        "MAX_BACKUP_PUBLIC_KEY": 65536,
        "MAX_CUSTODY": 2000,
        "foundation": SimpleNamespace(
            validate_change_reason=lambda value: value.strip() if value.strip()
            else (_ for _ in ()).throw(ValueError("Change reason is required")),
            snapshot_digest=lambda rows: hashlib.sha256(
                json.dumps(rows, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest(),
            resolve_governing_strict=lambda rows, on_date, **kwargs: max(
                (row for row in rows if str(row.get("effective_from")) <= str(on_date)),
                key=lambda row: str(row.get("effective_from")), default=None),
        ),
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
        "backup_retention_behavior": "Preserve all valid backup sets",
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

    def test_backup_only_command_commits_exact_validated_snapshot_and_rotates_receipts(self):
        action = self.policy["BACKUP_POLICY_ACTION"]
        target = self.policy["BACKUP_POLICY"]
        events = []
        doc = SimpleNamespace(policy_snapshot="", save=lambda **_kw: None)
        frappe = self.policy["frappe"]
        frappe.get_doc = lambda _doctype, name, **_kw: doc if name == target else None
        frappe.db.get_singles_dict = lambda _dt: {"policy_snapshot": doc.policy_snapshot}
        frappe.db.get_all = lambda _dt, filters, **_kw: events[:2] if filters["target"] == target else []
        frappe.db.get_value = lambda *args, **kwargs: events[0]["after_hash"] if events else None
        self.policy["_validated_governing_owner_operations"] = lambda _date=None: (
            self.fail("Dedicated settings must not read unrelated Owner policy"))

        def execute(kind, key, payload, work):
            self.assertEqual(kind, action)
            result, event = work("owner@example.invalid")
            events.insert(0, dict(event, action=kind, creation=f"2026-10-08 12:00:0{len(events)}"))
            return result

        self.policy["configuration_audit"].execute = execute
        terms = {k: v for k, v in valid_terms().items() if k.startswith("backup_") or k in {
            "custody_requirement", "recovery_quorum", "reason"}}
        configure = self.policy["configure_local_backup_policy"]
        with self.assertRaisesRegex(ValueError, "Recovery quorum"):
            configure("bad-quorum", **dict(terms, recovery_quorum=None))
        with self.assertRaisesRegex(ValueError, "Key custody requirement"):
            configure("bad-custody", **dict(terms, custody_requirement=""))
        self.assertEqual(events, [])

        result = configure("first-valid", **terms)
        self.assertEqual(result["status"], "Validated")
        self.assertNotIn("backup_recovery_public_key", result)
        self.assertEqual(set(json.loads(doc.policy_snapshot)), {*terms, "effective_from", "policy_nonce"})
        previous = self.policy["current_backup_policy"]()
        self.assertEqual(previous["schedule_time"], "02:30")
        self.assertEqual(base64.b64decode(self.policy["current_backup_public_key_b64"]()).decode(), TEST_PUBLIC_KEY)

        earlier_snapshot = doc.policy_snapshot
        configure("second-valid", **terms)
        self.assertEqual(events[0]["before_hash"], events[1]["after_hash"])
        self.assertNotEqual(previous["policy_hash"], self.policy["current_backup_policy"]()["policy_hash"])

        # Missing/malformed state, a stale snapshot and ambiguous evidence
        # all fail closed instead of reverting to the legacy policy.
        current_snapshot = doc.policy_snapshot
        for raw in ("", "{", earlier_snapshot):
            doc.policy_snapshot = raw
            self.assertEqual(self.policy["current_backup_policy"](),
                             {"configured": False, "status": "NOT CONFIGURED"})
            self.assertEqual(self.policy["current_backup_public_key_b64"](), "")
        doc.policy_snapshot = current_snapshot
        events[1]["creation"] = events[0]["creation"]
        self.assertFalse(self.policy["current_backup_policy"]()["configured"])

    def test_normalizes_native_time_values_without_defaulting(self):
        terms = self.policy["validate_terms"](valid_terms(backup_schedule_time="02:30:00"))
        self.assertEqual(terms["backup_schedule_time"], "02:30")
        self.assertEqual(terms["backup_retention_versions"], 3)
        self.assertEqual(terms["backup_retention_behavior"], "Preserve all valid backup sets")

    def test_missing_or_invalid_time_and_retention_fail_closed(self):
        for update in (
            {"backup_schedule_time": ""},
            {"backup_schedule_time": "25:00"},
            {"backup_schedule_time": "2:30"},
            {"backup_retention_versions": None},
            {"backup_retention_versions": 1},
            {"backup_retention_versions": True},
            {"backup_retention_versions": 10001},
            {"backup_retention_behavior": ""},
            {"backup_retention_behavior": "Unreviewed automatic deletion"},
            {"tax_rate": True},
            {"tax_rate": "NaN"},
            {"tax_rate": "Infinity"},
            {"backup_recovery_public_key": ""},
            {"backup_recovery_public_key": "-----BEGIN PGP PRIVATE KEY BLOCK-----"},
            {"backup_recovery_public_key": "not an armored key"},
            {"backup_recovery_public_key": TEST_PUBLIC_KEY + "\u2603"},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.policy["validate_terms"](valid_terms(**update))

    def test_missing_switch_is_off_even_with_complete_owner_policy(self):
        self.policy["frappe"].db.get_single_value = lambda *_: None
        self.assertEqual(
            self.policy["backup_switch_state"](),
            {"enabled": False, "status": "OFF", "switch_nonce": ""},
        )
        terms = valid_terms()
        terms["effective_from"] = "2026-10-07"
        self.policy["_validated_governing_owner_operations"] = lambda _date=None: terms
        self.assertEqual(
            self.policy["current_backup_policy"](),
            {"configured": False, "status": "OFF"},
        )
        self.assertEqual(self.policy["current_backup_public_key_b64"](), "")

    def test_on_requires_valid_change_identity(self):
        self.policy["frappe"].db.get_single_value = (
            lambda _dt, field: "1" if field == "enabled" else "bad")
        self.assertEqual(
            self.policy["current_backup_policy"](),
            {"configured": False, "status": "OFF"},
        )

    def test_re_enable_invalidates_previous_policy_hash(self):
        terms = valid_terms()
        terms["effective_from"] = "2026-10-07"
        self.policy["_validated_governing_owner_operations"] = lambda _date=None: terms
        first = self.policy["current_backup_policy"]()
        self.policy["frappe"].db.get_single_value = (
            lambda _dt, field: "1" if field == "enabled" else "e" * 32)
        second = self.policy["current_backup_policy"]()
        self.assertTrue(first["configured"] and second["configured"])
        self.assertNotEqual(first["policy_hash"], second["policy_hash"])

    def test_preexisting_legacy_version_remains_saveable_but_unconfigured(self):
        legacy = valid_terms()
        legacy.pop("backup_schedule_time")
        legacy.pop("backup_retention_versions")
        legacy.pop("backup_retention_behavior")
        legacy.pop("backup_recovery_public_key")
        normalized = self.policy["validate_terms"](legacy, allow_legacy_backup=True)
        self.assertEqual(normalized["backup_schedule_time"], "")
        self.assertIsNone(normalized["backup_retention_versions"])
        self.assertEqual(normalized["backup_retention_behavior"], "")
        self.policy["_validated_governing_owner_operations"] = lambda _date=None: legacy
        result = self.policy["current_backup_policy"]()
        self.assertEqual(result, {"configured": False, "status": "NOT CONFIGURED"})

    def test_legacy_schedule_without_recovery_key_remains_saveable_but_unconfigured(self):
        legacy = valid_terms()
        legacy.pop("backup_retention_behavior")
        legacy.pop("backup_recovery_public_key")
        normalized = self.policy["validate_terms"](legacy, allow_legacy_backup=True)
        self.assertEqual(normalized["backup_schedule_time"], "02:30")
        self.assertEqual(normalized["backup_retention_versions"], 3)
        self.policy["_validated_governing_owner_operations"] = lambda _date=None: legacy
        self.assertEqual(
            self.policy["current_backup_policy"](),
            {"configured": False, "status": "NOT CONFIGURED"},
        )

    def test_runtime_policy_requires_current_validation_after_every_policy_change(self):
        rows = [{"effective_from": "2026-10-07", "backup_schedule_time": "02:30"}]
        snapshot = self.policy["foundation"].snapshot_digest(rows)
        events = [{
            "action": "validate_owner_operations_policy",
            "after_hash": snapshot,
            "creation": "2026-10-07 10:00:00.000000",
        }]

        def read_events(doctype, *, filters, fields, limit_page_length):
            self.assertEqual(doctype, "TH Configuration Audit Event")
            self.assertEqual(filters, {"target": "OWNER-OPERATIONS"})
            self.assertEqual(fields, ["action", "after_hash", "creation"])
            self.assertEqual(limit_page_length, 0)
            return events

        self.policy["frappe"].db.get_all = read_events
        is_current = self.policy["_owner_policy_validation_is_current"]
        self.assertTrue(is_current("OWNER-OPERATIONS", rows))

        events.append({
            "action": "set_owner_operations_policy_version",
            "after_hash": "new-snapshot",
            "creation": "2026-10-07 10:00:01.000000",
        })
        self.assertFalse(is_current("OWNER-OPERATIONS", rows))

        events[-1]["creation"] = "2026-10-07 10:00:00.000000"
        self.assertFalse(is_current("OWNER-OPERATIONS", rows),
                         "same-time ordering is ambiguous and must fail closed")

        events.append({
            "action": "validate_owner_operations_policy",
            "after_hash": snapshot,
            "creation": "2026-10-07 10:00:02.000000",
        })
        self.assertTrue(is_current("OWNER-OPERATIONS", rows))

        self.assertFalse(is_current("", rows))
        self.assertFalse(is_current("OWNER-OPERATIONS", []))

    def test_public_owner_resolver_uses_validation_gated_terms(self):
        sentinel = {"effective_from": "2026-10-08", "capacity_target": 20}
        calls = []
        self.policy["_validated_governing_owner_operations"] = (
            lambda on_date=None: calls.append(on_date) or sentinel)
        self.assertEqual(
            self.policy["governing_owner_operations"]("2026-10-08"),
            sentinel)
        self.assertEqual(calls, ["2026-10-08"])

    def test_backup_resolver_fails_closed_until_current_snapshot_is_validated(self):
        terms = valid_terms()
        terms["effective_from"] = "2026-10-07"

        class VersionRow:
            def as_dict(self):
                return dict(terms)

        doc = SimpleNamespace(
            name="TH-OWNER-OPS", status="Active",
            get=lambda field: [VersionRow()] if field == "versions" else None,
        )
        self.policy["_policy_doc"] = lambda: doc
        events = []
        self.policy["frappe"].db.get_all = lambda _dt, filters, **_kw: (
            events if filters["target"] == doc.name else [])
        resolve = self.policy["_validated_governing_owner_operations"]
        self.assertEqual(resolve(), {}, "missing validation evidence must not resolve backup policy")
        self.assertEqual(
            self.policy["current_backup_policy"](),
            {"configured": False, "status": "NOT CONFIGURED"},
        )

        snapshot = self.policy["foundation"].snapshot_digest([terms])
        events.append({
            "action": "validate_owner_operations_policy",
            "after_hash": snapshot,
            "creation": "2026-10-08 10:00:00.000000",
        })
        expected_terms = {field: terms.get(field) for field in self.policy["GOVERNING_FIELDS"]}
        self.assertEqual(resolve(), expected_terms)
        self.assertTrue(self.policy["current_backup_policy"]()["configured"])

        events.append({
            "action": "set_owner_operations_policy_status",
            "after_hash": "status-change",
            "creation": "2026-10-08 10:00:01.000000",
        })
        self.assertEqual(resolve(), {}, "a later status change invalidates runtime validation")
        self.assertEqual(
            self.policy["current_backup_policy"](),
            {"configured": False, "status": "NOT CONFIGURED"},
        )

    def test_missing_retention_behavior_keeps_backup_policy_unconfigured(self):
        terms = valid_terms()
        terms.pop("backup_retention_behavior")
        terms["effective_from"] = "2026-10-07"
        self.policy["_validated_governing_owner_operations"] = lambda _date=None: terms
        self.assertEqual(
            self.policy["current_backup_policy"](),
            {"configured": False, "status": "NOT CONFIGURED"},
        )

    def test_current_effective_terms_have_stable_non_secret_identity(self):
        terms = valid_terms()
        terms["effective_from"] = "2026-10-07"
        self.policy["_validated_governing_owner_operations"] = lambda _date=None: terms
        result = self.policy["current_backup_policy"]()
        identity = {
            "effective_from": "2026-10-07",
            "schedule_time": "02:30",
            "retention_versions": 3,
            "retention_behavior": "Preserve all valid backup sets",
            "recovery_key_sha256": hashlib.sha256(
                TEST_PUBLIC_KEY.strip().encode("utf-8")).hexdigest(),
            "switch_nonce": "f" * 32,
        }
        expected = hashlib.sha256(json.dumps(
            identity, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        self.assertTrue(result["configured"])
        self.assertEqual(result["status"], "CONFIGURED")
        self.assertEqual(result["policy_hash"], expected)
        self.assertEqual(set(result), {
            "configured", "status", "schedule_time", "retention_versions",
            "retention_behavior", "recovery_key_sha256", "effective_from", "policy_hash",
        })
        self.assertNotIn("custody_requirement", result)
        self.assertNotIn("reason", result)

        delete_terms = valid_terms(
            backup_retention_behavior="Delete valid older sets beyond keep count")
        delete_terms["effective_from"] = "2026-10-07"
        self.policy["_validated_governing_owner_operations"] = lambda _date=None: delete_terms
        delete_result = self.policy["current_backup_policy"]()
        self.assertTrue(delete_result["configured"])
        self.assertEqual(
            delete_result["retention_behavior"],
            "Delete valid older sets beyond keep count")
        self.assertNotEqual(delete_result["policy_hash"], result["policy_hash"])

    def test_public_key_export_is_ascii_base64_and_fails_closed(self):
        terms = valid_terms()
        terms["effective_from"] = "2026-10-07"
        self.policy["_validated_governing_owner_operations"] = lambda _date=None: terms
        encoded = self.policy["current_backup_public_key_b64"]()
        self.assertEqual(base64.b64decode(encoded).decode("ascii"), TEST_PUBLIC_KEY.strip())

        terms["backup_recovery_public_key"] = "-----BEGIN PGP PRIVATE KEY BLOCK-----"
        self.assertEqual(self.policy["current_backup_public_key_b64"](), "")

    def test_invalid_effective_terms_are_reported_not_repaired(self):
        terms = valid_terms(backup_retention_versions=1)
        terms["effective_from"] = "2026-10-07"
        self.policy["_validated_governing_owner_operations"] = lambda _date=None: terms
        self.assertEqual(
            self.policy["current_backup_policy"](),
            {"configured": False, "status": "NOT CONFIGURED"},
        )


if __name__ == "__main__":
    unittest.main()

"""Contracts for the global Course Owner operational policy carrier."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps" / "toefl_house" / "toefl_house"
POLICY = APP / "operations" / "doctype" / "th_owner_operations_policy" / "th_owner_operations_policy.json"
VERSION = APP / "operations" / "doctype" / "th_owner_operations_policy_version" / "th_owner_operations_policy_version.json"
SOURCE = APP / "operations" / "owner_configuration.py"
DESK = APP / "desk" / "configuration.py"


class OwnerOperationsDoctypeTests(unittest.TestCase):
    def test_parent_is_course_owner_only_and_tracks_changes(self):
        doc = json.loads(POLICY.read_text(encoding="utf-8"))
        self.assertEqual(doc["name"], "TH Owner Operations Policy")
        self.assertEqual(doc["module"], "Operations")
        self.assertEqual(doc["track_changes"], 1)
        roles = {row["role"]: row for row in doc["permissions"]}
        self.assertEqual(set(roles), {"Course Owner"})
        self.assertEqual(roles["Course Owner"]["delete"], 0)

    def test_version_contains_all_owner_decisions(self):
        doc = json.loads(VERSION.read_text(encoding="utf-8"))
        fields = {row["fieldname"]: row for row in doc["fields"]}
        required = {
            "reporting_review_days", "capacity_target", "tax_enabled",
            "tax_rate", "tax_inclusive", "transfer_allowed",
            "withdrawal_allowed", "calendar_notice_days",
            "backup_offsite_required", "backup_destination_kind",
            "backup_destination_reference", "custody_requirement",
            "recovery_quorum", "effective_from", "reason", "set_by",
            "set_on", "superseded_on",
        }
        self.assertTrue(required.issubset(fields))
        self.assertEqual(fields["tax_rate"]["fieldtype"], "Percent")
        self.assertEqual(fields["backup_destination_reference"]["fieldtype"], "Data")
        self.assertEqual(fields["backup_destination_kind"]["options"], "Owner-controlled off-site hardware")
        self.assertIn('DESTINATION_KINDS = ("Owner-controlled off-site hardware",)', SOURCE.read_text(encoding="utf-8"))

    def test_secrets_are_explicitly_out_of_scope(self):
        text = VERSION.read_text(encoding="utf-8") + SOURCE.read_text(encoding="utf-8")
        lowered = text.lower()
        self.assertNotIn("secret_material", lowered)
        self.assertIn("credentials", lowered)
        self.assertIn("authorization", lowered)

    def test_d14_destination_boundary_is_owner_controlled_hardware_only(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('DESTINATION_KINDS = ("Owner-controlled off-site hardware",)', source)
        self.assertNotIn("S3-compatible", source)
        self.assertNotIn("Managed backup", source)
        self.assertNotIn("SFTP", source)
        policy_text = VERSION.read_text(encoding="utf-8") + source
        self.assertIn("ceremonies", policy_text.lower())


class OwnerOperationsCommandTests(unittest.TestCase):
    def test_commands_are_guarded_and_versioned(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        names = {node.name: node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef)}
        expected = (
            "create_owner_operations_policy",
            "set_owner_operations_policy_version",
            "set_owner_operations_policy_status",
            "validate_owner_operations_policy",
        )
        for name in expected:
            self.assertIn(name, names)
            source = ast.unparse(names[name])
            self.assertIn("configuration_audit.execute", source)
        self.assertIn("check_appends", ast.unparse(names["set_owner_operations_policy_version"]))
        self.assertIn("compute_readiness", ast.unparse(names["validate_owner_operations_policy"]))

    def test_configuration_desk_exposes_guarded_owner_commands(self):
        text = DESK.read_text(encoding="utf-8")
        client = (APP / "public" / "js" / "th_role_desks.js").read_text(encoding="utf-8")
        for endpoint in (
            "create_owner_operations_policy",
            "set_owner_operations_policy_version",
            "set_owner_operations_policy_status",
            "validate_owner_operations_policy",
        ):
            self.assertIn(endpoint, text)
            self.assertIn(endpoint, client)
        native_endpoints = (
            "create_catalog_linkage_policy", "set_catalog_linkage_version", "set_catalog_linkage_status",
            "create_returning_student_policy", "set_returning_student_policy_version", "set_returning_student_policy_status",
            "create_enrollment_exit_policy", "set_enrollment_exit_policy_version", "set_enrollment_exit_policy_status",
            "create_billing_policy", "set_billing_policy_version", "set_billing_policy_status",
            "create_roster_change_policy", "set_roster_change_policy_version", "set_roster_change_policy_status",
            "create_attendance_correction_policy", "set_attendance_correction_policy_version", "set_attendance_correction_policy_status",
            "create_adjustment_posting_policy", "set_adjustment_posting_version", "set_adjustment_posting_status",
        )
        for endpoint in native_endpoints:
            self.assertIn(endpoint, text)
            self.assertIn(endpoint, client)
        self.assertIn('("configuration", "TH Owner Operations Policy")', (APP / "desk" / "__init__.py").read_text(encoding="utf-8"))

    def test_configuration_desk_no_longer_calls_domains_unimplemented(self):
        text = DESK.read_text(encoding="utf-8")
        self.assertIn("TH Owner Operations Policy", text)
        self.assertNotIn("configuration surface\": \"Not implemented", text)
        self.assertNotIn("arrives in a later phase", text)


if __name__ == "__main__":
    unittest.main()

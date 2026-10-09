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
AUDIT = APP / "configuration" / "audit.py"
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
            "backup_schedule_time", "backup_retention_versions",
            "backup_retention_behavior", "backup_recovery_public_key",
            "custody_requirement",
            "recovery_quorum", "effective_from",
            "reason", "set_by", "set_on", "superseded_on",
        }
        self.assertTrue(required.issubset(fields))
        self.assertEqual(fields["tax_rate"]["fieldtype"], "Percent")
        self.assertEqual(fields["backup_schedule_time"]["fieldtype"], "Time")
        self.assertEqual(fields["backup_retention_versions"]["fieldtype"], "Int")
        self.assertEqual(fields["backup_retention_behavior"]["fieldtype"], "Select")
        self.assertIn("Preserve all valid backup sets",
                      fields["backup_retention_behavior"]["options"])
        self.assertIn("Delete valid older sets beyond keep count",
                      fields["backup_retention_behavior"]["options"])
        self.assertEqual(fields["backup_recovery_public_key"]["fieldtype"], "Small Text")
        self.assertEqual(fields["backup_schedule_time"]["reqd"], 0,
                         "legacy versions must remain saveable until the Owner adds backup policy")
        self.assertEqual(fields["backup_retention_behavior"]["reqd"], 0,
                         "legacy versions remain readable; the current backup resolver still fails closed without a choice")
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("MIN_BACKUP_VERSIONS = 2", source)
        self.assertIn("MAX_BACKUP_PUBLIC_KEY", source)
        self.assertIn("current_backup_policy", source)
        client = (APP / "public" / "js" / "th_role_desks.js").read_text(encoding="utf-8")
        self.assertIn('fieldname: "backup_schedule_time"', client)
        self.assertIn('fieldname: "backup_retention_versions"', client)
        self.assertIn('fieldname: "backup_retention_behavior"', client)
        self.assertIn("Leaving this unset keeps backup and activation fail-closed", client)
        self.assertIn('fieldname: "backup_recovery_public_key"', client)
        self.assertIn('fieldname: "tax_rate", label: "Tax rate (decision input only; %)"', client)
        for field in ("tax_enabled", "tax_inclusive", "transfer_allowed", "withdrawal_allowed"):
            self.assertIn(f'fieldname: "{field}"', client)
            self.assertIn('fieldtype: "Select", options: "\\nYes\\nNo", reqd: 1', client)
        for field in ("reporting_review_days", "capacity_target", "tax_enabled",
                      "tax_rate", "tax_inclusive", "transfer_allowed",
                      "withdrawal_allowed", "calendar_notice_days"):
            self.assertIn("decision input only", fields[field].get("description", "").lower())
        self.assertIn("not consumed by that resolver",
                      fields["withdrawal_allowed"]["description"])
        self.assertIn("no current report runner consumes this value",
                      fields["reporting_review_days"]["description"].lower())
        self.assertIn("max_strength", fields["capacity_target"]["description"])
        self.assertIn("tax configuration remains authoritative",
                      fields["tax_rate"]["description"])

    def test_secrets_are_explicitly_out_of_scope(self):
        text = VERSION.read_text(encoding="utf-8") + SOURCE.read_text(encoding="utf-8")
        lowered = text.lower()
        self.assertNotIn("secret_material", lowered)
        self.assertIn("credentials", lowered)
        self.assertIn("authorization", lowered)

    def test_backup_policy_is_local_owner_configured_and_fail_closed(self):
        source = SOURCE.read_text(encoding="utf-8")
        doctype = VERSION.read_text(encoding="utf-8")
        self.assertIn("MIN_BACKUP_VERSIONS = 2", source)
        self.assertIn('"configured": False, "status": "NOT CONFIGURED"', source)
        self.assertIn("backup_schedule_time", doctype)
        self.assertIn("backup_retention_versions", doctype)
        self.assertIn("backup_retention_behavior", doctype)
        self.assertIn("No default; an unset choice keeps backup and activation policy unconfigured.", doctype)
        self.assertIn("backup_retention_behavior", source)
        self.assertNotIn("backup_offsite_required", source)
        self.assertNotIn("backup_destination_kind", source)
        legacy_fields = {row["fieldname"]: row for row in json.loads(doctype)["fields"]
                         if row["fieldname"].startswith("backup_offsite")
                         or row["fieldname"].startswith("backup_destination")}
        self.assertEqual(set(legacy_fields), {
            "backup_offsite_required", "backup_destination_kind",
            "backup_destination_reference",
        })
        self.assertTrue(all(row.get("hidden") and row.get("read_only")
                            for row in legacy_fields.values()))
        client = (APP / "public" / "js" / "th_role_desks.js").read_text(encoding="utf-8")
        self.assertNotIn('fieldname: "backup_offsite_required"', client)
        self.assertIn("ceremonies", (doctype + source).lower())


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
        governing_source = ast.unparse(names["_governing_owner_terms"])
        self.assertIn("resolve_governing_strict", governing_source,
                      "corrupt or ambiguous version history must fail closed at runtime")
        backup_resolver = ast.unparse(names["_validated_governing_owner_operations"])
        self.assertIn("_owner_policy_validation_is_current", backup_resolver,
                      "runtime backup policy must require current validation evidence")
        audit_tree = ast.parse(AUDIT.read_text(encoding="utf-8"))
        authorities = next(ast.literal_eval(node.value) for node in audit_tree.body
                           if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name)
                                   and target.id == "KIND_AUTHORITY"
                                   for target in node.targets))
        for name in expected:
            self.assertEqual(authorities.get(name), "business_policy",
                             f"{name} must use the guarded Course Owner authority")

    def test_configuration_desk_exposes_guarded_owner_commands(self):
        text = DESK.read_text(encoding="utf-8")
        client = (APP / "public" / "js" / "th_role_desks.js").read_text(encoding="utf-8")
        self.assertIn("Complete every required Owner field with approved values", text)
        self.assertIn("no defaults or placeholders", text)
        self.assertIn("Backup TOEFL House ERP.cmd", text)
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

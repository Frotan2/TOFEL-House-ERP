"""Executable role-scoped handoff tests for the real create_case command.

The production path must require a recorded reception inquiry at the same
Branch, with confirmed Awaiting Placement status and matching test/live mode.
Native MariaDB transaction/concurrency acceptance remains a separate gate.
"""
import ast
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "apps/toefl_house/toefl_house/api.py").read_text(encoding="utf-8")
SOURCE_AST = ast.parse(SOURCE)


class Denied(Exception):
    pass


class Invalid(Exception):
    pass


def source_function():
    fn = next(node for node in SOURCE_AST.body
              if isinstance(node, ast.FunctionDef) and node.name == "create_case")
    fn.decorator_list = []
    return compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])),
                   "api.py", "exec")


class ReceptionToPlacementHandoffTests(unittest.TestCase):
    def setUp(self):
        self.status = "Awaiting Placement"
        self.inquiry_branch = "Branch A"
        self.mode_stamp = 0
        self.cases = []
        self.enabled = True
        self.has_inquiry = True
        self.actor_branch = "Branch A"
        self.production = True

        fixture = self
        frappe = types.ModuleType("frappe")
        frappe.PermissionError = Denied
        frappe.ValidationError = Invalid

        def get_value(doctype, key, field, as_dict=False):
            if doctype == "User" and field == "enabled":
                return fixture.enabled
            if doctype == "TH Reception Inquiry" and as_dict:
                if not fixture.has_inquiry or key != "INQ-A":
                    return None
                return types.SimpleNamespace(name="INQ-A", person_name="Visitor",
                    th_branch=fixture.inquiry_branch, status=fixture.status,
                    synthetic=fixture.mode_stamp)
            raise AssertionError(f"Unexpected DB read: {doctype} {field}")

        def exists(doctype, key):
            if doctype == "Branch":
                return key in ("Branch A", "Branch B")
            if doctype == "TH Placement Case":
                if "subject" in key:
                    return any(doc.subject == key["subject"] for doc in fixture.cases)
                if "reception_inquiry" in key:
                    return any(doc.reception_inquiry == key["reception_inquiry"] for doc in fixture.cases)
            raise AssertionError(f"Unexpected existence check {doctype} {key}")

        frappe.db = types.SimpleNamespace(get_value=get_value, exists=exists)
        def get_doc(fields):
            record = types.SimpleNamespace(name=f"CASE-{len(fixture.cases) + 1}", **fields)
            def insert(ignore_permissions=False):
                assert ignore_permissions
                fixture.cases.append(record)
                return record
            record.insert = insert
            return record
        frappe.get_doc = get_doc
        self.frappe = frappe

        scope = types.ModuleType("toefl_house.command_scope")
        def branch_choice(requested, actor):
            if actor != "publisher" or requested != fixture.actor_branch:
                raise Denied("Publisher is not allowed to create a case at this Branch")
            return requested
        scope.resolve_creation_branch = branch_choice

        root = types.ModuleType("toefl_house")
        root.__path__ = []
        self.patch = patch.dict(sys.modules, {
            "toefl_house": root,
            "toefl_house.command_scope": scope,
        })
        self.patch.start()
        self.addCleanup(self.patch.stop)

        self.env = {
            "frappe": frappe,
            "is_production": lambda: fixture.production,
            "SYNTHETIC_PURPOSE": "synthetic-placement",
            "record_synthetic_flag": lambda: 0 if fixture.production else 1,
            "CASE": "TH Placement Case",
            "digest": lambda values: "digest",
            "_execute": lambda kind, key, payload, work: work("publisher")[0],
        }
        exec(source_function(), self.env)

    def create(self, inquiry="INQ-A", branch="Branch A", subject=""):
        purpose = "Initial placement" if self.production else "synthetic-placement"
        return self.env["create_case"](
            "request-case-test-01", subject, purpose, branch, inquiry)

    def test_authorized_staff_handoff_retains_inquiry_and_branch(self):
        result = self.create()
        self.assertEqual(result["reception_inquiry"], "INQ-A")
        self.assertEqual(self.cases[0].reception_inquiry, "INQ-A")
        self.assertEqual(self.cases[0].th_branch, "Branch A")
        self.assertEqual(self.cases[0].synthetic, 0)
        self.assertTrue(result["subject"].startswith("THV-"))
        self.assertNotIn("@", result["subject"])

    def test_branch_mismatch_is_denied_before_case_created(self):
        self.inquiry_branch = "Branch B"
        with self.assertRaises(Denied):
            self.create()
        self.assertFalse(self.cases)

    def test_nonready_or_closed_inquiry_is_not_a_placement_referral(self):
        for status in ("New", "Contacted", "Closed"):
            with self.subTest(status=status):
                self.status = status
                with self.assertRaises(Invalid):
                    self.create()
        self.assertFalse(self.cases)

    def test_missing_inquiry_or_wrong_mode_cannot_start_live_placement(self):
        with self.assertRaises(Invalid):
            self.create(inquiry="")
        self.mode_stamp = 1
        with self.assertRaises(Denied):
            self.create()
        self.mode_stamp = None
        with self.assertRaises(Denied):
            self.create()
        self.mode_stamp = 0
        self.has_inquiry = False
        with self.assertRaises(Denied):
            self.create()
        self.assertFalse(self.cases)

    def test_duplicate_referral_and_fabricated_email_are_refused(self):
        self.create()
        with self.assertRaises(Invalid):
            self.create()
        with self.assertRaises(Invalid):
            self.create(subject="fake@example.test")
        self.assertEqual(len(self.cases), 1)

    def test_synthetic_legacy_case_can_omit_reception_handoff(self):
        self.production = False
        result = self.create(inquiry="", branch="", subject="synthetic@example.test")
        self.assertEqual(result["status"], "Open")
        self.assertEqual(result["reception_inquiry"], "")
        self.assertEqual(self.cases[0].synthetic, 1)


if __name__ == "__main__":
    unittest.main()

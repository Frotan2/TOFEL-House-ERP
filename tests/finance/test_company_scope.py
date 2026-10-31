"""Native Company User Permission is binding inside guarded money commands.

Fee issuance deliberately writes native Education/ERPNext documents through
audited, ignore_permissions internal operations. Such operations must still
respect a scoped Finance Officer's Company boundary.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
SOURCE = APP / "finance" / "company_scope.py"


class CompanyScopeTests(unittest.TestCase):
    def setUp(self):
        self.allowed = []
        self.existing = {"TOEFL House", "Other School"}
        self.actor = "finance@example.test"
        self.queries = []

        def get_all(doctype, **kwargs):
            self.queries.append((doctype, kwargs))
            if doctype == "User Permission":
                return list(self.allowed)
            return []

        fake = types.ModuleType("frappe")
        fake.session = types.SimpleNamespace(user=self.actor)
        fake.db = types.SimpleNamespace(
            exists=lambda doctype, name: doctype == "Company" and name in self.existing)
        fake.get_all = get_all
        fake.PermissionError = type("FinancePermissionError", (Exception,), {})
        fake.ValidationError = type("FinanceValidationError", (Exception,), {})
        self.frappe = fake
        replacement = patch.dict(sys.modules, {"frappe": fake})
        replacement.start()
        self.addCleanup(replacement.stop)
        spec = importlib.util.spec_from_file_location("scoped_finance_test", SOURCE)
        self.scope = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.scope)

    def test_hq_without_company_permission_remains_unrestricted(self):
        self.assertEqual(self.scope.require_finance_company("TOEFL House"), "TOEFL House")
        self.assertEqual(self.scope.require_finance_company("Other School"), "Other School")
        self.assertEqual(self.queries[-1][0], "User Permission")
        self.assertEqual(self.queries[-1][1]["filters"],
                         {"user": self.actor, "allow": "Company"})

    def test_restricted_finance_actor_can_write_only_allowed_company(self):
        self.allowed = ["TOEFL House"]
        self.assertEqual(self.scope.require_finance_company("TOEFL House"), "TOEFL House")
        with self.assertRaises(self.frappe.PermissionError):
            self.scope.require_finance_company("Other School")

    def test_native_dict_shape_for_user_permission_is_supported(self):
        self.allowed = [{"for_value": "Other School"}]
        self.assertEqual(self.scope.require_finance_company("Other School"), "Other School")
        with self.assertRaises(self.frappe.PermissionError):
            self.scope.require_finance_company("TOEFL House")

    def test_unknown_and_blank_companies_fail_before_money_writes(self):
        for company in ("", None, " ", "No Such Company", "X" * 141):
            with self.subTest(company=repr(company)):
                with self.assertRaises(self.frappe.ValidationError):
                    self.scope.require_finance_company(company)

    def test_reserved_or_anonymous_actor_cannot_invoke_helper(self):
        for actor in ("Guest", "Administrator", "", None):
            self.frappe.session.user = actor
            with self.subTest(actor=repr(actor)):
                with self.assertRaises(self.frappe.PermissionError):
                    self.scope.require_finance_company("TOEFL House")

    def test_every_guarded_fee_issuance_command_calls_scope_helper(self):
        single = (APP / "finance" / "__init__.py").read_text(encoding="utf-8")
        installments = (APP / "finance" / "installments.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(single.count("require_finance_company("), 2)
        self.assertIn("require_finance_company(COMPANY)", single)
        self.assertIn("require_finance_company(company)", single)
        self.assertIn("require_finance_company(company)", installments)
        # The check must precede every privileged native Fees submission.
        self.assertLess(single.index("require_finance_company(company)"),
                        single.index("fees.insert(ignore_permissions=True)"))
        self.assertLess(installments.index("require_finance_company(company)"),
                        installments.index("fees.insert(ignore_permissions=True)"))

        payroll = (APP / "teaching" / "compensation.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(payroll.count("require_finance_company("), 3)
        self.assertIn('require_finance_company(company_name)', payroll)
        self.assertIn('require_finance_company(frappe.db.get_value(EMPLOYEE, old.employee, "company"))', payroll)
        self.assertIn('require_finance_company(frappe.db.get_value(EMPLOYEE, employee_name, "company"))', payroll)
        self.assertLess(payroll.index("require_finance_company(company_name)"),
                        payroll.index("salary.insert(ignore_permissions=True)"))


if __name__ == "__main__":
    unittest.main()

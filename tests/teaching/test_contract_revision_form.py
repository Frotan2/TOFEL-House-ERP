"""Private pay rates are prefilled only after native read AND company authorization.

Run the production GET endpoint body against isolated Finance/HRMS doubles.
No production or test database is mutated.
"""
import ast
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

SOURCE = (Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
          / "toefl_house" / "teaching" / "compensation.py")


def real_reader(namespace):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    code = [n for n in tree.body if isinstance(n, ast.FunctionDef)
            and n.name == "get_contract_revision_form"]
    assert len(code) == 1
    code[0].decorator_list = []
    exec(compile(ast.Module(body=code, type_ignores=[]),
                 str(SOURCE), "exec"), namespace)
    return namespace["get_contract_revision_form"]


def fake_contract(skill_count=2, adjustment_count=1):
    skill = lambda index: types.SimpleNamespace(
        skill="SPK" if index == 0 else "WRT",
        unit_of_payment="Class", rate=2000, payable_quantity=2,
        minimum_amount=500, maximum_amount=5000)
    adjustment = lambda index: types.SimpleNamespace(
        adjustment_type="Bonus", amount=100,
        effective_date="2026-10-31", approver="finance@example.invalid",
        reason="Approved bonus")
    children = {
        "skill_terms": [skill(i) for i in range(skill_count)],
        "adjustments": [adjustment(i) for i in range(adjustment_count)],
    }
    return types.SimpleNamespace(
        name="TH-IC-1", employee="EMP-1", status="Active",
        compensation_model="Skill-Based", assignment_basis="Assigned skill",
        payment_frequency="Monthly", conditions="Approved conditions",
        earning_basis="Solar Hijri Monthly",
        effective_start="2026-10-01", effective_end=None,
        get=lambda key: children[key])


class AuthorizedContractPrefillTests(unittest.TestCase):
    def run_reader(self, permission=True, company_allowed=True,
                   skill_count=2, adjustment_count=1):
        get_doc = Mock(return_value=fake_contract(skill_count, adjustment_count))
        has_permission = Mock(return_value=permission)
        scope = Mock(side_effect=None if company_allowed
                     else PermissionError("Wrong company"))
        frappe = types.SimpleNamespace(
            has_permission=has_permission, get_doc=get_doc,
            db=types.SimpleNamespace(get_value=lambda *args: "TOEFL House"),
            ValidationError=ValueError, PermissionError=PermissionError)
        scope_mod = types.ModuleType("toefl_house.finance.company_scope")
        scope_mod.require_finance_company = scope
        ns = {"frappe": frappe,
              "_bounded": lambda value, label: value,
              "CONTRACT": "TH Instructor Contract", "EMPLOYEE": "Employee"}
        with patch.dict(sys.modules, {
            "toefl_house": types.ModuleType("toefl_house"),
            "toefl_house.finance": types.ModuleType("toefl_house.finance"),
            "toefl_house.finance.company_scope": scope_mod,
        }):
            return real_reader(ns)("TH-IC-1"), get_doc, has_permission, scope

    def test_full_existing_terms_and_limits_are_preserved(self):
        result, get_doc, permission, scope = self.run_reader()
        self.assertEqual(result["contract"], "TH-IC-1")
        self.assertEqual(len(result["skill_terms"]), 2)
        self.assertEqual(result["skill_terms"][0]["minimum_amount"], 500)
        self.assertEqual(result["skill_terms"][0]["maximum_amount"], 5000)
        self.assertEqual(result["adjustments"][0]["amount"], 100)
        permission.assert_called_once_with(
            "TH Instructor Contract", ptype="read", doc="TH-IC-1")
        scope.assert_called_once_with("TOEFL House")
        get_doc.assert_called_once_with("TH Instructor Contract", "TH-IC-1")

    def test_reader_never_fetches_document_without_read_permission(self):
        with self.assertRaisesRegex(PermissionError, "reading permission"):
            self.run_reader(permission=False)

    def test_cross_company_salary_details_are_denied(self):
        with self.assertRaisesRegex(PermissionError, "Wrong company"):
            self.run_reader(company_allowed=False)

    def test_oversized_terms_fail_closed_without_truncation(self):
        for skills, adjustments in ((7, 0), (2, 3)):
            with self.subTest(skills=skills, adjustments=adjustments):
                with self.assertRaisesRegex(ValueError, "more rows"):
                    self.run_reader(skill_count=skills, adjustment_count=adjustments)

    def test_ui_does_not_drop_pay_bounds_on_contract_replacement(self):
        js = (SOURCE.parents[2] / "toefl_house/public/js/th_role_desks.js").read_text(
            encoding="utf-8")
        self.assertIn("get_contract_revision_form", js)
        self.assertIn("current.contract !== contract", js)
        self.assertIn('values["skill_min_" + i] = row.minimum_amount;', js)
        self.assertIn('values["skill_max_" + i] = row.maximum_amount;', js)
        self.assertIn("term.minimum_amount = Number(minimum)", js)
        self.assertIn("term.maximum_amount = Number(maximum)", js)


if __name__ == "__main__":
    unittest.main()

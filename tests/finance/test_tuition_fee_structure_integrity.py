"""Native tuition billing must refuse ambiguous or malformed Fee Structures.

Executes the real shared resolver used by full-semester Fees and installments.
Isolated framework doubles keep these tests non-mutating and deterministic.
"""
import ast
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


SOURCE = (Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
          / "toefl_house" / "finance" / "__init__.py")


def production_resolver(context):
    syntax = ast.parse(SOURCE.read_text(encoding="utf-8"))
    fns = [node for node in syntax.body
           if isinstance(node, ast.FunctionDef)
           and node.name == "resolved_billable_components"]
    assert len(fns) == 1
    exec(compile(ast.Module(body=fns, type_ignores=[]), str(SOURCE), "exec"), context)
    return context["resolved_billable_components"]


class NativeBillingPlanIntegrityTests(unittest.TestCase):
    def resolve(self, plans, components, discount_rules=(), internal=False):
        calls = []
        def db_get_all(doctype, **kwargs):
            calls.append((doctype, kwargs))
            if doctype == "Fee Structure":
                return plans
            if doctype == "Fee Component":
                return [types.SimpleNamespace(**row) for row in components]
            if doctype == "TH Discount Rule":
                return discount_rules
            raise AssertionError(doctype)

        academic = types.ModuleType("toefl_house.academic")
        package = types.ModuleType("toefl_house")
        package.__path__ = [str(SOURCE.parent.parent)]
        frappe = types.SimpleNamespace(
            db=types.SimpleNamespace(get_all=db_get_all,
                                     get_value=lambda *args: "COMPANY"),
            ValidationError=ValueError)
        context = {"frappe": frappe, "FEE_STRUCTURE": "Fee Structure",
                   "_discount_family_for_native_program": lambda program: "GEN-ENG"}
        company_scope = types.ModuleType("toefl_house.finance.company_scope")
        company_scope.require_finance_company = lambda company: company
        security = types.ModuleType("toefl_house.security")
        security.is_internal_production = lambda: internal
        with patch.dict(sys.modules, {
            "toefl_house": package, "toefl_house.academic": academic,
            "toefl_house.security": security,
            "toefl_house.finance.company_scope": company_scope}):
            spec = importlib.util.spec_from_file_location(
                "offline_tuition_academic_rules", SOURCE.parent.parent / "academic" / "rules.py")
            academic.rules = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(academic.rules)
            result = production_resolver(context)(
                types.SimpleNamespace(program="N-STARTER", academic_year="1405",
                                      student="SYN-STUDENT"),
                "FS-1")
        return result, calls

    def test_one_matching_plan_bills_exactly_once(self):
        (rows, discounts, gross), calls = self.resolve(
            [{"name": "FS-1"}],
            [{"fees_category": "Semester Tuition Fee", "amount": 1000}])
        self.assertEqual(rows, [{"fees_category": "Semester Tuition Fee", "amount": 1000}])
        self.assertEqual(discounts, [])
        self.assertEqual(gross, 1000)
        self.assertEqual(calls[0][0], "Fee Structure")
        self.assertEqual(calls[0][1]["filters"]["docstatus"], ("!=", 2))
        self.assertEqual(calls[0][1]["filters"]["company"], "COMPANY")

    def test_no_plan_or_wrong_or_multiple_plan_blocks_billing(self):
        for plans in ([], [{"name": "FS-2"}],
                      [{"name": "FS-1"}, {"name": "FS-2"}]):
            with self.subTest(plans=plans), self.assertRaisesRegex(
                    ValueError, "missing, cancelled or ambiguous"):
                self.resolve(plans, [
                    {"fees_category": "Semester Tuition Fee", "amount": 1000}])

    def test_duplicate_invalid_fee_rows_block_both_billing_routes(self):
        for rows in (
            [{"fees_category": "Semester Tuition Fee", "amount": 1000},
             {"fees_category": "Semester Tuition Fee", "amount": 1000}],
            [{"fees_category": "Semester Tuition Fee", "amount": -100}],
            [{"fees_category": "", "amount": 1000}],
        ):
            with self.subTest(rows=rows), self.assertRaisesRegex(
                    ValueError, "duplicate, missing or invalid"):
                self.resolve([{"name": "FS-1"}], rows)

    def test_internal_hold_refuses_matching_awards_instead_of_issuing_gross_or_net(self):
        plans = [{"name": "FS-1"}]
        components = [{"fees_category": "Semester Tuition Fee", "amount": 1000}]
        for scope in (
            {},
            {"student": "SYN-STUDENT", "program": "GEN-ENG",
             "fee_category": "Semester Tuition Fee"},
        ):
            rule = dict(code="LEGACY", status="Active", discount_percentage=10,
                        precedence=1, **scope)
            with self.subTest(scope=scope):
                with self.assertRaisesRegex(ValueError, "Tuition was not issued.*on hold"):
                    self.resolve(plans, components, [rule], internal=True)
                (rows, discounts, gross), _ = self.resolve(plans, components, [rule])
                self.assertEqual((rows[0]["amount"], discounts[0]["rule_code"], gross),
                                 (900, "LEGACY", 1000))

    def test_internal_hold_does_not_block_undiscounted_tuition(self):
        plans = [{"name": "FS-1"}]
        components = [{"fees_category": "Semester Tuition Fee", "amount": 1000}]
        rule = dict(code="OTHER", status="Active", discount_percentage=10, precedence=1)
        for scope in ({"student": "OTHER-STUDENT"}, {"program": "EAP"},
                      {"fee_category": "Books"}, {"status": "Retired"}):
            with self.subTest(scope=scope):
                result, _ = self.resolve(plans, components, [dict(rule, **scope)],
                                         internal=True)
                self.assertEqual(result, (components, [], 1000))


if __name__ == "__main__":
    unittest.main()

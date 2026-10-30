"""Native tuition billing must refuse ambiguous or malformed Fee Structures.

Executes the real shared resolver used by full-semester Fees and installments.
Isolated framework doubles keep these tests non-mutating and deterministic.
"""
import ast
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
    def resolve(self, plans, components):
        calls = []
        def db_get_all(doctype, **kwargs):
            calls.append((doctype, kwargs))
            if doctype == "Fee Structure":
                return plans
            if doctype == "Fee Component":
                return [types.SimpleNamespace(**row) for row in components]
            if doctype == "TH Discount Rule":
                return []
            raise AssertionError(doctype)

        # Verify the shared resolver actually validates the native rows
        # before attempting discounts; reject duplicate, missing or invalid.
        def validate_component_rows(rows):
            seen = set()
            for row in rows:
                category, amount = row["category"], row["amount"]
                if not category or category in seen or float(amount) <= 0:
                    raise ValueError("bad component")
                seen.add(category)

        rules = types.SimpleNamespace(
            validate_component_rows=validate_component_rows,
            resolve_charge_discount=lambda *args, **kwargs: None)
        academic = types.ModuleType("toefl_house.academic")
        academic.rules = rules
        package = types.ModuleType("toefl_house")
        package.__path__ = []
        frappe = types.SimpleNamespace(
            db=types.SimpleNamespace(get_all=db_get_all),
            ValidationError=ValueError)
        context = {"frappe": frappe, "FEE_STRUCTURE": "Fee Structure",
                   "_discount_family_for_native_program": lambda program: "GEN-ENG"}
        with patch.dict(sys.modules, {
            "toefl_house": package, "toefl_house.academic": academic}):
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


if __name__ == "__main__":
    unittest.main()

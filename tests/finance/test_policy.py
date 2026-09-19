"""Pure local unit checks for the thin finance-slice policy surface.

Not native Frappe qualification; hosted acceptance lives in
tools/placement/native_checks.py on the branch-restricted runner.
"""
import ast
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import can_read, validate_finance_dates

ROOT = Path(__file__).resolve().parents[2]
FINANCE = ROOT / "apps/toefl_house/toefl_house/finance/__init__.py"
HOOKS = ROOT / "apps/toefl_house/toefl_house/hooks.py"
SECURITY = ROOT / "apps/toefl_house/toefl_house/security.py"
PERMISSIONS = ROOT / "apps/toefl_house/toefl_house/permissions.py"


class FinanceDateTests(unittest.TestCase):
    def test_valid_window_normalized(self):
        self.assertEqual(validate_finance_dates("2026-09-01", "2026-09-30"),
                         ("2026-09-01", "2026-09-30"))

    def test_same_day_window_allowed(self):
        self.assertEqual(validate_finance_dates("2026-09-01", "2026-09-01"),
                         ("2026-09-01", "2026-09-01"))

    def test_inverted_window_denied(self):
        with self.assertRaises(ValueError):
            validate_finance_dates("2026-09-30", "2026-09-01")

    def test_malformed_values_denied(self):
        for posting, due in (("09/01/2026", "2026-09-30"), ("2026-09-01", "30-09-2026"),
                             (None, "2026-09-30"), ("2026-09-01", 7), ("2026-13-01", "2026-13-02")):
            with self.assertRaises(ValueError):
                validate_finance_dates(posting, due)


class FinanceAuditorReadTests(unittest.TestCase):
    def test_finance_auditor_reads_receipts_only(self):
        for kind in ("audit", "operation"):
            self.assertTrue(can_read(kind, {"Finance Auditor"}, "fin-auditor@example.test",
                                     "someone-else@example.test"))

    def test_finance_auditor_does_not_read_domain_records(self):
        for kind in ("case", "attempt", "decision", "admission_decision", "item"):
            self.assertFalse(can_read(kind, {"Finance Auditor"}, "fin-auditor@example.test",
                                      "someone-else@example.test"))

    def test_finance_officer_gets_no_receipt_read(self):
        for kind in ("audit", "operation"):
            self.assertFalse(can_read(kind, {"Finance Officer"}, "fin-officer@example.test",
                                      "someone-else@example.test"))


class FinanceContainmentWiringTests(unittest.TestCase):
    """The deny-by-default wiring must exist statically (hosted proof runs it)."""

    def test_hooks_register_finance_guards(self):
        tree = ast.parse(HOOKS.read_text(encoding="utf-8"))
        source = HOOKS.read_text(encoding="utf-8")
        self.assertIsInstance(tree, ast.Module)
        self.assertIn('"toefl_house.finance.guard_fees"', source)
        self.assertIn('"toefl_house.finance.guard_sales_invoice"', source)

    def test_finance_guards_never_allow_without_command(self):
        source = FINANCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        guards = {n.name: n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name.startswith("guard_")}
        self.assertEqual(sorted(guards), ["guard_fees", "guard_sales_invoice"])
        for name, node in guards.items():
            calls = [c for c in ast.walk(node) if isinstance(c, ast.Call)]
            names = {c.func.id for c in calls if isinstance(c.func, ast.Name)}
            self.assertIn("finance_command_active", names, name)
            self.assertTrue(any(isinstance(n, ast.Raise) for n in ast.walk(node)), name)

    def test_finance_kinds_map_to_finance_officer(self):
        source = SECURITY.read_text(encoding="utf-8")
        self.assertIn('"issue_tuition_fees": "Finance Officer"', source)
        self.assertIn('"issue_placement_fee": "Finance Officer"', source)
        self.assertIn('"issue_tuition_fees": "Fees"', source)
        self.assertIn('"issue_placement_fee": "Sales Invoice"', source)

    def test_finance_auditor_query_branch(self):
        source = PERMISSIONS.read_text(encoding="utf-8")
        self.assertIn('"Finance Auditor"', source)

    def test_module_never_hardcodes_chargeability(self):
        # Owner policy: free-vs-charged is configuration, never a code constant.
        source = FINANCE.read_text(encoding="utf-8")
        self.assertIn("Placement fee is not configured as chargeable", source)
        # The rate is only ever read from the configured native price list.
        self.assertEqual(source.count("price_list_rate"), 1)
        self.assertNotIn("4000", source)

    def test_issue_commands_lock_the_billable_row_before_the_duplicate_check(self):
        """Two concurrent distinct keys must not both pass the exists() check."""
        source = FINANCE.read_text(encoding="utf-8")
        tree = ast.parse(source)

        def body(name):
            fn = next(n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef) and n.name == name)
            return ast.get_source_segment(source, fn) or ""

        tuition = body("issue_tuition_fees")
        self.assertIn("for update", tuition)
        self.assertIn('"fee_structure": fs_name', tuition,
                      "duplicate tuition is per enrollment and fee plan, not enrollment alone")
        self.assertLess(tuition.index("for update"),
                        tuition.index("Tuition is already billed for this enrollment on this fee plan"),
                        "the enrollment must be locked before the duplicate-billing check")
        placement = body("issue_placement_fee")
        self.assertIn("for update", placement)
        self.assertLess(placement.index("for update"),
                        placement.index("Placement fee is already billed for this case"),
                        "the placement case must be locked before the duplicate-billing check")


if __name__ == "__main__":
    unittest.main()

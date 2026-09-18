"""OD-CP-1 net-billing math, and the lock that finance bills the NET amount.

Hosted runs (tools/placement/native_checks.py, checks odcp-discount-*) prove
the live-site arithmetic; this file pins the pure helper and the command
shape offline. The defect this guards (fee-handoff audit, 2026-09-18): the
pinned native Education Fees controller computes grand_total as the plain
sum of component amounts and never applies the child ``discount`` field
(education 93bc70757533, fees.py calculate_total), so a resolved discount
that is only recorded on the child row never reaches the receivable. The
command therefore bills ``amount = net`` and keeps the percentage as a
descriptive record.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/toefl_house"))
sys.path.insert(0, str(ROOT / "apps/toefl_house/toefl_house/academic"))

import rules  # noqa: E402  (pure module, no frappe)

FINANCE = ROOT / "apps/toefl_house/toefl_house/finance/__init__.py"


class ApplyChargeDiscountTests(unittest.TestCase):
    def test_single_discount_per_line(self):
        self.assertEqual(rules.apply_charge_discount(25000, 10), 22500.0)
        self.assertEqual(rules.apply_charge_discount(5000, 30), 3500.0)
        self.assertEqual(rules.apply_charge_discount(25000, 50), 12500.0)

    def test_rounding_is_two_decimal_net(self):
        self.assertEqual(rules.apply_charge_discount(99.99, 33.33), 66.66)
        self.assertEqual(rules.apply_charge_discount(0.01, 50), 0.01)
        self.assertEqual(rules.apply_charge_discount(10, 33.333), 6.67)

    def test_full_waiver_boundary_is_zero_not_negative(self):
        self.assertEqual(rules.apply_charge_discount(12345.67, 100), 0.0)

    def test_string_percentages_are_normalized(self):
        self.assertEqual(rules.apply_charge_discount(25000, "10"), 22500.0)

    def test_rejects_bad_inputs(self):
        for bad_pct in (0, 0.0, -5, 101, True, None, "ten", ""):
            with self.assertRaises(ValueError, msg=repr(bad_pct)):
                rules.apply_charge_discount(100, bad_pct)
        with self.assertRaises(ValueError):
            rules.apply_charge_discount(-1, 10)

    def test_stacking_is_unrepresentable(self):
        """One percentage in, one application out: the helper accepts no
        collection of percentages, so stacked discounts cannot be
        introduced silently."""
        for stacked in ([10, 20], (10, 20), {"pct": 10}):
            with self.assertRaises(ValueError, msg=repr(stacked)):
                rules.apply_charge_discount(100, stacked)


class FinanceCommandShapeTests(unittest.TestCase):
    def test_issue_tuition_bills_the_net_amount(self):
        src = FINANCE.read_text(encoding="utf-8")
        self.assertIn("rules.apply_charge_discount(gross, winner[\"discount_percentage\"])", src)
        self.assertIn('comp_row["amount"] = net', src)
        self.assertIn('comp_row["discount"] = winner["discount_percentage"]', src)
        # receipt keeps gross/net so the reduction is auditable
        self.assertIn('"gross_amount": gross', src)
        self.assertIn('"net_amount": net', src)
        self.assertIn('result["discount_amount"]', src)

    def test_no_native_fee_discount_field_claim(self):
        """The helper docstring must keep recording WHY amount carries the
        discount: native grand_total ignores the child discount field."""
        helper = rules.apply_charge_discount.__doc__ or ""
        self.assertIn("plain sum of component amounts", helper)
        self.assertIn("discount", helper)


if __name__ == "__main__":
    unittest.main()

"""OD-CP-1 net-billing math, and the lock that finance bills the NET amount.

Hosted runs (tools/native/native_checks.py, checks odcp-discount-*) prove
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
        for bad_pct in (0, 0.0, -5, 101, True, None, "ten", "",
                        "nan", "inf", "-inf", "1e999",
                        float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError, msg=repr(bad_pct)):
                rules.apply_charge_discount(100, bad_pct)
        with self.assertRaises(ValueError):
            rules.apply_charge_discount(-1, 10)
        for gross in (None, True, "nonnumeric", "nan", "inf", "1e999",
                      float("nan"), float("inf"), float("-inf")):
            with self.subTest(gross=repr(gross)):
                with self.assertRaisesRegex(ValueError, "finite number"):
                    rules.apply_charge_discount(gross, 10)

    def test_stacking_is_unrepresentable(self):
        """One percentage in, one application out: the helper accepts no
        collection of percentages, so stacked discounts cannot be
        introduced silently."""
        for stacked in ([10, 20], (10, 20), {"pct": 10}):
            with self.assertRaises(ValueError, msg=repr(stacked)):
                rules.apply_charge_discount(100, stacked)


class ResolverRowShapeTests(unittest.TestCase):
    def test_rows_without_status_are_not_eligible(self):
        """The resolver's second guard needs the row's own status: a fetched
        row missing the key is treated as non-Active. This contract is why
        issue_tuition_fees must fetch "status" in its field list (the first
        hosted odcp run found rows fetched without it — every rule was
        silently skipped and no discount ever reached the receivable)."""
        rule = {"code": "X-1", "title": "Ten", "discount_percentage": 10.0,
                "precedence": 5}  # no "status" key
        self.assertIsNone(rules.resolve_charge_discount([rule], fee_category=None))
        self.assertEqual(
            rules.resolve_charge_discount([dict(rule, status="Active")])["rule_code"],
            "X-1")


    def test_active_malformed_rule_refuses_instead_of_corrupting_bill(self):
        for percent in (None, 0, "nan", "inf", float("nan"), float("inf")):
            active = {"code": "BAD", "status": "Active",
                      "discount_percentage": percent, "precedence": 10}
            with self.subTest(percent=repr(percent)):
                with self.assertRaises(ValueError):
                    rules.resolve_charge_discount([active])
        # A malformed rule for another program must not block unrelated Fees.
        unrelated = {"code": "BAD", "status": "Active",
                     "discount_percentage": float("nan"), "program": "EAP"}
        self.assertIsNone(rules.resolve_charge_discount([unrelated], program="GE"))

class StudentEligibilityTests(unittest.TestCase):
    def test_bounded_ordinary_discount_and_documented_full_waiver(self):
        self.assertEqual(rules.validate_discount_award(50), 50)
        with self.assertRaisesRegex(ValueError, "cannot exceed 50%"):
            rules.validate_discount_award(75)
        with self.assertRaises(ValueError):
            rules.validate_discount_award(100)
        with self.assertRaises(ValueError):
            rules.validate_discount_award(100, "STU-1")
        self.assertEqual(rules.validate_discount_award(
            100, "STU-1", "Verified staff dependent"), 100)

    def test_waiver_never_leaks_to_other_students_or_programs(self):
        rule = dict(code="FULL", status="Active", discount_percentage=100,
                    precedence=10, student="STU-1", program="GE")
        self.assertIsNone(rules.resolve_charge_discount([rule], program="GE", student="STU-2"))
        self.assertIsNone(rules.resolve_charge_discount([rule], program="EAP", student="STU-1"))
        self.assertIsNone(rules.resolve_charge_discount([rule], student="STU-1"))
        self.assertEqual(rules.resolve_charge_discount(
            [rule], program="GE", student="STU-1")["rule_code"], "FULL")

    def test_legacy_global_waiver_and_75_percent_cannot_bill(self):
        for pct in (75, 100):
            rule = dict(code="OLD", status="Active", discount_percentage=pct,
                        precedence=10)
            self.assertIsNone(rules.resolve_charge_discount([rule], student="STU-1"))

    def test_unresolved_family_never_matches_family_scoped_discount(self):
        rule = dict(code="GEN", status="Active", discount_percentage=10,
                    precedence=10, program="GEN")
        self.assertIsNone(rules.resolve_charge_discount([rule]))
        self.assertIsNotNone(rules.resolve_charge_discount([rule], program="GEN"))


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

    def test_rule_fetch_carries_the_status_field(self):
        """Regression lock (hosted run ecb227b found the defect offline-passing):
        the get_all for TH Discount Rule must select "status" alongside the
        resolver-consumed fields, or no rule can ever be eligible."""
        src = FINANCE.read_text(encoding="utf-8")
        fetch = src[src.index('frappe.db.get_all("TH Discount Rule"'):]
        fields = fetch[fetch.index("fields=["):fetch.index("]")]
        self.assertIn('"status"', fields)

    def test_finance_resolves_level_family_and_eligible_student(self):
        src = FINANCE.read_text(encoding="utf-8")
        self.assertIn('filters={"native_program": native_program}', src)
        self.assertIn("_discount_family_for_native_program(pe.program)", src)
        self.assertIn('program=discount_family, student=pe.student', src)
        self.assertIn('"student", "status"', src)

    def test_no_native_fee_discount_field_claim(self):
        """The helper docstring must keep recording WHY amount carries the
        discount: native grand_total ignores the child discount field."""
        helper = rules.apply_charge_discount.__doc__ or ""
        self.assertIn("plain sum of component amounts", helper)
        self.assertIn("discount", helper)


if __name__ == "__main__":
    unittest.main()

"""Worked-month payroll remains distinct from next-month cash payment."""
import importlib
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"


def module_under_test():
    names = ("toefl_house", "toefl_house.finance",
             "toefl_house.finance.shamsi",
             "toefl_house.finance.period_reporting",
             "toefl_house.teaching",
             "toefl_house.teaching.payroll_periods")
    original = {name: sys.modules.get(name) for name in names}
    for name, folder in (("toefl_house", APP),
                         ("toefl_house.finance", APP / "finance"),
                         ("toefl_house.teaching", APP / "teaching")):
        m = types.ModuleType(name)
        m.__path__ = [str(folder)]
        sys.modules[name] = m
    try:
        return importlib.import_module("toefl_house.teaching.payroll_periods")
    finally:
        for name, old in original.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


class WorkedShamsiMonthPayroll(unittest.TestCase):
    def setUp(self):
        self.p = module_under_test()
        self.slips = [
            {"name": "SAL-1405-07", "employee": "TEACHER-1",
             "docstatus": 1, "start_date": "2026-09-23",
             "end_date": "2026-10-22", "net_pay": 1000},
        ]

    def test_october_worked_month_paid_in_november_is_not_november_wages(self):
        payments = [{
            "name": "VOUCHER-1", "salary_slip": "SAL-1405-07",
            "docstatus": 1, "posting_date": "2026-11-10",
            "paid_amount": 600,
        }]
        early = self.p.worked_month_payroll(self.slips, payments, "1405-07", "2026-11-05")
        self.assertEqual(early["earned_net"], Decimal("1000.00"))
        self.assertEqual(early["paid"], Decimal("0.00"))
        self.assertEqual(early["unpaid_after_priority"], Decimal("0.00"))
        later = self.p.worked_month_payroll(self.slips, payments, "1405-07", "2026-11-11")
        self.assertEqual(later["priority_payment_by"], "2026-11-06")
        self.assertEqual(later["following_month_end"], "2026-11-21")
        self.assertEqual(later["earned_net"], Decimal("1000.00"))
        self.assertEqual(later["paid"], Decimal("600.00"))
        self.assertEqual(later["unpaid"], Decimal("400.00"))
        self.assertEqual(later["unpaid_after_priority"], Decimal("400.00"))
        self.assertEqual(later["salary_slips"][0]["paid_in_months"], {
            "1405-08": Decimal("600.00"),
        })
        overdue = self.p.worked_month_payroll(self.slips, payments, "1405-07", "2026-11-22")
        self.assertEqual(overdue["pending_after_following_month"], Decimal("400.00"))

    def test_submitted_slip_is_not_cash_payment(self):
        report = self.p.worked_month_payroll(self.slips, [], "1405-07", "2026-11-15")
        self.assertEqual(report["earned_net"], Decimal("1000.00"))
        self.assertEqual(report["paid"], Decimal("0.00"))
        self.assertFalse(report["payment_authorization_assumed"])

    def test_partial_double_or_unlinked_disbursements_are_refused(self):
        base = {"name": "PAY-1", "salary_slip": "SAL-1405-07",
                "docstatus": 1, "posting_date": "2026-11-10",
                "paid_amount": 500}
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.p.worked_month_payroll(self.slips, [base, base], "1405-07", "2026-11-15")
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.p.worked_month_payroll(self.slips, [
                dict(base, paid_amount=1001)], "1405-07", "2026-11-15")
        with self.assertRaisesRegex(ValueError, "missing submitted"):
            self.p.worked_month_payroll(self.slips, [
                dict(base, salary_slip="WRONG-SLIP")], "1405-07", "2026-11-15")

    def test_gregorian_salary_slip_overlap_cannot_mislabel_shamsi_pay(self):
        wrong = dict(self.slips[0], start_date="2026-10-01", end_date="2026-10-31")
        with self.assertRaisesRegex(ValueError, "overlaps"):
            self.p.worked_month_payroll([wrong], [], "1405-07", "2026-11-15")


if __name__ == "__main__":
    unittest.main()

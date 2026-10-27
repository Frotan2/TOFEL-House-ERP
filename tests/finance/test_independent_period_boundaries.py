"""Independent regression tests for native receivable views and Afghan months.

PURE source tests: do not require Frappe or touch customer data.
"""
from datetime import timedelta
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
FINANCE = ROOT / "apps" / "toefl_house" / "toefl_house" / "finance"


def load_pure_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Frappe-aware finance/__init__.py must not run during pure source tests.
_shamsi = load_pure_module("toefl_house.finance.shamsi", FINANCE / "shamsi.py")
_package = types.ModuleType("toefl_house")
_package.__path__ = []
_finance = types.ModuleType("toefl_house.finance")
_finance.__path__ = []
with patch.dict(sys.modules, {
    "toefl_house": _package,
    "toefl_house.finance": _finance,
    "toefl_house.finance.shamsi": _shamsi,
}):
    _reporting = load_pure_module(
        "independent_period_reporting_under_test", FINANCE / "period_reporting.py"
    )

add_months = _shamsi.add_months
days_in_month = _shamsi.days_in_month
fiscal_year_bounds = _shamsi.fiscal_year_bounds
following_month = _shamsi.following_month
gregorian_to_shamsi = _shamsi.gregorian_to_shamsi
month_bounds = _shamsi.month_bounds
month_key = _shamsi.month_key
monthly_due_dates = _shamsi.monthly_due_dates
parse_shamsi_month = _shamsi.parse_shamsi_month
shamsi_to_gregorian = _shamsi.shamsi_to_gregorian
solar_month_label = _shamsi.solar_month_label
amount = _reporting.amount
invoice_balances = _reporting.invoice_balances
solar_month_receivables = _reporting.solar_month_receivables
suggest_oldest_debt_allocation = _reporting.suggest_oldest_debt_allocation


def fee(name, posting, due, total):
    return dict(name=name, posting_date=str(posting), due_date=str(due),
                grand_total=total, docstatus=1)


def allocation(name, invoice, posting, total):
    return dict(name=name, reference_name=invoice, posting_date=str(posting),
                allocated_amount=total, docstatus=1)


class SolarHijriBoundaryTests(unittest.TestCase):
    def test_all_twelve_months_roll_into_next_year(self):
        self.assertEqual(following_month("1404-08"), "1404-09")
        self.assertEqual(following_month("1404-09"), "1404-10")
        self.assertEqual(following_month("1404-10"), "1404-11")
        self.assertEqual(following_month("1404-11"), "1404-12")
        self.assertEqual(following_month("1404-12"), "1405-01")
        self.assertEqual(add_months(1404, 12, 14), (1406, 2))

    def test_month_bounds_are_contiguous_across_year(self):
        for period in ("1404-08", "1404-09", "1404-10",
                       "1404-11", "1404-12", "1405-01"):
            start, end = month_bounds(period)
            self.assertEqual(month_key(start), period)
            self.assertEqual(month_key(end), period)
            self.assertEqual(month_key(end + timedelta(days=1)), following_month(period))
            self.assertEqual((end - start).days + 1,
                             days_in_month(*parse_shamsi_month(period)))

    def test_leap_and_nonleap_hoot(self):
        self.assertEqual(days_in_month(1403, 12), 30)
        self.assertEqual(days_in_month(1404, 12), 29)
        self.assertEqual(shamsi_to_gregorian(1403, 12, 30) + timedelta(days=1),
                         shamsi_to_gregorian(1404, 1, 1))
        with self.assertRaises(ValueError):
            shamsi_to_gregorian(1404, 12, 30)

    def test_month_due_dates_survive_year_rollover(self):
        dates = monthly_due_dates("1404-11", 4, 0)
        self.assertEqual([month_key(day) for day in dates],
                         ["1404-11", "1404-12", "1405-01", "1405-02"])
        self.assertTrue(all(gregorian_to_shamsi(day)[2] == 1 for day in dates))

    def test_fiscal_year_has_contiguous_transition(self):
        start, end = fiscal_year_bounds(1404)
        next_start, _ = fiscal_year_bounds(1405)
        self.assertEqual(start, shamsi_to_gregorian(1404, 1, 1))
        self.assertEqual(end + timedelta(days=1), next_start)

    def test_period_validation_rejects_bad_input(self):
        for invalid in ("1404-00", "1404-13", "1404-8", "۱۴۰۴-۰۸", "1404/08", ""):
            with self.subTest(period=invalid), self.assertRaises(ValueError):
                parse_shamsi_month(invalid)

    def test_afghan_labels(self):
        self.assertEqual(solar_month_label("1404-08"), "عقرب 1404")
        self.assertEqual(solar_month_label("1404-09"), "قوس 1404")
        self.assertEqual(solar_month_label("1404-12"), "حوت 1404")
        self.assertEqual(solar_month_label("1405-01"), "حمل 1405")


class NativeReceivableViewTests(unittest.TestCase):
    def setUp(self):
        self.period = "1404-08"
        self.start, self.end = month_bounds(self.period)
        self.invoices = [
            fee("FEE-A", self.start, self.start, "2500.00"),
            fee("FEE-B", self.start, self.end, "2500.00"),
        ]

    def test_oldest_due_first_independent_of_input_order(self):
        proposal = suggest_oldest_debt_allocation([
            {"name": "FEE-B", "due_date": str(self.end), "outstanding_amount": "2500"},
            {"name": "FEE-A", "due_date": str(self.start), "outstanding_amount": "2500"},
        ], "3000")
        self.assertEqual(proposal["allocations"], [
            {"fees": "FEE-A", "allocated_amount": Decimal("2500.00")},
            {"fees": "FEE-B", "allocated_amount": Decimal("500.00")},
        ])
        self.assertEqual(proposal["unapplied_proposed_advance"], Decimal("0.00"))

    def test_unapplied_amount_is_proposal_not_cash_post(self):
        p = suggest_oldest_debt_allocation([
            {"name": "FEE-A", "due_date": str(self.start), "outstanding_amount": "1000"}
        ], "1500")
        self.assertEqual(p["unapplied_proposed_advance"], Decimal("500.00"))

    def test_native_month_reconciles_and_end_day_is_not_overdue(self):
        rows = [allocation("PE-1:REF-1", "FEE-A", self.start, "1000")]
        report = solar_month_receivables(self.invoices, rows, self.period)
        self.assertEqual(report["posted_in_month"], Decimal("5000.00"))
        self.assertEqual(report["collections_in_month"], Decimal("1000.00"))
        self.assertEqual(report["closing_outstanding"], Decimal("4000.00"))
        self.assertEqual(report["receivables_reconciliation_difference"], Decimal("0.00"))
        self.assertEqual(report["due_on_month_end_outstanding"], Decimal("2500.00"))
        self.assertEqual(report["overdue_as_of_month_end"], Decimal("1500.00"))
        self.assertFalse(report["unallocated_advances_included"])

    def test_duplicate_payment_identity_fails_closed(self):
        rows = [
            allocation("PE-1:REF-1", "FEE-A", self.start, "100"),
            allocation("PE-1:REF-1", "FEE-A", self.start, "100"),
        ]
        with self.assertRaises(ValueError):
            invoice_balances(self.invoices, rows, self.end)

    def test_payment_before_invoice_rejected_without_fake_receivable(self):
        late_invoice = [fee("FEE-LATE", self.start + timedelta(days=2),
                            self.end, "2500")]
        rows = [allocation("ADV-1", "FEE-LATE", self.start, "100")]
        with self.assertRaises(ValueError):
            invoice_balances(late_invoice, rows, self.end)

    def test_overallocation_rejected(self):
        rows = [allocation("PE-1", "FEE-A", self.start, "2600")]
        with self.assertRaises(ValueError):
            invoice_balances(self.invoices, rows, self.end)

    def test_nonfinite_money_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity", "not-money"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                amount(value)

    def test_cancelled_native_receipt_is_excluded(self):
        receipt = allocation("PE-CANCELLED", "FEE-A", self.start, "2500")
        receipt["docstatus"] = 2
        rows = invoice_balances(self.invoices, [receipt], self.end)
        self.assertEqual(rows["FEE-A"]["outstanding"], Decimal("2500.00"))


if __name__ == "__main__":
    unittest.main()

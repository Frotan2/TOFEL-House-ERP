"""Cross-Shamsi-month receivables and allocation proposal acceptance."""
import unittest
from decimal import Decimal
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"


def load_under_test():
    import sys
    import types
    package = types.ModuleType("toefl_house")
    package.__path__ = [str(APP)]
    finance = types.ModuleType("toefl_house.finance")
    finance.__path__ = [str(APP / "finance")]
    previous = {name: sys.modules.get(name) for name in
                ("toefl_house", "toefl_house.finance",
                 "toefl_house.finance.shamsi", "toefl_house.finance.period_reporting")}
    for key, module in (("toefl_house", package), ("toefl_house.finance", finance)):
        sys.modules[key] = module
    try:
        import toefl_house.finance.period_reporting as reporting
        return reporting
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


class CrossMonthReceivables(unittest.TestCase):
    def setUp(self):
        self.r = load_under_test()
        # Illustrates two Shamsi month claims for a fixed semester, all
        # recorded on the same native Education Program Enrollment.
        self.fees = [
            {"name":"F-MIZAN","docstatus":1,
             "posting_date":"2026-09-23","due_date":"2026-09-23",
             "grand_total":1000},
            {"name":"F-AQRAB","docstatus":1,
             "posting_date":"2026-09-23","due_date":"2026-10-23",
             "grand_total":1000},
        ]
        self.allocations = [
            {"name":"PER-1","reference_name":"F-MIZAN","docstatus":1,
             "posting_date":"2026-09-25","allocated_amount":600},
            {"name":"PER-2","reference_name":"F-MIZAN","docstatus":1,
             "posting_date":"2026-10-25","allocated_amount":400},
            {"name":"PER-3","reference_name":"F-AQRAB","docstatus":1,
             "posting_date":"2026-10-25","allocated_amount":800},
        ]

    def test_earlier_month_debt_carries_without_double_counting_receipts(self):
        p=self.r.solar_month_receivables(self.fees,self.allocations,"1405-07")
        self.assertEqual(p["due_in_month"],Decimal("1000.00"))
        self.assertEqual(p["collections_in_month"],Decimal("600.00"))
        self.assertEqual(p["overdue_as_of_month_end"],Decimal("400.00"))
        self.assertEqual(p["future_due_outstanding"],Decimal("1000.00"))
        self.assertEqual(p["total_outstanding"],Decimal("1400.00"))
        self.assertFalse(p["unallocated_advances_included"])
        a=self.r.solar_month_receivables(self.fees,self.allocations,"1405-08")
        self.assertEqual(a["opening_outstanding"],Decimal("1400.00"))
        self.assertEqual(a["closing_outstanding"],Decimal("200.00"))
        self.assertEqual(a["receivables_reconciliation_difference"],Decimal("0.00"))
        self.assertEqual(a["posted_in_month"],Decimal("0.00"))
        self.assertEqual(a["due_in_month"],Decimal("1000.00"))
        self.assertEqual(a["collections_in_month"],Decimal("1200.00"))
        self.assertEqual(a["overdue_as_of_month_end"],Decimal("200.00"))
        self.assertEqual(a["future_due_outstanding"],Decimal("0.00"))
        self.assertEqual(a["total_outstanding"],Decimal("200.00"))

    def test_oldest_open_fee_receives_allocation_first(self):
        suggestion=self.r.suggest_oldest_debt_allocation([
            {"name":"F-AQRAB","due_date":"2026-10-23","outstanding_amount":1000},
            {"name":"F-MIZAN","due_date":"2026-09-23","outstanding_amount":400},
        ],1200)
        self.assertEqual(suggestion["allocations"],[
            {"fees":"F-MIZAN","allocated_amount":Decimal("400.00")},
            {"fees":"F-AQRAB","allocated_amount":Decimal("800.00")}])
        self.assertEqual(suggestion["unapplied_proposed_advance"],Decimal("0.00"))

    def test_month_movement_includes_old_debt_new_invoices_and_partial_receipts(self):
        bills = [self.fees[0], dict(self.fees[1], posting_date="2026-10-23")]
        report = self.r.solar_month_receivables(bills, self.allocations, "1405-08")
        self.assertEqual(report["opening_outstanding"], Decimal("400.00"))
        self.assertEqual(report["posted_in_month"], Decimal("1000.00"))
        self.assertEqual(report["collections_in_month"], Decimal("1200.00"))
        self.assertEqual(report["closing_outstanding"], Decimal("200.00"))
        self.assertEqual(report["receivables_reconciliation_difference"], Decimal("0.00"))

    def test_due_on_month_end_is_outstanding_but_not_yet_overdue(self):
        bill = dict(self.fees[0], due_date="2026-10-22")
        report = self.r.solar_month_receivables([bill], [], "1405-07")
        self.assertEqual(report["total_outstanding"], Decimal("1000.00"))
        self.assertEqual(report["overdue_as_of_month_end"], Decimal("0.00"))
        self.assertEqual(report["due_on_month_end_outstanding"], Decimal("1000.00"))
        self.assertEqual(report["future_due_outstanding"], Decimal("0.00"))

    def test_streamed_rows_keep_the_same_opening_and_closing_balances(self):
        streamed = self.r.solar_month_receivables(iter(self.fees), iter(self.allocations), "1405-08")
        listed = self.r.solar_month_receivables(self.fees, self.allocations, "1405-08")
        self.assertEqual(streamed, listed)

    def test_advance_is_not_disguised_as_allocation_before_invoice_posting(self):
        receipt = dict(self.allocations[0], posting_date="2026-09-22")
        with self.assertRaisesRegex(ValueError, "native advance separately"):
            self.r.solar_month_receivables(self.fees, [receipt], "1405-07")

    def test_unrepresentable_currency_has_a_validation_error(self):
        with self.assertRaisesRegex(ValueError, "supported range"):
            self.r.amount("1e999999")

    def test_excess_never_becomes_a_ghost_receipt(self):
        suggestion=self.r.suggest_oldest_debt_allocation([
            {"name":"F-MIZAN","due_date":"2026-09-23","outstanding_amount":400}],500)
        self.assertEqual(suggestion["unapplied_proposed_advance"],Decimal("100.00"))

    def test_duplicate_or_unapproved_allocations_fail_closed(self):
        extra=dict(self.allocations[0])
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            self.r.invoice_balances(self.fees,[extra,extra],"2026-10-25")
        with self.assertRaisesRegex(ValueError,"Over-allocation"):
            self.r.invoice_balances(self.fees,self.allocations+[
                {"name":"PER-4","reference_name":"F-MIZAN","docstatus":1,
                 "posting_date":"2026-10-25","allocated_amount":1}
            ],"2026-10-25")
        with self.assertRaisesRegex(ValueError,"unknown"):
            self.r.invoice_balances(self.fees,[{
                "name":"PER-5","reference_name":"OTHER-STUDENT",
                "docstatus":1,"posting_date":"2026-10-25",
                "allocated_amount":1
            }],"2026-10-25")
        with self.assertRaises(ValueError):
            self.r.suggest_oldest_debt_allocation([], -10)

    def test_cancelled_payment_is_not_money_and_late_refund_is_separate(self):
        receipt=dict(self.allocations[0],docstatus=2)
        statement=self.r.solar_month_receivables(
            [self.fees[0]],[receipt],"1405-07")
        self.assertEqual(statement["collections_in_month"],Decimal("0.00"))
        self.assertEqual(statement["overdue_as_of_month_end"],Decimal("1000.00"))


if __name__ == "__main__":
    unittest.main()

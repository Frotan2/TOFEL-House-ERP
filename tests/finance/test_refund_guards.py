"""Refund and return integrity for native book commerce.

A credit note restocks books and creates a customer credit; a customer refund
pays that credit out in cash. Both move real value out of the institute, so
the shape rules are pinned here: cumulative restocking never exceeds what was
sold, cumulative credit never exceeds what was billed, and a refund always
settles a submitted credit note from a Cash/Bank account.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"


class _ValidationError(Exception):
    pass


def load_refunds():
    frappe = types.ModuleType("frappe")
    frappe.ValidationError = _ValidationError
    frappe.PermissionError = type("PermissionError", (Exception,), {})
    frappe.db = types.SimpleNamespace()
    sys.modules["frappe"] = frappe
    security = types.ModuleType("toefl_house.security")
    security.require_operational = lambda: None
    sys.modules["toefl_house.security"] = security
    spec = importlib.util.spec_from_file_location(
        "toefl_house.finance.refunds", APP / "finance" / "refunds.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["toefl_house.finance.refunds"] = module
    spec.loader.exec_module(module)
    return module


class ReturnQuantityTests(unittest.TestCase):
    def setUp(self):
        self.module = load_refunds()
        self.original = {"SYN-BOOK": 2.0}

    def test_full_return_of_a_sold_quantity_is_allowed(self):
        self.assertTrue(self.module.return_quantities_ok(
            self.original, [], {"SYN-BOOK": 2.0}))

    def test_partial_return_is_allowed(self):
        self.assertTrue(self.module.return_quantities_ok(
            self.original, [], {"SYN-BOOK": 1.0}))

    def test_returning_more_than_sold_is_refused(self):
        self.assertFalse(self.module.return_quantities_ok(
            self.original, [], {"SYN-BOOK": 3.0}))

    def test_returning_an_item_the_invoice_never_sold_is_refused(self):
        self.assertFalse(self.module.return_quantities_ok(
            self.original, [], {"SYN-OTHER": 1.0}))

    def test_a_second_full_return_after_the_first_is_refused(self):
        self.assertFalse(self.module.return_quantities_ok(
            self.original, [{"SYN-BOOK": 2.0}], {"SYN-BOOK": 2.0}))

    def test_a_split_return_totalling_the_sale_is_allowed(self):
        self.assertTrue(self.module.return_quantities_ok(
            self.original, [{"SYN-BOOK": 1.0}], {"SYN-BOOK": 1.0}))

    def test_zero_or_negative_return_quantity_is_refused(self):
        for qty in (0.0, -1.0):
            with self.subTest(qty=qty):
                self.assertFalse(self.module.return_quantities_ok(
                    self.original, [], {"SYN-BOOK": qty}))


class ReturnValueTests(unittest.TestCase):
    def setUp(self):
        self.module = load_refunds()

    def test_full_credit_is_allowed(self):
        self.assertTrue(self.module.return_value_ok(600.0, 0.0, -600.0))

    def test_credit_beyond_the_invoice_is_refused(self):
        self.assertFalse(self.module.return_value_ok(600.0, 0.0, -700.0))

    def test_second_credit_beyond_the_remaining_value_is_refused(self):
        self.assertFalse(self.module.return_value_ok(600.0, -600.0, -600.0))

    def test_zero_credit_is_refused(self):
        self.assertFalse(self.module.return_value_ok(600.0, 0.0, 0.0))


def credit_note(**overrides):
    row = {"docstatus": 1, "is_return": 1, "customer": "SYN-CUSTOMER",
           "company": "TOEFL House", "outstanding_amount": -600.0,
           "grand_total": -600.0}
    row.update(overrides)
    return row


def payment(**overrides):
    facts = {"payment_type": "Pay", "party_type": "Customer",
             "party": "SYN-CUSTOMER", "company": "TOEFL House",
             "paid_from": "Cash - TH", "paid_to": "Debtors - TH",
             "unallocated_amount": 0.0,
             "reference_rows": [{"reference_name": "SYN-CREDIT",
                                 "allocated_amount": -600.0}]}
    facts.update(overrides)
    return facts


CASH = {"Cash - TH", "Bank - TH"}


class RefundTests(unittest.TestCase):
    def setUp(self):
        self.module = load_refunds()
        self.notes = {"SYN-CREDIT": credit_note()}

    def judge(self, facts=None, notes=None, cash=CASH):
        return self.module.refund_allocation_ok(
            facts or payment(), self.notes if notes is None else notes,
            "Debtors - TH", cash)

    def test_refund_against_a_credit_note_is_allowed(self):
        self.assertTrue(self.judge())

    def test_partial_refund_is_allowed(self):
        self.assertTrue(self.judge(payment(
            reference_rows=[{"reference_name": "SYN-CREDIT",
                             "allocated_amount": -250.0}])))

    def test_refund_without_a_reference_is_refused(self):
        self.assertFalse(self.judge(payment(reference_rows=[])))

    def test_refund_against_a_live_sales_invoice_is_refused(self):
        self.assertFalse(self.judge(notes={"SYN-CREDIT": credit_note(is_return=0)}))

    def test_refund_against_a_cancelled_credit_note_is_refused(self):
        self.assertFalse(self.judge(notes={"SYN-CREDIT": credit_note(docstatus=2)}))

    def test_refund_for_another_customer_is_refused(self):
        self.assertFalse(self.judge(notes={"SYN-CREDIT": credit_note(customer="OTHER")}))

    def test_over_allocation_is_refused(self):
        self.assertFalse(self.judge(payment(
            reference_rows=[{"reference_name": "SYN-CREDIT",
                             "allocated_amount": -900.0}])))

    def test_refund_from_a_non_cash_account_is_refused(self):
        self.assertFalse(self.judge(payment(paid_from="Income - TH")))

    def test_refund_not_paid_to_the_receivable_is_refused(self):
        self.assertFalse(self.judge(payment(paid_to="Expense - TH")))

    def test_refund_with_an_unallocated_remainder_is_refused(self):
        self.assertFalse(self.judge(payment(unallocated_amount=-50.0)))

    def test_receipts_and_supplier_payments_are_untouched(self):
        self.assertTrue(self.judge(payment(payment_type="Receive")))
        self.assertTrue(self.judge(payment(party_type="Supplier")))

    # A submitted refund is cancelled or carries a post-submit field edit
    # through the same seam. By then the credit note it settled owes nothing,
    # so the "no more than it still owes" ceiling would read every legitimate
    # cancellation as an over-allocation and block the native reversal.
    def test_cancelling_a_settled_refund_is_allowed(self):
        self.assertTrue(self.module.refund_allocation_ok(
            payment(), {"SYN-CREDIT": credit_note(outstanding_amount=0.0)},
            "Debtors - TH", CASH, existing=True))

    def test_cancel_path_still_requires_the_same_submitted_credit_note(self):
        for notes in ({"SYN-CREDIT": credit_note(docstatus=2)},
                      {"SYN-CREDIT": credit_note(is_return=0)},
                      {"SYN-CREDIT": credit_note(customer="OTHER")},
                      {}):
            self.assertFalse(self.module.refund_allocation_ok(
                payment(), notes, "Debtors - TH", CASH, existing=True), notes)
        self.assertFalse(self.module.refund_allocation_ok(
            payment(reference_rows=[]), {}, "Debtors - TH", CASH, existing=True))

    def test_cancel_path_still_requires_cash_and_full_allocation(self):
        self.assertFalse(self.module.refund_allocation_ok(
            payment(paid_from="Income - TH"), {"SYN-CREDIT": credit_note()},
            "Debtors - TH", CASH, existing=True))
        self.assertFalse(self.module.refund_allocation_ok(
            payment(unallocated_amount=-5.0), {"SYN-CREDIT": credit_note()},
            "Debtors - TH", CASH, existing=True))


class WiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hooks = (APP / "hooks.py").read_text(encoding="utf-8")
        cls.finance = (APP / "finance" / "__init__.py").read_text(encoding="utf-8")

    def test_payment_entry_guard_runs_before_save_and_on_cancel(self):
        block = self.hooks.split('"Payment Entry": {')[1].split("}")[0]
        self.assertIn("toefl_house.finance.refunds.guard_payment_entry", block)
        for seam in ("validate", "before_cancel", "before_update_after_submit"):
            self.assertIn(seam, block)

    def test_book_return_guard_uses_the_cumulative_limits(self):
        self.assertIn("refunds.book_return_permitted", self.finance)

    def test_guard_relaxes_only_on_the_native_reversal_paths(self):
        source = (APP / "finance" / "refunds.py").read_text(encoding="utf-8")
        self.assertIn('existing=method in (', source)
        self.assertIn('"before_cancel", "before_update_after_submit"', source)
        # Creation and submission keep the strict ceiling.
        self.assertIn("if not existing and allocated - outstanding > TOLERANCE:",
                      source)


def tearDownModule():
    """Drop the stubs this module installed so later suites load fresh."""
    for name in ("frappe", "toefl_house", "toefl_house.policy", "toefl_house.api", "toefl_house.security", "toefl_house.finance", "toefl_house.finance.policies", "toefl_house.finance.cashier", "toefl_house.finance.taxes", "toefl_house.finance.refunds", "toefl_house.finance.installments",):
        sys.modules.pop(name, None)


if __name__ == "__main__":
    unittest.main()

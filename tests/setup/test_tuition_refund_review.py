"""Synthetic case-by-case tuition refund tests. No Frappe or money movement."""
import copy
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
sys.path.insert(0, str(APP))

from toefl_house.setup_presets.tuition_refund_review import (  # noqa: E402
    inspect_case_refund,
)


class TuitionRefundReviewTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "student": "STU-01", "company": "TH-CO", "fees": "FEES-01",
            "approved_amount": "150.00", "reason": "Manager-approved exceptional withdrawal",
            "approved_by": "general.manager@example.invalid",
            "paying_user": "finance.manager@example.invalid",
            "approval_status": "Approved",
        }
        self.collections = [
            {"payment_entry": "IN-01", "student": "STU-01", "company": "TH-CO",
             "fees": "FEES-01", "docstatus": 1, "amount": "400.00"},
            {"payment_entry": "IN-02", "student": "STU-01", "company": "TH-CO",
             "fees": "FEES-01", "docstatus": 1, "amount": "100.00"},
        ]
        self.refunds = [
            {"payment_entry": "OUT-01", "student": "STU-01", "company": "TH-CO",
             "fees": "FEES-01", "docstatus": 1, "amount": "200.00"},
        ]

    def check(self, case=None, collections=None, refunds=None, evidence=True):
        return inspect_case_refund(
            self.case if case is None else case,
            self.collections if collections is None else collections,
            self.refunds if refunds is None else refunds,
            native_evidence_complete=evidence)

    def test_approved_refund_below_actual_remaining_is_read_only(self):
        original = copy.deepcopy((self.case, self.collections, self.refunds))
        result = self.check()
        self.assertEqual(result["verified_collections_afn"], "500.00")
        self.assertEqual(result["prior_refunds_afn"], "200.00")
        self.assertEqual(result["approved_amount_afn"], "150.00")
        self.assertEqual(result["remaining_after_proposal_afn"], "150.00")
        self.assertFalse(result["payment_permitted"])
        self.assertEqual((self.case, self.collections, self.refunds), original)

    def test_no_unverified_native_evidence(self):
        with self.assertRaisesRegex(ValueError, "native ledger evidence"):
            self.check(evidence=False)

    def test_overpayment_and_repeat_refund_are_denied(self):
        claim = dict(self.case, approved_amount="300.01")
        with self.assertRaisesRegex(ValueError, "exceeds collected"):
            self.check(case=claim)
        twice = self.refunds + [{
            "payment_entry": "OUT-02", "student": "STU-01", "company": "TH-CO",
            "fees": "FEES-01", "docstatus": 1, "amount": "200.00"}]
        with self.assertRaisesRegex(ValueError, "exceeds collected"):
            self.check(refunds=twice)

    def test_draft_or_cancelled_cash_cannot_raise_paid_ceiling(self):
        extras = [
            {"payment_entry": "IN-DRAFT", "student": "STU-01",
             "company": "TH-CO", "fees": "FEES-01",
             "docstatus": 0, "amount": "9000.00"},
            {"payment_entry": "IN-VOID", "student": "STU-01",
             "company": "TH-CO", "fees": "FEES-01",
             "docstatus": 2, "amount": "9000.00"},
        ]
        result = self.check(collections=self.collections + extras)
        self.assertEqual(result["verified_collections_afn"], "500.00")
        no_cash = [dict(x, docstatus=2) for x in self.collections]
        with self.assertRaisesRegex(ValueError, "No verified"):
            self.check(collections=no_cash)

    def test_cancelled_refund_does_not_reduce_available_paid_amount(self):
        void_refund = [dict(self.refunds[0], docstatus=2)]
        result = self.check(refunds=void_refund)
        self.assertEqual(result["prior_refunds_afn"], "0")
        self.assertEqual(result["remaining_refundable_afn"], "500.00")

    def test_cross_company_student_and_invoice_refused(self):
        for key, new_value in (("student", "OTHER"), ("company", "OTHER"),
                               ("fees", "OTHER")):
            bad = dict(self.collections[0], **{key: new_value})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "unrelated"):
                self.check(collections=[bad] + self.collections[1:])

    def test_duplicate_receipts_cannot_double_credit_paid_amount(self):
        with self.assertRaisesRegex(ValueError, "Duplicate Collections"):
            self.check(collections=self.collections + self.collections)

    def test_no_self_approval_or_payment_without_approval(self):
        with self.assertRaisesRegex(ValueError, "own refund"):
            self.check(case=dict(self.case, paying_user=self.case["approved_by"]))
        with self.assertRaisesRegex(ValueError, "approved before Finance"):
            self.check(case=dict(self.case, approval_status="Requested"))

    def test_no_zero_negative_nan_or_fractional_cents(self):
        for amount in ("0", "-1", "NaN", "Infinity", "10.001", "1E+999", "1000000000000", True, None):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.check(case=dict(self.case, approved_amount=amount))

    def test_bad_receipt_shapes_are_rejected(self):
        for status in (-1, 3, True, "Submitted"):
            bad = dict(self.collections[0], docstatus=status)
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "docstatus"):
                self.check(collections=[bad] + self.collections[1:])
        bad = dict(self.collections[0], amount="Infinity")
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            self.check(collections=[bad] + self.collections[1:])

    def test_justification_required_and_no_auto_payment(self):
        for reason in ("", " ", None):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, "reason"):
                self.check(case=dict(self.case, reason=reason))
        self.assertEqual(self.check()["live_native_fees_refund_integration"],
                         "NOT_YET_VERIFIED")


if __name__ == "__main__":
    unittest.main()

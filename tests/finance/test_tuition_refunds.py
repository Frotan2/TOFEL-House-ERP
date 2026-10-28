"""Tuition refund workflow (Issue #115) — pure rules, no site, no money.

Tests load the pure modules by file path with stubbed parent packages,
following tests/finance/test_refund_guards.py. No Frappe, no database, no
native posting is attempted anywhere here: the pinned native Fees refund
mechanism does not exist, so pay_preflight must refuse at the posting
step with NativeRefundBlocked and leave the request Approved.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "apps" / "toefl_house" / "toefl_house"


def _load(name, path, parent):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_modules():
    # Stub packages point their __path__ at the real app directories, so
    # modules loaded later in the same process (operations, placement,
    # ...) still resolve real submodules through them. An empty __path__
    # would make those imports fail at load time — that broke the full
    # discovery run (3 spurious loader errors) until this was fixed.
    toefl = types.ModuleType("toefl_house")
    toefl.__path__ = [str(APP)]
    sys.modules["toefl_house"] = toefl
    setup = types.ModuleType("toefl_house.setup_presets")
    setup.__path__ = [str(APP / "setup_presets")]
    sys.modules["toefl_house.setup_presets"] = setup
    finance = types.ModuleType("toefl_house.finance")
    finance.__path__ = [str(APP / "finance")]
    sys.modules["toefl_house.finance"] = finance
    review = _load("toefl_house.setup_presets.tuition_refund_review",
                   APP / "setup_presets" / "tuition_refund_review.py", setup)
    refunds = _load("toefl_house.finance.tuition_refunds",
                    APP / "finance" / "tuition_refunds.py", finance)
    policy = _load("toefl_house.finance.student_payout_policy",
                   APP / "finance" / "student_payout_policy.py", finance)
    return review, refunds, policy


REVIEW, REFUNDS, POLICY = load_modules()
RefundError = REFUNDS.RefundError
NativeRefundBlocked = REFUNDS.NativeRefundBlocked


def collections(*amounts):
    return [{"payment_entry": f"IN-{i:02d}", "student": "STU-01",
             "company": "TH-CO", "fees": "FEES-01", "docstatus": 1,
             "amount": amount} for i, amount in enumerate(amounts, 1)]


def refunds(*rows):
    out = []
    for i, (amount, docstatus) in enumerate(rows, 1):
        out.append({"payment_entry": f"OUT-{i:02d}", "student": "STU-01",
                    "company": "TH-CO", "fees": "FEES-01",
                    "docstatus": docstatus, "amount": amount})
    return out


class TuitionRefundWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.cols = collections("400.00", "100.00")  # ceiling 500
        self.refs = refunds(("200.00", 1))  # prior refunds 200, available 300
        self.request = REFUNDS.create_request(
            student="STU-01", company="TH-CO", fees="FEES-01",
            requested_amount="150.00", reason="Exceptional withdrawal",
            evidence="Signed withdrawal letter", requested_by="fin.off@example.invalid",
            existing_requests=[], collections=self.cols, refunds=self.refs)

    def approve(self, request=None, approver="gm@example.invalid"):
        return REFUNDS.approve_request(
            request or self.request, approver=approver,
            approver_roles=["General Manager"])

    def test_request_and_approval_record_exact_amount_and_roles(self):
        self.assertEqual(self.request["status"], "Requested")
        self.assertEqual(self.request["requested_amount"], "150.00")
        approved = self.approve()
        self.assertEqual(approved["status"], "Approved")
        self.assertEqual(approved["approved_amount"], "150.00")
        self.assertEqual(approved["approved_by"], "gm@example.invalid")

    def test_exactly_at_ceiling_is_allowed_and_one_cent_above_is_refused(self):
        REFUNDS.create_request(
            student="STU-01", company="TH-CO", fees="FEES-01",
            requested_amount="300.00", reason="Full remaining",
            evidence="Evidence", requested_by="fin.off@example.invalid",
            existing_requests=[], collections=self.cols, refunds=self.refs)
        with self.assertRaisesRegex(RefundError, "exceeds collected"):
            REFUNDS.create_request(
                student="STU-01", company="TH-CO", fees="FEES-01",
                requested_amount="300.01", reason="One cent over",
                evidence="Evidence", requested_by="fin.off@example.invalid",
                existing_requests=[], collections=self.cols, refunds=self.refs)

    def test_over_refund_above_ceiling_is_refused(self):
        with self.assertRaisesRegex(RefundError, "exceeds collected"):
            REFUNDS.create_request(
                student="STU-01", company="TH-CO", fees="FEES-01",
                requested_amount="300.01", reason="Over",
                evidence="Evidence", requested_by="fin.off@example.invalid",
                existing_requests=[], collections=self.cols, refunds=self.refs)

    def test_split_installments_totalling_ceiling_allowed_exceeding_refused(self):
        first = REFUNDS.create_request(
            student="STU-01", company="TH-CO", fees="FEES-01",
            requested_amount="200.00", reason="First instalment",
            evidence="Evidence", requested_by="fin.off@example.invalid",
            existing_requests=[], collections=self.cols, refunds=self.refs)
        REFUNDS.create_request(
            student="STU-01", company="TH-CO", fees="FEES-01",
            requested_amount="100.00", reason="Second instalment",
            evidence="Evidence", requested_by="fin.off@example.invalid",
            existing_requests=[first], collections=self.cols, refunds=self.refs)
        with self.assertRaisesRegex(RefundError, "exceeds collected"):
            REFUNDS.create_request(
                student="STU-01", company="TH-CO", fees="FEES-01",
                requested_amount="100.01", reason="Too much split",
                evidence="Evidence", requested_by="fin.off@example.invalid",
                existing_requests=[first], collections=self.cols, refunds=self.refs)

    def test_second_request_while_one_is_approved_is_capped_by_open_amount(self):
        approved = self.approve()
        with self.assertRaisesRegex(RefundError, "exceeds collected"):
            REFUNDS.create_request(
                student="STU-01", company="TH-CO", fees="FEES-01",
                requested_amount="150.01", reason="Would exceed with open",
                evidence="Evidence", requested_by="fin.off@example.invalid",
                existing_requests=[approved], collections=self.cols,
                refunds=self.refs)

    def test_draft_and_cancelled_rows_do_not_raise_the_ceiling(self):
        cols = self.cols + [{"payment_entry": "IN-99", "student": "STU-01",
                             "company": "TH-CO", "fees": "FEES-01",
                             "docstatus": 0, "amount": "9999.00"}]
        refs = self.refs + [{"payment_entry": "OUT-99", "student": "STU-01",
                             "company": "TH-CO", "fees": "FEES-01",
                             "docstatus": 2, "amount": "9999.00"}]
        with self.assertRaisesRegex(RefundError, "exceeds collected"):
            REFUNDS.create_request(
                student="STU-01", company="TH-CO", fees="FEES-01",
                requested_amount="300.01", reason="Draft cannot fund",
                evidence="Evidence", requested_by="fin.off@example.invalid",
                existing_requests=[], collections=cols, refunds=refs)

    def test_forged_amount_approver_payer_student_company_fees_refused(self):
        # Tampered approval amount: approve always pins the requested amount.
        approved = self.approve()
        self.assertEqual(approved["approved_amount"], "150.00")
        # Forged payer == approver at pay time.
        with self.assertRaisesRegex(RefundError, "must not execute"):
            REFUNDS.pay_preflight(
                approved, payer="gm@example.invalid",
                payer_roles=["Finance Manager"], collections=self.cols,
                refunds=self.refs)
        # Forged roles.
        with self.assertRaisesRegex(RefundError, "General Manager"):
            REFUNDS.approve_request(self.request, approver="someone@example.invalid",
                                    approver_roles=["Finance Officer"])
        with self.assertRaisesRegex(RefundError, "Finance Manager"):
            REFUNDS.pay_preflight(
                approved, payer="reception@example.invalid",
                payer_roles=["Reception"], collections=self.cols,
                refunds=self.refs)
        # Forged student/company/fees in the ledger rows.
        bad_cols = [dict(self.cols[0], student="STU-99")]
        with self.assertRaisesRegex(RefundError, "unrelated"):
            REFUNDS.pay_preflight(
                approved, payer="fm@example.invalid",
                payer_roles=["Finance Manager"], collections=bad_cols,
                refunds=self.refs)
        # Forged request status: a Requested (unapproved) request cannot pay.
        with self.assertRaisesRegex(RefundError, "Only an Approved"):
            REFUNDS.pay_preflight(
                self.request, payer="fm@example.invalid",
                payer_roles=["Finance Manager"], collections=self.cols,
                refunds=self.refs)

    def test_self_approval_is_refused(self):
        with self.assertRaisesRegex(RefundError, "cannot approve their own"):
            REFUNDS.approve_request(self.request, approver="fin.off@example.invalid",
                                    approver_roles=["General Manager"])

    def test_cross_company_access_is_refused(self):
        other_cols = [dict(row, company="OTHER-CO") for row in self.cols]
        with self.assertRaisesRegex(RefundError, "unrelated"):
            REFUNDS.create_request(
                student="STU-01", company="TH-CO", fees="FEES-01",
                requested_amount="10.00", reason="Cross company",
                evidence="Evidence", requested_by="fin.off@example.invalid",
                existing_requests=[], collections=other_cols, refunds=self.refs)

    def test_zero_negative_and_fractional_cent_amounts_refused(self):
        for amount in ("0", "-5.00", "10.001", "NaN", "Infinity"):
            with self.subTest(amount=amount):
                with self.assertRaises(RefundError):
                    REFUNDS.create_request(
                        student="STU-01", company="TH-CO", fees="FEES-01",
                        requested_amount=amount, reason="Bad amount",
                        evidence="Evidence", requested_by="fin.off@example.invalid",
                        existing_requests=[], collections=self.cols,
                        refunds=self.refs)

    def test_reason_and_evidence_are_mandatory_and_bounded(self):
        for reason, evidence in (("", "Evidence"), ("Reason", ""), ("x" * 1001, "Evidence")):
            with self.subTest(reason=reason[:10], evidence=evidence[:10]):
                with self.assertRaises(RefundError):
                    REFUNDS.create_request(
                        student="STU-01", company="TH-CO", fees="FEES-01",
                        requested_amount="10.00", reason=reason,
                        evidence=evidence, requested_by="fin.off@example.invalid",
                        existing_requests=[], collections=self.cols,
                        refunds=self.refs)

    def test_denied_request_cannot_be_approved_or_paid(self):
        denied = REFUNDS.deny_request(self.request, approver="gm@example.invalid",
                                      approver_roles=["General Manager"])
        self.assertEqual(denied["status"], "Denied")
        with self.assertRaisesRegex(RefundError, "Only a Requested"):
            REFUNDS.approve_request(denied, approver="gm@example.invalid",
                                    approver_roles=["General Manager"])
        with self.assertRaisesRegex(RefundError, "Only an Approved"):
            REFUNDS.pay_preflight(
                denied, payer="fm@example.invalid",
                payer_roles=["Finance Manager"], collections=self.cols,
                refunds=self.refs)

    def test_pay_is_blocked_by_the_native_mechanism_and_leaves_request_approved(self):
        approved = self.approve()
        with self.assertRaises(NativeRefundBlocked):
            REFUNDS.pay_preflight(
                approved, payer="fm@example.invalid",
                payer_roles=["Finance Manager"], collections=self.cols,
                refunds=self.refs)
        # The request itself is untouched: still Approved, not Paid, not
        # consumed — a future verified mechanism can pay it without a new
        # approval round, and a second pay attempt is the same refusal.
        self.assertEqual(approved["status"], "Approved")
        self.assertIsNone(approved["payment_entry"])
        with self.assertRaises(NativeRefundBlocked):
            REFUNDS.pay_preflight(
                approved, payer="fm@example.invalid",
                payer_roles=["Finance Manager"], collections=self.cols,
                refunds=self.refs)

    def test_failed_ceiling_check_at_pay_time_is_not_a_blocker_consumption(self):
        # Collections shrink after approval (a receipt is cancelled): the
        # ceiling recomputed at pay time refuses, and the request stays
        # Approved for a corrected retry — it is not marked Paid.
        approved = self.approve()
        smaller_cols = collections("100.00")
        with self.assertRaises(RefundError):
            REFUNDS.pay_preflight(
                approved, payer="fm@example.invalid",
                payer_roles=["Finance Manager"], collections=smaller_cols,
                refunds=self.refs)
        self.assertEqual(approved["status"], "Approved")

    def test_cancelling_a_paid_refund_restores_the_ceiling_for_a_new_request_only(self):
        # A paid refund (docstatus 1) reduces the ceiling; cancelling it
        # (docstatus 2) restores it. The old request row itself is never
        # resurrected: pay on a Paid row is refused.
        paid_ceiling = REFUNDS.ceiling_after_cancellation(
            self.cols, self.refs, student="STU-01", company="TH-CO", fees="FEES-01")
        self.assertEqual(str(paid_ceiling), "300.00")
        cancelled_refs = refunds(("200.00", 2))
        restored = REFUNDS.ceiling_after_cancellation(
            self.cols, cancelled_refs, student="STU-01", company="TH-CO",
            fees="FEES-01")
        self.assertEqual(str(restored), "500.00")
        paid_row = dict(self.approve(), status="Paid")
        with self.assertRaisesRegex(RefundError, "Only an Approved"):
            REFUNDS.pay_preflight(
                paid_row, payer="fm@example.invalid",
                payer_roles=["Finance Manager"], collections=self.cols,
                refunds=cancelled_refs)


class StudentPayGuardExceptionTests(unittest.TestCase):
    def payment(self, **overrides):
        doc = {
            "payment_type": "Pay", "party_type": "Student", "party": "STU-01",
            "company": "TH-CO", "paid_amount": "150.00",
            "references": [{"reference_doctype": "Fees", "reference_name": "FEES-01",
                            "allocated_amount": "150.00"}],
        }
        doc.update(overrides)
        return doc

    def test_direct_student_pay_outside_any_command_is_still_denied(self):
        for method in (None, "validate", "before_submit", "before_update_after_submit", ""):
            with self.subTest(method=method):
                self.assertFalse(POLICY.student_pay_write_allowed(
                    "Pay", "Student", method, payment=self.payment()))

    def test_cancellation_of_a_legacy_student_pay_is_still_allowed(self):
        self.assertTrue(POLICY.student_pay_write_allowed(
            "Pay", "Student", "before_cancel", payment=self.payment()))

    def test_receipts_and_non_student_payments_unaffected(self):
        self.assertTrue(POLICY.student_pay_write_allowed("Receive", "Student", "validate"))
        self.assertTrue(POLICY.student_pay_write_allowed("Pay", "Customer", None))

    def test_narrow_exception_matches_only_the_exact_live_request(self):
        context = {"student": "STU-01", "company": "TH-CO", "fees": "FEES-01",
                   "amount": "150.00"}
        with POLICY.refund_payment_context(context):
            self.assertTrue(POLICY.student_pay_write_allowed(
                "Pay", "Student", "validate", payment=self.payment()))
            for bad in (
                    self.payment(party="STU-99"),
                    self.payment(company="OTHER-CO"),
                    self.payment(paid_amount="150.01"),
                    self.payment(references=[{"reference_doctype": "Fees",
                                             "reference_name": "FEES-99",
                                             "allocated_amount": "150.00"}]),
                    self.payment(references=[]),
                    self.payment(references=[
                        {"reference_doctype": "Fees", "reference_name": "FEES-01",
                         "allocated_amount": "150.00"},
                        {"reference_doctype": "Fees", "reference_name": "FEES-01",
                         "allocated_amount": "0.00"}]),
            ):
                with self.subTest(bad=bad):
                    self.assertFalse(POLICY.student_pay_write_allowed(
                        "Pay", "Student", "validate", payment=bad))
        # Context is cleared: the same payment is denied again afterwards.
        self.assertFalse(POLICY.student_pay_write_allowed(
            "Pay", "Student", "validate", payment=self.payment()))

    def test_refund_payment_matches_predicate_agrees_with_guard(self):
        approved = REFUNDS.approve_request(
            REFUNDS.create_request(
                student="STU-01", company="TH-CO", fees="FEES-01",
                requested_amount="150.00", reason="Withdrawal",
                evidence="Letter", requested_by="fin.off@example.invalid",
                existing_requests=[], collections=collections("500.00"),
                refunds=[]),
            approver="gm@example.invalid", approver_roles=["General Manager"])
        self.assertTrue(REFUNDS.refund_payment_matches(self.payment(), approved))
        self.assertFalse(REFUNDS.refund_payment_matches(
            self.payment(paid_amount="200.00"), approved))


class NativeBlockerEvidenceTests(unittest.TestCase):
    def test_blocker_names_the_pinned_failure(self):
        self.assertIn("Payment", REFUNDS.NATIVE_BLOCKER)
        self.assertIn("Fees", REFUNDS.NATIVE_BLOCKER)
        self.assertIn("disabled", REFUNDS.NATIVE_BLOCKER)

    def test_command_layer_references_the_pure_rules_and_blocker(self):
        source = (APP / "finance" / "tuition_refund_commands.py").read_text()
        for token in ("request_tuition_refund", "approve_tuition_refund",
                      "deny_tuition_refund", "pay_tuition_refund",
                      "NativeRefundBlocked", "NATIVE_BLOCKER",
                      "require_finance_company", "tuition_refunds.pay_preflight"):
            self.assertIn(token, source)

    def test_doctype_json_matches_the_workflow_fields(self):
        import json
        doctype = json.loads((APP / "finance" / "doctype"
                              / "th_tuition_refund_request"
                              / "th_tuition_refund_request.json").read_text())
        fields = {field["fieldname"] for field in doctype["fields"]}
        for expected in ("student", "company", "fees", "requested_amount",
                         "approved_amount", "reason", "evidence", "status",
                         "requested_by", "approved_by", "paying_user",
                         "payment_entry", "synthetic"):
            self.assertIn(expected, fields)
        self.assertEqual(doctype["name"], "TH Tuition Refund Request")


if __name__ == "__main__":
    unittest.main()

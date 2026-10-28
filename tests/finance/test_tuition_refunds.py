"""Tuition refund workflow (Issue #115) — pure rules, no site, no money.

Tests load the pure modules by file path with stubbed parent packages,
following tests/finance/test_refund_guards.py. No Frappe, no database, no
native posting is attempted anywhere here: the pinned native Fees refund
mechanism does not exist, so pay_preflight must refuse at the posting
step with NativeRefundBlocked and leave the request Approved.
"""
import ast
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


class StudentPayGuardHoldTests(unittest.TestCase):
    def test_every_new_student_payout_is_denied(self):
        for method in (None, "validate", "before_submit",
                       "before_update_after_submit", ""):
            with self.subTest(method=method):
                self.assertFalse(POLICY.student_pay_write_allowed(
                    "Pay", "Student", method))

    def test_cancellation_of_legacy_student_payout_is_permitted(self):
        self.assertTrue(POLICY.student_pay_write_allowed(
            "Pay", "Student", "before_cancel"))

    def test_native_receipts_and_non_student_payments_are_unaffected(self):
        self.assertTrue(POLICY.student_pay_write_allowed(
            "Receive", "Student", "validate"))
        self.assertTrue(POLICY.student_pay_write_allowed(
            "Pay", "Customer", None))


class RefundSourceCompletenessTests(unittest.TestCase):
    def load_query(self, function, db):
        path = APP / "finance" / "tuition_refund_commands.py"
        source = ast.parse(path.read_text(encoding="utf-8"))
        selected = next(n for n in source.body
                        if isinstance(n, ast.FunctionDef) and n.name == function)
        namespace = {
            "frappe": types.SimpleNamespace(db=db, ValidationError=ValueError),
            "REQUEST": "TH Tuition Refund Request",
            "FEES": "Fees", "PAYMENT": "Payment Entry",
        }
        exec(compile(ast.Module(body=[selected], type_ignores=[]),
                     str(path), "exec"), namespace)
        return namespace[function]

    def test_refund_source_rows_keep_fee_identity_for_open_reservations(self):
        class Stub:
            def get_all(self, doctype, filters, fields, limit_page_length):
                self_fields = {"fees": "FEES-01", "status": "Approved",
                               "requested_amount": 200,
                               "approved_amount": 200}
                return [{key: self_fields[key] for key in fields}]
        rows = self.load_query("_existing_requests", Stub())("FEES-01")
        self.assertEqual(rows[0]["fees"], "FEES-01")
        self.assertEqual(str(REFUNDS.open_amount(rows, fees="FEES-01")), "200")
        with self.assertRaises(RefundError):
            REFUNDS.create_request(
                student="STU-01", company="TH-CO", fees="FEES-01",
                requested_amount="101.00", reason="Oversubscribed",
                evidence="Evidence", requested_by="officer@example.invalid",
                existing_requests=rows,
                collections=collections("300.00"), refunds=[])

    def test_native_currency_floats_are_normalized_at_trusted_read_boundary(self):
        class Stub:
            def get_all(self, doctype, filters, fields, limit_page_length):
                return [
                    {"fees": "FEES-01", "status": "Approved",
                     "requested_amount": 40.0, "approved_amount": 40.0},
                    {"fees": "FEES-01", "status": "Denied",
                     "requested_amount": 10.0, "approved_amount": 0.0},
                ]
        rows = self.load_query("_existing_requests", Stub())("FEES-01")
        self.assertEqual(rows[0]["requested_amount"], "40.0")
        self.assertEqual(rows[0]["approved_amount"], "40.0")
        self.assertEqual(str(REFUNDS.open_amount(rows, fees="FEES-01")), "40.0")

    def test_database_currency_normalization_does_not_accept_bad_precision(self):
        class Stub:
            def get_all(self, doctype, filters, fields, limit_page_length):
                return [{"fees": "FEES-01", "status": "Requested",
                         "requested_amount": 10.001, "approved_amount": 0.0}]
        rows = self.load_query("_existing_requests", Stub())("FEES-01")
        with self.assertRaises(RefundError):
            REFUNDS.open_amount(rows, fees="FEES-01")

    def test_truncated_refund_claim_sources_fail_closed(self):
        class Stub:
            def get_all(self, doctype, filters, fields, limit_page_length):
                self.limit = limit_page_length
                return [{"fees": "FEES-01"} for _ in range(limit_page_length)]
        db = Stub()
        with self.assertRaises(ValueError):
            self.load_query("_existing_requests", db)("FEES-01")
        self.assertEqual(db.limit, 1001)

    def test_truncated_payment_allocations_fail_closed(self):
        class Stub:
            def get_all(self, doctype, filters, fields, limit_page_length):
                self.limit = limit_page_length
                return [{"parent": "PE", "allocated_amount": 1}
                        for _ in range(limit_page_length)]
        db = Stub()
        with self.assertRaises(ValueError):
            self.load_query("_ledger_rows", db)(
                "STU-01", "TH-CO", "FEES-01", kind="Collections")
        self.assertEqual(db.limit, 1001)


class NativeRefundControllerBoundaryTests(unittest.TestCase):
    class Row(dict):
        def __getattr__(self, key):
            return self.get(key)

    def check(self, before, after, kind, actor="general.manager@example.invalid"):
        source_path = APP / "controllers.py"
        source = ast.parse(source_path.read_text(encoding="utf-8"))
        parent = next(node for node in source.body
                      if isinstance(node, ast.ClassDef)
                      and node.name == "ProtectedRecord")
        fn = next(node for node in parent.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "_validate_tuition_refund_request")
        namespace = {
            "frappe": types.SimpleNamespace(PermissionError=PermissionError),
            "require_command": lambda doctype: (kind, actor),
        }
        exec(compile(ast.Module(body=[fn], type_ignores=[]),
                     str(source_path), "exec"), namespace)
        namespace[fn.name](after, before)

    def refund(self, status, **changes):
        base = {
            "doctype": "TH Tuition Refund Request", "student": "STU-01",
            "company": "TH-CO", "fees": "FEES-01",
            "requested_amount": 100, "reason": "Withdrawal",
            "evidence": "Original supporting letter",
            "requested_by": "finance.officer@example.invalid",
            "approved_amount": None, "approval_evidence": None,
            "approved_by": None, "payment_entry": None,
            "status": status,
        }
        base.update(changes)
        return self.Row(base)

    def test_only_matching_GM_command_can_approve_or_deny(self):
        original = self.refund("Requested")
        approved = self.refund(
            "Approved", approved_by="general.manager@example.invalid",
            approved_amount=100, approval_evidence="Reviewed withdrawal letter")
        self.check(original, approved, "approve_tuition_refund")
        with self.assertRaises(PermissionError):
            self.check(original, approved, "request_tuition_refund")
        with self.assertRaises(PermissionError):
            self.check(original, approved, "deny_tuition_refund")
        denied = self.refund(
            "Denied", approved_by="general.manager@example.invalid")
        self.check(original, denied, "deny_tuition_refund")
        with self.assertRaises(PermissionError):
            self.check(original, denied, "approve_tuition_refund")

    def test_frappe_currency_zero_default_allows_first_gm_approval_only(self):
        # Pinned Frappe get_valid_dict converts empty Currency to 0.0 at
        # SQL insert. A blank, never-approved amount must not freeze approval.
        original = self.refund("Requested", approved_amount=0.0)
        approved = self.refund(
            "Approved", approved_by="general.manager@example.invalid",
            approved_amount=100, approval_evidence="Reviewed withdrawal letter")
        self.check(original, approved, "approve_tuition_refund")
        # A prepopulated nonzero amount on a Requested record is suspicious,
        # not an excuse to overwrite an existing or forged approval value.
        with self.assertRaises(PermissionError):
            self.check(self.refund("Requested", approved_amount=1.0),
                       approved, "approve_tuition_refund")
        with self.assertRaises(PermissionError):
            self.check(self.refund("Approved", approved_amount=100,
                                  approved_by="general.manager@example.invalid"),
                       self.refund("Paid", approved_amount=50,
                                   approved_by="general.manager@example.invalid"),
                       "pay_tuition_refund")

    def test_paid_transition_is_blocked_even_with_valid_command_context(self):
        approved = self.refund(
            "Approved", approved_by="general.manager@example.invalid",
            approved_amount=100, approval_evidence="Approved")
        paid = self.refund(
            "Paid", approved_by="general.manager@example.invalid",
            approved_amount=100, approval_evidence="Approved",
            payment_entry="PE-0001")
        for kind in ("pay_tuition_refund", "approve_tuition_refund"):
            with self.subTest(kind=kind):
                with self.assertRaises(PermissionError):
                    self.check(approved, paid, kind)

    def test_requester_evidence_cannot_be_overwritten_during_approval(self):
        original = self.refund("Requested")
        overwritten = self.refund(
            "Approved", approved_by="general.manager@example.invalid",
            approved_amount=100, approval_evidence="Reviewed",
            evidence="Different supporting letter")
        with self.assertRaises(PermissionError):
            self.check(original, overwritten, "approve_tuition_refund")


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
                         "approved_amount", "reason", "evidence", "approval_evidence",
                         "status",
                         "requested_by", "approved_by", "paying_user",
                         "payment_entry", "synthetic"):
            self.assertIn(expected, fields)
        self.assertEqual(doctype["name"], "TH Tuition Refund Request")


if __name__ == "__main__":
    unittest.main()

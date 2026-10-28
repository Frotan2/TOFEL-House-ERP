"""Frappe command layer for tuition refunds (Issue #115).

Thin wrappers around the pure rules in ``toefl_house.finance.tuition_refunds``:
they lock the Fees row and the request row (``for update``), re-prove live
facts against the native ledger at each step, enforce Company scope
(``require_finance_company``) and Branch scope (``command_scope`` via
``_execute``), and record the decision on the ``TH Tuition Refund Request``
record. Request creation requires Finance Officer; approve/deny
require General Manager, and payout requires a different Finance Manager.
These are distinct command roles (no Finance Officer prerequisite for the
approver or payer), and native Fees payout remains blocked.

Payout is deliberately NOT posted here: ``pay_tuition_refund`` runs the
full preflight and then raises the native-mechanism blocker, leaving the
request Approved and unconsumed. See ``tuition_refunds.NATIVE_BLOCKER``
for the pinned-code evidence. When a verified native Fees refund
mechanism exists, only the final step of ``pay_tuition_refund`` changes:
create the native artifact inside the refund-payment guard context, submit
it, then set status Paid and payment_entry — all other checks stay.
"""
import frappe
from toefl_house.api import _execute
from toefl_house.finance import tuition_refunds
from toefl_house.finance.company_scope import require_finance_company
from toefl_house.policy import digest
from toefl_house.security import record_synthetic_flag

REQUEST = "TH Tuition Refund Request"
FEES = "Fees"
PAYMENT = "Payment Entry"


def _audit_hash(req):
    """Bind one audit event to the exact persisted refund request state.

    No raw student identity, reason, or supporting evidence is copied into
    the shared event ledger. A hash of the authoritative record distinguishes
    Requested, Approved, and Denied transitions and exposes stale replays.
    """
    return digest({
        "name": req.name,
        "student": req.get("student"),
        "company": req.get("company"),
        "fees": req.get("fees"),
        "requested_amount": str(req.get("requested_amount") or ""),
        "approved_amount": str(req.get("approved_amount") or ""),
        "reason": req.get("reason") or "",
        "evidence": req.get("evidence") or "",
        "approval_evidence": req.get("approval_evidence") or "",
        "status": req.get("status"),
        "requested_by": req.get("requested_by"),
        "approved_by": req.get("approved_by"),
        "paying_user": req.get("paying_user"),
        "payment_entry": req.get("payment_entry"),
    })


def _name(value, label):
    if not isinstance(value, str) or not value or len(value) > 140:
        raise frappe.ValidationError(f"{label} required")
    return value


def _require_role(actor, role):
    if role not in frappe.get_roles(actor):
        raise frappe.PermissionError(f"Actor does not hold the {role} role")


def _ledger_rows(student, company, fees, *, kind):
    """Native ledger rows for one student/company/Fees, scoped and complete.

    Collections: submitted Payment Entry Receive rows referencing the Fees
    (party Student). Refunds: submitted Payment Entry Pay rows referencing
    the Fees — today there are none for tuition, because payout is blocked;
    the query still runs so a future mechanism's refunds are counted, and
    cancelled rows are returned with docstatus 2 so the preflight excludes
    them from the ceiling while still proving completeness.
    """
    rows = frappe.db.get_all(
        "Payment Entry Reference",
        filters={"reference_doctype": FEES, "reference_name": fees},
        fields=["parent", "allocated_amount"],
        limit_page_length=1001,
    )
    if len(rows or []) > 1000:
        raise frappe.ValidationError(
            "Tuition payment references exceed the verified reporting limit")
    scoped = []
    for row in rows or []:
        entry = frappe.db.get_value(
            PAYMENT, row["parent"],
            ["payment_type", "party_type", "party", "company", "docstatus"],
            as_dict=True)
        if not entry or entry.get("party_type") != "Student" \
                or entry.get("party") != student \
                or entry.get("company") != company:
            raise frappe.ValidationError(
                "Tuition payment reference has missing or mismatched ownership")
        if kind == "Collections" and entry.get("payment_type") != "Receive":
            continue
        if kind == "Refunds" and entry.get("payment_type") != "Pay":
            continue
        scoped.append({
            "payment_entry": row["parent"], "student": student,
            "company": company, "fees": fees,
            "docstatus": int(entry.get("docstatus") or 0),
            "amount": str(row["allocated_amount"]),
        })
    return scoped


def _existing_requests(fees):
    rows = frappe.db.get_all(
        REQUEST, filters={"fees": fees},
        fields=["fees", "status", "requested_amount", "approved_amount"],
        limit_page_length=1001)
    if len(rows or []) > 1000:
        raise frappe.ValidationError(
            "Tuition refund request evidence exceeds the verified reporting limit")
    return [dict(row) for row in (rows or [])]


def _pending_request(name):
    if not frappe.db.exists(REQUEST, name):
        raise frappe.ValidationError("Unknown tuition refund request")
    frappe.db.sql(
        "select name from `tabTH Tuition Refund Request` where name=%s for update",
        (name,))
    return frappe.get_doc(REQUEST, name)


@frappe.whitelist(methods=["POST"])
def request_tuition_refund(request_key, student, company, fees, requested_amount,
                           reason, evidence):
    """Open a tuition refund request (Finance Officer). No money moves."""
    def work(actor):
        student_name = _name(student, "Student")
        company_name = require_finance_company(_name(company, "Company"))
        fees_name = _name(fees, "Fees")
        frappe.db.sql("select name from `tabFees` where name=%s for update", (fees_name,))
        fee_row = frappe.db.get_value(
            FEES, fees_name, ["docstatus", "student", "company"], as_dict=True)
        if not fee_row:
            raise frappe.ValidationError("Unknown fee")
        if int(fee_row.docstatus or 0) != 1:
            raise frappe.ValidationError("Refunds require a submitted fee")
        if fee_row.student != student_name or fee_row.company != company_name:
            raise frappe.ValidationError(
                "The fee does not belong to this student and company")
        try:
            validated = tuition_refunds.create_request(
                student=student_name, company=company_name, fees=fees_name,
                requested_amount=requested_amount, reason=reason,
                evidence=evidence, requested_by=actor,
                existing_requests=_existing_requests(fees_name),
                collections=_ledger_rows(student_name, company_name, fees_name,
                                         kind="Collections"),
                refunds=_ledger_rows(student_name, company_name, fees_name,
                                     kind="Refunds"))
        except (tuition_refunds.RefundError, ValueError) as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = frappe.get_doc(dict(
            doctype=REQUEST, student=validated["student"],
            company=validated["company"], fees=validated["fees"],
            requested_amount=float(validated["requested_amount"]),
            reason=validated["reason"], evidence=validated["evidence"],
            status="Requested", requested_by=actor,
            synthetic=record_synthetic_flag()))
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        result = {"name": doc.name, "status": "Requested",
                  "requested_amount": validated["requested_amount"]}
        return result, dict(target=doc.name, after_hash=_audit_hash(doc))

    return _execute("request_tuition_refund", request_key,
                    {"student": student, "company": company, "fees": fees,
                     "requested_amount": requested_amount, "reason": reason,
                     "evidence": evidence}, work)


@frappe.whitelist(methods=["POST"])
def approve_tuition_refund(request_key, request, evidence=None):
    """General Manager approval; requester may not self-approve."""
    def work(actor):
        _require_role(actor, tuition_refunds.APPROVER_ROLE)
        req = _pending_request(_name(request, "Tuition refund request"))
        _require_target_company(req.fees)
        try:
            approved = tuition_refunds.approve_request(
                {"status": req.status, "requested_by": req.requested_by,
                 "requested_amount": str(req.requested_amount),
                 "evidence": req.evidence},
                approver=actor, approver_roles=frappe.get_roles(actor),
                evidence=evidence)
        except (tuition_refunds.RefundError, ValueError) as exc:
            raise frappe.ValidationError(str(exc)) from exc
        before_hash = _audit_hash(req)
        req.flags.ignore_permissions = True
        req.status = "Approved"
        req.approved_by = actor
        req.approved_amount = float(approved["approved_amount"])
        req.approval_evidence = approved["evidence"]
        req.save(ignore_permissions=True)
        return {"name": req.name, "status": "Approved",
                "approved_amount": approved["approved_amount"]}, \
            dict(target=req.name, before_hash=before_hash, after_hash=_audit_hash(req))

    return _execute("approve_tuition_refund", request_key,
                    {"request": request, "evidence": evidence}, work)


@frappe.whitelist(methods=["POST"])
def deny_tuition_refund(request_key, request):
    """General Manager denial. No money moves."""
    def work(actor):
        _require_role(actor, tuition_refunds.APPROVER_ROLE)
        req = _pending_request(_name(request, "Tuition refund request"))
        _require_target_company(req.fees)
        try:
            tuition_refunds.deny_request(
                {"status": req.status}, approver=actor,
                approver_roles=frappe.get_roles(actor))
        except (tuition_refunds.RefundError, ValueError) as exc:
            raise frappe.ValidationError(str(exc)) from exc
        before_hash = _audit_hash(req)
        req.flags.ignore_permissions = True
        req.status = "Denied"
        req.approved_by = actor
        req.save(ignore_permissions=True)
        return {"name": req.name, "status": "Denied"}, dict(
            target=req.name, before_hash=before_hash, after_hash=_audit_hash(req))

    return _execute("deny_tuition_refund", request_key,
                    {"request": request}, work)


def _require_target_company(fees):
    from toefl_house.finance.corrections import _require_target_company as require
    return require(FEES, fees)


@frappe.whitelist(methods=["POST"])
def pay_tuition_refund(request_key, request):
    """Finance Manager payout attempt.

    Runs the full preflight (Approved status, Finance Manager role,
    approver != payer, ceiling recomputed from the live native ledger at
    pay time) and then refuses at the native posting step: no verified
    native Fees refund mechanism exists on the pinned stack, so no Payment
    Entry is created, the request stays Approved, and the approval is not
    consumed. A retry after a mechanism exists needs no new approval.
    """
    def work(actor):
        _require_role(actor, tuition_refunds.PAYER_ROLE)
        req = _pending_request(_name(request, "Tuition refund request"))
        _require_target_company(req.fees)
        try:
            tuition_refunds.pay_preflight(
                {"status": req.status, "student": req.student,
                 "company": req.company, "fees": req.fees,
                 "approved_amount": str(req.approved_amount),
                 "reason": req.reason, "approved_by": req.approved_by},
                payer=actor, payer_roles=frappe.get_roles(actor),
                collections=_ledger_rows(req.student, req.company, req.fees,
                                         kind="Collections"),
                refunds=_ledger_rows(req.student, req.company, req.fees,
                                     kind="Refunds"))
        except tuition_refunds.NativeRefundBlocked as exc:
            raise frappe.ValidationError(str(exc)) from exc
        except (tuition_refunds.RefundError, ValueError) as exc:
            raise frappe.ValidationError(str(exc)) from exc
        raise frappe.ValidationError(tuition_refunds.NATIVE_BLOCKER)

    return _execute("pay_tuition_refund", request_key,
                    {"request": request}, work)

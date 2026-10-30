"""Pure case-by-case tuition refund authority and reservation rules.

General Manager approves each exact amount with supporting evidence; a
DIFFERENT Finance Manager executes it. The ceiling is verified submitted
tuition collections less earlier completed native refunds. No automatic
percentage, refund window, pro-rata price or unpaid-balance waiver is inferred.

validate_payment_authority checks those rules without granting native writes.
The server's tuition_refund_native module separately posts and reconciles a
native income credit and Student payout against the exact Fees in one atomic
command. A standalone Student Pay increases receivable and is never a valid
refund by itself. pay_preflight remains a deliberately nonposting legacy
utility; its NativeRefundBlocked exception cannot authorize any accounting.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from toefl_house.setup_presets.tuition_refund_review import inspect_case_refund

CENT = Decimal("0.01")
STATUSES = ("Requested", "Approved", "Denied", "Paid", "Voided")
APPROVER_ROLE = "General Manager"
PAYER_ROLE = "Finance Manager"
REQUESTER_ROLE = "Finance Officer"

NATIVE_BLOCKER = (
    "A standalone Payment Entry Pay/Student referencing Fees is not a "
    "tuition refund. Standalone payout stays disabled. Only the separately "
    "qualified atomic native credit/payment command may move funds; this "
    "legacy preflight leaves the request Approved and unconsumed."
)


class NativeRefundBlocked(ValueError):
    """Legacy preflight refuses standalone posting; native pair is separate."""


class RefundError(ValueError):
    """Any request/approval/pay rule refusal (pure, no Frappe dependency)."""


def _money(value, what):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise RefundError(f"{what} must be a currency amount")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise RefundError(f"{what} must be a currency amount") from exc
    if not number.is_finite() or number <= 0 \
            or number > Decimal("999999999999.99"):
        raise RefundError(f"{what} must be a bounded positive currency amount")
    try:
        valid = number == number.quantize(CENT)
    except InvalidOperation as exc:
        raise RefundError(f"{what} exceeds supported currency precision") from exc
    if not valid:
        raise RefundError(f"{what} must have at most two decimals")
    return number


def _id(value, what):
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise RefundError(f"{what} must be a nonempty bounded identifier")
    return value.strip()


def _text(value, what, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise RefundError(f"{what} is required and bounded to {limit} characters")
    return value.strip()


def _rows_for(rows, *, student, company, fees, kind):
    """Ledger rows already scoped to one student/company/Fees by the caller.

    The caller (command layer) must read these from the native ledger with
    Company/Branch scope enforced; this function refuses any row that does
    not match, so a forged client row list can never widen the ceiling.
    """
    scoped = []
    for row in rows or []:
        if not isinstance(row, dict):
            raise RefundError(f"{kind} must contain native document facts")
        if (row.get("student") != student or row.get("company") != company
                or row.get("fees") != fees):
            raise RefundError(f"{kind} includes an unrelated student/company/bill")
        scoped.append(row)
    return scoped


def ceiling(collections, refunds, *, student, company, fees):
    """Available refundable amount from native ledger rows, in AFN.

    Uses the existing ceiling preflight's own arithmetic (submitted
    collections minus submitted refunds; draft and cancelled rows count
    for nothing), with a zero approved amount used only to read the
    ceiling — never as a payout. Returns a Decimal.
    """
    probe = {
        "student": student, "company": company, "fees": fees,
        "approved_amount": "0.01", "reason": "ceiling probe",
        "approved_by": "general.manager@example.invalid",
        "paying_user": "finance.manager@example.invalid",
        "approval_status": "Approved",
    }
    # A zero-amount probe is refused by the preflight, so read the ceiling
    # by asking it to approve 0.01 and, if that itself exceeds the ceiling,
    # the ceiling is below 0.01 — i.e. effectively zero for AFN cents.
    try:
        result = inspect_case_refund(
            probe, _rows_for(collections, student=student, company=company,
                             fees=fees, kind="Collections"),
            _rows_for(refunds, student=student, company=company, fees=fees,
                      kind="Refunds"), native_evidence_complete=True)
        return Decimal(result["remaining_refundable_afn"])
    except ValueError as exc:
        message = str(exc)
        if "exceeds collected" in message:
            # Available is less than one cent: no refundable amount.
            return Decimal("0")
        if "No verified submitted tuition receipt" in message:
            return Decimal("0")
        raise RefundError(message) from exc


def open_amount(requests, *, fees):
    """Sum of Requested + Approved amounts for one Fees document.

    Paid requests are already in the refunds ledger rows, so counting them
    here would double-count. Denied and Voided requests reserve nothing.
    """
    total = Decimal("0")
    for request in requests or []:
        if not isinstance(request, dict):
            raise RefundError("Refund requests must be records")
        if request.get("fees") != fees:
            continue
        status = request.get("status")
        if status not in STATUSES:
            raise RefundError("Unknown refund request status in reservation ledger")
        if status in ("Requested", "Approved"):
            requested = _money(request.get("requested_amount"), "Request amount")
            if status == "Approved":
                approved = _money(request.get("approved_amount"), "Approved amount")
                if approved != requested:
                    raise RefundError("Approved refund differs from requested amount")
            total += requested
    return total


def create_request(*, student, company, fees, requested_amount, reason,
                   evidence, requested_by, existing_requests,
                   collections, refunds):
    """Validate a new tuition refund request (status Requested).

    A new request is refused when the open (Requested + Approved) amount
    for the same Fees plus the new amount would exceed the recomputed
    ceiling — split installments are allowed only while their total stays
    inside the ceiling.
    """
    student = _id(student, "Student")
    company = _id(company, "Company")
    fees = _id(fees, "Original Fees")
    amount = _money(requested_amount, "Requested refund")
    reason = _text(reason, "Refund reason", 1000)
    evidence = _text(evidence, "Supporting evidence", 2000)
    requested_by = _id(requested_by, "Requesting Finance Officer")
    available = ceiling(collections, refunds, student=student,
                        company=company, fees=fees)
    already_open = open_amount(existing_requests, fees=fees)
    if already_open + amount > available:
        raise RefundError(
            "Requested refund exceeds collected tuition less earlier refunds "
            "and open refund requests")
    return {
        "student": student, "company": company, "fees": fees,
        "requested_amount": str(amount), "approved_amount": None,
        "reason": reason, "evidence": evidence,
        "status": "Requested", "requested_by": requested_by,
        "approved_by": None, "paying_user": None, "payment_entry": None,
    }


def approve_request(request, *, approver, approver_roles, evidence=None):
    """General Manager approval of a Requested request.

    The approved amount is exactly the requested amount — the approver
    cannot silently change it; a different amount needs a denied request
    and a new one. Evidence must be present (recorded at request time or
    supplied at approval). The approver must not be the requester.
    """
    if not isinstance(request, dict):
        raise RefundError("Refund request is required")
    if request.get("status") != "Requested":
        raise RefundError("Only a Requested refund can be approved")
    approver = _id(approver, "Approving General Manager")
    if APPROVER_ROLE not in (approver_roles or []):
        raise RefundError("Only a General Manager may approve a tuition refund")
    if approver == request.get("requested_by"):
        raise RefundError("A requester cannot approve their own refund")
    final_evidence = evidence if evidence is not None else request.get("evidence")
    _text(final_evidence, "Supporting evidence", 2000)
    approved = dict(request)
    approved["status"] = "Approved"
    approved["approved_by"] = approver
    approved["approved_amount"] = approved["requested_amount"]
    approved["evidence"] = final_evidence.strip()
    return approved


def deny_request(request, *, approver, approver_roles):
    """General Manager denial of a Requested request; no money moves."""
    if not isinstance(request, dict):
        raise RefundError("Refund request is required")
    if request.get("status") != "Requested":
        raise RefundError("Only a Requested refund can be denied")
    approver = _id(approver, "Approving General Manager")
    if APPROVER_ROLE not in (approver_roles or []):
        raise RefundError("Only a General Manager may deny a tuition refund")
    denied = dict(request)
    denied["status"] = "Denied"
    denied["approved_by"] = approver
    return denied


def void_approval(request, *, actor, roles, reason):
    """Revoke an unpaid approval without changing its recorded decision facts."""
    if not isinstance(request, dict) or request.get("status") != "Approved":
        raise RefundError("Only an Approved unpaid refund may be voided")
    if APPROVER_ROLE not in (roles or []):
        raise RefundError("Only a General Manager may void a tuition refund approval")
    actor = _id(actor, "Voiding General Manager")
    reason = _text(reason, "Approval withdrawal reason", 1000)
    if request.get("payment_entry") or request.get("credit_journal") or request.get("paying_user"):
        raise RefundError("A posted refund requires an independently authorized paired reversal")
    return dict(request, status="Voided", voided_by=actor, void_reason=reason)


def validate_payment_authority(request, *, payer, payer_roles, collections, refunds):
    """Validate case authority and ceiling; this never posts or grants native writes."""
    if not isinstance(request, dict):
        raise RefundError("Refund request is required")
    if request.get("status") != "Approved":
        raise RefundError("Only an Approved refund can be paid")
    payer = _id(payer, "Finance Manager")
    if PAYER_ROLE not in (payer_roles or []):
        raise RefundError("Only a Finance Manager may pay a tuition refund")
    if payer == request.get("approved_by"):
        raise RefundError("The approving manager must not execute their own refund")
    if request.get("approved_amount") is None:
        raise RefundError("Approved refund amount is missing")
    try:
        report = inspect_case_refund(
            {
                "student": request["student"], "company": request["company"],
                "fees": request["fees"],
                "approved_amount": request["approved_amount"],
                "reason": request["reason"], "approved_by": request["approved_by"],
                "paying_user": payer, "approval_status": "Approved",
            },
            _rows_for(collections, student=request["student"],
                      company=request["company"], fees=request["fees"],
                      kind="Collections"),
            _rows_for(refunds, student=request["student"],
                      company=request["company"], fees=request["fees"],
                      kind="Refunds"),
            native_evidence_complete=True)
    except ValueError as exc:
        # A ledger that no longer supports the approval (receipt cancelled,
        # refunds now exceeding collections) is a rule refusal, not a
        # blocker consumption: the request stays Approved.
        raise RefundError(str(exc)) from exc
    if report["payment_permitted"]:
        raise RefundError("Unexpected: refund preflight permitted a payout")
    return report


def pay_preflight(request, *, payer, payer_roles, collections, refunds):
    """Legacy nonposting preflight; native accounting must qualify separately."""
    validate_payment_authority(request, payer=payer, payer_roles=payer_roles,
                               collections=collections, refunds=refunds)
    raise NativeRefundBlocked(NATIVE_BLOCKER)


def ceiling_after_cancellation(collections, refunds, *, student, company, fees):
    """Ceiling after a paid refund Payment Entry is cancelled.

    Cancelled rows (docstatus 2) are excluded by the preflight's own
    arithmetic, so the ceiling is restored for a NEW request. The old
    request row itself stays Paid and is never resurrected: pay_preflight
    refuses any non-Approved request.
    """
    return ceiling(collections, refunds, student=student, company=company,
                   fees=fees)


def refund_payment_matches(payment, request):
    """Narrow Student Pay guard predicate (see student_payout_policy).

    ``payment`` is a Payment Entry-like mapping/object with payment_type,
    party_type, party, company, paid_amount and a single Fees reference
    (reference_doctype/reference_name/allocated_amount). It matches only
    when every field equals the live Approved request exactly. Any other
    Student Pay stays denied by the guard.
    """
    def get(obj, key):
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    if get(payment, "payment_type") != "Pay" \
            or get(payment, "party_type") != "Student":
        return False
    if request.get("status") != "Approved":
        return False
    if get(payment, "party") != request.get("student") \
            or get(payment, "company") != request.get("company"):
        return False
    try:
        amount = _money(get(payment, "paid_amount"), "Payment amount")
    except RefundError:
        return False
    try:
        approved_amount = _money(request.get("approved_amount"), "Approved amount")
    except RefundError:
        return False
    if amount != approved_amount:
        return False
    references = get(payment, "references") or []
    if len(references) != 1:
        return False
    reference = references[0]
    if get(reference, "reference_doctype") != "Fees" \
            or get(reference, "reference_name") != request.get("fees"):
        return False
    try:
        allocated = _money(get(reference, "allocated_amount"), "Allocated amount")
    except RefundError:
        return False
    return allocated == amount

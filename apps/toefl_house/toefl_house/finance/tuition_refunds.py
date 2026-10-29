"""Durable, auditable tuition refund request workflow — pure logic.

This module contains NO native accounting writes and NO Frappe import, so
its rules are testable without a site. The Frappe command layer lives in
``toefl_house.finance.tuition_refund_commands`` and reuses these rules
against live rows; the request record itself is the ``TH Tuition Refund
Request`` DocType (see its JSON next to the correction request DocType).

Approved business policy (Issue #115, Owner decision, 2026-10-28):
General Manager reviews each case, records supporting evidence, the reason
and the exact approved AFN amount; a DIFFERENT Finance Manager performs
the payout; no routine Course Owner approval is required; refunds never
exceed verified submitted tuition collections minus earlier completed
refunds; no automatic percentage, refund window or pro-rata amount is
authorized.

NATIVE BLOCKER — read before wiring a payout:
Pinned ERPNext 4048fb7 ``payment_entry.py`` provides NO Fees-aware refund
path, and a Payment Entry Pay/Student referencing Fees is actively the
wrong accounting:
- ``get_valid_reference_doctypes`` (line ~745) returns a tuple only for
  Customer / Shareholder / Employee / Supplier. For party_type Student it
  returns None, so ``validate_reference_documents`` returns early: Fees is
  neither approved nor rejected, and the party-association check
  (reference's student == payment party) is never run for Student.
- ``get_reference_details`` (line 2800) treats any non-invoice reference
  generically: outstanding = total - advance_paid. Fees has no
  advance_paid field, so the computed outstanding is the Fees grand_total,
  not its live outstanding_amount.
- ``validate_allocated_amount`` (line ~368, generic branch for non
  Customer/Supplier parties) throws when allocated_amount > outstanding.
  A fully paid Fees has outstanding 0, so ANY positive refund allocation
  against it throws at submit. A partially paid Fees (outstanding 400)
  would accept a 300 allocation — but ``add_party_gl_entries`` (line 1368)
  books a Pay as a DEBIT to the party (receivable) account, so the GL
  outstanding for the Fees (sum debit - sum credit against the voucher,
  ``gl_entry.py`` line ~410, Fees in ``OUTSTANDING_DOCTYPES``) INCREASES
  from 400 to 700: the student appears to owe MORE after being refunded,
  the Fees indicator flips back to Unpaid, and tuition income is never
  reversed. That is a new charge, not a refund.
- Pinned Education 93bc707 ``fees.py`` has no refund, credit or reversal
  document for Fees at all: on submit it debits receivable / credits
  income, and on cancel it reverses those GL entries in full. There is no
  partial-refund document to post.
Consequence: ``pay_tuition_refund`` runs every approval, separation,
ceiling and identity check and then REFUSES at the posting step with
``NativeRefundBlocked``. The request stays Approved (not Paid, not
consumed), so a future approved native mechanism can pay it without a
new approval round — but until such a mechanism exists, payout stays
disabled and no Journal Entry or other accounting workaround is invented
here. The ceiling and request state are the durable, auditable part that
can ship now; the money movement cannot, honestly, ship on this pinned
stack.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from toefl_house.setup_presets.tuition_refund_review import inspect_case_refund

CENT = Decimal("0.01")
STATUSES = ("Requested", "Approved", "Denied", "Paid")
APPROVER_ROLE = "General Manager"
PAYER_ROLE = "Finance Manager"
REQUESTER_ROLE = "Finance Officer"

NATIVE_BLOCKER = (
    "No native Fees refund mechanism exists on the pinned stack: a Payment "
    "Entry Pay/Student referencing Fees is not a Fees-aware refund (see the "
    "module docstring for the pinned-code evidence). Payout stays disabled; "
    "this request remains Approved and is not consumed."
)


class NativeRefundBlocked(ValueError):
    """Raised at the posting step of pay: no trustworthy native mechanism."""


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
    here would double-count. Denied requests count for nothing.
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


def pay_preflight(request, *, payer, payer_roles, collections, refunds):
    """All payout checks, in order, ending at the native posting blocker.

    Raises RefundError for every rule refusal. When every check passes it
    raises NativeRefundBlocked instead of returning: NativeRefundBlocked
    deliberately does NOT inherit RefundError, so callers can distinguish
    "rule refused" from "blocked by the native mechanism — request stays
    Approved and retryable". No caller may mark the request Paid, because
    no money moved.
    """
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

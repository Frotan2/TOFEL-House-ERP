"""Pure, fail-closed tuition refund ceiling preflight.

No native accounting writes happen here. Source rows MUST be read from the
authorized, transactionally consistent native ERPNext ledger by a separate
narrow Finance integration; do not treat arbitrary client JSON as evidence.

Tuition Fees are not Sales Invoice book returns. The existing native book
refund guard cannot be reused to post a tuition refund by itself.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

_CENT = Decimal("0.01")
_REQUIRED = ("student", "company", "fees", "approved_amount", "reason",
             "approved_by", "paying_user")


def _money(value, what):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(f"{what} must be a currency amount")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{what} must be a currency amount") from exc
    if not number.is_finite() or number < 0 or number > Decimal("999999999999.99"):
        raise ValueError(f"{what} must be a bounded nonnegative currency amount")
    try:
        valid_cents = number == number.quantize(_CENT)
    except InvalidOperation as exc:
        raise ValueError(f"{what} exceeds supported currency precision") from exc
    if not valid_cents:
        raise ValueError(f"{what} must have at most two decimals")
    return number


def _id(value, what):
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise ValueError(f"{what} must be a nonempty bounded identifier")
    return value.strip()


def _source(rows, *, student, company, fees, kind):
    if not isinstance(rows, list):
        raise ValueError(f"{kind} must be a complete native-ledger row list")
    seen = set()
    total = Decimal("0")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{kind} must contain native document facts")
        name = _id(row.get("payment_entry"), f"{kind} native payment reference")
        if name in seen:
            raise ValueError(f"Duplicate {kind} native payment reference")
        seen.add(name)
        if (row.get("student") != student or row.get("company") != company
                or row.get("fees") != fees):
            raise ValueError(f"{kind} includes an unrelated student/company/bill")
        status = row.get("docstatus")
        if isinstance(status, bool) or status not in (0, 1, 2):
            raise ValueError(f"{kind} native docstatus is unknown")
        amount = _money(row.get("amount"), f"{kind} amount")
        if status == 1:
            if amount <= 0:
                raise ValueError(f"Submitted {kind} amount must be positive")
            total += amount
        # Draft (0) and cancelled (2) records do not move the paid ceiling.
    return total, seen


def inspect_case_refund(request: dict, collections: list, refunds: list,
                        *, native_evidence_complete: bool = False) -> dict:
    """Check an OWNER-approved case without authorizing a real payout.

    The caller MUST independently establish all source documents are genuine,
    fully scoped to Company/Branch, and locked/transactionally consistent.
    The proposed refund is not posted by this function or its callers.
    """
    if not native_evidence_complete:
        raise ValueError("Complete authorized native ledger evidence is mandatory")
    if not isinstance(request, dict) or any(key not in request for key in _REQUIRED):
        raise ValueError("Refund case is incomplete")
    student = _id(request["student"], "Student")
    company = _id(request["company"], "Company")
    fees = _id(request["fees"], "Original Fees")
    approver = _id(request["approved_by"], "Approving General Manager")
    payer = _id(request["paying_user"], "Finance Manager")
    if approver == payer:
        raise ValueError("The approving manager must not execute their own refund")
    if request.get("approval_status") != "Approved":
        raise ValueError("Refund must be approved before Finance may consider payment")
    reason = request["reason"]
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ValueError("A bounded written refund decision reason is mandatory")
    amount = _money(request["approved_amount"], "Approved refund")
    if amount <= 0:
        raise ValueError("Approved refund must be greater than zero")
    paid, source_ids = _source(
        collections, student=student, company=company, fees=fees, kind="Collections")
    repaid, refund_ids = _source(
        refunds, student=student, company=company, fees=fees, kind="Refunds")
    if source_ids & refund_ids:
        raise ValueError("A receipt cannot also appear as a refund")
    if paid <= 0:
        raise ValueError("No verified submitted tuition receipt to refund")
    if repaid > paid:
        raise ValueError("Posted refunds exceed verified original tuition collections")
    available = paid - repaid
    if amount > available:
        raise ValueError("Approved amount exceeds collected tuition less earlier refunds")
    return {
        "status": "POLICY_CEILING_CHECK_ONLY",
        "student": student,
        "company": company,
        "fees": fees,
        "approved_amount_afn": str(amount),
        "verified_collections_afn": str(paid),
        "prior_refunds_afn": str(repaid),
        "remaining_refundable_afn": str(available),
        "remaining_after_proposal_afn": str(available - amount),
        "approved_by": approver,
        "paying_user": payer,
        "payment_permitted": False,
        "live_native_fees_refund_integration": "NOT_YET_VERIFIED",
    }

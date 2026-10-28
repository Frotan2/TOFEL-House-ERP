"""Fail-closed native Payment Entry guard for Student cash disbursement.

The system currently has receipted native Fees/Student collections but no
approved, independently verified native tuition refund payout workflow.
Do not allow a directly entered 'Pay' to party_type='Student' to bypass
General Manager approval and independent Finance Manager authorization.

Cancellation of *existing* submitted Student Pay documents is explicitly
allowed so correcting pre-existing legacy transactions is not blocked.
No new Student payout may be created/edited/submitted through native UI
until the separately audited tuition refund command exists and is accepted.
This pure guard grants no permission or operational approval.

NARROW EXCEPTION (Issue #115): a Student Pay is permitted ONLY while the
pay_tuition_refund command holds an active refund-payment context AND the
payment document matches that context exactly (party, company, single Fees
reference, amount equal to the live Approved request's approved amount).
The context is set by the command layer alone, cleared in a finally block,
and never set by UI/API code. Outside that context — including inside any
other command — every new Student Pay is still denied. Because the pinned
native Fees refund mechanism does not exist (see
toefl_house.finance.tuition_refunds.NATIVE_BLOCKER), the pay command
currently refuses before creating any Payment Entry, so this exception is
not reachable for a real payout today; it is the guard half of the
designed exception, proven by tests, awaiting a verified native mechanism.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

_ACTIVE_REFUND = ContextVar("toefl_house_active_refund_payment", default=None)


@contextmanager
def refund_payment_context(details):
    """Hold one live Approved refund's exact payment facts for the guard.

    ``details`` must be a dict with student, company, fees and amount
    (a string with at most two decimals). The guard matches a Payment
    Entry against these facts; anything else stays denied.
    """
    token = _ACTIVE_REFUND.set(dict(details) if details else None)
    try:
        yield
    finally:
        _ACTIVE_REFUND.reset(token)


def active_refund_payment():
    """The currently active refund-payment facts, or None."""
    return _ACTIVE_REFUND.get()


def _field(payment, key):
    if isinstance(payment, dict):
        return payment.get(key)
    return getattr(payment, key, None)


def _payment_matches_context(payment, context):
    if not context:
        return False
    if _field(payment, "party") != context.get("student"):
        return False
    if _field(payment, "company") != context.get("company"):
        return False
    amount = _field(payment, "paid_amount")
    if amount is None:
        return False
    try:
        from decimal import Decimal
        paid = Decimal(str(amount))
        approved = Decimal(str(context.get("amount")))
    except Exception:
        return False
    if paid != approved:
        return False
    references = _field(payment, "references") or []
    if len(references) != 1:
        return False
    reference = references[0]
    if _field(reference, "reference_doctype") != "Fees":
        return False
    if _field(reference, "reference_name") != context.get("fees"):
        return False
    allocated = _field(reference, "allocated_amount")
    if allocated is None:
        return False
    try:
        return Decimal(str(allocated)) == approved
    except Exception:
        return False


def student_pay_write_allowed(payment_type, party_type, method=None, payment=None):
    if payment_type != "Pay" or party_type != "Student":
        return True
    if method == "before_cancel":
        return True
    # Narrow, context-bound exception only: the live pay_tuition_refund
    # command holds the exact Approved request facts, and this payment
    # must match them field for field. Every other Student Pay is denied.
    if payment is not None and _payment_matches_context(payment, _ACTIVE_REFUND.get()):
        return True
    return False

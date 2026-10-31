"""Enforce tuition approval containment on the native Journal Entry surface."""
import frappe

from toefl_house.finance.student_payout_policy import student_journal_write_allowed
from toefl_house.security import require_operational


def guard_student_journal(doc, method=None):
    require_operational()
    from toefl_house.finance.tuition_refund_native import protect_bound_artifact, exact_native_write_allowed, lock_cash_accounts

    if exact_native_write_allowed(doc, method):
        return
    protect_bound_artifact(doc)
    lock_cash_accounts([row.get("account") for row in (doc.get("accounts") or [])])
    if not student_journal_write_allowed(doc.get("accounts") or [], method):
        raise frappe.ValidationError(
            "Student/Fees Journal Entries require a qualified tuition refund workflow. "
            "Direct Student journals cannot bypass General Manager authorization "
            "and independent Finance payout.")

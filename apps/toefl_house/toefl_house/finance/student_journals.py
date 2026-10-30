"""Enforce tuition approval containment on the native Journal Entry surface."""
import frappe

from toefl_house.finance.student_payout_policy import student_journal_write_allowed
from toefl_house.security import require_operational


def guard_student_journal(doc, method=None):
    require_operational()
    if not student_journal_write_allowed(doc.get("accounts") or [], method):
        raise frappe.ValidationError(
            "Student/Fees Journal Entries require a qualified tuition refund workflow. "
            "Direct Student journals cannot bypass General Manager authorization "
            "and independent Finance payout.")

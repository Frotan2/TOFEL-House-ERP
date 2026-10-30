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
"""
from __future__ import annotations


def student_pay_write_allowed(payment_type, party_type, method=None):
    if payment_type != "Pay" or party_type != "Student":
        return True
    return method == "before_cancel"


def student_journal_write_allowed(accounts, method=None):
    """Contain Student/Fees journals until the paired refund is qualified.

    Payment Entry containment alone cannot protect the same receivable/cash
    accounts from native Journal Entry writes. Legacy cancellation remains
    subject to native permissions; payroll and operating journals are unaffected.
    """
    protected = any(row.get("party_type") == "Student"
                    or row.get("reference_type") == "Fees" for row in accounts)
    return not protected or method == "before_cancel"

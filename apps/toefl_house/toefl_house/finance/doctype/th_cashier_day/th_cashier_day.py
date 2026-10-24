"""Controller for TH Cashier Day: the guarded command is the only write path.

A cashier day close is a **control record, never a ledger entry**: it states
what the native general ledger says the drawer should hold, what the cashier
counted, and the difference. It posts nothing, corrects nothing and can never
stand in for a Payment Entry or a Journal Entry.

Writes arrive exclusively through ``toefl_house.finance.cashier``'s guarded
command (Finance Officer role, idempotent receipt, audited); a native form,
REST call or import that tries to create, submit, cancel or edit after submit
is refused here — on every seam, because pinned Frappe fires ``validate`` only
for save/submit while cancel and post-submit edits take their own paths.
"""
import frappe

from toefl_house.finance import cashier

SEAMS = ("validate", "before_cancel", "before_update_after_submit")


class THCashierDay(frappe.model.document.Document):
    def validate(self):
        guard(self)


def guard(doc, method=None):
    """Refuse a cashier close raised outside the guarded command."""
    cashier.guard(doc, method)

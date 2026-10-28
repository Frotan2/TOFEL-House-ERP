"""Controller for TH Configuration Operation: receipts are immutable.

Idempotency receipts for the guarded configuration commands. No role
holds any write permission: only the commands write them (inside the
bound-authority gate and the command context), and a Completed receipt
can never change again. The controller refuses any save attempted
outside a configuration command first, so no native, API, or import
path can forge or mutate a receipt.
"""
import frappe
from frappe.model.document import Document

from toefl_house.configuration import rules as foundation


class THConfigurationOperation(Document):
    def validate(self):
        validate(self)


def validate(doc, method=None):
    try:
        foundation.assert_command_context(
            "Configuration operation receipts are written only by the "
            "guarded configuration commands")
    except ValueError as exc:
        raise frappe.PermissionError(str(exc)) from exc
    if doc.status not in ("Applying", "Complete"):
        raise frappe.ValidationError("Operation status must be Applying or Complete")
    before = doc.get_doc_before_save()
    if before and before.status == "Complete":
        raise frappe.PermissionError("Completed configuration operation receipts are immutable")

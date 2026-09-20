"""Controller for TH Configuration Operation: receipts are immutable.

Idempotency receipts for the guarded configuration commands. No role
holds any write permission: only the commands write them (inside the
bound-authority gate), and a Completed receipt can never change again.
Governance boundary: no command-context or site-mode machinery — the
same boundary as the configuration the receipts trail.
"""
import frappe
from frappe.model.document import Document


class THConfigurationOperation(Document):
    def validate(self):
        validate(self)


def validate(doc, method=None):
    if doc.status not in ("Applying", "Complete"):
        raise frappe.ValidationError("Operation status must be Applying or Complete")
    before = doc.get_doc_before_save()
    if before and before.status == "Complete":
        raise frappe.PermissionError("Completed configuration operation receipts are immutable")

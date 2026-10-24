import frappe
from frappe.model.document import Document
class THGuardianConsent(Document):
    def validate(self):
        if self.status not in ("Pending", "Active", "Revoked", "Expired"):
            frappe.throw("Invalid consent status")
        if self.evidence_type not in ("Link","Attachment","Both"):
            frappe.throw("Invalid evidence_type")
def validate(doc, method=None):
    doc.validate()

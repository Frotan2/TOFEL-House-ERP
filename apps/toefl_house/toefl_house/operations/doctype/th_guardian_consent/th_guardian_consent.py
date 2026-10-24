import frappe
from frappe.model.document import Document
class THGuardianConsent(Document):
    def validate(self):
        if self.status not in ("Pending", "Active", "Revoked", "Expired"):
            frappe.throw("Invalid consent status")
        if self.evidence_type not in ("Link","Attachment","Both"):
            frappe.throw("Invalid evidence_type")
        if self.status == "Active" and (not self.approved_by or not self.approved_on):
            frappe.throw("Active consent requires independently recorded staff approval")
def validate(doc, method=None):
    doc.validate()

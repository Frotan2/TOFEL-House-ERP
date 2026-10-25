import frappe
from frappe.model.document import Document
class THPortalAnnouncement(Document):
    pass
def validate(doc, method=None):
    if doc.status not in ("Draft","Published","Retired"):
        frappe.throw("Invalid status")

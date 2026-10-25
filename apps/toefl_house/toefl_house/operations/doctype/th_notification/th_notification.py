"""Controller: delivery state machine is the ONLY write path for status.

Raw inserts are guarded: notifications start queued and only move through
the explicit states via operations.notifications helpers.
"""
import frappe
from frappe.model.document import Document

VALID_TRANSITIONS = {
    "queued": ("delivered", "failed"),
    "delivered": ("acknowledged",),
    "failed": ("delivered", "failed"),
    "acknowledged": (),
}

class THNotification(Document):
    def validate(self):
        if self.status not in VALID_TRANSITIONS:
            frappe.throw("Invalid notification status")
        # New docs must start queued
        if self.is_new() and self.status != "queued":
            frappe.throw("New notifications must start in queued state")
        if self.event_type not in ("overdue_tuition","pending_academic_approval","incomplete_attendance","class_change","low_book_stock","scheduling_conflict","system_alert"):
            frappe.throw("Unknown event_type")
        if self.severity not in ("info","warning","critical"):
            frappe.throw("Invalid severity")
        if self.channel not in ("Dashboard","Email","SMS","WhatsApp"):
            frappe.throw("Invalid channel")

def validate(doc, method=None):
    doc.validate()

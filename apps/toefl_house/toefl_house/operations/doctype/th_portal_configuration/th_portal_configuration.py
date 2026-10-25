"""Owner-configured portal and communication access is command-only."""
import frappe
from frappe.model.document import Document
from toefl_house.configuration import rules as foundation


class THPortalConfiguration(Document):
    def validate(self):
        validate(self)


def validate(doc, method=None):
    if foundation.active_command() != "set_portal_flags":
        raise frappe.PermissionError(
            "Portal and channel access can only change through the "
            "audited Course Owner configuration action")
    for field in ("student_portal_enabled", "guardian_portal_enabled",
                  "dashboard_enabled", "email_enabled", "sms_enabled",
                  "whatsapp_enabled"):
        value = doc.get(field)
        if value not in (0, 1, False, True, None):
            raise frappe.ValidationError("Portal enablement must be a boolean")

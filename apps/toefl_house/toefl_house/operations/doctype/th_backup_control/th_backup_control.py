"""Backup On/Off is a command-only owner setting, never a direct Desk form edit."""
import re

import frappe
from frappe.model.document import Document
from toefl_house.configuration import rules as foundation


class THBackupControl(Document):
    def validate(self):
        validate(self)


def validate(doc, method=None):
    if foundation.active_command() != "set_backup_enabled":
        raise frappe.PermissionError(
                "Only the audited Course Owner Backup On/Off action may change this setting")
    if doc.get("enabled") not in (0, 1, False, True):
        raise frappe.ValidationError("Backup On/Off must be a boolean")
        if not re.fullmatch(r"[0-9a-f]{32}", str(doc.get("switch_nonce") or "")):
        raise frappe.ValidationError("A fresh switch identity is required")
    if not doc.get("changed_by") or not doc.get("changed_at"):
        raise frappe.ValidationError("Backup changes must record the acting owner and time")

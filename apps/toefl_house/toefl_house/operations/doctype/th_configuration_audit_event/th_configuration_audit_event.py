"""Controller for TH Configuration Audit Event: the trail is append-only.

One hash-chained event per configuration command (actor, operation,
action, target, before/after hashes). No role holds any write
permission; events are written once by the commands and can never be
edited afterwards. Governance boundary: no command-context or site-mode
machinery — the same boundary as the configuration trailed here.
"""
import frappe
from frappe.model.document import Document


class THConfigurationAuditEvent(Document):
    def validate(self):
        validate(self)


REQUIRED = ("actor", "operation", "action", "target", "after_hash")


def validate(doc, method=None):
    if doc.get_doc_before_save() is not None:
        raise frappe.PermissionError("Configuration audit events are append-only")
    for field in REQUIRED:
        if not doc.get(field):
            raise frappe.ValidationError(
                f"Configuration audit events require {field.replace('_', ' ')}")

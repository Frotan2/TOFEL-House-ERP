"""Controller for TH Configuration Audit Event: the trail is append-only.

One hash-chained event per configuration command (actor, operation,
action, target, before/after hashes). No role holds any write
permission; the commands write each event once, inside the
bound-authority gate and the command context, and it can never be
edited afterwards. The controller refuses any save attempted outside a
configuration command first, so no native, API, or import path can
forge or rewrite the trail.
"""
import frappe
from frappe.model.document import Document

from toefl_house.configuration import rules as foundation


class THConfigurationAuditEvent(Document):
    def validate(self):
        validate(self)


REQUIRED = ("actor", "operation", "action", "target", "after_hash")


def validate(doc, method=None):
    try:
        foundation.assert_command_context(
            "Configuration audit events are written only by the guarded "
            "configuration commands")
    except ValueError as exc:
        raise frappe.PermissionError(str(exc)) from exc
    if doc.get_doc_before_save() is not None:
        raise frappe.PermissionError("Configuration audit events are append-only")
    for field in REQUIRED:
        if not doc.get(field):
            raise frappe.ValidationError(
                f"Configuration audit events require {field.replace('_', ' ')}")

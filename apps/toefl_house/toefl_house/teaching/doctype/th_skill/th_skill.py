"""Controller for TH Skill: configurable teaching-skill master.

Skills are central owner configuration (Course Owner writes; operational
roles read). Codes are stable identity; titles are presentation; Active
skills can be used in new teaching assignments and contracts; Retired
skills are preserved for historical references on existing records but
cannot be selected for new ones. Deletion and rename are not permitted
for any role — retirement is the only lifecycle action, and once retired
a skill can never be reactivated.
"""
import frappe
from frappe import _
from frappe.model.document import Document

from toefl_house.academic import rules as code_rules


class THSkill(Document):
    def validate(self):
        validate(self)

    def before_save(self):
        before_save(self)

    def on_trash(self):
        raise frappe.PermissionError("Skills cannot be deleted; retire them instead")

    def before_rename(self, *args, **kwargs):
        raise frappe.PermissionError("Skill codes are stable identity and cannot be renamed")


# Allowed status transitions: only Active -> Retired. Once retired a skill
# stays retired (no reactivation without an explicit Owner decision and a
# new code, to preserve compensation history).
_ALLOWED_TRANSITIONS = {("Active", "Retired")}


def validate(doc, method=None):
    code_rules.validate_code(doc.code or "")
    code_rules.validate_title(doc.title or "", "Skill title")
    if doc.status not in ("Active", "Retired"):
        frappe.throw(_("Skill status must be Active or Retired"))
    # Code immutability: the code IS the identity and never changes after
    # creation (we enforce this even though the field is set_only_once,
    # because the field-level flag is a client-side hint).
    before = doc.get_doc_before_save()
    if before is not None and before.code != doc.code:
        frappe.throw(_("Skill code is the stable identifier and cannot be changed"))
    if before is not None:
        pair = (before.status, doc.status)
        if before.status != doc.status and pair not in _ALLOWED_TRANSITIONS:
            frappe.throw(_(f"Illegal skill status transition: {before.status} → {doc.status}. "
                           "Only Active → Retired is allowed."))
        if doc.status == "Retired":
            # Title/description may still be edited for clarity while retired,
            # but no other substantive field changes occur. set_by/set_on stay
            # frozen from original creation.
            if before.set_by != doc.set_by or str(before.set_on) != str(doc.set_on):
                frappe.throw(_("Retired skill audit metadata is immutable"))


def before_save(doc, method=None):
    """Auto-record set_by / set_on on first insert."""
    if not doc.get("__islocal"):
        return
    if not doc.set_by:
        doc.set_by = frappe.session.user
    if not doc.set_on:
        doc.set_on = frappe.utils.now_datetime()

"""Controller for TH Capacity Objective: commands are the ONLY write path.

The guarded toefl_house.operations.capacity_objective commands mutate this master
exclusively, from inside the command context. The Course Owner holds
native write permission only so the form stays reachable; this
controller refuses any save attempted outside a configuration command —
native form, REST API, or data import — so no version can ever bypass
its mandatory change reason and hash-chained audit. Inside a command,
the rules below bind on every write.
"""
import frappe
from frappe import _
from frappe.model.document import Document

from toefl_house.academic import rules
from toefl_house.configuration import rules as foundation
from toefl_house.operations import capacity_objective


class THCapacityObjective(Document):
    def validate(self):
        validate(self)


def validate(doc, method=None):
    # Authorization first: outside a configuration command this is a
    # native/API/import write, refused in business language before any
    # data check runs. Inside a command the rules below bind as before.
    try:
        foundation.assert_command_context(_(
            "Capacity objectives change only through the guarded Course "
            "Owner commands, so every change keeps its reason and audit "
            "trail"))
    except ValueError as exc:
        raise frappe.PermissionError(str(exc)) from exc
    rules.validate_code(doc.code or "")
    rules.validate_title(doc.title or "", "Capacity objective title")
    if doc.status not in ("Active", "Retired"):
        frappe.throw(_("Status must be Active or Retired"))
    for row in doc.get("versions") or []:
        rules.parse_date(str(row.get("effective_from") or ""),
                         "Version effective date")
        foundation.validate_change_reason(row.get("reason") or "",
                                          "Version reason")
        capacity_objective.validate_terms(
            row.get("concurrent_users_target"),
            row.get("document_scale_target"),
            row.get("read_share_percent"),
            row.get("availability_target_percent"))
    _assert_versions_sound(doc)


def _assert_versions_sound(doc):
    effective = [str(row.get("effective_from") or "")
                 for row in (doc.get("versions") or [])]
    if len(effective) != len(set(effective)):
        frappe.throw(_(
            "Two capacity objective versions cannot share one effective date"))
    for row in (doc.get("versions") or []):
        if row.get("superseded_on") and str(row.get("superseded_on")) <= str(row.get("effective_from") or ""):
            frappe.throw(_(
                "A version's closed date must fall after its effective date"))

"""Controller for TH Assessment Policy: commands are the ONLY write path.

The guarded toefl_house.academic assessment commands mutate this master
exclusively, from inside the command context. The Course Owner holds
native write permission only so the form stays reachable; this
controller refuses any save attempted outside a configuration command —
native form, REST API, or data import — so no version can ever bypass
its mandatory change reason and hash-chained audit. Inside a command,
the D1 reference rules below bind on every write.
"""
import frappe
from frappe import _
from frappe.model.document import Document

from toefl_house.academic import rules
from toefl_house.configuration import rules as foundation


class THAssessmentPolicy(Document):
    def validate(self):
        validate(self)


def validate(doc, method=None):
    # Authorization first: outside a configuration command this is a
    # native/API/import write, refused in business language before any
    # data check runs. Inside a command the rules below bind as before.
    try:
        foundation.assert_command_context(_(
            "Assessment policies change only through the guided Course "
            "Owner actions, so every change keeps its reason and audit "
            "trail — please use the desk action instead of editing here"))
    except ValueError as exc:
        raise frappe.PermissionError(str(exc)) from exc
    rules.validate_code(doc.code or "")
    rules.validate_title(doc.title or "", "Assessment policy title")
    if not doc.family:
        frappe.throw(_("An assessment policy needs its program family"))
    if doc.status not in ("Active", "Retired"):
        frappe.throw(_("Status must be Active or Retired"))
    for row in doc.get("versions") or []:
        rules.parse_date(str(row.get("effective_from") or ""),
                         "Version effective date")
        foundation.validate_change_reason(row.get("reason") or "",
                                          "Version reason")
        rules.validate_policy_facets(
            {facet: row.get(facet) for facet in rules.ASSESSMENT_FACETS})
    _assert_versions_sound(doc)


def _assert_versions_sound(doc):
    effective = [str(row.get("effective_from") or "")
                 for row in (doc.get("versions") or [])]
    if len(effective) != len(set(effective)):
        frappe.throw(_("Two assessment policy versions cannot share one effective date"))
    for row in (doc.get("versions") or []):
        if row.get("superseded_on") and str(row["superseded_on"]) <= str(row.get("effective_from") or ""):
            frappe.throw(_("A version's closed date must fall after its effective date"))

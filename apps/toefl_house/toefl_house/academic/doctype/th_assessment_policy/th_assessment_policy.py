"""Controller for TH Assessment Policy: the D1 reference rules bind on EVERY write path.

The guarded toefl_house.academic assessment commands are the only
sanctioned mutation surface, but the Course Owner does hold native write
permission on this master. These hooks make the configuration integrity
rules unconditional: even a native-form edit cannot break identity,
close or rewrite version history, share one effective date between two
versions, or save a version without its mandatory change reason.
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
    _assert_versions_sound(doc)


def _assert_versions_sound(doc):
    effective = [str(row.get("effective_from") or "")
                 for row in (doc.get("versions") or [])]
    if len(effective) != len(set(effective)):
        frappe.throw(_("Two assessment policy versions cannot share one effective date"))
    for row in (doc.get("versions") or []):
        if row.get("superseded_on") and str(row["superseded_on"]) <= str(row.get("effective_from") or ""):
            frappe.throw(_("A version's closed date must fall after its effective date"))

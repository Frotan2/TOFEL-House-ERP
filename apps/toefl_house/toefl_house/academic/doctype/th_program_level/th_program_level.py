"""Controller for TH Program Level: the rules bind on EVERY write path.

The guarded toefl_house.academic commands are the only sanctioned mutation
surface, but the Course Owner does hold native write permission on this
master. These hooks make the configuration integrity rules unconditional:
even a native-form edit cannot break sibling sequence uniqueness, close or
rewrite version history, or detach the native anchor.
"""
import frappe
from frappe import _

from toefl_house.academic import rules


def validate(doc, method=None):
    rules.validate_code(doc.code or "")
    rules.validate_title(doc.title or "", "Level title")
    rules.validate_sequence(doc.sequence)
    for row in doc.get("durations") or []:
        rules.validate_duration_value(row.get("duration_value"), row.get("duration_unit"))
        rules.parse_date(str(row.get("effective_from") or ""), "Version effective date")
    _assert_versions_monotone(doc)
    if not doc.native_program and not doc.get("__islocal"):
        frappe.throw(_("A level cannot exist without its native program anchor"))


def _assert_versions_monotone(doc):
    effective = [str(row.get("effective_from") or "")
                 for row in (doc.get("durations") or [])]
    if len(effective) != len(set(effective)):
        frappe.throw(_("Two duration versions cannot share one effective date"))
    for row in (doc.get("durations") or []):
        if row.get("superseded_on") and str(row["superseded_on"]) <= str(row.get("effective_from") or ""):
            frappe.throw(_("A version's closed date must fall after its effective date"))


def before_save(doc, method=None):
    """Sibling sequence uniqueness (needs the database)."""
    siblings = frappe.db.get_all(
        "TH Program Level",
        filters={"family": doc.family, "name": ("!=", doc.name)},
        fields=["code", "sequence"], limit=0)
    taken = {int(row["sequence"]) for row in siblings
             if str(row.get("sequence") or "").lstrip("-").isdigit()}
    if int(doc.sequence or 0) in taken:
        frappe.throw(_(f"Level position {doc.sequence} is already taken in this program"))

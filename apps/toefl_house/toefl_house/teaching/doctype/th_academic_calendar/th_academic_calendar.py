"""Controller for TH Academic Calendar: commands are the ONLY write path.

Calendars are governance configuration: the guarded
toefl_house.teaching.calendars commands write them inside the configuration
command context, and this controller refuses any native/API/import save. The
calendar never restates an Academic Year or a Student Group — it only answers
whether teaching may happen on a date.
"""
import frappe
from frappe import _
from frappe.model.document import Document

from toefl_house.academic import rules
from toefl_house.configuration import rules as foundation
from toefl_house.teaching import calendars


class THAcademicCalendar(Document):
    def validate(self):
        validate(self)


def validate(doc, method=None):
    try:
        foundation.assert_command_context(_(
            "Academic calendars change only through the guarded Course Owner "
            "commands, so every change keeps its reason and audit trail"))
    except ValueError as exc:
        raise frappe.PermissionError(str(exc)) from exc
    rules.validate_code(doc.code or "")
    rules.validate_title(doc.title or "", "Calendar title")
    if doc.status not in ("Active", "Retired"):
        frappe.throw(_("Status must be Active or Retired"))
    if doc.academic_year and not frappe.db.exists("Academic Year", doc.academic_year):
        frappe.throw(_("Unknown academic year"))
    if doc.branch and not frappe.db.exists("Branch", doc.branch):
        frappe.throw(_("Unknown branch"))
    try:
        calendars.normalize_days(doc.get("days") or [])
    except ValueError as exc:
        frappe.throw(str(exc))

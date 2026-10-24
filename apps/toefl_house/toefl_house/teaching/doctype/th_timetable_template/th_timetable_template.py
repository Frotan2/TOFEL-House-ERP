"""Controller for TH Timetable Template: commands are the ONLY write path.

A template is the weekly pattern configuration; the guarded
toefl_house.teaching.timetables commands write it inside the configuration
command context and this controller refuses any native/API/import save. The
template never creates a session by itself — sessions are native Course
Schedule rows produced by the generate-timetable command.
"""
import frappe
from frappe import _
from frappe.model.document import Document

from toefl_house.academic import rules
from toefl_house.configuration import rules as foundation
from toefl_house.teaching import timetables


class THTimetableTemplate(Document):
    def validate(self):
        validate(self)


def validate(doc, method=None):
    try:
        foundation.assert_command_context(_(
            "Timetable templates change only through the guarded Course Owner "
            "commands, so every change keeps its reason and audit trail"))
    except ValueError as exc:
        raise frappe.PermissionError(str(exc)) from exc
    rules.validate_code(doc.code or "")
    rules.validate_title(doc.title or "", "Timetable template title")
    if doc.status not in ("Active", "Retired"):
        frappe.throw(_("Status must be Active or Retired"))
    if doc.program and not frappe.db.exists("Program", doc.program):
        frappe.throw(_("Unknown program"))
    if doc.branch and not frappe.db.exists("Branch", doc.branch):
        frappe.throw(_("Unknown branch"))
    try:
        timetables.validate_slots([row.as_dict() for row in (doc.get("slots") or [])])
    except ValueError as exc:
        frappe.throw(str(exc))

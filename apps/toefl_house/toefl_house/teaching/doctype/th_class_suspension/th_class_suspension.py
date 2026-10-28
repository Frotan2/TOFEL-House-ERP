"""Controller for TH Class Suspension: a bounded pause, never a roster edit.

The suspension window and target are immutable; the record ends exactly once
(Active to Ended) and stays in history. Ending it early is the only mutation
a resumed row allows; the roster row it paused is untouched throughout.
"""
import frappe
from toefl_house.controllers import ProtectedRecord
from toefl_house.security import teaching_command_active

FACT_FIELDS = ("scope", "student_group", "student", "from_date", "until_date",
               "reason", "requested_by", "requested_on", "policy_effective_from")


class THClassSuspension(ProtectedRecord):
    def validate(self):
        super().validate()
        if not teaching_command_active(self.doctype):
            raise frappe.PermissionError(
                "Class suspensions change only through the guarded suspension commands")
        before = self.get_doc_before_save()
        if before is None:
            if self.status != "Active":
                raise frappe.ValidationError("A new suspension must start as Active")
            if self.scope == "Student" and not self.student:
                raise frappe.ValidationError("A student suspension names the student")
            if self.scope == "Class" and self.student:
                raise frappe.ValidationError("A class suspension names no student")
            if not self.requested_by or not self.requested_on:
                raise frappe.ValidationError("A suspension records its requester")
            return
        for field in FACT_FIELDS:
            if before.get(field) != self.get(field):
                raise frappe.PermissionError(f"Suspension fact {field} is immutable")
        if (before.status, self.status) != ("Active", "Ended"):
            raise frappe.PermissionError("A suspension can only be ended")
        if not self.ended_by or not self.ended_on:
            raise frappe.ValidationError("Ending a suspension records who and when")

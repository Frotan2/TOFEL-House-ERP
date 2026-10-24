"""Controller for TH Capacity Override: one approval, one seat, one use.

The approval facts (class, student, seats, reason, approver) are immutable;
the status moves Approved to Used, Revoked or Expired and never back. A used
override cannot be reused by a later admission because the admitting command
re-reads the row under lock and the record is marked Used in the same
transaction.
"""
import frappe
from toefl_house.controllers import ProtectedRecord
from toefl_house.security import teaching_command_active

FACT_FIELDS = ("student_group", "student", "seats", "reason", "approved_by",
               "approved_on", "expires_on", "policy_effective_from")
TRANSITIONS = {("Approved", "Used"), ("Approved", "Revoked"),
               ("Approved", "Expired")}


class THCapacityOverride(ProtectedRecord):
    def validate(self):
        super().validate()
        if not teaching_command_active(self.doctype):
            raise frappe.PermissionError(
                "Capacity overrides change only through the guarded override commands")
        before = self.get_doc_before_save()
        if before is None:
            if self.status != "Approved":
                raise frappe.ValidationError("A new override must start as Approved")
            if not self.approved_by or not self.approved_on:
                raise frappe.ValidationError("An override records its approver")
            return
        for field in FACT_FIELDS:
            if before.get(field) != self.get(field):
                raise frappe.PermissionError(f"Override fact {field} is immutable")
        if (before.status, self.status) not in TRANSITIONS:
            raise frappe.PermissionError(
                f"Illegal override transition: {before.status} to {self.status}")
        if self.status == "Used" and not self.used_on:
            raise frappe.ValidationError("A used override records when it was used")
        if self.status == "Revoked" and not (self.revoked_on and self.revocation_reason):
            raise frappe.ValidationError(
                "A revoked override records when and why it was revoked")

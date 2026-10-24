"""Controller for TH Class Waiting List: queued demand, never a roster row.

A waiting entry reserves nothing by itself — only an Offered entry with an
unexpired offer holds a seat. Facts set at request time are immutable; the
status machine is one-way and terminal states never reopen, so an entry
cannot be "un-withdrawn" or silently re-admitted. Only the guarded waiting
commands write rows.
"""
import frappe
from toefl_house.controllers import ProtectedRecord
from toefl_house.security import teaching_command_active

FACT_FIELDS = ("student", "student_group", "priority", "requested_by",
               "requested_on", "policy_effective_from")
TRANSITIONS = {
    ("Waiting", "Offered"), ("Waiting", "Admitted"),
    ("Waiting", "Withdrawn"), ("Waiting", "Expired"),
    ("Offered", "Admitted"), ("Offered", "Withdrawn"), ("Offered", "Expired"),
}


class THClassWaitingList(ProtectedRecord):
    def validate(self):
        super().validate()
        if not teaching_command_active(self.doctype):
            raise frappe.PermissionError(
                "Waiting-list entries change only through the guarded waiting commands")
        before = self.get_doc_before_save()
        if before is None:
            if self.status not in ("Waiting", "Offered"):
                raise frappe.ValidationError(
                    "A new waiting-list entry starts as Waiting or Offered")
            if not self.requested_by or not self.requested_on:
                raise frappe.ValidationError("A waiting-list entry records its requester")
            return
        for field in FACT_FIELDS:
            if before.get(field) != self.get(field):
                raise frappe.PermissionError(
                    f"Waiting-list fact {field} is immutable")
        if (before.status, self.status) not in TRANSITIONS:
            raise frappe.PermissionError(
                f"Illegal waiting-list transition: {before.status} to {self.status}")
        if self.status == "Offered":
            if not self.offered_by or not self.offered_on or not self.offer_expires_on:
                raise frappe.ValidationError(
                    "An offer records who offered it, when, and until when it holds")
        if self.status == "Admitted" and not self.admitted_on:
            raise frappe.ValidationError("An admitted entry records when it was admitted")

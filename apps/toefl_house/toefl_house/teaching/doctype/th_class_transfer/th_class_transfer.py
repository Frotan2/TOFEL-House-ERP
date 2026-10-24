"""Controller for TH Class Transfer: one request, one independent decision.

Facts captured at request time are immutable; a decision is one-shot and
terminal. Only the transfer commands (inside ``toefl_house.teaching.transfers``)
may insert or change a row, and ``require_command`` refuses every other write
path — native form, REST, import or script — even with ignore_permissions.
"""
import frappe
from toefl_house.controllers import ProtectedRecord
from toefl_house.security import teaching_command_active

FACT_FIELDS = ("student", "from_group", "to_group", "transfer_kind",
               "effective_date", "reason", "requested_by", "requested_on",
               "pinned_effective_from", "pinned_approver_role",
               "eligibility_json", "preserved_json")
DECISIONS = {("Requested", "Executed"), ("Requested", "Denied"),
             ("Requested", "Cancelled")}


class THClassTransfer(ProtectedRecord):
    def validate(self):
        super().validate()
        if not teaching_command_active(self.doctype):
            raise frappe.PermissionError(
                "Class transfers change only through the guarded transfer commands")
        before = self.get_doc_before_save()
        if before is None:
            if self.status != "Requested":
                raise frappe.ValidationError("A new transfer must start as Requested")
            if not self.requested_by or not self.requested_on:
                raise frappe.ValidationError("A transfer request records its requester")
            return
        for field in FACT_FIELDS:
            if before.get(field) != self.get(field):
                raise frappe.PermissionError(
                    f"Transfer fact {field} is immutable; request a new transfer instead")
        if before.status == self.status:
            raise frappe.PermissionError("Transfer decisions are one-shot")
        if (before.status, self.status) not in DECISIONS:
            raise frappe.PermissionError("Illegal transfer transition")
        if self.status == "Executed":
            if not self.approved_by or not self.executed_on or not self.decided_on:
                raise frappe.ValidationError(
                    "An executed transfer records its approver and execution time")
        elif self.status == "Denied":
            if not self.approved_by or not self.decided_on or not self.denial_reason:
                raise frappe.ValidationError(
                    "A denied transfer records its decision and reason")
        elif self.status == "Cancelled":
            if not self.decided_on or not self.denial_reason:
                raise frappe.ValidationError(
                    "A cancelled transfer records its cancellation reason")

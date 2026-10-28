"""Verified guardian consent — evidence and approval are separate authorities.

A guardian may submit Pending evidence. Only the Course Owner's audited,
idempotent approval command may transition a record to Active. Native form,
REST, import and direct DocType writes cannot fabricate approved access.
"""
import frappe
from frappe.model.document import Document
from toefl_house.configuration import rules as foundation


class THGuardianConsent(Document):
    def validate(self):
        validate(self)


def validate(doc, method=None):
    if doc.status not in ("Pending", "Active", "Revoked", "Expired"):
        raise frappe.ValidationError("Invalid guardian consent status")
    if doc.evidence_type not in ("Link", "Attachment", "Both"):
        raise frappe.ValidationError("Invalid guardian consent evidence type")
    if doc.status == "Active":
        if foundation.active_command() != "approve_guardian_consent":
            raise frappe.PermissionError(
                "Only an independently audited Course Owner approval "
                "can activate guardian access")
        if not doc.approved_by or not doc.approved_on:
            raise frappe.ValidationError(
                "Active guardian consent requires independent staff approval")
        if doc.approved_by == doc.recorded_by:
            raise frappe.PermissionError(
                "The evidence submitter cannot approve their own guardian access")
        if not doc.expiry_date:
            raise frappe.ValidationError("Guardian consent requires an expiry date")

"""Preserve native Education Student; never fabricate email or login.

Native Student.validate_user creates a Website User if creation is enabled in
Education Settings. TOEFL House requires staff-led enrollment for students who
do not have an email address. Candidate identity is the internal Student name
and the separately governed th_candidate_ref, NOT User.email.
"""
import frappe
from education.education.doctype.student.student import Student
from toefl_house.security import active_command_kind, is_production


def _protect_candidate_provenance(doc, doctype, fields):
    """Refuse ordinary document edits to authoritative student identity links.

    Native name, phone and actual email may be corrected under their own
    permissions; origin links may not be silently reassigned to another
    applicant or Reception visit. New documents remain insertable by the
    separately guarded Admission command.
    """
    if doc.is_new():
        return
    previous = frappe.db.get_value(doctype, doc.name, list(fields), as_dict=True)
    if previous is None:
        raise frappe.ValidationError("Cannot validate original Student identity")
    for field in fields:
        if (doc.get(field) or "") != (previous.get(field) or ""):
            raise frappe.PermissionError(
                "Verified candidate provenance cannot be changed from a native form; "
                "request an independently approved identity correction")


def protect_applicant_identity(doc, method=None):
    if is_production() and doc.is_new():
        if active_command_kind() != "record_applicant":
            raise frappe.PermissionError(
                "Native Student Applicant creation requires approved placement intake")
        if not doc.get("th_candidate_ref") or not doc.get("th_reception_inquiry"):
            raise frappe.ValidationError(
                "Student Applicant needs a verified candidate and Reception referral")
    _protect_candidate_provenance(
        doc, "Student Applicant",
        ("th_candidate_ref", "th_reception_inquiry", "first_name", "last_name"))


class THEmailOptionalStudent(Student):
    def validate(self):
        if is_production() and self.is_new():
            if active_command_kind() != "convert_applicant":
                raise frappe.PermissionError(
                    "Native Student creation requires an approved admission conversion")
            if not self.get("student_applicant") or not self.get("th_candidate_ref"):
                raise frappe.ValidationError(
                    "Student needs a verified Applicant and candidate reference")
        _protect_candidate_provenance(
            self, "Student",
            ("student_applicant", "th_candidate_ref", "first_name", "last_name"))
        return super().validate()

    def validate_user(self):
        # A student record never silently provisions a website login.
        # A real self-service account is an independently approved workflow.
        if self.user:
            user_email = frappe.db.get_value("User", self.user, "email")
            if not user_email or not self.student_email_id or user_email != self.student_email_id:
                raise frappe.PermissionError(
                    "A Student portal User must have an independently verified matching email")
        return None

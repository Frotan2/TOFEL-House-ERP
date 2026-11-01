"""Preserve native Education Student; never fabricate email or login.

Native Student.validate_user creates a Website User if creation is enabled in
Education Settings. TOEFL House requires staff-led enrollment for students who
do not have an email address. Candidate identity is the internal Student name
and the separately governed th_candidate_ref, NOT User.email.
"""
import frappe
from education.education.doctype.student.student import Student


class THEmailOptionalStudent(Student):
    def validate_user(self):
        # A student record never silently provisions a website login.
        # A real self-service account is an independently approved workflow.
        if self.user:
            user_email = frappe.db.get_value("User", self.user, "email")
            if not user_email or not self.student_email_id or user_email != self.student_email_id:
                raise frappe.PermissionError(
                    "A Student portal User must have an independently verified matching email")
        return None

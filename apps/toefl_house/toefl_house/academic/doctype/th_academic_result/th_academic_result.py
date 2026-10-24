import frappe

from toefl_house.controllers import ProtectedRecord


class THAcademicResult(ProtectedRecord):
    """A published result is evidence: never editable, never re-graded in place.

    Corrections create a new revision that supersedes this row; the previous
    row keeps the exact snapshot, outcome and digest it published.
    """

    IMMUTABLE = (
        "student", "student_group", "level", "book", "attempt", "revision",
        "policy", "policy_effective_from", "policy_digest", "grading_scale",
        "overall_percent", "grade_code", "outcome", "passed",
        "attendance_percent", "snapshot_json", "snapshot_digest",
        "native_assessment_result", "supersedes", "published_by",
        "published_on",
    )

    def validate(self):
        super().validate()
        before = self.get_doc_before_save()
        if not before:
            return
        if before.status == "Superseded":
            raise frappe.PermissionError("A superseded result is final")
        for field in self.IMMUTABLE:
            if before.get(field) != self.get(field):
                raise frappe.PermissionError(
                    "Published results are immutable; correct the result by "
                    "publishing a new revision")

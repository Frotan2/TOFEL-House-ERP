import frappe

from toefl_house.controllers import ProtectedRecord


class THAssessmentBook(ProtectedRecord):
    """Command-only mark book.

    Marks are grading evidence: they are written, corrected, approved and
    published only through the guarded academic assessment commands, never
    through a native form, REST call, import or script (ProtectedRecord pins
    that on every save path). The status trail and the pinned policy
    identity are additionally immutable once written.
    """

    IMMUTABLE = (
        "student_group", "level", "policy", "policy_effective_from",
        "policy_digest", "grading_scale", "assessment_plan", "attempt",
        "opened_by", "opened_on",
    )

    def validate(self):
        super().validate()
        before = self.get_doc_before_save()
        if not before:
            return
        for field in self.IMMUTABLE:
            if before.get(field) != self.get(field):
                raise frappe.PermissionError(
                    "Assessment book identity is immutable; open a new attempt instead")


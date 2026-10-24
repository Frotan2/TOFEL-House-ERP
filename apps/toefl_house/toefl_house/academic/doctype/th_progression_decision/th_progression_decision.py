import frappe

from toefl_house.controllers import ProtectedRecord


class THProgressionDecision(ProtectedRecord):
    """An approved progression decision is final evidence.

    Decisions are recorded once, by an authorized academic actor, and are
    never edited: a later change of mind is a new decision row, and earlier
    rows keep their eligibility snapshot.
    """

    IMMUTABLE = (
        "student", "academic_result", "decision", "from_level", "to_level",
        "policy", "policy_effective_from", "eligible", "override_used",
        "override_reason", "eligibility_json", "eligibility_digest",
        "reason", "decided_by", "decided_on",
    )

    def validate(self):
        super().validate()
        before = self.get_doc_before_save()
        if not before:
            return
        for field in self.IMMUTABLE:
            if before.get(field) != self.get(field):
                raise frappe.PermissionError(
                    "A recorded progression decision is immutable")

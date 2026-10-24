from frappe.model.document import Document


class THAssessmentBookCorrection(Document):
    """Append-only log of academic corrections (a mark is never rewritten silently)."""
    pass

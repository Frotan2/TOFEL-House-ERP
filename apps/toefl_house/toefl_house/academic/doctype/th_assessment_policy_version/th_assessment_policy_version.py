"""Controller for TH Assessment Policy Version (child table).

The class must exist so bench migrate keeps the DocType registered; all
version integrity rules run on the parent (TH Assessment Policy), which
sees the whole version set at once.
"""
from frappe.model.document import Document


class THAssessmentPolicyVersion(Document):
    pass

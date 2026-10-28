"""Controller for TH Returning Student Policy Version (child table).

The class must exist so bench migrate keeps the DocType registered; all
version integrity rules run on the parent (TH Returning Student Policy),
which sees the whole version set at once.
"""
from frappe.model.document import Document


class THReturningStudentPolicyVersion(Document):
    pass

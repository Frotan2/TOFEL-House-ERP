"""Child rows are deliberately unguarded; the parent controller and guarded commands own the mutation boundary."""
from frappe.model.document import Document

class THOwnerOperationsPolicyVersion(Document):
    pass

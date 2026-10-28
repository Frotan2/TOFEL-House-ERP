"""Child-row controller for TH Roster Change Policy Version.

Rows live only inside their parent policy's version table and are
written exclusively by the guarded policy commands. The parent
controller validates every row on each save, so this controller binds
no additional rule.
"""
from frappe.model.document import Document


class THRosterChangePolicyVersion(Document):
    pass

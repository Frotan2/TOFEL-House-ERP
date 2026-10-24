"""Child-row controller for TH Academic Calendar Day.

Rows live only inside their parent calendar and are written exclusively by the
guarded calendar commands; the parent validates every row on each save.
"""
from frappe.model.document import Document


class THAcademicCalendarDay(Document):
    pass

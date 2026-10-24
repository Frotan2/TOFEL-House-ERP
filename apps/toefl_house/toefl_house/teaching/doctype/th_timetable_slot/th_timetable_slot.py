"""Child-row controller for TH Timetable Slot.

Rows live only inside their parent template and are written exclusively by the
guarded timetable commands; the parent validates every row on each save.
"""
from frappe.model.document import Document


class THTimetableSlot(Document):
    pass

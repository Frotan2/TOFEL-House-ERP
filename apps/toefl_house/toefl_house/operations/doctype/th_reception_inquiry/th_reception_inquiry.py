"""Native controller: prohibit manual edits and deletion of intake evidence."""
from frappe.model.document import Document

from toefl_house.reception_intake import protect_inquiry


class THReceptionInquiry(Document):
    def validate(self):
        protect_inquiry(self)

    def on_trash(self):
        protect_inquiry(self, "on_trash")

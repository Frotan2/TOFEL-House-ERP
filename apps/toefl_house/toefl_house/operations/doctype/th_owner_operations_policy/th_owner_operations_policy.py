"""Controller for the global Course Owner operational policy carrier."""
from frappe.model.document import Document
from toefl_house.operations import owner_configuration

class THOwnerOperationsPolicy(Document):
    def validate(self):
        owner_configuration.validate_policy(self)

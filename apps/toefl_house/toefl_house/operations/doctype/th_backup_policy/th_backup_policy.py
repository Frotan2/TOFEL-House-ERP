"""Only the guarded Course Owner command can change the local backup policy."""
import frappe
from frappe.model.document import Document
from toefl_house.configuration import rules as foundation
from toefl_house.operations.owner_configuration import (
    BACKUP_POLICY_ACTION, validate_backup_policy_snapshot,
)


class THBackupPolicy(Document):
    def validate(self):
        if foundation.active_command() != BACKUP_POLICY_ACTION:
            raise frappe.PermissionError(
                "Only the audited Course Owner backup configuration action may change this policy")
        try:
            validate_backup_policy_snapshot(self.policy_snapshot)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc

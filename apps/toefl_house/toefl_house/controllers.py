"""Owned document invariants apply even when generic writes ignore permissions."""
import frappe
from frappe.model.document import Document
from toefl_house.security import require_command


class ProtectedRecord(Document):
    def before_insert(self):
        require_command(self.doctype)

    def validate(self):
        require_command(self.doctype)
        if self.get("synthetic") != 1:
            raise frappe.ValidationError("Only synthetic records are supported")
        before = self.get_doc_before_save()
        if before and self.doctype in ("TH Placement Audit Event",):
            raise frappe.PermissionError("Audit events are append-only")
        if before and self.doctype == "TH Placement Operation" and before.status == "Complete":
            raise frappe.PermissionError("Completed operation receipts are immutable")
        if before and self.doctype == "TH Placement Item Revision":
            if before.status == "Published" or before.family != self.family or before.revision != self.revision or before.owner != self.owner:
                raise frappe.PermissionError("Published content and revision identity are immutable")
        if before and self.doctype == "TH Placement Key Revision":
            raise frappe.PermissionError("Key versions are append-only")

    def db_insert(self, *args, **kwargs):
        require_command(self.doctype)
        return super().db_insert(*args, **kwargs)

    def db_update(self, *args, **kwargs):
        require_command(self.doctype)
        return super().db_update(*args, **kwargs)

    def db_set(self, *args, **kwargs):
        raise frappe.PermissionError("Direct setters are not a placement mutation path")

    def before_rename(self, *args, **kwargs):
        raise frappe.PermissionError("Placement records cannot be renamed")

    def on_trash(self):
        raise frappe.PermissionError("Placement history cannot be deleted through CRUD")

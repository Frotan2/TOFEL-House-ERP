"""Only owned indexes and module installation; never activate operations."""
import frappe


def after_migrate():
    frappe.db.add_unique("TH Placement Item Revision", ["family", "revision"], "th_item_family_revision")
    frappe.db.add_unique("TH Placement Key Revision", ["item_revision", "key_version"], "th_key_item_version")
    frappe.db.add_index("TH Placement Audit Event", ["item_revision", "creation"])


def after_install():
    after_migrate()

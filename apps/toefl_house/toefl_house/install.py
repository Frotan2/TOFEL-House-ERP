"""Only owned indexes and module installation; never activate operations."""
import frappe


def after_migrate():
    frappe.db.add_unique("TH Placement Item Revision", ["family", "revision"], "th_item_family_revision")
    frappe.db.add_unique("TH Placement Key Revision", ["item_revision", "key_version"], "th_key_item_version")
    frappe.db.add_unique("TH Placement Blueprint Revision", ["code", "revision"], "th_blueprint_code_revision")
    frappe.db.add_unique("TH Placement Policy Revision", ["code", "revision"], "th_policy_code_revision")
    frappe.db.add_index("TH Placement Audit Event", ["item_revision", "creation"])
    frappe.db.add_index("TH Placement Audit Event", ["target", "creation"])
    frappe.db.add_index("TH Placement Blueprint Revision", ["status", "creation"])
    frappe.db.add_index("TH Placement Policy Revision", ["status", "creation"])
    frappe.db.add_unique("TH Placement Case", ["subject"], "th_case_subject")
    frappe.db.add_unique("TH Placement Attempt", ["case_name", "ordinal"], "th_attempt_case_ordinal")
    frappe.db.add_unique("TH Placement Form Manifest", ["attempt"], "th_manifest_attempt")
    frappe.db.add_unique("TH Placement Exposure", ["attempt", "family", "event"], "th_exposure_attempt_family_event")
    frappe.db.add_index("TH Placement Item Revision", ["status", "skill"], "th_item_status_skill")
    frappe.db.add_index("TH Placement Exposure", ["subject"], "th_exposure_subject")
    frappe.db.add_index("TH Placement Exposure", ["family"], "th_exposure_family")


def after_install():
    # Initialize the native site key once at install, never race key generation in requests.
    from frappe.utils.password import get_encryption_key
    get_encryption_key()
    after_migrate()

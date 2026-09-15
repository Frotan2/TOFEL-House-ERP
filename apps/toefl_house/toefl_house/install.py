"""Only owned indexes and module installation; never activate operations."""
import frappe


def after_migrate():
    frappe.db.add_unique("TH Placement Item Revision", ["family", "revision"], "th_item_family_revision")
    frappe.db.add_unique("TH Placement Key Revision", ["item_revision", "key_version"], "th_key_item_version")
    frappe.db.add_unique("TH Placement Blueprint Revision", ["code", "revision"], "th_blueprint_code_revision")
    frappe.db.add_unique("TH Placement Policy Revision", ["code", "revision"], "th_policy_code_revision")
    frappe.db.add_unique("TH Placement Course Map Revision", ["code", "revision"], "th_course_map_code_revision")
    frappe.db.add_index("TH Placement Audit Event", ["item_revision", "creation"])
    frappe.db.add_index("TH Placement Audit Event", ["target", "creation"])
    frappe.db.add_index("TH Placement Blueprint Revision", ["status", "creation"])
    frappe.db.add_index("TH Placement Policy Revision", ["status", "creation"])
    frappe.db.add_index("TH Placement Course Map Revision", ["status", "creation"])
    frappe.db.add_unique("TH Placement Case", ["subject"], "th_case_subject")
    frappe.db.add_unique("TH Placement Attempt", ["case_name", "ordinal"], "th_attempt_case_ordinal")
    frappe.db.add_unique("TH Placement Form Manifest", ["attempt"], "th_manifest_attempt")
    frappe.db.add_unique("TH Placement Exposure", ["attempt", "family", "event"], "th_exposure_attempt_family_event")
    frappe.db.add_index("TH Placement Item Revision", ["status", "skill"], "th_item_status_skill")
    frappe.db.add_index("TH Placement Exposure", ["subject"], "th_exposure_subject")
    frappe.db.add_index("TH Placement Exposure", ["family"], "th_exposure_family")
    frappe.db.add_unique("TH Placement Response", ["attempt", "occurrence", "revision"],
                         "th_response_attempt_occurrence_revision")
    frappe.db.add_index("TH Placement Response", ["attempt", "occurrence"], "th_response_attempt_occurrence")
    frappe.db.add_unique("TH Placement Score", ["attempt", "revision"], "th_score_attempt_revision")
    frappe.db.add_index("TH Placement Score", ["attempt"], "th_score_attempt")
    frappe.db.add_unique("TH Placement Decision", ["attempt", "revision"], "th_decision_attempt_revision")
    frappe.db.add_index("TH Placement Decision", ["attempt"], "th_decision_attempt")
    frappe.db.add_index("TH Admission Decision", ["student_applicant"], "th_admission_applicant")
    frappe.db.add_index("TH Admission Decision", ["placement_decision"], "th_admission_placement")
    frappe.db.add_index("TH Admission Decision", ["native_student"], "th_admission_student")
    frappe.db.add_index("TH Admission Decision", ["status"], "th_admission_status")


def after_install():
    # Initialize the native site key once at install, never race key generation in requests.
    from frappe.utils.password import get_encryption_key
    get_encryption_key()
    after_migrate()

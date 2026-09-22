"""Only owned indexes and module installation; never activate operations."""
import frappe


# Canonical default skills seeded at install. Codes are stable identity; titles
# may be renamed by the Course Owner through configuration. The canonical three
# match the originally hard-coded teaching skill vocabulary so existing
# references (if any) keep their identity under the new configurable master.
DEFAULT_SKILLS = (
    ("SL", "Speaking & Listening"),
    ("WG", "Writing & Grammar"),
    ("RV", "Reading & Vocabulary"),
)


def _seed_skills():
    """Seed the three canonical TH Skill masters if they do not exist yet.

    Safe to run on every migrate: existing skill records (by unique code) are
    left untouched; this never overwrites owner configuration.
    """
    for code, title in DEFAULT_SKILLS:
        if frappe.db.exists("TH Skill", code):
            continue
        try:
            doc = frappe.get_doc({
                "doctype": "TH Skill",
                "code": code,
                "title": title,
                "status": "Active",
                "set_by": "Administrator",
                "set_on": frappe.utils.now_datetime(),
            })
            doc.flags.ignore_permissions = True
            doc.insert(ignore_permissions=True)
        except Exception:
            # Another migrate or parallel process may have created it concurrently.
            frappe.db.rollback()


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
    # D2 teaching compensation lookups (overlap windows are command-enforced).
    frappe.db.add_index("TH Instructor Contract", ["instructor", "status"], "th_contract_instructor_status")
    frappe.db.add_index("TH Teaching Assignment", ["student_group", "skill"], "th_assignment_group_skill")
    frappe.db.add_index("TH Teaching Assignment", ["contract"], "th_assignment_contract")
    frappe.db.add_index("TH Teaching Assignment", ["instructor", "effective_start"], "th_assignment_instructor_start")
    # TH Skill lookups (config master).
    frappe.db.add_index("TH Skill", ["status"], "th_skill_status")
    # Student Group class lifecycle lookups (operational class fields). These
    # columns come from Custom Field fixtures; during install-app the
    # fixtures have not been applied yet, so adding the index there fails
    # with MySQL 1072 (hosted run 35332459813). Guard on column existence:
    # the next migrate adds the index once the Custom Fields are present.
    for column, index in (("th_class_status", "th_sg_class_status"),
                          ("th_branch", "th_sg_branch"),
                          ("th_class_start_date", "th_sg_start_date")):
        if frappe.db.has_column("Student Group", column):
            frappe.db.add_index("Student Group", [column], index)
    # D2 compensation locking reads (BUG-PAY-01): the one-off existence probes
    # lock matching Additional Salary rows; the covering index keeps the lock
    # footprint to the referenced rows instead of a table scan.
    frappe.db.add_index("Additional Salary", ["ref_doctype", "ref_docname"], "th_ads_ref")
    # D3 correction framework lookups.
    frappe.db.add_index("TH Correction Policy", ["status"], "th_correction_policy_status")
    frappe.db.add_index("TH Correction Request", ["sales_invoice"], "th_correction_request_invoice")
    _seed_skills()


def after_install():
    # Initialize the native site key once at install, never race key generation in requests.
    from frappe.utils.password import get_encryption_key
    get_encryption_key()
    after_migrate()

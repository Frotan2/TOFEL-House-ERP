app_name = "toefl_house"
app_title = "TOEFL House Placement (Synthetic Qualification)"
app_publisher = "TOEFL House"
app_description = "Synthetic-only governed placement, thin admission, native Program Enrollment and native teaching operations"
app_email = "validation@example.test"
app_license = "MIT"
required_apps = ["erpnext", "education", "foundation_security"]
after_install = "toefl_house.install.after_install"
after_migrate = "toefl_house.install.after_migrate"
# Release navigation is deliberately split by the native framework boundary.
# Workspaces remain only TH Receipts and TH Finance.  They pass Frappe's
# workspace module gate and do not grant document permission.  D10's
# API-first roles receive native Page records instead: pinned Page.get checks
# only the Page Has Role rows, so a page can launch an existing guarded command
# without widening native document permissions or creating another Workspace.
# `app_home` routes the TOEFL House app tile to the role-filtered command centre;
# every individual page remains independently Page-role-gated server-side.
app_home = "/app/th-command-centre"
_COMMAND_PAGES = (
    "th-administration-control-centre",
    "th-command-centre",
    "th-placement-author", "th-placement-publisher", "th-placement-invigilation",
    "th-placement-assessment", "th-placement-review", "th-placement-release",
    "th-admission-officer", "th-admission-review", "th-admission-approval",
    "th-enrollment", "th-teaching-scheduling", "th-attendance-recording",
)
page_js = {name: "public/js/th_command_pages.js" for name in _COMMAND_PAGES}
# Role desks (docs/product/ROLE-DESKS.md) use the desk client. They are
# separate native Pages, independently role-gated server-side; they share the
# design system stylesheet with the command pages but not the command client.
_DESK_PAGES = (
    "th-reception-desk", "th-academic-desk", "th-finance-desk",
    "th-operations-desk", "th-owner-cockpit", "th-academic-setup",
)
page_js.update({name: "public/js/th_role_desks.js" for name in _DESK_PAGES})
fixtures = [{"dt": "Role", "filters": [["name", "in", ["Placement Author", "Placement Publisher", "Placement Auditor", "Placement Invigilator", "Placement Assessor", "Placement Reviewer", "Placement Releaser", "Admission Officer", "Admission Reviewer", "Admission Approver", "Admission Auditor", "Enrollment Officer", "Enrollment Auditor", "Teaching Scheduler", "Attendance Recorder", "Teaching Auditor", "Finance Officer", "Finance Auditor", "Course Owner", "General Manager", "Academic Manager", "Finance Manager", "Reception"]]]},
            {"dt": "Custom Field", "filters": [["dt", "=", "Sales Invoice"], ["fieldname", "=", "th_placement_case"]]}]
has_permission = {
    name: "toefl_house.permissions.has_permission"
    for name in ("TH Placement Item Revision", "TH Placement Key Revision", "TH Placement Audit Event",
                 "TH Placement Operation", "TH Placement Blueprint Revision", "TH Placement Policy Revision",
                 "TH Placement Case", "TH Placement Attempt", "TH Placement Form Manifest",
                 "TH Placement Exposure", "TH Placement Allocation Guard",
                 "TH Placement Response", "TH Placement Score",
                 "TH Placement Course Map Revision", "TH Placement Decision",
                 "TH Admission Decision", "TH Instructor Contract",
                 "TH Teaching Assignment", "TH Correction Policy",
                 "TH Correction Request",
                 "TH Academic Program", "TH Program Level",
                 "TH Discount Rule")
}
has_permission["TH Academic Program"] = "toefl_house.permissions.configuration_has_permission"
has_permission["TH Program Level"] = "toefl_house.permissions.configuration_has_permission"
has_permission["TH Discount Rule"] = "toefl_house.permissions.configuration_has_permission"
permission_query_conditions = {
    name: "toefl_house.permissions.query_" + suffix
    for name, suffix in (
        ("TH Placement Item Revision", "item"), ("TH Placement Key Revision", "key"),
        ("TH Placement Audit Event", "audit"), ("TH Placement Operation", "operation"),
        ("TH Placement Blueprint Revision", "blueprint"), ("TH Placement Policy Revision", "policy"),
        ("TH Placement Case", "case"), ("TH Placement Attempt", "attempt"),
        ("TH Placement Form Manifest", "manifest"), ("TH Placement Exposure", "exposure"),
        ("TH Placement Allocation Guard", "guard"), ("TH Placement Response", "response"),
        ("TH Placement Score", "score"),
        ("TH Placement Course Map Revision", "course_map"),
        ("TH Placement Decision", "decision"),
        ("TH Admission Decision", "admission_decision"),
        ("TH Instructor Contract", "contract"),
        ("TH Teaching Assignment", "assignment"),
        ("TH Correction Policy", "correction_policy"),
        ("TH Correction Request", "correction_request"))
}
# Governance configuration is queried through the non-synthetic checker.
permission_query_conditions["TH Academic Program"] = "toefl_house.permissions.configuration_query"
permission_query_conditions["TH Program Level"] = "toefl_house.permissions.configuration_query"
permission_query_conditions["TH Discount Rule"] = "toefl_house.permissions.configuration_query"
override_whitelisted_methods = {
    "education.education.api.enroll_student": "toefl_house.admission.deny_enroll_student",
}
# Containment seam coverage (A13): in pinned frappe (988e54f3c4c2,
# frappe/model/document.py run_before_save_methods), the "validate"
# doc_event fires only for save/submit actions. Cancel runs
# "before_cancel" and post-submit edits run "before_update_after_submit"
# WITHOUT validate, so each command-only doctype pins the same guard on
# all three seams. Delete of submitted documents is natively denied by
# frappe (delete_doc check_permission_and_not_submitted); drafts cannot
# exist outside commands because insert is denied on validate.
doc_events = {
    # Governance configuration: unconditional integrity hooks (the rules bind
    # on every write path, native form included). Distinct from the command
    # containment guards below; sanctioned by tests/finance/test_containment_hooks.
    "TH Academic Program": {
        "validate": "toefl_house.academic.doctype.th_academic_program.th_academic_program.validate",
    },
    "TH Program Level": {
        "validate": "toefl_house.academic.doctype.th_program_level.th_program_level.validate",
        "before_save": "toefl_house.academic.doctype.th_program_level.th_program_level.before_save",
    },
    "TH Discount Rule": {
        "validate": "toefl_house.academic.doctype.th_discount_rule.th_discount_rule.validate",
    },
    "Program Enrollment": {
        "validate": "toefl_house.enrollment.guard_program_enrollment",
        "before_cancel": "toefl_house.enrollment.guard_program_enrollment",
        "before_update_after_submit": "toefl_house.enrollment.guard_program_enrollment",
    },
    "Course Enrollment": {
        "validate": "toefl_house.enrollment.guard_course_enrollment",
        "before_cancel": "toefl_house.enrollment.guard_course_enrollment",
        "before_update_after_submit": "toefl_house.enrollment.guard_course_enrollment",
    },
    "Sales Invoice": {
        # finance.guard_sales_invoice chains the enrollment slice's
        # premature-billing guard first, then applies finance containment.
        "validate": "toefl_house.finance.guard_sales_invoice",
        "before_cancel": "toefl_house.finance.guard_sales_invoice",
        "before_update_after_submit": "toefl_house.finance.guard_sales_invoice",
    },
    "Fees": {
        "validate": "toefl_house.finance.guard_fees",
        "before_cancel": "toefl_house.finance.guard_fees",
        "before_update_after_submit": "toefl_house.finance.guard_fees",
    },
    "Student Group": {
        "validate": "toefl_house.teaching.guard_student_group",
        "before_cancel": "toefl_house.teaching.guard_student_group",
        "before_update_after_submit": "toefl_house.teaching.guard_student_group",
    },
    "Course Schedule": {
        "validate": "toefl_house.teaching.guard_course_schedule",
        "before_cancel": "toefl_house.teaching.guard_course_schedule",
        "before_update_after_submit": "toefl_house.teaching.guard_course_schedule",
    },
    "Student Attendance": {
        "validate": "toefl_house.teaching.guard_student_attendance",
        "before_cancel": "toefl_house.teaching.guard_student_attendance",
        "before_update_after_submit": "toefl_house.teaching.guard_student_attendance",
    },
}

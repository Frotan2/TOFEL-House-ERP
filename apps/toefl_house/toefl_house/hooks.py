app_name = "toefl_house"
app_title = "TOEFL House Placement (Synthetic Qualification)"
app_publisher = "TOEFL House"
app_description = "Synthetic-only governed placement, thin admission, native Program Enrollment and native teaching operations"
app_email = "validation@example.test"
app_license = "MIT"
required_apps = ["erpnext", "education", "foundation_security"]
after_install = "toefl_house.install.after_install"
after_migrate = "toefl_house.install.after_migrate"
fixtures = [{"dt": "Role", "filters": [["name", "in", ["Placement Author", "Placement Publisher", "Placement Auditor", "Placement Invigilator", "Placement Assessor", "Placement Reviewer", "Placement Releaser", "Admission Officer", "Admission Reviewer", "Admission Approver", "Admission Auditor", "Enrollment Officer", "Enrollment Auditor", "Teaching Scheduler", "Attendance Recorder", "Teaching Auditor", "Finance Officer", "Finance Auditor"]]]},
            {"dt": "Custom Field", "filters": [["dt", "=", "Sales Invoice"], ["fieldname", "=", "th_placement_case"]]}]
has_permission = {
    name: "toefl_house.permissions.has_permission"
    for name in ("TH Placement Item Revision", "TH Placement Key Revision", "TH Placement Audit Event",
                 "TH Placement Operation", "TH Placement Blueprint Revision", "TH Placement Policy Revision",
                 "TH Placement Case", "TH Placement Attempt", "TH Placement Form Manifest",
                 "TH Placement Exposure", "TH Placement Allocation Guard",
                 "TH Placement Response", "TH Placement Score",
                 "TH Placement Course Map Revision", "TH Placement Decision",
                 "TH Admission Decision")
}
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
        ("TH Admission Decision", "admission_decision"))
}
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

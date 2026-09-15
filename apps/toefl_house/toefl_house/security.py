"""Deny-by-default synthetic operation guard and non-serializable command context."""
from contextlib import contextmanager
from contextvars import ContextVar
import frappe

_CONTEXT = ContextVar("toefl_house_content_command", default=None)
KIND_ROLES = {
    "create_draft": "Placement Author",
    "revise_draft": "Placement Author",
    "publish": "Placement Publisher",
    "create_blueprint": "Placement Author",
    "create_policy": "Placement Author",
    "revise_blueprint": "Placement Author",
    "revise_policy": "Placement Author",
    "review_blueprint": "Placement Publisher",
    "review_policy": "Placement Publisher",
    "publish_blueprint": "Placement Publisher",
    "publish_policy": "Placement Publisher",
    "retire_blueprint": "Placement Publisher",
    "retire_policy": "Placement Publisher",
    "create_case": "Placement Publisher",
    "allocate_attempt": "Placement Publisher",
    "verify_attempt": "Placement Invigilator",
    "deliver_attempt": "Placement Invigilator",
    "save_response": "Placement Invigilator",
    "seal_attempt": "Placement Invigilator",
    "score_attempt": "Placement Assessor",
    "review_attempt": "Placement Reviewer",
    "finalize_attempt": "Placement Reviewer",
    "create_course_map": "Placement Author",
    "revise_course_map": "Placement Author",
    "review_course_map": "Placement Publisher",
    "publish_course_map": "Placement Publisher",
    "retire_course_map": "Placement Publisher",
    "release_decision": "Placement Releaser",
    "record_applicant": "Admission Officer",
    "create_admission": "Admission Officer",
    "review_admission": "Admission Reviewer",
    "decide_admission": "Admission Approver",
    "accept_offer": "Admission Officer",
    "withdraw_admission": "Admission Officer",
    "revoke_admission": "Admission Approver",
    "expire_admission": "Admission Officer",
    "convert_applicant": "Admission Approver",
    "enroll_in_program": "Enrollment Officer",
    "create_student_group": "Teaching Scheduler",
    "schedule_session": "Teaching Scheduler",
    "record_attendance": "Attendance Recorder",
}
KINDS = set(KIND_ROLES)
DOCTYPES = {
    "TH Placement Item Revision", "TH Placement Key Revision",
    "TH Placement Audit Event", "TH Placement Operation",
    "TH Placement Blueprint Revision", "TH Placement Policy Revision",
    "TH Placement Case", "TH Placement Attempt", "TH Placement Form Manifest",
    "TH Placement Exposure", "TH Placement Allocation Guard",
    "TH Placement Response", "TH Placement Score",
    "TH Placement Course Map Revision", "TH Placement Decision",
    "TH Admission Decision",
}
CONFIG_DOCTYPES = ("TH Placement Blueprint Revision", "TH Placement Policy Revision",
                   "TH Placement Course Map Revision")


def require_synthetic():
    if (frappe.conf.get("toefl_house_synthetic_only") != 1
            or frappe.conf.get("allow_tests") != 1
            or frappe.local.site not in {"placement-test.localhost", "placement-second.localhost"}):
        raise frappe.PermissionError("Placement is disabled outside explicitly isolated synthetic test sites")


def authorize(role):
    require_synthetic()
    user = frappe.session.user
    if user in (None, "Guest", "Administrator") or role not in frappe.get_roles(user):
        raise frappe.PermissionError("An explicitly assigned non-administrator actor is required")
    if not frappe.db.get_value("User", user, "enabled"):
        raise frappe.PermissionError("Actor has been disabled")
    return user


@contextmanager
def command(kind, actor):
    if kind not in KINDS or _CONTEXT.get() is not None:
        raise frappe.PermissionError("Invalid or nested placement command")
    token = _CONTEXT.set((kind, actor))
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def require_command(doctype):
    require_synthetic()
    context = _CONTEXT.get()
    if doctype not in DOCTYPES or context is None or context[1] != frappe.session.user:
        raise frappe.PermissionError("Protected records require an authorized domain command")
    authorize(KIND_ROLES[context[0]])
    return context


def enrollment_command_active():
    context = _CONTEXT.get()
    return bool(context and context[0] == "enroll_in_program" and context[1] == frappe.session.user)


TEACHING_COMMANDS = {
    "create_student_group": "Student Group",
    "schedule_session": "Course Schedule",
    "record_attendance": "Student Attendance",
}


def teaching_command_active(doctype):
    """Return True only inside the matching teaching command for this actor."""
    context = _CONTEXT.get()
    return bool(context and context[1] == frappe.session.user
                and TEACHING_COMMANDS.get(context[0]) == doctype)

"""The shared student-lifecycle stage machine.

Pure functions, no Frappe import, directly unit-tested. One definition of
"where is this person in the funnel and what happens next" is what makes the
five desks (and the cross-role workflow in docs/product/ROLE-DESKS.md) read as
one system instead of five disconnected screens.

Every stage names:
- `label`      — staff-facing stage name (never a DocType name)
- `definition` — the exact record states that produce this stage
- `next`       — the next action, in staff language
- `role`       — the role that owns the next action
- `command`    — the guarded command kind that performs it (KIND_ROLES name),
                 or None when the next action is a human hand-off
"""

PLACEMENT_ATTEMPT_ORDER = (
    "Allocated", "Verified", "In Progress", "Sealed", "Marking", "Review",
    "Finalized",
)
ADMISSION_OPEN_STATUSES = ("Draft", "Review", "Approved", "Conditional")
ADMISSION_CLOSED_STATUSES = ("Deferred", "Rejected", "Withdrawn", "Revoked", "Expired")


def placement_session_stage(attempt_status):
    """The in-placement sub-stage, or None when the attempt is not running."""
    order = PLACEMENT_ATTEMPT_ORDER
    if attempt_status not in order:
        return None
    if attempt_status == "Finalized":
        return None
    if attempt_status in ("Allocated", "Verified", "In Progress", "Sealed"):
        return {
            "label": "Placement session",
            "definition": f"Placement attempt is {attempt_status}.",
            "next": "Run the supervised placement session to seal the attempt.",
            "role": "Placement Invigilator",
            "command": "deliver_attempt",
        }
    if attempt_status == "Marking":
        return {
            "label": "Marking",
            "definition": "Sealed attempt is waiting for objective scoring.",
            "next": "Score the sealed attempt.",
            "role": "Placement Assessor",
            "command": "score_attempt",
        }
    return {
        "label": "Independent review",
        "definition": "Marked attempt is waiting for independent review and finalization.",
        "next": "Review and finalize the marked attempt.",
        "role": "Placement Reviewer",
        "command": "review_attempt",
    }


def admission_stage(admission_status, accepted, has_native_student):
    """Admission stage from the TH Admission Decision state facts.

    `accepted` is the decision's accepted flag; `has_native_student` says
    whether the decision already converted to a native Student.
    """
    if admission_status == "Draft":
        return {
            "label": "Admission drafted",
            "definition": "Intake is recorded and the admission decision is a draft.",
            "next": "Send the admission decision for independent review.",
            "role": "Admission Reviewer",
            "command": "review_admission",
        }
    if admission_status == "Review":
        return {
            "label": "Admission review",
            "definition": "The admission decision is in independent review.",
            "next": "Record the admission outcome (approve, condition, defer or reject).",
            "role": "Admission Approver",
            "command": "decide_admission",
        }
    if admission_status in ("Approved", "Conditional"):
        if has_native_student:
            return {
                "label": "Student created",
                "definition": "The admission is approved and a native Student exists.",
                "next": "Enroll the student in the program.",
                "role": "Enrollment Officer",
                "command": "enroll_in_program",
            }
        if accepted:
            return {
                "label": "Offer accepted",
                "definition": "The offer was accepted and conversion is next.",
                "next": "Convert the applicant into a native Student.",
                "role": "Admission Approver",
                "command": "convert_applicant",
            }
        return {
            "label": "Admission decided" if admission_status == "Approved" else "Conditional admission",
            "definition": f"The admission outcome is {admission_status}.",
            "next": "Record the offer acceptance.",
            "role": "Admission Officer",
            "command": "accept_offer",
        }
    if admission_status == "Deferred":
        return {
            "label": "Deferred",
            "definition": "The admission was deferred by the approver.",
            "next": "Follow up with the applicant before the placement decision expires.",
            "role": "Admission Officer",
            "command": None,
        }
    if admission_status in ADMISSION_CLOSED_STATUSES:
        return {
            "label": admission_status,
            "definition": f"The admission decision is {admission_status.lower()}; this file is closed.",
            "next": "No further action on this file.",
            "role": None,
            "command": None,
        }
    return {
        "label": admission_status or "Unknown",
        "definition": "The admission decision state is not one of the defined states.",
        "next": "Ask an Admission Auditor to inspect this record.",
        "role": None,
        "command": None,
    }


def enrollment_stage(has_submitted_enrollment, has_cohort_group):
    """Stage after conversion, from the native enrollment and class facts.

    `has_cohort_group` is a cohort fact (a class planned or running exists
    for the enrollment's program and academic year), not a membership claim:
    the desk never asserts a student is on a roster it cannot see.
    """
    if not has_submitted_enrollment:
        return {
            "label": "Awaiting enrollment",
            "definition": "The learner record exists but no enrollment has been submitted yet.",
            "next": "Enroll the student in the program.",
            "role": "Enrollment Officer",
            "command": "enroll_in_program",
        }
    if not has_cohort_group:
        return {
            "label": "Enrolled, no class",
            "definition": "The enrollment is submitted; no class is planned or running for this level and year yet.",
            "next": "Create the class cohort for this enrollment.",
            "role": "Teaching Scheduler",
            "command": "create_student_group",
        }
    return {
        "label": "Enrolled",
        "definition": "The enrollment is submitted and a class is planned or running for this level and year.",
        "next": "Confirm the class roster and record attendance.",
        "role": "Teaching Scheduler",
        "command": None,
    }


def funnel_order():
    """Canonical stage order of the funnel, for tiles and for 'oldest waiting'."""
    return (
        "Placement session",
        "Marking",
        "Independent review",
        "Awaiting release",
        "Ready for intake",
        "Admission drafted",
        "Admission review",
        "Admission decided",
        "Conditional admission",
        "Offer accepted",
        "Student created",
        "Awaiting enrollment",
        "Enrolled, no class",
        "Enrolled",
        "Deferred",
    )

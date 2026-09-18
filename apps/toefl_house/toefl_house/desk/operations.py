"""General Manager desk: cross-role operations, exceptions, staffing.

Read-only, fact-based, branch-wide. This is deliberately NOT a second Owner
cockpit: no release posture, no governance claims — operational queues and
exception facts only. Sections are specified in docs/product/ROLE-DESKS.md.
"""
import frappe
from frappe.utils import now_datetime

from toefl_house.desk import (
    BOUNCE_WINDOW,
    DESKS,
    LIMIT_QUEUES,
    active_cohort_rows,
    open_cohort_keys,
    project_rows,
    require_desk_audience,
    section,
    viewer_roles,
)
from toefl_house.desk import lifecycle

SLUG = "th-operations-desk"

ATTEMPT = "TH Placement Attempt"
DECISION = "TH Placement Decision"
ADMISSION = "TH Admission Decision"
CORRECTION = "TH Correction Request"
ENROLLMENT = "Program Enrollment"
GROUP = "Student Group"
SCHEDULE = "Course Schedule"

STAFF_ROLES = (
    "Reception", "Admission Officer", "Admission Reviewer", "Admission Approver",
    "Enrollment Officer", "Teaching Scheduler", "Attendance Recorder",
    "Finance Officer", "Academic Manager", "Finance Manager", "General Manager",
)


def _staff_counts():
    """Enabled users per shipped operational role, from the native Has Role."""
    counts = {}
    for role in STAFF_ROLES:
        holders = {row["parent"]
                   for row in project_rows("management", "Has Role",
                                           ["name", "parent", "role", "parenttype"],
                                           filters={"role": role, "parenttype": "User"},
                                           order_by="parent asc", limit=BOUNCE_WINDOW)
                   if row.get("parent") not in (None, "Administrator", "Guest", "")}
        enabled = 0
        if holders:
            rows = project_rows("management", "User", ["name"],
                                filters={"name": ("in", sorted(holders)), "enabled": 1},
                                order_by="name asc", limit=BOUNCE_WINDOW)
            enabled = len(rows)
        counts[role] = enabled
    return counts


def _role_items(counts):
    return [{
        "id": role,
        "person": f"{count} enabled user" + ("" if count == 1 else "s"),
        "detail": "",
        "status": "Unstaffed" if count == 0 else "Staffed",
        "stage": "Role coverage",
        "stage_definition": f"Enabled users holding the {role} role (native Has Role rows).",
        "next": "Assign a user to this role from the Administration Control Centre." if count == 0
        else "No action.",
        "next_role": "Course Owner" if count == 0 else None,
        "waiting_since": None,
    } for role, count in counts.items()]


def _age_label(value):
    if not value:
        return ""
    try:
        from frappe.utils import get_datetime
        delta = now_datetime() - get_datetime(value)
        days = delta.days
        if days <= 0:
            return "today"
        if days == 1:
            return "1 day"
        return f"{days} days"
    except Exception:
        return ""


@frappe.whitelist(methods=["GET", "POST"])
def work():
    """GM desk payload: funnel, exceptions, staffing, links."""
    require_desk_audience(SLUG)

    admissions_open = project_rows("management", ADMISSION,
                                   ["name", "student_applicant", "program", "status",
                                    "version", "modified"],
                                   filters={"status": ("in", list(lifecycle.ADMISSION_OPEN_STATUSES))},
                                   order_by="modified asc", limit=BOUNCE_WINDOW)
    review_waiting = [row for row in admissions_open if row["status"] == "Review"]
    corrections = project_rows("management", CORRECTION,
                               ["name", "sales_invoice", "fees", "reason",
                                "requested_amount", "status", "modified"],
                               filters={"status": "Requested"},
                               order_by="modified asc", limit=LIMIT_QUEUES)
    attempts_running = project_rows("management", ATTEMPT,
                                    ["name", "case_name", "status", "deadline_at"],
                                    filters={"status": ("in", list(lifecycle.PLACEMENT_ATTEMPT_ORDER))},
                                    order_by="modified asc", limit=BOUNCE_WINDOW)
    finalized = project_rows("management", ATTEMPT,
                             ["name", "case_name", "status", "deadline_at"],
                             filters={"status": "Finalized"},
                             order_by="modified asc", limit=BOUNCE_WINDOW)
    released = project_rows("management", DECISION,
                            ["name", "attempt", "status", "released_at", "expires_at"],
                            filters={"status": "Released"},
                            order_by="released_at desc", limit=BOUNCE_WINDOW)
    released_attempts = {row["attempt"] for row in released if row.get("attempt")}
    awaiting_release = [row for row in finalized if row["name"] not in released_attempts]

    enrollments = project_rows("management", ENROLLMENT,
                               ["name", "student", "student_name", "program",
                                "academic_year", "enrollment_date", "docstatus"],
                               filters={"docstatus": 1},
                               order_by="enrollment_date desc", limit=BOUNCE_WINDOW)
    groups = project_rows("management", GROUP,
                          ["name", "student_group_name", "program", "academic_year",
                           "max_strength", "course", "disabled", "th_class_status"],
                          filters={"disabled": 0}, order_by="student_group_name asc",
                          limit=LIMIT_QUEUES)
    cohorts = open_cohort_keys(groups)
    unclassed = [row for row in enrollments
                 if (row.get("program"), row.get("academic_year")) not in cohorts]

    now = now_datetime()
    overdue_deadlines = []
    for row in attempts_running:
        if row.get("deadline_at"):
            try:
                from frappe.utils import get_datetime
                if get_datetime(row["deadline_at"]) < now:
                    overdue_deadlines.append(row)
            except Exception:
                continue

    funnel_facts = [
        {"label": "Placement sessions running",
         "definition": "Attempts from Allocated through Review.",
         "value": len(attempts_running), "owner": "Placement Invigilator"},
        {"label": "Results awaiting release",
         "definition": "Finalized attempts with no released decision yet.",
         "value": len(awaiting_release), "owner": "Placement Releaser"},
        {"label": "Admissions in Draft",
         "definition": "Admission decisions in Draft.",
         "value": sum(1 for row in admissions_open if row["status"] == "Draft"),
         "owner": "Admission Reviewer"},
        {"label": "Admissions in review",
         "definition": "Admission decisions in Review.",
         "value": len(review_waiting), "owner": "Admission Approver"},
        {"label": "Enrollments awaiting a class",
         "definition": "Submitted enrollments whose level and academic year have no class planned or running yet.",
         "value": len(unclassed), "owner": "Teaching Scheduler"},
        {"label": "Classes running",
         "definition": "Classes whose lifecycle is Active (planned classes are counted under enrollment coverage instead).",
         "value": len(active_cohort_rows(groups)), "owner": "Teaching Scheduler"},
        {"label": "Corrections pending",
         "definition": "Correction requests (invoice or tuition fee) in Requested status.",
         "value": len(corrections), "owner": "Finance Officer"},
    ]

    exception_items = []
    for row in review_waiting:
        exception_items.append({
            "id": row["name"],
            "person": row.get("student_applicant") or "",
            "detail": row.get("program") or "",
            "status": "Review",
            "stage": "Admission waiting in review",
            "stage_definition": "The admission decision has been in review longest; work it or escalate it.",
            "next": "Record the admission outcome.",
            "next_role": "Admission Approver",
            "waiting_since": row.get("modified"),
            "age": _age_label(row.get("modified")),
        })
    for row in overdue_deadlines:
        exception_items.append({
            "id": row["name"],
            "person": row.get("case_name") or "",
            "detail": "Placement attempt",
            "status": row["status"],
            "stage": "Attempt past deadline",
            "stage_definition": "A running placement attempt is past its server-set deadline; the next save seals it as Timeout.",
            "next": "Seal the attempt and continue the marking workflow.",
            "next_role": "Placement Invigilator",
            "waiting_since": row.get("deadline_at"),
            "age": _age_label(row.get("deadline_at")),
        })
    for row in corrections:
        # A correction names whatever it targets: the invoice or the
        # tuition-fee document — never an empty row for the fees leg (D6).
        is_fees = bool(row.get("fees"))
        target = row.get("fees") if is_fees else row.get("sales_invoice")
        reason = row.get("reason") or ""
        exception_items.append({
            "id": row["name"],
            "person": target or row["name"],
            "detail": ("Tuition-fee correction" if is_fees else "Invoice correction")
                      + (f" · {reason}" if reason else ""),
            "status": row["status"],
            "stage": "Correction pending",
            "stage_definition": (
                "A tuition-fee correction request is waiting for the policy-"
                "configured approver." if is_fees else
                "An invoice correction request is waiting for the policy-"
                "configured approver."),
            "next": "Approve or deny the correction.",
            "next_role": "Finance Officer",
            "waiting_since": row.get("modified"),
            "age": _age_label(row.get("modified")),
        })

    staff_counts = _staff_counts()
    desks_for_viewer = []
    held = viewer_roles()
    for slug, spec in DESKS.items():
        if slug == SLUG:
            continue
        if set(spec["roles"]) & held:
            desks_for_viewer.append({"slug": slug, "title": spec["title"]})

    return {
        "desk": SLUG,
        "title": DESKS[SLUG]["title"],
        "sections": [
            section("funnel", "Operation funnel", "facts", facts=funnel_facts,
                    empty_title="No operational records yet",
                    empty_body="Nothing is running in the placement, admission, enrollment or finance pipeline."),
            section("exceptions", "Exceptions and oldest waiting work", "queue",
                    items=exception_items,
                    empty_title="No exceptions",
                    empty_body="Nothing is overdue, stuck or waiting on an approver right now."),
            section("staffing", "Role coverage", "queue", items=_role_items(staff_counts),
                    empty_title="No operational roles",
                    empty_body="No shipped operational role is assigned to an enabled user."),
            section("desks", "Your desks", "links", items=desks_for_viewer,
                    empty_title="No other desks for your account",
                    empty_body="This account holds only the General Manager desk."),
        ],
    }

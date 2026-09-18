"""Academic Manager desk: the academic operations cockpit.

Read-only aggregation over the placement, admission, enrollment and teaching
records the qualified slices already run on. Sections and data sources are
specified in docs/product/ROLE-DESKS.md.
"""
import frappe
from frappe.utils import now_datetime, today

from toefl_house.desk import (
    BOUNCE_WINDOW,
    DESKS,
    LIMIT_QUEUES,
    guided_action,
    project_count,
    project_rows,
    require_desk_audience,
    section,
)
from toefl_house.desk import lifecycle

SLUG = "th-academic-desk"

ATTEMPT = "TH Placement Attempt"
DECISION = "TH Placement Decision"
ADMISSION = "TH Admission Decision"
GROUP = "Student Group"
SCHEDULE = "Course Schedule"
ASSIGNMENT = "TH Teaching Assignment"
ATTENDANCE = "Student Attendance"
ENROLLMENT = "Program Enrollment"

ADMISSION_FIELDS = ["name", "student_applicant", "program", "academic_year",
                    "status", "accepted", "native_student", "version", "modified",
                    "drafted_by"]


def _admission_queue(admissions):
    items = []
    for row in admissions:
        stage = lifecycle.admission_stage(
            row["status"], bool(row.get("accepted")), bool(row.get("native_student")))
        item = {
            "id": row["name"],
            "person": row.get("student_applicant") or "",
            "detail": row.get("program") or "",
            "status": row["status"],
            "stage": stage["label"],
            "stage_definition": stage["definition"],
            "next": stage["next"],
            "next_role": stage["role"],
            "waiting_since": row.get("modified"),
        }
        prefills = {
            "review_admission": ("Admission Reviewer", "toefl_house.admission.review_admission",
                                 "Send for review", {"name": row["name"], "expected_version": row["version"]}),
            "decide_admission": ("Admission Approver", "toefl_house.admission.decide_admission",
                                 "Record outcome", {"name": row["name"], "expected_version": row["version"]}),
            "accept_offer": ("Admission Officer", "toefl_house.admission.accept_offer",
                             "Accept offer", {"name": row["name"], "expected_version": row["version"]}),
            "convert_applicant": ("Admission Approver", "toefl_house.admission.convert_applicant",
                                  "Convert to Student", {"name": row["name"], "expected_version": row["version"]}),
        }
        if stage["command"] in prefills:
            role, endpoint, label, args = prefills[stage["command"]]
            item["action"] = guided_action(role, endpoint, label, args)
        items.append(item)
    return items


@frappe.whitelist(methods=["GET", "POST"])
def work():
    """Academic desk payload: academic queues, classes, sessions, workload."""
    require_desk_audience(SLUG)
    day = today()

    # --- admissions awaiting an academic decision --------------------------
    admissions = project_rows("academic", ADMISSION, ADMISSION_FIELDS,
                              filters={"status": ("in", ["Draft", "Review"])},
                              order_by="modified asc", limit=LIMIT_QUEUES)
    offers = project_rows("academic", ADMISSION, ADMISSION_FIELDS,
                          filters={"status": ("in", ["Approved", "Conditional"]), "accepted": 0},
                          order_by="modified asc", limit=LIMIT_QUEUES)
    conversions = project_rows("academic", ADMISSION, ADMISSION_FIELDS,
                               filters={"status": ("in", ["Approved", "Conditional"]),
                                        "accepted": 1, "native_student": ("is", "not set")},
                               order_by="modified asc", limit=LIMIT_QUEUES)

    # --- placement pipeline -------------------------------------------------
    finalized_waiting = project_rows(
        "academic", ATTEMPT,
        ["name", "case_name", "ordinal", "status", "version", "mode", "deadline_at"],
        filters={"status": "Finalized"},
        order_by="modified asc", limit=LIMIT_QUEUES)
    released = project_rows("academic", DECISION,
                            ["name", "attempt", "status", "released_at", "expires_at",
                             "course_code", "internal_level"],
                            filters={"status": "Released"},
                            order_by="released_at desc", limit=BOUNCE_WINDOW)
    released_attempts = {row["attempt"] for row in released if row.get("attempt")}
    awaiting_release = [row for row in finalized_waiting if row["name"] not in released_attempts]

    # --- classes and today's sessions ---------------------------------------
    groups = project_rows("academic", GROUP,
                          ["name", "student_group_name", "program", "academic_year",
                           "max_strength", "course", "active"],
                          filters={"active": 1}, order_by="student_group_name asc",
                          limit=LIMIT_QUEUES)
    sessions = project_rows("academic", SCHEDULE,
                            ["name", "student_group", "instructor", "course", "room",
                             "from_time", "to_time", "schedule_date"],
                            filters={"schedule_date": day},
                            order_by="from_time asc", limit=LIMIT_QUEUES)
    assignments = project_rows("academic", ASSIGNMENT,
                               ["name", "student_group", "skill", "instructor", "contract",
                                "course_schedule", "effective_start", "effective_end"],
                               order_by="modified desc", limit=LIMIT_QUEUES)

    # --- enrollment -> cohort coverage (facts) ------------------------------
    enrollments = project_rows("academic", ENROLLMENT,
                               ["name", "student", "student_name", "program",
                                "academic_year", "enrollment_date", "docstatus"],
                               filters={"docstatus": 1},
                               order_by="enrollment_date desc", limit=BOUNCE_WINDOW)
    cohorts = {(row["program"], row.get("academic_year")) for row in groups}
    unclassed = [row for row in enrollments
                 if (row.get("program"), row.get("academic_year")) not in cohorts]

    attendance_facts = _attendance_window(groups)

    funnel_facts = [
        {"label": "Placement attempts running",
         "definition": "Attempts from Allocated through Review.",
         "value": project_count("academic", ATTEMPT, {
             "status": ("in", [s for s in lifecycle.PLACEMENT_ATTEMPT_ORDER if s != "Finalized"])}),
         "owner": "Placement Invigilator"},
        {"label": "Finalized, awaiting release",
         "definition": "Finalized attempts with no released decision yet.",
         "value": len(awaiting_release), "owner": "Placement Releaser"},
        {"label": "Admissions drafted",
         "definition": "Admission decisions in Draft.",
         "value": project_count("academic", ADMISSION, {"status": "Draft"}),
         "owner": "Admission Reviewer"},
        {"label": "Admissions in review",
         "definition": "Admission decisions in Review.",
         "value": project_count("academic", ADMISSION, {"status": "Review"}),
         "owner": "Admission Approver"},
        {"label": "Offers to accept",
         "definition": "Approved or Conditional decisions not yet accepted.",
         "value": project_count("academic", ADMISSION,
                                {"status": ("in", ["Approved", "Conditional"]), "accepted": 0}),
         "owner": "Admission Officer"},
        {"label": "Active cohorts",
         "definition": "Active Student Group records.",
         "value": len(groups), "owner": "Teaching Scheduler"},
        {"label": "Enrollments without a cohort",
         "definition": "Submitted Program Enrollments whose program and academic year have no active Student Group.",
         "value": len(unclassed), "owner": "Teaching Scheduler"},
    ]

    release_items = [{
        "id": row["name"],
        "person": row.get("case_name") or row["name"],
        "detail": f"Attempt {row.get('ordinal', '')}".strip(),
        "status": row["status"],
        "stage": "Awaiting release",
        "stage_definition": "The attempt is finalized; the placement decision has not been released.",
        "next": "Release the placement decision.",
        "next_role": "Placement Releaser",
        "waiting_since": None,
        "action": guided_action("Placement Releaser", "toefl_house.api.release_decision",
                                "Release decision", {"attempt": row["name"],
                                                     "expected_version": row["version"]}),
    } for row in awaiting_release]

    session_items = [{
        "id": row["name"],
        "person": row.get("student_group") or "",
        "detail": " · ".join(part for part in (row.get("course"), row.get("room"),
                                               row.get("instructor")) if part),
        "status": f"{row.get('from_time', '')}–{row.get('to_time', '')}",
        "stage": "Session today",
        "stage_definition": "Scheduled course session for today.",
        "next": "Record attendance after the session.",
        "next_role": "Attendance Recorder",
        "waiting_since": None,
        "action": None,
    } for row in sessions]

    cohort_items = [{
        "id": row["name"],
        "person": row.get("student_group_name") or row["name"],
        "detail": " · ".join(part for part in (row.get("program"),
                                               row.get("academic_year"),
                                               row.get("course")) if part),
        "status": f"max {row.get('max_strength', '')}" if row.get("max_strength") else "",
        "stage": "Active cohort",
        "stage_definition": "Active Student Group.",
        "next": "Check the roster before the next session.",
        "next_role": "Teaching Scheduler",
        "waiting_since": None,
        "action": None,
    } for row in groups]

    assignment_items = [{
        "id": row["name"],
        "person": row.get("instructor") or "",
        "detail": " · ".join(part for part in (row.get("student_group"), row.get("skill")) if part),
        "status": row.get("effective_end") or "open",
        "stage": "Teaching assignment",
        "stage_definition": "Skill assignment fact from the teaching compensation slice.",
        "next": "Review the assignment when a term or schedule changes.",
        "next_role": "Teaching Scheduler",
        "waiting_since": row.get("effective_start"),
        "action": None,
    } for row in assignments]

    return {
        "desk": SLUG,
        "title": DESKS[SLUG]["title"],
        "sections": [
            section("funnel", "Academic funnel", "facts", facts=funnel_facts,
                    empty_title="Nothing in the academic pipeline",
                    empty_body="No attempts, admissions or cohorts exist yet. Records appear here as the placement and admission workflows advance."),
            section("admissions", "Admissions waiting on academic action", "queue",
                    items=_admission_queue(admissions) + _admission_queue(offers) + _admission_queue(conversions),
                    empty_title="No admission needs an academic action",
                    empty_body="Nothing is waiting for review, outcome, acceptance or conversion right now."),
            section("release", "Placement results awaiting release", "queue",
                    items=release_items,
                    empty_title="Nothing is awaiting release",
                    empty_body="Every finalized attempt already has its released decision."),
            section("sessions", "Sessions today", "queue", items=session_items,
                    empty_title="No sessions scheduled today",
                    empty_body="Course Schedule has no sessions for today. Schedule one from the Teaching Scheduling page."),
            section("cohorts", "Active cohorts", "queue", items=cohort_items,
                    empty_title="No active cohorts",
                    empty_body="No active Student Group exists yet. Create one from the Teaching Scheduling page once enrollments exist."),
            section("assignments", "Teaching assignments", "queue", items=assignment_items,
                    empty_title="No teaching assignments",
                    empty_body="No skill assignment exists yet. Assign instructors to cohorts from the Teaching Scheduling page."),
            section("attendance", "Attendance, last 30 days", "facts", facts=attendance_facts,
                    empty_title="No attendance recorded yet",
                    empty_body="Attendance facts appear after the first session is recorded."),
        ],
    }



def _attendance_window(groups):
    """Recent attendance facts per cohort: recorded vs absent, last 30 days.

    Facts only. Any threshold ("how many absences are too many") is an owner
    decision and is deliberately not computed here.
    """
    from datetime import timedelta
    since = now_datetime() - timedelta(days=30)
    facts = []
    for group in groups[:10]:
        recorded = project_count("academic", ATTENDANCE, {
            "student_group": group["name"], "date": (">=", since.date()), "docstatus": 1})
        if not recorded:
            continue
        absent = project_count("academic", ATTENDANCE, {
            "student_group": group["name"], "date": (">=", since.date()),
            "status": "Absent", "docstatus": 1})
        facts.append({
            "label": group.get("student_group_name") or group["name"],
            "definition": f"Submitted attendance rows in the last 30 days: {recorded}. Absent: {absent}.",
            "value": absent,
            "owner": "Attendance Recorder",
        })
    return facts

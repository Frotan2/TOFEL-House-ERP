"""Instructor desk: a teacher's own daily work, nothing else.

Audience: the Instructor role. Identity resolves through the NATIVE chain
only — session User -> Employee.user_id -> Instructor.employee -> teaching
assignments (Employee.user_id at erpnext 4048fb70, Instructor.employee at
education 93bc707, and create_teaching_contract refuses any contract whose
employee is not the instructor's own). There is no invented link: a viewer
who holds the role but resolves to no instructor gets an explicit empty
state naming the missing link, never another teacher's classes.

Sections follow the daily path: My Classes -> Today -> Sessions &
attendance -> Students -> Academic work -> Compensation facts. Money facts
are identity-and-window only (ROLE-DESKS: no rates, no payable amounts, no
payroll rows); recorded assessment rows are shown as recorded, while
grading policy itself stays the owner decision D1.
"""
import frappe
from frappe.utils import today

from toefl_house.desk import (
    BOUNCE_WINDOW,
    DESKS,
    LIMIT_QUEUES,
    cohort_state,
    guided_action,
    project_rows,
    require_desk_audience,
    section,
)

SLUG = "th-teacher-desk"

EMPLOYEE = "Employee"
INSTRUCTOR = "Instructor"
ASSIGNMENT = "TH Teaching Assignment"
SKILL = "TH Skill"
GROUP = "Student Group"
SCHEDULE = "Course Schedule"
ROSTER = "Student Group Student"
ATTENDANCE = "Student Attendance"
RESULT = "Assessment Result"
CONTRACT = "TH Instructor Contract"

ASSIGNMENT_FIELDS = ["name", "student_group", "skill", "instructor", "contract",
                     "course_schedule", "effective_start", "effective_end"]
GROUP_FIELDS = ["name", "student_group_name", "program", "academic_year",
                "max_strength", "course", "disabled", "th_class_status"]
SCHEDULE_FIELDS = ["name", "student_group", "instructor", "course", "room",
                   "from_time", "to_time", "schedule_date"]


def _resolve_instructor(user):
    """The instructor natively linked to this login, or None.

    Employee must be Active (the same rule create_teaching_contract
    enforces); the instructor row is matched by its native employee link
    and surfaced with its verbatim status — no status vocabulary invented.
    """
    employees = project_rows("teacher", EMPLOYEE,
                             ["name", "employee_name", "status", "user_id"],
                             filters={"user_id": user, "status": "Active"},
                             order_by="name asc", limit=1)
    if not employees:
        return None, None
    employee = employees[0]
    instructors = project_rows("teacher", INSTRUCTOR,
                               ["name", "instructor_name", "employee", "status"],
                               filters={"employee": employee["name"]},
                               order_by="name asc", limit=1)
    if not instructors:
        return employee, None
    return employee, instructors[0]


def _unlinked_payload():
    """Fail-closed empty state: the role is held, the link is missing."""
    body = ("This login holds the Instructor role but is not linked to an "
            "instructor record: either no active employee points at this "
            "login, or no instructor points at that employee. Ask the Course "
            "Owner to link the employee login and the instructor record; "
            "until then no class is shown.")
    return {
        "desk": SLUG,
        "title": DESKS[SLUG]["title"],
        "sections": [
            section("classes", "My classes", "queue", items=[],
                    empty_title="No instructor link on this login",
                    empty_body=body),
            section("today", "Today", "queue", items=[],
                    empty_title="No instructor link on this login",
                    empty_body=body),
        ],
    }


@frappe.whitelist(methods=["GET", "POST"])
def work():
    """Teacher desk payload: my classes, today, attendance, students, work, pay facts."""
    require_desk_audience(SLUG)
    user = frappe.session.user
    _, instructor = _resolve_instructor(user)
    if not instructor:
        return _unlinked_payload()
    day = today()

    assignments = project_rows("teacher", ASSIGNMENT, ASSIGNMENT_FIELDS,
                               filters={"instructor": instructor["name"]},
                               order_by="effective_start asc",
                               limit=BOUNCE_WINDOW)
    group_names = sorted({row["student_group"] for row in assignments
                          if row.get("student_group")})
    groups = []
    if group_names:
        groups = project_rows("teacher", GROUP, GROUP_FIELDS,
                              filters={"name": ("in", group_names)},
                              order_by="student_group_name asc",
                              limit=BOUNCE_WINDOW)
    groups_by_name = {row["name"]: row for row in groups}
    skill_names = sorted({row["skill"] for row in assignments if row.get("skill")})
    skills = {}
    if skill_names:
        for row in project_rows("teacher", SKILL,
                                ["name", "code", "title", "status"],
                                filters={"name": ("in", skill_names)},
                                order_by="title asc", limit=BOUNCE_WINDOW):
            skills[row["name"]] = row.get("title") or row.get("code") or row["name"]

    sessions_today = []
    recent_sessions = []
    if group_names:
        sessions_today = project_rows(
            "teacher", SCHEDULE, SCHEDULE_FIELDS,
            filters={"student_group": ("in", group_names), "schedule_date": day},
            order_by="from_time asc", limit=LIMIT_QUEUES)
        recent_sessions = project_rows(
            "teacher", SCHEDULE, SCHEDULE_FIELDS,
            filters={"student_group": ("in", group_names)},
            order_by="schedule_date desc", limit=LIMIT_QUEUES)

    roster = []
    if group_names:
        roster = project_rows("teacher", ROSTER,
                              ["name", "parent", "student", "student_name",
                               "group_roll_number", "active"],
                              filters={"parent": ("in", group_names)},
                              order_by="group_roll_number asc",
                              limit=BOUNCE_WINDOW)
    roster_by_group = {}
    for row in roster:
        roster_by_group.setdefault(row.get("parent"), []).append(row)

    session_names = [row["name"] for row in recent_sessions]
    attendance_by_session = {}
    if session_names:
        for row in project_rows("teacher", ATTENDANCE,
                                ["name", "student", "student_group",
                                 "course_schedule", "date", "status",
                                 "docstatus"],
                                filters={"course_schedule": ("in", session_names),
                                         "docstatus": 1},
                                order_by="date desc", limit=BOUNCE_WINDOW):
            attendance_by_session.setdefault(row.get("course_schedule"), []).append(row)

    results = []
    if group_names:
        results = project_rows("teacher", RESULT,
                               ["name", "student", "student_name", "student_group",
                                "course", "total_score", "maximum_score",
                                "grade", "docstatus"],
                               filters={"student_group": ("in", group_names)},
                               order_by="creation desc", limit=LIMIT_QUEUES)

    contracts = project_rows("teacher", CONTRACT,
                             ["name", "instructor", "employee",
                              "compensation_model", "assignment_basis",
                              "payment_frequency", "effective_start",
                              "effective_end", "status"],
                             filters={"instructor": instructor["name"]},
                             order_by="effective_start desc",
                             limit=LIMIT_QUEUES)

    class_items = []
    for row in assignments:
        group = groups_by_name.get(row.get("student_group")) or {}
        state = cohort_state(group) if group else "Unknown"
        members = roster_by_group.get(row.get("student_group"), [])
        active_members = [member for member in members
                          if int(member.get("active") or 0)]
        skill_title = skills.get(row.get("skill")) or row.get("skill") or ""
        window = " – ".join(part for part in (str(row.get("effective_start") or ""),
                                              str(row.get("effective_end") or "open"))
                            if part)
        class_items.append({
            "id": row["name"],
            "person": group.get("student_group_name") or row.get("student_group") or "",
            "detail": " · ".join(part for part in (
                group.get("program") or "", group.get("academic_year") or "",
                skill_title) if part),
            "status": state,
            "stage": "My class",
            "stage_definition": ("A class this instructor is assigned to, with its "
                               "lifecycle state and roster size. Closed classes stay "
                               "listed so past work is visible."),
            "next": ("Check today's sessions below." if state == "Active"
                     else "No action; this class is not running."),
            "next_role": None,
            "waiting_since": row.get("effective_start"),
            "members": f"{len(active_members)} on the roster"
                       + (f" (capacity {group.get('max_strength')})"
                          if group.get("max_strength") else ""),
            "window": window,
        })

    today_items = []
    for row in sessions_today:
        group = groups_by_name.get(row.get("student_group")) or {}
        marked = attendance_by_session.get(row["name"], [])
        absent = sum(1 for entry in marked if entry.get("status") == "Absent")
        item = {
            "id": row["name"],
            "person": group.get("student_group_name") or row.get("student_group") or "",
            "detail": " · ".join(part for part in (row.get("course"),
                                                 row.get("room")) if part),
            "status": f"{row.get('from_time', '')}–{row.get('to_time', '')}",
            "stage": "Session today",
            "stage_definition": "A scheduled session for one of my classes today.",
            "next": ("Attendance is recorded "
                     f"({len(marked)} marked, {absent} absent)."
                     if marked else "Record attendance after the session."),
            "next_role": "Attendance Recorder" if not marked else None,
            "waiting_since": None,
        }
        if not marked:
            action = guided_action("Attendance Recorder",
                                   "toefl_house.teaching.record_attendance",
                                   "Record attendance",
                                   {"course_schedule": row["name"]})
            if action:
                item["action"] = action
        today_items.append(item)

    session_items = []
    for row in recent_sessions:
        group = groups_by_name.get(row.get("student_group")) or {}
        marked = attendance_by_session.get(row["name"], [])
        absent = sum(1 for entry in marked if entry.get("status") == "Absent")
        item = {
            "id": row["name"],
            "person": group.get("student_group_name") or row.get("student_group") or "",
            "detail": " · ".join(part for part in (str(row.get("schedule_date") or ""),
                                                 row.get("course") or "") if part),
            "status": (f"{len(marked)} marked, {absent} absent" if marked
                       else "not recorded"),
            "stage": "Session",
            "stage_definition": ("A scheduled session with its recorded attendance. "
                               "Only submitted attendance rows count."),
            "next": ("No action." if marked else "Record attendance for this session."),
            "next_role": None if marked else "Attendance Recorder",
            "waiting_since": str(row.get("schedule_date") or "") or None,
        }
        if not marked:
            action = guided_action("Attendance Recorder",
                                   "toefl_house.teaching.record_attendance",
                                   "Record attendance",
                                   {"course_schedule": row["name"]})
            if action:
                item["action"] = action
        session_items.append(item)

    student_items = []
    for row in roster:
        group = groups_by_name.get(row.get("parent")) or {}
        student_items.append({
            "id": row["name"],
            "person": row.get("student_name") or row.get("student") or "",
            "detail": " · ".join(part for part in (
                group.get("student_group_name") or "",
                f"roll {row.get('group_roll_number')}" if row.get("group_roll_number") else "") if part),
            "status": "on the roster" if int(row.get("active") or 0) else "inactive",
            "stage": "Student",
            "stage_definition": "A student on one of my class rosters.",
            "next": "No action.",
            "next_role": None,
            "waiting_since": None,
        })

    work_items = []
    for row in results:
        state = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(
            int(row.get("docstatus") or 0), "Draft")
        score = row.get("total_score")
        maximum = row.get("maximum_score")
        work_items.append({
            "id": row["name"],
            "person": row.get("student_name") or row.get("student") or "",
            "detail": " · ".join(part for part in (row.get("course") or "",
                                                 f"grade {row['grade']}" if row.get("grade") else "") if part),
            "status": state,
            "stage": "Recorded result",
            "stage_definition": ("A recorded assessment result for one of my classes, "
                               "shown exactly as recorded. Grading policy is an owner "
                               "decision; this desk states no thresholds."),
            "next": "No action.",
            "next_role": None,
            "waiting_since": None,
            "score": f"{score} of {maximum}" if score is not None and maximum else "",
        })

    pay_items = []
    for row in contracts:
        window = " – ".join(part for part in (str(row.get("effective_start") or ""),
                                              str(row.get("effective_end") or "open"))
                            if part)
        pay_items.append({
            "id": row["name"],
            "person": row.get("compensation_model") or "",
            "detail": " · ".join(part for part in (row.get("assignment_basis") or "",
                                                 row.get("payment_frequency") or "",
                                                 window) if part),
            "status": row.get("status") or "",
            "stage": "Compensation fact",
            "stage_definition": ("A teaching contract identity and window. Pay runs "
                               "through native payroll; this desk does not calculate "
                               "pay and shows no rates or amounts."),
            "next": "No action.",
            "next_role": None,
            "waiting_since": row.get("effective_start"),
        })

    return {
        "desk": SLUG,
        "title": DESKS[SLUG]["title"],
        "sections": [
            section("classes", "My classes", "queue", items=class_items,
                    empty_title="No classes assigned",
                    empty_body="No teaching assignment names this instructor. Assignments appear here from teaching scheduling."),
            section("today", "Today", "queue", items=today_items,
                    empty_title="No sessions today",
                    empty_body="Nothing is scheduled for my classes today."),
            section("sessions", "Sessions and attendance", "queue", items=session_items,
                    empty_title="No sessions yet",
                    empty_body="Scheduled sessions for my classes appear here with their recorded attendance."),
            section("students", "Students", "queue", items=student_items,
                    empty_title="No students on my rosters",
                    empty_body="Students appear here once class rosters are set."),
            section("work", "Academic work", "queue", items=work_items,
                    empty_title="No recorded results",
                    empty_body="Recorded assessment results for my classes appear here exactly as recorded."),
            section("compensation", "Compensation facts", "queue", items=pay_items,
                    empty_title="No contracts on file",
                    empty_body="Teaching contracts for this instructor appear here as identity and window facts; pay itself stays on native payroll."),
        ],
    }

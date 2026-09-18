"""Thin teaching operations over native Education scheduling and attendance.

Native authorities: Student Group (class roster), Course Schedule (session)
and Student Attendance (participation record). This module owns no roster,
timetable, grading, assessment, invoice, attendance ledger or payroll record.
Academic assessment/progression (B04/B05), fees (B07) and payroll (A09)
remain outside this slice and are not activated by it.

Class lifecycle is modelled as thin Custom Fields on Student Group
(th_class_start_date, th_class_end_date, th_delivery_mode, th_branch,
th_class_status) — no competing TH Class / TH Cohort DocType is introduced.

Owner policy for class amendments after creation is NOT yet decided. The
controller therefore fails-closed on all class-fact edits after insert:
only the explicit ``transition_class`` command may change ``th_class_status``
(and only through the legal state machine). Changes to start date, end date,
delivery mode, or branch after creation require an explicit owner amendment
policy and are deliberately refused until then — no silent ad-hoc Desk edit,
API call, or script may rewrite class facts.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta
import frappe
from toefl_house.api import _execute
from toefl_house.academic.rules import resolve_duration
from toefl_house.policy import (DELIVERY_MODES, digest, is_valid_class_transition,
                                validate_attendance_statuses, validate_capacity,
                                validate_class_status, validate_delivery_mode,
                                validate_group_name, validate_schedule_date,
                                validate_session_window)
from toefl_house.security import active_command_kind, require_synthetic, teaching_command_active

GROUP = "Student Group"
SCHEDULE = "Course Schedule"
ATTENDANCE = "Student Attendance"
PROGRAM = "Program"
LEVEL = "TH Program Level"
YEAR = "Academic Year"
TERM = "Academic Term"
DURATION_UNIT_TO_KWARGS = {"Month": "months", "Week": "weeks", "Day": "days"}
# Class lifecycle facts. These are NOT free-form editable metadata.
CLASS_FACT_FIELDS = ("th_class_start_date", "th_class_end_date", "th_delivery_mode",
                     "th_branch", "th_class_status")


@frappe.whitelist()
def active_skills():
    """Return Active TH Skill codes (read-only lookup for command pages).

    This is a read-only, permission-gated projection; readers (GM/AM/FM/FO/FA/
    TS/TA/Course Owner) already hold Select on TH Skill via the permission
    table, but the command pages deliberately avoid Link searches. Anyone who
    can reach the teaching-scheduling page may read the active vocabulary.
    """
    if not any(frappe.has_role(r) for r in
               ("Course Owner", "General Manager", "Academic Manager",
                "Finance Manager", "Finance Officer", "Finance Auditor",
                "Teaching Scheduler", "Teaching Auditor")):
        raise frappe.PermissionError("Active skills are not available to your role")
    rows = frappe.get_all("TH Skill", filters={"status": "Active"},
                          fields=["code", "title"], order_by="code asc")
    return [{"code": r["code"], "title": r["title"]} for r in rows]


def guard_student_group(doc, method=None):
    """Command-only containment for native Student Group.

    Two guarantees hold under all save paths (native form, REST, Python API,
    bulk edit, background jobs, etc., even with ``ignore_permissions=True``):

    1. A Student Group may never be inserted or modified outside an
       active Teaching Scheduler command (create_student_group or
       transition_class).
    2. After insert, class-fact fields (dates, delivery mode, branch, status)
       are immutable except for the controlled status transition applied by
       transition_class. Amendments to end date / delivery mode / branch
       require an explicit owner policy and are refused until then — this
       module will not silently invent an amendment pathway.
    """
    require_synthetic()
    if teaching_command_active(GROUP):
        _enforce_class_fact_invariants(doc)
        return
    raise frappe.ValidationError("Student Group requires an authorized teaching command")


def _enforce_class_fact_invariants(doc):
    """Enforce the immutable-command-fact contract on Student Group saves.

    On insert, all class facts must be set with valid values (Planned status,
    valid delivery mode, valid start/end dates, end >= start).
    After insert, only transition_class may write to th_class_status and
    only through the legal state machine. All other class-fact fields are
    immutable after creation until the owner defines an amendment policy.
    """
    before = doc.get_doc_before_save()
    if before is None:
        # Insert path: enforced by create_student_group directly; re-validate
        # invariants defensively here in case any future command writes groups.
        _validate_class_facts_on_insert(doc)
        return

    kind = active_command_kind()
    allowed_status_change = (kind == "transition_class")
    for field in CLASS_FACT_FIELDS:
        new_value = doc.get(field)
        old_value = before.get(field)
        if _equal_values(old_value, new_value):
            continue
        if field == "th_class_status" and allowed_status_change:
            if not is_valid_class_transition(old_value or "Planned", new_value):
                raise frappe.ValidationError(
                    f"Illegal class transition: {old_value} → {new_value}")
            continue
        raise frappe.ValidationError(
            f"Class fact {field} is immutable after creation. Amendments to end date, "
            "delivery mode, branch or start date require an explicit owner policy "
            "(no ad-hoc edits permitted).")


def _equal_values(a, b):
    if a is None and b in (None, "", False, 0):
        return True
    if b is None and a in (None, "", False, 0):
        return True
    return str(a) == str(b)


def _validate_class_facts_on_insert(doc):
    status = doc.th_class_status or "Planned"
    if status != "Planned":
        raise frappe.ValidationError("New classes must start in Planned status")
    mode = doc.th_delivery_mode
    if mode not in DELIVERY_MODES:
        raise frappe.ValidationError(f"Invalid delivery mode: {mode}")
    start = doc.th_class_start_date
    end = doc.th_class_end_date
    if not start or not end or str(end) < str(start):
        raise frappe.ValidationError("Class end date must be on or after start date")
    if doc.th_branch and not frappe.db.exists("Branch", doc.th_branch):
        # Branch is operational scope only; never carries policy configuration.
        raise frappe.ValidationError("Unknown branch")
    # Clear any supplied status outside the enum (belt-and-braces).
    doc.th_class_status = status


def guard_course_schedule(doc, method=None):
    require_synthetic()
    if teaching_command_active(SCHEDULE):
        return
    raise frappe.ValidationError("Course Schedule requires an authorized teaching command")


def guard_student_attendance(doc, method=None):
    require_synthetic()
    if teaching_command_active(ATTENDANCE):
        return
    raise frappe.ValidationError("Student Attendance requires an authorized teaching command")


@contextmanager
def _roster_read():
    """StudentAttendance.validate_student calls get_student_group_students.

    That helper enforces a Desk read permission on Student Group which the
    Attendance Recorder must not hold (no native CRUD roles are granted).
    Patch only the module-level reference for this command; never switch the
    session user or relax frappe.has_permission.
    """
    from education.education.doctype.student_attendance import student_attendance as native

    original = native.get_student_group_students

    def roster(student_group, include_inactive=0):
        return frappe.db.sql(
            "select student, student_name from `tabStudent Group Student` where parent=%s",
            (student_group,), as_dict=True)

    native.get_student_group_students = roster
    try:
        yield
    finally:
        native.get_student_group_students = original


def _bounded_name(value, label):
    if not isinstance(value, str) or not value or len(value) > 140:
        raise frappe.ValidationError(f"{label} required")
    return value


def _suggested_end_date(start_date_str, program_name):
    """Resolve the governing TH Level Duration from the level anchored to this
    native Program and compute a suggested end date (a planning default only;
    the user-entered actual end date is what gets stored on the class).
    Returns None if no duration governs — the caller must supply an end date.
    """
    level_name = frappe.db.get_value(LEVEL, {"native_program": program_name}, "name")
    if not level_name:
        return None
    level = frappe.get_doc(LEVEL, level_name)
    versions = [dict(row) for row in (level.get("durations") or [])]
    governing = resolve_duration(versions, start_date_str)
    if not governing:
        return None
    try:
        start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    unit = str(governing.get("duration_unit") or "")
    value = float(governing.get("duration_value") or 0)
    if unit not in DURATION_UNIT_TO_KWARGS or value <= 0:
        return None
    kwargs = {DURATION_UNIT_TO_KWARGS[unit]: value}
    # dateutil.relativedelta is the right tool but we avoid adding a dependency:
    # approximate month addition by stepping calendar months manually.
    if unit == "Month":
        month = start.month - 1 + int(value)
        year = start.year + month // 12
        month = month % 12 + 1
        # clamp day to end of month if needed
        from calendar import monthrange
        day = min(start.day, monthrange(year, month)[1])
        return start.replace(year=year, month=month, day=day).isoformat()
    return (start + timedelta(**kwargs)).isoformat()


@frappe.whitelist(methods=["POST"])
def create_student_group(request_key, group_name, program, academic_year, academic_term="",
                         max_strength=0, class_start_date=None, class_end_date=None,
                         delivery_mode="On-site", branch=""):
    """Roster a class strictly from submitted native Program Enrollments.

    The roster is derived from the native enrollment ledger (no manual student
    lists are accepted), so an unenrolled learner cannot enter a class.
    Capacity and duplicate students remain native Student Group validations.

    The class is created in Planned status. The governing TH Level Duration is
    used only to suggest a default class end date when one is not supplied;
    the actual dates stored are operational facts and will not be rewritten by
    later policy changes.
    """
    def work(actor):
        try:
            name = validate_group_name(group_name)
            capacity = validate_capacity(max_strength)
            start = validate_schedule_date(class_start_date) if class_start_date else frappe.utils.today()
            mode = validate_delivery_mode(delivery_mode)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        program_name = _bounded_name(program, "Program")
        year_name = _bounded_name(academic_year, "Academic Year")
        term_name = _bounded_name(academic_term, "Academic Term") if academic_term else ""
        branch_name = ""
        if branch:
            branch_name = _bounded_name(branch, "Branch")
            if not frappe.db.exists("Branch", branch_name):
                raise frappe.ValidationError("Unknown branch")
        if not frappe.db.exists(PROGRAM, program_name):
            raise frappe.ValidationError("Unknown program")
        if not frappe.db.exists(YEAR, year_name):
            raise frappe.ValidationError("Unknown academic year")
        if term_name and not frappe.db.exists(TERM, term_name):
            raise frappe.ValidationError("Unknown academic term")
        # End date: explicit value wins, else suggested from duration policy.
        if class_end_date:
            try:
                end = validate_schedule_date(class_end_date)
            except ValueError as exc:
                raise frappe.ValidationError(str(exc)) from exc
        else:
            end = _suggested_end_date(start, program_name)
            if not end:
                raise frappe.ValidationError(
                    "No governing duration policy for this level; supply class_end_date explicitly")
        if end < start:
            raise frappe.ValidationError("Class end date cannot precede start date")
        frappe.db.sql("select name from `tabProgram` where name=%s for update", (program_name,))
        from education.education.doctype.student_group.student_group import get_program_enrollment
        roster_rows = get_program_enrollment(year_name, term_name or None, program_name)
        if not roster_rows:
            raise frappe.ValidationError("No submitted program enrollment for this intake")
        if len(roster_rows) > capacity:
            raise frappe.ValidationError("Roster exceeds the declared class capacity")
        if frappe.db.exists(GROUP, name):
            raise frappe.ValidationError("Student group already exists")
        group = frappe.get_doc(dict(
            doctype=GROUP, student_group_name=name, group_based_on="Batch",
            program=program_name, academic_year=year_name, academic_term=term_name or None,
            max_strength=capacity,
            th_class_start_date=start, th_class_end_date=end,
            th_class_status="Planned", th_delivery_mode=mode,
            th_branch=branch_name or None,
            students=[dict(student=row["student"], student_name=row["student_name"], active=1)
                      for row in roster_rows]))
        group.flags.ignore_permissions = True
        group.flags.ignore_links = True
        group.insert(ignore_permissions=True)
        students = sorted(row["student"] for row in roster_rows)
        suggested = _suggested_end_date(start, program_name)
        result = {
            "name": group.name,
            "program": program_name,
            "academic_year": year_name,
            "academic_term": term_name,
            "max_strength": capacity,
            "students": len(students),
            "roster": students,
            "class_start_date": start,
            "class_end_date": end,
            "class_status": "Planned",
            "delivery_mode": mode,
            "branch": branch_name,
            "suggested_end_date": suggested,
            "end_date_was_suggested": (end == suggested),
        }
        return result, dict(target=group.name,
                            after_hash=digest([group.name, program_name, capacity, students,
                                               start, end, mode, branch_name]))

    return _execute("create_student_group", request_key,
                    {"group_name": group_name, "program": program,
                     "academic_year": academic_year, "academic_term": academic_term or "",
                     "max_strength": max_strength,
                     "class_start_date": class_start_date or "",
                     "class_end_date": class_end_date or "",
                     "delivery_mode": delivery_mode, "branch": branch or ""}, work)


@frappe.whitelist(methods=["POST"])
def transition_class(request_key, student_group, to_status):
    """Advance a class through its operational lifecycle.

    Transitions are guarded: Planned → Active → Completed; Planned or Active
    may be Cancelled. Completed/Cancelled are terminal.
    """
    def work(actor):
        group_name = _bounded_name(student_group, "Student group")
        try:
            target = validate_class_status(to_status)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if not frappe.db.exists(GROUP, group_name):
            raise frappe.ValidationError("Unknown student group")
        frappe.db.sql("select name from `tabStudent Group` where name=%s for update", (group_name,))
        doc = frappe.get_doc(GROUP, group_name)
        before = doc.th_class_status or "Planned"
        if not is_valid_class_transition(before, target):
            raise frappe.ValidationError(
                f"Illegal class transition: {before} → {target}")
        # Guard scheduling: completed/cancelled classes reject new sessions.
        doc.th_class_status = target
        doc.flags.ignore_permissions = True
        doc.flags.ignore_links = True
        doc.save(ignore_permissions=True)
        return {"name": group_name, "before_status": before, "after_status": target}, \
            dict(target=group_name,
                 after_hash=digest([group_name, before, target]))

    return _execute("transition_class", request_key,
                    {"student_group": student_group, "to_status": to_status}, work)


@frappe.whitelist(methods=["POST"])
def schedule_session(request_key, student_group, schedule_date, from_time, to_time,
                     instructor, room, course):
    """Create a native Course Schedule for a rostered class.

    Native validation stays authoritative for the academic-calendar window and
    group/instructor/room overlap. The group, instructor and room rows are
    locked first so concurrent overlap checks serialize (read-then-insert is
    not a concurrency proof).
    """
    def work(actor):
        group_name = _bounded_name(student_group, "Student group")
        instructor_name = _bounded_name(instructor, "Instructor")
        room_name = _bounded_name(room, "Room")
        course_name = _bounded_name(course, "Course")
        try:
            day = validate_schedule_date(schedule_date)
            start, end = validate_session_window(from_time, to_time)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        for doctype, value, label in ((GROUP, group_name, "Student group"),
                                      ("Instructor", instructor_name, "Instructor"),
                                      ("Room", room_name, "Room"),
                                      ("Course", course_name, "Course")):
            if not frappe.db.exists(doctype, value):
                raise frappe.ValidationError(f"Unknown {label.lower()}")
        group = frappe.db.get_value(GROUP, group_name,
                                    ["program", "disabled", "th_class_status"],
                                    as_dict=True)
        if int(group.disabled or 0):
            raise frappe.ValidationError("Student group is disabled")
        if group.th_class_status != "Active":
            raise frappe.ValidationError(
                "Sessions can only be scheduled for Active classes "
                f"(current status: {group.th_class_status or 'Planned'})")
        if frappe.db.get_value("Instructor", instructor_name, "status") == "Left":
            raise frappe.ValidationError("A departed instructor cannot be scheduled")
        if not frappe.db.exists("Program Course", {"parent": group.program, "course": course_name}):
            raise frappe.ValidationError("Course is not part of the group's program catalog")
        frappe.db.sql("select name from `tabStudent Group` where name=%s for update", (group_name,))
        frappe.db.sql("select name from `tabInstructor` where name=%s for update", (instructor_name,))
        frappe.db.sql("select name from `tabRoom` where name=%s for update", (room_name,))
        session = frappe.get_doc(dict(
            doctype=SCHEDULE, naming_series="EDU-CSH-.YYYY.-",
            student_group=group_name, instructor=instructor_name, room=room_name,
            course=course_name, schedule_date=day, from_time=start, to_time=end))
        session.flags.ignore_permissions = True
        session.flags.ignore_links = True
        session.insert(ignore_permissions=True)
        result = {
            "name": session.name,
            "student_group": group_name,
            "course": session.course,
            "instructor": instructor_name,
            "room": room_name,
            "schedule_date": str(session.schedule_date),
            "from_time": str(session.from_time),
            "to_time": str(session.to_time),
            "title": session.title,
        }
        return result, dict(target=session.name,
                            after_hash=digest([session.name, group_name, instructor_name,
                                               room_name, course_name, day, start, end]))

    return _execute("schedule_session", request_key,
                    {"student_group": student_group, "schedule_date": schedule_date,
                     "from_time": from_time, "to_time": to_time, "instructor": instructor,
                     "room": room, "course": course}, work)


@frappe.whitelist(methods=["POST"])
def record_attendance(request_key, course_schedule, statuses):
    """Record submitted native Student Attendance for a scheduled session.

    Only explicit per-student native statuses are accepted; missing students
    are not defaulted. The session row is locked and existing records are
    checked under lock so concurrent marking cannot double-record (the native
    duplication check remains the backstop).
    """
    def work(actor):
        schedule_name = _bounded_name(course_schedule, "Course Schedule")
        try:
            marks = validate_attendance_statuses(statuses)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if not frappe.db.exists(SCHEDULE, schedule_name):
            raise frappe.ValidationError("Unknown course schedule")
        frappe.db.sql("select name from `tabCourse Schedule` where name=%s for update",
                      (schedule_name,))
        session = frappe.db.get_value(SCHEDULE, schedule_name,
                                      ["student_group", "schedule_date"], as_dict=True)
        roster = {row.student for row in frappe.db.sql(
            "select student from `tabStudent Group Student` where parent=%s",
            (session.student_group,), as_dict=True)}
        for student in sorted(marks):
            if student not in roster:
                raise frappe.ValidationError("Student is not on the scheduled group roster")
            if frappe.db.sql("select name from `tabStudent Attendance` where student=%s "
                             "and course_schedule=%s and docstatus!=2 for update",
                             (student, schedule_name)):
                raise frappe.ValidationError("Attendance is already recorded for this session")
        records = {}
        with _roster_read():
            for student in sorted(marks):
                doc = frappe.get_doc(dict(
                    doctype=ATTENDANCE, naming_series="EDU-ATT-.YYYY.-",
                    student=student, course_schedule=schedule_name, status=marks[student]))
                doc.flags.ignore_permissions = True
                doc.flags.ignore_links = True
                doc.insert(ignore_permissions=True)
                doc.flags.ignore_permissions = True
                doc.flags.ignore_links = True
                doc.submit()
                if int(doc.docstatus or 0) != 1:
                    raise frappe.ValidationError("Student Attendance must be submitted")
                records[student] = doc.name
        result = {
            "course_schedule": schedule_name,
            "student_group": session.student_group,
            "date": str(session.schedule_date),
            "marked": len(records),
            "records": records,
        }
        return result, dict(target=schedule_name,
                            after_hash=digest([schedule_name,
                                               {s: records[s] for s in sorted(records)}]))

    return _execute("record_attendance", request_key,
                    {"course_schedule": course_schedule, "statuses": statuses}, work)

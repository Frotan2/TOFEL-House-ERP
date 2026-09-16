"""Thin teaching operations over native Education scheduling and attendance.

Native authorities: Student Group (class roster), Course Schedule (session)
and Student Attendance (participation record). This module owns no roster,
timetable, grading, assessment, invoice, attendance ledger or payroll record.
Academic assessment/progression (B04/B05), fees (B07) and payroll (A09)
remain outside this slice and are not activated by it.
"""
from contextlib import contextmanager
import frappe
from toefl_house.api import _execute
from toefl_house.policy import (digest, validate_attendance_statuses, validate_capacity,
                                validate_group_name, validate_schedule_date,
                                validate_session_window)
from toefl_house.security import require_synthetic, teaching_command_active

GROUP = "Student Group"
SCHEDULE = "Course Schedule"
ATTENDANCE = "Student Attendance"
PROGRAM = "Program"
YEAR = "Academic Year"
TERM = "Academic Term"


def guard_student_group(doc, method=None):
    require_synthetic()
    if teaching_command_active(GROUP):
        return
    raise frappe.ValidationError("Student Group requires an authorized teaching command")


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


@frappe.whitelist(methods=["POST"])
def create_student_group(request_key, group_name, program, academic_year, academic_term="",
                         max_strength=0):
    """Roster a class strictly from submitted native Program Enrollments.

    The roster is derived from the native enrollment ledger (no manual student
    lists are accepted), so an unenrolled learner cannot enter a class.
    Capacity and duplicate students remain native Student Group validations.
    """
    def work(actor):
        try:
            name = validate_group_name(group_name)
            capacity = validate_capacity(max_strength)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        program_name = _bounded_name(program, "Program")
        year_name = _bounded_name(academic_year, "Academic Year")
        term_name = _bounded_name(academic_term, "Academic Term") if academic_term else ""
        if not frappe.db.exists(PROGRAM, program_name):
            raise frappe.ValidationError("Unknown program")
        if not frappe.db.exists(YEAR, year_name):
            raise frappe.ValidationError("Unknown academic year")
        if term_name and not frappe.db.exists(TERM, term_name):
            raise frappe.ValidationError("Unknown academic term")
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
            students=[dict(student=row["student"], student_name=row["student_name"], active=1)
                      for row in roster_rows]))
        group.flags.ignore_permissions = True
        group.flags.ignore_links = True
        group.insert(ignore_permissions=True)
        students = sorted(row["student"] for row in roster_rows)
        result = {
            "name": group.name,
            "program": program_name,
            "academic_year": year_name,
            "academic_term": term_name,
            "max_strength": capacity,
            "students": len(students),
            "roster": students,
        }
        return result, dict(target=group.name,
                            after_hash=digest([group.name, program_name, capacity, students]))

    return _execute("create_student_group", request_key,
                    {"group_name": group_name, "program": program,
                     "academic_year": academic_year, "academic_term": academic_term or "",
                     "max_strength": max_strength}, work)


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
        group = frappe.db.get_value(GROUP, group_name, ["program", "disabled"], as_dict=True)
        if int(group.disabled or 0):
            raise frappe.ValidationError("Student group is disabled")
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

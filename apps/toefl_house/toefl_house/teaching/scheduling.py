"""Server-side session scheduling: conflicts, calendars, postponement, make-up.

Native Course Schedule remains the authoritative session record. This module
adds the checks and lifecycle the native controller does not cover, all on
the server and all fail-closed:

* the session must fall inside the class's own start/end window;
* when a class-operations policy governs, its teaching days, session-duration
  bounds and per-class daily session limit apply;
* the academic calendar blocks Holidays and Closed days (a Working Day
  reopens one);
* no overlapping session may exist for the same class, instructor or room,
  and no active roster student may be double-booked into another class at
  the same time;
* a room whose configured seating capacity is below the class capacity is
  refused (the class cannot physically sit there);
* postponement, cancellation and make-up sessions execute only when the
  governing policy permits them, keep the original row intact, and link the
  replacement through ``th_replaces``.

Conflicts are re-checked under row locks inside the command transaction, so
two schedulers racing on the same slot cannot both win.
"""
from datetime import date, timedelta

import frappe

from toefl_house.policy import (clock_text, digest, session_minutes,
                                session_windows_overlap, validate_schedule_date,
                                validate_session_window)
from toefl_house.teaching import calendars as academic_calendar
from toefl_house.teaching import class_operations, timetables

SESSION = "Course Schedule"
GROUP = "Student Group"
ATTENDANCE = "Student Attendance"

SESSION_STATUSES = ("Scheduled", "Postponed", "Cancelled")
SESSION_KINDS = ("Regular", "Replacement", "Makeup")
ACTIVE_SESSION_STATUS = "Scheduled"
REASON_LIMIT = 500
_NAME_LIMIT = 140


def governing_terms():
    """The validated terms of the governing policy, or ``{}`` when none.

    Session scheduling itself works without a policy (the native calendar and
    the conflict invariants still bind); the policy tightens it with teaching
    days, duration bounds and a daily limit, and it is mandatory for every
    command that changes a session's life (postpone, cancel, replace).
    """
    return class_operations.governing_operations()


def _bounded(value, what):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > _NAME_LIMIT:
        raise frappe.ValidationError(f"{what} is required")
    return value.strip()


def _reason(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > REASON_LIMIT:
        raise frappe.ValidationError(
            f"A reason is required (at most {REASON_LIMIT} characters)")
    return value.strip()


def _require_role(role, actor, what):
    if not role or role not in frappe.get_roles(actor):
        raise frappe.PermissionError(
            f"{what} requires the policy-configured role: {role or 'not configured'}")
    return role


def _lock(doctype, name):
    frappe.db.sql(
        f"select name from `tab{doctype}` where name=%s for update", (name,))


def group_facts(group_name):
    """The class facts scheduling depends on, or a refusal."""
    facts = frappe.db.get_value(
        GROUP, group_name,
        ["program", "academic_year", "academic_term", "max_strength",
         "disabled", "th_class_status", "th_class_start_date",
         "th_class_end_date", "th_delivery_mode", "th_branch"], as_dict=True)
    if facts is None:
        raise frappe.ValidationError(f"Unknown student group: {group_name}")
    return facts


def require_active_class(group_name, facts=None, action="Sessions"):
    facts = facts or group_facts(group_name)
    if int(facts.disabled or 0):
        raise frappe.ValidationError(f"Student group {group_name} is disabled")
    if facts.th_class_status != "Active":
        raise frappe.ValidationError(
            f"{action} apply to Active classes only "
            f"(current status: {facts.th_class_status or 'Planned'})")
    return facts


def session_facts(session_name):
    facts = frappe.db.get_value(
        SESSION, session_name,
        ["name", "student_group", "instructor", "room", "course",
         "schedule_date", "from_time", "to_time", "th_session_status",
         "th_session_kind", "th_replaces"], as_dict=True)
    if facts is None:
        raise frappe.ValidationError(f"Unknown course schedule: {session_name}")
    return facts


def scheduled_sessions_on(day, exclude_session=None):
    """Every Scheduled session on a date, locked for the transaction."""
    rows = frappe.db.sql(
        "select name, student_group, instructor, room, from_time, to_time, "
        "ifnull(th_session_status, 'Scheduled') as th_session_status "
        "from `tabCourse Schedule` where schedule_date=%s for update", (day,),
        as_dict=True)
    return [row for row in rows
            if str(row.get("th_session_status") or ACTIVE_SESSION_STATUS) == ACTIVE_SESSION_STATUS
            and row.get("name") != exclude_session]


def _conflict(rows, field, value, start, end):
    if not value:
        return None
    for row in rows:
        if str(row.get(field) or "") != str(value):
            continue
        if session_windows_overlap(row.get("from_time"), row.get("to_time"), start, end):
            return row
    return None


def student_conflicts(group_name, day, start, end, exclude_session=None):
    """Active roster students double-booked into another class at the time.

    The native controller validates the class/instructor/room overlap; it has
    no student-level view, so a learner rostered into two overlapping classes
    would otherwise appear in two places at once. This join answers exactly
    that question over active roster rows only.
    """
    params = [day, exclude_session or "", end, start, group_name, group_name]
    rows = frappe.db.sql(
        "select s.name, s.student_group, s.from_time, s.to_time, rs.student "
        "from `tabCourse Schedule` s "
        "join `tabStudent Group Student` rs on rs.parent = s.student_group and rs.active = 1 "
        "where s.schedule_date=%s and s.name!=%s "
        "and ifnull(s.th_session_status, 'Scheduled')='Scheduled' "
        "and s.from_time < %s and s.to_time > %s and s.student_group != %s "
        "and rs.student in (select student from `tabStudent Group Student` "
        "where parent=%s and active=1)", tuple(params), as_dict=True)
    return rows


def room_seating(room):
    """The room's configured seating capacity, or 0 when unset."""
    value = frappe.db.get_value("Room", room, "seating_capacity") if room else 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _daily_session_count(group_name, day, exclude_session=None):
    rows = frappe.db.sql(
        "select name from `tabCourse Schedule` where student_group=%s "
        "and schedule_date=%s and ifnull(th_session_status, 'Scheduled')='Scheduled'",
        (group_name, day))
    return len([row for row in rows
                if (row[0] if isinstance(row, (list, tuple)) else row) != exclude_session])


def check_new_session(terms, group_name, day, start, end, instructor, room,
                      course, exclude_session=None):
    """Validate one prospective session; raise before anything is written.

    ``terms`` may be ``{}`` (no policy governs): the invariant checks still
    run — class window, calendar closures, class/instructor/room/student
    conflicts, room seating — because those are correctness rules, not
    owner preferences.
    """
    try:
        clean_day = validate_schedule_date(day)
        clean_start, clean_end = validate_session_window(start, end)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    facts = require_active_class(group_name)
    class_start = str(facts.th_class_start_date or "")
    class_end = str(facts.th_class_end_date or "")
    if not class_start or not class_end:
        raise frappe.ValidationError(
            "The class has no start/end window; sessions cannot be placed")
    if clean_day < class_start or clean_day > class_end:
        raise frappe.ValidationError(
            f"{clean_day} falls outside the class window {class_start} to {class_end}")
    if terms:
        minutes = session_minutes(clean_start, clean_end)
        if not terms["min_session_minutes"] <= minutes <= terms["max_session_minutes"]:
            raise frappe.ValidationError(
                f"A {minutes}-minute session is outside the policy's "
                f"{terms['min_session_minutes']}-{terms['max_session_minutes']} minute bounds")
        existing = _daily_session_count(group_name, clean_day, exclude_session)
        if existing + 1 > terms["max_sessions_per_day"]:
            raise frappe.ValidationError(
                f"{group_name} already has {existing} session(s) on {clean_day}; the "
                f"policy allows at most {terms['max_sessions_per_day']} per day")
    academic_calendar.assert_teaching_allowed(
        clean_day, terms.get("teaching_days") if terms else None,
        facts.academic_year or "", facts.th_branch or "")
    for course_name in (course,):
        if not course_name:
            raise frappe.ValidationError("A session requires a course")
    _lock(GROUP, group_name)
    for doctype, value, label in (("Instructor", instructor, "instructor"),
                                  ("Room", room, "room")):
        if value:
            _lock(doctype, value)
    rows = scheduled_sessions_on(clean_day, exclude_session)
    conflict = _conflict(rows, "student_group", group_name, clean_start, clean_end)
    if conflict:
        raise frappe.ValidationError(
            f"{group_name} already has session {conflict.get('name')} at "
            f"{clock_text(conflict.get('from_time'))}-"
            f"{clock_text(conflict.get('to_time'))} on {clean_day}")
    conflict = _conflict(rows, "instructor", instructor, clean_start, clean_end)
    if conflict:
        raise frappe.ValidationError(
            f"Instructor {instructor} is already scheduled in session "
            f"{conflict.get('name')} at {clock_text(conflict.get('from_time'))}-"
            f"{clock_text(conflict.get('to_time'))} on {clean_day}")
    conflict = _conflict(rows, "room", room, clean_start, clean_end)
    if conflict:
        raise frappe.ValidationError(
            f"Room {room} is already booked by session {conflict.get('name')} "
            f"at {clock_text(conflict.get('from_time'))}-"
            f"{clock_text(conflict.get('to_time'))} on {clean_day}")
    doubled = student_conflicts(group_name, clean_day, clean_start, clean_end,
                                exclude_session)
    if doubled:
        first = doubled[0]
        raise frappe.ValidationError(
            f"Student {first.get('student')} is already in session "
            f"{first.get('name')} ({first.get('student_group')}) at "
            f"{clock_text(first.get('from_time'))}-"
            f"{clock_text(first.get('to_time'))} on {clean_day}")
    seating = room_seating(room)
    if seating and int(facts.max_strength or 0) > seating:
        raise frappe.ValidationError(
            f"Room {room} seats {seating}, below the class capacity "
            f"{int(facts.max_strength)}")
    return {"schedule_date": clean_day, "from_time": clean_start,
            "to_time": clean_end, "facts": facts}


def insert_session(group_name, day, start, end, instructor, room, course,
                   kind="Regular", replaces=None, note=""):
    """Insert one native Course Schedule row inside the active command."""
    session = frappe.get_doc(dict(
        doctype=SESSION, naming_series="EDU-CSH-.YYYY.-",
        student_group=group_name, instructor=instructor, room=room,
        course=course, schedule_date=day, from_time=start, to_time=end,
        th_session_kind=kind, th_session_status="Scheduled",
        th_replaces=replaces or None, th_session_note=note or None))
    session.flags.ignore_permissions = True
    session.flags.ignore_links = True
    session.insert(ignore_permissions=True)
    return session


def _session_result(session):
    return {
        "name": session.name, "student_group": session.student_group,
        "instructor": session.instructor, "room": session.room,
        "course": session.course, "schedule_date": str(session.schedule_date),
        "from_time": clock_text(session.from_time),
        "to_time": clock_text(session.to_time),
        "kind": session.get("th_session_kind") or "Regular",
        "status": session.get("th_session_status") or "Scheduled",
        "replaces": session.get("th_replaces") or "",
    }


def assert_session_open_for_attendance(session_name):
    """Attendance may only be recorded for a session that will actually meet."""
    facts = session_facts(session_name)
    status = str(facts.get("th_session_status") or ACTIVE_SESSION_STATUS)
    if status != ACTIVE_SESSION_STATUS:
        raise frappe.ValidationError(
            f"Session {session_name} is {status}; attendance applies to "
            "Scheduled sessions only")
    return facts


def _live_attendance(session_name):
    return int(frappe.db.count(ATTENDANCE, {"course_schedule": session_name,
                                            "docstatus": 1}))


@frappe.whitelist(methods=["POST"])
def generate_timetable(request_key, student_group, template, start_date,
                       end_date):
    """Materialize a timetable template into native sessions for one range.

    Only Scheduled sessions are created; skipped dates (holidays, closed days,
    non-teaching weekdays) are reported back so the scheduler can see exactly
    which dates the calendar excluded.
    """
    from toefl_house.api import _execute

    def work(actor):
        terms = class_operations.require_operations()
        group_name = _bounded(student_group, "Student group")
        template_code = _bounded(template, "Timetable template")
        try:
            start = validate_schedule_date(start_date)
            end = validate_schedule_date(end_date)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if end < start:
            raise frappe.ValidationError("Timetable end date precedes its start")
        span = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        if span > terms["timetable_horizon_days"]:
            raise frappe.ValidationError(
                f"The range spans {span} days; the policy allows at most "
                f"{terms['timetable_horizon_days']} days per generation")
        facts = require_active_class(group_name)
        template_doc = timetables._template_doc(template_code)
        if template_doc.status != "Active":
            raise frappe.ValidationError(
                f"Timetable template {template_code} is retired")
        if template_doc.program and template_doc.program != facts.program:
            raise frappe.ValidationError(
                "The timetable template belongs to a different program")
        if template_doc.branch and template_doc.branch != (facts.th_branch or ""):
            raise frappe.ValidationError(
                "The timetable template belongs to a different branch")
        if template_doc.delivery_mode != (facts.th_delivery_mode or ""):
            raise frappe.ValidationError(
                "The timetable template delivery mode does not match the class")
        try:
            slots = timetables.validate_slots(
                [row.as_dict() for row in (template_doc.get("slots") or [])])
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        plan = academic_calendar.calendar_plan(
            start, end, facts.academic_year or "", facts.th_branch or "")
        blocked = academic_calendar.blocked_dates(plan)
        try:
            candidates = timetables.expand_slots(
                slots, start, end, terms["teaching_days"], blocked)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if not candidates:
            raise frappe.ValidationError(
                "No teachable date in this range: the calendar or the "
                "policy's teaching days exclude every day")
        _lock(GROUP, group_name)
        for value in {row["instructor"] for row in candidates if row["instructor"]}:
            _lock("Instructor", value)
        for value in {row["room"] for row in candidates if row["room"]}:
            _lock("Room", value)
        generated = []
        for candidate in candidates:
            try:
                check_new_session(
                    terms, group_name, candidate["schedule_date"],
                    candidate["from_time"], candidate["to_time"],
                    candidate["instructor"], candidate["room"], candidate["course"])
                session = insert_session(
                    group_name, candidate["schedule_date"], candidate["from_time"],
                    candidate["to_time"], candidate["instructor"], candidate["room"],
                    candidate["course"], kind="Regular")
            except frappe.ValidationError as exc:
                raise frappe.ValidationError(
                    f"{candidate['schedule_date']} {candidate['from_time']}: {exc}") from exc
            generated.append(_session_result(session))
        result = {
            "student_group": group_name, "template": template_code,
            "generated": len(generated), "sessions": generated,
            "skipped_calendar_days": sorted(blocked), "policy_effective_from":
            terms.get("effective_from", ""),
        }
        return result, dict(target=group_name,
                            after_hash=digest([group_name, template_code,
                                               [row["name"] for row in generated]]))

    return _execute("generate_timetable", request_key,
                    {"student_group": student_group, "template": template,
                     "start_date": start_date, "end_date": end_date}, work)


@frappe.whitelist(methods=["POST"])
def postpone_session(request_key, course_schedule, reason, new_date,
                     from_time="", to_time="", room="", instructor=""):
    """Postpone one session: keep the original row, schedule its replacement.

    The original row is never rewritten or deleted — it becomes ``Postponed``
    with the operator's reason, and the replacement session carries
    ``th_replaces`` back to it. Attendance already recorded on the original
    refuses the postponement (the session happened; correct the record
    instead).
    """
    from toefl_house.api import _execute

    def work(actor):
        terms = class_operations.require_operations(
            feature="allow_postponement",
            message="Session postponement is not permitted by the governing "
                    "class-operations policy")
        name = _bounded(course_schedule, "Course schedule")
        clean_reason = _reason(reason)
        _lock(SESSION, name)
        facts = session_facts(name)
        status = str(facts.get("th_session_status") or ACTIVE_SESSION_STATUS)
        if status != ACTIVE_SESSION_STATUS:
            raise frappe.ValidationError(
                f"Session {name} is already {status}")
        if _live_attendance(name):
            raise frappe.ValidationError(
                "Attendance is already recorded for this session; a session "
                "that happened is not postponed")
        try:
            day = validate_schedule_date(new_date)
            start, end = validate_session_window(
                from_time or facts.from_time, to_time or facts.to_time)
            original_day = str(facts.schedule_date)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if day < original_day:
            raise frappe.ValidationError(
                "A postponed session may not move before the original date")
        if day > (date.fromisoformat(original_day) + timedelta(
                days=terms["postpone_max_days"])).isoformat():
            raise frappe.ValidationError(
                f"A postponement may move at most {terms['postpone_max_days']} "
                f"day(s) after {original_day}")
        if day < frappe.utils.today():
            raise frappe.ValidationError("A postponed session cannot land in the past")
        teacher = instructor or facts.instructor
        place = room or facts.room
        check_new_session(terms, facts.student_group, day, start, end, teacher,
                          place, facts.course, exclude_session=name)
        original = frappe.get_doc(SESSION, name)
        original.flags.ignore_permissions = True
        original.flags.ignore_links = True
        original.th_session_status = "Postponed"
        original.th_session_note = clean_reason
        original.save(ignore_permissions=True)
        replacement = insert_session(
            facts.student_group, day, start, end, teacher, place, facts.course,
            kind="Replacement", replaces=name, note=clean_reason)
        result = {
            "original": name, "original_status": "Postponed",
            "replacement": _session_result(replacement),
            "reason": clean_reason,
            "policy_effective_from": terms.get("effective_from", ""),
        }
        return result, dict(target=name,
                            after_hash=digest([name, "Postponed",
                                               replacement.name, day, start, end]))

    return _execute("postpone_session", request_key,
                    {"course_schedule": course_schedule, "reason": reason,
                     "new_date": new_date, "from_time": from_time,
                     "to_time": to_time, "room": room,
                     "instructor": instructor}, work)


@frappe.whitelist(methods=["POST"])
def schedule_replacement_session(request_key, course_schedule, reason,
                                 schedule_date, from_time, to_time, room="",
                                 instructor=""):
    """Schedule the make-up for a postponed or cancelled session.

    Requires the policy's replacement feature AND the policy-configured
    replacement approver role (dual key). The make-up must fall inside the
    replacement window, and one original session can have exactly one
    replacement so a retried request cannot duplicate it.
    """
    from toefl_house.api import _execute

    def work(actor):
        terms = class_operations.require_operations(
            feature="allow_replacement_sessions",
            message="Replacement sessions are not permitted by the governing "
                    "class-operations policy")
        _require_role(terms["replacement_approver_role"], actor,
                      "Scheduling a replacement session")
        name = _bounded(course_schedule, "Course schedule")
        clean_reason = _reason(reason)
        _lock(SESSION, name)
        facts = session_facts(name)
        status = str(facts.get("th_session_status") or ACTIVE_SESSION_STATUS)
        if status not in ("Postponed", "Cancelled"):
            raise frappe.ValidationError(
                "A replacement can only follow a postponed or cancelled session")
        try:
            day = validate_schedule_date(schedule_date)
            start, end = validate_session_window(from_time, to_time)
            original_day = str(facts.schedule_date)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if day < original_day:
            raise frappe.ValidationError(
                "A replacement may not precede the session it replaces")
        limit = (date.fromisoformat(original_day) + timedelta(
            days=terms["replacement_window_days"])).isoformat()
        if day > limit:
            raise frappe.ValidationError(
                f"A replacement must fall on or before {limit} "
                f"(the policy's {terms['replacement_window_days']}-day window)")
        if frappe.db.exists(SESSION, {"th_replaces": name}):
            raise frappe.ValidationError(
                "A replacement session already exists for this session")
        teacher = instructor or facts.instructor
        place = room or facts.room
        check_new_session(terms, facts.student_group, day, start, end, teacher,
                          place, facts.course, exclude_session=name)
        replacement = insert_session(
            facts.student_group, day, start, end, teacher, place, facts.course,
            kind="Makeup", replaces=name, note=clean_reason)
        result = {
            "original": name, "original_status": status,
            "replacement": _session_result(replacement), "reason": clean_reason,
            "policy_effective_from": terms.get("effective_from", ""),
        }
        return result, dict(target=name,
                            after_hash=digest([name, status, replacement.name,
                                               day, start, end]))

    return _execute("schedule_replacement_session", request_key,
                    {"course_schedule": course_schedule, "reason": reason,
                     "schedule_date": schedule_date, "from_time": from_time,
                     "to_time": to_time, "room": room,
                     "instructor": instructor}, work)


@frappe.whitelist(methods=["POST"])
def cancel_session(request_key, course_schedule, reason):
    """Cancel one session that will not meet (attendance must not exist yet)."""
    from toefl_house.api import _execute

    def work(actor):
        terms = class_operations.require_operations(
            feature="allow_session_cancellation",
            message="Session cancellation is not permitted by the governing "
                    "class-operations policy")
        name = _bounded(course_schedule, "Course schedule")
        clean_reason = _reason(reason)
        _lock(SESSION, name)
        facts = session_facts(name)
        status = str(facts.get("th_session_status") or ACTIVE_SESSION_STATUS)
        if status != ACTIVE_SESSION_STATUS:
            raise frappe.ValidationError(f"Session {name} is already {status}")
        if _live_attendance(name):
            raise frappe.ValidationError(
                "Attendance is already recorded for this session; a session "
                "that happened is not cancelled")
        session = frappe.get_doc(SESSION, name)
        session.flags.ignore_permissions = True
        session.flags.ignore_links = True
        session.th_session_status = "Cancelled"
        session.th_session_note = clean_reason
        session.save(ignore_permissions=True)
        result = {"name": name, "status": "Cancelled", "reason": clean_reason,
                  "policy_effective_from": terms.get("effective_from", "")}
        return result, dict(target=name,
                            after_hash=digest([name, "Cancelled", clean_reason]))

    return _execute("cancel_session", request_key,
                    {"course_schedule": course_schedule, "reason": reason}, work)

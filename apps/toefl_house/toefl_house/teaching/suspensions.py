"""Temporary suspensions: a class pauses, or one student pauses, then returns.

A suspension is an operational period record, not a roster edit and not a
second enrollment: the native roster row stays exactly as it was, the
attendance history stays exactly as it was, and capacity keeps counting the
same rows. What the record changes is the *permission to act* during its
window:

* a **class** suspension blocks scheduling a session inside the window;
* a **student** suspension blocks marking that student Present inside the
  window (Absent and Leave remain recordable — the learner is away, and the
  record must still be truthful);
* a suspension ends explicitly (resume) or silently stops applying after its
  ``until_date`` — the row is never deleted, so the history of the pause
  survives every later change.

Both windows are bounded by the governing class-operations policy and fail
closed without one.
"""
from datetime import date

import frappe

from toefl_house.policy import digest
from toefl_house.security import record_synthetic_flag
from toefl_house.teaching import class_operations

SUSPENSION = "TH Class Suspension"
GROUP = "Student Group"
STUDENT = "Student"
ROSTER_TABLE = "Student Group Student"
SCOPES = ("Class", "Student")
STATUSES = ("Active", "Ended")
REASON_LIMIT = 500
NAME_LIMIT = 140


def _bounded(value, what):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > NAME_LIMIT:
        raise frappe.ValidationError(f"{what} is required")
    return value.strip()


def _reason(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > REASON_LIMIT:
        raise frappe.ValidationError(
            f"A reason is required (at most {REASON_LIMIT} characters)")
    return value.strip()


def _day(value, what):
    try:
        return date.fromisoformat(str(value or "")).isoformat()
    except ValueError as exc:
        raise frappe.ValidationError(f"{what} must be a date (YYYY-MM-DD)") from exc


def _today():
    return str(frappe.utils.today())


def _lock(doctype, name):
    frappe.db.sql(
        f"select name from `tab{doctype}` where name=%s for update", (name,))


def suspension_window_valid(from_date, until_date, limit_days, label):
    """Validate one suspension window against the configured limit."""
    start = _day(from_date, "Suspension start")
    end = _day(until_date, "Suspension end")
    if end < start:
        raise frappe.ValidationError("A suspension cannot end before it starts")
    span = (date.fromisoformat(end) - date.fromisoformat(start)).days
    if span > limit_days:
        raise frappe.ValidationError(
            f"A {label} suspension may not exceed {limit_days} day(s)")
    return start, end


def overlapping_suspension(group_name, student="", scope=None, on_date=None):
    """An existing Active suspension covering the date for the same target."""
    filters = {"student_group": group_name, "status": "Active"}
    if scope:
        filters["scope"] = scope
    if student:
        filters["student"] = student
    rows = frappe.get_all(SUSPENSION, filters=filters,
                          fields=["name", "scope", "student", "from_date",
                                  "until_date"], limit_page_length=50)
    day = str(on_date or _today())
    for row in rows:
        if str(row.get("from_date") or "") <= day <= str(row.get("until_date") or ""):
            return row
    return None


def active_suspension(group_name, student="", on_date=None):
    """The Active suspension covering a date, class-wide or for one student."""
    day = str(on_date or _today())
    rows = frappe.get_all(
        SUSPENSION,
        filters={"student_group": group_name, "status": "Active"},
        fields=["name", "scope", "student", "from_date", "until_date", "reason"],
        limit_page_length=50)
    for row in rows:
        if not str(row.get("from_date") or "") <= day <= str(row.get("until_date") or ""):
            continue
        if row.get("scope") == "Class":
            return row
        if student and row.get("student") == student:
            return row
    return None


def assert_scheduling_allowed(group_name, day):
    """Refuse scheduling a session inside a class suspension window."""
    group = frappe.db.get_value(GROUP, group_name, "th_class_status")
    if group is None:
        raise frappe.ValidationError(f"Unknown student group: {group_name}")
    row = active_suspension(group_name, on_date=day)
    if row and row.get("scope") == "Class":
        raise frappe.ValidationError(
            f"Class {group_name} is suspended on {day} "
            f"({row.get('from_date')} to {row.get('until_date')}): {row.get('reason')}")
    return True


def assert_attendance_allowed(group_name, day, marks):
    """Refuse Present marks for a suspended class or student.

    Absent and Leave remain allowed: the session still happened and the
    record must say so; only "Present" contradicts the suspension.
    """
    class_suspension = active_suspension(group_name, on_date=day)
    if class_suspension and class_suspension.get("scope") == "Class":
        if any(status == "Present" for status in marks.values()):
            raise frappe.ValidationError(
                f"Class {group_name} is suspended on {day}; no Present marks "
                "can be recorded inside a class suspension")
    for student, status in marks.items():
        if status != "Present":
            continue
        row = active_suspension(group_name, student, on_date=day)
        if row and row.get("scope") == "Student":
            raise frappe.ValidationError(
                f"Student {student} is suspended on {day}; record Leave or "
                "Absent instead of Present")
    return True


def _suspension_row(name, for_update=True):
    if for_update:
        _lock(SUSPENSION, name)
    row = frappe.db.get_value(
        SUSPENSION, name,
        ["name", "scope", "student_group", "student", "from_date", "until_date",
         "reason", "status", "requested_by", "requested_on", "policy_effective_from"],
        as_dict=True)
    if row is None:
        raise frappe.ValidationError(f"Unknown class suspension: {name}")
    return row


def _require_member(group_name, student):
    rows = frappe.db.sql(
        "select active from `tabStudent Group Student` where parent=%s and student=%s",
        (group_name, student), as_dict=True)
    if not rows or not int(rows[0].get("active") or 0):
        raise frappe.ValidationError(
            f"Student {student} is not an active member of {group_name}; a "
            "suspension applies to a current class membership")


def _suspend(scope, group_name, student, reason, from_date, until_date,
             terms, actor, flag_key, limit_key, label):
    if not terms.get(flag_key):
        raise frappe.ValidationError(
            f"{label} suspensions are not permitted by the governing "
            "class-operations policy")
    _lock(GROUP, group_name)
    facts = frappe.db.get_value(GROUP, group_name,
                                ["disabled", "th_class_status"], as_dict=True)
    if facts is None:
        raise frappe.ValidationError(f"Unknown student group: {group_name}")
    if facts.th_class_status not in ("Planned", "Active"):
        raise frappe.ValidationError(
            f"Student group {group_name} is {facts.th_class_status}; suspensions "
            "apply to Planned or Active classes only")
    clean_reason = _reason(reason)
    start, end = suspension_window_valid(from_date, until_date,
                                         terms[limit_key], label.lower())
    if scope == "Student":
        _require_member(group_name, student)
        if overlapping_suspension(group_name, student, "Student", start):
            raise frappe.ValidationError(
                f"Student {student} already has an active suspension on {start}")
    elif overlapping_suspension(group_name, "", "Class", start):
        raise frappe.ValidationError(
            f"Class {group_name} already has an active suspension on {start}")
    doc = frappe.get_doc({
        "doctype": SUSPENSION, "scope": scope, "student_group": group_name,
        "student": student or None, "from_date": start, "until_date": end,
        "reason": clean_reason, "status": "Active", "requested_by": actor,
        "requested_on": frappe.utils.now_datetime(),
        "policy_effective_from": terms.get("effective_from", ""),
        "synthetic": record_synthetic_flag(),
    })
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    result = {"name": doc.name, "scope": scope, "student_group": group_name,
              "student": student or "", "from_date": start, "until_date": end,
              "status": "Active", "policy_effective_from":
              terms.get("effective_from", "")}
    return result, dict(target=doc.name,
                        after_hash=digest([doc.name, scope, group_name, student or "",
                                           start, end]))


@frappe.whitelist(methods=["POST"])
def suspend_class(request_key, student_group, reason, from_date, until_date):
    """Pause sessions for a whole class inside a bounded window."""
    from toefl_house.api import _execute

    def work(actor):
        terms = class_operations.require_operations()
        return _suspend("Class", _bounded(student_group, "Student group"), "",
                        reason, from_date, until_date, terms, actor,
                        "allow_class_suspension", "class_suspension_max_days",
                        "Class")

    return _execute("suspend_class", request_key,
                    {"student_group": student_group, "reason": reason,
                     "from_date": from_date, "until_date": until_date}, work)


@frappe.whitelist(methods=["POST"])
def suspend_student_membership(request_key, student_group, student, reason,
                               from_date, until_date):
    """Pause one student's attendance inside a bounded window (roster kept)."""
    from toefl_house.api import _execute

    def work(actor):
        terms = class_operations.require_operations()
        return _suspend("Student", _bounded(student_group, "Student group"),
                        _bounded(student, "Student"), reason, from_date,
                        until_date, terms, actor, "allow_student_suspension",
                        "student_suspension_max_days", "Student")

    return _execute("suspend_student_membership", request_key,
                    {"student_group": student_group, "student": student,
                     "reason": reason, "from_date": from_date,
                     "until_date": until_date}, work)


@frappe.whitelist(methods=["POST"])
def resume_suspension(request_key, suspension, reason=""):
    """End a suspension early; the row and its window stay in history."""
    from toefl_house.api import _execute

    def work(actor):
        row = _suspension_row(_bounded(suspension, "Class suspension"))
        if row["status"] != "Active":
            raise frappe.ValidationError(
                f"Class suspension {suspension} is already {row['status']}")
        note = (reason or "").strip()
        if len(note) > REASON_LIMIT:
            raise frappe.ValidationError(
                f"The resume note must be at most {REASON_LIMIT} characters")
        doc = frappe.get_doc(SUSPENSION, row["name"])
        doc.flags.ignore_permissions = True
        doc.status = "Ended"
        doc.ended_by = actor
        doc.ended_on = frappe.utils.now_datetime()
        doc.save(ignore_permissions=True)
        result = {"name": doc.name, "status": "Ended",
                  "student_group": row["student_group"],
                  "student": row.get("student") or ""}
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, "Ended", note]))

    return _execute("resume_suspension", request_key,
                    {"suspension": suspension, "reason": reason}, work)


__all__ = ["SUSPENSION", "SCOPES", "STATUSES", "suspension_window_valid",
           "active_suspension", "assert_scheduling_allowed",
           "assert_attendance_allowed", "suspend_class",
           "suspend_student_membership", "resume_suspension"]

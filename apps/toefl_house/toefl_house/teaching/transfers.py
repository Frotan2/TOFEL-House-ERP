"""Controlled student transfers between classes, times, programs and branches.

A transfer is a request, an independent approval, and an atomic execution —
never an in-place roster rewrite:

1. **Request** (Teaching Scheduler): every eligibility fact is proven and
   snapshotted — active membership in the source, a submitted enrollment for
   the target intake, target class open, no timetable collision with the
   learner's other classes, no suspension, policy allows this kind of
   transfer and the transfer window is open. The governing policy version is
   pinned onto the request.
2. **Approval** (Academic Manager holding the pinned approver role): the
   approver must not be the requester, and every eligibility fact is
   re-proven under lock, because the world may have moved since the request.
   Capacity is re-checked; a full target needs a matching Approved override.
3. **Execution** (inside the approval): the source roster row is deactivated
   (kept for history, exactly like a move), the target row is appended or
   reactivated, and the transfer row records the preserved evidence.

Nothing is deleted and nothing is rewritten: attendance, assessment results,
financial references and instructor assignments still point at the class
they happened in, and the transfer row carries the counts and identifiers of
those records so any later audit can find them by name.
"""
from datetime import date, timedelta
import json

import frappe

from toefl_house.policy import digest
from toefl_house.security import record_synthetic_flag
from toefl_house.teaching import capacity, class_operations

TRANSFER = "TH Class Transfer"
GROUP = "Student Group"
STUDENT = "Student"
REASON_LIMIT = 500
NAME_LIMIT = 140
EVIDENCE_SAMPLE = 100
MAX_SESSIONS = 200
TERMINAL_CLASS = ("Completed", "Cancelled")
TRANSFER_KINDS = ("Class", "Time", "Program", "Branch")


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


def _lock(doctype, name):
    frappe.db.sql(
        f"select name from `tab{doctype}` where name=%s for update", (name,))


def classify(source, target):
    """Name the transfer by what actually changes between the two classes."""
    if source.get("program") != target.get("program"):
        return "Program"
    if (source.get("th_branch") or "") != (target.get("th_branch") or ""):
        return "Branch"
    if (source.get("academic_term") or "") != (target.get("academic_term") or ""):
        return "Time"
    return "Class"


def _group(name):
    facts = frappe.db.get_value(
        GROUP, name,
        ["name", "program", "academic_year", "academic_term", "max_strength",
         "disabled", "th_class_status", "th_delivery_mode", "th_branch",
         "th_class_start_date", "th_class_end_date"], as_dict=True)
    if facts is None:
        raise frappe.ValidationError(f"Unknown student group: {name}")
    return facts


def _active_member(group_name, student):
    rows = frappe.db.sql(
        "select active from `tabStudent Group Student` where parent=%s and student=%s",
        (group_name, student), as_dict=True)
    return bool(rows) and int(rows[0].get("active") or 0) == 1


def _student_name(student):
    if not frappe.db.exists(STUDENT, student):
        raise frappe.ValidationError(f"Unknown student: {student}")
    if not frappe.db.get_value(STUDENT, student, "enabled"):
        raise frappe.ValidationError(
            f"Student {student} is disabled and cannot transfer")
    return frappe.db.get_value(STUDENT, student, "student_name") or student


def _sessions(group_name, from_day=None):
    from_day = from_day or "1000-01-01"
    return frappe.db.sql(
        "select name, schedule_date, from_time, to_time, student_group "
        "from `tabCourse Schedule` where student_group=%s and schedule_date>=%s "
        "and ifnull(th_session_status, 'Scheduled')='Scheduled' "
        "order by schedule_date asc limit %s",
        (group_name, from_day, MAX_SESSIONS), as_dict=True)


def timetable_conflicts(student, target_group, from_day):
    """The learner's other classes that collide with the target timetable."""
    from toefl_house.policy import session_windows_overlap
    target = _sessions(target_group, from_day)
    if not target:
        return []
    rows = frappe.db.sql(
        "select s.name, s.schedule_date, s.from_time, s.to_time, s.student_group "
        "from `tabCourse Schedule` s "
        "join `tabStudent Group Student` rs on rs.parent = s.student_group "
        "and rs.active = 1 "
        "where rs.student=%s and s.student_group!=%s "
        "and ifnull(s.th_session_status, 'Scheduled')='Scheduled' "
        "and s.schedule_date>=%s", (student, target_group, from_day), as_dict=True)
    by_day = {}
    for row in rows:
        by_day.setdefault(str(row.get("schedule_date")), []).append(row)
    conflicts = []
    for session in target:
        for other in by_day.get(str(session.get("schedule_date")), []):
            if session_windows_overlap(session.get("from_time"),
                                       session.get("to_time"),
                                       other.get("from_time"),
                                       other.get("to_time")):
                conflicts.append({
                    "target_session": session.get("name"),
                    "target_group": target_group,
                    "other_session": other.get("name"),
                    "other_group": other.get("student_group"),
                    "schedule_date": str(session.get("schedule_date")),
                    "from_time": str(session.get("from_time")),
                    "to_time": str(session.get("to_time")),
                })
    return conflicts


def preserved_evidence(student, from_group):
    """Identifiers of the history that stays attached to the source class.

    Read-only counts and bounded samples; the transfer never rewrites any of
    these records. Stored on the transfer row so a later audit can locate
    the exact attendance, assessment, finance and instructor history of the
    student's time in the source class.
    """
    attendance = frappe.db.sql(
        "select a.name from `tabStudent Attendance` a "
        "join `tabCourse Schedule` s on s.name = a.course_schedule "
        "where a.student=%s and s.student_group=%s and a.docstatus=1 "
        "order by a.name limit %s", (student, from_group, EVIDENCE_SAMPLE),
        as_dict=True)
    attendance_count = frappe.db.count(
        "Student Attendance", {"student": student, "docstatus": 1})
    assessments = frappe.get_all(
        "Assessment Result", filters={"student": student, "docstatus": 1},
        fields=["name"], limit_page_length=EVIDENCE_SAMPLE)
    fees = frappe.get_all(
        "Fees", filters={"student": student, "docstatus": 1},
        fields=["name"], limit_page_length=EVIDENCE_SAMPLE)
    assignments = frappe.get_all(
        "TH Teaching Assignment", filters={"student_group": from_group},
        fields=["name", "instructor", "skill"], limit_page_length=EVIDENCE_SAMPLE)
    enrollments = frappe.get_all(
        "Program Enrollment", filters={"student": student, "docstatus": 1},
        fields=["name", "program", "academic_year", "academic_term"],
        limit_page_length=EVIDENCE_SAMPLE)
    return {
        "source_class": from_group,
        "attendance_in_source_class": {
            "count": int(attendance_count),
            "count_total_for_student": int(attendance_count),
            "sample": [row.get("name") for row in attendance],
        },
        "assessment_results": {
            "count": len(assessments),
            "sample": [row.get("name") for row in assessments],
        },
        "fees": {
            "count": len(fees),
            "sample": [row.get("name") for row in fees],
        },
        "instructor_assignments": {
            "count": len(assignments),
            "sample": [{"name": row.get("name"), "instructor": row.get("instructor"),
                        "skill": row.get("skill")} for row in assignments],
        },
        "program_enrollments": [row for row in enrollments],
    }


def _eligibility(student, from_group, to_group, effective_day, terms):
    """Prove every transfer fact; return the evidence snapshot."""
    if from_group == to_group:
        raise frappe.ValidationError("Source and target classes must differ")
    _student_name(student)
    source = _group(from_group)
    target = _group(to_group)
    for label, facts in (("source", source), ("target", target)):
        if int(facts.disabled or 0):
            raise frappe.ValidationError(f"The {label} class is disabled")
    if source.th_class_status in TERMINAL_CLASS:
        raise frappe.ValidationError(
            f"The source class is {source.th_class_status}; no transfer can start there")
    if target.th_class_status in TERMINAL_CLASS:
        raise frappe.ValidationError(
            f"The target class is {target.th_class_status}; no transfer can land there")
    if not _active_member(from_group, student):
        raise frappe.ValidationError(
            f"Student {student} is not an active member of {from_group}")
    if _active_member(to_group, student):
        raise frappe.ValidationError(
            f"Student {student} is already an active member of {to_group}")
    kind = classify(source, target)
    if not terms.get("allow_transfers"):
        raise frappe.ValidationError(
            "Transfers are not permitted by the governing class-operations policy")
    if kind == "Program" and not terms.get("allow_program_transfers"):
        raise frappe.ValidationError(
            "Transfers between programs are not permitted by the governing policy")
    if kind == "Branch" and not terms.get("allow_branch_transfers"):
        raise frappe.ValidationError(
            "Transfers between branches are not permitted by the governing policy")
    target_start = str(target.th_class_start_date or "")
    if not target_start:
        raise frappe.ValidationError("The target class has no start date")
    window_end = (date.fromisoformat(target_start)
                  + timedelta(days=terms["transfer_window_days"])).isoformat()
    if effective_day > window_end:
        raise frappe.ValidationError(
            f"A transfer into {to_group} must take effect on or before {window_end} "
            f"(start {target_start} plus the policy's "
            f"{terms['transfer_window_days']}-day window)")
    suspension = frappe.get_all(
        "TH Class Suspension",
        filters={"student_group": from_group, "status": "Active",
                 "scope": "Student", "student": student},
        fields=["name", "from_date", "until_date"], limit_page_length=20)
    blocking = [row for row in suspension
                if str(row.get("from_date")) <= effective_day <= str(row.get("until_date"))]
    if blocking:
        raise frappe.ValidationError(
            f"Student {student} is suspended in {from_group} on {effective_day}; "
            "resume the membership before transferring")
    capacity.require_matching_enrollment(student, target, to_group)
    conflicts = timetable_conflicts(student, to_group, effective_day)
    if conflicts:
        first = conflicts[0]
        raise frappe.ValidationError(
            f"The target timetable collides with session {first['other_session']} "
            f"({first['other_group']}) on {first['schedule_date']} "
            f"{first['from_time']}-{first['to_time']}")
    seats = capacity.seat_facts(to_group)
    evidence = {
        "kind": kind,
        "effective_date": effective_day,
        "source": {
            "name": from_group, "program": source.program,
            "academic_year": source.academic_year,
            "academic_term": source.academic_term or "",
            "branch": source.th_branch or "",
            "class_status": source.th_class_status,
        },
        "target": {
            "name": to_group, "program": target.program,
            "academic_year": target.academic_year,
            "academic_term": target.academic_term or "",
            "branch": target.th_branch or "",
            "class_status": target.th_class_status,
            "start_date": target_start,
        },
        "target_seats": {
            "capacity": seats["capacity"], "rostered": seats["rostered"],
            "reserved": seats["reserved"], "available": seats["available"],
        },
        "target_requires_override": seats["available"] < 1,
        "policy_effective_from": terms.get("effective_from", ""),
        "checks": [
            "active source membership", "submitted target-intake enrollment",
            "target class open", "no target timetable collision",
            "no active student suspension", "policy allows this transfer kind",
            "transfer window open",
        ],
    }
    return evidence, seats


def _transfer_row(name, for_update=True):
    if for_update:
        _lock(TRANSFER, name)
    row = frappe.db.get_value(
        TRANSFER, name,
        ["name", "student", "from_group", "to_group", "transfer_kind",
         "effective_date", "reason", "status", "requested_by", "requested_on",
         "pinned_effective_from", "pinned_approver_role", "approved_by",
         "decided_on", "denial_reason", "executed_on", "eligibility_json",
         "preserved_json"], as_dict=True)
    if row is None:
        raise frappe.ValidationError(f"Unknown class transfer: {name}")
    return row


def _terms_for_pin(terms, pinned_from):
    """Judge a decision against the pinned policy, never against today's."""
    if str(terms.get("effective_from", "")) != str(pinned_from):
        raise frappe.ValidationError(
            "The pinned class-operations policy version is no longer the "
            "governing one; re-request the transfer under the current policy")
    return terms


@frappe.whitelist(methods=["POST"])
def request_class_transfer(request_key, student, from_group, to_group, reason,
                           effective_date):
    """Open a transfer request with its eligibility and preservation evidence."""
    from toefl_house.api import _execute

    def work(actor):
        terms = class_operations.require_operations(
            feature="allow_transfers",
            message="Transfers are not permitted by the governing "
                    "class-operations policy")
        student_name = _bounded(student, "Student")
        source = _bounded(from_group, "Source class")
        target = _bounded(to_group, "Target class")
        clean_reason = _reason(reason)
        effective_day = _day(effective_date, "Effective date")
        if effective_day < str(frappe.utils.today()):
            raise frappe.ValidationError("A transfer cannot take effect in the past")
        _lock(GROUP, source)
        _lock(GROUP, target)
        evidence, _seats = _eligibility(student_name, source, target,
                                        effective_day, terms)
        preserved = preserved_evidence(student_name, source)
        doc = frappe.get_doc({
            "doctype": TRANSFER, "student": student_name,
            "from_group": source, "to_group": target,
            "transfer_kind": evidence["kind"],
            "effective_date": effective_day, "reason": clean_reason,
            "status": "Requested", "requested_by": actor,
            "requested_on": frappe.utils.now_datetime(),
            "pinned_effective_from": terms.get("effective_from", ""),
            "pinned_approver_role": terms.get("transfer_approver_role", ""),
            "eligibility_json": json.dumps(evidence, sort_keys=True),
            "preserved_json": json.dumps(preserved, sort_keys=True),
            "synthetic": record_synthetic_flag(),
        })
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        result = {
            "name": doc.name, "student": student_name,
            "from_group": source, "to_group": target,
            "transfer_kind": evidence["kind"],
            "effective_date": effective_day, "status": "Requested",
            "pinned_effective_from": doc.pinned_effective_from,
            "approver_role": doc.pinned_approver_role,
            "target_seats": evidence["target_seats"],
            "target_requires_override": evidence["target_requires_override"],
            "preserved": {
                key: (value if not isinstance(value, dict) else value.get("count"))
                for key, value in preserved.items() if isinstance(value, dict)},
        }
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, student_name, source,
                                               target, effective_day, "Requested"]))

    return _execute("request_class_transfer", request_key,
                    {"student": student, "from_group": from_group,
                     "to_group": to_group, "reason": reason,
                     "effective_date": effective_date}, work)


@frappe.whitelist(methods=["POST"])
def approve_class_transfer(request_key, transfer, override=""):
    """Approve and execute a pending transfer, re-proving every fact."""
    from toefl_house.api import _execute

    def work(actor):
        terms = class_operations.require_operations(
            feature="allow_transfers",
            message="Transfers are not permitted by the governing "
                    "class-operations policy")
        name = _bounded(transfer, "Class transfer")
        row = _transfer_row(name)
        if row["status"] != "Requested":
            raise frappe.ValidationError(
                f"Class transfer {name} is {row['status']}")
        _terms_for_pin(terms, row.get("pinned_effective_from"))
        role = row.get("pinned_approver_role") or ""
        if not role or role not in frappe.get_roles(actor):
            raise frappe.PermissionError(
                "The transfer requires the policy-configured approver role: "
                + (role or "not configured"))
        if actor == row.get("requested_by"):
            raise frappe.PermissionError(
                "A transfer cannot be approved by the person who requested it")
        source, target, student = row["from_group"], row["to_group"], row["student"]
        _lock(GROUP, source)
        _lock(GROUP, target)
        effective_day = str(row["effective_date"])
        evidence, _seats = _eligibility(student, source, target,
                                        effective_day, terms)
        seat = capacity.assert_seat_available(target, student, override)
        from toefl_house.teaching import _set_membership
        label = frappe.db.get_value(STUDENT, student, "student_name") or student
        _set_membership(source, student, label, False)
        _set_membership(target, student, label, True)
        doc = frappe.get_doc(TRANSFER, name)
        doc.flags.ignore_permissions = True
        doc.status = "Executed"
        doc.approved_by = actor
        doc.decided_on = frappe.utils.now_datetime()
        doc.executed_on = frappe.utils.now_datetime()
        doc.save(ignore_permissions=True)
        result = {
            "name": doc.name, "status": "Executed", "student": student,
            "from_group": source, "to_group": target,
            "transfer_kind": doc.transfer_kind,
            "effective_date": effective_day,
            "approved_by": actor, "override": seat["override"],
            "preserved": json.loads(row.get("preserved_json") or "{}"),
            "policy_effective_from": terms.get("effective_from", ""),
        }
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, student, source, target,
                                               effective_day, "Executed"]))

    return _execute("approve_class_transfer", request_key,
                    {"transfer": transfer, "override": override}, work)


@frappe.whitelist(methods=["POST"])
def deny_class_transfer(request_key, transfer, reason):
    """Deny a pending transfer; the student stays in the source class."""
    from toefl_house.api import _execute

    def work(actor):
        name = _bounded(transfer, "Class transfer")
        row = _transfer_row(name)
        if row["status"] != "Requested":
            raise frappe.ValidationError(
                f"Class transfer {name} is {row['status']}")
        role = row.get("pinned_approver_role") or ""
        if not role or role not in frappe.get_roles(actor):
            raise frappe.PermissionError(
                "The transfer requires the policy-configured approver role: "
                + (role or "not configured"))
        if actor == row.get("requested_by"):
            raise frappe.PermissionError(
                "A transfer cannot be decided by the person who requested it")
        clean_reason = _reason(reason)
        doc = frappe.get_doc(TRANSFER, name)
        doc.flags.ignore_permissions = True
        doc.status = "Denied"
        doc.approved_by = actor
        doc.decided_on = frappe.utils.now_datetime()
        doc.denial_reason = clean_reason
        doc.save(ignore_permissions=True)
        result = {"name": doc.name, "status": "Denied",
                  "denial_reason": clean_reason}
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, "Denied", clean_reason]))

    return _execute("deny_class_transfer", request_key,
                    {"transfer": transfer, "reason": reason}, work)


@frappe.whitelist(methods=["POST"])
def cancel_class_transfer(request_key, transfer, reason):
    """Withdraw a pending request (only the requester may cancel it)."""
    from toefl_house.api import _execute

    def work(actor):
        name = _bounded(transfer, "Class transfer")
        row = _transfer_row(name)
        if row["status"] != "Requested":
            raise frappe.ValidationError(
                f"Class transfer {name} is {row['status']}")
        if actor != row.get("requested_by"):
            raise frappe.PermissionError(
                "Only the requester can cancel a pending transfer")
        clean_reason = _reason(reason)
        doc = frappe.get_doc(TRANSFER, name)
        doc.flags.ignore_permissions = True
        doc.status = "Cancelled"
        doc.decided_on = frappe.utils.now_datetime()
        doc.denial_reason = clean_reason
        doc.save(ignore_permissions=True)
        result = {"name": doc.name, "status": "Cancelled"}
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, "Cancelled", clean_reason]))

    return _execute("cancel_class_transfer", request_key,
                    {"transfer": transfer, "reason": reason}, work)


__all__ = ["TRANSFER", "TRANSFER_KINDS", "classify", "timetable_conflicts",
           "preserved_evidence", "request_class_transfer",
           "approve_class_transfer", "deny_class_transfer",
           "cancel_class_transfer"]

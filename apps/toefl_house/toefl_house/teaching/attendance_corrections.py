"""S9 attendance corrections (OD-NEW-06): a D3-shaped request/approve/deny
flow over submitted native Student Attendance, governed by an
effective-dated owner policy (S7/S8 singleton mechanics).

Fail-closed by construction: with no policy row, a retired policy, or
no effective version, new requests are denied — the owner opts in by
appending a version, never by default. Policy terms are the D3 pair
(approver role, correction window in days); each request VALUE-PINS
the governing terms at creation, and approvals judge against the pin
even after the version is superseded or the policy retired. Live
record facts (existence, submitted state, current mark, session date)
are always re-proven against the live records.

The native artifact is cancel-plus-replacement: approval voids the
erroneous record (docstatus 2, its row preserved) and submits a
corrected record for the same student and session. History therefore
shows both marks; no mark is ever rewritten in place. The request row
carries the decision trail (requester, approver, replacement link).
"""
from datetime import date, timedelta
import frappe

from toefl_house.academic import rules
from toefl_house.api import _execute
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import (ATTENDANCE_STATUSES, digest,
                                validate_correction_window_days)
from toefl_house.security import record_synthetic_flag
from toefl_house.teaching import _roster_read

POLICY = "TH Attendance Correction Policy"
REQUEST = "TH Attendance Correction Request"
ATTENDANCE = "Student Attendance"
SCHEDULE = "Course Schedule"


def _name(value, label):
    if not isinstance(value, str) or not value or len(value) > 140:
        raise frappe.ValidationError(f"{label} required")
    return value


def validate_terms(approver_role, window_days):
    """Shape-check one policy version's terms (command + controller)."""
    if not isinstance(approver_role, str) or not approver_role \
            or len(approver_role) > 140:
        raise ValueError("Approver role required")
    days = validate_correction_window_days(window_days)
    return approver_role, days


def _policy_doc(code, for_update=False):
    name = frappe.db.get_value(POLICY, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown attendance-correction policy: {code}")
    return frappe.get_doc(POLICY, name, for_update=for_update)


def _as_bool(value, what):
    if isinstance(value, str) and value.strip().lower() in ("1", "true", "yes"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("0", "false", "no"):
        return False
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise ValueError(f"{what} must be true or false")


def _policy_result(doc, extra=None):
    versions = [row.as_dict() for row in (doc.get("versions") or [])]
    governing = configuration_rules.resolve_governing(
        versions, frappe.utils.today())
    result = {
        "name": doc.name, "code": doc.code, "title": doc.title,
        "status": doc.status, "version_count": len(versions),
        "governing_effective_from": (
            str(governing.get("effective_from")) if governing else ""),
        "governing_approver_role": (
            (governing.get("approver_role") or "") if governing else ""),
        "governing_window_days": (
            governing.get("correction_window_days")
            if governing else ""),
    }
    if extra:
        result.update(extra)
    return result


def governing_correction_terms(on_date=None):
    """Read-only resolver: governing terms, or {} when unconfigured.

    No receipt: a pure read used inside command work() closures.
    Fail-closed in three ways — no policy row, retired policy, no
    effective version — and every one means new requests refuse.
    """
    rows = frappe.db.get_all(POLICY, fields=["name"], limit=1)
    if not rows:
        return {}
    doc = frappe.get_doc(POLICY, rows[0]["name"])
    if doc.status != "Active":
        return {}
    versions = [row.as_dict() for row in (doc.get("versions") or [])]
    governing = configuration_rules.resolve_governing(
        versions, on_date or frappe.utils.today())
    if not governing:
        return {}
    return {
        "effective_from": str(governing.get("effective_from") or ""),
        "approver_role": governing.get("approver_role") or "",
        "window_days": governing.get("correction_window_days"),
    }


@frappe.whitelist(methods=["POST"])
def create_attendance_correction_policy(request_key, code, title,
                                        description=""):
    """Define the attendance-correction policy shell (OD-NEW-06 mechanism).

    Creates the single policy row with NO versions: corrections stay
    denied until the Course Owner appends the first effective-dated
    version. The shell carries no terms — the owner's choice arrives
    only through versions, and only after owner decision OD-NEW-06.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Attendance-correction policy title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.get_all(POLICY, fields=["name"], limit=1):
            raise frappe.ValidationError(
                "An attendance-correction policy already exists; version it instead")
        if frappe.db.exists(POLICY, clean_code):
            raise frappe.ValidationError(
                f"Attendance-correction policy {clean_code} already exists")
        doc = frappe.get_doc({
            "doctype": POLICY,
            "code": clean_code, "title": clean_title, "status": "Active",
            "description": clean_description,
        })
        doc.insert(ignore_permissions=True)
        return _policy_result(doc), {
            "target": doc.name, "before_hash": "",
            "after_hash": configuration_rules.snapshot_digest([]),
        }

    payload = {"code": code, "title": title, "description": description}
    return configuration_audit.execute(
        "create_attendance_correction_policy", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_attendance_correction_policy_version(request_key, policy,
                                              effective_from, reason,
                                              approver_role,
                                              correction_window_days):
    """Append an effective-dated attendance-correction policy version.

    The version enacts one approver role and correction window from
    ``effective_from``; a change reason is mandatory; backdated or
    same-day versions are refused. The superseded version is closed,
    never rewritten.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            clean_role, clean_days = validate_terms(approver_role,
                                                    correction_window_days)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if not frappe.db.exists("Role", clean_role):
            raise frappe.ValidationError("Unknown approver role")
        doc = _policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Attendance-correction policy {clean_code} is retired; reactivate it "
                "before adding a version")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="attendance-correction policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.append("versions", {
            "effective_from": clean_from, "approver_role": clean_role,
            "correction_window_days": clean_days,
            "reason": clean_reason, "set_by": actor,
            "set_on": frappe.utils.now_datetime()})
        if current:
            # Close the superseded version; never rewrite its meaning, only
            # record the date it stopped governing new activity.
            for row in doc.get("versions") or []:
                if (str(row.get("effective_from")) == str(current.get("effective_from"))
                        and not row.get("superseded_on")):
                    row.superseded_on = clean_from
                    break
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("versions") or [])])
        return _policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "effective_from": effective_from,
               "reason": reason, "approver_role": approver_role,
               "correction_window_days": correction_window_days}
    return configuration_audit.execute(
        "set_attendance_correction_policy_version", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_attendance_correction_policy_status(request_key, policy, active):
    """Deactivate (retire) or reactivate the attendance-correction policy.

    Retiring is the off-switch: with no active policy new requests
    refuse again. Earlier requests keep their pinned terms and recorded
    receipts — the policy gates creation only, and history is never
    rewritten by a later switch.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            flag = _as_bool(active, "active")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _policy_doc(clean_code, for_update=True)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.status = "Active" if flag else "Retired"
        doc.save(ignore_permissions=True)
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        after = digest(["status", doc.status,
                        configuration_rules.snapshot_digest(versions)])
        return _policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "active": active}
    return configuration_audit.execute(
        "set_attendance_correction_policy_status", request_key, payload, work)


def _pending_request(req_name):
    if not frappe.db.exists(REQUEST, req_name):
        raise frappe.ValidationError("Unknown attendance-correction request")
    frappe.db.sql("select name from `tabTH Attendance Correction Request` "
                  "where name=%s for update", (req_name,))
    req = frappe.get_doc(REQUEST, req_name)
    if req.status != "Requested":
        raise frappe.ValidationError("Attendance-correction request is not pending")
    return req


def _require_approver(pinned_role, actor):
    if pinned_role not in frappe.get_roles(actor):
        raise frappe.PermissionError(
            "Actor does not hold the policy-configured approver role")


def _locked_attendance_facts(att_name):
    frappe.db.sql("select name from `tabStudent Attendance` where name=%s for update",
                  (att_name,))
    facts = frappe.db.get_value(
        ATTENDANCE, att_name,
        ["student", "course_schedule", "status", "docstatus"], as_dict=True)
    if facts is None:
        raise frappe.ValidationError("Unknown student attendance record")
    return facts


@frappe.whitelist(methods=["POST"])
def request_attendance_correction(request_key, attendance, requested_status,
                                  reason):
    """Request a correction of one submitted attendance mark.

    Executed by the Attendance Recorder inside an active policy. Only
    submitted records are correctable; the requested mark must be a
    native status that differs from the submitted one; each record
    carries at most one pending request. The governing terms are
    value-pinned onto the request — approvals judge against the pin,
    never against the current policy.
    """
    def work(actor):
        att_name = _name(attendance, "Student Attendance")
        if requested_status not in ATTENDANCE_STATUSES:
            raise frappe.ValidationError("Unsupported attendance status")
        if not isinstance(reason, str) or not reason or len(reason) > 300:
            raise frappe.ValidationError(
                "Correction reason is required (at most 300 characters)")
        terms = governing_correction_terms()
        if not terms:
            raise frappe.ValidationError(
                "No active attendance-correction policy; corrections fail "
                "closed until one is configured")
        if not frappe.db.exists(ATTENDANCE, att_name):
            raise frappe.ValidationError("Unknown student attendance record")
        facts = _locked_attendance_facts(att_name)
        if int(facts.docstatus or 0) != 1:
            raise frappe.ValidationError(
                "Only submitted attendance marks are correctable")
        if facts.status == requested_status:
            raise frappe.ValidationError(
                "Correction must change the mark; it already reads "
                f"{facts.status}")
        if frappe.db.exists(REQUEST, {"attendance": att_name,
                                      "status": "Requested"}):
            raise frappe.ValidationError(
                "This attendance record already has a pending correction request")
        req = frappe.get_doc({
            "doctype": REQUEST, "attendance": att_name,
            "course_schedule": facts.course_schedule,
            "from_status": facts.status, "requested_status": requested_status,
            "reason": reason, "requested_by": actor,
            "requested_on": frappe.utils.now_datetime(),
            "pinned_effective_from": terms["effective_from"],
            "pinned_approver_role": terms["approver_role"],
            "pinned_window_days": terms["window_days"],
            "status": "Requested", "synthetic": record_synthetic_flag(),
        })
        req.flags.ignore_permissions = True
        req.insert(ignore_permissions=True)
        result = {"name": req.name, "status": "Requested",
                  "attendance": att_name, "from_status": facts.status,
                  "requested_status": requested_status}
        return result, dict(target=req.name,
                            after_hash=digest([req.name, "Requested",
                                               att_name, facts.status,
                                               requested_status]))

    return _execute("request_attendance_correction", request_key,
                    {"attendance": attendance,
                     "requested_status": requested_status,
                     "reason": reason}, work)


@frappe.whitelist(methods=["POST"])
def approve_attendance_correction(request_key, request):
    """Approve and post the correction as cancel-plus-replacement.

    Dual key: Attendance Recorder command access plus the
    policy-configured approver role from the request's pin. The
    erroneous record is voided (its row preserved) and a corrected
    record for the same student and session is submitted — history
    shows both marks. The record is locked and the request-time
    invariants re-proven here: a stale approval would void a mark
    that no longer matches the recorded from-status.
    """
    def work(actor):
        req = _pending_request(_name(request, "Attendance-correction request"))
        _require_approver(req.pinned_approver_role, actor)
        facts = _locked_attendance_facts(req.attendance)
        if int(facts.docstatus or 0) != 1:
            raise frappe.ValidationError(
                "The attendance record is no longer submitted; this correction "
                "request can no longer be approved")
        if facts.status != req.from_status:
            raise frappe.ValidationError(
                "The attendance mark changed after this request was raised; "
                "raise a new request for the current mark")
        session_date = frappe.db.get_value(SCHEDULE, facts.course_schedule,
                                           "schedule_date")
        limit = date.fromisoformat(str(session_date)) + timedelta(
            days=int(req.pinned_window_days))
        if date.today() > limit:
            raise frappe.ValidationError(
                "Correction window for this session has closed")
        original = frappe.get_doc(ATTENDANCE, req.attendance)
        original.flags.ignore_permissions = True
        original.cancel()
        if int(original.docstatus or 0) != 2:
            raise frappe.ValidationError("The erroneous mark was not voided")
        with _roster_read():
            fixed = frappe.get_doc(dict(
                doctype=ATTENDANCE, naming_series="EDU-ATT-.YYYY.-",
                student=facts.student, course_schedule=facts.course_schedule,
                status=req.requested_status))
            fixed.flags.ignore_permissions = True
            fixed.flags.ignore_links = True
            fixed.insert(ignore_permissions=True)
            fixed.flags.ignore_permissions = True
            fixed.flags.ignore_links = True
            fixed.submit()
        if int(fixed.docstatus or 0) != 1:
            raise frappe.ValidationError("Replacement attendance must be submitted")
        if fixed.status != req.requested_status:
            raise frappe.ValidationError(
                "Replacement mark does not match the approved request")
        req.flags.ignore_permissions = True
        req.status = "Posted"
        req.approved_by = actor
        req.replacement_attendance = fixed.name
        req.save(ignore_permissions=True)
        result = {"name": req.name, "status": "Posted",
                  "attendance": req.attendance,
                  "replacement_attendance": fixed.name,
                  "from_status": req.from_status,
                  "requested_status": req.requested_status}
        return result, dict(target=req.name,
                            before_hash=digest([req.name, "Requested"]),
                            after_hash=digest([req.name, "Posted", fixed.name]))

    return _execute("approve_attendance_correction", request_key,
                    {"request": request}, work)


@frappe.whitelist(methods=["POST"])
def deny_attendance_correction(request_key, request):
    """Deny a pending attendance-correction request; no record is voided.

    The approver role comes from the version the request pinned at
    creation, never from whatever is current.
    """
    def work(actor):
        req = _pending_request(_name(request, "Attendance-correction request"))
        _require_approver(req.pinned_approver_role, actor)
        req.flags.ignore_permissions = True
        req.status = "Denied"
        req.approved_by = actor
        req.save(ignore_permissions=True)
        result = {"name": req.name, "status": "Denied"}
        return result, dict(target=req.name,
                            before_hash=digest([req.name, "Requested"]),
                            after_hash=digest([req.name, "Denied"]))

    return _execute("deny_attendance_correction", request_key,
                    {"request": request}, work)

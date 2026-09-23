"""S10 enrollment exits (OD-NEW-07): withdrawals single-shot, dismissals by
D3-shaped request/approve/deny, both governed by an effective-dated owner
policy (S7/S8/S9 singleton mechanics).

Fail-closed by construction: with no policy row, a retired policy, or no
effective version, exits are denied — the owner opts in by appending a
version, never by default. Dismissal requests VALUE-PIN the governing
terms at creation, and decisions judge against the pin even after the
version is superseded or the policy retired. Live enrollment facts
(existence, submitted state, billed Fees) are always re-proven against
the live records.

The native artifact is cancel: the exit deletes the derived Course
Enrollments explicitly (native would delete them anyway inside
ProgramEnrollment.on_cancel, but without the command's permission
context) and cancels the submitted Program Enrollment (docstatus 2, its
row preserved). Roster rows, attendance marks and admission history are
untouched — exits end the registration, they never rewrite the past.
The receivable consequence is referenced, never re-implemented: an exit
is refused while submitted Fees bill the enrollment, and the exit row
snapshots every Fees on record so finance acts on native documents.
"""

from datetime import date
import frappe

from toefl_house.academic import rules
from toefl_house.api import _execute
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest
from toefl_house.security import record_synthetic_flag

POLICY = "TH Enrollment Exit Policy"
EXIT = "TH Enrollment Exit"
PE = "Program Enrollment"
CE = "Course Enrollment"
FEES = "Fees"

WITHDRAWAL = "Withdrawal"
DISMISSAL = "Dismissal"
REQUESTED = "Requested"
POSTED = "Posted"
DENIED = "Denied"

_FEES_STATUS = {0: "Draft", 1: "Submitted", 2: "Cancelled"}


def _name(value, label):
    if not isinstance(value, str) or not value or len(value) > 140:
        raise frappe.ValidationError(f"{label} required")
    return value


def validate_terms(approver_role):
    """Shape-check one policy version's terms (command + controller)."""
    if not isinstance(approver_role, str) or not approver_role \
            or len(approver_role) > 140:
        raise ValueError("Approver role required")
    return approver_role


def _policy_doc(code, for_update=False):
    name = frappe.db.get_value(POLICY, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown enrollment-exit policy: {code}")
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
    }
    if extra:
        result.update(extra)
    return result


def governing_exit_terms(on_date=None):
    """Read-only resolver: governing terms, or {} when unconfigured.

    No receipt: a pure read used inside command work() closures.
    Fail-closed in three ways — no policy row, retired policy, no
    effective version — and every one means new exits refuse.
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
    }


@frappe.whitelist(methods=["POST"])
def create_enrollment_exit_policy(request_key, code, title, description=""):
    """Define the enrollment-exit policy shell (OD-NEW-07 mechanism).

    Creates the single policy row with NO versions: exits stay denied
    until the Course Owner appends the first effective-dated version.
    The shell carries no terms — the owner's choice arrives only through
    versions, and only after owner decision OD-NEW-07.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Enrollment-exit policy title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.get_all(POLICY, fields=["name"], limit=1):
            raise frappe.ValidationError(
                "An enrollment-exit policy already exists; version it instead")
        if frappe.db.exists(POLICY, clean_code):
            raise frappe.ValidationError(
                f"Enrollment-exit policy {clean_code} already exists")
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
        "create_enrollment_exit_policy", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_enrollment_exit_policy_version(request_key, policy, effective_from,
                                       reason, approver_role):
    """Append an effective-dated enrollment-exit policy version.

    The version enacts one dismissal approver role from
    ``effective_from``; a change reason is mandatory; backdated or
    same-day versions are refused. The superseded version is closed,
    never rewritten.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            clean_role = validate_terms(approver_role)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if not frappe.db.exists("Role", clean_role):
            raise frappe.ValidationError("Unknown approver role")
        doc = _policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Enrollment-exit policy {clean_code} is retired; reactivate it "
                "before adding a version")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="enrollment-exit policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.append("versions", {
            "effective_from": clean_from, "approver_role": clean_role,
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
               "reason": reason, "approver_role": approver_role}
    return configuration_audit.execute(
        "set_enrollment_exit_policy_version", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_enrollment_exit_policy_status(request_key, policy, active):
    """Deactivate (retire) or reactivate the enrollment-exit policy.

    Retiring is the off-switch: with no active policy new exits refuse
    again. Earlier exits keep their pinned terms and recorded receipts —
    the policy gates creation only, and history is never rewritten by a
    later switch.
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
        "set_enrollment_exit_policy_status", request_key, payload, work)


def _locked_enrollment_facts(pe_name):
    if not frappe.db.exists(PE, pe_name):
        raise frappe.ValidationError("Unknown program enrollment")
    frappe.db.sql("select name from `tabProgram Enrollment` where name=%s for update",
                  (pe_name,))
    facts = frappe.db.get_value(
        PE, pe_name,
        ["student", "program", "academic_year", "enrollment_date", "docstatus"],
        as_dict=True)
    if facts is None:
        raise frappe.ValidationError("Unknown program enrollment")
    return facts


def _refuse_live_fees(pe_name):
    billed = frappe.db.get_all(
        FEES, filters={"program_enrollment": pe_name, "docstatus": 1},
        fields=["name"], limit=1)
    if billed:
        raise frappe.ValidationError(
            f"Program enrollment {pe_name} is billed by submitted Fees "
            f"{billed[0]['name']}; settle or void the receivable through "
            "finance before exiting the enrollment")


def _fees_snapshot(pe_name):
    rows = frappe.db.get_all(
        FEES, filters={"program_enrollment": pe_name},
        fields=["name", "docstatus", "outstanding_amount"], order_by="name")
    if not rows:
        return "no Fees on record"
    lines = []
    for row in rows:
        status = _FEES_STATUS.get(int(row.get("docstatus") or 0), "Draft")
        outstanding = row.get("outstanding_amount") or 0
        line = f"{row['name']} ({status})"
        if outstanding:
            line = f"{row['name']} ({status}, outstanding {outstanding})"
        lines.append(line)
    return "; ".join(lines)


def _refuse_prior_exit(pe_name):
    if frappe.db.exists(EXIT, {"program_enrollment": pe_name, "status": POSTED}):
        raise frappe.ValidationError(
            "This enrollment already has a posted exit; exits are single-shot")
    if frappe.db.exists(EXIT, {"program_enrollment": pe_name, "status": REQUESTED}):
        raise frappe.ValidationError(
            "This enrollment has a pending dismissal request; decide it first")


def _check_exit_date(clean_exit, enrollment_date):
    today = date.today()
    if clean_exit > today:
        raise frappe.ValidationError("Exit date cannot be in the future")
    enrolled = date.fromisoformat(str(enrollment_date))
    if clean_exit < enrolled:
        raise frappe.ValidationError("Exit date cannot precede the enrollment date")


def _cancel_enrollment(pe_name):
    """Delete derived Course Enrollments, then cancel the enrollment.

    Native ProgramEnrollment.on_cancel deletes the Course Enrollments
    itself, but its delete_doc calls carry no permission context — the
    command deletes them explicitly first (identical outcome,
    deterministic permission), leaving native on_cancel a no-op.
    """
    ce_names = frappe.db.get_all(
        CE, filters={"program_enrollment": pe_name}, pluck="name")
    for ce_name in ce_names:
        frappe.delete_doc(CE, ce_name, ignore_permissions=True)
    pe = frappe.get_doc(PE, pe_name)
    pe.flags.ignore_permissions = True
    pe.cancel()
    if int(pe.docstatus or 0) != 2:
        raise frappe.ValidationError("The program enrollment was not cancelled")
    return list(ce_names)


def _pending_exit(exit_name):
    if not frappe.db.exists(EXIT, exit_name):
        raise frappe.ValidationError("Unknown enrollment exit")
    frappe.db.sql("select name from `tabTH Enrollment Exit` where name=%s for update",
                  (exit_name,))
    req = frappe.get_doc(EXIT, exit_name)
    if req.status != REQUESTED:
        raise frappe.ValidationError("Enrollment exit is not pending")
    if req.exit_kind != DISMISSAL:
        raise frappe.ValidationError("Only dismissal exits await a decision")
    return req


def _require_approver(pinned_role, actor):
    if pinned_role not in frappe.get_roles(actor):
        raise frappe.PermissionError(
            "Actor does not hold the policy-configured approver role")


def _check_reason(reason):
    if not isinstance(reason, str) or not reason or len(reason) > 300:
        raise frappe.ValidationError(
            "Exit reason is required (at most 300 characters)")
    return reason


@frappe.whitelist(methods=["POST"])
def withdraw_enrollment(request_key, program_enrollment, exit_date, reason):
    """Withdraw one submitted enrollment, single-shot.

    Executed by the Enrollment Officer inside an active policy: the
    student-initiated exit records who left, when, and why, then ends
    the registration. Only submitted enrollments are withdrawable; a
    pending dismissal decides first; an exit dated in the future or
    before the enrollment is refused; submitted Fees block the exit
    until finance settles the receivable.
    """
    def work(actor):
        pe_name = _name(program_enrollment, "Program enrollment")
        clean_reason = _check_reason(reason)
        try:
            clean_exit = date.fromisoformat(rules.parse_date(exit_date))
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        terms = governing_exit_terms()
        if not terms:
            raise frappe.ValidationError(
                "No active enrollment-exit policy; exits fail closed "
                "until one is configured")
        facts = _locked_enrollment_facts(pe_name)
        if int(facts.docstatus or 0) != 1:
            raise frappe.ValidationError(
                "Only submitted program enrollments can be withdrawn")
        _check_exit_date(clean_exit, facts.enrollment_date)
        _refuse_prior_exit(pe_name)
        _refuse_live_fees(pe_name)
        cancelled = _cancel_enrollment(pe_name)
        exit_doc = frappe.get_doc({
            "doctype": EXIT, "program_enrollment": pe_name,
            "student": facts.student, "exit_kind": WITHDRAWAL,
            "exit_date": str(clean_exit), "reason": clean_reason,
            "status": POSTED, "requested_by": actor,
            "requested_on": frappe.utils.now_datetime(),
            "pinned_effective_from": terms["effective_from"],
            "pinned_approver_role": terms["approver_role"],
            "approved_by": actor,
            "fees_snapshot": _fees_snapshot(pe_name),
            "cancelled_courses": ", ".join(cancelled) if cancelled else "none",
            "synthetic": record_synthetic_flag(),
        })
        exit_doc.flags.ignore_permissions = True
        exit_doc.insert(ignore_permissions=True)
        result = {"name": exit_doc.name, "status": POSTED,
                  "exit_kind": WITHDRAWAL, "program_enrollment": pe_name,
                  "exit_date": str(clean_exit),
                  "cancelled_course_enrollments": len(cancelled)}
        return result, dict(target=exit_doc.name,
                            after_hash=digest([exit_doc.name, POSTED, pe_name,
                                               str(clean_exit)]))

    return _execute("withdraw_enrollment", request_key,
                    {"program_enrollment": program_enrollment,
                     "exit_date": exit_date, "reason": reason}, work)


@frappe.whitelist(methods=["POST"])
def request_enrollment_dismissal(request_key, program_enrollment, reason):
    """Request the dismissal of one submitted enrollment.

    Executed by the Enrollment Officer inside an active policy. The
    authority's decision date becomes the exit date at approval, so the
    request carries no date — only the enrollment and the reason. The
    governing terms are value-pinned onto the exit; the decision judges
    against the pin, never against the current policy.
    """
    def work(actor):
        pe_name = _name(program_enrollment, "Program enrollment")
        clean_reason = _check_reason(reason)
        terms = governing_exit_terms()
        if not terms:
            raise frappe.ValidationError(
                "No active enrollment-exit policy; exits fail closed "
                "until one is configured")
        facts = _locked_enrollment_facts(pe_name)
        if int(facts.docstatus or 0) != 1:
            raise frappe.ValidationError(
                "Only submitted program enrollments can be dismissed")
        _refuse_prior_exit(pe_name)
        _refuse_live_fees(pe_name)
        exit_doc = frappe.get_doc({
            "doctype": EXIT, "program_enrollment": pe_name,
            "student": facts.student, "exit_kind": DISMISSAL,
            "reason": clean_reason, "status": REQUESTED,
            "requested_by": actor,
            "requested_on": frappe.utils.now_datetime(),
            "pinned_effective_from": terms["effective_from"],
            "pinned_approver_role": terms["approver_role"],
            "fees_snapshot": _fees_snapshot(pe_name),
            "synthetic": record_synthetic_flag(),
        })
        exit_doc.flags.ignore_permissions = True
        exit_doc.insert(ignore_permissions=True)
        result = {"name": exit_doc.name, "status": REQUESTED,
                  "exit_kind": DISMISSAL, "program_enrollment": pe_name}
        return result, dict(target=exit_doc.name,
                            after_hash=digest([exit_doc.name, REQUESTED, pe_name]))

    return _execute("request_enrollment_dismissal", request_key,
                    {"program_enrollment": program_enrollment,
                     "reason": reason}, work)


@frappe.whitelist(methods=["POST"])
def approve_enrollment_dismissal(request_key, exit):
    """Approve a pending dismissal and post it as an exit.

    Dual key: Enrollment Officer command access plus the
    policy-configured approver role from the exit's pin. The enrollment
    is locked and the request-time invariants re-proven here: a stale
    approval must not exit an enrollment that was meanwhile withdrawn,
    re-billed, or otherwise moved. The decision date is the exit date.
    """
    def work(actor):
        req = _pending_exit(_name(exit, "Enrollment exit"))
        _require_approver(req.pinned_approver_role, actor)
        facts = _locked_enrollment_facts(req.program_enrollment)
        if int(facts.docstatus or 0) != 1:
            raise frappe.ValidationError(
                "The program enrollment is no longer submitted; this "
                "dismissal can no longer be approved")
        _refuse_live_fees(req.program_enrollment)
        clean_exit = date.today()
        _check_exit_date(clean_exit, facts.enrollment_date)
        cancelled = _cancel_enrollment(req.program_enrollment)
        req.flags.ignore_permissions = True
        req.status = POSTED
        req.exit_date = str(clean_exit)
        req.approved_by = actor
        req.fees_snapshot = _fees_snapshot(req.program_enrollment)
        req.cancelled_courses = ", ".join(cancelled) if cancelled else "none"
        req.save(ignore_permissions=True)
        result = {"name": req.name, "status": POSTED,
                  "exit_kind": DISMISSAL,
                  "program_enrollment": req.program_enrollment,
                  "exit_date": str(clean_exit),
                  "cancelled_course_enrollments": len(cancelled)}
        return result, dict(target=req.name,
                            before_hash=digest([req.name, REQUESTED]),
                            after_hash=digest([req.name, POSTED, str(clean_exit)]))

    return _execute("approve_enrollment_dismissal", request_key,
                    {"exit": exit}, work)


@frappe.whitelist(methods=["POST"])
def deny_enrollment_dismissal(request_key, exit):
    """Deny a pending dismissal; the enrollment stays submitted.

    The approver role comes from the version the exit pinned at
    request time, never from whatever is current.
    """
    def work(actor):
        req = _pending_exit(_name(exit, "Enrollment exit"))
        _require_approver(req.pinned_approver_role, actor)
        req.flags.ignore_permissions = True
        req.status = DENIED
        req.approved_by = actor
        req.save(ignore_permissions=True)
        result = {"name": req.name, "status": DENIED}
        return result, dict(target=req.name,
                            before_hash=digest([req.name, REQUESTED]),
                            after_hash=digest([req.name, DENIED]))

    return _execute("deny_enrollment_dismissal", request_key,
                    {"exit": exit}, work)

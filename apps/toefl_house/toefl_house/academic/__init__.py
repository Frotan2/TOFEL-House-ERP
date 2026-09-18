"""Owner configuration commands: the Academic Control Plane's guarded gate.

This is a governance surface in the administration precedent
(``toefl_house.administration``): NOT synthetic-gated — the Course Owner
configures the real institution, exactly like role governance — and fail-closed
on every input. The Course Owner role is checked at the command gate; native
records are then written inside the gate, so no additional native write
authority is granted to anybody.

What this deliberately is NOT:
- not a second Program/Enrollment/Fee authority: levels ARE native ``Program``
  records; enrollments, fee structures, classes and assessments consume them
  through native links (docs/product/CONFIGURATION-PLANE.md);
- not a rule engine: structured configuration + validation + effective dating;
- not deletable: configuration is deactivated/retired, never removed, and the
  doctype permissions carry no delete for any role.

Audit: native ``Version`` (track_changes on both configuration doctypes)
records who/what/before/after/when; duration versions additionally carry
set_by/set_on/reason/effective_from as first-class data because the effective
date IS business meaning, not just audit metadata.
"""
import frappe

from toefl_house.academic import rules
from toefl_house.policy import validate_request_key

PROGRAM = "TH Academic Program"
LEVEL = "TH Program Level"
DURATION = "TH Level Duration"
NATIVE_PROGRAM = "Program"
ENROLLMENT = "Program Enrollment"


def _require_course_owner():
    user = frappe.session.user
    if user in (None, "Guest", "Administrator") or "Course Owner" not in set(frappe.get_roles(user)):
        raise frappe.PermissionError(
            "The Course Owner configures the academic control plane; "
            "ask the Course Owner for this change")
    return user


def _context():
    return (frappe.utils.now_datetime().isoformat(timespec="seconds"),
            frappe.utils.today())


def _family_doc(code, for_update=False):
    name = frappe.db.get_value(PROGRAM, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown program: {code}")
    return frappe.get_doc(PROGRAM, name, for_update=for_update)


def _level_doc(code, for_update=False):
    name = frappe.db.get_value(LEVEL, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown level: {code}")
    return frappe.get_doc(LEVEL, name, for_update=for_update)


@frappe.whitelist(methods=["POST"])
def create_program(request_key, code, title, description=""):
    """Define a program family (e.g. a language track the institution sells).

    Retry-safe by the unique code: a replayed request fails as a duplicate
    instead of double-applying. The family owns no money and no enrollment —
    it orders and governs its levels.
    """
    _require_course_owner()
    try:
        validate_request_key(request_key)
        clean_code = rules.validate_code(code)
        clean_title = rules.validate_title(title, "Program title")
        clean_description = rules.validate_reason(description)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    if frappe.db.exists(PROGRAM, clean_code):
        raise frappe.ValidationError(f"Program {clean_code} already exists")
    doc = frappe.get_doc({
        "doctype": PROGRAM, "code": clean_code, "title": clean_title,
        "status": "Active", "description": clean_description,
    })
    doc.insert(ignore_permissions=True)
    return _program_result(doc)


@frappe.whitelist(methods=["POST"])
def create_level(request_key, family, code, title, sequence,
                 duration_value, duration_unit, effective_from, next_level=""):
    """Define one level of a program family and anchor it to a native Program.

    The native Education ``Program`` is created here so that native Program
    Enrollment, Fee Structure (which is keyed per Program), Student Group,
    Assessment Plan and every dashboard consume the level without any
    TOEFL-specific master. The anchor is written once and never changed.
    """
    actor = _require_course_owner()
    try:
        validate_request_key(request_key)
        clean_family = rules.validate_code(family)
        clean_code = rules.validate_code(code)
        clean_title = rules.validate_title(title, "Level title")
        clean_sequence = rules.validate_sequence(sequence)
        clean_value = rules.validate_duration_value(duration_value, duration_unit)
        clean_from = rules.parse_date(effective_from)
        clean_next = rules.validate_reason(next_level or "")
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc

    family_doc = _family_doc(clean_family, for_update=True)
    if family_doc.status != "Active":
        raise frappe.ValidationError(
            f"Program {clean_family} is retired; reactivate it before adding levels")
    if frappe.db.exists(LEVEL, clean_code):
        raise frappe.ValidationError(f"Level {clean_code} already exists")
    siblings = frappe.db.get_all(LEVEL, filters={"family": family_doc.name},
                                 fields=["code", "sequence"])
    if any(int(row["sequence"]) == clean_sequence for row in siblings):
        raise frappe.ValidationError(
            f"Level position {clean_sequence} is already taken in {clean_family}; "
            "two levels cannot share one position")
    if clean_next:
        rules.validate_next_level(
            clean_code, clean_next,
            family_of=lambda c: _family_of(c),
            next_of=lambda c: _next_of(c))

    native = frappe.get_doc({
        "doctype": NATIVE_PROGRAM,
        "program_name": f"{family_doc.title} — {clean_title}",
        "program_abbreviation": clean_code,
    })
    native.insert(ignore_permissions=True)
    doc = frappe.get_doc({
        "doctype": LEVEL, "family": family_doc.name, "code": clean_code,
        "title": clean_title, "sequence": clean_sequence, "status": "Active",
        "native_program": native.name, "next_level": clean_next or None,
        "durations": [{
            "duration_value": clean_value, "duration_unit": duration_unit,
            "effective_from": clean_from, "reason": "Initial configuration",
            "set_by": actor, "set_on": frappe.utils.now_datetime(),
        }],
    })
    doc.insert(ignore_permissions=True)
    return _level_result(doc)


@frappe.whitelist(methods=["POST"])
def set_level_duration(request_key, level, duration_value, duration_unit,
                       effective_from, reason=""):
    """Append a new effective-dated duration version for a level.

    Older versions are closed (superseded_on), never rewritten: enrollments
    and fees created under the previous version keep their historical truth,
    and every date still resolves to exactly one governing version.
    """
    actor = _require_course_owner()
    try:
        validate_request_key(request_key)
        clean_value = rules.validate_duration_value(duration_value, duration_unit)
        clean_from = rules.parse_date(effective_from)
        clean_reason = rules.validate_reason(reason)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    doc = _level_doc(level, for_update=True)
    if doc.status != "Active":
        raise frappe.ValidationError(
            f"Level {level} is retired; reactivate it before changing its duration")
    try:
        versions = [dict(row) for row in (doc.get("durations") or [])]
        rules.check_version_appends(versions, clean_from)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    current = rules.latest_version(versions)
    doc.append("durations", {
        "duration_value": clean_value, "duration_unit": duration_unit,
        "effective_from": clean_from, "reason": clean_reason,
        "set_by": actor, "set_on": frappe.utils.now_datetime(),
    })
    if current:
        # Close the superseded version; never rewrite its meaning, only record
        # the date it stopped governing new activity.
        for row in doc.get("durations") or []:
            if (str(row.get("effective_from")) == str(current.get("effective_from"))
                    and not row.get("superseded_on")):
                row.superseded_on = clean_from
                break
    doc.save(ignore_permissions=True)
    return _level_result(doc, extra={
        "previous_version": (rules.duration_label(current) if current else ""),
        "previous_effective_from": (str(current.get("effective_from")) if current else ""),
    })


@frappe.whitelist(methods=["POST"])
def set_next_level(request_key, level, next_level):
    """Configure where students normally progress after this level."""
    _require_course_owner()
    try:
        validate_request_key(request_key)
        clean_code = rules.validate_code(level)
        clean_next = rules.validate_reason(next_level or "")
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    doc = _level_doc(clean_code, for_update=True)
    if clean_next:
        rules.validate_next_level(
            clean_code, clean_next,
            family_of=lambda c: _family_of(c),
            next_of=lambda c: _next_of(c))
        if _level_doc(clean_next).status != "Active":
            raise frappe.ValidationError(
                f"The next level {clean_next} is retired; progression must point "
                "at an active level")
    doc.next_level = clean_next or None
    doc.save(ignore_permissions=True)
    return _level_result(doc)


@frappe.whitelist(methods=["POST"])
def set_program_status(request_key, program, active):
    """Deactivate (retire) or reactivate a program family."""
    _require_course_owner()
    try:
        validate_request_key(request_key)
        clean_code = rules.validate_code(program)
        flag = _as_bool(active, "active")
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    doc = _family_doc(clean_code, for_update=True)
    if not flag:
        active_levels = frappe.db.count(
            LEVEL, {"family": doc.name, "status": "Active"})
        if active_levels:
            raise frappe.ValidationError(rules.program_has_levels_message(clean_code, active_levels))
    doc.status = "Active" if flag else "Retired"
    doc.save(ignore_permissions=True)
    return _program_result(doc)


@frappe.whitelist(methods=["POST"])
def set_level_status(request_key, level, active):
    """Deactivate (retire) or reactivate a level.

    Deactivation is refused in business language while submitted native
    enrollments still run on the level (no raw exception, no silent damage).
    """
    _require_course_owner()
    try:
        validate_request_key(request_key)
        clean_code = rules.validate_code(level)
        flag = _as_bool(active, "active")
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    doc = _level_doc(clean_code, for_update=True)
    if not flag:
        if not doc.native_program:
            raise frappe.ValidationError(rules.level_missing_native_message(clean_code))
        in_use = frappe.db.count(
            ENROLLMENT, {"program": doc.native_program, "docstatus": 1})
        if in_use:
            raise frappe.ValidationError(rules.level_in_use_message(clean_code, in_use))
    else:
        family_status = frappe.db.get_value(PROGRAM, doc.family, "status")
        if family_status != "Active":
            raise frappe.ValidationError(
                f"The program family {doc.family} is retired; reactivate it first")
    doc.status = "Active" if flag else "Retired"
    doc.save(ignore_permissions=True)
    return _level_result(doc)


def _as_bool(value, what):
    if isinstance(value, str):
        if value in ("0", "1"):
            return value == "1"
        raise ValueError(f"{what} must be 0 or 1")
    if isinstance(value, (int, bool)) and not isinstance(value, float):
        return bool(value)
    raise ValueError(f"{what} must be boolean-like")


def _family_of(code):
    return frappe.db.get_value(LEVEL, {"code": code}, "family")


def _next_of(code):
    return frappe.db.get_value(LEVEL, {"code": code}, "next_level")


def _program_result(doc, extra=None):
    result = {
        "name": doc.name, "code": doc.code, "title": doc.title,
        "status": doc.status,
    }
    if extra:
        result.update(extra)
    return result


def _level_result(doc, extra=None):
    current = rules.resolve_duration(
        [dict(row) for row in (doc.get("durations") or [])], frappe.utils.today())
    result = {
        "name": doc.name, "code": doc.code, "title": doc.title,
        "status": doc.status, "family": doc.family,
        "native_program": doc.native_program,
        "duration": rules.duration_label(current),
        "duration_effective_from": (str(current.get("effective_from")) if current else ""),
    }
    if extra:
        result.update(extra)
    return result

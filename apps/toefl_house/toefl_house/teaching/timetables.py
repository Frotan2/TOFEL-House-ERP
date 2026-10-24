"""Weekly timetable templates materialized into native Course Schedule rows.

A template is configuration, not a parallel timetable: it stores only the
weekly pattern (weekday, window, course, optional room/instructor) and the
``generate_timetable`` command turns that pattern into ordinary native
Course Schedule rows over a bounded date range. Every generated row goes
through the same server-side conflict validation as a hand-scheduled
session, and dates excluded by the academic calendar or the policy's
teaching days are skipped (reported, never silently dropped).

Templates change only through the guarded Course Owner commands below; the
controller refuses native/API/import saves. A template edit never rewrites
sessions already materialized from it.
"""
from datetime import date, timedelta
import json

import frappe

from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import (DELIVERY_MODES, digest, session_minutes,
                                session_windows_overlap, validate_delivery_mode,
                                validate_session_window)
from toefl_house.teaching.class_operations import WEEKDAYS, WEEKDAY_INDEX

TEMPLATE = "TH Timetable Template"
SLOT_TABLE = "TH Timetable Slot"
MAX_SLOTS = 40
MAX_GENERATED_SESSIONS = 400
_NAME_LIMIT = 140


def _bounded(value, what):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > _NAME_LIMIT:
        raise ValueError(f"{what} is required (at most {_NAME_LIMIT} characters)")
    return value.strip()


def _slot_payload(value):
    if isinstance(value, str):
        if len(value) > 40000:
            raise ValueError("Timetable slot batch exceeds the request limit")
        try:
            value = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Timetable slots must be a JSON list") from exc
    if not isinstance(value, list):
        raise ValueError("Timetable slots must be a list")
    if not 1 <= len(value) <= MAX_SLOTS:
        raise ValueError(f"Supply 1 to {MAX_SLOTS} timetable slots")
    return value


def validate_slots(value):
    """Validate a complete weekly slot set; return normalized, ordered rows.

    A slot names a real weekday, a bounded window and a course. Slots on the
    same weekday must not overlap (a class cannot sit in two places at once),
    and exact duplicates are refused. Nothing else is inferred: room and
    instructor stay optional template hints, validated again at generation
    time against real conflicts.
    """
    slots = []
    for raw in _slot_payload(value):
        if not isinstance(raw, dict):
            raise ValueError("Each timetable slot must be an object")
        weekday = str(raw.get("weekday") or "").strip()
        if weekday not in WEEKDAYS:
            raise ValueError("Unknown weekday " + repr(weekday) + "; use " + ", ".join(WEEKDAYS))
        start, end = validate_session_window(raw.get("from_time"), raw.get("to_time"))
        course = _bounded(raw.get("course"), "Slot course")
        room = raw.get("room") or ""
        instructor = raw.get("instructor") or ""
        slots.append({
            "weekday": weekday, "from_time": start, "to_time": end,
            "course": course,
            "room": _bounded(room, "Slot room") if room else "",
            "instructor": _bounded(instructor, "Slot instructor") if instructor else "",
        })
    slots.sort(key=lambda row: (WEEKDAY_INDEX[row["weekday"]], row["from_time"]))
    for index, slot in enumerate(slots):
        for other in slots[index + 1:]:
            if slot["weekday"] != other["weekday"]:
                continue
            if slot["from_time"] == other["from_time"] and slot["to_time"] == other["to_time"]:
                raise ValueError(
                    f"Duplicate timetable slot on {slot['weekday']} at {slot['from_time']}")
            if session_windows_overlap(slot["from_time"], slot["to_time"],
                                       other["from_time"], other["to_time"]):
                raise ValueError(
                    f"Timetable slots overlap on {slot['weekday']}: "
                    f"{slot['from_time']}-{slot['to_time']} and "
                    f"{other['from_time']}-{other['to_time']}")
    return slots


def expand_slots(slots, start_day, end_day, teaching_days, blocked=None):
    """Expand weekly slots into candidate sessions between two dates.

    ``blocked`` is the resolved calendar view from
    :func:`toefl_house.teaching.calendars.calendar_plan`. Dates whose weekday
    is not a configured teaching day or that the calendar blocks are skipped;
    the caller reports them. Expansion is deterministic: the same inputs
    always produce the same ordered candidate list, so a retried command
    cannot invent a different timetable.
    """
    first = date.fromisoformat(rules.parse_date(start_day, "Timetable start"))
    last = date.fromisoformat(rules.parse_date(end_day, "Timetable end"))
    if last < first:
        raise ValueError("Timetable end precedes its start")
    span = (last - first).days + 1
    if span > 366:
        raise ValueError("Timetable range exceeds 366 days")
    allowed_days = {WEEKDAY_INDEX[code] for code in teaching_days or ()}
    blocked = blocked or {}
    candidates = []
    day = first
    while day <= last:
        iso = day.isoformat()
        if day.weekday() in allowed_days and iso not in blocked:
            for slot in slots:
                if WEEKDAY_INDEX[slot["weekday"]] != day.weekday():
                    continue
                candidates.append({
                    "schedule_date": iso, "from_time": slot["from_time"],
                    "to_time": slot["to_time"], "course": slot["course"],
                    "room": slot["room"], "instructor": slot["instructor"],
                })
        day += timedelta(days=1)
    if len(candidates) > MAX_GENERATED_SESSIONS:
        raise ValueError(
            f"Range produces {len(candidates)} sessions; narrow it to at most "
            f"{MAX_GENERATED_SESSIONS} per command")
    return candidates


def _template_doc(code, for_update=False):
    name = frappe.db.get_value(TEMPLATE, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown timetable template: {code}")
    return frappe.get_doc(TEMPLATE, name, for_update=for_update)


def _template_result(doc, extra=None):
    slots = [row.as_dict() for row in (doc.get("slots") or [])]
    result = {
        "name": doc.name, "code": doc.code, "title": doc.title,
        "status": doc.status, "program": doc.program or "",
        "branch": doc.branch or "", "delivery_mode": doc.delivery_mode,
        "slot_count": len(slots),
        "slots": [{key: str(row.get(key) or "") for key in
                   ("weekday", "from_time", "to_time", "course", "room", "instructor")}
                  for row in slots],
    }
    if extra:
        result.update(extra)
    return result


@frappe.whitelist(methods=["POST"])
def create_timetable_template(request_key, code, title, program="", branch="",
                              delivery_mode="On-site", description=""):
    """Create one template shell; the slot set is replaced by its own command."""
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Timetable template title")
            clean_mode = validate_delivery_mode(delivery_mode)
            clean_description = rules.validate_reason(description)
            clean_program = _bounded(program, "Program") if program else ""
            clean_branch = _bounded(branch, "Branch") if branch else ""
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.exists(TEMPLATE, clean_code):
            raise frappe.ValidationError(
                f"Timetable template {clean_code} already exists")
        if clean_program and not frappe.db.exists("Program", clean_program):
            raise frappe.ValidationError("Unknown program")
        if clean_branch and not frappe.db.exists("Branch", clean_branch):
            raise frappe.ValidationError("Unknown branch")
        doc = frappe.get_doc({
            "doctype": TEMPLATE, "code": clean_code, "title": clean_title,
            "status": "Active", "program": clean_program or None,
            "branch": clean_branch or None, "delivery_mode": clean_mode,
            "description": clean_description,
        })
        doc.insert(ignore_permissions=True)
        return _template_result(doc), {
            "target": doc.name, "before_hash": "",
            "after_hash": configuration_rules.snapshot_digest([]),
        }

    payload = {"code": code, "title": title, "program": program,
               "branch": branch, "delivery_mode": delivery_mode,
               "description": description}
    return configuration_audit.execute(
        "create_timetable_template", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_timetable_slots(request_key, template, slots, reason):
    """Replace the template's whole weekly pattern, atomically and audited."""
    def work(actor):
        try:
            clean_code = rules.validate_code(template)
            clean_slots = validate_slots(slots)
            configuration_rules.validate_change_reason(reason)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _template_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                "A retired timetable template cannot change; reactivate it first")
        for slot in clean_slots:
            if not frappe.db.exists("Course", slot["course"]):
                raise frappe.ValidationError(f"Unknown course: {slot['course']}")
            if slot["room"] and not frappe.db.exists("Room", slot["room"]):
                raise frappe.ValidationError(f"Unknown room: {slot['room']}")
            if slot["instructor"] and not frappe.db.exists("Instructor", slot["instructor"]):
                raise frappe.ValidationError(f"Unknown instructor: {slot['instructor']}")
        before = configuration_audit.latest_after_hash(doc.name)
        doc.set("slots", [])
        for slot in clean_slots:
            doc.append("slots", dict(slot))
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("slots") or [])])
        return _template_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"template": template, "slots": slots, "reason": reason}
    return configuration_audit.execute(
        "set_timetable_slots", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_timetable_template_status(request_key, template, active):
    """Retire or reactivate a template (retiring stops generation from it)."""
    def work(actor):
        try:
            clean_code = rules.validate_code(template)
            flag = _as_active(active)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _template_doc(clean_code, for_update=True)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.status = "Active" if flag else "Retired"
        doc.save(ignore_permissions=True)
        after = digest(["status", doc.status,
                        configuration_rules.snapshot_digest(
                            [row.as_dict() for row in (doc.get("slots") or [])])])
        return _template_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"template": template, "active": active}
    return configuration_audit.execute(
        "set_timetable_template_status", request_key, payload, work)


def _as_active(value):
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "yes"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("false", "no"):
        return False
    raise ValueError("active must be true or false")


__all__ = ["TEMPLATE", "validate_slots", "expand_slots", "MAX_SLOTS",
           "MAX_GENERATED_SESSIONS", "create_timetable_template",
           "set_timetable_slots", "set_timetable_template_status",
           "DELIVERY_MODES", "session_minutes"]

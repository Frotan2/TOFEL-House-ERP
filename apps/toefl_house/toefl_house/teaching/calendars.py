"""Configurable academic calendars: teaching days, holidays and closures.

A calendar is an owned operational record, not a second academic master: it
never renames an Academic Year, never restates a term and never touches a
native Student Group or Course Schedule row. It answers one question for the
scheduler — "may teaching happen on this date?" — and the answer is always
the owner's configured one:

* a **Holiday** or **Closed** day blocks teaching;
* a **Working Day** reopens a date another calendar closed;
* a branch calendar overrides the global calendar for that branch on the
  same date (most specific wins, then the explicit reopening wins);
* with no calendar at all, nothing is blocked here and the teaching-day rule
  of the class-operations policy still applies.

Calendars change only through the Course Owner commands below (hash-chained
configuration audit); the controller refuses a native/API/import save. A
later calendar change never rewrites a session that was already scheduled —
history keeps the dates it was created under.
"""
from datetime import date, timedelta
import json

import frappe

from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest
from toefl_house.teaching.class_operations import WEEKDAYS, WEEKDAY_INDEX

CALENDAR = "TH Academic Calendar"
DAY_TABLE = "TH Academic Calendar Day"
DAY_KINDS = ("Holiday", "Closed", "Working Day")
BLOCKING_KINDS = ("Holiday", "Closed")
_DESCRIPTION_LIMIT = 140


def validate_day_kind(value):
    if value not in DAY_KINDS:
        raise ValueError("Calendar day kind must be Holiday, Closed or Working Day")
    return value


def parse_day(value, what="Calendar date"):
    """Strict ISO date; returns the ``YYYY-MM-DD`` string."""
    return rules.parse_date(value, what)


def weekday_code(day):
    """The ``Mon``..``Sun`` code of an ISO date string (Monday = 0)."""
    parsed = date.fromisoformat(parse_day(day))
    return WEEKDAYS[parsed.weekday()]


def weekday_matches(day, teaching_days):
    """True when a date falls on one of the configured teaching weekdays."""
    return WEEKDAY_INDEX[weekday_code(day)] in {
        WEEKDAY_INDEX[code] for code in teaching_days or ()}


def is_blocking_kind(kind):
    return kind in BLOCKING_KINDS


def resolve_day_kinds(rows, branch=""):
    """Resolve one date's effective kind from competing calendar rows.

    ``rows`` are ``{"branch": ..., "kind": ...}`` mappings for ONE date. A
    branch-specific row outranks a global row; among equally specific rows an
    explicit ``Working Day`` wins (the owner deliberately reopened the date),
    otherwise any blocking kind blocks. Returns ``""`` when nothing applies.
    """
    matching = [row for row in rows
                if not row.get("branch") or row.get("branch") == branch]
    if not matching:
        return ""
    specific = [row for row in matching if row.get("branch")]
    pool = specific or matching
    kinds = {row.get("kind") for row in pool}
    if "Working Day" in kinds:
        return "Working Day"
    if "Closed" in kinds:
        return "Closed"
    if "Holiday" in kinds:
        return "Holiday"
    return ""


def blocked_dates(plan):
    """The set of ISO dates a resolved ``{date: kind}`` plan blocks."""
    return {day for day, kind in (plan or {}).items() if is_blocking_kind(kind)}


def teaching_refusal(day, teaching_days, plan):
    """Return a refusal message when a date cannot carry teaching, else "".

    ``plan`` is the resolved ``{date: kind}`` calendar view (possibly empty).
    A missing calendar never blocks; the configured teaching days always
    apply when supplied.
    """
    kind = (plan or {}).get(day, "")
    if is_blocking_kind(kind):
        return f"{day} is a {kind} day in the academic calendar"
    if teaching_days is not None and not weekday_matches(day, teaching_days):
        return (f"{day} is a {weekday_code(day)} and the class-operations "
                "policy does not teach on that weekday")
    return ""


def normalize_days(rows):
    """Normalize a calendar's day rows into ordered, duplicate-free dicts."""
    seen = set()
    normalized = []
    for row in rows or []:
        values = row.as_dict() if hasattr(row, "as_dict") else dict(row or {})
        day = parse_day(str(values.get("date") or ""))
        kind = validate_day_kind(values.get("kind"))
        if day in seen:
            raise ValueError(f"Calendar date {day} appears twice")
        seen.add(day)
        normalized.append({"date": day, "kind": kind,
                           "description": _description(values.get("description"))})
    return sorted(normalized, key=lambda row: row["date"])


def _bounded_name(value, what):
    """An optional reference: empty means "applies to every year/branch"."""
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 140:
        raise ValueError(f"{what} must name an existing record")
    return value.strip()


def _description(value):
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or len(value.strip()) > _DESCRIPTION_LIMIT:
        raise ValueError(
            f"Calendar day description must be at most {_DESCRIPTION_LIMIT} characters")
    return value.strip()


def _rows_payload(value):
    if isinstance(value, str):
        if len(value) > 20000:
            raise ValueError("Calendar day batch exceeds the request limit")
        try:
            value = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Calendar days must be a JSON list") from exc
    if not isinstance(value, list):
        raise ValueError("Calendar days must be a list")
    return value


def _calendar_doc(code, for_update=False):
    name = frappe.db.get_value(CALENDAR, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown academic calendar: {code}")
    return frappe.get_doc(CALENDAR, name, for_update=for_update)


def _calendar_result(doc, extra=None):
    days = [row.as_dict() for row in (doc.get("days") or [])]
    result = {
        "name": doc.name, "code": doc.code, "title": doc.title,
        "status": doc.status, "academic_year": doc.academic_year or "",
        "branch": doc.branch or "", "day_count": len(days),
    }
    if extra:
        result.update(extra)
    return result


def calendar_plan(start_day, end_day, academic_year="", branch=""):
    """Resolved ``{date: kind}`` view of every Active calendar in a range.

    A calendar applies when its academic year is empty or equal to the
    class's year AND its branch is empty or equal to the class's branch.
    Reading is bounded by the caller's range (timetable generation asks for
    exactly the horizon it is about to materialize).
    """
    start = parse_day(start_day)
    end = parse_day(end_day)
    if end < start:
        raise ValueError("Calendar range end precedes its start")
    calendars = frappe.get_all(
        CALENDAR, filters={"status": "Active"},
        fields=["name", "branch", "academic_year"], limit_page_length=100)
    rows_by_date = {}
    for row in calendars:
        if row.get("academic_year") and row.get("academic_year") != (academic_year or ""):
            continue
        if row.get("branch") and row.get("branch") != (branch or ""):
            continue
        doc = frappe.get_doc(CALENDAR, row["name"])
        for day_row in doc.get("days") or []:
            day = str(day_row.get("date") or "")
            if not day or day < start or day > end:
                continue
            rows_by_date.setdefault(day, []).append({
                "branch": doc.branch or "", "kind": day_row.get("kind")})
    return {day: resolve_day_kinds(rows, branch)
            for day, rows in rows_by_date.items()}


def assert_teaching_allowed(day, teaching_days, academic_year="", branch=""):
    """Refuse a date the calendar or the configured teaching days exclude."""
    clean = parse_day(day)
    plan = calendar_plan(clean, clean, academic_year, branch)
    refusal = teaching_refusal(clean, teaching_days, plan)
    if refusal:
        raise frappe.ValidationError(refusal)
    return clean


@frappe.whitelist(methods=["POST"])
def create_academic_calendar(request_key, code, title, academic_year="",
                             branch="", description=""):
    """Create one calendar shell; days are added by the day commands."""
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Calendar title")
            clean_description = rules.validate_reason(description)
            clean_year = _bounded_name(academic_year, "Academic year")
            clean_branch = _bounded_name(branch, "Branch")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.exists(CALENDAR, clean_code):
            raise frappe.ValidationError(
                f"Academic calendar {clean_code} already exists")
        if clean_year and not frappe.db.exists("Academic Year", clean_year):
            raise frappe.ValidationError("Unknown academic year")
        if clean_branch and not frappe.db.exists("Branch", clean_branch):
            raise frappe.ValidationError("Unknown branch")
        doc = frappe.get_doc({
            "doctype": CALENDAR, "code": clean_code, "title": clean_title,
            "status": "Active", "academic_year": clean_year or None,
            "branch": clean_branch or None, "description": clean_description,
        })
        doc.insert(ignore_permissions=True)
        return _calendar_result(doc), {
            "target": doc.name, "before_hash": "",
            "after_hash": configuration_rules.snapshot_digest([]),
        }

    payload = {"code": code, "title": title, "academic_year": academic_year,
               "branch": branch, "description": description}
    return configuration_audit.execute(
        "create_academic_calendar", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def add_academic_calendar_day(request_key, calendar, day, kind, description=""):
    """Append one Holiday, Closed or Working Day to an Active calendar."""
    def work(actor):
        try:
            clean_code = rules.validate_code(calendar)
            clean_day = parse_day(day)
            clean_kind = validate_day_kind(kind)
            clean_description = _description(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _calendar_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                "A retired calendar cannot take new days; reactivate it first")
        before = configuration_audit.latest_after_hash(doc.name)
        if any(str(row.get("date")) == clean_day for row in doc.get("days") or []):
            raise frappe.ValidationError(
                f"Calendar date {clean_day} is already recorded")
        doc.append("days", {"date": clean_day, "kind": clean_kind,
                            "description": clean_description})
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("days") or [])])
        return _calendar_result(doc, {"day": clean_day, "kind": clean_kind}), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"calendar": calendar, "day": day, "kind": kind,
               "description": description}
    return configuration_audit.execute(
        "add_academic_calendar_day", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def remove_academic_calendar_day(request_key, calendar, day, reason):
    """Remove one day row, with a mandatory reason (the audit keeps it)."""
    def work(actor):
        try:
            clean_code = rules.validate_code(calendar)
            clean_day = parse_day(day)
            configuration_rules.validate_change_reason(reason)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _calendar_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                "A retired calendar cannot change; reactivate it first")
        before = configuration_audit.latest_after_hash(doc.name)
        remaining = [row for row in (doc.get("days") or [])
                     if str(row.get("date")) != clean_day]
        if len(remaining) == len(doc.get("days") or []):
            raise frappe.ValidationError(
                f"Calendar date {clean_day} is not recorded")
        doc.set("days", [])
        for row in remaining:
            doc.append("days", row.as_dict() if hasattr(row, "as_dict") else dict(row))
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("days") or [])])
        return _calendar_result(doc, {"removed": clean_day}), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"calendar": calendar, "day": day, "reason": reason}
    return configuration_audit.execute(
        "remove_academic_calendar_day", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_academic_calendar_status(request_key, calendar, active):
    """Retire or reactivate a calendar (retiring stops its holidays applying)."""
    def work(actor):
        try:
            clean_code = rules.validate_code(calendar)
            flag = _as_active(active)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _calendar_doc(clean_code, for_update=True)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.status = "Active" if flag else "Retired"
        doc.save(ignore_permissions=True)
        after = digest(["status", doc.status,
                        configuration_rules.snapshot_digest(
                            [row.as_dict() for row in (doc.get("days") or [])])])
        return _calendar_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"calendar": calendar, "active": active}
    return configuration_audit.execute(
        "set_academic_calendar_status", request_key, payload, work)


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


def next_teaching_days(start_day, count, teaching_days, academic_year="",
                       branch=""):
    """The next ``count`` teachable dates from ``start_day`` (read-only aid).

    Used by availability projections to answer "when can this intake start?"
    without inventing a date: holidays and non-teaching weekdays are skipped,
    and the horizon is bounded by the caller.
    """
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 60:
        raise ValueError("count must be between 1 and 60")
    day = date.fromisoformat(parse_day(start_day))
    horizon = day + timedelta(days=400)
    plan = calendar_plan(day.isoformat(), horizon.isoformat(),
                         academic_year, branch)
    found = []
    while day <= horizon and len(found) < count:
        iso = day.isoformat()
        if not teaching_refusal(iso, teaching_days, plan):
            found.append(iso)
        day += timedelta(days=1)
    return found

"""Pure content validation, not scoring or academic placement policy."""
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import re

SKILLS = ("Vocabulary", "Grammar", "Reading", "Listening", "Speaking", "Writing")
KINDS = ("Single Choice", "True False")
FIELDS = {"skill", "difficulty", "question_type", "prompt", "options", "answer"}
MODES = ("Digital", "Physical", "Hybrid")
DIFFICULTIES = ("Entry", "Core", "Stretch")
SYNTHETIC_CODE = re.compile(r"SYN-[A-Z0-9_-]{1,48}")
SECTION_ID = re.compile(r"[a-z][a-z0-9_]{0,15}")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def request_digest(value, secret):
    if not isinstance(secret, str) or not secret:
        raise ValueError("Native site encryption key must be configured")
    return hmac.new(secret.encode(), canonical(value).encode(), hashlib.sha256).hexdigest()


def validate_content(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("Content must contain exactly the supported fields")
    if value["skill"] not in SKILLS or value["difficulty"] not in DIFFICULTIES:
        raise ValueError("Unknown editorial category")
    if value["question_type"] not in KINDS:
        raise ValueError("Format not implemented in this increment")
    if value["skill"] in ("Speaking", "Writing"):
        raise ValueError("Productive-skill rubric tasks are not implemented in this increment")
    # Test-content marker is an explicit guardrail, not a PII detection claim.
    if not isinstance(value["prompt"], str) or not value["prompt"].startswith("SYNTHETIC: ") or not 12 <= len(value["prompt"]) <= 4000:
        raise ValueError("Only bounded, explicitly synthetic plain-text prompts are accepted")
    options = value["options"]
    if not isinstance(options, list) or not 2 <= len(options) <= 6:
        raise ValueError("Supply two to six options")
    ids = []
    for option in options:
        if not isinstance(option, dict) or set(option) != {"id", "text"}:
            raise ValueError("Each option needs only a stable id and text")
        if not isinstance(option["id"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,15}", option["id"]):
            raise ValueError("Invalid option id")
        if not isinstance(option["text"], str) or not 1 <= len(option["text"].strip()) <= 1000:
            raise ValueError("Invalid option text")
        ids.append(option["id"])
    if len(set(ids)) != len(ids) or value["answer"] not in ids:
        raise ValueError("Duplicate option id or missing key")
    if value["question_type"] == "True False" and options != [{"id": "true", "text": "True"}, {"id": "false", "text": "False"}]:
        raise ValueError("True/False requires canonical stable options")
    return value


def validate_family(family, revision):
    if not isinstance(family, str) or not re.fullmatch(r"SYN-[A-Z0-9_-]{1,48}", family):
        raise ValueError("Synthetic family id required")
    if type(revision) is not int or not 1 <= revision <= 100000:
        raise ValueError("Revision must be a positive integer")


def validate_config_code(code, revision):
    if not isinstance(code, str) or not SYNTHETIC_CODE.fullmatch(code):
        raise ValueError("Synthetic config code required")
    if type(revision) is not int or not 1 <= revision <= 100000:
        raise ValueError("Revision must be a positive integer")


def _bounded_int(value, field, lo, hi):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"{field} must be an integer between {lo} and {hi}")
    return value


def _unique_strs(values, field, lo, hi, pattern=None):
    if not isinstance(values, list) or not lo <= len(values) <= hi:
        raise ValueError(f"{field} must contain {lo} to {hi} entries")
    seen = set()
    for entry in values:
        if not isinstance(entry, str) or not entry or len(entry) > 64:
            raise ValueError(f"Invalid {field} entry")
        if pattern is not None and not pattern.fullmatch(entry):
            raise ValueError(f"Invalid {field} entry")
        if entry in seen:
            raise ValueError(f"Duplicate {field} entry")
        seen.add(entry)
    return list(values)


def validate_blueprint(value):
    """Bounded structural validation of a synthetic blueprint definition.

    Engineering bounds and internal consistency only. Section quotas, minutes
    and modes are fixture values, not approved operational policy (P2).
    """
    if not isinstance(value, dict) or set(value) != {"mode", "sections", "total_minutes"}:
        raise ValueError("Blueprint must contain exactly mode, sections, total_minutes")
    if value["mode"] not in MODES:
        raise ValueError("Unknown delivery mode")
    sections = value["sections"]
    if not isinstance(sections, list) or not 1 <= len(sections) <= 12:
        raise ValueError("Supply one to twelve sections")
    ids = []
    minutes_total = 0
    for section in sections:
        if not isinstance(section, dict) or set(section) != {"id", "skill", "minutes", "item_count"}:
            raise ValueError("Section must contain exactly id, skill, minutes, item_count")
        _unique_strs([section["id"]], "section id", 1, 1, SECTION_ID)
        ids.append(section["id"])
        if section["skill"] not in SKILLS:
            raise ValueError("Unknown section skill")
        minutes_total += _bounded_int(section["minutes"], "section minutes", 1, 240)
        _bounded_int(section["item_count"], "section item_count", 1, 100)
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate section id")
    total = _bounded_int(value["total_minutes"], "total_minutes", 1, 240)
    if total != minutes_total:
        raise ValueError("total_minutes must equal the sum of section minutes")
    return value


def validate_policy(value):
    """Bounded structural validation of a synthetic operational policy profile.

    Values are parameterized ranges with fixture inputs, not institutional
    F03/F04/F05 values; actual owner configuration remains a later activation
    prerequisite (P1-P5).
    """
    if not isinstance(value, dict) or set(value) != {
            "result_validity_days", "retest_wait_days",
            "release_working_days", "appeal_working_days", "retention_years"}:
        raise ValueError("Policy must contain exactly the supported parameter fields")
    _bounded_int(value["result_validity_days"], "result_validity_days", 1, 730)
    _bounded_int(value["retest_wait_days"], "retest_wait_days", 0, 90)
    _bounded_int(value["release_working_days"], "release_working_days", 1, 30)
    _bounded_int(value["appeal_working_days"], "appeal_working_days", 1, 30)
    _bounded_int(value["retention_years"], "retention_years", 1, 10)
    return value


COURSE_MAP_MATCHES = ("any_correct",)


def validate_course_map(value):
    """Bounded structural validation of a synthetic course/level map.

    Fixture entries are not approved Academic Owner operational policy
    (P1/P4 remain owner deliverables). No percent, cutoff, CEFR or
    official TOEFL fields are accepted.
    """
    if not isinstance(value, dict) or set(value) != {"algorithm", "entries"}:
        raise ValueError("Course map must contain exactly algorithm, entries")
    if value["algorithm"] != "course-map-v1":
        raise ValueError("Unsupported course map algorithm")
    entries = value["entries"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= 32:
        raise ValueError("Supply one to thirty-two course map entries")
    seen = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"internal_level", "course_code", "match"}:
            raise ValueError("Entry must contain exactly internal_level, course_code, match")
        if not isinstance(entry["internal_level"], str) or not SYNTHETIC_CODE.fullmatch(entry["internal_level"]):
            raise ValueError("Synthetic internal_level required")
        if not isinstance(entry["course_code"], str) or not SYNTHETIC_CODE.fullmatch(entry["course_code"]):
            raise ValueError("Synthetic course_code required")
        if entry["match"] not in COURSE_MAP_MATCHES:
            raise ValueError("Unsupported course map match")
        key = (entry["internal_level"], entry["course_code"], entry["match"])
        if key in seen:
            raise ValueError("Duplicate course map entry")
        seen.append(key)
    return value


def recommend_course(score, course_map):
    """Map sealed objective evidence to a synthetic internal course.

    Missing evidence is never treated as zero. No composite, percent,
    cutoff, CEFR or official TOEFL output. Unmatched evidence fails closed.
    """
    if not isinstance(score, dict):
        raise ValueError("Score projection required")
    for forbidden in ("percent", "cutoff", "cefr", "toefl", "composite"):
        if forbidden in score:
            raise ValueError("Score must not carry a composite or external claim")
    presented, correct, incorrect, missing = (score.get("presented"), score.get("correct"),
                                              score.get("incorrect"), score.get("missing"))
    if not all(type(value) is int for value in (presented, correct, incorrect, missing)):
        raise ValueError("Score completeness required")
    if presented < 1 or presented != correct + incorrect + missing:
        raise ValueError("Score completeness mismatch")
    course_map = validate_course_map(course_map)
    for entry in course_map["entries"]:
        if entry["match"] == "any_correct" and correct >= 1:
            return {
                "algorithm": "course-map-v1",
                "internal_level": entry["internal_level"],
                "course_code": entry["course_code"],
                "rationale": ("Synthetic non-operational fixture mapping from observed "
                              "correct evidence; not an approved academic policy."),
            }
    raise ValueError("No eligible course mapping for this evidence")


def attempt_deadline(started_at, total_minutes):
    """Overall candidate-work deadline from the pinned blueprint budget.

    Fixture minutes are engineering bounds, not approved institutional timing.
    """
    if not isinstance(started_at, datetime):
        raise ValueError("started_at must be a datetime")
    return started_at + timedelta(minutes=_bounded_int(total_minutes, "total_minutes", 1, 240))


def deadline_reached(now, deadline):
    if not isinstance(now, datetime) or not isinstance(deadline, datetime):
        raise ValueError("now and deadline must be datetimes")
    return now >= deadline


def project_form(form, catalog):
    """Staff-supervised delivery projection: prompts and display options only.

    The catalog is keyed by item name and must not include answers. Seed,
    algorithm, pool digest, family and item identity never appear in the
    projection (those stay on the staff-restricted manifest).
    """
    if not isinstance(form, dict) or not isinstance(catalog, dict):
        raise ValueError("Form and catalog required")
    items = form.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Form items required")
    projected = []
    for entry in items:
        if not isinstance(entry, dict):
            raise ValueError("Invalid form item")
        src = catalog.get(entry.get("item"))
        if not isinstance(src, dict):
            raise ValueError("Catalog missing allocated item")
        if "answer" in src:
            raise ValueError("Catalog must not include answers")
        options = src.get("options")
        if not isinstance(options, list):
            raise ValueError("Catalog options required")
        by_id = {}
        for option in options:
            if not isinstance(option, dict) or "id" not in option or "text" not in option:
                raise ValueError("Invalid catalog option")
            by_id[option["id"]] = option["text"]
        if entry.get("question_type") == "True False":
            displayed = [{"id": option["id"], "text": option["text"]} for option in options]
        else:
            order = entry.get("option_order")
            if not isinstance(order, list):
                raise ValueError("Single-choice option_order required")
            displayed = [{"id": option_id, "text": by_id[option_id]} for option_id in order]
        projected.append({
            "order": entry["order"],
            "occurrence_id": entry["occurrence_id"],
            "section": entry["section"],
            "skill": entry["skill"],
            "difficulty": entry["difficulty"],
            "question_type": entry["question_type"],
            "prompt": src["prompt"],
            "options": displayed,
        })
    sections = [{"id": section["id"], "skill": section["skill"],
                 "minutes": section["minutes"], "item_count": section["item_count"]}
                for section in form["sections"]]
    return {
        "attempt": form["attempt"],
        "case": form["case"],
        "subject": form["subject"],
        "sections": sections,
        "items": projected,
    }


ATTEMPT_STATUSES = ("Allocated", "Verified", "In Progress", "Sealed", "Marking", "Review", "Finalized")
ATTEMPT_TRANSITIONS = {
    ("Allocated", "Verified"),
    ("Verified", "In Progress"),
    ("In Progress", "Sealed"),
    ("Sealed", "Marking"),
    ("Marking", "Review"),
    ("Review", "Finalized"),
}

ADMISSION_STATUSES = (
    "Draft", "Review", "Approved", "Conditional", "Deferred", "Rejected",
    "Withdrawn", "Revoked", "Expired",
)
ADMISSION_ACTIVE = ("Draft", "Review", "Approved", "Conditional")
ADMISSION_TERMINAL = ("Deferred", "Rejected", "Withdrawn", "Revoked", "Expired")
ADMISSION_TRANSITIONS = {
    ("Draft", "Review"),
    ("Draft", "Withdrawn"),
    ("Review", "Approved"),
    ("Review", "Conditional"),
    ("Review", "Deferred"),
    ("Review", "Rejected"),
    ("Review", "Withdrawn"),
    ("Approved", "Revoked"),
    ("Approved", "Expired"),
    ("Conditional", "Revoked"),
    ("Conditional", "Expired"),
}
ADMISSION_OUTCOMES = ("Approved", "Conditional", "Deferred", "Rejected")
REASON_LIMIT = (8, 500)


def is_admission_transition(before, after):
    return (before, after) in ADMISSION_TRANSITIONS


def validate_admission_text(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    text = value.strip()
    lo, hi = REASON_LIMIT
    if not lo <= len(text) <= hi:
        raise ValueError(f"{field} must be {lo} to {hi} characters")
    return text


ATTENDANCE_STATUSES = ("Present", "Absent", "Leave")
TIME_PATTERN = re.compile(r"([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?")


def validate_group_name(value):
    """Class roster names are explicit synthetic fixtures, not real classes."""
    if not isinstance(value, str) or not SYNTHETIC_CODE.fullmatch(value):
        raise ValueError("Synthetic student group name required")
    return value


def validate_capacity(value):
    """Explicit declared class capacity; native max_strength stays the authority.

    The 1..500 range is an engineering bound for the synthetic slice, not an
    approved institutional class-size policy.
    """
    if type(value) is not int or not 1 <= value <= 500:
        raise ValueError("max_strength must be an integer between 1 and 500")
    return value


def validate_schedule_date(value):
    if not isinstance(value, str):
        raise ValueError("schedule_date must be an ISO date string")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("schedule_date must be YYYY-MM-DD") from exc
    return parsed.isoformat()


def _normalize_time(value, field):
    if not isinstance(value, str) or not TIME_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be HH:MM or HH:MM:SS")
    return value if len(value) == 8 else value + ":00"


def validate_session_window(from_time, to_time):
    """Bounded session window; zero-length or inverted windows fail closed.

    The native Course Schedule controller remains the authority for the
    academic-calendar window and instructor/room/group overlap.
    """
    start = _normalize_time(from_time, "from_time")
    end = _normalize_time(to_time, "to_time")
    if start >= end:
        raise ValueError("from_time must be strictly before to_time")
    return start, end


def validate_attendance_statuses(value):
    """Bounded attendance batch using only native Student Attendance statuses.

    Present/Absent/Leave are the pinned native Select options; no status is
    invented and missing evidence is never defaulted.
    """
    if isinstance(value, str):
        if len(value) > 20000:
            raise ValueError("Attendance batch exceeds request limit")
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("Attendance batch must be a JSON object") from exc
    if not isinstance(value, dict) or not 1 <= len(value) <= 100:
        raise ValueError("Attendance batch must contain 1 to 100 entries")
    marks = {}
    for student, status in value.items():
        if not isinstance(student, str) or not student or len(student) > 140:
            raise ValueError("Invalid student reference")
        if status not in ATTENDANCE_STATUSES:
            raise ValueError("Unsupported attendance status")
        marks[student] = status
    return marks


def enrollment_is_eligible(status, accepted, native_student, existing_student="", conditions=""):
    """Pure predicate: native Program Enrollment is allowed only after convert.

    Returning-student and Conditional paths remain denied in this slice.
    """
    if status != "Approved":
        raise ValueError("Only an Approved admission can enroll")
    if not int(accepted or 0):
        raise ValueError("Offer acceptance is required before enrollment")
    if not native_student:
        raise ValueError("Native Student conversion is required before enrollment")
    if existing_student:
        raise ValueError("Returning-student enrollment is not part of this slice")
    if conditions:
        raise ValueError("Conditional admission is not permission to enroll")
    return True

CONFIG_VALIDATORS = {"blueprint": validate_blueprint, "policy": validate_policy,
                     "course_map": validate_course_map}

# Draft -> Reviewed -> Published -> Retired. Retired is terminal.
CONFIG_STATUSES = ("Draft", "Reviewed", "Published", "Retired")
CONFIG_TRANSITIONS = {
    ("Draft", "Reviewed"),
    ("Reviewed", "Published"),
    ("Published", "Retired"),
}
FROZEN_STATUSES = ("Published", "Retired")


def is_config_transition(before, after):
    return before == after or (before, after) in CONFIG_TRANSITIONS


def validate_request_key(key):
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,96}", key):
        raise ValueError("Idempotency key must contain 16–96 safe characters")


def can_read(kind, roles, actor, owner, status=None):
    roles = set(roles)
    # The allocation guard is an internal lock row: no business role reads it.
    if kind == "guard":
        return False
    if kind == "admission_decision":
        return bool(roles & {"Admission Officer", "Admission Reviewer",
                             "Admission Approver", "Admission Auditor"})
    if kind in ("audit", "operation"):
        return bool(roles & {"Placement Auditor", "Admission Auditor", "Enrollment Auditor",
                             "Teaching Auditor"})
    if "Placement Publisher" in roles:
        return True
    # Invigilator may operate the Digital session and read the operational
    # rows it needs; the manifest (seed / full form) stays Publisher/Auditor.
    if kind in ("case", "attempt", "exposure", "response") and "Placement Invigilator" in roles:
        return True
    # Assessor marks sealed Digital attempts; keys and the seed-bearing
    # manifest stay off this role (loaded only inside the scoring command).
    if kind in ("case", "attempt", "response", "score") and "Placement Assessor" in roles:
        return True
    # Reviewer independently accepts a marked Digital score; keys and the
    # seed-bearing manifest stay off this role.
    if kind in ("case", "attempt", "response", "score") and "Placement Reviewer" in roles:
        return True
    # Releaser publishes the internal decision; keys and the seed-bearing
    # manifest stay off this role.
    if kind in ("case", "attempt", "response", "score", "decision") and "Placement Releaser" in roles:
        return True
    # Case/attempt/manifest/exposure/response/score/decision are staff-only
    # operational records (the manifest carries the seed and the full form,
    # never candidate feedback).
    if kind in ("case", "attempt", "manifest", "exposure", "response", "score", "decision"):
        return "Placement Auditor" in roles
    if kind in ("item", "blueprint", "policy", "course_map") and "Placement Auditor" in roles:
        return status == "Published"
    if kind in ("item", "blueprint", "policy", "course_map"):
        return "Placement Author" in roles and (owner == actor or status == "Published")
    if kind == "key":
        return "Placement Author" in roles and owner == actor
    return False

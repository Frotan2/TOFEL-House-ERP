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

# D16 fixture-separation mirror: on the production site, test markers are
# forbidden everywhere they are required on synthetic sites. Bounds are kept;
# no production code format is invented — real values are owner configuration.
PRODUCTION_CODE_LIMIT = 64


def _production_code(value, label):
    if not isinstance(value, str) or not 1 <= len(value) <= PRODUCTION_CODE_LIMIT:
        raise ValueError(f"{label} must be 1 to 64 characters")
    if value.startswith("SYN-") or value.startswith("SYNTHETIC"):
        raise ValueError(f"{label} must not carry the synthetic test marker on the production site")
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def request_digest(value, secret):
    if not isinstance(secret, str) or not secret:
        raise ValueError("Native site encryption key must be configured")
    return hmac.new(secret.encode(), canonical(value).encode(), hashlib.sha256).hexdigest()


def validate_content(value, *, production=False):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("Content must contain exactly the supported fields")
    if value["skill"] not in SKILLS or value["difficulty"] not in DIFFICULTIES:
        raise ValueError("Unknown editorial category")
    if value["question_type"] not in KINDS:
        raise ValueError("Format not implemented in this increment")
    if value["skill"] in ("Speaking", "Writing"):
        raise ValueError("Productive-skill rubric tasks are not implemented in this increment")
    # Test-content marker is an explicit guardrail, not a PII detection claim.
    # D16 mirror: required on synthetic sites, forbidden on the production site.
    prompt = value["prompt"]
    if production:
        if not isinstance(prompt, str) or not 12 <= len(prompt) <= 4000:
            raise ValueError("Only bounded plain-text prompts are accepted")
        if prompt.startswith("SYNTHETIC: "):
            raise ValueError("Test-fixture prompts are not accepted on the production site")
    elif not isinstance(prompt, str) or not prompt.startswith("SYNTHETIC: ") or not 12 <= len(prompt) <= 4000:
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


def validate_family(family, revision, *, production=False):
    if production:
        _production_code(family, "Family id")
    elif not isinstance(family, str) or not re.fullmatch(r"SYN-[A-Z0-9_-]{1,48}", family):
        raise ValueError("Synthetic family id required")
    if type(revision) is not int or not 1 <= revision <= 100000:
        raise ValueError("Revision must be a positive integer")


def validate_config_code(code, revision, *, production=False):
    if production:
        _production_code(code, "Config code")
    elif not isinstance(code, str) or not SYNTHETIC_CODE.fullmatch(code):
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


def validate_course_map(value, *, production=False):
    """Bounded structural validation of a synthetic course/level map.

    Fixture entries are not approved Academic Owner operational policy
    (P1/P4 remain owner deliverables). No percent, cutoff, CEFR or
    official TOEFL fields are accepted. D16 mirror: on the production site
    the same structure holds with real owner-configured codes and test
    markers forbidden.
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
        if production:
            _production_code(entry["internal_level"], "internal_level")
            _production_code(entry["course_code"], "course_code")
        else:
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


def recommend_course(score, course_map, *, production=False):
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
    course_map = validate_course_map(course_map, production=production)
    for entry in course_map["entries"]:
        if entry["match"] == "any_correct" and correct >= 1:
            rationale = ("Configured course mapping from observed correct evidence; "
                         "not an approved academic grading policy.") if production else (
                         "Synthetic non-operational fixture mapping from observed "
                         "correct evidence; not an approved academic policy.")
            return {
                "algorithm": "course-map-v1",
                "internal_level": entry["internal_level"],
                "course_code": entry["course_code"],
                "rationale": rationale,
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
    ("Conditional", "Approved"),
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


def validate_group_name(value, *, production=False):
    """Class roster names are explicit synthetic fixtures, not real classes."""
    if production:
        return _production_code(value, "Student group name")
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


def validate_finance_dates(posting_date, due_date):
    """Billing dates are ISO calendar dates; the due date cannot precede posting.

    No fiscal-calendar or payment-term policy is invented here: tax rules and
    terms stay native configuration supplied by the owner (R05 record).
    """
    out = []
    for field, value in (("posting_date", posting_date), ("due_date", due_date)):
        if not isinstance(value, str):
            raise ValueError(f"{field} must be an ISO date string")
        try:
            out.append(datetime.strptime(value, "%Y-%m-%d").date())
        except ValueError as exc:
            raise ValueError(f"{field} must be YYYY-MM-DD") from exc
    if out[1] < out[0]:
        raise ValueError("due_date cannot precede posting_date")
    return out[0].isoformat(), out[1].isoformat()


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

    Conditional paths remain denied. Returning students enroll through
    the same predicate: convert links ``native_student`` to the
    officer-declared ``existing_student``, and any divergence between
    the two is a linkage break, never a silent substitution.
    """
    if status != "Approved":
        raise ValueError("Only an Approved admission can enroll")
    if not int(accepted or 0):
        raise ValueError("Offer acceptance is required before enrollment")
    if not native_student:
        raise ValueError("Native Student conversion is required before enrollment")
    if existing_student and native_student != existing_student:
        raise ValueError("Returning-student linkage is broken")
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
                             "Teaching Auditor", "Finance Auditor"})
    # D2 compensation records are finance-sensitive: evaluated before the
    # Placement Publisher fall-through so placement breadth never reaches them.
    if kind == "contract":
        return bool(roles & {"Finance Officer", "Finance Auditor"})
    if kind == "assignment":
        return bool(roles & {"Teaching Scheduler", "Teaching Auditor",
                             "Finance Officer", "Finance Auditor"})
    if kind in ("correction_policy", "correction_request"):
        return bool(roles & {"Finance Officer", "Finance Auditor"})
    if kind == "attendance_correction":
        return bool(roles & {"Attendance Recorder", "Teaching Auditor"})
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


# --- D2 teaching compensation (owner requirement 2026-09-16) -------------
# Skill is a configurable TH Skill master (Course Owner configuration);
# compensation models, adjustment types and contract statuses are the
# enumerated vocabulary the owner selected. Rates, quantities, limits and
# terms are always owner-entered contract data; nothing here supplies a
# default value.
COMPENSATION_MODELS = ("Fixed Salary", "Skill-Based", "Hybrid")
ADJUSTMENT_TYPES = ("Bonus", "Deduction")
CONTRACT_STATUSES = ("Active", "Superseded")
DELIVERY_MODES = ("On-site", "Online", "Hybrid")
CLASS_STATUSES = ("Planned", "Active", "Completed", "Cancelled")
CLASS_TRANSITIONS = {
    ("Planned", "Active"),
    ("Planned", "Cancelled"),
    ("Active", "Completed"),
    ("Active", "Cancelled"),
}
OPEN_END = "9999-12-31"
MAX_AMOUNT = 10 ** 9
MAX_QUANTITY = 10 ** 6


def validate_skill(value):
    """Validate a skill reference as a bounded name.

    Existence against the TH Skill master and the Active/Retired lifecycle
    are enforced at the command layer (where frappe.db is available); this
    pure function only rejects empty / implausible values so offline tests
    do not need a database.
    """
    if not isinstance(value, str) or not value or len(value) > 140:
        raise ValueError("A skill reference is required")
    return value


def validate_delivery_mode(value):
    if value not in DELIVERY_MODES:
        raise ValueError("Delivery mode must be one of: " + ", ".join(DELIVERY_MODES))
    return value


def validate_class_status(value):
    if value not in CLASS_STATUSES:
        raise ValueError("Class status must be one of: " + ", ".join(CLASS_STATUSES))
    return value


def is_valid_class_transition(before, after):
    """Guarded class lifecycle transitions. Terminal states (Completed, Cancelled)
    do not regress.
    """
    return before == after or (before, after) in CLASS_TRANSITIONS


def validate_compensation_model(value):
    if value not in COMPENSATION_MODELS:
        raise ValueError("Compensation model must be explicitly one of: " + ", ".join(COMPENSATION_MODELS))
    return value


def validate_positive_amount(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    value = float(value)
    if not (0 < value <= MAX_AMOUNT):
        raise ValueError(f"{label} must be a positive bounded amount")
    return value


def validate_optional_amount(value, label):
    if value in (None, "", 0):
        return None
    return validate_positive_amount(value, label)


def validate_payable_quantity(value):
    if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= MAX_QUANTITY):
        raise ValueError("Payable quantity must be a positive bounded integer")
    return value


def validate_effective_window(start, end):
    start = validate_schedule_date(start)
    if end in (None, ""):
        return start, None
    end = validate_schedule_date(end)
    if end < start:
        raise ValueError("Effective end precedes effective start")
    return start, end


def windows_overlap(a_start, a_end, b_start, b_end):
    """Inclusive overlap for effective windows; None end means open-ended."""
    return a_start <= (b_end or OPEN_END) and b_start <= (a_end or OPEN_END)


def compute_skill_payable(quantity, rate, minimum=None, maximum=None):
    """Apply declared contract terms to a payable quantity.

    This is contract-term application, not a payroll engine: no statutory,
    tax or deduction logic lives here (that remains in the native HRMS
    Salary Slip), and no rounding policy beyond two-decimal currency.
    """
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("Contract minimum exceeds contract maximum")
    amount = round(validate_payable_quantity(quantity) * validate_positive_amount(rate, "Rate"), 2)
    if minimum is not None and amount < minimum:
        amount = round(float(minimum), 2)
    if maximum is not None and amount > maximum:
        amount = round(float(maximum), 2)
    return amount


# --- D3 correction framework (owner: "framework approved; exact terms
# later", 2026-09-16). The policy doctype carries owner-entered approval
# terms; with no Active policy every correction command fails closed.
# No window, approver or partial-refund rule is invented here.
CORRECTION_POLICY_STATUSES = ("Active", "Retired")
CORRECTION_REQUEST_STATUSES = ("Requested", "Posted", "Denied")
# Typo-guard ceiling for the owner-entered correction window, in the
# DURATION_MAX tradition: a data-entry plausibility bound, not a policy
# cap. A window beyond ~10 years is a mistyped value, not a term; the
# owner chooses any value at or below it. The lower bound 0 is the
# mathematical minimum (a same-posting-date-only window); negative
# durations are meaningless. Integer-only is day granularity.
CORRECTION_WINDOW_MAX_DAYS = 3650


def validate_correction_window_days(value):
    if isinstance(value, bool) or not isinstance(value, int) or not (
            0 <= value <= CORRECTION_WINDOW_MAX_DAYS):
        raise ValueError(
            "Correction window must be an integer number of days "
            f"(0-{CORRECTION_WINDOW_MAX_DAYS})")
    return value

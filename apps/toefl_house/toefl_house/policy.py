"""Pure content validation, not scoring or academic placement policy."""
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


CONFIG_VALIDATORS = {"blueprint": validate_blueprint, "policy": validate_policy}

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
    if kind in ("audit", "operation"):
        return "Placement Auditor" in roles
    if "Placement Publisher" in roles:
        return True
    # Case/attempt/manifest/exposure are staff-only operational records (the
    # manifest carries the seed and the full form, never candidate feedback).
    if kind in ("case", "attempt", "manifest", "exposure"):
        return "Placement Auditor" in roles
    if kind in ("item", "blueprint", "policy") and "Placement Auditor" in roles:
        return status == "Published"
    if kind in ("item", "blueprint", "policy"):
        return "Placement Author" in roles and (owner == actor or status == "Published")
    if kind == "key":
        return "Placement Author" in roles and owner == actor
    return False

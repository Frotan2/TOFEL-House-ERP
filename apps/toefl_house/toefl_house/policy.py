"""Pure content validation, not scoring or academic placement policy."""
import hashlib
import hmac
import json
import re

SKILLS = ("Vocabulary", "Grammar", "Reading", "Listening", "Speaking", "Writing")
KINDS = ("Single Choice", "True False")
FIELDS = {"skill", "difficulty", "question_type", "prompt", "options", "answer"}


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
    if value["skill"] not in SKILLS or value["difficulty"] not in ("Entry", "Core", "Stretch"):
        raise ValueError("Unknown editorial category")
    if value["question_type"] not in KINDS:
        raise ValueError("Format not implemented in this increment")
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


def validate_request_key(key):
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,96}", key):
        raise ValueError("Idempotency key must contain 16–96 safe characters")


def can_read(kind, roles, actor, owner, status=None):
    roles = set(roles)
    if kind in ("audit", "operation"):
        return "Placement Auditor" in roles
    if "Placement Publisher" in roles:
        return True
    if kind == "item" and "Placement Auditor" in roles:
        return status == "Published"
    return "Placement Author" in roles and (owner == actor or (kind == "item" and status == "Published"))

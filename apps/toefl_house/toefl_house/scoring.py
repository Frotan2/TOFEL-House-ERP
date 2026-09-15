"""Closed-registry objective scoring for sealed synthetic responses.

Pure standard-library module; no Frappe import. This is the Mark command
family of spec section 4 / section 6 for the formats this increment
implements: Single Choice and True False exact match. It is NOT a
composite, cutoff, course recommendation, CEFR map or human rubric.

Missing / unanswered evidence is an explicit outcome, never a silent zero
and never dropped from the denominator (assessment model). Incorrect is
recorded as incorrect, never a negative mark. The projection never carries
answers, keys, item identity, family or seed.
"""
from toefl_house.policy import digest

SCORER_VERSION = "objective-v1"
SUPPORTED_KINDS = ("Single Choice", "True False")
OUTCOMES = ("correct", "incorrect", "missing")


class ScoringUnavailable(ValueError):
    """Scoring cannot complete; str(exc) is the operator reason."""


def response_fingerprint(responses):
    """Order-independent digest of the latest sealed responses (no keys)."""
    return digest(sorted(
        (int(occurrence), int(row["revision"]), row.get("option_id") or "", int(row["missing"]))
        for occurrence, row in responses.items()))


def key_fingerprint(keys):
    """Digest of key versions used, without answers."""
    return digest(sorted(
        (name, int(row["key_version"]), row["content_hash"])
        for name, row in keys.items()))


def score(form, responses, keys):
    """Compute the objective projection. Raises ScoringUnavailable.

    form: allocated form with items [{order, item, skill, question_type}].
    responses: {order: {option_id, missing, revision}} — latest revision
    per occurrence, including explicit missing rows from seal.
    keys: {item name: {answer, key_version, content_hash}}.
    """
    if not isinstance(form, dict) or not isinstance(responses, dict) or not isinstance(keys, dict):
        raise ScoringUnavailable("Form, responses and keys required")
    items = form.get("items")
    if not isinstance(items, list) or not items:
        raise ScoringUnavailable("Form items required")
    orders = []
    projected = []
    by_skill = {}
    correct = incorrect = missing = 0
    for entry in items:
        if not isinstance(entry, dict):
            raise ScoringUnavailable("Invalid form item")
        order = entry.get("order")
        item_name = entry.get("item")
        skill = entry.get("skill")
        kind = entry.get("question_type")
        if type(order) is not int or order < 1 or not item_name or not skill:
            raise ScoringUnavailable("Form item identity required")
        if kind not in SUPPORTED_KINDS:
            raise ScoringUnavailable(f"Unsupported question type for objective scoring: {kind}")
        if order in orders:
            raise ScoringUnavailable("Duplicate occurrence")
        orders.append(order)
        if order not in responses:
            raise ScoringUnavailable(f"Missing sealed response for occurrence {order}")
        resp = responses[order]
        if not isinstance(resp, dict):
            raise ScoringUnavailable("Invalid response")
        if type(resp.get("missing")) is not int or resp["missing"] not in (0, 1):
            raise ScoringUnavailable("Response missing flag must be 0 or 1")
        if type(resp.get("revision")) is not int or resp["revision"] < 1:
            raise ScoringUnavailable("Response revision required")
        key = keys.get(item_name)
        if not isinstance(key, dict) or not isinstance(key.get("answer"), str) or not key["answer"]:
            raise ScoringUnavailable("Key required for allocated item")
        if type(key.get("key_version")) is not int or not key.get("content_hash"):
            raise ScoringUnavailable("Key version required")
        option_id = "" if resp.get("option_id") is None else resp.get("option_id")
        if resp["missing"]:
            if option_id not in ("", None):
                raise ScoringUnavailable("Missing responses cannot carry an option")
            outcome = "missing"
            missing += 1
        else:
            if not isinstance(option_id, str) or not option_id:
                raise ScoringUnavailable("Non-missing response requires an option")
            # Exact match; no Unicode folding, partial credit or negative marks.
            outcome = "correct" if option_id == key["answer"] else "incorrect"
            if outcome == "correct":
                correct += 1
            else:
                incorrect += 1
        bucket = by_skill.setdefault(skill, {"presented": 0, "correct": 0, "incorrect": 0, "missing": 0})
        bucket["presented"] += 1
        bucket[outcome] += 1
        projected.append({
            "order": order,
            "skill": skill,
            "question_type": kind,
            "outcome": outcome,
        })
    extra = set(responses) - set(orders)
    if extra:
        raise ScoringUnavailable("Response for unknown occurrence")
    if [entry["order"] for entry in items] != list(range(1, len(items) + 1)):
        raise ScoringUnavailable("Occurrences must be ordered 1..N")
    presented = len(items)
    if presented != correct + incorrect + missing:
        raise ScoringUnavailable("Score completeness mismatch")
    return {
        "algorithm": SCORER_VERSION,
        "items": projected,
        "by_skill": by_skill,
        "presented": presented,
        "correct": correct,
        "incorrect": incorrect,
        "missing": missing,
    }

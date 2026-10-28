"""Bounded constrained selection of synthetic candidate forms.

Pure standard-library module; no Frappe import. This is the allocation
algorithm of spec section 5 ("Allocation and exposure algorithm"): bounded
constrained selection over indexed, stratified eligible pools. It is NOT an
adaptive model and NOT an unrestricted random draw.

Determinism and auditability
----------------------------
The solver is a pure function of (sections, items, seed, exposure_counts):
the same inputs always produce the identical plan. Randomness enters only
through a server-generated cryptographic seed (64 hex chars, produced by the
caller with secrets.token_hex(32)); client input can never supply it. Every
plan records the pool digest, the seed and the algorithm version so an
authorized reader can re-derive the exact selection (the hosted acceptance
checks do exactly that).

Selection contract (ALGORITHM_VERSION = "allocation-v1")
--------------------------------------------------------
- sections carry exact per-skill item quotas from the published blueprint;
  a skill without enough eligible families makes the allocation infeasible
  (fail closed, explicit operator reason).
- at most one item per family per form: the family is the exposure unit and
  the exposure ledger is unique per (attempt, family, event kind).
- within a section, difficulty strata are balanced by round-robin preference
  (the stratum with the fewest already-selected items first). This is an
  engineering stratification spread, not an approved psychometric or
  institutional value.
- remaining ties prefer the family with the fewest total exposure events
  across the site (exposure_counts), then a seed-derived HMAC nonce, then
  the stable item name: fully deterministic, no client-influenced order.
- single-choice option display order is a seed-derived permutation of the
  item's stable option ids (answer-preserving: the key stores option ids,
  never positions). True/False keeps its canonical order; order-dependent
  content is never shuffled.
- bounded budget per spec 5.4: at most max_expansions candidate evaluations
  or max_seconds solver wall time; exhaustion raises
  AllocationUnavailable, never a silent quota or exposure relaxation.
"""
import time

from toefl_house.policy import digest

ALGORITHM_VERSION = "allocation-v1"
DEFAULT_MAX_EXPANSIONS = 10000
DEFAULT_MAX_SECONDS = 2.0
_DIFFICULTIES = ("Entry", "Core", "Stretch")


class AllocationUnavailable(ValueError):
    """Feasibility or budget failure; str(exc) is the operator reason."""


def _nonce(seed, *parts):
    message = "|".join(str(part) for part in parts).encode()
    import hashlib
    import hmac
    return int.from_bytes(hmac.new(seed.encode(), message, hashlib.sha256).digest()[:16], "big")


def pool_digest(items):
    """Order-independent digest of the eligible pool snapshot."""
    return digest(sorted(
        (item["name"], item["family"], item["skill"], item["difficulty"], item["question_type"])
        for item in items))


def derive_option_order(seed, question_type, option_ids, item_name, order):
    """Seed-derived display permutation of stable option ids.

    Returns None for non-single-choice types (canonical order is the only
    correct order for order-dependent content).
    """
    if question_type != "Single Choice":
        return None
    ids = list(option_ids)
    n = len(ids)
    for i in range(n - 1):
        j = i + _nonce(seed, "perm", item_name, order, i) % (n - i)
        ids[i], ids[j] = ids[j], ids[i]
    return ids


def allocate(sections, items, seed, exposure_counts,
             max_expansions=DEFAULT_MAX_EXPANSIONS, max_seconds=DEFAULT_MAX_SECONDS):
    """Select the form. Raises AllocationUnavailable with an operator reason.

    sections: list of {"id", "skill", "item_count"} in blueprint order.
    items:    list of {"name", "family", "skill", "difficulty",
                        "question_type", "options"} (eligible pool rows).
    seed:     64 hex chars of server-generated cryptographic randomness.
    exposure_counts: {family: total exposure events site-wide}; missing = 0.
    """
    started = time.monotonic()
    expansions = 0
    if not isinstance(seed, str) or len(seed) != 64:
        raise ValueError("Seed must be 64 hexadecimal characters")
    seen_ids = set()
    for section in sections:
        if not isinstance(section, dict) or set(section) != {"id", "skill", "item_count"}:
            raise ValueError("Section must contain exactly id, skill, item_count")
        if not section["id"] or section["id"] in seen_ids:
            raise ValueError("Invalid or duplicate section id")
        seen_ids.add(section["id"])
        if type(section["item_count"]) is not int or not 1 <= section["item_count"] <= 100:
            raise ValueError("Section item_count out of bounds")
    by_skill = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {
                "name", "family", "skill", "difficulty", "question_type", "options"}:
            raise ValueError("Invalid eligible pool entry")
        by_skill.setdefault(item["skill"], []).append(item)
    demand = {}
    for section in sections:
        demand[section["skill"]] = demand.get(section["skill"], 0) + section["item_count"]
    # Fail closed before spending budget: distinct eligible families per
    # skill must cover the skill's total demand (one item per family).
    for skill in sorted(demand):
        have = len({item["family"] for item in by_skill.get(skill, [])})
        if have < demand[skill]:
            raise AllocationUnavailable(
                f"insufficient eligible families for skill {skill}: need {demand[skill]}, have {have}")
    used_families = set()
    picked = {}
    # Most-constrained skill first (smallest pool, then largest demand), then
    # blueprint order within a skill; deterministic under any input order.
    for skill in sorted(demand, key=lambda sk: (len(by_skill.get(sk, [])), -demand[sk], sk)):
        for section in [s for s in sections if s["skill"] == skill]:
            picks = []
            stratum_counts = {d: 0 for d in _DIFFICULTIES}
            for _ in range(section["item_count"]):
                best = None
                for item in by_skill[skill]:
                    if item["family"] in used_families:
                        continue
                    expansions += 1
                    if expansions > max_expansions:
                        raise AllocationUnavailable("solver expansion budget exhausted")
                    score = (stratum_counts[item["difficulty"]],
                             exposure_counts.get(item["family"], 0),
                             _nonce(seed, "pick", item["name"], section["id"]),
                             item["name"])
                    if best is None or score < best[0]:
                        best = (score, item)
                if best is None:
                    raise AllocationUnavailable(f"no eligible item remains for section {section['id']}")
                item = best[1]
                picks.append(item)
                used_families.add(item["family"])
                stratum_counts[item["difficulty"]] += 1
                if time.monotonic() - started > max_seconds:
                    raise AllocationUnavailable("solver wall time budget exhausted")
            picked[section["id"]] = picks
    out_items = []
    order = 0
    for section in sections:
        for item in picked[section["id"]]:
            order += 1
            out_items.append({
                "order": order,
                "occurrence_id": "O%03d" % order,
                "item": item["name"],
                "family": item["family"],
                "skill": item["skill"],
                "difficulty": item["difficulty"],
                "section": section["id"],
                "question_type": item["question_type"],
                "option_order": derive_option_order(
                    seed, item["question_type"], item["options"], item["name"], order),
            })
    return {
        "algorithm": ALGORITHM_VERSION,
        "seed": seed,
        "pool_digest": pool_digest(items),
        "sections": [dict(s) for s in sections],
        "items": out_items,
    }

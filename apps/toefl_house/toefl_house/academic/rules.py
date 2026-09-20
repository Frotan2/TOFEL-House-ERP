"""Pure validation and resolution rules for the Owner configuration plane.

Everything here is deliberately frappe-free so the full rule set — including
the effective-dating semantics that protect historical records — is testable
offline (tests/configuration). The whitelisted commands in the package
``__init__`` are thin wrappers that apply these rules inside the guarded
Course Owner gate.

Design invariants (docs/product/CONFIGURATION-PLANE.md):

1. Codes are the stable identity; titles are presentation and may change.
2. A level's native Program anchor is set once and never changed.
3. Durations are effective-dated versions. Older versions are closed
   (``superseded_on``), never rewritten, so every date resolves to exactly
   one governing version and history keeps the version it was created under.
4. Version rows are monotone by ``effective_from`` — a new version must start
   strictly after the latest existing one, otherwise "which version governs
   this date" would be ambiguous.
5. Deactivation is the only destructive action; it is refused, in business
   language, while live records still depend on the configuration.

The generic version primitives live in the configuration foundation
(``toefl_house.configuration.rules``) and are delegated to — not copied —
below, so every domain resolves history by one implementation.
"""
import json
import math
import re

from toefl_house.configuration import rules as foundation

CODE_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9-]{1,31}")
DURATION_UNITS = ("Month", "Week", "Day")
# Numeric ceiling: one year in the smallest unit is already far beyond any
# real TOEFL House level; this is a typo guard, not business policy.
DURATION_MAX = {"Month": 24.0, "Week": 104.0, "Day": 730.0}
TITLE_MAX = 140
REASON_MAX = 500


def validate_code(value):
    """Stable code: 2–32 uppercase letters/digits/dashes, dashes not at the edges."""
    if not isinstance(value, str):
        raise ValueError("A code is required")
    code = value.strip()
    if not CODE_PATTERN.fullmatch(code):
        raise ValueError(
            "Codes use 2-32 characters of A-Z, 0-9 and dashes, starting with a letter or digit")
    if code.startswith("-") or code.endswith("-") or "--" in code:
        raise ValueError("Codes cannot start or end with a dash or contain double dashes")
    return code


def validate_title(value, what="Title"):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} is required")
    title = " ".join(value.strip().split())
    if len(title) > TITLE_MAX:
        raise ValueError(f"{what} must be at most {TITLE_MAX} characters")
    return title


def validate_reason(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("Reason must be text")
    reason = value.strip()
    if len(reason) > REASON_MAX:
        raise ValueError(f"Reason must be at most {REASON_MAX} characters")
    return reason


def validate_sequence(value):
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Sequence must be a whole number (1 = first level)")
    if value < 1 or value > 999:
        raise ValueError("Sequence must be between 1 and 999")
    return value


def validate_duration_value(value, unit):
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("Duration must be a number") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Duration must be a number")
    value = float(value)
    if unit not in DURATION_UNITS:
        raise ValueError("Duration unit must be Month, Week or Day")
    if value <= 0:
        raise ValueError("Duration must be greater than zero")
    if value > DURATION_MAX[unit]:
        raise ValueError(
            f"Duration of {value:g} {unit.lower()}s looks like a typo; "
            f"the maximum accepted is {DURATION_MAX[unit]:g} {unit.lower()}s")
    return value


def parse_date(value, what="Effective date"):
    """Strict ISO date parse; returns the ``YYYY-MM-DD`` string."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        raise ValueError(f"{what} must be a date (YYYY-MM-DD)")
    date = value.strip()
    year, month, day = (int(part) for part in date.split("-"))
    import datetime
    try:
        datetime.date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"{what} is not a real calendar date") from exc
    return date


def normalize_versions(rows):
    """Order version rows by effective date (input order breaks ties)."""
    return foundation.normalize_versions(rows)


def resolve_duration(rows, on_date):
    """The duration version governing ``on_date``: the latest version whose
    ``effective_from`` is on or before that date. Returns None when no version
    is effective yet — callers must surface that, never guess.

    Historical integrity: because rows are only ever appended and closed, the
    same (rows, on_date) pair always resolves to the same version, so an
    enrollment that recorded its governing version can never be invalidated
    by later changes.
    """
    return foundation.resolve_governing(rows, on_date)


def duration_label(row):
    if not row:
        return ""
    value = float(row.get("duration_value") or 0)
    unit = str(row.get("duration_unit") or "").lower()
    number = f"{value:g}"
    if float(value).is_integer() and unit in ("month", "week", "day") and value == 1:
        return f"{number} {unit}"
    return f"{number} {unit}s" if unit else ""


def check_version_appends(rows, new_effective_from):
    """The monotone-version rule: a new version must start strictly after the
    latest existing one, so every date resolves to exactly one version."""
    foundation.check_appends(rows, new_effective_from, what="duration version")


def validate_fee_amount(value):
    """A fee component amount: positive number, bounded by a typo guard.

    The ceiling is not business policy — it exists so a slipped keystroke
    cannot silently define a nine-figure charge. The Owner's real amounts
    are data; this only refuses implausible input.
    """
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("Fee amount must be a number") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Fee amount must be a number")
    value = float(value)
    if value <= 0:
        raise ValueError("Fee amount must be greater than zero")
    if value > 100_000_000:
        raise ValueError("Fee amount looks like a typo; the maximum accepted is 100000000")
    return value


def validate_component_rows(rows):
    """A fee plan's component set: non-empty, unique categories, valid amounts.

    Category is the native Fee Category name (which owns the native Item);
    amounts are what the student is charged. This is display-and-validation
    only — the native Fee Structure remains the money authority.
    """
    if not rows:
        raise ValueError("A fee plan needs at least one fee component")
    seen = set()
    normalized = []
    for row in rows:
        category = rules_category(row)
        if category in seen:
            raise ValueError(f"Fee category {category} appears more than once in the plan")
        seen.add(category)
        amount = validate_fee_amount(row.get("amount") if isinstance(row, dict) else row)
        normalized.append({"category": category, "amount": amount})
    return normalized


def rules_category(row):
    if not isinstance(row, dict):
        raise ValueError("Each fee component needs a fee category and an amount")
    category = row.get("category")
    if not isinstance(category, str) or not category.strip():
        raise ValueError("Each fee component needs a fee category")
    category = category.strip()
    if len(category) > 140:
        raise ValueError("Fee category names must be at most 140 characters")
    return category


def validate_year_bounds(start_date, end_date):
    start = parse_date(start_date, "Academic year start")
    end = parse_date(end_date, "Academic year end")
    if end < start:
        raise ValueError("The academic year cannot end before it starts")
    return start, end


def duration_history_counts(rows, enrollment_dates):
    """Answer 'which configuration was active when?' (mission §17).

    For each enrollment date, resolve the duration version that governed it
    and count. The result is how the Owner sees history split across policy
    versions without any record being rewritten. Unresolvable dates (before
    the first version) are counted under "" — surfaced, never guessed.
    """
    counts = {}
    for value in enrollment_dates or []:
        governing = resolve_duration(rows, str(value))
        label = duration_label(governing) if governing else ""
        key = f"{label} (from {governing.get('effective_from')})" if governing \
            else "before the first configured version"
        counts[key] = counts.get(key, 0) + 1
    return counts


def latest_version(rows):
    """The most recently effective version row, or None."""
    return foundation.latest_version(rows)


def validate_next_level(level_code, next_code, family_of, next_of, max_depth=64):
    """Same-family, non-self, acyclic progression link.

    ``family_of`` and ``next_of`` are lookup callables over level codes so the
    rule stays frappe-free and testable.
    """
    if not next_code:
        return None
    if next_code == level_code:
        raise ValueError("A level cannot be its own next level")
    target_family = family_of(next_code)
    if target_family is None:
        raise ValueError("The next level must be an existing level of the same program")
    if target_family != family_of(level_code):
        raise ValueError("The next level must belong to the same program family")
    # Walk forward from the target; reaching level_code again means a cycle.
    seen = {level_code}
    cursor = next_code
    depth = 0
    while cursor and depth < max_depth:
        if cursor in seen:
            raise ValueError("That next level would create a progression cycle")
        seen.add(cursor)
        cursor = next_of(cursor)
        depth += 1
    return next_code


def level_in_use_message(code, enrollments):
    return (
        f"Level {code} is currently used by {enrollments} submitted enrollment(s). "
        "It cannot be deactivated while live enrollments depend on it. "
        "Let those learners finish, then retire the level for new enrollments.")


def program_has_levels_message(code, levels):
    return (
        f"Program {code} still has {levels} active level(s). "
        "Deactivate or retire the levels first; the program itself is deactivated "
        "only once no active level depends on it.")


def level_missing_native_message(code):
    return (
        f"Level {code} has no native program anchor. This is a configuration "
        "integrity fault: contact the administrator; do not enroll against it.")


def validate_discount_percentage(value):
    """Discount percentage: number between >0 and <=100."""
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("Discount percentage must be a number") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Discount percentage must be a number")
    val = float(value)
    if val <= 0:
        raise ValueError("Discount percentage must be greater than zero")
    if val > 100.0:
        raise ValueError("Discount percentage cannot exceed 100%")
    return val


def validate_precedence(value):
    """Explicit configured precedence: whole number (higher value = higher precedence)."""
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Precedence must be a whole number (1 = base priority)")
    if value < 1 or value > 999999:
        raise ValueError("Precedence must be between 1 and 999999")
    return value


def apply_charge_discount(gross, discount_percentage):
    """Net billable amount after the single winning discount (OD-CP-1 A).

    The pinned native Education Fees controller computes grand_total as the
    plain sum of component amounts and never applies the child ``discount``
    field; the resolved discount therefore has to be baked into the billed
    amount itself. One application per line — stacking is unrepresentable by
    construction, because a single percentage is supplied here at most once.
    """
    g = float(gross)
    if g < 0:
        raise ValueError("Fee amount must not be negative")
    percent = validate_discount_percentage(discount_percentage)
    return round(g - (g * percent / 100.0), 2)


def resolve_charge_discount(rules_list, fee_category=None, program=None):
    """Resolve eligible discount rules under OD-CP-1 Policy A (Single Discount Per Charge).

    A charge line may receive zero or one discount only. Discounts must never stack.
    If multiple rules are eligible, the system resolves them to one applicable discount
    according to explicit configured precedence (higher precedence wins; ties broken
    deterministically by highest percentage, then rule code).
    """
    eligible = []
    for rule in rules_list or []:
        if rule.get("status") != "Active":
            continue
        rule_cat = rule.get("fee_category")
        if rule_cat and fee_category and rule_cat != fee_category:
            continue
        rule_prog = rule.get("program")
        if rule_prog and program and rule_prog != program:
            continue
        eligible.append(rule)

    if not eligible:
        return None

    # Explicit precedence order: higher precedence wins; tie-break on percentage then code
    eligible.sort(
        key=lambda r: (
            int(r.get("precedence") or 1),
            float(r.get("discount_percentage") or 0),
            -len(str(r.get("code") or "")),
            str(r.get("code") or "")
        ),
        reverse=True
    )
    winner = eligible[0]
    return {
        "rule_code": winner.get("code") or winner.get("name"),
        "rule_title": winner.get("title") or winner.get("code") or winner.get("name"),
        "discount_percentage": float(winner.get("discount_percentage") or 0),
        "precedence": int(winner.get("precedence") or 1),
    }


# --- D1 assessment-policy facets (structures only, zero business values) -----
# Each facet is one owner-decided face of an assessment policy version,
# stored as canonical JSON on the version row (or absent until the Course
# Owner defines it). Shapes, bounds, cross-references and the fixed
# structural vocabularies below are engineering; every value inside them
# is owner-entered through the guarded facet commands. Unknown keys are
# refused everywhere: a mistyped key must fail closed, never silently
# drop a rule. Native per-group Assessment Plans are scheduled instances
# and are never referenced here; native Course weight columns are never
# read — combination semantics arrive with a future owner rule.
ASSESSMENT_FACETS = ("components", "weights", "pass_rules", "rubrics",
                     "progression", "retakes", "level_mapping")
# Numeric ceiling: far beyond any plausible component maximum; a typo
# guard in the DURATION_MAX tradition, not business policy.
ASSESSMENT_SCORE_MAX = 1000000.0
PERCENT_MIN = 0.0
PERCENT_MAX = 100.0
# Structural vocabularies (engineering-fixed alternatives; the owner picks
# among them and supplies every value). A cutoff is expressible either as
# a percentage or as a grade code because native grading produces exactly
# those two outputs; progression evidence kinds mirror the native evidence
# authorities (results, attendance, human approval).
PASS_MINIMUM_KINDS = ("percent", "grade")
PROGRESSION_EVIDENCE_KINDS = ("assessment_pass", "attendance", "approval")
RETAKE_SCOPES = ("full", "partial")
RETAKE_GOVERNING = ("latest", "best", "first")
PROGRESSION_NEXT = "next"


def _facet_number(value, what, minimum=None, maximum=None, whole=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{what} must be a finite number")
    if whole and number != int(number):
        raise ValueError(f"{what} must be a whole number")
    if minimum is not None and number < minimum:
        raise ValueError(f"{what} must be at least {minimum:g}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{what} must be at most {maximum:g}")
    return int(number) if whole else number


def _facet_text(value, what, maximum=TITLE_MAX):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} is required")
    text = value.strip()
    if len(text) > maximum:
        raise ValueError(f"{what} must be at most {maximum} characters")
    return text


def _facet_entries(value, what):
    if not isinstance(value, list) or not value:
        raise ValueError(f"{what} must be a non-empty list")
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError(f"{what} entries must be objects")
    return value


def _facet_object(value, what):
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{what} must be a non-empty object")
    return value


def _refuse_unknown(entry, allowed, what):
    for key in entry:
        if key not in allowed:
            raise ValueError(
                f"{what} has an unknown key {key!r}; allowed keys are "
                + ", ".join(sorted(allowed)))


def _refuse_duplicates(values, what):
    seen = set()
    for value in values:
        if value in seen:
            raise ValueError(f"{what} lists {value!r} twice")
        seen.add(value)


def parse_facet(name, raw):
    """Parse one stored facet to python, or None when absent/withdrawn.

    Accepts canonical JSON text (the stored form) or an already-parsed
    object (command input). Empty containers normalize to absent: a
    withdrawn facet is simply undefined again, with the withdrawal itself
    recorded by the version reason and the command audit event.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{name} must be valid JSON") from exc
    elif isinstance(raw, (dict, list)):
        parsed = raw
    else:
        raise ValueError(f"{name} must be valid JSON")
    if parsed in ([], {}):
        return None
    return parsed


def validate_components(entries):
    cleaned = []
    for position, entry in enumerate(_facet_entries(entries, "Components"),
                                     start=1):
        _refuse_unknown(entry, {"code", "title", "maximum_score",
                                "criteria"},
                        f"Component {position}")
        row = {"code": validate_code(entry.get("code")),
               "title": validate_title(entry.get("title"),
                                       "Component title"),
               "maximum_score": _facet_number(
                   entry.get("maximum_score"), "Component maximum score",
                   minimum=0, maximum=ASSESSMENT_SCORE_MAX)}
        if row["maximum_score"] <= 0:
            raise ValueError("Component maximum score must be greater than zero")
        if entry.get("criteria") not in (None, ""):
            row["criteria"] = _facet_text(entry.get("criteria"),
                                          "Component criteria")
        cleaned.append(row)
    _refuse_duplicates([row["code"] for row in cleaned],
                       "Components")
    return cleaned


def validate_weights(entries, components):
    codes = [row["code"] for row in components or []]
    if not codes:
        raise ValueError(
            "Weights need defined components first; set the components facet")
    cleaned = []
    for position, entry in enumerate(_facet_entries(entries, "Weights"),
                                     start=1):
        _refuse_unknown(entry, {"component", "weight"},
                        f"Weight {position}")
        component = validate_code(entry.get("component"))
        if component not in codes:
            raise ValueError(
                f"Weight {position} names unknown component {component!r}")
        cleaned.append({"component": component,
                        "weight": _facet_number(entry.get("weight"),
                                                "Component weight",
                                                minimum=0)})
    _refuse_duplicates([row["component"] for row in cleaned], "Weights")
    return cleaned


def _validate_minimum(entry, what):
    _refuse_unknown(entry, {"kind", "value"}, what)
    kind = entry.get("kind")
    if kind not in PASS_MINIMUM_KINDS:
        raise ValueError(
            f"{what} kind must be one of {', '.join(PASS_MINIMUM_KINDS)}")
    if kind == "percent":
        return {"kind": kind,
                "value": _facet_number(entry.get("value"),
                                       f"{what} percent",
                                       minimum=PERCENT_MIN,
                                       maximum=PERCENT_MAX)}
    return {"kind": kind,
            "value": _facet_text(entry.get("value"), f"{what} grade code")}


def validate_pass_rules(mapping, components):
    codes = [row["code"] for row in components or []]
    body = _facet_object(mapping, "Pass rules")
    _refuse_unknown(body, {"components", "overall"}, "Pass rules")
    items = body.get("components") or []
    if not isinstance(items, list):
        raise ValueError("Pass rule components must be a list")
    cleaned = []
    for position, entry in enumerate(items, start=1):
        if not isinstance(entry, dict):
            raise ValueError("Pass rule components must be objects")
        _refuse_unknown(entry, {"component", "minimum"},
                        f"Pass rule {position}")
        component = validate_code(entry.get("component"))
        if component not in codes:
            raise ValueError(
                f"Pass rule {position} names unknown component {component!r}")
        minimum = entry.get("minimum")
        if not isinstance(minimum, dict):
            raise ValueError(f"Pass rule {position} needs a minimum")
        cleaned.append({"component": component,
                        "minimum": _validate_minimum(
                            minimum, f"Pass rule {position} minimum")})
    _refuse_duplicates([row["component"] for row in cleaned], "Pass rules")
    result = {"components": cleaned}
    if body.get("overall") is not None:
        overall = body.get("overall")
        if not isinstance(overall, dict):
            raise ValueError("Pass rule overall minimum must be an object")
        result["overall"] = _validate_minimum(overall, "Overall minimum")
    if not cleaned and "overall" not in result:
        raise ValueError(
            "Pass rules must define at least one component or overall minimum")
    return result


def validate_rubrics(entries, components):
    codes = [row["code"] for row in components or []]
    cleaned = []
    for position, entry in enumerate(_facet_entries(entries, "Rubrics"),
                                     start=1):
        _refuse_unknown(entry, {"code", "title", "component", "evidence",
                                "levels"},
                        f"Rubric {position}")
        row = {"code": _facet_text(entry.get("code"), "Rubric code"),
               "title": validate_title(entry.get("title"), "Rubric title")}
        if entry.get("component") not in (None, ""):
            component = validate_code(entry.get("component"))
            if component not in codes:
                raise ValueError(
                    f"Rubric {position} names unknown component {component!r}")
            row["component"] = component
        evidence = entry.get("evidence")
        if (not isinstance(evidence, list) or not evidence
                or any(not isinstance(line, str) or not line.strip()
                       for line in evidence)):
            raise ValueError(
                f"Rubric {position} needs a non-empty evidence list")
        row["evidence"] = [_facet_text(line, "Rubric evidence")
                           for line in evidence]
        levels = entry.get("levels") or []
        if not isinstance(levels, list):
            raise ValueError(f"Rubric {position} levels must be a list")
        cleaned_levels = []
        for number, level in enumerate(levels, start=1):
            if not isinstance(level, dict):
                raise ValueError(f"Rubric {position} levels must be objects")
            _refuse_unknown(level, {"code", "title", "description"},
                            f"Rubric {position} level {number}")
            cleaned_level = {
                "code": _facet_text(level.get("code"), "Rubric level code"),
                "title": validate_title(level.get("title"),
                                        "Rubric level title")}
            if level.get("description") not in (None, ""):
                if not isinstance(level.get("description"), str):
                    raise ValueError(
                        f"Rubric {position} level {number} description "
                        "must be text")
                cleaned_level["description"] = level["description"].strip()
            cleaned_levels.append(cleaned_level)
        _refuse_duplicates([level["code"] for level in cleaned_levels],
                           f"Rubric {position} levels")
        if cleaned_levels:
            row["levels"] = cleaned_levels
        cleaned.append(row)
    _refuse_duplicates([row["code"] for row in cleaned], "Rubrics")
    return cleaned


def _validate_progression_evidence(entry, position):
    if not isinstance(entry, dict):
        raise ValueError("Progression evidence entries must be objects")
    kind = entry.get("kind")
    if kind not in PROGRESSION_EVIDENCE_KINDS:
        raise ValueError(
            "Progression evidence kind must be one of "
            + ", ".join(PROGRESSION_EVIDENCE_KINDS))
    if kind == "assessment_pass":
        _refuse_unknown(entry, {"kind", "policy"},
                        f"Progression evidence {position}")
        return {"kind": kind,
                "policy": validate_code(entry.get("policy"))}
    if kind == "attendance":
        _refuse_unknown(entry, {"kind", "minimum_percent"},
                        f"Progression evidence {position}")
        return {"kind": kind,
                "minimum_percent": _facet_number(
                    entry.get("minimum_percent"),
                    "Progression attendance minimum",
                    minimum=PERCENT_MIN, maximum=PERCENT_MAX)}
    _refuse_unknown(entry, {"kind", "role"},
                    f"Progression evidence {position}")
    return {"kind": kind,
            "role": _facet_text(entry.get("role"), "Progression approver role")}


def validate_progression(mapping):
    body = _facet_object(mapping, "Progression")
    _refuse_unknown(body, {"target", "requires"}, "Progression")
    target = body.get("target")
    if target != PROGRESSION_NEXT:
        target = validate_code(target)
    requires = body.get("requires")
    if not isinstance(requires, list) or not requires:
        raise ValueError("Progression needs a non-empty evidence list")
    return {"target": target,
            "requires": [_validate_progression_evidence(entry, position)
                         for position, entry in enumerate(requires, start=1)]}


def validate_retakes(mapping):
    body = _facet_object(mapping, "Retakes")
    _refuse_unknown(body, {"max_attempts", "wait_days", "scope",
                           "governing"},
                    "Retakes")
    for required in ("max_attempts", "wait_days", "scope", "governing"):
        if required not in body:
            raise ValueError(f"Retakes need {required.replace('_', ' ')}")
    attempts = body.get("max_attempts")
    cleaned = {"max_attempts": (
        None if attempts is None
        else _facet_number(attempts, "Retake attempts", minimum=1,
                           whole=True))}
    cleaned["wait_days"] = _facet_number(body.get("wait_days"), "Retake wait",
                                         minimum=0, whole=True)
    scope = body.get("scope")
    if scope not in RETAKE_SCOPES:
        raise ValueError(
            "Retake scope must be one of " + ", ".join(RETAKE_SCOPES))
    cleaned["scope"] = scope
    governing = body.get("governing")
    if governing not in RETAKE_GOVERNING:
        raise ValueError(
            "Retake governing attempt must be one of "
            + ", ".join(RETAKE_GOVERNING))
    cleaned["governing"] = governing
    return cleaned


def validate_level_mapping(mapping):
    body = _facet_object(mapping, "Level mapping")
    _refuse_unknown(body, {"levels"}, "Level mapping")
    levels = body.get("levels")
    if not isinstance(levels, list):
        raise ValueError("Level mapping levels must be a list")
    cleaned = [validate_code(code) for code in levels]
    _refuse_duplicates(cleaned, "Level mapping")
    return {"levels": cleaned}


def canonical_facet(name, raw, components=None):
    """Validate one facet and return its canonical stored form.

    Returns "" when absent/withdrawn, else canonical JSON (sorted keys,
    compact separators) so identical meaning always digests identically.
    ``components`` carries the row's parsed components for the
    cross-references weights, pass rules and rubrics make into them.
    """
    parsed = parse_facet(name, raw)
    if parsed is None:
        return ""
    if name == "components":
        cleaned = validate_components(parsed)
    elif name == "weights":
        cleaned = validate_weights(parsed, components)
    elif name == "pass_rules":
        cleaned = validate_pass_rules(parsed, components)
    elif name == "rubrics":
        cleaned = validate_rubrics(parsed, components)
    elif name == "progression":
        cleaned = validate_progression(parsed)
    elif name == "retakes":
        cleaned = validate_retakes(parsed)
    elif name == "level_mapping":
        cleaned = validate_level_mapping(parsed)
    else:
        raise ValueError(f"Unknown assessment facet {name!r}")
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def validate_policy_facets(facets):
    """Validate every facet present on one version row, coherently.

    ``facets`` maps facet name to its stored raw value. Returns the parsed
    facets (absent ones omitted). Malformed stored JSON is an integrity
    fault, never silently skipped — history must keep resolving.
    """
    parsed = {}
    for name in ASSESSMENT_FACETS:
        value = parse_facet(name, (facets or {}).get(name))
        if value is not None:
            parsed[name] = value
    components = parsed.get("components")
    if "components" in parsed:
        parsed["components"] = validate_components(components)
        components = parsed["components"]
    if "weights" in parsed:
        parsed["weights"] = validate_weights(parsed["weights"], components)
    if "pass_rules" in parsed:
        parsed["pass_rules"] = validate_pass_rules(parsed["pass_rules"],
                                                   components)
    if "rubrics" in parsed:
        parsed["rubrics"] = validate_rubrics(parsed["rubrics"], components)
    if "progression" in parsed:
        parsed["progression"] = validate_progression(parsed["progression"])
    if "retakes" in parsed:
        parsed["retakes"] = validate_retakes(parsed["retakes"])
    if "level_mapping" in parsed:
        parsed["level_mapping"] = validate_level_mapping(
            parsed["level_mapping"])
    return parsed


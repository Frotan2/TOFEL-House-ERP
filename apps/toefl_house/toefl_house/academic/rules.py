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
"""
import re

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
    return sorted(list(rows or []), key=lambda row: str(row.get("effective_from") or ""))


def resolve_duration(rows, on_date):
    """The duration version governing ``on_date``: the latest version whose
    ``effective_from`` is on or before that date. Returns None when no version
    is effective yet — callers must surface that, never guess.

    Historical integrity: because rows are only ever appended and closed, the
    same (rows, on_date) pair always resolves to the same version, so an
    enrollment that recorded its governing version can never be invalidated
    by later changes.
    """
    governing = None
    for row in rows or []:
        effective = str(row.get("effective_from") or "")
        if not effective or str(on_date) < effective:
            continue
        if governing is None or effective >= str(governing.get("effective_from") or ""):
            governing = row
    return governing


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
    existing = normalize_versions(rows)
    if existing:
        latest = existing[-1]
        if str(new_effective_from) <= str(latest.get("effective_from") or ""):
            raise ValueError(
                "A new duration version must start after the latest version "
                f"({latest.get('effective_from')}); backdated or same-day versions "
                "would make history ambiguous")


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
    existing = normalize_versions(rows)
    return existing[-1] if existing else None


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


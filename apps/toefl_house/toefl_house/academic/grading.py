"""Deterministic academic grading over Owner-configured assessment policy.

D1 (the deferral of grading policy) is answered by *configuration*, not by
code: this module contains no threshold, weight, cutoff, attempt limit or
attendance minimum. It carries only the engineering semantics that turn the
Owner's effective-dated facets — components, weights, pass rules, rubrics,
progression, retakes, level mapping — plus the native ``Grading Scale`` the
version points at, plus the marks an authorized instructor recorded, into
one reproducible result.

Design invariants (docs/ACADEMIC-ASSESSMENT.md):

1. **Nothing is invented.** Every academic value comes from a policy facet or
   from the native Grading Scale intervals the Owner maintains natively. A
   missing facet is an explicit ``unconfigured`` state, never a default.
2. **Deterministic.** The same (policy snapshot, marks, scale, algorithm
   version) always yields the same bytes. No clock, no database, no
   float-order dependence: arithmetic is Decimal with one documented
   quantization (4 decimal places, ROUND_HALF_UP), and the result is
   assembled into a canonical, digestible snapshot.
3. **Transparent.** Every number carries the explanation that produced it;
   the snapshot the site stores is the same structure the caller sees here.
4. **Fail closed.** Missing marks are ``Incomplete`` and never a pass; a
   component without a weight, a weight set that sums to zero, a pass rule
   naming an unknown component, or a grade cutoff with no configured native
   scale all raise instead of guessing.

Frappe-free by design so the whole rule set is testable offline
(tests/academic), exactly like ``toefl_house.academic.rules``.
"""
from decimal import Decimal, ROUND_HALF_UP

from toefl_house.academic import rules
from toefl_house.policy import canonical, digest

ALGORITHM = "th-grading-v1"
# Engineering precision, not academic policy: four decimal places is enough
# to keep any realistic component/weight arithmetic order-independent while
# staying exactly reproducible across sites and machines.
QUANTUM = Decimal("0.0001")
PERCENT = Decimal("100")
# The facets a grading run needs before it may produce a result. Their
# absence is the explicit "unconfigured" state the command layer surfaces.
GRADING_FACETS = ("components", "weights", "pass_rules")
OUTCOMES = ("Pass", "Fail", "Incomplete")


def _decimal(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError(f"{what} must be a number")
    if isinstance(value, Decimal):
        number = value
    else:
        try:
            number = Decimal(str(value).strip())
        except Exception as exc:  # noqa: BLE001 - Decimal raises several types
            raise ValueError(f"{what} must be a number") from exc
    if not number.is_finite():
        raise ValueError(f"{what} must be a finite number")
    return number


def quantize(value):
    """The single rounding rule of the assessment runtime (4dp, half up)."""
    return _decimal(value, "Value").quantize(QUANTUM, rounding=ROUND_HALF_UP)


def _fmt(value):
    """A number as it reads in an explanation (trailing zeros dropped)."""
    return format(float(value), "g")


def parse_facets(raw):
    """Parse and re-validate the stored facets of one policy version.

    Stored facets are canonical JSON written only by the guarded facet
    commands, so a parse failure here is an integrity fault: it raises
    rather than grading against a partly-understood policy.
    """
    return rules.validate_policy_facets(raw or {})


def policy_state(facets, grading_scale_intervals):
    """Is this policy version complete enough to grade? Never a guess.

    Returns ``{"configured": bool, "missing": [...], "explanations": [...]}``.
    The command layer refuses grading and explains exactly which Owner
    decision is outstanding; nothing here supplies a fallback value.
    """
    missing = [name for name in GRADING_FACETS if not facets.get(name)]
    explanations = []
    if missing:
        explanations.append(
            "This assessment policy version has no "
            + ", ".join(missing)
            + " configured; the Course Owner must define them before marks "
            "can be graded")
    components = facets.get("components") or []
    weights = facets.get("weights") or []
    if components and weights:
        weighted = {row["component"] for row in weights}
        unweighted = [row["code"] for row in components
                      if row["code"] not in weighted]
        if unweighted:
            missing.append("weights for " + ", ".join(unweighted))
            explanations.append(
                "Components " + ", ".join(unweighted)
                + " have no configured weight; the weighted result is "
                "undefined until the Course Owner sets one")
        elif sum(Decimal(str(row["weight"])) for row in weights) <= 0:
            missing.append("a positive weight total")
            explanations.append(
                "The configured weights total zero; the weighted result is "
                "undefined until the Course Owner sets positive weights")
    if not grading_scale_intervals:
        missing.append("grading scale intervals")
        explanations.append(
            "No native Grading Scale intervals are configured for this "
            "policy version, so no grade code can be produced")
    return {"configured": not missing, "missing": missing,
            "explanations": explanations}


def grade_for(intervals, percent):
    """The native ``Grading Scale`` grade for a percentage.

    Mirrors ``education.education.api.get_grade`` exactly (highest configured
    threshold at or below the percentage; empty when none applies) so a
    published TH result and the native Assessment Result agree. Thresholds
    are Owner-entered on the native scale; none are supplied here.
    """
    if percent is None:
        return ""
    best = None
    for row in intervals or []:
        threshold = _decimal(row.get("threshold"), "Grading scale threshold")
        code = row.get("grade_code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Every grading scale interval needs a grade code")
        if _decimal(percent, "Percentage") >= threshold:
            if best is None or threshold > best[0]:
                best = (threshold, code)
    return best[1] if best else ""


def _minimum_met(minimum, percent, grade_code):
    """One pass-rule minimum, judged exactly as the Owner configured it."""
    kind = minimum.get("kind")
    value = minimum.get("value")
    if kind == "percent":
        target = _decimal(value, "Percent minimum")
        return (_decimal(percent, "Component percentage") >= target,
                _fmt(target) + "%", _fmt(quantize(percent)) + "%")
    if kind == "grade":
        # A grade cutoff is only meaningful with a grade code; the native
        # scale decides the boundaries, so no ordering is assumed here.
        if not isinstance(value, str) or not value.strip():
            raise ValueError("A grade minimum needs a grade code")
        return (grade_code == value, f"grade {value}",
                f"grade {grade_code or '(none)'}")
    raise ValueError(f"Unknown pass minimum kind: {kind}")


def compute_result(facets, marks, grading_scale_intervals):
    """Compute one student's result from the pinned policy and their marks.

    ``facets`` are the parsed facets of the pinned policy version, ``marks``
    maps component code to ``{"mark": number|None, "missing_reason": str}``
    and ``grading_scale_intervals`` are the native scale rows. Returns a
    self-describing snapshot; nothing is stored, persisted or emailed here.
    """
    state = policy_state(facets, grading_scale_intervals)
    if not state["configured"]:
        raise ValueError("; ".join(state["explanations"]))
    components = facets["components"]
    weight_of = {row["component"]: _decimal(row["weight"], "Component weight")
                 for row in facets["weights"]}
    total_weight = sum(weight_of.values(), Decimal("0"))
    if total_weight <= 0:
        raise ValueError("The configured weights total zero; no weighted result exists")

    rows = []
    explanations = []
    missing = []
    contributions = []
    for component in components:
        code = component["code"]
        maximum = _decimal(component["maximum_score"], "Component maximum score")
        recorded = (marks or {}).get(code) or {}
        raw_mark = recorded.get("mark")
        weight = weight_of[code]
        if raw_mark is None:
            missing.append(code)
            explanations.append(
                f"Component {code} ({component['title']}) has no mark"
                + (f": {recorded.get('missing_reason')}"
                   if recorded.get("missing_reason") else ""))
            rows.append({
                "component": code, "title": component["title"],
                "maximum_score": float(maximum), "mark": None,
                "percent": None, "weight": float(weight),
                "weighted_percent": None, "missing": 1,
                "missing_reason": recorded.get("missing_reason") or "",
            })
            continue
        mark = _decimal(raw_mark, f"Mark for {code}")
        if mark < 0:
            raise ValueError(f"Mark for {code} cannot be negative")
        if mark > maximum:
            raise ValueError(
                f"Mark for {code} ({mark:g}) exceeds the configured maximum "
                f"({maximum:g})")
        exact_percent = mark / maximum * PERCENT
        percent = exact_percent.quantize(QUANTUM, rounding=ROUND_HALF_UP)
        exact_weighted = exact_percent * weight / total_weight
        weighted = exact_weighted.quantize(QUANTUM, rounding=ROUND_HALF_UP)
        contributions.append(exact_weighted)
        explanations.append(
            f"Component {code} ({component['title']}): {_fmt(mark)}/{_fmt(maximum)} "
            f"= {_fmt(percent)}% at weight {_fmt(weight)} of {_fmt(total_weight)} "
            f"-> contributes {_fmt(weighted)} points")
        rows.append({
            "component": code, "title": component["title"],
            "maximum_score": float(maximum), "mark": float(mark),
            "percent": float(percent), "weight": float(weight),
            "weighted_percent": float(weighted), "missing": 0,
            "missing_reason": "",
        })

    # The overall percentage is the quantized sum of the UNROUNDED weighted
    # contributions, so per-component display rounding can never move a result.
    overall = (sum(contributions, Decimal("0")).quantize(
        QUANTUM, rounding=ROUND_HALF_UP) if not missing else None)
    grade_code = grade_for(grading_scale_intervals, overall) if overall is not None else ""
    if overall is not None:
        explanations.append(
            f"Weighted overall: {_fmt(overall)}% -> grade "
            f"{grade_code or '(no configured interval applies)'}")

    checks = []
    met_all = True
    percents = {row["component"]: row["percent"] for row in rows}
    for rule in (facets.get("pass_rules") or {}).get("components") or []:
        code = rule["component"]
        percent = percents.get(code)
        row_grade = grade_for(grading_scale_intervals, percent) if percent is not None else ""
        if percent is None:
            met, target, actual = False, "a recorded mark", "no mark"
        else:
            met, target, actual = _minimum_met(rule["minimum"], percent, row_grade)
        met_all = met_all and met
        checks.append({"scope": code, "rule": rule["minimum"],
                       "target": target, "actual": actual, "met": met})
        explanations.append(
            f"Pass rule component {code}: needs {target}, recorded {actual} "
            f"-> {'met' if met else 'not met'}")
    overall_rule = (facets.get("pass_rules") or {}).get("overall")
    if overall_rule:
        if overall is None:
            met, target, actual = False, "an overall percentage", "incomplete"
        else:
            met, target, actual = _minimum_met(overall_rule, overall, grade_code)
        met_all = met_all and met
        checks.append({"scope": "overall", "rule": overall_rule,
                       "target": target, "actual": actual, "met": met})
        explanations.append(
            f"Pass rule overall: needs {target}, recorded {actual} "
            f"-> {'met' if met else 'not met'}")

    if missing:
        outcome = "Incomplete"
        explanations.append(
            "Result is Incomplete: " + ", ".join(missing)
            + " still need a mark or a recorded missing reason. An "
            "incomplete result is never a pass")
    else:
        outcome = "Pass" if met_all else "Fail"

    return {
        "algorithm": ALGORITHM,
        "quantization": "4dp round-half-up",
        "grading_scale_intervals": sorted(
            ({"threshold": float(_decimal(row.get("threshold"), "Threshold")),
              "grade_code": row.get("grade_code")}
             for row in grading_scale_intervals or []),
            key=lambda row: (-row["threshold"], str(row["grade_code"]))),
        "weights": {code: float(weight) for code, weight in weight_of.items()},
        "weight_total": float(total_weight),
        "components": rows,
        "pass_rules": facets.get("pass_rules") or {},
        "checks": checks,
        "missing": missing,
        "overall_percent": float(overall) if overall is not None else None,
        "grade_code": grade_code,
        "outcome": outcome,
        "passed": outcome == "Pass",
        "explanations": explanations,
    }


def evaluate_progression(progression, *, outcome, attendance_percent,
                         approval_roles):
    """Judge one progression rule set against the available evidence.

    ``progression`` is the pinned policy's progression facet
    (``{"target": ..., "requires": [...]}``); ``approval_roles`` are the
    roles the acting decision-maker actually holds. Every requirement is
    reported with its configured target, the observed value and whether it
    is met — never a bare pass/fail — so the decision record explains itself.
    """
    if not progression or not progression.get("requires"):
        raise ValueError(
            "This assessment policy version configures no progression rules; "
            "progression fails closed until the Course Owner defines them")
    roles = set(approval_roles or ())
    requirements = []
    reasons = []
    approval_needed = False
    for entry in progression["requires"]:
        kind = entry.get("kind")
        if kind == "assessment_pass":
            met = outcome == "Pass"
            requirements.append({"kind": kind, "target": entry.get("policy"),
                                 "actual": outcome, "met": met})
            reasons.append(
                f"Assessment pass under policy {entry.get('policy')}: "
                f"outcome {outcome} -> {'met' if met else 'not met'}")
        elif kind == "attendance":
            minimum = entry.get("minimum_percent")
            actual = attendance_percent
            met = actual is not None and _decimal(actual, "Attendance") >= _decimal(
                minimum, "Attendance minimum")
            requirements.append({
                "kind": kind, "target": minimum,
                "actual": None if actual is None else float(quantize(actual)),
                "met": bool(met)})
            reasons.append(
                f"Attendance: needs {_fmt(minimum)}%, recorded "
                + (f"{_fmt(quantize(actual))}%" if actual is not None
                   else "no attendance records")
                + f" -> {'met' if met else 'not met'}")
        elif kind == "approval":
            approval_needed = True
            held = entry.get("role") in roles
            requirements.append({"kind": kind, "target": entry.get("role"),
                                 "actual": "held" if held else "not held",
                                 "met": held})
            reasons.append(
                f"Approval by {entry.get('role')}: "
                + ("the deciding actor holds the role" if held
                   else "the deciding actor does not hold the role"))
        else:
            raise ValueError(f"Unknown progression requirement kind: {kind}")
    eligible = all(row["met"] for row in requirements) and approval_needed
    if not approval_needed:
        reasons.append(
            "No approval requirement is configured; progression requires "
            "authorized academic approval and therefore fails closed")
    return {"eligible": eligible, "requirements": requirements,
            "approval_required": approval_needed, "reasons": reasons}


def retake_state(retakes, *, attempts_made, last_attempt_on, on_date):
    """Judge whether another attempt is allowed under the retakes facet.

    ``retakes`` is ``{"max_attempts", "wait_days", "scope", "governing"}``
    from the pinned policy; an unconfigured facet refuses (fail closed).
    Dates are ISO ``YYYY-MM-DD`` strings; the caller passes the site date.
    """
    if not retakes:
        raise ValueError(
            "This assessment policy version configures no retake rules; "
            "retakes fail closed until the Course Owner defines them")
    limit = retakes.get("max_attempts")
    wait_days = int(retakes.get("wait_days") or 0)
    if limit is not None and int(attempts_made) >= int(limit):
        return {"allowed": False, "max_attempts": limit,
                "attempts_made": int(attempts_made),
                "reason": f"All {limit} permitted attempts have been used"}
    if wait_days and last_attempt_on:
        wait_until = _add_days(str(last_attempt_on), wait_days)
        if str(on_date) < wait_until:
            return {"allowed": False, "max_attempts": limit,
                    "attempts_made": int(attempts_made),
                    "wait_until": wait_until,
                    "reason": f"The configured {wait_days}-day retake wait "
                              f"ends on {wait_until}"}
    return {"allowed": True, "max_attempts": limit,
            "attempts_made": int(attempts_made),
            "governing": retakes.get("governing"),
            "scope": retakes.get("scope")}


def _add_days(date_value, days):
    import datetime
    try:
        start = datetime.date.fromisoformat(str(date_value))
    except ValueError as exc:
        raise ValueError("Retake reference date must be YYYY-MM-DD") from exc
    return (start + datetime.timedelta(days=int(days))).isoformat()


# --- Academic retake policy (Owner addendum 2026-10-28, mission policy) ---
# The retakes facet is Owner-configured, but the mission policy bounds it
# from both sides and never relaxes it: at most ONE retake (two attempts in
# total) and at least SEVEN days after the original publication, whatever
# the facet says. A facet that is stricter still governs.
MISSION_MIN_WAIT_DAYS = 7
MISSION_MAX_TOTAL_ATTEMPTS = 2


def effective_retake_rules(retakes):
    """The facet's retake rules bounded by the mission policy (never relaxed)."""
    if not retakes:
        raise ValueError(
            "This assessment policy version configures no retake rules; "
            "retakes fail closed until the Course Owner defines them")
    limit = retakes.get("max_attempts")
    wait = int(retakes.get("wait_days") or 0)
    return {
        "max_attempts": (MISSION_MAX_TOTAL_ATTEMPTS if limit is None
                         else min(int(limit), MISSION_MAX_TOTAL_ATTEMPTS)),
        "wait_days": max(wait, MISSION_MIN_WAIT_DAYS),
        "scope": retakes.get("scope"),
        "governing": retakes.get("governing"),
    }


def wait_until_for_retake(wait_days, published_on):
    """First date a retake may start, under the mission's 7-day floor."""
    return _add_days(str(published_on)[:10], max(int(wait_days or 0),
                                                 MISSION_MIN_WAIT_DAYS))


def retake_gate(retakes, *, outcome, attempts_made, last_attempt_on, on_date,
                prior_retake=False, retake_exists=False):
    """The full retake authorization check for one judged result.

    ``retake_state`` alone checks only the facet's count and wait; this gate
    additionally enforces the mission policy: the judged result must be a
    Fail (initial failure only), no retake may already have been approved
    for this attempt, and no retake attempt may already exist. The wait
    and count themselves use the mission-bounded rules from
    ``effective_retake_rules``.
    """
    if not retakes:
        raise ValueError(
            "This assessment policy version configures no retake rules; "
            "retakes fail closed until the Course Owner defines them")
    if outcome != "Fail":
        return {"allowed": False, "max_attempts": retakes.get("max_attempts"),
                "attempts_made": int(attempts_made),
                "reason": "Retakes are only permitted after a failed attempt; "
                          f"this result is {outcome}"}
    if prior_retake:
        return {"allowed": False, "max_attempts": retakes.get("max_attempts"),
                "attempts_made": int(attempts_made),
                "reason": "A retake has already been approved for this attempt"}
    if retake_exists:
        return {"allowed": False, "max_attempts": retakes.get("max_attempts"),
                "attempts_made": int(attempts_made),
                "reason": "A retake attempt already exists for this student and level"}
    effective = effective_retake_rules(retakes)
    state = retake_state(effective, attempts_made=attempts_made,
                         last_attempt_on=last_attempt_on, on_date=on_date)
    if not state["allowed"]:
        return state
    return dict(state, effective_max_attempts=effective["max_attempts"],
                effective_wait_days=effective["wait_days"])


def _attempt_field(row, field):
    if isinstance(row, dict):
        return row.get(field)
    getter = getattr(row, "get", None)
    if callable(getter):
        return getter(field)
    return getattr(row, field, None)


def select_best_attempt(attempts):
    """The best VALID published attempt, as a read-time selection.

    Valid means: status Published (never Superseded, draft or cancelled)
    with a finite overall percentage. Best means the highest overall
    percentage; ties go to the earliest published attempt, then the lowest
    attempt ordinal, then the name, so the choice is deterministic. This
    never modifies any result row: it only selects among them. The
    "highest overall percent" rule is the mission's reading of the
    governing facet's "best"; see the handover for the Owner confirmation
    still needed (a higher-percent Fail can beat a lower-percent Pass on
    percent alone, and progression eligibility still requires a Pass).
    """
    candidates = []
    for row in attempts or []:
        if _attempt_field(row, "status") != "Published":
            continue
        try:
            percent = _decimal(_attempt_field(row, "overall_percent"),
                               "Overall percent")
        except (ValueError, TypeError):
            continue
        candidates.append((percent, row))
    if not candidates:
        return None
    def sort_key(item):
        percent, row = item
        published = str(_attempt_field(row, "published_on") or "")
        try:
            attempt = int(_attempt_field(row, "attempt") or 0)
        except (ValueError, TypeError):
            attempt = 0
        return (-percent, published, attempt, str(_attempt_field(row, "name") or ""))
    candidates.sort(key=sort_key)
    return candidates[0][1]


def snapshot_digest(snapshot):
    """The audit fingerprint of a calculation snapshot (canonical bytes)."""
    return digest(snapshot)


def snapshot_json(snapshot):
    return canonical(snapshot)

"""Frappe-free validation for Course Owner native grading scales.

The native Education Grading Scale contains one interval per minimum
percentage. A new immutable submitted scale is created for every approved
version; previous scales and their historical assessment links are retained.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import re

_CODE = re.compile(r"[A-Z][A-Z0-9-]{0,11}")

# The approved 60% pass threshold applies ONLY to formal graded programs.
# Specialist programs (Special Speaking, TOEFL Preparation) are progress +
# teacher feedback only, with no automatic pass/fail or promotion, so
# their scales must not be forced to carry a 60 threshold. Scope is
# explicit at creation and defaults to formal: any caller that does not
# name a scope is treated as a formal graded program and stays
# fail-closed on the 60% rule. Scope is a technical enum only -- program
# names are Owner data (see the preset) and are never hard-coded here.
FORMAL_SCOPE = "formal"
SPECIALIST_SCOPE = "specialist"


def canonical_grading_scope(scope):
    """Map a scope name to ``"formal"`` or ``"specialist"``.

    Accepts ``"formal"`` / ``"specialist"`` (case-insensitive, surrounding
    whitespace ignored). Anything else -- including ``None``, an empty
    string, or an unknown word -- is refused fail-closed instead of
    guessing a scope.
    """
    if not isinstance(scope, str):
        raise ValueError(
            "Grading scale scope must be 'formal' or 'specialist'")
    clean = scope.strip().lower()
    if clean in (FORMAL_SCOPE, SPECIALIST_SCOPE):
        return clean
    raise ValueError(
        f"Unknown grading scale scope {scope!r}: use 'formal' or 'specialist'")


def normalize_intervals(value, scope="formal"):
    """Return validated native Grading Scale Interval rows, descending.

    The approved 60% pass threshold is required only for formal graded
    programs (the default scope). Specialist-program scales (Special
    Speaking, TOEFL Preparation) are exempt from the 60 requirement: they
    record progress only and must never imply a pass/fail boundary. The
    zero threshold is still required for every scope -- native Education
    requires a grade at threshold zero.
    """
    canonical_scope = canonical_grading_scope(scope)
    if isinstance(value, str):
        if len(value) > 8192:
            raise ValueError("Grading interval payload is too large")
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("Grading intervals must be a JSON list") from exc
    if not isinstance(value, list) or not 2 <= len(value) <= 12:
        raise ValueError("A grading scale needs two to twelve intervals")

    rows, codes, thresholds = [], set(), set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"grade_code", "threshold"}:
            raise ValueError("Every interval needs only grade_code and threshold")
        code = item["grade_code"]
        if not isinstance(code, str) or not _CODE.fullmatch(code):
            raise ValueError("Grade codes must be short uppercase identifiers")
        if code in codes:
            raise ValueError("Duplicate grade code")
        codes.add(code)
        raw = item["threshold"]
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str, Decimal)):
            raise ValueError("Grade threshold must be numeric")
        try:
            percent = Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("Grade threshold must be numeric") from exc
        if (not percent.is_finite() or not Decimal("0") <= percent <= Decimal("100")
                or percent != percent.to_integral_value()):
            raise ValueError("Native grade threshold must be a whole percent from 0 to 100")
        if percent in thresholds:
            raise ValueError("Duplicate grade threshold")
        thresholds.add(percent)
        rows.append({"grade_code": code, "threshold": float(percent)})
    if Decimal("0") not in thresholds:
        raise ValueError("Native Education requires a grade at threshold zero")
    if canonical_scope == FORMAL_SCOPE and Decimal("60") not in thresholds:
        raise ValueError(
            "A formal grading scale requires the approved 60% pass "
            "threshold: no formal scale may be created without a grade at "
            "exactly 60")
    return sorted(rows, key=lambda row: (-row["threshold"], row["grade_code"]))


def assert_grading_scale_scope_link(description, expected_scope):
    """Guard the policy->native-scale boundary against scope confusion.

    The Course Owner creation command stamps the scope in the submitted
    native scale's description. A legacy unmarked native scale may remain
    linked to a formal policy for backward compatibility, but unmarked
    scales cannot become specialist progress scales: there is no evidence
    that they were created without pass/fail semantics.

    This check is *scope* validation, not a substitute for submission
    and native interval/grade-code checks elsewhere.
    """
    expected = canonical_grading_scope(expected_scope)
    if description is None:
        description = ""
    if not isinstance(description, str):
        raise ValueError("Grading scale scope evidence must be text")
    marker = re.match(
        r"^Owner-approved scale \((formal|specialist) scope\)\.",
        description,
    )
    if marker is None:
        if description.startswith("Owner-approved scale ("):
            raise ValueError("Grading scale has an invalid Owner scope marker")
        if expected == SPECIALIST_SCOPE:
            raise ValueError(
                "A specialist progress policy requires an explicitly "
                "Owner-approved specialist grading scale; an unmarked "
                "legacy scale cannot establish that scope")
        return FORMAL_SCOPE  # Legacy native scale; formal policy only.
    actual = marker.group(1)
    if actual != expected:
        raise ValueError(
            f"Grading scale scope {actual!r} conflicts with the "
            f"assessment program scope {expected!r}")
    return actual

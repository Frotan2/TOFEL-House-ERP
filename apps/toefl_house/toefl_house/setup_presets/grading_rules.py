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


def normalize_intervals(value):
    """Return validated native Grading Scale Interval rows, descending."""
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
    return sorted(rows, key=lambda row: (-row["threshold"], row["grade_code"]))

#!/usr/bin/env python3
"""Read-only audit of stored HTML-capable values (GHSA-VHRC residual 1).

Rows saved before the Education/containment fixes may still hold markup that the
containment hook would now change. This script only reads. It issues SELECT statements
and never writes, commits, or deletes. It prints counts and record names, never the
stored content, because that content may be private.

Classification reuses the containment module's own decision (`contain_value`):
  - a row is "would_change" when containment would store a different value;
  - a row is "json_shaped" when it takes Frappe's JSON short-circuit (the exposure path);
  - rows with a `javascript:` scheme or an inline `on<event>=` handler are counted
    separately, whatever their shape.

Run inside the bench (read-only session):
    cd <bench>/sites && <bench>/env/bin/python <repo>/tools/foundation/audit_stored_html.py <site>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/foundation_security"))

from foundation_security.html_containment import HTML_FIELDTYPES, contain_value  # noqa: E402

FIELDNAME = re.compile(r"[a-z0-9_]{1,140}\Z")
DOCTYPE = re.compile(r"[A-Za-z0-9 ]{1,140}\Z")
JAVASCRIPT_SCHEME = re.compile(r"javascript\s*:", re.IGNORECASE)
INLINE_HANDLER = re.compile(r"[\s\"';/]on[a-z]{2,20}\s*=", re.IGNORECASE)


def classify_rows(rows, *, sanitize, is_json_fn, linkify: bool) -> dict:
    """Pure classifier over (record_name, stored_value) pairs. Returns counts and names only."""
    counts = Counter()
    names = {"would_change": [], "json_shaped": [], "scheme_or_handler": []}
    for name, value in rows:
        counts["scanned"] += 1
        if not isinstance(value, str) or not value:
            continue
        if JAVASCRIPT_SCHEME.search(value) or INLINE_HANDLER.search(value):
            counts["scheme_or_handler"] += 1
            names["scheme_or_handler"].append(name)
        if is_json_fn(value):
            counts["json_shaped"] += 1
            names["json_shaped"].append(name)
        contained = contain_value(value, linkify=linkify, sanitize=sanitize, is_json_fn=is_json_fn)
        if contained != value:
            counts["would_change"] += 1
            names["would_change"].append(name)
    return {"counts": dict(counts), "record_names": {k: sorted(set(v)) for k, v in names.items()}}


def _field_rows(frappe):
    """Yield (table_doctype, fieldname, fieldtype, ignore_xss_filter) for every HTML-capable field.

    Covers standard fields (DocField) and site-level Custom Fields (Custom Field, keyed by `dt`).
    """
    html_types = sorted(HTML_FIELDTYPES)
    for row in frappe.get_all("DocField", filters={"fieldtype": ["in", html_types]},
                              fields=["parent", "fieldname", "fieldtype", "ignore_xss_filter"]):
        yield row.parent, row.fieldname, row.fieldtype, row.ignore_xss_filter
    for row in frappe.get_all("Custom Field", filters={"fieldtype": ["in", html_types]},
                              fields=["dt", "fieldname", "fieldtype", "ignore_xss_filter"]):
        yield row.dt, row.fieldname, row.fieldtype, row.ignore_xss_filter


def audit_site(frappe, sanitize, is_json_fn) -> dict:
    """Walk HTML-capable fields of every table doctype. SELECT only, no LIKE pre-filter.

    A pre-filter on literal "<" would miss JSON-escaped markup (for example \\u003c), so every
    non-empty value is classified. ignore_xss_filter fields are scanned and flagged, not skipped:
    Frappe does not sanitize them, so they are the highest-risk rows.
    """
    report = {"fields": [], "skipped": []}
    seen = set()
    for parent, fieldname, fieldtype, ignore_xss in _field_rows(frappe):
        key = (parent, fieldname)
        if key in seen:
            continue
        seen.add(key)
        if not DOCTYPE.fullmatch(parent or "") or not FIELDNAME.fullmatch(fieldname or ""):
            report["skipped"].append({"doctype": parent, "fieldname": fieldname, "reason": "unsafe identifier"})
            continue
        table = "tab" + parent
        try:
            rows = frappe.db.sql(
                f"select name, `{fieldname}` from `{table}` where `{fieldname}` is not null and `{fieldname}` != ''")
        except Exception:
            report["skipped"].append({"doctype": parent, "fieldname": fieldname, "reason": "table not readable"})
            continue
        result = classify_rows(rows, sanitize=sanitize, is_json_fn=is_json_fn,
                               linkify=fieldtype == "Text Editor")
        report["fields"].append({"doctype": parent, "fieldname": fieldname, "fieldtype": fieldtype,
                                 "ignore_xss_filter": bool(ignore_xss), **result})
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("site")
    args = parser.parse_args(argv)
    import frappe
    from frappe.utils.html_utils import is_json, sanitize_html

    frappe.init(site=args.site)
    frappe.connect()
    try:
        report = audit_site(frappe, sanitize_html, is_json)
    finally:
        frappe.destroy()
    totals = Counter()
    for item in report["fields"]:
        totals.update(item["counts"])
    print(json.dumps({"site": args.site, "totals": dict(totals), "fields": report["fields"],
                      "skipped": report["skipped"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Schema ledger for the role-desk fidelity guard (D2-class recurrence prevention).

The desk projections read NATIVE authorities pinned at exact upstream
revisions (frappe 988e54f3c4c2, education 93bc70757533, erpnext 4048fb70…).
A projected field, filter key or order-by column that the pinned doctype does
not have compiles, passes every stubbed test (the stub world is a dict that
answers anything), and then throws Unknown-column on a real MariaDB — the
defect the 2026-09-18 desk audit found in five of six desks (Student Group
.active, Payment Entry .currency, Student Applicant .applicant_name).

This module freezes what the pinned schema actually contains so tests can
refuse schema fiction structurally:

- ``real_fields(doctype)`` — the full set of columns a desk may legally use
  for a doctype: pinned native fields (pinned_schema.json) or the repository's
  own TH doctype JSON, always unioned with the standard Frappe columns and
  our Custom Fields (fixtures/custom_field.json).
- ``is_pinned_native(doctype)`` — membership in the frozen native ledger.

When the hosted bench pins a new upstream revision, regenerate
pinned_schema.json from the pinned doctype JSONs — a stale ledger fails
closed (desk columns "disappear"), which is the desired direction of drift.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
LEDGER_PATH = Path(__file__).with_name("pinned_schema.json")

_LEDGER = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
_NATIVE = {dt: set(row["fields"]) for dt, row in _LEDGER["doctypes"].items()}
_STANDARD = set(_LEDGER["standard_frappe_columns"])

def _custom_fields():
    path = APP / "fixtures" / "custom_field.json"
    out = {}
    if path.exists():
        for row in json.loads(path.read_text(encoding="utf-8")):
            out.setdefault(row["dt"], set()).add(row["fieldname"])
    return out

_CUSTOM = _custom_fields()


def _repo_th_fields(doctype):
    slug = doctype.lower().replace(" ", "_")
    for path in APP.glob(f"*/doctype/{slug}/{slug}.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("name") == doctype:
            return {field["fieldname"] for field in doc.get("fields", [])}
    return None


def is_pinned_native(doctype):
    return doctype in _NATIVE


def real_fields(doctype):
    """All columns a desk may legally reference for this doctype, or None
    when the schema is unknown (callers must fail closed on None)."""
    if doctype in _NATIVE:
        fields = set(_NATIVE[doctype])
    else:
        fields = _repo_th_fields(doctype)
        if fields is None:
            return None
    fields |= _STANDARD
    fields |= _CUSTOM.get(doctype, set())
    return fields

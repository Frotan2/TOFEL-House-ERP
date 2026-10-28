"""Real-site stored-HTML check (GHSA-VHRC-hgrq-x75r residual 1 tooling), synthetic rows only.

Runs inside the bench on the disposable CI site (placement-test.localhost). Uses the real
Frappe `Note.content` Text Editor field, the real containment `validate` hook wired by
foundation_security/hooks.py, the real pinned sanitize_html and is_json, and a real MariaDB.

Checks:
  1. Save path: a JSON-wrapped onerror payload inserted through the real document lifecycle
     is stored inert, and stays inert when reopened from the database.
  2. Legitimate formatting inserted through the same path is stored unchanged.
  3. Pre-upgrade simulation: a hostile row written with raw SQL (which bypasses validate) is
     classified would_change by the read-only audit; the save-path row is not.
  4. A non-JSON javascript: href written raw is counted as scheme_or_handler, not would_change,
     because Frappe's own sanitizer handles non-JSON values on save.
  5. The audit is read-only: a full snapshot of tabNote is identical before and after it runs.
  6. The printed summary contains counts and record names only, never stored content.

Writes are rolled back at the end. Runs only on the disposable CI site, never a production
site. This is a CI-only qualification check, not owner evidence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/foundation_security"))
sys.path.insert(0, str(ROOT / "tools/foundation"))

import frappe  # noqa: E402
from frappe.utils.html_utils import is_json, sanitize_html  # noqa: E402

import audit_stored_html as audit  # noqa: E402

SITE = "placement-test.localhost"

# Raw stored forms. Each is checked for activity before use (2026-10-16 real-sanitizer rule).
JSON_HANDLER = '"<img src=x onerror=alert(1)>"'
JS_HREF = '<p><a href="javascript:alert(1)">SYNTHETIC link</a></p>'
LEGIT = "<p>SYNTHETIC <strong>formatted</strong> text</p>"


def _snapshot():
    return frappe.db.sql("select name, content from `tabNote` order by name")


def main() -> int:
    frappe.init(site=SITE, sites_path=str(Path.cwd()))
    frappe.connect()
    frappe.set_user("Administrator")
    try:
        # Raw-form activity precondition: the hostile forms must really be dangerous as stored.
        assert is_json(JSON_HANDLER), "precondition: JSON-wrapped payload must take the JSON path"
        assert "onerror=" in JSON_HANDLER and "javascript:" in JS_HREF

        def new_note(content, title):
            doc = frappe.get_doc({"doctype": "Note", "title": title, "content": content})
            doc.insert(ignore_permissions=True)
            return doc.name

        # 1 and 2: save path through the real lifecycle.
        saved_hostile = new_note(JSON_HANDLER, "SYNTHETIC stored-html save path")
        saved_legit = new_note(LEGIT, "SYNTHETIC stored-html legit")
        stored_hostile = frappe.db.get_value("Note", saved_hostile, "content")
        stored_legit = frappe.db.get_value("Note", saved_legit, "content")
        assert "onerror" not in (stored_hostile or "").lower(), "save path left an active handler"
        assert "alert(1)" not in (stored_hostile or ""), "save path left the payload body"
        assert stored_legit == LEGIT, f"legitimate formatting changed on save: {stored_legit!r}"
        reopened = frappe.get_doc("Note", saved_hostile)
        assert "onerror" not in (reopened.content or "").lower(), "reopened row is active"

        # 3 and 4: pre-upgrade simulation via raw SQL, which bypasses validate.
        pre_upgrade_json = new_note(LEGIT, "SYNTHETIC stored-html pre-upgrade json")
        pre_upgrade_href = new_note(LEGIT, "SYNTHETIC stored-html pre-upgrade href")
        frappe.db.sql("update `tabNote` set `content`=%s where name=%s", (JSON_HANDLER, pre_upgrade_json))
        frappe.db.sql("update `tabNote` set `content`=%s where name=%s", (JS_HREF, pre_upgrade_href))
        assert frappe.db.get_value("Note", pre_upgrade_json, "content") == JSON_HANDLER

        # 5: read-only proof.
        before = _snapshot()
        report = audit.audit_site(frappe, sanitize_html, is_json)
        after = _snapshot()
        assert before == after, "the audit changed tabNote rows"

        note_field = [f for f in report["fields"] if f["doctype"] == "Note" and f["fieldname"] == "content"]
        assert len(note_field) == 1, "Note.content was not in the audit scope"
        field = note_field[0]
        assert field["ignore_xss_filter"] is False
        names = field["record_names"]
        assert pre_upgrade_json in names["would_change"], "pre-upgrade JSON row not flagged"
        assert saved_hostile not in names["would_change"], "save-path row still flagged"
        assert saved_legit not in names["would_change"], "legitimate row flagged"
        assert pre_upgrade_href in names["scheme_or_handler"], "javascript: href not counted"
        assert pre_upgrade_href not in names["would_change"], "non-JSON href wrongly classed would_change"

        # 6: output discipline. Print counts and names only; assert no payload text leaks.
        summary = {
            "site": SITE,
            "note_content_counts": field["counts"],
            "note_content_record_count_by_kind": {k: len(v) for k, v in names.items()},
            "save_path_checks": "passed",
            "read_only_snapshot_identical": True,
        }
        rendered = json.dumps(summary, sort_keys=True)
        for forbidden in ("onerror", "javascript:", "alert(1)", "SYNTHETIC"):
            assert forbidden not in rendered, f"summary leaked {forbidden!r}"
        print(rendered)
        return 0
    finally:
        # Nothing in this check is committed. Roll back every synthetic write.
        frappe.db.rollback()
        frappe.destroy()


if __name__ == "__main__":
    raise SystemExit(main())

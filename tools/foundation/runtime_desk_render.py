"""Desk rendering fixture for the Foundation runtime (2026-10-18). Synthetic data only.

Creates one dedicated HR System User and one real HRMS record (Job Opening Template.description, a
Text Editor field) whose stored value is built from hostile payloads plus one legitimate
formatting element. The record is written through the server insert path, then read back from the
database and checked for executable markup before the browser step opens it.

The browser step (desk_render_check.mjs) then logs in as that user and renders the Desk form.
This fixture never touches an existing user's roles or password. Its only new User row is the
dedicated HR user; Frappe's throttle_user_creation counts new User rows per hour, so the
fixture creates exactly one.

Usage (from the bench sites directory): FOUNDATION_DESK_FIXTURE=<path> python runtime_desk_render.py <site>
"""
import json
import os
from pathlib import Path
import secrets
import sys

import frappe

USER = "validation-hr-render@example.test"
DOCTYPE = "Job Opening Template"
# Each payload is inert only after the containment hook and Frappe's sanitizer have run.
# The flag stays undefined unless a handler executes in the browser.
PAYLOAD = (
    '<p>SYNTHETIC <strong>formatted</strong> text</p>'
    '<img src=x onerror="window.__synthetic_pwned=1">'
    '<p><a href="javascript:window.__synthetic_pwned=2">SYNTHETIC link</a></p>'
    '<svg onload="window.__synthetic_pwned=3"></svg>'
    '<iframe srcdoc="&lt;script&gt;window.__synthetic_pwned=4&lt;/script&gt;"></iframe>'
)
MARKERS = ("onerror", "onload", "javascript:", "<script", "srcdoc", "<iframe")


def ensure_user(password: str) -> None:
    if frappe.db.exists("User", USER):
        return
    frappe.get_doc(
        {
            "doctype": "User",
            "email": USER,
            "first_name": "Validation HR render",
            "user_type": "System User",
            "enabled": 1,
            "send_welcome_email": 0,
            "new_password": password,
            "roles": [{"role": "HR User"}],
        }
    ).insert(ignore_permissions=True)


def main() -> int:
    site = sys.argv[1]
    output = Path(os.environ["FOUNDATION_DESK_FIXTURE"])
    password = os.environ["FOUNDATION_TEST_PASSWORD"]
    frappe.init(site=site, sites_path=os.getcwd())
    frappe.connect()
    frappe.set_user("Administrator")
    try:
        ensure_user(password)
        title = "SYN-DESK-RENDER-" + secrets.token_hex(4)
        doc = frappe.get_doc({"doctype": DOCTYPE, "template_title": title, "description": PAYLOAD})
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        stored = frappe.db.get_value(DOCTYPE, doc.name, "description") or ""
        low = stored.lower()
        leaked = [marker for marker in MARKERS if marker in low]
        if leaked:
            raise SystemExit(f"stored value still carries executable markup: {leaked}")
        if "<strong>formatted</strong>" not in stored:
            raise SystemExit("legitimate formatting was not stored")
        output.write_text(
            json.dumps({"site": site, "user": USER, "name": doc.name, "stored_markers": 0}, indent=2) + "\n",
            encoding="utf-8",
        )
        print("desk render fixture written: stored value inert, legitimate formatting kept")
        return 0
    finally:
        frappe.destroy()


if __name__ == "__main__":
    raise SystemExit(main())

"""Save-time guard: one Office 365 identity may be linked to at most one User (2026-10-18).

Login (social_login.login_via_office365) already denies when more than one User holds the
same signed subject. This guard closes the write side: a User cannot be saved with an
office_365 `userid` that another User already holds, and a single User cannot list the same
identity twice. Matching uses the same database lookup as login, so the collation rules are
identical on both paths.

Blank `userid` rows are ignored: a signed `sub` is never blank, so such a row cannot match
at login and cannot attach an identity.
"""

import frappe

PROVIDER = "office_365"
LINK_DOCTYPE = "User Social Login"


def validate_office365_links(doc, method=None):
    seen = set()
    for row in doc.get("social_logins") or []:
        if (row.get("provider") or "") != PROVIDER:
            continue
        userid = (row.get("userid") or "").strip()
        if not userid:
            continue

        # Duplicate rows inside this same User: compare case-insensitively, the stricter form.
        key = userid.casefold()
        if key in seen:
            frappe.throw(
                frappe._("This Office 365 identity is listed more than once on this user."),
                frappe.ValidationError,
            )
        seen.add(key)

        # Any other User already holding this identity. A new, unsaved User has no
        # rows in the database, so the exclusion is applied only when a name exists.
        filters = {"provider": PROVIDER, "userid": userid}
        if doc.name:
            filters["parent"] = ["!=", doc.name]
        holders = frappe.get_all(LINK_DOCTYPE, filters=filters, fields=["parent"], limit_page_length=1)
        if holders:
            frappe.throw(
                frappe._("This Office 365 identity is already linked to another user. Contact the Course Owner."),
                frappe.ValidationError,
            )

"""Enforce native Company User Permission for guarded Finance writes.

Finance commands insert submitted ERPNext/Education documents with
ignore_permissions because their role gate is an audited operation rather
than direct stock/account CRUD. That must never bypass a *native* Company
User Permission on the acting Finance Officer. Unrestricted HQ officers
have no Company User Permission; a scoped officer may act only in the
explicitly allowed company, matching the read-only cashier scope.

This is an additive Company boundary, not a substitute for student/branch
identity, document, or native accounting validation.
"""
import frappe


def require_finance_company(company):
    """Return authorized Company or refuse before any native money write."""
    if not isinstance(company, str) or not company.strip() or len(company) > 140:
        raise frappe.ValidationError("A valid accounting company is required")
    if not frappe.db.exists("Company", company):
        raise frappe.ValidationError("Unknown accounting company")
    actor = frappe.session.user
    if not actor or actor in ("Guest", "Administrator"):
        raise frappe.PermissionError("An authorized Finance Officer is required")
    rows = frappe.get_all(
        "User Permission",
        filters={"user": actor, "allow": "Company"},
        pluck="for_value",
        limit_page_length=100,
    )
    if rows:
        allowed = {
            row.get("for_value") if isinstance(row, dict) else row
            for row in rows
        }
        if company not in allowed:
            raise frappe.PermissionError(
                "This login has no finance authority for the selected company")
    return company

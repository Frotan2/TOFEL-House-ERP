"""Fail-closed governance/control-centre surface.

This module is a controlled interface over native Frappe/ERPNext administrative
records. It deliberately does not create a second role, branch, accounting,
student, payroll, monitoring, or audit authority.
"""
import json

import frappe
from toefl_house.policy import validate_request_key

CONTROL_ROLES = {"Course Owner", "General Manager"}
MANAGED_ROLES = {
    "General Manager", "Academic Manager", "Finance Manager", "Reception",
    "Placement Author", "Placement Publisher", "Placement Auditor",
    "Placement Invigilator", "Placement Assessor", "Placement Reviewer",
    "Placement Releaser", "Admission Officer", "Admission Reviewer",
    "Admission Approver", "Admission Auditor", "Enrollment Officer",
    "Enrollment Auditor", "Teaching Scheduler", "Attendance Recorder",
    "Teaching Auditor", "Finance Officer", "Finance Auditor",
}
PROTECTED_USERS = {"Administrator", "Guest"}


def _require_control_role():
    roles = set(frappe.get_roles(frappe.session.user))
    if not roles.intersection(CONTROL_ROLES):
        raise frappe.PermissionError("Course Owner or General Manager role required")
    # S3: a disabled login holds no authority even with the role still
    # attached (same rule the desk audience gate enforces).
    if not frappe.db.get_value("User", frappe.session.user, "enabled"):
        raise frappe.PermissionError("This account has been disabled.")
    return roles


@frappe.whitelist(methods=["GET", "POST"])
def get_control_center_snapshot():
    """Return a non-sensitive readiness/attention projection for the Desk page."""
    roles = _require_control_role()
    return {
        "viewer_roles": sorted(roles.intersection(CONTROL_ROLES)),
        "managed_roles": sorted(MANAGED_ROLES),
        "production_state": "REJECT",
        "synthetic_only_guard": "REQUIRED",
        "deployment_phase": "LOCAL_SERVER_TAILSCALE",
        "operational_attention": [
            {
                "id": "dependency-security",
                "state": "UPSTREAM-BLOCKED / REJECT",
                "detail": "SEC-DEPS-01 remains a hard production stop.",
            },
            {
                "id": "d8-evidence",
                "state": "BLOCKED",
                "detail": "Selected deployment, backup/recovery, branch-isolation, monitoring, capacity, and rollback evidence is not yet proven.",
            },
            {
                "id": "future-hosting",
                "state": "NOT_SELECTED",
                "detail": "Future internet-hosted provider, hostname, DNS, and public edge are intentionally not selected.",
            },
            {
                "id": "deferred-scope",
                "state": "DEFERRED",
                "detail": "Student/guardian portal and online payment gateway are not launch scope.",
            },
        ],
        "native_authorities": [
            "User and Role for identity and role administration",
            "User Permission plus native Company/Branch for branch scope",
            "ERPNext/Education native masters and lifecycle documents",
            "HRMS native employee and payroll documents",
        ],
        "control_routes": [
            {"label": "Users", "route": ["List", "User"]},
            {"label": "Roles", "route": ["List", "Role"]},
            {"label": "User Permissions", "route": ["List", "User Permission"]},
            {"label": "Companies", "route": ["List", "Company"]},
            {"label": "Branches", "route": ["List", "Branch"]},
            {"label": "System Settings", "route": ["Form", "System Settings"]},
        ],
    }


@frappe.whitelist(methods=["POST"])
def set_managed_role(request_key, user, role, enabled):
    """Assign or revoke an allow-listed TOEFL role through native User.

    Course Owner is the only role allowed to perform this sensitive mutation.
    The protected Administrator/Guest identities and Course Owner self-role are
    not routine targets. Native Version is used for the auditable change record;
    no custom role or permission ledger is introduced.
    """
    actor_roles = set(frappe.get_roles(frappe.session.user))
    if "Course Owner" not in actor_roles:
        raise frappe.PermissionError("Course Owner role required")
    if not frappe.db.get_value("User", frappe.session.user, "enabled"):
        raise frappe.PermissionError("This account has been disabled.")
    try:
        validate_request_key(request_key)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    if not isinstance(user, str) or not user or user in PROTECTED_USERS:
        raise frappe.ValidationError("Protected or invalid User")
    if not isinstance(role, str) or role not in MANAGED_ROLES:
        raise frappe.ValidationError("Role is not managed by this controlled surface")
    if isinstance(enabled, str):
        if enabled not in {"0", "1"}:
            raise frappe.ValidationError("enabled must be 0 or 1")
        enabled = enabled == "1"
    elif isinstance(enabled, (int, bool)):
        enabled = bool(enabled)
    else:
        raise frappe.ValidationError("enabled must be boolean-like")
    if user == frappe.session.user and not enabled and role in {"General Manager", "Course Owner"}:
        raise frappe.ValidationError("The acting Course Owner cannot revoke its own operational role")

    # Lock the native User before checking the request receipt. This serializes
    # concurrent retries for the same target without introducing a second lock
    # table or operation ledger; the row lock is held through the native User
    # change and its Version audit insert.
    target = frappe.get_doc("User", user, for_update=True)
    # BUG-ADMIN-01: `_` is legal in request keys but wild in LIKE, and a bare
    # limit-1 LIKE could return a neighbor key's row instead of this key's own
    # receipt. Escape the pattern, scan every candidate, and replay only on an
    # EXACT key match; anything else (including an unreadable neighbor row) is
    # not this request's receipt.
    escaped = request_key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    candidates = frappe.get_list(
        "Version",
        filters={"ref_doctype": "User", "docname": user, "data": ["like", f"%{escaped}%"]},
        fields=["data"],
        limit_page_length=25,
        ignore_permissions=True,
    )
    recorded = None
    for candidate in candidates:
        try:
            row = json.loads(candidate["data"])
        except (TypeError, ValueError):
            continue
        if isinstance(row, dict) and row.get("request_key") == request_key:
            recorded = row
            break
    if recorded is not None:
        if recorded.get("managed_role") != role or recorded.get("enabled") != enabled:
            raise frappe.ValidationError("Idempotency key conflicts with an existing role change")
        return {
            "user": user,
            "role": role,
            "enabled": enabled,
            # Older native receipts predate the explicit field and only exist
            # for real changes, so retain their historical replay semantics.
            "changed": bool(recorded.get("changed", True)),
            "replayed": True,
            "audit_authority": "Version",
        }

    current = set(target.get_roles())
    already = (role in current) == enabled
    if not already:
        if enabled:
            target.add_roles(role)
        else:
            target.remove_roles(role)
        target.save(ignore_permissions=True)
        after = set(target.get_roles())
    else:
        after = current

    # Native Version is the audit authority. Record even a no-op so the
    # request key binds the requested operation and cannot later be reused for
    # a different role or state.
    version = frappe.get_doc({
        "doctype": "Version",
        "ref_doctype": "User",
        "docname": user,
        "data": json.dumps({
            "changed_by": frappe.session.user,
            "request_key": request_key,
            "managed_role": role,
            "enabled": enabled,
            "changed": not already,
            "before_roles": sorted(current),
            "after_roles": sorted(after),
        }, sort_keys=True),
    })
    version.insert(ignore_permissions=True)
    return {
        "user": user,
        "role": role,
        "enabled": enabled,
        "changed": not already,
        "audit_authority": "Version",
    }

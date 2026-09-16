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
    try:
        validate_request_key(request_key)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    if not isinstance(user, str) or not user or user in PROTECTED_USERS:
        raise frappe.ValidationError("Protected or invalid User")
    if role not in MANAGED_ROLES:
        raise frappe.ValidationError("Role is not managed by this controlled surface")
    if isinstance(enabled, str):
        if enabled not in {"0", "1"}:
            raise frappe.ValidationError("enabled must be 0 or 1")
        enabled = enabled == "1"
    elif isinstance(enabled, (int, bool)):
        enabled = bool(enabled)
    else:
        raise frappe.ValidationError("enabled must be boolean-like")
    if role == "General Manager" and user == frappe.session.user and not enabled:
        raise frappe.ValidationError("The acting Course Owner cannot revoke its own operational role")

    prior = frappe.get_list(
        "Version",
        filters={"ref_doctype": "User", "docname": user, "data": ["like", f"%{request_key}%"]},
        fields=["data"],
        limit_page_length=1,
        ignore_permissions=True,
    )
    if prior:
        try:
            recorded = json.loads(prior[0]["data"])
        except (TypeError, ValueError) as exc:
            raise frappe.ValidationError("Existing audit record is not valid") from exc
        if recorded.get("managed_role") != role or recorded.get("enabled") != enabled:
            raise frappe.ValidationError("Idempotency key conflicts with an existing role change")
        return {
            "user": user,
            "role": role,
            "enabled": enabled,
            "changed": True,
            "replayed": True,
            "audit_authority": "Version",
        }

    target = frappe.get_doc("User", user)
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

    # Native Version is the audit authority. The request key makes retries
    # reviewable without creating a parallel operation/role ledger.
    if not already:
        version = frappe.get_doc({
            "doctype": "Version",
            "ref_doctype": "User",
            "docname": user,
            "data": json.dumps({
                "changed_by": frappe.session.user,
                "request_key": request_key,
                "managed_role": role,
                "enabled": enabled,
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

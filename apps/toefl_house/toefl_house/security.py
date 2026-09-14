"""Deny-by-default synthetic operation guard and non-serializable command context."""
from contextlib import contextmanager
from contextvars import ContextVar
import frappe

_CONTEXT = ContextVar("toefl_house_content_command", default=None)
KIND_ROLES = {
    "create_draft": "Placement Author",
    "revise_draft": "Placement Author",
    "publish": "Placement Publisher",
    "create_blueprint": "Placement Author",
    "create_policy": "Placement Author",
    "revise_blueprint": "Placement Author",
    "revise_policy": "Placement Author",
    "review_blueprint": "Placement Publisher",
    "review_policy": "Placement Publisher",
    "publish_blueprint": "Placement Publisher",
    "publish_policy": "Placement Publisher",
    "retire_blueprint": "Placement Publisher",
    "retire_policy": "Placement Publisher",
}
KINDS = set(KIND_ROLES)
DOCTYPES = {
    "TH Placement Item Revision", "TH Placement Key Revision",
    "TH Placement Audit Event", "TH Placement Operation",
    "TH Placement Blueprint Revision", "TH Placement Policy Revision",
}
CONFIG_DOCTYPES = ("TH Placement Blueprint Revision", "TH Placement Policy Revision")


def require_synthetic():
    if (frappe.conf.get("toefl_house_synthetic_only") != 1
            or frappe.conf.get("allow_tests") != 1
            or frappe.local.site not in {"placement-test.localhost", "placement-second.localhost"}):
        raise frappe.PermissionError("Placement is disabled outside explicitly isolated synthetic test sites")


def authorize(role):
    require_synthetic()
    user = frappe.session.user
    if user in (None, "Guest", "Administrator") or role not in frappe.get_roles(user):
        raise frappe.PermissionError("An explicitly assigned non-administrator actor is required")
    if not frappe.db.get_value("User", user, "enabled"):
        raise frappe.PermissionError("Actor has been disabled")
    return user


@contextmanager
def command(kind, actor):
    if kind not in KINDS or _CONTEXT.get() is not None:
        raise frappe.PermissionError("Invalid or nested placement command")
    token = _CONTEXT.set((kind, actor))
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def require_command(doctype):
    require_synthetic()
    context = _CONTEXT.get()
    if doctype not in DOCTYPES or context is None or context[1] != frappe.session.user:
        raise frappe.PermissionError("Protected records require an authorized placement command")
    authorize(KIND_ROLES[context[0]])
    return context

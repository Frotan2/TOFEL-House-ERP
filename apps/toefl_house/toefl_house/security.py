"""Deny-by-default synthetic operation guard and non-serializable command context."""
from contextlib import contextmanager
from contextvars import ContextVar
import frappe

_CONTEXT = ContextVar("toefl_house_content_command", default=None)
KINDS = {"create_draft", "revise_draft", "publish"}
DOCTYPES = {"TH Placement Item Revision", "TH Placement Key Revision", "TH Placement Audit Event", "TH Placement Operation"}


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
    authorize("Placement Publisher" if context[0] == "publish" else "Placement Author")
    return context

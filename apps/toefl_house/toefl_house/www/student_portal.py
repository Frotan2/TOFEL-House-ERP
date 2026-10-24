"""Student portal page controller — server-side gating + context."""
import frappe
from toefl_house.operations import portal_policy


def get_context(context):
    context.no_cache = 1
    # Portal disabled ⇒ show disabled notice, no data
    if not portal_policy.is_portal_enabled("student_portal"):
        context.portal_enabled = False
        context.portal_message = (
            "Student portal is currently disabled. "
            "Contact the administration for access."
        )
        return context
    if frappe.session.user in (None, "Guest"):
        frappe.local.flags.redirect_location = "/login"
        raise frappe.Redirect
    context.portal_enabled = True
    # The page itself is static HTML/JS; data loads via whitelisted API calls
    # that re-check portal enablement and student ownership per request.
    return context

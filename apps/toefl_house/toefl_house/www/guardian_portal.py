"""Guardian portal page controller — strictly scoped + consent-gated."""
import frappe
from toefl_house.operations import portal_policy


def get_context(context):
    context.no_cache = 1
    if not portal_policy.is_portal_enabled("guardian_portal"):
        context.portal_enabled = False
        context.portal_message = (
            "Guardian portal is currently disabled. "
            "Consent and relationship verification are required for access."
        )
        return context
    if frappe.session.user in (None, "Guest"):
        frappe.local.flags.redirect_location = "/login"
        raise frappe.Redirect
    context.portal_enabled = True
    return context

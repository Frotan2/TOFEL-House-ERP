"""Keep the native wizard's first account out of operational/portal roles."""
import frappe


def setup_wizard_success(args):
    """Narrow native default roles before Frappe signs in the first user.

    Frappe/ERPNext grant broad default roles during setup, including Education
    portal identities. Those identities require canonical student/guardian
    records and must never be assigned to the installation administrator.
    Business roles are provisioned independently after setup.
    """
    if not frappe.flags.in_setup_wizard or frappe.session.user != "Administrator":
        raise frappe.PermissionError("Initial account qualification requires the native setup wizard")
    email = args.get("email")
    if not email:
        return
    if email in ("Administrator", "Guest"):
        raise frappe.PermissionError("A separate initial setup account is required")
    user = frappe.get_doc("User", email)
    if (not user.enabled or "System Manager" not in {row.role for row in user.roles}
            or user.role_profile_name
            or frappe.db.exists("Student", {"user": email})
            or frappe.db.exists("Guardian", {"user": email})):
        raise frappe.PermissionError("Initial setup account has an unexpected identity or role profile")
    user.set("roles", [{"role": "System Manager"}])
    user.save()
    frappe.clear_cache(user=email)

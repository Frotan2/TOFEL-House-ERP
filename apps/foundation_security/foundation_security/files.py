"""Deny private-file ownership exceptions that outlive parent-record access."""
import frappe


def parent_permission(doc, ptype=None, user=None, debug=False):
    user = user or frappe.session.user
    if user in (None, "Guest", "Administrator") or not ({"Student", "Guardian"} & set(frappe.get_roles(user))):
        return True  # additional deny-only hook; never replaces native File ACLs
    if not doc.is_private or not doc.attached_to_doctype or not doc.attached_to_name:
        return True
    if doc.attached_to_doctype == "File":
        return False  # no recursive File-parent authority or cycles in this profile
    required = "read" if ptype in (None, "read", "select", "print", "email") else "write"
    return bool(frappe.has_permission(doc.attached_to_doctype, doc=doc.attached_to_name,
                                      ptype=required, user=user))

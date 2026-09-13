"""Fail closed using canonical upstream identities and native permission records.

No identity cache or additional authority is introduced. Re-read native scope on
requests so deletion/expansion of a permission cannot leave old sessions unscoped.
"""
import frappe


def validate_student_scope():
    user = frappe.session.user
    if user in (None, "Guest", "Administrator") or "Student" not in frappe.get_roles(user):
        return
    if not (
        frappe.db.get_single_value("Website Settings", "disable_signup")
        and frappe.db.get_single_value("Education Settings", "user_creation_skip")
        and frappe.db.get_single_value("System Settings", "apply_strict_user_permissions")
        and frappe.db.get_single_value("System Settings", "disable_document_sharing")
        and frappe.conf.get("disable_website_cache")
    ):
        raise frappe.PermissionError("Student access requires the qualified security configuration")
    students = frappe.get_all("Student", filters={"user": user}, fields=["name", "customer"], limit_page_length=2)
    if len(students) != 1 or not students[0].customer:
        raise frappe.PermissionError("Student access requires one canonical Student and Customer")
    for allow, expected in (("Student", students[0].name), ("Customer", students[0].customer)):
        rules = frappe.get_all("User Permission", filters={"user": user, "allow": allow},
                               fields=["for_value", "apply_to_all_doctypes"])
        if len(rules) != 1 or rules[0].for_value != expected or not rules[0].apply_to_all_doctypes:
            raise frappe.PermissionError("Student access requires an exact native permission scope")
    # Existing shares can override User Permissions even after sharing is disabled.
    # Fail closed instead of silently granting access through inherited shares.
    if frappe.db.exists("DocShare", {"user": user}):
        raise frappe.PermissionError("Student document shares require security review")


def on_session_creation(login_manager=None):
    validate_student_scope()
    if frappe.session.user not in (None, "Guest"):
        from frappe.sessions import get_csrf_token
        get_csrf_token()

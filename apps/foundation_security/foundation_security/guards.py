"""Fail closed using canonical upstream identities and native permission records.

No identity cache or additional authority is introduced. Re-read native scope on
requests so deletion/expansion of a permission cannot leave old sessions unscoped.
"""
import frappe


def validate_student_scope():
    validate_guardian_scope()
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
    # Core User.share_with_self creates a share for each user's own profile.
    # Preserve that canonical self-profile grant, but reject other inherited or
    # global shares that could override the Student document boundary.
    shares = frappe.get_all("DocShare", or_filters={"user": user, "everyone": 1},
                            fields=["share_doctype", "share_name", "everyone"])
    if any(s.everyone or s.share_doctype != "User" or s.share_name != user for s in shares):
        raise frappe.PermissionError("Student document shares require security review")


def on_session_creation(login_manager=None):
    validate_student_scope()


def validate_request():
    validate_student_scope()
    if frappe.session.user in (None, "Guest") or frappe.session.sid in (None, "Guest"):
        return
    # HTTPRequest establishes the login session BEFORE its native CSRF check.
    # Minting in on_session_creation would invalidate the very login request
    # that created the session. auth_hooks runs AFTER that native validation.
    from frappe.sessions import get_csrf_token
    missing = not frappe.session.data.csrf_token
    login_request = frappe.request.path == "/api/method/login" or frappe.form_dict.get("cmd") == "login"
    if missing and frappe.request.method not in ("GET", "HEAD", "OPTIONS") and not login_request:
        # Legacy pre-extension sessions must reload rather than get one unsafe
        # write through while their token is being initialized.
        get_csrf_token()
        raise frappe.CSRFTokenError("Reload the page before changing data")
    get_csrf_token()


def validate_guardian_scope():
    """Canonical native Guardian membership, including multiple children; no cache."""
    user = frappe.session.user
    if user in (None, "Guest", "Administrator") or "Guardian" not in frappe.get_roles(user):
        return
    if not (frappe.db.get_single_value("Website Settings", "disable_signup")
            and frappe.db.get_single_value("Education Settings", "user_creation_skip")
            and frappe.db.get_single_value("System Settings", "apply_strict_user_permissions")
            and frappe.db.get_single_value("System Settings", "disable_document_sharing")
            and frappe.conf.get("disable_website_cache")):
        raise frappe.PermissionError("Guardian requires qualified security settings")
    guardians = frappe.get_all("Guardian", filters={"user": user}, fields=["name"], limit_page_length=2)
    if len(guardians) != 1:
        raise frappe.PermissionError("Guardian requires one canonical identity")
    links = frappe.get_all("Student Guardian", filters={"guardian": guardians[0].name,
        "parenttype":"Student", "parentfield":"guardians"}, pluck="parent")
    if not links:
        raise frappe.PermissionError("Guardian requires canonical child membership")
    students = frappe.get_all("Student", filters={"name":["in", list(set(links))]}, fields=["name", "customer"])
    if len(students) != len(set(links)) or any(not s.customer for s in students):
        raise frappe.PermissionError("Guardian child/customer scope is incomplete")
    expected = {"Guardian":{guardians[0].name}, "Student":{s.name for s in students},
                "Customer":{s.customer for s in students}}
    for allow, values in expected.items():
        rules = frappe.get_all("User Permission", filters={"user":user,"allow":allow},
                               fields=["for_value","apply_to_all_doctypes"])
        if len(rules) != len(values) or {r.for_value for r in rules} != values or any(not r.apply_to_all_doctypes for r in rules):
            raise frappe.PermissionError("Guardian requires exact native permission scopes")
    shares = frappe.get_all("DocShare", or_filters={"user":user,"everyone":1},
                            fields=["share_doctype","share_name","everyone"])
    if any(s.everyone or s.share_doctype != "User" or s.share_name != user for s in shares):
        raise frappe.PermissionError("Guardian document shares require security review")

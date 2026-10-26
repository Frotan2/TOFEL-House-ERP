"""Route authenticated staff to their role desk without granting permissions."""
import frappe

from toefl_house.security import KIND_ROLES


ROLE_DESKS = (
    ("Course Owner", "th-owner-cockpit"),
    ("General Manager", "th-operations-desk"),
    ("Finance Manager", "th-finance-desk"),
    ("Academic Manager", "th-academic-desk"),
    ("Reception", "th-reception-desk"),
    ("Instructor", "th-teacher-desk"),
)


def staff_home_page(user=None):
    user = user or frappe.session.user
    if not user or user in {"Guest", "Administrator"}:
        return None
    if not frappe.is_setup_complete():
        return None
    identity = frappe.get_cached_value("User", user, ["enabled", "user_type"], as_dict=True)
    if not identity or not identity.enabled or identity.user_type != "System User":
        return None
    roles = set(frappe.get_roles(user))
    for role, page in ROLE_DESKS:
        if role in roles:
            return "desk/" + page
    if roles.intersection(KIND_ROLES.values()):
        return "desk/th-command-centre"
    return None


def on_login(login_manager):
    # Native login otherwise selects the generic ERP workspace. A request-local
    # home also takes precedence over a stale generic default-workspace choice;
    # no User preference, role or module permission is rewritten.
    home = staff_home_page(login_manager.user)
    if home:
        frappe.local.flags.home_page = home


def boot_session(bootinfo):
    home = staff_home_page()
    if home:
        bootinfo["home_page"] = home.rsplit("/", 1)[-1]


def after_request(response, request):
    # Native logout preserves /desk as redirect-to. Also cover existing root
    # bookmarks without overriding explicit deep links or changing API replies.
    if (request.method not in {"GET", "HEAD"}
            or request.path not in {"/desk", "/desk/", "/app", "/app/"}
            or response.status_code != 200):
        return
    home = staff_home_page()
    if home:
        response.status_code = 302
        response.headers["Location"] = "/" + home
        response.headers["Cache-Control"] = "no-store, private"
        response.set_data(b"")

"""Fresh staff login must not depend on a manual route to the correct desk."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class StaffNavigationTests(unittest.TestCase):
    def setUp(self):
        self.roles = ["Reception", "Admission Officer", "Desk User"]
        self.identity = types.SimpleNamespace(enabled=1, user_type="System User")
        self.frappe = types.ModuleType("frappe")
        self.frappe.session = types.SimpleNamespace(user="staff@example.test")
        self.frappe.local = types.SimpleNamespace(flags=types.SimpleNamespace())
        self.frappe.get_cached_value = Mock(side_effect=lambda *a, **kw: self.identity)
        self.frappe.get_roles = Mock(side_effect=lambda *a: self.roles)
        self.frappe.is_setup_complete = Mock(return_value=True)
        package = types.ModuleType("toefl_house")
        security = types.ModuleType("toefl_house.security")
        security.KIND_ROLES = {"record_applicant": "Admission Officer"}
        context = patch.dict(sys.modules, {"frappe": self.frappe,
            "toefl_house": package, "toefl_house.security": security})
        context.start()
        self.addCleanup(context.stop)
        source = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house/navigation.py"
        spec = importlib.util.spec_from_file_location("navigation_under_test", source)
        self.navigation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.navigation)

    def test_reception_lands_on_its_desk(self):
        self.assertEqual(self.navigation.staff_home_page(), "desk/th-reception-desk")

    def test_each_primary_role_has_a_desk(self):
        for role, page in self.navigation.ROLE_DESKS:
            with self.subTest(role=role):
                self.roles = [role]
                self.assertEqual(self.navigation.staff_home_page(), "desk/" + page)

    def test_owner_priority_is_not_role_list_order(self):
        self.roles = ["Reception", "Finance Manager", "Course Owner"]
        self.assertEqual(self.navigation.staff_home_page(), "desk/th-owner-cockpit")

    def test_login_uses_authenticated_target_before_session_switch(self):
        self.frappe.session.user = "Guest"
        self.navigation.on_login(types.SimpleNamespace(user="staff@example.test"))
        self.assertEqual(self.frappe.local.flags.home_page, "desk/th-reception-desk")
        self.frappe.get_roles.assert_called_with("staff@example.test")

    def test_boot_routes_existing_session_without_changing_roles(self):
        boot = {"home_page": "desktop", "user": {"can_read": ["Student"]}}
        self.navigation.boot_session(boot)
        self.assertEqual(boot, {"home_page": "th-reception-desk", "user": {"can_read": ["Student"]}})

    def test_api_only_staff_get_role_filtered_command_centre(self):
        self.roles = ["Admission Officer"]
        self.assertEqual(self.navigation.staff_home_page(), "desk/th-command-centre")

    def test_builtin_accounts_are_unchanged(self):
        for user in ("Guest", "Administrator"):
            self.assertIsNone(self.navigation.staff_home_page(user))
        self.frappe.get_cached_value.assert_not_called()

    def test_incomplete_setup_keeps_native_wizard_routing(self):
        self.frappe.is_setup_complete.return_value = False
        self.assertIsNone(self.navigation.staff_home_page())
        self.frappe.get_cached_value.assert_not_called()

    def test_disabled_website_and_unrelated_accounts_are_unchanged(self):
        self.identity.enabled = 0
        self.assertIsNone(self.navigation.staff_home_page())
        self.identity.enabled = 1
        self.identity.user_type = "Website User"
        self.assertIsNone(self.navigation.staff_home_page())
        self.identity.user_type = "System User"
        self.roles = ["Desk User", "Accounts User"]
        self.assertIsNone(self.navigation.staff_home_page())

    def test_old_root_bookmark_redirects_privately_and_preserves_cookie(self):
        response = Mock(status_code=200, headers={"Set-Cookie": "unchanged"})
        self.navigation.after_request(response, types.SimpleNamespace(method="GET", path="/desk"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/desk/th-reception-desk")
        self.assertEqual(response.headers["Set-Cookie"], "unchanged")
        self.assertEqual(response.headers["Cache-Control"], "no-store, private")
        response.set_data.assert_called_once_with(b"")

    def test_root_hook_never_overrides_api_deep_link_post_or_failed_response(self):
        for method, path, status in (("GET", "/api/method/login", 200),
                ("GET", "/desk/th-admission-officer", 200), ("POST", "/desk", 200),
                ("GET", "/desk", 403)):
            with self.subTest(method=method, path=path, status=status):
                response = Mock(status_code=status, headers={})
                self.navigation.after_request(response, types.SimpleNamespace(method=method, path=path))
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.headers, {})
                response.set_data.assert_not_called()

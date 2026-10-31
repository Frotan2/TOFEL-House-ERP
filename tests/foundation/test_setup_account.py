import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as O
import unittest
from unittest.mock import Mock, patch


class SetupAccountTests(unittest.TestCase):
    def setUp(self):
        self.user = Mock(enabled=1, role_profile_name=None)
        self.user.roles = [O(role=r) for r in ("System Manager", "Guardian", "Student", "Accounts Manager")]
        self.frappe = O(flags=O(in_setup_wizard=True), session=O(user="Administrator"),
                        PermissionError=PermissionError, get_doc=Mock(return_value=self.user),
                        db=O(exists=Mock(return_value=False)), clear_cache=Mock())
        path = Path(__file__).resolve().parents[2] / "apps/foundation_security/foundation_security/setup.py"
        spec = importlib.util.spec_from_file_location("initial_setup_test", path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"frappe": self.frappe}):
            spec.loader.exec_module(self.module)

    def run_hook(self, email="initial@example.test"):
        self.module.setup_wizard_success({"email": email})

    def assert_refused(self):
        with self.assertRaises(PermissionError):
            self.run_hook()
        self.user.save.assert_not_called()

    def test_only_system_management_survives_native_default_roles(self):
        self.run_hook()
        self.user.set.assert_called_once_with("roles", [{"role": "System Manager"}])
        self.user.save.assert_called_once_with()
        self.frappe.clear_cache.assert_called_once_with(user="initial@example.test")

    def test_not_a_general_role_reset_entrypoint(self):
        self.frappe.flags.in_setup_wizard = False
        self.assert_refused()

    def test_requires_administrator_setup_actor(self):
        self.frappe.session.user = "other@example.test"
        self.assert_refused()

    def test_existing_portal_identity_refused(self):
        for doctype in ("Student", "Guardian"):
            with self.subTest(doctype=doctype):
                self.frappe.db.exists.side_effect = lambda dt, filters: dt == doctype
                self.assert_refused()

    def test_role_profile_refused(self):
        self.user.role_profile_name = "Existing profile"
        self.assert_refused()

    def test_disabled_account_refused(self):
        self.user.enabled = 0
        self.assert_refused()

    def test_non_setup_account_refused(self):
        self.user.roles = [O(role="Reception")]
        self.assert_refused()

    def test_no_first_user_leaves_native_administrator_unchanged(self):
        self.run_hook(email=None)
        self.frappe.get_doc.assert_not_called()

    def test_reserved_accounts_refused(self):
        for email in ("Administrator", "Guest"):
            with self.assertRaises(PermissionError):
                self.run_hook(email=email)
        self.user.save.assert_not_called()

    def test_native_hook_is_wired(self):
        path = Path(__file__).resolve().parents[2] / "apps/foundation_security/foundation_security/hooks.py"
        self.assertIn('setup_wizard_success = "foundation_security.setup.setup_wizard_success"', path.read_text())

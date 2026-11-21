"""First-owner eligibility must ignore only the native wizard's own candidate."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as O
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = "initial@example.test"


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeRoleRows:
    """Small native-row fixture, evaluating the actual gate's filter values."""

    def __init__(self):
        self.admin_present = True
        self.roles = {}
        self.calls = []

    def get_value(self, doctype, filters, field, **kwargs):
        self.calls.append((doctype, filters, field, kwargs))
        if doctype == "User":
            if filters != "Administrator":
                raise AssertionError("Unexpected User lookup")
            return "Administrator" if self.admin_present else None
        if doctype != "Has Role":
            raise AssertionError("Unexpected native table")
        for user, roles in self.roles.items():
            for role in roles:
                row = {"parenttype": "User", "parent": user, "role": role,
                       "name": user + ":" + role}
                matches = True
                for key, expected in filters.items():
                    if isinstance(expected, list):
                        if expected[0] != "!=":
                            raise AssertionError("Unexpected native filter operator")
                        matches &= row[key] != expected[1]
                    else:
                        matches &= row[key] == expected
                if matches:
                    return row[field]
        return None

    def exists(self, doctype, filters):
        if doctype not in ("Student", "Guardian"):
            raise AssertionError("Unexpected native identity lookup")
        return False


class ProviderFirstOwnerTests(unittest.TestCase):
    def setUp(self):
        self.db = NativeRoleRows()
        # Native setup assigns broad roles before foundation_security narrows them.
        self.db.roles[CANDIDATE] = [
            "System Manager", "Course Owner", "Guardian", "Student", "Accounts Manager",
        ]
        self.user = O(enabled=1, role_profile_name=None,
                      roles=[O(role=role) for role in self.db.roles[CANDIDATE]])
        self.user.set = Mock(side_effect=lambda field, rows: setattr(
            self.user, field, [O(**row) for row in rows]))
        self.user.save = Mock(side_effect=lambda: self.db.roles.__setitem__(
            CANDIDATE, [row.role for row in self.user.roles]))
        self.frappe = O(flags=O(in_setup_wizard=True), session=O(user="Administrator"),
                        db=self.db, PermissionError=PermissionError,
                        get_doc=Mock(return_value=self.user), clear_cache=Mock(),
                        get_installed_apps=Mock(return_value=["frappe", "foundation_security", "toefl_house"]))
        self.mode = Mock(return_value="REFUSED")
        modules = {
            "frappe": self.frappe,
            "toefl_house.security": O(REFUSED="REFUSED", site_mode=self.mode),
        }
        self.environment = patch.dict(sys.modules, modules)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.provider = load("first_owner_provider_test",
                             "apps/toefl_house/toefl_house/setup_presets/provider_release.py")
        self.provider.has_verified_factory_release = Mock(return_value=True)
        sys.modules["toefl_house.setup_presets.provider_release"] = self.provider
        self.hook = load("first_owner_hook_test", "apps/foundation_security/foundation_security/setup.py")

    def test_native_candidate_transient_owner_grant_does_not_block_itself(self):
        self.assertTrue(self.provider.first_owner_enrollment_allowed(CANDIDATE))

    def test_native_hook_preserves_only_management_and_first_owner(self):
        self.hook.setup_wizard_success({"email": CANDIDATE})
        self.assertEqual(self.db.roles[CANDIDATE], ["System Manager", "Course Owner"])
        self.user.save.assert_called_once_with()
        self.frappe.clear_cache.assert_called_once_with(user=CANDIDATE)

    def test_another_owner_blocks_candidate_without_changing_existing_owner(self):
        self.db.roles["existing@example.test"] = ["Course Owner", "General Manager"]
        self.hook.setup_wizard_success({"email": CANDIDATE})
        self.assertEqual(self.db.roles[CANDIDATE], ["System Manager"])
        self.assertEqual(self.db.roles["existing@example.test"], ["Course Owner", "General Manager"])

    def test_explicit_administrator_owner_grant_is_not_excluded_as_candidate(self):
        self.db.roles["Administrator"] = ["System Manager", "Course Owner"]
        self.assertFalse(self.provider.first_owner_enrollment_allowed(CANDIDATE))

    def test_no_transient_owner_role_is_also_a_valid_first_candidate(self):
        self.db.roles[CANDIDATE] = ["System Manager"]
        self.assertTrue(self.provider.first_owner_enrollment_allowed(CANDIDATE))

    def test_only_candidate_is_excluded_and_reads_remain_serialized(self):
        self.assertTrue(self.provider.first_owner_enrollment_allowed(CANDIDATE))
        self.assertEqual(self.db.calls, [
            ("User", "Administrator", "name", {"for_update": True}),
            ("Has Role", {"parenttype": "User", "role": "Course Owner",
                          "parent": ["!=", CANDIDATE]}, "name", {"for_update": True}),
        ])

    def test_missing_administrator_lock_row_refuses_first_owner(self):
        self.db.admin_present = False
        self.assertFalse(self.provider.first_owner_enrollment_allowed(CANDIDATE))
        self.assertEqual(len(self.db.calls), 1)

    def test_invalid_or_protected_candidate_refused_before_database_reads(self):
        for candidate in (None, "", "Administrator", "Guest", 7, [], {}):
            with self.subTest(candidate=candidate):
                self.assertFalse(self.provider.first_owner_enrollment_allowed(candidate))
        self.assertEqual(self.db.calls, [])
        self.provider.has_verified_factory_release.assert_not_called()

    def test_only_administrator_in_native_wizard_may_enroll_first_owner(self):
        for wizard, actor in ((False, "Administrator"), (True, CANDIDATE), (True, "Guest")):
            with self.subTest(wizard=wizard, actor=actor):
                self.frappe.flags.in_setup_wizard = wizard
                self.frappe.session.user = actor
                self.assertFalse(self.provider.first_owner_enrollment_allowed(CANDIDATE))
        self.assertEqual(self.db.calls, [])

    def test_unverified_factory_release_cannot_enroll_owner(self):
        self.provider.has_verified_factory_release.return_value = False
        self.hook.setup_wizard_success({"email": CANDIDATE})
        self.assertEqual(self.db.roles[CANDIDATE], ["System Manager"])
        self.assertEqual(self.db.calls, [])

    def test_already_operational_or_synthetic_site_cannot_enroll_owner(self):
        for mode in ("PRODUCTION", "SYNTHETIC"):
            with self.subTest(mode=mode):
                self.mode.return_value = mode
                self.assertFalse(self.provider.first_owner_enrollment_allowed(CANDIDATE))
        self.assertEqual(self.db.calls, [])
        self.provider.has_verified_factory_release.assert_not_called()


if __name__ == "__main__":
    unittest.main()

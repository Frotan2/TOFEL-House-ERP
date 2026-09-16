"""Static contract for the owner/manager governance surface.

The page is intentionally a native-authority navigation and attention projection:
it must not become a parallel role, branch, accounting, payroll, student or
business-data ledger.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
ROLES = APP / "fixtures/role.json"
PAGE = APP / "placement/page/th_administration_control_centre/th_administration_control_centre.json"
HOOKS = APP / "hooks.py"
ADMIN = APP / "administration.py"

GOVERNANCE_ROLES = {"Course Owner", "General Manager", "Academic Manager", "Finance Manager", "Reception"}
CONTROL_ROLES = {"Course Owner", "General Manager"}


class GovernanceSurfaceTests(unittest.TestCase):
    def test_governance_roles_are_shipped_without_implicit_permissions(self):
        rows = {row["name"]: row for row in json.loads(ROLES.read_text())}
        self.assertTrue(GOVERNANCE_ROLES <= rows.keys())
        for role in GOVERNANCE_ROLES:
            self.assertEqual(rows[role]["desk_access"], 1)
            self.assertEqual(rows[role]["disabled"], 0)
            self.assertNotIn("permissions", rows[role])

    def test_control_centre_is_role_gated_and_native(self):
        page = json.loads(PAGE.read_text())
        self.assertEqual(page["doctype"], "Page")
        self.assertEqual({row["role"] for row in page["roles"]}, CONTROL_ROLES)
        source = ADMIN.read_text()
        self.assertIn("@frappe.whitelist(methods=[\"GET\", \"POST\"])", source)
        self.assertIn("Course Owner or General Manager role required", source)
        self.assertIn('"production_state": "REJECT"', source)
        self.assertIn('"deployment_phase": "LOCAL_SERVER_TAILSCALE"', source)
        self.assertIn("def set_managed_role", source)
        self.assertIn('"audit_authority": "Version"', source)
        self.assertIn("MANAGED_ROLES", source)
        self.assertIn("PROTECTED_USERS", source)
        for native in ("User", "Role", "User Permission", "Company", "Branch", "Version"):
            self.assertIn(native, source)
        self.assertNotIn("frappe.db.get_list", source)
        self.assertNotIn("frappe.get_all", source)

    def test_hooks_register_the_page_and_roles_for_migration(self):
        source = HOOKS.read_text()
        self.assertIn('"th-administration-control-centre"', source)
        for role in GOVERNANCE_ROLES:
            self.assertIn(f'"{role}"', source)


if __name__ == "__main__":
    unittest.main()

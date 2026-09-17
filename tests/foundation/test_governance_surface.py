"""Static contract for the owner/manager governance surface.

The page is intentionally a native-authority navigation and attention projection:
it must not become a parallel role, branch, accounting, payroll, student or
business-data ledger.
"""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
ROLES = APP / "fixtures/role.json"
PAGE = APP / "placement/page/th_administration_control_centre/th_administration_control_centre.json"
HOOKS = APP / "hooks.py"
ADMIN = APP / "administration.py"
MATRIX = ROOT / "docs/engineering/d8-production-operations-decision-matrix.json"

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
        self.assertIn('for_update=True', source)
        self.assertIn('"changed": not already', source)
        self.assertIn("not isinstance(recorded, dict)", source)
        self.assertIn("cannot revoke its own operational role", source)
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

    def test_attention_projection_matches_the_authoritative_d8_matrix(self):
        """The Desk snapshot must not become a second source of truth for D8.

        ``get_control_center_snapshot`` hand-copies release state that the D8
        matrix owns. Copied state drifts: the matrix is validated on every run
        by ``d8_validate.py``, while this projection is only ever read by a
        human on a Desk page, so a divergence would show a manager a different
        production posture from the one the release gate actually enforces.

        These assertions tie the copy to the authority. They are deliberately
        directional: if the matrix changes, this test fails until the
        projection is deliberately updated and reviewed, rather than the two
        drifting apart in silence.
        """
        matrix = json.loads(MATRIX.read_text())
        source = ADMIN.read_text()

        # Parse the returned literal rather than pattern-matching the file, so
        # reformatting cannot make the check vacuous. The dict is not wholly
        # literal (`viewer_roles` calls sorted()), so each key is read on its
        # own and a non-literal value is reported rather than skipped silently.
        tree = ast.parse(source)
        returned = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_control_center_snapshot":
                for child in ast.walk(node):
                    if isinstance(child, ast.Return) and isinstance(child.value, ast.Dict):
                        returned = child.value
        self.assertIsNotNone(returned, "could not find the snapshot return literal")
        keys = {
            key.value: value
            for key, value in zip(returned.keys, returned.values)
            if isinstance(key, ast.Constant)
        }

        def literal(name):
            self.assertIn(name, keys, f"snapshot no longer reports {name}")
            return ast.literal_eval(keys[name])

        self.assertEqual(
            literal("production_state"), matrix["production_state"],
            "Desk production_state diverged from the authoritative D8 matrix",
        )

        attention = {row["id"]: row for row in literal("operational_attention")}
        self.assertEqual(
            attention["dependency-security"]["state"], matrix["security_dependency_state"],
            "SEC-DEPS-01 state on the Desk diverged from the D8 matrix",
        )
        self.assertEqual(
            attention["d8-evidence"]["state"], matrix["overall_gate_state"],
            "D8 evidence state on the Desk diverged from the D8 matrix",
        )

        # The projection may summarise but must never soften: a gate the matrix
        # marks REJECT must not be reported to a manager as merely BLOCKED.
        severity = {"PASS": 0, "BLOCKED": 1, "REJECT": 2}
        desk_posture = literal("production_state").split(" / ")[-1]
        self.assertIn(desk_posture, severity)
        self.assertGreaterEqual(
            severity[desk_posture],
            severity[matrix["production_state"]],
            "the Desk must not report a softer posture than the matrix enforces",
        )


if __name__ == "__main__":
    unittest.main()

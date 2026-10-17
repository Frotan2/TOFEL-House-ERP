"""Disabled users are refused on every authenticated path (2026-10-15 review).

Traced in the pinned Frappe v16.33.1 (988e54f3): frappe/app.py application()
calls validate_auth() on every request. validate_auth() resolves OAuth bearer
and API-key credentials, then ALWAYS calls validate_auth_via_hooks(), which runs
each auth_hooks entry. So the foundation_security guard covers cookie sessions,
API keys and bearer tokens alike, but only while this wiring holds. These tests
pin the wiring and the check order, so an edit cannot silently drop either.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "apps/foundation_security/foundation_security/hooks.py"
GUARDS = ROOT / "apps/foundation_security/foundation_security/guards.py"


def _functions(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


class DisabledUserPathTests(unittest.TestCase):
    def test_auth_hook_declares_the_request_guard(self):
        tree = ast.parse(HOOKS.read_text(encoding="utf-8"))
        declared = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "auth_hooks" for t in node.targets
            ):
                declared = ast.literal_eval(node.value)
        self.assertEqual(declared, ["foundation_security.guards.validate_request"])

    def test_request_guard_checks_user_enabled_before_anything_else(self):
        fn = _functions(GUARDS)["validate_request"]
        first = fn.body[0]
        self.assertIsInstance(first, ast.Expr)
        self.assertIsInstance(first.value, ast.Call)
        self.assertEqual(first.value.func.id, "validate_user_enabled")

    def test_user_enabled_check_raises_and_skips_only_guest_and_missing(self):
        src = GUARDS.read_text(encoding="utf-8")
        fn = _functions(GUARDS)["validate_user_enabled"]
        body = ast.get_source_segment(src, fn)
        self.assertIn('if user in (None, "Guest"):', body)
        self.assertIn("if not frappe.get_cached_value(\"User\", user, \"enabled\"):", body)
        self.assertIn("raise frappe.AuthenticationError", body)


if __name__ == "__main__":
    unittest.main()

"""A disabled Administrator is refused on every credential path (owner decision 2026-10-18).

Frappe exempts Administrator at interactive login (frappe/auth.py at 988e54f3c4c2:
`elif not (user.name == "Administrator" or user.enabled)`). The owner decided the
foundation guard must NOT mirror that exemption. Request-time auth (cookie, API key,
bearer) already reaches validate_user_enabled with no Administrator exclusion; the
login path (on_session_creation) must enforce it too.
"""
import ast
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
GUARDS = ROOT / "apps/foundation_security/foundation_security/guards.py"


class _AuthError(Exception):
    pass


def _load_guards(user, enabled):
    fake = Obj(
        session=Obj(user=user),
        get_roles=lambda u: [],
        PermissionError=PermissionError,
        AuthenticationError=_AuthError,
        conf={},
        get_cached_value=lambda doctype, name, field: enabled,
        get_all=lambda *a, **k: [],
        db=Obj(get_single_value=lambda *a: 1, exists=lambda *a: False),
    )
    spec = importlib.util.spec_from_file_location("guard_admin_under_test", GUARDS)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"frappe": fake}):
        spec.loader.exec_module(module)
    return module


class AdministratorDisabledTests(unittest.TestCase):
    def test_login_guard_checks_enabled_before_scope_checks(self):
        tree = ast.parse(GUARDS.read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "on_session_creation")
        first = fn.body[0]
        self.assertIsInstance(first.value, ast.Call)
        self.assertEqual(first.value.func.id, "validate_user_enabled")

    def test_disabled_administrator_refused_at_login(self):
        guards = _load_guards("Administrator", enabled=0)
        guards.frappe.AuthenticationError = _AuthError
        with self.assertRaises(_AuthError):
            guards.on_session_creation()

    def test_disabled_administrator_refused_on_request(self):
        guards = _load_guards("Administrator", enabled=0)
        guards.frappe.AuthenticationError = _AuthError
        with self.assertRaises(_AuthError):
            guards.validate_request()

    def test_enabled_administrator_still_allowed(self):
        guards = _load_guards("Administrator", enabled=1)
        guards.on_session_creation()
        guards.validate_user_enabled()

    def test_guest_is_not_refused_by_enabled_check(self):
        guards = _load_guards("Guest", enabled=0)
        guards.validate_user_enabled()


if __name__ == "__main__":
    unittest.main()

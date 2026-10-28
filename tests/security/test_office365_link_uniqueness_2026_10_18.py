"""Office 365 account linking: one identity cannot be attached to two Users (2026-10-18).

Local unit level with a fake frappe module. The real-site proof of the same rule (a real User
save that is refused by the real database lookup) is in tools/native/native_checks.py.
"""
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "apps/toefl_house/toefl_house/identity_links.py"
HOOKS = ROOT / "apps/toefl_house/toefl_house/hooks.py"


class _ThrowError(Exception):
    pass


def _fake_frappe(holders):
    """`holders` maps a userid to the list of User names that already hold it."""
    frappe = types.ModuleType("frappe")
    frappe.ValidationError = _ThrowError
    frappe._ = lambda text, *args: text
    frappe.calls = []

    def throw(message, exc=None):
        raise (exc or Exception)(message)

    def get_all(doctype, filters=None, fields=None, limit_page_length=None, **_):
        frappe.calls.append((doctype, dict(filters)))
        assert doctype == "User Social Login"
        userid = filters["userid"]
        exclude = filters.get("parent", [None, None])[1] if isinstance(filters.get("parent"), list) else None
        rows = [{"parent": name} for name in holders.get(userid, []) if name != exclude]
        return rows[:limit_page_length]

    frappe.throw = throw
    frappe.get_all = get_all
    return frappe


def _load(frappe):
    spec = importlib.util.spec_from_file_location("identity_links_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    with patch.dict("sys.modules", {"frappe": frappe}):
        spec.loader.exec_module(module)
    return module


def _doc(name, *rows):
    return types.SimpleNamespace(name=name, get=lambda key, default=None: list(rows) if key == "social_logins" else default)


def _row(userid, provider="office_365"):
    return {"provider": provider, "userid": userid}


class Office365LinkUniquenessTests(unittest.TestCase):
    def setUp(self):
        self.holders = {"SUB-A": ["alice@example.test"], "SUB-B": []}

    def _run(self, doc):
        frappe = _fake_frappe(self.holders)
        module = _load(frappe)
        module.validate_office365_links(doc)
        return frappe

    def test_free_identity_saves(self):
        frappe = self._run(_doc("bob@example.test", _row("SUB-B")))
        self.assertEqual(frappe.calls[0][1]["parent"], ["!=", "bob@example.test"])

    def test_identity_held_by_another_user_is_refused(self):
        with self.assertRaises(_ThrowError) as ctx:
            self._run(_doc("bob@example.test", _row("SUB-A")))
        self.assertIn("already linked to another user", str(ctx.exception))

    def test_user_may_keep_its_own_identity(self):
        # The holder re-saves its own row: the exclusion removes its own parent, so no refusal.
        self._run(_doc("alice@example.test", _row("SUB-A")))

    def test_unsaved_user_cannot_take_a_held_identity(self):
        with self.assertRaises(_ThrowError):
            self._run(_doc(None, _row("SUB-A")))

    def test_unsaved_user_with_free_identity_is_allowed_and_has_no_exclusion(self):
        frappe = self._run(_doc(None, _row("SUB-B")))
        self.assertNotIn("parent", frappe.calls[0][1])

    def test_same_identity_twice_on_one_user_is_refused_case_insensitively(self):
        with self.assertRaises(_ThrowError) as ctx:
            self._run(_doc("bob@example.test", _row("SUB-B"), _row("sub-b")))
        self.assertIn("more than once", str(ctx.exception))

    def test_blank_and_other_provider_rows_are_ignored(self):
        frappe = self._run(_doc("bob@example.test", _row(""), _row("SUB-A", provider="google")))
        self.assertEqual(frappe.calls, [])

    def test_hook_is_registered_for_user_validate(self):
        text = HOOKS.read_text(encoding="utf-8")
        self.assertIn('"User": {', text)
        self.assertIn('"validate": "toefl_house.identity_links.validate_office365_links"', text)


if __name__ == "__main__":
    unittest.main()

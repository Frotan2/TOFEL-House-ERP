"""Executable tests for the native administration facade's request contract."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
ADMIN_PATH = ROOT / "apps/toefl_house/toefl_house/administration.py"


class FakeUser:
    def __init__(self, roles):
        self.roles = set(roles)
        self.save_calls = 0

    def get_roles(self):
        return sorted(self.roles)

    def add_roles(self, role):
        self.roles.add(role)

    def remove_roles(self, role):
        self.roles.discard(role)

    def save(self, **kwargs):
        self.save_calls += 1


class FakeVersion:
    def __init__(self, frappe, values):
        self.frappe = frappe
        self.data = values["data"]

    def insert(self, **kwargs):
        self.frappe.version_rows.append({"data": self.data})


class FakeFrappe(types.ModuleType):
    class ValidationError(Exception):
        pass

    class PermissionError(Exception):
        pass

    def __init__(self):
        super().__init__("frappe")
        self.session = types.SimpleNamespace(user="owner@example.test")
        self.users = {"staff@example.test": FakeUser({"Reception"})}
        self.version_rows = []
        self.calls = []

    def whitelist(self, **kwargs):
        return lambda function: function

    def get_roles(self, user):
        return {"Course Owner"} if user == self.session.user else set()

    def get_doc(self, doctype_or_values, name=None, **kwargs):
        if isinstance(doctype_or_values, dict):
            return FakeVersion(self, doctype_or_values)
        self.calls.append((doctype_or_values, name, kwargs))
        return self.users[name]

    def get_list(self, *args, **kwargs):
        return list(self.version_rows)


def load_administration(fake_frappe):
    policy = types.ModuleType("toefl_house.policy")
    policy.validate_request_key = lambda key: None
    package = types.ModuleType("toefl_house")
    package.__path__ = []
    with patch.dict(sys.modules, {
        "frappe": fake_frappe,
        "toefl_house": package,
        "toefl_house.policy": policy,
    }):
        spec = importlib.util.spec_from_file_location("toefl_house.administration", ADMIN_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class AdministrationIdempotencyTests(unittest.TestCase):
    def test_noop_is_recorded_and_replay_cannot_change_operation(self):
        fake = FakeFrappe()
        administration = load_administration(fake)

        first = administration.set_managed_role(
            "request-key-00000001", "staff@example.test", "Reception", True
        )
        self.assertFalse(first["changed"])
        self.assertEqual(len(fake.version_rows), 1)
        self.assertEqual(fake.users["staff@example.test"].save_calls, 0)

        replay = administration.set_managed_role(
            "request-key-00000001", "staff@example.test", "Reception", True
        )
        self.assertTrue(replay["replayed"])
        self.assertFalse(replay["changed"])
        self.assertEqual(len(fake.version_rows), 1)

        with self.assertRaises(fake.ValidationError):
            administration.set_managed_role(
                "request-key-00000001", "staff@example.test", "Finance Officer", True
            )

    def test_user_is_locked_before_receipt_lookup_and_inputs_fail_closed(self):
        fake = FakeFrappe()
        administration = load_administration(fake)

        with self.assertRaises(fake.ValidationError):
            administration.set_managed_role(
                "request-key-00000002", "staff@example.test", [], True
            )
        with self.assertRaises(fake.ValidationError):
            administration.set_managed_role(
                "request-key-00000003", "owner@example.test", "General Manager", False
            )

        administration.set_managed_role(
            "request-key-00000004", "staff@example.test", "Finance Officer", True
        )
        self.assertEqual(fake.calls[0][0:2], ("User", "staff@example.test"))
        self.assertTrue(fake.calls[0][2]["for_update"])


if __name__ == "__main__":
    unittest.main()

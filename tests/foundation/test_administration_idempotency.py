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
        self.enabled = 1
        self.list_calls = []
        self.db = types.SimpleNamespace(get_value=self._db_get_value)

    def _db_get_value(self, doctype, name, fieldname=None, **kwargs):
        assert (doctype, fieldname) == ("User", "enabled")
        return self.enabled if name == self.session.user else 1

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
        self.list_calls.append(kwargs)
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

    def test_like_pattern_escapes_wildcards_in_the_key(self):
        # S3 (BUG-ADMIN-01): `_` and `%` are wild in LIKE; the replay lookup
        # must escape them so the pattern cannot over-match neighbor keys.
        fake = FakeFrappe()
        administration = load_administration(fake)
        administration.set_managed_role(
            "request_key-000000%A", "staff@example.test", "Reception", True
        )
        operand = fake.list_calls[-1]["filters"]["data"][1]
        self.assertIn("\\_", operand)
        self.assertIn("\\%", operand)
        self.assertTrue(operand.startswith("%") and operand.endswith("%"))

    def test_neighbor_key_never_replays_or_conflicts(self):
        # S3 (BUG-ADMIN-01): only an EXACT request_key match is this call's
        # receipt. A neighbor row — even one a bare LIKE would over-match,
        # and even for the same role+state — must be ignored, not replayed.
        import json

        fake = FakeFrappe()
        administration = load_administration(fake)
        fake.version_rows.append({"data": json.dumps({
            "changed_by": "owner@example.test",
            "request_key": "requestXkey_00000001",
            "managed_role": "Finance Officer",
            "enabled": True,
            "changed": True,
        })})
        result = administration.set_managed_role(
            "request_key_00000001", "staff@example.test", "Finance Officer", True
        )
        self.assertNotIn("replayed", result)
        self.assertTrue(result["changed"])
        self.assertEqual(len(fake.version_rows), 2)

    def test_unreadable_neighbor_row_does_not_brick_role_admin(self):
        # S3 (BUG-ADMIN-01): an unreadable row that is not this key's receipt
        # is skipped; the call proceeds and records its own audit row.
        fake = FakeFrappe()
        administration = load_administration(fake)
        fake.version_rows.append({"data": "not-json{"})
        result = administration.set_managed_role(
            "request-key-00000009", "staff@example.test", "Finance Officer", True
        )
        self.assertTrue(result["changed"])
        self.assertEqual(len(fake.version_rows), 2)

    def test_disabled_actor_holds_no_administration_authority(self):
        # S3: a disabled login cannot assign roles even with Course Owner
        # still attached; the control snapshot refuses the same way.
        fake = FakeFrappe()
        administration = load_administration(fake)
        fake.enabled = 0
        with self.assertRaises(fake.PermissionError):
            administration.set_managed_role(
                "request-key-00000010", "staff@example.test", "Reception", True
            )
        with self.assertRaises(fake.PermissionError):
            administration.get_control_center_snapshot()


if __name__ == "__main__":
    unittest.main()

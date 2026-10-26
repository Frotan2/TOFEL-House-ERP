import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as O
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeFeeItemTests(unittest.TestCase):
    def setUp(self):
        self.rules = load(APP / "configuration/rules.py", "fee_item_rules_test")
        self.actor = "owner@example.test"
        self.authority = Mock(return_value=self.actor)
        modules = {"frappe": O(session=O(user=self.actor), db=O(exists=Mock(return_value=True)),
                                 ValidationError=ValueError),
                   "toefl_house.configuration": O(rules=self.rules),
                   "toefl_house.configuration.audit": O(require_authority=self.authority)}
        self.patches = patch.dict(sys.modules, modules)
        self.patches.start()
        self.addCleanup(self.patches.stop)
        module = load(APP / "academic/native_fee_item.py", "native_fee_item_test")

        class NativeItem:
            def validate(self):
                self.native_validated = True

            def has_permission(self, permtype="read", *, debug=False, user=None):
                return False

        class Item(module.FeeItemPermissionMixin, NativeItem):
            pass

        self.item = Item()
        self.item.name = None
        self.item.item_code = "SYN Fee"
        self.item.item_group = "Fee Component"
        self.item.is_stock_item = 0
        self.item.is_sales_item = 1
        self.item.stock_uom = None

    def scope(self):
        return self.rules.fee_item_context(self.actor, "SYN Fee")

    def test_native_creation_and_update_only_inside_the_exact_command(self):
        with self.rules.command_context("create_fee_type"), self.scope():
            self.assertTrue(self.item.has_permission("create"))
            self.item.name = "SYN Fee"
            self.assertTrue(self.item.has_permission("write"))
            for permission in ("read", "delete", "submit", "cancel", "share"):
                self.assertFalse(self.item.has_permission(permission))
        self.assertFalse(self.item.has_permission("write"))

    def test_raw_item_call_keeps_native_permissions(self):
        self.assertFalse(self.item.has_permission("create"))
        self.authority.assert_not_called()

    def test_other_command_cannot_open_scope(self):
        with self.rules.command_context("create_program"):
            with self.assertRaises(ValueError):
                with self.scope():
                    pass

    def test_foreign_or_stock_item_never_gets_authority(self):
        for field, value in (("item_code", "Other"), ("name", "Other"),
                             ("item_group", "Products"), ("is_stock_item", 1),
                             ("is_sales_item", 0)):
            old = getattr(self.item, field)
            with self.subTest(field=field), self.rules.command_context("create_fee_type"), self.scope():
                setattr(self.item, field, value)
                self.assertFalse(self.item.has_permission("create"))
            setattr(self.item, field, old)

    def test_no_permission_for_another_requested_user(self):
        with self.rules.command_context("create_fee_type"), self.scope():
            self.assertFalse(self.item.has_permission("create", user="other@example.test"))

    def test_revoked_authority_is_rechecked(self):
        self.authority.side_effect = PermissionError("Disabled or revoked")
        with self.rules.command_context("create_fee_type"), self.scope():
            with self.assertRaises(PermissionError):
                self.item.has_permission("create")

    def test_scope_resets_on_failure_and_does_not_cross_requests(self):
        from contextvars import Context
        with self.assertRaises(RuntimeError):
            with self.rules.command_context("create_fee_type"), self.scope():
                self.assertFalse(Context().run(self.item.has_permission, "create"))
                raise RuntimeError("Rollback")
        self.assertIsNone(self.rules.active_fee_item())

    def test_scoped_fee_item_receives_native_mandatory_service_uom(self):
        with self.rules.command_context("create_fee_type"), self.scope():
            self.item.validate()
        self.assertEqual(self.item.stock_uom, "Nos")
        self.assertTrue(self.item.native_validated)

    def test_foreign_item_and_outside_command_keep_native_validation(self):
        self.item.validate()
        self.assertIsNone(self.item.stock_uom)
        with self.rules.command_context("create_fee_type"), self.scope():
            self.item.item_code = "Unrelated Product"
            self.item.validate()
            self.assertIsNone(self.item.stock_uom)
            self.item.item_code = "SYN Fee"
            self.item.item_group = "Products"
            self.item.validate()
            self.assertIsNone(self.item.stock_uom)
            self.item.item_group = "Fee Component"
            self.item.stock_uom = "Box"
            self.item.validate()
            self.assertEqual(self.item.stock_uom, "Box")

    def test_missing_native_standard_uom_refuses_without_creating_master(self):
        import frappe
        frappe.db.exists.return_value = False
        with self.rules.command_context("create_fee_type"), self.scope():
            with self.assertRaisesRegex(ValueError, "standard Nos unit of measure"):
                self.item.validate()
        self.assertIsNone(self.item.stock_uom)
        frappe.db.exists.assert_called_once_with("UOM", "Nos")

    def test_revoked_owner_cannot_default_item_uom(self):
        self.authority.side_effect = PermissionError("Disabled or revoked")
        with self.rules.command_context("create_fee_type"), self.scope():
            with self.assertRaises(PermissionError):
                self.item.validate()
        self.assertIsNone(self.item.stock_uom)

    def test_native_controller_extension_is_wired(self):
        self.assertIn('"Item": ["toefl_house.academic.native_fee_item.FeeItemPermissionMixin"]',
                      (APP / "hooks.py").read_text())

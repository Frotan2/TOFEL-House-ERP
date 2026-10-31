import importlib.util
from pathlib import Path
from types import SimpleNamespace as O
import sys
import unittest
from unittest.mock import Mock, patch


class NativeCatalogSetupTests(unittest.TestCase):
    def setUp(self):
        self.doc = O(name="Fee Component", parent_item_group="", is_group=0, save=Mock())
        self.frappe = O(session=O(user="Administrator"), flags=O(in_setup_wizard=True),
                        db=O(exists=Mock(return_value=True)), get_doc=Mock(return_value=self.doc),
                        get_all=Mock(return_value=[self.doc.name]),
                        PermissionError=PermissionError, ValidationError=ValueError)
        self.modules = patch.dict(sys.modules, {"frappe": self.frappe})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        path = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house/academic/native_setup.py"
        spec = importlib.util.spec_from_file_location("native_setup_test", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_malformed_root_uses_native_save_and_retains_identity(self):
        self.assertTrue(self.module.ensure_fee_component_root())
        self.assertEqual(self.doc.is_group, 1)
        self.assertEqual(self.doc.name, "Fee Component")
        self.doc.save.assert_called_once_with()
        self.frappe.get_doc.assert_called_once_with("Item Group", "Fee Component", for_update=True)
        self.assertFalse(self.module.ensure_fee_component_root())
        self.doc.save.assert_called_once()

    def test_normal_leaf_below_a_root_is_untouched(self):
        self.doc.parent_item_group = "All Item Groups"
        self.assertFalse(self.module.ensure_fee_component_root())
        self.doc.save.assert_not_called()

    def test_missing_education_group_is_untouched(self):
        self.frappe.db.exists.return_value = False
        self.assertFalse(self.module.ensure_fee_component_root())
        self.frappe.get_doc.assert_not_called()

    def test_ambiguous_roots_fail_without_mutation(self):
        self.frappe.get_all.return_value = ["All Item Groups", "Fee Component"]
        with self.assertRaises(ValueError):
            self.module.ensure_fee_component_root()
        self.doc.save.assert_not_called()
        self.assertEqual(self.doc.is_group, 0)

    def test_native_validation_failure_is_not_swallowed(self):
        self.doc.save.side_effect = ValueError("native tree validation")
        with self.assertRaisesRegex(ValueError, "native tree"):
            self.module.ensure_fee_component_root()

    def test_repair_rejects_business_actor_and_nonwizard_hook(self):
        self.frappe.session.user = "owner@example.test"
        with self.assertRaises(PermissionError):
            self.module.ensure_fee_component_root()
        self.frappe.session.user = "Administrator"
        self.frappe.flags.in_setup_wizard = False
        with self.assertRaises(PermissionError):
            self.module.setup_wizard_success({})
        self.doc.save.assert_not_called()

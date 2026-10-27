"""Temporary reference ACLs cannot persist or expand beyond the selected fees."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class ReferenceReadTests(unittest.TestCase):
    def setUp(self):
        self.rows = {}
        self.callbacks = []
        self.kind = "record_reception_collection"
        self.frappe = types.ModuleType("frappe")
        self.frappe.PermissionError = PermissionError
        self.frappe.session = types.SimpleNamespace(user="reception")
        self.frappe.generate_hash = lambda **kw: "lease-" + str(len(self.rows))
        self.delete_fails = False

        def delete(doctype, filters):
            if self.delete_fails:
                raise RuntimeError("delete unavailable")
            for name in filters["name"][1]:
                self.rows.pop(name, None)

        self.frappe.db = types.SimpleNamespace(
            get_value=lambda dt, name, field: {"FEE-A": "STUDENT-A", "FEE-B": "STUDENT-B"}.get(name),
            exists=lambda *a, **kw: False, delete=delete,
            count=lambda dt, filters: len([name for name in filters["name"][1] if name in self.rows]),
            before_commit=types.SimpleNamespace(add=self.callbacks.append))

        def get_doc(data):
            doc = types.SimpleNamespace(**data)
            doc.db_insert = lambda: self.rows.update({data["name"]: dict(data)})
            return doc
        self.frappe.get_doc = get_doc
        security = types.ModuleType("toefl_house.security")
        security.KIND_ROLES = {"record_reception_collection": "Reception", "correct_reception_collection": "Course Owner"}
        security.active_command_kind = lambda: self.kind
        security.authorize = Mock(return_value="reception")
        self.scope = types.ModuleType("toefl_house.command_scope")
        self.scope.authorize_command_scope = Mock()
        package = types.ModuleType("toefl_house")
        context = patch.dict(sys.modules, {"frappe": self.frappe, "toefl_house": package,
            "toefl_house.security": security, "toefl_house.command_scope": self.scope})
        context.start()
        self.addCleanup(context.stop)
        path = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house/finance/collection_reads.py"
        spec = importlib.util.spec_from_file_location("collection_read_lease", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.refs = [("Fees", "FEE-A"), ("Student", "STUDENT-A")]

    def test_only_exact_read_rights_exist_during_validation(self):
        with self.module.native_reference_reads(self.refs):
            self.assertEqual(len(self.rows), 2)
            for row in self.rows.values():
                self.assertEqual(row["user"], "reception")
                self.assertEqual(row["read"], 1)
                for field in ("write", "submit", "share", "everyone", "notify_by_email"):
                    self.assertEqual(row[field], 0)
            with self.assertRaises(PermissionError):
                self.callbacks[0]()
        self.assertEqual(self.rows, {})
        self.assertIsNone(self.module._LEASE.get())
        self.callbacks[0]()
        self.scope.authorize_command_scope.assert_called_once_with(
            "record_reception_collection", {"fees": "FEE-A"}, "reception")

    def test_native_validation_failure_still_cleans_up(self):
        with self.assertRaisesRegex(ValueError, "native refused"):
            with self.module.native_reference_reads(self.refs):
                raise ValueError("native refused")
        self.assertEqual(self.rows, {})
        self.assertIsNone(self.module._LEASE.get())

    def test_cleanup_failure_poison_prevents_later_commit(self):
        with self.assertRaises(RuntimeError):
            with self.module.native_reference_reads(self.refs):
                self.delete_fails = True
        self.assertIsNone(self.module._LEASE.get())
        with self.assertRaises(PermissionError):
            self.callbacks[0]()

    def test_outside_nested_and_unrelated_references_are_denied(self):
        self.kind = None
        with self.assertRaises(PermissionError), self.module.native_reference_reads(self.refs):
            pass
        self.kind = "record_reception_collection"
        for refs in ([("User", "reception")], [("Student", "STUDENT-A")],
                     [("Fees", "FEE-A"), ("Student", "STUDENT-B")]):
            with self.subTest(refs=refs), self.assertRaises(PermissionError), self.module.native_reference_reads(refs):
                pass
        with self.module.native_reference_reads(self.refs):
            with self.assertRaises(PermissionError), self.module.native_reference_reads(self.refs):
                pass
        self.assertEqual(self.rows, {})

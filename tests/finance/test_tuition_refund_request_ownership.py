"""Fail-closed refund approval identity tests without a Frappe site.

The real helper is extracted from the source AST and executed with a stubbed
database. These tests never create, approve or pay actual financial documents.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = (Path(__file__).resolve().parents[2] / "apps" / "toefl_house" /
          "toefl_house" / "finance" / "tuition_refund_commands.py")


class _DB:
    def __init__(self, fee):
        self.fee = fee
        self.calls = []

    def get_value(self, doctype, name, fields, *, as_dict, for_update):
        self.calls.append((doctype, name, tuple(fields), as_dict, for_update))
        return self.fee


class TuitionRefundOwnershipTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        functions = {node.name: node for node in tree.body
                     if isinstance(node, ast.FunctionDef)}
        self.assertIn("_require_request_fee_identity", functions)
        self.functions = functions
        self.fee = SimpleNamespace(docstatus=1, student="ST-1", company="CO-1")
        self.db = _DB(self.fee)
        self.scope_calls = []

        class ValidationError(Exception):
            pass

        self.ValidationError = ValidationError
        namespace = {
            "frappe": SimpleNamespace(db=self.db, ValidationError=ValidationError),
            "FEES": "Fees",
            "_require_target_company": self.scope_calls.append,
        }
        exec(compile(ast.Module(body=[functions["_require_request_fee_identity"]],
                                type_ignores=[]), str(SOURCE), "exec"), namespace)
        self.check = namespace["_require_request_fee_identity"]
        self.req = SimpleNamespace(fees="FEE-1", student="ST-1", company="CO-1")

    def test_matching_submitted_fee_is_locked_and_scoped(self):
        self.check(self.req)
        self.assertEqual(self.db.calls, [
            ("Fees", "FEE-1", ("docstatus", "student", "company"), True, True)])
        self.assertEqual(self.scope_calls, ["FEE-1"])

    def test_missing_draft_cancelled_or_wrong_owner_fails_before_scope(self):
        invalid = [
            None,
            SimpleNamespace(docstatus=0, student="ST-1", company="CO-1"),
            SimpleNamespace(docstatus=2, student="ST-1", company="CO-1"),
            SimpleNamespace(docstatus=1, student="ST-OTHER", company="CO-1"),
            SimpleNamespace(docstatus=1, student="ST-1", company="CO-OTHER"),
        ]
        for fee in invalid:
            with self.subTest(fee=fee):
                self.db.fee = fee
                self.scope_calls.clear()
                with self.assertRaisesRegex(self.ValidationError, "does not match"):
                    self.check(self.req)
                self.assertEqual(self.scope_calls, [])

    def test_all_gm_transitions_revalidate_and_lock_fee_before_request(self):
        for command in ("approve_tuition_refund", "deny_tuition_refund",
                        "void_tuition_refund"):
            with self.subTest(command=command):
                fn = self.functions[command]
                source = ast.get_source_segment(SOURCE.read_text(encoding="utf-8"), fn)
                self.assertIn("_require_request_fee_identity(req)", source)
                self.assertIn("select name from `tabFees` where name=%s for update", source)
                self.assertLess(source.index("select name from `tabFees` where name=%s for update"),
                                source.index("req = _pending_request("))
                self.assertIn("if req.fees != fees:", source)
                self.assertIn("Refund request Fees link changed during lock acquisition", source)
                self.assertLess(source.index("req = _pending_request("),
                                source.index("if req.fees != fees:"))
                self.assertLess(source.index("if req.fees != fees:"),
                                source.index("_require_request_fee_identity(req)"))


if __name__ == "__main__":
    unittest.main()

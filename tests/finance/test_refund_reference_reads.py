"""Exact refund-pair reference authority; native DB qualification is separate."""
import ast
from contextvars import ContextVar
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch


class RefundReferenceAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.context = ContextVar("test_exact_refund_pair", default=None)
        self.frappe = types.SimpleNamespace(PermissionError=PermissionError,
                                           session=types.SimpleNamespace(user="payer"))
        self.kind = "pay_tuition_refund"
        self.scope = types.ModuleType("toefl_house.command_scope")
        self.scope.authorize_command_scope = Mock()
        source = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house/finance/tuition_refund_native.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "assert_reference_lease")
        namespace = dict(_PAIR=self.context, frappe=self.frappe, active_command_kind=lambda: self.kind)
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
        self.authorize = namespace["assert_reference_lease"]
        self.refs = [("Fees", "FEE"), ("Student", "STUDENT")]
        self.pair = types.SimpleNamespace(request="CASE", payer="payer", approver="manager",
                                         fee=types.SimpleNamespace(name="FEE", student="STUDENT"))
        modules = patch.dict("sys.modules", {"toefl_house.command_scope": self.scope})
        modules.start()
        self.addCleanup(modules.stop)

    def test_even_exact_reference_names_need_the_private_pair_context(self):
        with self.assertRaises(PermissionError):
            self.authorize(self.refs)
        self.scope.authorize_command_scope.assert_not_called()

    def test_pair_rechecks_its_request_company_and_student_branch_authority(self):
        self.context.set(self.pair)
        self.authorize(self.refs)
        self.scope.authorize_command_scope.assert_called_once_with("pay_tuition_refund",
            {"request": "CASE", "fees": "FEE", "student": "STUDENT"}, "payer")

    def test_other_references_actor_command_and_self_approval_are_refused(self):
        cases = [
            ("pay_tuition_refund", "payer", "manager", [("Fees", "OTHER"), ("Student", "STUDENT")]),
            ("pay_tuition_refund", "other", "manager", self.refs),
            ("request_tuition_refund", "payer", "manager", self.refs),
            ("pay_tuition_refund", "payer", "payer", self.refs),
        ]
        for kind, actor, approver, refs in cases:
            with self.subTest(kind=kind, actor=actor, approver=approver):
                self.context.set(self.pair)
                self.kind = kind
                self.frappe.session.user = actor
                self.pair.approver = approver
                with self.assertRaises(PermissionError):
                    self.authorize(refs)
        self.scope.authorize_command_scope.assert_not_called()


if __name__ == "__main__":
    unittest.main()

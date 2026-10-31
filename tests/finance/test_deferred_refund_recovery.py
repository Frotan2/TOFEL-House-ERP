"""Deferred recovery cannot be enabled by a caller, configuration or role."""
import ast
from pathlib import Path
import types
import unittest


class DeferredRecoveryTests(unittest.TestCase):
    def test_gate_refuses_every_payload_before_database_access(self):
        source = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house/finance/refund_feature_gate.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
        function.decorator_list = []
        namespace = {"frappe": types.SimpleNamespace(PermissionError=PermissionError)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
        for payload in ({}, {"enable": True}, {"ignore_permissions": True},
                        {"role": "Course Owner", "production_active": True}):
            with self.subTest(payload=payload), self.assertRaisesRegex(PermissionError, "not available in this release"):
                namespace[function.name](**payload)

    def test_every_deferred_route_maps_to_the_same_closed_server_gate(self):
        root = Path(__file__).resolve().parents[2]
        tree = ast.parse((root / "apps/toefl_house/toefl_house/hooks.py").read_text(encoding="utf-8"))
        mapping = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "override_whitelisted_methods" for target in node.targets))
        prefix = "toefl_house.finance.tuition_refund_reversal_commands."
        for method in ("request_tuition_refund_reversal", "approve_tuition_refund_reversal",
                       "deny_tuition_refund_reversal", "reverse_tuition_refund"):
            self.assertEqual(mapping[prefix + method], "toefl_house.finance.refund_feature_gate.disabled_paid_recovery")
        self.assertFalse((root / "apps/toefl_house/toefl_house/finance/tuition_refund_reversal_commands.py").exists())

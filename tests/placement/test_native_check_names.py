"""Static consistency guard: every api.NAME referenced in the hosted native
checks must exist at module level in toefl_house/api.py.

This catches attribute-name drift (e.g. api.BP vs api.BLUEPRINT) locally,
before it can fail only on the hosted runner. Pure AST; imports nothing
from the app.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "tools/placement/native_checks.py"
API = ROOT / "apps/toefl_house/toefl_house/api.py"
ADMISSION = ROOT / "apps/toefl_house/toefl_house/admission/__init__.py"
ENROLLMENT = ROOT / "apps/toefl_house/toefl_house/enrollment/__init__.py"


def _module_level_names(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names


def _api_attribute_uses(tree, name="api"):
    used = set()

    class Visitor(ast.NodeVisitor):
        def visit_Attribute(self, node):
            if isinstance(node.value, ast.Name) and node.value.id == name:
                used.add(node.attr)
            self.generic_visit(node)

    Visitor().visit(tree)
    return used


class NativeCheckNameGuardTests(unittest.TestCase):
    def test_native_check_api_references_resolve(self):
        used = _api_attribute_uses(ast.parse(NATIVE.read_text(encoding="utf-8")))
        defined = _module_level_names(ast.parse(API.read_text(encoding="utf-8")))
        self.assertTrue(used, "expected api.* references in native_checks.py")
        missing = sorted(used - defined)
        self.assertEqual(
            missing,
            [],
            "native_checks.py references api names not defined in api.py: %s" % missing,
        )

    def test_native_check_admission_references_resolve(self):
        used = _api_attribute_uses(ast.parse(NATIVE.read_text(encoding="utf-8")), "adm")
        defined = _module_level_names(ast.parse(ADMISSION.read_text(encoding="utf-8")))
        self.assertTrue(used, "expected adm.* references in native_checks.py")
        missing = sorted(used - defined)
        self.assertEqual(
            missing,
            [],
            "native_checks.py references admission names not defined: %s" % missing,
        )

    def test_native_check_enrollment_references_resolve(self):
        used = _api_attribute_uses(ast.parse(NATIVE.read_text(encoding="utf-8")), "enr")
        defined = _module_level_names(ast.parse(ENROLLMENT.read_text(encoding="utf-8")))
        self.assertTrue(used, "expected enr.* references in native_checks.py")
        missing = sorted(used - defined)
        self.assertEqual(
            missing,
            [],
            "native_checks.py references enrollment names not defined: %s" % missing,
        )


if __name__ == "__main__":
    unittest.main()

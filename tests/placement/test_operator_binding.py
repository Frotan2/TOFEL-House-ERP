"""A verified attempt belongs to its verifying invigilator, not the role group."""
import ast
from pathlib import Path
import types
import unittest

SOURCE = (Path(__file__).resolve().parents[2] /
          "apps/toefl_house/toefl_house/api.py").read_text(encoding="utf-8")
FN = next(node for node in ast.parse(SOURCE).body
          if isinstance(node, ast.FunctionDef) and node.name == "_require_session_operator")


class Refused(Exception):
    pass


class Invalid(Exception):
    pass


class OperatorBindingTests(unittest.TestCase):
    def setUp(self):
        env = {"frappe": types.SimpleNamespace(PermissionError=Refused, ValidationError=Invalid)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[FN], type_ignores=[])),
                     "api.py", "exec"), env)
        self.guard = env["_require_session_operator"]

    def test_verified_and_in_progress_are_pinned_to_one_invigilator(self):
        for status in ("Verified", "In Progress"):
            row = types.SimpleNamespace(allocated_by="publisher",
                verified_by="invigilator-one", mode="Digital", status=status)
            with self.subTest(status=status):
                self.assertIsNone(self.guard("invigilator-one", row))
                for actor in ("publisher", "invigilator-two"):
                    with self.assertRaises(Refused):
                        self.guard(actor, row)

    def test_allocation_still_allows_independent_initial_verification(self):
        row = types.SimpleNamespace(allocated_by="publisher",
            verified_by=None, mode="Digital", status="Allocated")
        self.assertIsNone(self.guard("invigilator-one", row))
        with self.assertRaises(Refused):
            self.guard("publisher", row)

    def test_physical_mode_does_not_gain_unimplemented_digital_actions(self):
        row = types.SimpleNamespace(allocated_by="publisher",
            verified_by="invigilator-one", mode="Physical", status="In Progress")
        with self.assertRaises(Invalid):
            self.guard("invigilator-one", row)


if __name__ == "__main__":
    unittest.main()

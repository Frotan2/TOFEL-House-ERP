"""The invigilator attempt picker is bounded and explicitly branch-authorized."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SRC = (ROOT / "apps/toefl_house/toefl_house/api.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)


class SupervisedAttemptPickerTests(unittest.TestCase):
    def test_source_requires_role_and_branch_filters_before_read(self):
        fn = next(n for n in TREE.body if isinstance(n, ast.FunctionDef)
                  and n.name == "supervised_attempt_choices")
        body = ast.get_source_segment(SRC, fn)
        for required in (
            'authorize("Placement Invigilator")',
            "branches = actor_branches(actor)",
            'filters={"th_branch": ("in", sorted(branches))}',
            '"case_name": ("in", list(by_case))',
            '"status": ("in", ["Allocated", "Verified", "In Progress"])',
            "if len(cases) >= max_cases:",
            "if len(attempts) >= limit:",
            'if row.get("allocated_by") == actor:',
        ):
            with self.subTest(required=required):
                self.assertIn(required, body)
        for forbidden in (".insert(", ".save(", "_manifest_form(", "_key_catalog("):
            self.assertNotIn(forbidden, body)


if __name__ == "__main__":
    unittest.main()

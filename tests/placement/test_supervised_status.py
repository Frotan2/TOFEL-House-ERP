"""Status reads return no question content before verified timed delivery."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "apps/toefl_house/toefl_house/api.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

class PlacementStatusSafetyTests(unittest.TestCase):
    def test_status_read_requires_invigilator_and_branch(self):
        fn = next(n for n in TREE.body if isinstance(n, ast.FunctionDef)
                  and n.name == "supervised_attempt_status")
        source = ast.get_source_segment(SOURCE, fn)
        for clause in (
            'authorize("Placement Invigilator")',
            "_require_session_operator(actor, row)",
            "branch not in allowed",
            "deadline_reached(_now()",
            '"read_only": True',
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, source)
        self.assertNotIn("project_form(", source)
        self.assertNotIn("form_json", source)
        self.assertNotIn("_latest_responses(", source)
        self.assertNotIn(".save(", source)
        self.assertNotIn(".insert(", source)

if __name__ == "__main__":
    unittest.main()

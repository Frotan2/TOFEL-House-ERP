"""Supervised digital placement recovery: static security invariants.

Native, role-backed authorization tests are still required before live use.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "apps/toefl_house/toefl_house/api.py"
SOURCE = API.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

class SupervisedPlacementReadTests(unittest.TestCase):
    def test_read_endpoint_checks_live_role_branch_state_and_deadline(self):
        fn = next(x for x in TREE.body if isinstance(x, ast.FunctionDef)
                  and x.name == "supervised_attempt_view")
        body = ast.get_source_segment(SOURCE, fn)
        self.assertIn('authorize("Placement Invigilator")', body)
        self.assertIn("_require_session_operator(actor, row)", body)
        self.assertIn("case_branch not in allowed", body)
        self.assertIn('row.status != "In Progress"', body)
        self.assertIn("deadline_reached(", body)
        self.assertIn("_manifest_form(", body)
        self.assertIn("project_form(", body)
        self.assertIn("_latest_responses(", body)
        self.assertIn("return {", body)
        self.assertNotIn("return form", body)
        self.assertNotIn("seed\":", body)

    def test_read_endpoint_is_get_only_and_doctype_write_free(self):
        fn = next(x for x in TREE.body if isinstance(x, ast.FunctionDef)
                  and x.name == "supervised_attempt_view")
        source = ast.get_source_segment(SOURCE, fn)
        self.assertIn('@frappe.whitelist(methods=["GET"])', SOURCE[
            max(0, SOURCE.find(source) - 70):SOURCE.find(source)])
        self.assertNotIn(".insert(", source)
        self.assertNotIn(".save(", source)
        self.assertNotIn(".delete(", source)

if __name__ == "__main__":
    unittest.main()

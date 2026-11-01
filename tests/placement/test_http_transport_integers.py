"""Integer web-transport compatibility without loosening domain invariants."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SRC = (ROOT / "apps/toefl_house/toefl_house/api.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)


class ValidationError(Exception):
    pass


def helper():
    f = next(x for x in TREE.body if isinstance(x, ast.FunctionDef)
             and x.name == "_web_integer")
    f.decorator_list = []
    namespace = {"frappe": type("Frappe", (), {"ValidationError": ValidationError})()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[f], type_ignores=[])),
                 "api.py", "exec"), namespace)
    return namespace["_web_integer"]


class PlacementHTTPIntegerTests(unittest.TestCase):
    def test_canonical_form_integers_are_supported(self):
        to_int = helper()
        for value, expected in ((1, 1), ("1", 1), ("120", 120), ("0", 0)):
            with self.subTest(value=value):
                self.assertEqual(to_int(value, "field", minimum=0), expected)

    def test_ambiguous_or_malformed_values_are_denied(self):
        to_int = helper()
        for value in ("", "01", "+1", "-1", " 1", "1 ", "1.0", "۱", "١",
                      "3e2", "false", 1.0, True, False, None, [], {}, "0" * 1000):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValidationError):
                    to_int(value, "field")

    def test_answer_revisions_and_flags_keep_their_bounds(self):
        to_int = helper()
        self.assertEqual(to_int("0", "expected_revision", minimum=0), 0)
        self.assertEqual(to_int("1", "missing", minimum=0, maximum=1), 1)
        for value in ("2", 2, "-1", 1.1):
            with self.assertRaises(ValidationError):
                to_int(value, "missing", minimum=0, maximum=1)

    def test_public_exam_commands_normalize_before_work(self):
        names = {
            "verify_attempt", "deliver_attempt", "save_response", "seal_attempt",
            "score_attempt", "review_attempt", "finalize_attempt", "release_decision",
            "allocate_attempt",
            "create_draft", "revise_draft", "publish",
            "create_draft_config", "revise_draft_config",
            "review_config", "publish_config", "retire_config",
        }
        for node in TREE.body:
            if not isinstance(node, ast.FunctionDef) or node.name not in names:
                continue
            with self.subTest(command=node.name):
                code = ast.get_source_segment(SRC, node)
                self.assertIn("_web_integer(", code)
                self.assertLess(code.index("_web_integer("), code.index("def work(actor):"))

if __name__ == "__main__":
    unittest.main()

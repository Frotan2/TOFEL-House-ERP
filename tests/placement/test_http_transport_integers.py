"""Integer web-transport compatibility without loosening domain invariants."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SRC = (ROOT / "apps/toefl_house/toefl_house/api.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)


class ValidationError(Exception):
    pass


def helper(frappe=None):
    f = next(x for x in TREE.body if isinstance(x, ast.FunctionDef)
             and x.name == "_web_integer")
    f.decorator_list = []
    namespace = {"frappe": frappe if frappe is not None else type("Frappe", (), {"ValidationError": ValidationError})()}
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

    def test_admission_commands_normalize_before_idempotency(self):
        path = ROOT / "apps/toefl_house/toefl_house/admission/__init__.py"
        commands = [
            node for node in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef)
            and any(arg.arg == "expected_version" for arg in node.args.args)
            and node.decorator_list
        ]
        self.assertEqual(len(commands), 8)
        for command in commands:
            with self.subTest(command=command.name):
                command.decorator_list = []
                namespace = {
                    "_web_integer": helper(),
                    "_execute": lambda kind, key, payload, work: payload,
                }
                exec(compile(ast.Module(body=[command], type_ignores=[]), str(path), "exec"), namespace)
                call = namespace[command.name]
                args = dict(request_key="synthetic-request", name="decision", expected_version="2")
                extras = {"outcome": "Approved", "reason": "Reason", "evidence": "Evidence"}
                args.update({arg.arg: extras[arg.arg] for arg in command.args.args if arg.arg in extras})
                self.assertEqual(call(**args)["expected_version"], 2)
                args["expected_version"] = "02"
                with self.assertRaises(ValidationError):
                    call(**args)

    def test_class_creation_normalizes_form_capacity(self):
        path = ROOT / "apps/toefl_house/toefl_house/teaching/__init__.py"
        command = next(
            node for node in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef) and node.name == "create_student_group"
        )
        command.decorator_list = []
        namespace = {"_web_integer": helper(), "_execute": lambda kind, key, payload, work: payload}
        exec(compile(ast.Module(body=[command], type_ignores=[]), str(path), "exec"), namespace)
        call = namespace["create_student_group"]
        self.assertEqual(call("request", "group", "program", "year", max_strength="2")["max_strength"], 2)
        for value in ("0", "02", "501"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                call("request", "group", "program", "year", max_strength=value)

if __name__ == "__main__":
    unittest.main()

"""Isolated executable checks for the real supervised-placement GET source.

The exercise compiles the source function without its decorator, injects a
small schema-aware Frappe seam, and uses the real pure question projection.
It is a security regression, not a substitute for native HTTP/DB acceptance.
"""
import ast
import copy
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
API_FILE = ROOT / "apps/toefl_house/toefl_house/api.py"
POLICY_FILE = ROOT / "apps/toefl_house/toefl_house/policy.py"


class Denied(Exception):
    pass


class Invalid(Exception):
    pass


def isolated_functions():
    source = API_FILE.read_text(encoding="utf-8")
    parsed = ast.parse(source)
    names = {"supervised_attempt_view", "_require_session_operator"}
    functions = []
    for node in parsed.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            functions.append(fn)
    assert {fn.name for fn in functions} == names
    code = compile(ast.fix_missing_locations(ast.Module(
        body=functions, type_ignores=[])), str(API_FILE), "exec")
    namespace = {}
    exec(code, namespace)
    return namespace


def read_policy():
    spec = importlib.util.spec_from_file_location("isolated_placement_policy", POLICY_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SupervisedRecoveryRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.actor = "invigilator@example.test"
        self.branch = "Branch Alpha"
        self.allowed = {"Branch Alpha"}
        self.status = "In Progress"
        self.deadline = "2026-09-17 11:00:00"
        self.item_status = "Published"
        self.authorized = True
        self.responses = {1: {"option_id": "b", "revision": 3, "missing": 0}}
        self.get_doc_calls = []
        policy = read_policy()
        functions = isolated_functions()
        self.form = {
            "attempt": "ATT-1", "case": "CASE-1", "subject": "candidate@example.test",
            "sections": [{"id": "vocab", "skill": "Vocabulary", "minutes": 20, "item_count": 1}],
            "items": [{
                "order": 1, "occurrence_id": "O-1", "item": "ITEM-1",
                "section": "vocab", "skill": "Vocabulary", "difficulty": "Core",
                "question_type": "Single Choice", "option_order": ["b", "a"],
                "family": "TOP-SECRET-FAMILY", "answer": "a",
            }],
            "seed": "NEVER-EXPOSE-THIS-SEED",
        }
        obj = self

        def get_value(doctype, target, fields, as_dict=False):
            if doctype == "TH Placement Attempt" and as_dict:
                if target != "ATT-1":
                    return None
                return types.SimpleNamespace(
                    name="ATT-1", case_name="CASE-1",
                    allocated_by="different@example.test", verified_by=obj.actor, mode="Digital",
                    status=obj.status, version=3,
                    started_at="2026-09-17 09:00:00", deadline_at=obj.deadline)
            if doctype == "TH Placement Case" and fields == "th_branch":
                return obj.branch
            raise AssertionError(f"Unexpected DB read {doctype}/{fields}")

        def get_all(doctype, filters=None, fields=None, ignore_permissions=False):
            self.assertEqual(doctype, "TH Placement Item Revision")
            self.assertEqual(filters, {"name": ("in", ["ITEM-1"])})
            self.assertNotIn("answer", fields)
            return [types.SimpleNamespace(
                name="ITEM-1", status=obj.item_status, prompt="Choose the correct word",
                question_type="Single Choice",
                options_json='[{"id":"a","text":"First"},{"id":"b","text":"Second"}]')]

        frappe = types.ModuleType("frappe")
        frappe.PermissionError = Denied
        frappe.ValidationError = Invalid
        frappe.db = types.SimpleNamespace(get_value=get_value)
        frappe.get_all = get_all

        def authorize(role):
            if role != "Placement Invigilator" or not obj.authorized:
                raise Denied("Wrong role")
            return obj.actor

        functions["supervised_attempt_view"].__globals__.update({
            "frappe": frappe,
            "json": json,
            "authorize": authorize,
            "_now": lambda: datetime(2026, 9, 17, 10, 0),
            "get_datetime": lambda raw: datetime.fromisoformat(str(raw)),
            "deadline_reached": policy.deadline_reached,
            "ATTEMPT": "TH Placement Attempt",
            "CASE": "TH Placement Case",
            "ITEM": "TH Placement Item Revision",
            "_manifest_form": lambda name: (None, obj.form),
            "_latest_responses": lambda name: obj.responses,
            "project_form": policy.project_form,
            "_iso": lambda value: str(value),
        })
        self.read = functions["supervised_attempt_view"]
        self.read.__globals__["_require_session_operator"] = functions["_require_session_operator"]
        scope = types.ModuleType("toefl_house.command_scope")
        scope.actor_branches = lambda actor: obj.allowed
        package = types.ModuleType("toefl_house")
        package.__path__ = []
        self.sys_patch = patch.dict(sys.modules, {
            "toefl_house": package, "toefl_house.command_scope": scope,
        })
        self.sys_patch.start()
        self.addCleanup(self.sys_patch.stop)

    def test_valid_session_returns_only_safe_projection_and_latest_response(self):
        result = self.read("ATT-1")
        self.assertEqual(result["version"], 3)
        self.assertEqual(result["responses"][0]["option_id"], "b")
        self.assertEqual(result["responses"][0]["revision"], 3)
        self.assertEqual([x["id"] for x in result["projection"]["items"][0]["options"]], ["b", "a"])
        visible = json.dumps(result)
        self.assertNotIn("NEVER-EXPOSE-THIS-SEED", visible)
        self.assertNotIn("TOP-SECRET-FAMILY", visible)
        self.assertNotIn('"answer"', visible)
        self.assertNotIn('"item"', visible)

    def test_wrong_role_and_branch_are_denied(self):
        self.authorized = False
        with self.assertRaises(Denied):
            self.read("ATT-1")
        self.authorized = True
        for branch, allowed in ((None, {"Branch Alpha"}), ("Branch Beta", {"Branch Alpha"}),
                                ("Branch Alpha", None)):
            with self.subTest(branch=branch, allowed=allowed):
                self.branch, self.allowed = branch, allowed
                with self.assertRaises(Denied):
                    self.read("ATT-1")

    def test_expired_or_nonactive_attempt_will_not_expose_form(self):
        self.deadline = "2026-09-17 09:00:00"
        with self.assertRaisesRegex(Invalid, "time has ended"):
            self.read("ATT-1")
        self.deadline = "2026-09-17 11:00:00"
        for status in ("Allocated", "Verified", "Sealed", "Finalized"):
            with self.subTest(status=status):
                self.status = status
                with self.assertRaisesRegex(Invalid, "in-progress"):
                    self.read("ATT-1")

    def test_missing_or_withdrawn_item_is_denied(self):
        self.item_status = "Retired"
        with self.assertRaisesRegex(Invalid, "withdrawn"):
            self.read("ATT-1")

    def test_unknown_attempt_is_not_enumerated(self):
        with self.assertRaisesRegex(Invalid, "does not exist"):
            self.read("ATT-UNKNOWN")


if __name__ == "__main__":
    unittest.main()

"""Native discount form and REST must never bypass Owner approval commands.

These tests execute the actual controller validator under the same command
context implementation used by configuration_audit, with an isolated Frappe
PermissionError stub. No real student/financial data is touched.
"""
import ast
import json
import sys
import types
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
sys.path.insert(0, str(APP))
from toefl_house.configuration import rules as config_rules  # noqa: E402
from toefl_house.academic import rules as academic_rules  # noqa: E402

CONTROLLER = APP / "toefl_house/academic/doctype/th_discount_rule/th_discount_rule.py"
SCHEMA = APP / "toefl_house/academic/doctype/th_discount_rule/th_discount_rule.json"
COMMANDS = APP / "toefl_house/academic/__init__.py"


class Denied(Exception):
    pass


def load_validator():
    tree = ast.parse(CONTROLLER.read_text(encoding="utf-8"))
    target = [x for x in tree.body
              if isinstance(x, ast.FunctionDef) and x.name == "validate"]
    assert len(target) == 1
    code = compile(ast.Module(body=target, type_ignores=[]), str(CONTROLLER), "exec")
    fake = types.SimpleNamespace(PermissionError=Denied, throw=lambda msg: (_ for _ in ()).throw(Denied(msg)))
    scope = {"frappe": fake, "_": lambda s: s, "rules": academic_rules,
             "configuration_rules": config_rules}
    exec(code, scope)
    return scope["validate"]


class Doc:
    code = "NAMED-10"
    title = "Named course discount"
    discount_percentage = 10
    precedence = 1
    status = "Retired"

    def get(self, key):
        return {"student": "STU-1", "description": "Specific case approved by Owner"}[key]


class DiscountWriteAuthorityTests(unittest.TestCase):
    def test_form_save_and_rest_save_fail_without_command(self):
        validator = load_validator()
        with self.assertRaisesRegex(Denied, "guided configuration"):
            validator(Doc(), method="validate")

    def test_unrelated_config_command_does_not_authorize_discount_edits(self):
        validator = load_validator()
        with config_rules.command_context("set_level_fee_component"):
            with self.assertRaisesRegex(Denied, "audited discount"):
                validator(Doc())

    def test_exact_create_and_activation_commands_pass(self):
        validator = load_validator()
        for name in ("create_discount_rule", "set_discount_rule_status"):
            with self.subTest(command=name), config_rules.command_context(name):
                validator(Doc())

    def test_schema_is_inactive_by_default(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        status = next(x for x in schema["fields"] if x["fieldname"] == "status")
        self.assertEqual(status["default"], "Retired")

    def test_create_command_never_applies_discount_immediately(self):
        source = COMMANDS.read_text(encoding="utf-8")
        create = source.split("def create_discount_rule(", 1)[1].split(
            '\n@frappe.whitelist(methods=["POST"])', 1)[0]
        self.assertIn('"status": "Retired"', create)
        status = source.split("def set_discount_rule_status(", 1)[1].split(
            '\ndef _assessment_policy_doc', 1)[0]
        self.assertIn('if not doc.student:', status)
        self.assertIn('if not frappe.db.exists("Student", doc.student):', status)


if __name__ == "__main__":
    unittest.main()

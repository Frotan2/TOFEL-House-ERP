"""Real academic creation commands must not duplicate names behind new IDs.

AST extraction invokes the production code with framework doubles and refuses
duplicate records before any native Course, Program or policy is inserted.
These checks do not touch a real institute database.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

SRC = (Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
       / "toefl_house" / "academic" / "__init__.py")


def load_command(name, namespace):
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    functions = [n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(functions) == 1
    functions[0].decorator_list = []
    exec(compile(ast.Module(body=functions, type_ignores=[]),
                 str(SRC), "exec"), namespace)
    return namespace[name]


class CatalogUniquenessTests(unittest.TestCase):
    def context(self, doctype_and_query, *, level=False):
        queries = []
        def exists(doctype, name):
            queries.append((doctype, name))
            return doctype == doctype_and_query[0] and name == doctype_and_query[1]
        db = SimpleNamespace(
            exists=exists, get_all=Mock(return_value=[]),
            get_value=Mock(return_value="TH Academic Program"))
        get_doc = Mock(side_effect=AssertionError(
            "Cannot insert ANY record when a duplicate is detected"))
        frappe = SimpleNamespace(db=db, get_doc=get_doc, ValidationError=ValueError)
        rules = SimpleNamespace(
            validate_code=lambda value: value,
            validate_title=lambda value, what: value,
            validate_reason=lambda value: value,
            validate_sequence=lambda value: value,
            validate_duration_value=lambda value, unit: value,
            parse_date=lambda value: value,
        )
        family = SimpleNamespace(name="GEN-ENG", title="General English",
                                 status="Active")
        context = {
            "frappe": frappe, "rules": rules,
            "PROGRAM": "TH Academic Program",
            "LEVEL": "TH Program Level",
            "NATIVE_PROGRAM": "Program",
            "ASSESSMENT_POLICY": "TH Assessment Policy",
            "validate_request_key": lambda request_key: None,
            "_family_doc": lambda code, for_update: family,
            "configuration_audit": SimpleNamespace(
                execute=lambda operation, key, payload, callback: callback("Course Owner")),
        }
        return context, get_doc, queries

    def test_program_duplicate_title_is_not_created_with_new_code(self):
        ctx, get_doc, queries = self.context(
            ("TH Academic Program", {"title": "General English"}))
        command = load_command("create_program", ctx)
        with self.assertRaisesRegex(ValueError, "name already exists"):
            command("key", "NEW-GE", "General English", "")
        get_doc.assert_not_called()
        self.assertIn(("TH Academic Program", {"title": "General English"}), queries)
        ctx["frappe"].db.get_value.assert_called_once_with(
            "DocType", "TH Academic Program", "name", for_update=True)

    def test_level_duplicate_title_in_same_family_is_rejected(self):
        ctx, get_doc, queries = self.context(
            ("TH Program Level", {"family": "GEN-ENG", "title": "Starter"}))
        command = load_command("create_level", ctx)
        with self.assertRaisesRegex(ValueError, "level with this name"):
            command("key", "GEN-ENG", "NEW-STARTER", "Starter", 1, 2,
                    "Solar Hijri Month", "2026-11-01")
        get_doc.assert_not_called()

    def test_native_collisions_refused_before_course_insertion(self):
        cases = [
            ("Course", {"course_name": "General English — Starter"}),
            ("Program", {"program_name": "General English — Starter"}),
            ("Program", {"program_abbreviation": "NEW-STARTER"}),
        ]
        for name, selector in cases:
            with self.subTest(name=name, selector=selector):
                ctx, get_doc, queries = self.context((name, selector))
                command = load_command("create_level", ctx)
                with self.assertRaisesRegex(ValueError, "duplicate curriculum"):
                    command("key", "GEN-ENG", "NEW-STARTER", "Starter", 1, 2,
                            "Solar Hijri Month", "2026-11-01")
                get_doc.assert_not_called()
                self.assertIn((name, selector), queries)

    def test_duplicate_assessment_policy_title_is_not_created(self):
        ctx, get_doc, queries = self.context(
            ("TH Assessment Policy",
             {"family": "GEN-ENG", "title": "General English Assessment"}))
        command = load_command("create_assessment_policy", ctx)
        with self.assertRaisesRegex(ValueError, "already has an assessment policy"):
            command("key", "GEN-ENG", "GE-ASSESS-NEW",
                    "General English Assessment")
        get_doc.assert_not_called()


if __name__ == "__main__":
    unittest.main()

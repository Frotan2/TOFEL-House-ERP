"""Pinned email-optional native integration and no surrogate User creation."""
import ast
import json
from pathlib import Path
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"


class OptionalEmailFixtureTests(unittest.TestCase):
    def test_native_field_override_is_explicit_and_reversible(self):
        setters = json.loads((APP / "fixtures/property_setter.json").read_text())
        self.assertEqual(setters, [{
            "doctype": "Property Setter", "name": "Student-student_email_id-reqd",
            "doc_type": "Student", "doctype_or_field": "DocField",
            "field_name": "student_email_id", "property": "reqd",
            "property_type": "Check", "value": "0",
        }])
        hook = (APP / "hooks.py").read_text()
        self.assertIn('"dt": "Property Setter"', hook)

    def test_native_student_controller_does_not_autocreate_users(self):
        hook = (APP / "hooks.py").read_text()
        code = (APP / "admission/native_student.py").read_text()
        self.assertIn('"Student": "toefl_house.admission.native_student.THEmailOptionalStudent"', hook)
        self.assertIn('class THEmailOptionalStudent(Student)', code)
        self.assertIn('def validate_user(self):', code)
        self.assertNotIn('.insert(', code)
        self.assertNotIn('.save(', code)

    def test_native_student_never_provisions_an_unsolicited_website_user(self):
        source = (APP / "admission/native_student.py").read_text()
        tree = ast.parse(source)
        controller = next(node for node in tree.body
                          if isinstance(node, ast.ClassDef) and
                          node.name == "THEmailOptionalStudent")
        method = next(node for node in controller.body
                      if isinstance(node, ast.FunctionDef) and
                      node.name == "validate_user")
        scope = {"frappe": types.SimpleNamespace(
            db=types.SimpleNamespace(get_value=lambda *_args: "verified@example.test"),
            PermissionError=PermissionError)}
        exec(compile(ast.fix_missing_locations(ast.Module(
            body=[method], type_ignores=[])), "native_student.py", "exec"), scope)
        guard = scope["validate_user"]
        for student in (
            types.SimpleNamespace(user=None, student_email_id=None),
            types.SimpleNamespace(user=None, student_email_id="real@example.test"),
        ):
            with self.subTest(student=repr(student)):
                self.assertIsNone(guard(student))
        with self.assertRaises(PermissionError):
            guard(types.SimpleNamespace(
                user="staff@example.test", student_email_id=None))
        self.assertIsNone(guard(types.SimpleNamespace(
            user="staff@example.test", student_email_id="verified@example.test")))

    def test_candidate_id_fields_are_native_links_not_fake_email(self):
        data = json.loads((APP / "fixtures/custom_field.json").read_text())
        for dt in ("Student", "Student Applicant"):
            fields = [x for x in data if x.get("dt") == dt and x.get("fieldname") == "th_candidate_ref"]
            self.assertEqual(len(fields), 1)
            self.assertEqual(fields[0]["unique"], 1)
            self.assertEqual(fields[0]["read_only"], 1)


if __name__ == "__main__":
    unittest.main()

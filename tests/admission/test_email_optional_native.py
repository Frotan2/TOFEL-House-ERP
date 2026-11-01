"""Pinned email-optional native integration and no surrogate User creation."""
import json
from pathlib import Path
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

    def test_candidate_id_fields_are_native_links_not_fake_email(self):
        data = json.loads((APP / "fixtures/custom_field.json").read_text())
        for dt in ("Student", "Student Applicant"):
            fields = [x for x in data if x.get("dt") == dt and x.get("fieldname") == "th_candidate_ref"]
            self.assertEqual(len(fields), 1)
            self.assertEqual(fields[0]["unique"], 1)
            self.assertEqual(fields[0]["read_only"], 1)


if __name__ == "__main__":
    unittest.main()

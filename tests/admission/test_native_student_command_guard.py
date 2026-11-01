"""Execute the native Student and Applicant production write gates.

No real Student is created; only the source's actual controller methods and
validation hook are run against isolated native stubs.
"""
import ast
from pathlib import Path
import types
import unittest

SOURCE = (Path(__file__).resolve().parents[2] /
          "apps/toefl_house/toefl_house/admission/native_student.py").read_text()
TREE = ast.parse(SOURCE)


class Denied(Exception):
    pass


class Invalid(Exception):
    pass


class Doc:
    def __init__(self, fields, new=True):
        self.fields = fields
        self.name = "STU-1"
        self.new = new

    def get(self, field):
        return self.fields.get(field)

    def is_new(self):
        return self.new

    def validate(self):
        return "native Education validations"


class CommandGuardTests(unittest.TestCase):
    def setUp(self):
        self.kind = None
        self.production = True
        self.previous = {
            "student_applicant": "APP-1", "th_candidate_ref": "THV-ABC",
            "th_reception_inquiry": "INQ-1",
        }
        fake = self
        def get_value(doctype, name, fields, as_dict=False):
            return {field: fake.previous.get(field) for field in fields}
        funcs = [node for node in TREE.body if isinstance(node, ast.FunctionDef) and
                 node.name in ("_protect_candidate_provenance", "protect_applicant_identity")]
        cls = next(node for node in TREE.body if isinstance(node, ast.ClassDef)
                   and node.name == "THEmailOptionalStudent")
        globals_ = {
            "frappe": types.SimpleNamespace(
                db=types.SimpleNamespace(get_value=get_value),
                ValidationError=Invalid, PermissionError=Denied),
            "active_command_kind": lambda: fake.kind,
            "is_production": lambda: fake.production,
            "Student": Doc,
        }
        exec(compile(ast.fix_missing_locations(ast.Module(
            body=funcs + [cls], type_ignores=[])),
            "native_student.py", "exec"), globals_)
        self.applicant_guard = globals_["protect_applicant_identity"]
        self.student = globals_["THEmailOptionalStudent"]

    def test_direct_native_student_creation_denied_in_live_mode(self):
        obj = self.student({
            "student_applicant": "APP-1", "th_candidate_ref": "THV-ABC"})
        with self.assertRaisesRegex(Denied, "approved admission conversion"):
            obj.validate()

    def test_approved_student_conversion_invokes_native_validation(self):
        self.kind = "convert_applicant"
        obj = self.student({
            "student_applicant": "APP-1", "th_candidate_ref": "THV-ABC"})
        self.assertEqual(obj.validate(), "native Education validations")

    def test_conversion_without_candidate_link_is_denied(self):
        self.kind = "convert_applicant"
        obj = self.student({"student_applicant": "APP-1"})
        with self.assertRaises(Invalid):
            obj.validate()

    def test_native_applicant_creation_rejected_without_admission_command(self):
        obj = Doc({"th_candidate_ref": "THV-ABC",
                   "th_reception_inquiry": "INQ-1"})
        with self.assertRaisesRegex(Denied, "approved placement intake"):
            self.applicant_guard(obj)

    def test_verified_applicant_creation_requires_both_links(self):
        self.kind = "record_applicant"
        obj = Doc({"th_candidate_ref": "THV-ABC"})
        with self.assertRaises(Invalid):
            self.applicant_guard(obj)

    def test_record_applicant_command_may_create_valid_native_applicant(self):
        self.kind = "record_applicant"
        self.applicant_guard(Doc({
            "th_candidate_ref": "THV-ABC", "th_reception_inquiry": "INQ-1"}))

    def test_post_conversion_mutation_denied_regardless_of_role(self):
        self.kind = None
        obj = self.student({
            "student_applicant": "APP-OTHER", "th_candidate_ref": "THV-ABC"}, new=False)
        with self.assertRaises(Denied):
            obj.validate()

    def test_synthetic_native_fixture_behavior_preserved(self):
        self.production = False
        self.student({"student_applicant": "APP-1"}).validate()


if __name__ == "__main__":
    unittest.main()

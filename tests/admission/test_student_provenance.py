"""Execute native candidate provenance protection without a Frappe database."""
import ast
from pathlib import Path
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
SOURCE = (APP / "admission/native_student.py").read_text()


class Denied(Exception):
    pass


class Invalid(Exception):
    pass


class NativeRecord:
    def __init__(self, fields, new=False):
        self.data = dict(fields)
        self.name = "DOC-1"
        self.new = new

    def is_new(self):
        return self.new

    def get(self, key):
        return self.data.get(key)


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.saved = {
            "student_applicant": "APP-1", "th_candidate_ref": "THV-ONE",
            "th_reception_inquiry": "INQ-1",
        }
        original = self
        def get_value(dt, name, fields, as_dict=False):
            self.assertIn(dt, ("Student", "Student Applicant"))
            self.assertEqual(name, "DOC-1")
            return {key: original.saved.get(key) for key in fields}
        tree = ast.parse(SOURCE)
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_protect_candidate_provenance")
        namespace = {"frappe": types.SimpleNamespace(
            db=types.SimpleNamespace(get_value=get_value),
            PermissionError=Denied, ValidationError=Invalid)}
        exec(compile(ast.fix_missing_locations(ast.Module(
            body=[fn], type_ignores=[])), "native_student.py", "exec"), namespace)
        self.protect = namespace["_protect_candidate_provenance"]

    def test_new_applicant_can_receive_authorized_identity(self):
        record = NativeRecord({"th_candidate_ref": "THV-ONE",
                               "th_reception_inquiry": "INQ-1"}, new=True)
        self.protect(record, "Student Applicant",
                     ("th_candidate_ref", "th_reception_inquiry"))

    def test_applicant_cannot_change_referral(self):
        record = NativeRecord({"th_candidate_ref": "THV-ONE",
                               "th_reception_inquiry": "INQ-OTHER"})
        with self.assertRaises(Denied):
            self.protect(record, "Student Applicant",
                         ("th_candidate_ref", "th_reception_inquiry"))

    def test_student_cannot_change_native_applicant(self):
        record = NativeRecord({"student_applicant": "APP-OTHER",
                               "th_candidate_ref": "THV-ONE"})
        with self.assertRaises(Denied):
            self.protect(record, "Student", ("student_applicant", "th_candidate_ref"))

    def test_student_cannot_change_candidate_ref(self):
        record = NativeRecord({"student_applicant": "APP-1",
                               "th_candidate_ref": "THV-OTHER"})
        with self.assertRaises(Denied):
            self.protect(record, "Student", ("student_applicant", "th_candidate_ref"))

    def test_normal_student_contact_updates_do_not_change_origin(self):
        record = NativeRecord({"student_applicant": "APP-1",
                               "th_candidate_ref": "THV-ONE",
                               "student_mobile_number": "0790000000"})
        self.protect(record, "Student", ("student_applicant", "th_candidate_ref"))

    def test_hooked_in_both_native_applicant_and_student(self):
        hooks = (APP / "hooks.py").read_text()
        self.assertIn('"Student Applicant": {\n        "validate": "toefl_house.admission.native_student.protect_applicant_identity"', hooks)
        self.assertIn('"Student": "toefl_house.admission.native_student.THEmailOptionalStudent"', hooks)
        self.assertIn("_protect_candidate_provenance(\n            self, \"Student\"", SOURCE)


if __name__ == "__main__":
    unittest.main()

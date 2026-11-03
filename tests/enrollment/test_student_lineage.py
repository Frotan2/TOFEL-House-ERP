"""Execute the real Student enrollment lineage gate with adversarial records.

No native Student, Customer, Program Enrollment or fees are created here.
The independent MariaDB, role and HTTP acceptance gates still apply.
"""
import ast
from pathlib import Path
import types
import unittest

SOURCE = (Path(__file__).resolve().parents[2] /
          "apps/toefl_house/toefl_house/enrollment/__init__.py").read_text()
TREE = ast.parse(SOURCE)


class Invalid(Exception):
    pass


class Denied(Exception):
    pass


class EnrollmentLineageTests(unittest.TestCase):
    def setUp(self):
        self.case = types.SimpleNamespace(
            subject="THV-" + "a" * 32, th_branch="Branch A",
            reception_inquiry="INQ-1")
        self.applicant = types.SimpleNamespace(
            name="APP-1", th_candidate_ref=self.case.subject,
            th_branch="Branch A", th_reception_inquiry="INQ-1")
        self.linked = types.SimpleNamespace(
            name="STU-1", student_applicant="APP-1",
            th_candidate_ref=self.case.subject, enabled=1)
        self.admission = types.SimpleNamespace(
            student_applicant="APP-1", existing_student="")
        self.placement = types.SimpleNamespace(attempt="ATT-1")
        self.production = True
        fixture = self
        def get_value(doctype, key, fields, as_dict=False):
            if doctype == "TH Placement Attempt":
                self.assertEqual(key, "ATT-1")
                self.assertEqual(fields, "case_name")
                return "CASE-1"
            if doctype == "TH Placement Case":
                self.assertEqual(key, "CASE-1")
                return fixture.case
            if doctype == "Student Applicant":
                self.assertEqual(key, "APP-1")
                return fixture.applicant
            self.fail(f"Unexpected database lookup: {doctype}")
        fn = next(node for node in TREE.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_check_student_lineage")
        scope = {
            "frappe": types.SimpleNamespace(
                db=types.SimpleNamespace(get_value=get_value),
                ValidationError=Invalid, PermissionError=Denied),
            "is_production": lambda: fixture.production,
        }
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],
            type_ignores=[])), "enrollment/__init__.py", "exec"), scope)
        self.check = scope["_check_student_lineage"]

    def allow(self):
        self.assertIsNone(self.check(self.admission, self.placement, self.linked))

    def test_new_no_email_candidate_matches_every_document(self):
        self.allow()

    def test_legitimate_returning_candidate_same_record_is_allowed(self):
        self.admission.existing_student = "STU-1"
        self.allow()

    def test_disabled_student_is_refused(self):
        self.linked.enabled = 0
        with self.assertRaisesRegex(Invalid, "Disabled Student"):
            self.allow()

    def test_missing_native_student_is_refused(self):
        with self.assertRaisesRegex(Invalid, "Native Student not found"):
            self.check(self.admission, self.placement, None)

    def test_returning_student_must_be_the_declared_student(self):
        self.admission.existing_student = "STU-OTHER"
        with self.assertRaises(Invalid):
            self.allow()

    def test_wrong_native_applicant_is_refused_even_when_email_would_match(self):
        self.linked.student_applicant = "APP-OTHER"
        with self.assertRaises(Denied):
            self.allow()

    def test_wrong_candidate_reference_is_refused(self):
        self.linked.th_candidate_ref = "THV-" + "b" * 32
        with self.assertRaises(Denied):
            self.allow()

    def test_wrong_reception_inquiry_is_refused(self):
        self.applicant.th_reception_inquiry = "INQ-OTHER"
        with self.assertRaises(Denied):
            self.allow()

    def test_wrong_branch_is_refused(self):
        self.applicant.th_branch = "Branch B"
        with self.assertRaises(Denied):
            self.allow()

    def test_no_verified_origin_is_refused(self):
        self.case.reception_inquiry = ""
        with self.assertRaises(Denied):
            self.allow()

    def test_applicant_does_not_match_released_candidate(self):
        self.applicant.th_candidate_ref = "THV-" + "b" * 32
        with self.assertRaises(Denied):
            self.allow()

    def test_legacy_synthetic_candidate_keeps_its_original_linkage(self):
        self.production = False
        self.linked.th_candidate_ref = None
        self.allow()
        self.linked.student_applicant = "APP-OTHER"
        with self.assertRaises(Invalid):
            self.allow()


if __name__ == "__main__":
    unittest.main()

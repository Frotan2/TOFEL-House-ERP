"""S7 regression: returning-student conversion links, never duplicates.

convert_applicant with an officer-declared existing_student must LINK
that Student (email-match identity proof, enabled, no duplicate link,
no new Customer) instead of inserting a second Student — native
Student.student_email_id is unique, so a duplicate cannot exist. The
normal branch is unchanged. Loads the REAL admission module against a
scripted frappe stub; the end-to-end returning journey is proven on
hosted CI in tools/placement/native_checks.py.
"""
import importlib.util
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"
ACTOR = "approver.one@example.com"
SUBJECT = "returning@example.test"


class _PermissionError(Exception):
    pass


class _ValidationError(Exception):
    pass


def _load_real(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


class _Decision:
    def __init__(self, **fields):
        self._fields = dict(fields)

    def __getattr__(self, name):
        return self._fields.get(name)

    def set(self, field, value):
        self._fields[field] = value

    def save(self, ignore_permissions=False):
        return self


class ReturningConvertTests(unittest.TestCase):
    def setUp(self):
        self.existing_student = "EDU-STU-2025-00001"
        self.student_email = SUBJECT
        self.student_enabled = 1
        self.student_missing = False
        self.student_customer = "CUST-OLD"
        self.applicant_owned = False
        self.already_enrolled = []
        self.drafted_by = "officer@example.com"
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
        fake = self

        def get_value(doctype, name_or_filters, fieldname=None, as_dict=False, **kwargs):
            if doctype == "TH Admission Decision" and fieldname == "student_applicant":
                return "APP-NEW"
            if doctype == "TH Placement Decision" and as_dict:
                return SimpleNamespace(name="PD-1", status="Released", attempt="ATT-1",
                                       released_at="2026-09-01 00:00:00",
                                       expires_at="2026-12-31 00:00:00",
                                       course_code="TH-A1", internal_level="A1")
            if doctype == "Student Applicant" and as_dict:
                return SimpleNamespace(name="APP-NEW", first_name="SYNTHETIC Return",
                                       last_name="Applicant", student_email_id=SUBJECT,
                                       application_status="Admitted")
            if doctype == "Student Applicant" and fieldname == "application_status":
                return "Admitted"
            if doctype == "Student" and as_dict and not fake.student_missing:
                return SimpleNamespace(name=fake.existing_student,
                                       student_email_id=fake.student_email,
                                       enabled=fake.student_enabled,
                                       customer=fake.student_customer)
            if doctype == "Student" and as_dict and fake.student_missing:
                return None
            if doctype == "Student" and fieldname == "customer":
                return fake.student_customer
            raise AssertionError(f"unexpected get_value {doctype} {fieldname}")

        def sql(query, values=(), **kwargs):
            if "tabStudent Applicant" in query:
                return []
            if "tabProgram Enrollment" in query:
                return list(fake.already_enrolled)
            raise AssertionError(f"unexpected sql {query[:80]}")

        def exists(doctype, name):
            if doctype == "Student":
                return fake.applicant_owned
            return True

        def get_doc(doctype, name=None, for_update=False, **kwargs):
            assert doctype == "TH Admission Decision" and for_update
            return _Decision(
                name="ADM-1", student_applicant="APP-NEW", program="TH-PROG",
                academic_year="2026-27", academic_term="", placement_decision="PD-1",
                status="Approved", version=5, drafted_by=fake.drafted_by,
                reviewed_by="reviewer@example.com", decided_by="approver.two@example.com",
                accepted=1, native_student="", existing_student=fake.existing_student,
                conditions="")

        stub = types.ModuleType("frappe")
        stub.session = SimpleNamespace(user=ACTOR)
        stub.conf = {"toefl_house_synthetic_only": 1, "allow_tests": 1}
        stub.local = SimpleNamespace(site="placement-test.localhost")
        stub.PermissionError = _PermissionError
        stub.ValidationError = _ValidationError
        stub.get_roles = lambda user: {"Admission Approver"}
        stub.whitelist = lambda **kwargs: (lambda func: func)
        stub.flags = SimpleNamespace()
        stub.utils = SimpleNamespace(
            today=lambda: "2026-09-22",
            get_datetime=lambda v=None: v if isinstance(v, datetime) else datetime.fromisoformat(str(v)))
        stub.db = SimpleNamespace(get_value=get_value, sql=sql, exists=exists)
        stub.get_doc = get_doc
        sys.modules["frappe"] = stub
        sys.modules["frappe.utils"] = stub.utils

        package = types.ModuleType("toefl_house")
        package.__path__ = [str(APP)]
        sys.modules["toefl_house"] = package
        _load_real("toefl_house.policy", APP / "policy.py")
        security = types.ModuleType("toefl_house.security")
        security.is_production = lambda: False
        security.record_synthetic_flag = lambda: 1
        sys.modules["toefl_house.security"] = security
        api = types.ModuleType("toefl_house.api")
        api.ATTEMPT = "TH Placement Attempt"
        api.DECISION = "TH Placement Decision"
        api._execute = lambda kind, key, payload, work: work(ACTOR)[0]
        api._now = lambda: datetime(2026, 9, 22, 12, 0, 0)
        sys.modules["toefl_house.api"] = api
        returning = types.ModuleType("toefl_house.admission.policies")
        returning.governing_returning_mode = lambda on_date=None: ""
        sys.modules["toefl_house.admission.policies"] = returning
        self.admission = _load_real("toefl_house.admission", APP / "admission/__init__.py")

    def _convert(self, key="test-key-return-convert-01"):
        return self.admission.convert_applicant(key, "ADM-1", 5)

    def test_returning_convert_links_the_existing_student(self):
        result = self._convert()
        self.assertEqual(result["native_student"], "EDU-STU-2025-00001")
        self.assertEqual(result["customer"], "CUST-OLD")
        self.assertTrue(result["returning"])
        self.assertEqual(result["version"], 6)
        self.assertEqual(result["program_enrollment"], 0)
        self.assertEqual(result["native_application_status"], "Admitted")

    def test_email_mismatch_is_refused(self):
        self.student_email = "someone.else@example.test"
        with self.assertRaises(_ValidationError) as ctx:
            self._convert()
        self.assertIn("does not belong to this applicant", str(ctx.exception))

    def test_disabled_student_is_refused(self):
        self.student_enabled = 0
        with self.assertRaises(_ValidationError) as ctx:
            self._convert()
        self.assertIn("disabled", str(ctx.exception))

    def test_missing_student_is_refused(self):
        self.student_missing = True
        with self.assertRaises(_ValidationError) as ctx:
            self._convert()
        self.assertIn("Existing Student not found", str(ctx.exception))

    def test_applicant_with_a_student_cannot_link_again(self):
        self.applicant_owned = True
        with self.assertRaises(_ValidationError) as ctx:
            self._convert()
        self.assertIn("already exists for this applicant", str(ctx.exception))

    def test_already_enrolled_returning_is_refused(self):
        self.already_enrolled = [{"name": "PE-OLD"}]
        with self.assertRaises(_ValidationError) as ctx:
            self._convert()
        self.assertIn("already enrolled", str(ctx.exception))

    def test_returning_convert_keeps_separation_of_duties(self):
        self.drafted_by = ACTOR
        with self.assertRaises(_PermissionError) as ctx:
            self._convert()
        self.assertIn("cannot convert their own draft", str(ctx.exception))

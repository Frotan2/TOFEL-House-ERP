"""S7 regression: returning admission decisions reuse the one applicant.

Native applicant email is unique, so a returning journey opens its new
decision on the EXISTING applicant row: Admitted applicants must declare
their existing Student (email-match identity proof), an open decision
blocks, and journey program/year/term overrides are honored only for
returning admissions. Loads the REAL admission module against a
scripted frappe stub; hosted CI proves the full returning journey.
"""
import importlib.util
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"
ACTOR = "admission.officer@example.com"
SUBJECT = "returning@example.test"


class _PermissionError(Exception):
    pass


class _ValidationError(Exception):
    pass


class _DoesNotExistError(Exception):
    pass


def _load_real(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


class _Decision:
    def __init__(self, payload):
        self._fields = dict(payload)
        self.name = "ADM-NEW"

    def __getattr__(self, name):
        return self._fields.get(name)

    def insert(self, ignore_permissions=False):
        return self


class ReturningCreateTests(unittest.TestCase):
    def setUp(self):
        self.applicant_status = "Admitted"
        self.applicant_email = SUBJECT
        self.student_email = SUBJECT
        self.student_missing = False
        self.open_decisions = []
        self.unknown_program = False
        self.execute_calls = []
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
        fake = self

        def get_value(doctype, name_or_filters, fieldname=None, as_dict=False, **kwargs):
            if doctype == "TH Placement Decision" and as_dict:
                return SimpleNamespace(name="PD-NEW", status="Released", attempt="ATT-1",
                                       released_at="2026-09-01 00:00:00",
                                       expires_at="2026-12-31 00:00:00",
                                       course_code="TH-A1", internal_level="A1")
            if doctype == "TH Placement Attempt" and fieldname == "subject":
                return SUBJECT
            if doctype == "Student" and fieldname == "student_email_id":
                return None if fake.student_missing else fake.student_email
            raise AssertionError(f"unexpected get_value {doctype} {fieldname}")

        def sql(query, values=(), **kwargs):
            if "tabStudent Applicant" in query:
                return []
            if "tabTH Admission Decision" in query and "placement_decision" in query:
                return []
            if "tabTH Admission Decision" in query:
                return list(fake.open_decisions)
            raise AssertionError(f"unexpected sql {query[:80]}")

        def exists(doctype, name):
            if doctype == "Program" and fake.unknown_program:
                return False
            return True

        def get_doc(doctype, name=None, **kwargs):
            if isinstance(doctype, dict):
                return _Decision(doctype)
            if doctype == "Student Applicant":
                return SimpleNamespace(name="APP-OLD", program="TH-PROG",
                                       academic_year="2026-27",
                                       student_email_id=fake.applicant_email,
                                       application_status=fake.applicant_status,
                                       paid=0,
                                       get=lambda field: {"academic_term": ""}.get(field))
            raise AssertionError(f"unexpected get_doc {doctype}")

        stub = types.ModuleType("frappe")
        stub.session = SimpleNamespace(user=ACTOR)
        stub.PermissionError = _PermissionError
        stub.ValidationError = _ValidationError
        stub.DoesNotExistError = _DoesNotExistError
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

        def _execute(kind, key, payload, work):
            fake.execute_calls.append((kind, key, dict(payload)))
            return work(ACTOR)[0]

        api._execute = _execute
        api._now = lambda: datetime(2026, 9, 22, 12, 0, 0)
        sys.modules["toefl_house.api"] = api
        returning = types.ModuleType("toefl_house.admission.policies")
        returning.governing_returning_mode = lambda on_date=None: ""
        sys.modules["toefl_house.admission.policies"] = returning
        self.admission = _load_real("toefl_house.admission", APP / "admission/__init__.py")

    def _create(self, **overrides):
        params = {"request_key": "test-key-return-create-01",
                  "student_applicant": "APP-OLD",
                  "placement_decision": "PD-NEW",
                  "existing_student": "EDU-STU-2025-00001"}
        params.update(overrides)
        return self.admission.create_admission(**params)

    def test_returning_create_honors_journey_overrides(self):
        result = self._create(program="TH-NEXT", academic_year="2027-28",
                              academic_term="TERM-2")
        self.assertEqual(result["program"], "TH-NEXT")
        self.assertEqual(result["academic_year"], "2027-28")
        _kind, _key, payload = self.execute_calls[0]
        self.assertEqual(payload["program"], "TH-NEXT")
        self.assertEqual(payload["academic_year"], "2027-28")
        self.assertEqual(payload["academic_term"], "TERM-2")

    def test_returning_create_inherits_without_overrides(self):
        result = self._create()
        self.assertEqual(result["program"], "TH-PROG")
        self.assertEqual(result["academic_year"], "2026-27")

    def test_admitted_applicant_must_link_its_student(self):
        with self.assertRaises(_ValidationError) as ctx:
            self._create(existing_student="")
        self.assertIn("declare it", str(ctx.exception))

    def test_non_applied_non_admitted_applicant_refused(self):
        self.applicant_status = "Rejected"
        with self.assertRaises(_ValidationError) as ctx:
            self._create()
        self.assertIn("Applied status", str(ctx.exception))

    def test_overrides_without_existing_student_refused(self):
        self.applicant_status = "Applied"
        with self.assertRaises(_ValidationError) as ctx:
            self._create(existing_student="", program="TH-NEXT")
        self.assertIn("only for returning admissions", str(ctx.exception))

    def test_email_mismatch_at_create_refused(self):
        self.student_email = "someone.else@example.test"
        with self.assertRaises(_ValidationError) as ctx:
            self._create()
        self.assertIn("does not belong to this applicant", str(ctx.exception))

    def test_open_decision_blocks_new_journey(self):
        self.open_decisions = [{"name": "ADM-OLD"}]
        with self.assertRaises(_ValidationError) as ctx:
            self._create()
        self.assertIn("open admission decision", str(ctx.exception))

    def test_unknown_override_program_refused(self):
        self.unknown_program = True
        with self.assertRaises(_ValidationError) as ctx:
            self._create(program="NO-SUCH-PROGRAM")
        self.assertIn("Unknown program", str(ctx.exception))

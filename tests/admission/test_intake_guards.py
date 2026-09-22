"""S3 regression: duplicate-applicant intake race (BUG-ADM-01).

record_applicant must serialize concurrent same-subject intake on the
placement case row (the subject is unique per case, so contenders always
share it even across decisions) and probe for an existing applicant with a
locking read, so the loser observes the winner on every isolation level.

Loads the REAL admission module against a scripted frappe stub.
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


class _Doc:
    def __init__(self, doctype, payload):
        self.doctype = doctype
        self._payload = dict(payload)
        self.flags = SimpleNamespace()
        self.name = "APP-0001"
        self.application_status = "Applied"
        self.paid = 0

    def insert(self, ignore_permissions=False):
        return self


class IntakeGuardTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.applicant_probe = []
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
        fake = self

        def sql(query, values=(), **kwargs):
            fake.calls.append((query, tuple(values)))
            if "tabTH Placement Case" in query:
                assert "for update" in query
                return [{"name": values[0]}]
            if "tabStudent Applicant" in query:
                return list(fake.applicant_probe)
            raise AssertionError(f"unexpected sql {query[:80]}")

        def get_value(doctype, name_or_filters, fieldname=None, as_dict=False, **kwargs):
            if doctype == "TH Placement Decision" and as_dict:
                return SimpleNamespace(name="PD-1", status="Released", attempt="ATT-1",
                                       released_at="2026-09-01 00:00:00",
                                       expires_at="2026-12-31 00:00:00",
                                       course_code="TH-A1", internal_level="A1")
            if doctype == "TH Placement Attempt" and fieldname == "subject":
                return "subject@example.test"
            if doctype == "TH Placement Attempt" and fieldname == "case_name":
                return fake.case_name
            raise AssertionError(f"unexpected get_value {doctype} {fieldname}")

        stub = types.ModuleType("frappe")
        stub.session = SimpleNamespace(user=ACTOR)
        stub.conf = {"toefl_house_synthetic_only": 1, "allow_tests": 1}
        stub.local = SimpleNamespace(site="placement-test.localhost")
        stub.PermissionError = _PermissionError
        stub.ValidationError = _ValidationError
        stub.get_roles = lambda user: {"Admission Officer"}
        stub.whitelist = lambda **kwargs: (lambda func: func)
        stub.flags = SimpleNamespace()
        stub.utils = SimpleNamespace(
            today=lambda: "2026-09-22",
            get_datetime=lambda v=None: v if isinstance(v, datetime) else datetime.fromisoformat(str(v)))
        def exists(doctype, name):
            if doctype == "Student Applicant":
                return bool(fake.applicant_probe)
            return True

        stub.db = SimpleNamespace(get_value=get_value, sql=sql, exists=exists)
        stub.get_doc = lambda doctype, name=None, **k: _Doc(
            doctype["doctype"] if isinstance(doctype, dict) else doctype,
            doctype if isinstance(doctype, dict) else {})
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
        self.admission = _load_real("toefl_house.admission", APP / "admission/__init__.py")
        self.case_name = "CASE-1"

    def _record(self, key="test-key-record-00000001"):
        return self.admission.record_applicant(
            key, "PD-1", "SYNTHETIC Probe", "TH-PROG", "2026-27")

    def test_intake_locks_case_then_probes_applicant_with_lock(self):
        result = self._record()
        self.assertEqual(result["student_email_id"], "subject@example.test")
        kinds = ["case" if "Placement Case" in query else "probe" for query, _ in self.calls]
        self.assertEqual(kinds, ["case", "probe"])
        case_query, case_values = self.calls[0]
        self.assertIn("for update", case_query)
        self.assertEqual(case_values, ("CASE-1",))
        probe_query, probe_values = self.calls[1]
        self.assertIn("for update", probe_query)
        self.assertEqual(probe_values, ("subject@example.test",))

    def test_existing_applicant_denied_after_probe(self):
        self.applicant_probe = [{"name": "APP-OLD"}]
        with self.assertRaises(_ValidationError):
            self._record()

    def test_missing_attempt_case_fails_closed(self):
        self.case_name = ""
        with self.assertRaises(_ValidationError):
            self._record()

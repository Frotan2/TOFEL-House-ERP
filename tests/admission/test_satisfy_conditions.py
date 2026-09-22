"""S6 regression: conditional satisfaction (GAP-CONDITIONAL, OD-NEW-02).

satisfy_conditions moves Conditional -> Approved with the conditions
cleared, so the normal accept/convert path proceeds. Lattice rule:
independent verification -- the satisfier must be an Admission Approver
other than the deciding approver -- plus a mandatory evidence note and
an unexpired placement decision. Loads the REAL admission module
against a scripted frappe stub; the end-to-end journey
(Conditional -> accept -> satisfy -> convert -> enroll) is proven on
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
ACTOR = "approver.two@example.com"
DECIDER = "approver.one@example.com"


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


class SatisfyConditionsTests(unittest.TestCase):
    def setUp(self):
        self.status = "Conditional"
        self.version = 3
        self.decided_by = DECIDER
        self.expires_at = "2026-12-31 00:00:00"
        self.execute_calls = []
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
        fake = self

        def get_value(doctype, name_or_filters, fieldname=None, as_dict=False, **kwargs):
            if doctype == "TH Admission Decision":
                return "APP-1"
            if doctype == "TH Placement Decision" and as_dict:
                return SimpleNamespace(name="PD-1", status="Released", attempt="ATT-1",
                                       released_at="2026-09-01 00:00:00",
                                       expires_at=fake.expires_at,
                                       course_code="TH-A1", internal_level="A1")
            raise AssertionError(f"unexpected get_value {doctype} {fieldname}")

        def get_doc(doctype, name=None, for_update=False, **kwargs):
            assert doctype == "TH Admission Decision" and for_update
            return _Decision(
                name="ADM-1", student_applicant="APP-1", program="TH-PROG",
                academic_year="2026-27", placement_decision="PD-1",
                status=fake.status, version=fake.version,
                decided_by=fake.decided_by, accepted=0, native_student="",
                existing_student="", conditions="Bring transcripts")

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
        stub.db = SimpleNamespace(get_value=get_value,
                                  sql=lambda query, values=(), **k: [],
                                  exists=lambda doctype, name: True)
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
        self.admission = _load_real("toefl_house.admission", APP / "admission/__init__.py")

    def _satisfy(self, key="test-key-satisfy-00000001", evidence="Transcripts verified"):
        return self.admission.satisfy_conditions(key, "ADM-1", self.version, evidence)

    def test_conditional_becomes_approved_with_conditions_cleared(self):
        result = self._satisfy()
        self.assertEqual(result["status"], "Approved")
        self.assertEqual(result["conditions"], "")
        self.assertEqual(result["version"], 4)
        self.assertEqual(result["satisfied_by"], ACTOR)
        self.assertEqual(result["satisfaction_evidence"], "Transcripts verified")
        self.assertEqual(result["satisfied_at"], "2026-09-22 12:00:00")
        kind, _key, payload = self.execute_calls[0]
        self.assertEqual(kind, "satisfy_conditions")
        self.assertEqual(payload["evidence"], "Transcripts verified")

    def test_non_conditional_status_is_refused(self):
        self.status = "Approved"
        with self.assertRaises(_ValidationError) as ctx:
            self._satisfy()
        self.assertIn("Only Conditional", str(ctx.exception))

    def test_deciding_approver_cannot_self_satisfy(self):
        self.decided_by = ACTOR
        with self.assertRaises(_PermissionError) as ctx:
            self._satisfy()
        self.assertIn("cannot verify their own", str(ctx.exception))

    def test_evidence_is_mandatory(self):
        with self.assertRaises(_ValidationError) as ctx:
            self._satisfy(evidence="  ")
        self.assertIn("evidence must be", str(ctx.exception))

    def test_stale_version_is_refused(self):
        with self.assertRaises(_ValidationError) as ctx:
            self.admission.satisfy_conditions(
                "test-key-satisfy-00000002", "ADM-1", 999, "Transcripts verified")
        self.assertIn("Stale admission revision", str(ctx.exception))

    def test_expired_placement_is_refused(self):
        self.expires_at = "2026-01-01 00:00:00"
        with self.assertRaises(_ValidationError) as ctx:
            self._satisfy()
        self.assertIn("has expired", str(ctx.exception))

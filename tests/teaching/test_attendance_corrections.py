"""S9 regression: attendance-correction request/approve/deny (OD-NEW-06).

Only submitted marks are correctable, inside an active policy; each
record carries at most one pending request; approvals void the
erroneous record and submit a replacement (both marks stay visible),
judging the pinned terms against live re-proven facts. Loads the REAL
teaching attendance-corrections module against a scripted frappe stub;
hosted CI proves the correction journey.
"""
import importlib.util
import sys
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"
ACTOR = "attendance.recorder@example.com"
APPROVER = "teaching.auditor@example.com"


class _ValidationError(Exception):
    pass


class _PermissionError(Exception):
    pass


def _load_real(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


class _Row(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value

    def as_dict(self):
        return dict(self)


class _Doc:
    def __init__(self, name, **fields):
        self._fields = dict(fields)
        self._fields["name"] = name
        self.flags = SimpleNamespace()
        self.inserted = False
        self.saved = False
        self.submitted = False
        self.cancelled = False

    def __getattr__(self, name):
        return self._fields.get(name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._fields[name] = value

    def get(self, field):
        return self._fields.get(field)

    def append(self, field, row):
        self._fields.setdefault(field, []).append(_Row(row))

    def insert(self, ignore_permissions=False):
        self.inserted = True
        return self

    def save(self, ignore_permissions=False):
        self.saved = True
        return self

    def submit(self):
        self.submitted = True
        self._fields["docstatus"] = 1
        return self

    def cancel(self):
        self.cancelled = True
        self._fields["docstatus"] = 2
        return self


class AttendanceCorrectionCommandTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.actor_roles = {"Attendance Recorder"}
        self.policy_rows = [{"name": "ATT-CORR-POL"}]
        self.policy_doc = _Doc(
            "ATT-CORR-POL", code="ATT-CORR-POL", title="Correction rule",
            status="Active", versions=[_Row({
                "effective_from": "2026-09-20",
                "approver_role": "Teaching Auditor",
                "correction_window_days": 7,
                "reason": "Owner opens attendance corrections",
                "set_by": "course.owner@example.com",
                "set_on": "2026-09-19 12:00:00"})])
        self.attendance = {
            "ATT-1": {"student": "STU-1", "course_schedule": "SCHED-1",
                      "status": "Absent", "docstatus": 1}}
        self.schedule_date = str(date.today() - timedelta(days=1))
        self.pending = []
        self.request_doc = None
        self.inserted_requests = []
        self.inserted_attendance = []
        self.attendance_docs = {}
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
        fake = self

        def sql(query, values=(), **kwargs):
            fake.calls.append((query, tuple(values)))
            if "for update" in query:
                return [(values[0],)]
            raise AssertionError(f"unexpected sql {query[:80]}")

        def get_value(doctype, name_or_filters, fieldname=None, **kwargs):
            if doctype == "TH Attendance Correction Policy":
                return fake.policy_doc.name
            if doctype == "Student Attendance":
                return SimpleNamespace(**fake.attendance[name_or_filters])
            if doctype == "Course Schedule":
                assert fieldname == "schedule_date"
                return fake.schedule_date
            raise AssertionError(f"unexpected get_value {doctype} {fieldname}")

        def get_all(doctype, fields=None, filters=None, limit=None, **kwargs):
            assert doctype == "TH Attendance Correction Policy"
            return list(fake.policy_rows)

        def exists(doctype, name):
            if doctype == "Student Attendance":
                return name in fake.attendance
            if doctype == "TH Attendance Correction Request":
                if isinstance(name, dict):
                    return any(r["attendance"] == name.get("attendance")
                               and r["status"] == name.get("status")
                               for r in fake.pending)
                return fake.request_doc is not None
            if doctype == "Role":
                return True
            raise AssertionError(f"unexpected exists {doctype}")

        stub = types.ModuleType("frappe")
        stub.session = SimpleNamespace(user=ACTOR)
        stub.PermissionError = _PermissionError
        stub.ValidationError = _ValidationError
        stub.whitelist = lambda **kwargs: (lambda func: func)
        stub.utils = SimpleNamespace(
            today=lambda: str(date.today()),
            now_datetime=lambda: "2026-09-22 12:00:00")
        stub.db = SimpleNamespace(get_value=get_value, get_all=get_all,
                                  sql=sql, exists=exists)
        stub.get_roles = lambda user: set(fake.actor_roles)

        def get_doc(doctype, name=None, for_update=False, **kwargs):
            if isinstance(doctype, dict):
                payload = dict(doctype)
                if payload["doctype"] == "TH Attendance Correction Request":
                    doc = _Doc("REQ-NEW", **payload)
                    fake.inserted_requests.append(doc)
                    return doc
                doc = _Doc("ATT-NEW", **payload)
                fake.inserted_attendance.append(doc)
                return doc
            if doctype == "TH Attendance Correction Request":
                assert fake.request_doc is not None
                return fake.request_doc
            if doctype == "Student Attendance":
                if name not in fake.attendance_docs:
                    fake.attendance_docs[name] = _Doc(
                        name, **fake.attendance[name])
                return fake.attendance_docs[name]
            if doctype == "TH Attendance Correction Policy":
                return fake.policy_doc
            raise AssertionError(f"unexpected get_doc {doctype}")

        stub.get_doc = get_doc
        sys.modules["frappe"] = stub
        sys.modules["frappe.utils"] = stub.utils

        package = types.ModuleType("toefl_house")
        package.__path__ = [str(APP)]
        sys.modules["toefl_house"] = package
        academic_pkg = types.ModuleType("toefl_house.academic")
        academic_pkg.__path__ = [str(APP / "academic")]
        sys.modules["toefl_house.academic"] = academic_pkg
        config_pkg = types.ModuleType("toefl_house.configuration")
        config_pkg.__path__ = [str(APP / "configuration")]
        sys.modules["toefl_house.configuration"] = config_pkg
        _load_real("toefl_house.configuration.rules",
                   APP / "configuration/rules.py")
        _load_real("toefl_house.academic.rules", APP / "academic/rules.py")
        _load_real("toefl_house.policy", APP / "policy.py")
        audit = types.ModuleType("toefl_house.configuration.audit")
        audit.execute = lambda kind, key, payload, work: work(ACTOR)[0]
        audit.latest_after_hash = lambda target: ""
        sys.modules["toefl_house.configuration.audit"] = audit
        api = types.ModuleType("toefl_house.api")
        api._execute = lambda kind, key, payload, work: work(ACTOR)[0]
        sys.modules["toefl_house.api"] = api
        security = types.ModuleType("toefl_house.security")
        security.record_synthetic_flag = lambda: 1
        sys.modules["toefl_house.security"] = security
        teaching_pkg = types.ModuleType("toefl_house.teaching")
        teaching_pkg.__path__ = [str(APP / "teaching")]
        from contextlib import nullcontext
        teaching_pkg._roster_read = nullcontext
        sys.modules["toefl_house.teaching"] = teaching_pkg
        self.corrections = _load_real(
            "toefl_house.teaching.attendance_corrections",
            APP / "teaching/attendance_corrections.py")

    def _request(self, key="test-key-attcorr-req01", attendance="ATT-1",
                 status="Present", reason="Recorder misread the sheet"):
        return self.corrections.request_attendance_correction(
            key, attendance, status, reason)

    def _pending_doc(self, **overrides):
        fields = {"attendance": "ATT-1", "course_schedule": "SCHED-1",
                  "from_status": "Absent", "requested_status": "Present",
                  "reason": "Recorder misread the sheet",
                  "requested_by": ACTOR,
                  "requested_on": "2026-09-22 12:00:00",
                  "pinned_effective_from": "2026-09-20",
                  "pinned_approver_role": "Teaching Auditor",
                  "pinned_window_days": 7, "status": "Requested"}
        fields.update(overrides)
        self.request_doc = _Doc("REQ-1", **fields)
        return self.request_doc

    # --- request ---------------------------------------------------------

    def test_request_pins_the_governing_terms(self):
        result = self._request()
        self.assertEqual(result["attendance"], "ATT-1")
        self.assertEqual(result["from_status"], "Absent")
        self.assertEqual(result["requested_status"], "Present")
        req = self.inserted_requests[0]
        self.assertTrue(req.inserted)
        self.assertEqual(req.status, "Requested")
        self.assertEqual(req.pinned_effective_from, "2026-09-20")
        self.assertEqual(req.pinned_approver_role, "Teaching Auditor")
        self.assertEqual(req.pinned_window_days, 7)
        self.assertEqual(req.requested_by, ACTOR)

    def test_request_refused_without_a_policy(self):
        self.policy_rows = []
        with self.assertRaises(_ValidationError) as ctx:
            self._request(key="test-key-attcorr-req02")
        self.assertIn("fail closed until one is configured", str(ctx.exception))

    def test_request_refused_for_a_non_native_status(self):
        with self.assertRaises(_ValidationError) as ctx:
            self._request(key="test-key-attcorr-req03", status="Late")
        self.assertIn("Unsupported attendance status", str(ctx.exception))

    def test_request_refused_when_the_mark_matches(self):
        with self.assertRaises(_ValidationError) as ctx:
            self._request(key="test-key-attcorr-req04", status="Absent")
        self.assertIn("must change the mark", str(ctx.exception))

    def test_request_refused_for_an_unsubmitted_record(self):
        self.attendance["ATT-1"]["docstatus"] = 2
        with self.assertRaises(_ValidationError) as ctx:
            self._request(key="test-key-attcorr-req05")
        self.assertIn("Only submitted attendance marks", str(ctx.exception))

    def test_request_refused_when_one_is_pending(self):
        self.pending = [{"attendance": "ATT-1", "status": "Requested"}]
        with self.assertRaises(_ValidationError) as ctx:
            self._request(key="test-key-attcorr-req06")
        self.assertIn("already has a pending correction request", str(ctx.exception))

    def test_request_refused_without_a_reason(self):
        with self.assertRaises(_ValidationError) as ctx:
            self._request(key="test-key-attcorr-req07", reason="")
        self.assertIn("Correction reason", str(ctx.exception))

    # --- approve ---------------------------------------------------------

    def test_approve_voids_and_replaces_inside_the_window(self):
        self.actor_roles = {"Attendance Recorder", "Teaching Auditor"}
        self._pending_doc()
        result = self.corrections.approve_attendance_correction(
            "test-key-attcorr-app01", "REQ-1")
        self.assertEqual(result["status"], "Posted")
        original = self.attendance_docs["ATT-1"]
        self.assertTrue(original.cancelled)
        fixed = self.inserted_attendance[0]
        self.assertTrue(fixed.inserted and fixed.submitted)
        self.assertEqual(fixed.status, "Present")
        self.assertEqual(fixed.student, "STU-1")
        self.assertEqual(fixed.course_schedule, "SCHED-1")
        self.assertEqual(result["replacement_attendance"], "ATT-NEW")
        self.assertEqual(self.request_doc.status, "Posted")
        self.assertEqual(self.request_doc.replacement_attendance, "ATT-NEW")
        self.assertEqual(self.request_doc.approved_by, ACTOR)

    def test_approve_refused_without_the_approver_role(self):
        self._pending_doc()
        with self.assertRaises(_PermissionError) as ctx:
            self.corrections.approve_attendance_correction(
                "test-key-attcorr-app02", "REQ-1")
        self.assertIn("approver role", str(ctx.exception))

    def test_approve_refused_when_not_pending(self):
        self.actor_roles = {"Attendance Recorder", "Teaching Auditor"}
        self._pending_doc(status="Posted")
        with self.assertRaises(_ValidationError) as ctx:
            self.corrections.approve_attendance_correction(
                "test-key-attcorr-app03", "REQ-1")
        self.assertIn("not pending", str(ctx.exception))

    def test_approve_refused_when_the_mark_moved(self):
        self.actor_roles = {"Attendance Recorder", "Teaching Auditor"}
        self._pending_doc()
        self.attendance["ATT-1"]["status"] = "Leave"
        with self.assertRaises(_ValidationError) as ctx:
            self.corrections.approve_attendance_correction(
                "test-key-attcorr-app04", "REQ-1")
        self.assertIn("changed after this request was raised", str(ctx.exception))

    def test_approve_refused_after_the_window(self):
        self.actor_roles = {"Attendance Recorder", "Teaching Auditor"}
        self._pending_doc()
        self.schedule_date = str(date.today() - timedelta(days=8))
        with self.assertRaises(_ValidationError) as ctx:
            self.corrections.approve_attendance_correction(
                "test-key-attcorr-app05", "REQ-1")
        self.assertIn("window for this session has closed", str(ctx.exception))

    def test_approve_refused_when_no_longer_submitted(self):
        self.actor_roles = {"Attendance Recorder", "Teaching Auditor"}
        self._pending_doc()
        self.attendance["ATT-1"]["docstatus"] = 2
        with self.assertRaises(_ValidationError) as ctx:
            self.corrections.approve_attendance_correction(
                "test-key-attcorr-app06", "REQ-1")
        self.assertIn("no longer submitted", str(ctx.exception))

    # --- deny ------------------------------------------------------------

    def test_deny_records_the_decision_without_an_artifact(self):
        self.actor_roles = {"Attendance Recorder", "Teaching Auditor"}
        self._pending_doc()
        result = self.corrections.deny_attendance_correction(
            "test-key-attcorr-deny01", "REQ-1")
        self.assertEqual(result["status"], "Denied")
        self.assertEqual(self.request_doc.status, "Denied")
        self.assertEqual(self.request_doc.approved_by, ACTOR)
        self.assertEqual(self.inserted_attendance, [])
        self.assertNotIn("ATT-1", self.attendance_docs)

    def test_deny_refused_without_the_approver_role(self):
        self._pending_doc()
        with self.assertRaises(_PermissionError) as ctx:
            self.corrections.deny_attendance_correction(
                "test-key-attcorr-deny02", "REQ-1")
        self.assertIn("approver role", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

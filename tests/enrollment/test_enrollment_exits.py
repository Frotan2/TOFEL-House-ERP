"""S10 regression: enrollment withdraw/dismiss request/approve/deny (OD-NEW-07).

Only submitted enrollments exit, inside an active policy; submitted
Fees block the exit until finance settles the receivable; each
enrollment carries at most one pending dismissal; approvals cancel
the enrollment (its row preserved) judging the pinned terms against
live re-proven facts. Loads the REAL enrollment exits module against
a scripted frappe stub; hosted CI proves the exit journey.
"""
import importlib.util
import sys
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"
ACTOR = "enrollment.officer@example.com"


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


class EnrollmentExitCommandTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.actor_roles = {"Enrollment Officer"}
        self.policy_rows = [{"name": "ENROLL-EXIT-POL"}]
        self.policy_doc = _Doc(
            "ENROLL-EXIT-POL", code="ENROLL-EXIT-POL", title="Exit rule",
            status="Active", versions=[_Row({
                "effective_from": str(date.today() - timedelta(days=30)),
                "approver_role": "Academic Manager",
                "reason": "Owner opens enrollment exits",
                "set_by": "course.owner@example.com",
                "set_on": "2026-09-19 12:00:00"})])
        self.enrollments = {
            "PE-1": {"student": "STU-1", "program": "PROG-1",
                     "academic_year": "2026",
                     "enrollment_date": str(date.today() - timedelta(days=30)),
                     "docstatus": 1}}
        self.fees = []
        self.course_enrollments = ["CE-1", "CE-2"]
        self.deleted_ces = []
        self.existing_exits = []
        self.exit_doc = None
        self.inserted_exits = []
        self.pe_docs = {}
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
        fake = self

        def sql(query, values=(), **kwargs):
            fake.calls.append((query, tuple(values)))
            if "for update" in query:
                return [(values[0],)]
            raise AssertionError(f"unexpected sql {query[:80]}")

        def get_value(doctype, name_or_filters, fieldname=None, **kwargs):
            if doctype == "TH Enrollment Exit Policy":
                return fake.policy_doc.name
            if doctype == "Program Enrollment":
                return SimpleNamespace(**fake.enrollments[name_or_filters])
            raise AssertionError(f"unexpected get_value {doctype} {fieldname}")

        def get_all(doctype, fields=None, filters=None, limit=None, **kwargs):
            if doctype == "TH Enrollment Exit Policy":
                return list(fake.policy_rows)
            if doctype == "Fees":
                rows = [row for row in fake.fees
                        if row["program_enrollment"] == (filters or {}).get("program_enrollment")]
                if (filters or {}).get("docstatus") == 1:
                    rows = [row for row in rows if row["docstatus"] == 1]
                if limit is not None:
                    rows = rows[:limit]
                return [dict(row) for row in rows]
            if doctype == "Course Enrollment":
                assert (filters or {}).get("program_enrollment") == "PE-1"
                if kwargs.get("pluck") == "name":
                    return list(fake.course_enrollments)
                return [{"name": name} for name in fake.course_enrollments]
            raise AssertionError(f"unexpected get_all {doctype}")

        def exists(doctype, name):
            if doctype == "Program Enrollment":
                return name in fake.enrollments
            if doctype == "TH Enrollment Exit":
                if isinstance(name, dict):
                    return any(row["program_enrollment"] == name.get("program_enrollment")
                               and row["status"] == name.get("status")
                               for row in fake.existing_exits)
                return fake.exit_doc is not None
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

        def delete_doc(doctype, name, ignore_permissions=False, **kwargs):
            assert doctype == "Course Enrollment"
            assert ignore_permissions
            fake.deleted_ces.append(name)
            fake.course_enrollments = [ce for ce in fake.course_enrollments
                                       if ce != name]

        stub.delete_doc = delete_doc

        def get_doc(doctype, name=None, for_update=False, **kwargs):
            if isinstance(doctype, dict):
                payload = dict(doctype)
                assert payload["doctype"] == "TH Enrollment Exit"
                doc = _Doc("EXIT-NEW", **payload)
                fake.inserted_exits.append(doc)
                return doc
            if doctype == "TH Enrollment Exit":
                assert fake.exit_doc is not None
                return fake.exit_doc
            if doctype == "Program Enrollment":
                if name not in fake.pe_docs:
                    fake.pe_docs[name] = _Doc(name, **fake.enrollments[name])
                return fake.pe_docs[name]
            if doctype == "TH Enrollment Exit Policy":
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
        enrollment_pkg = types.ModuleType("toefl_house.enrollment")
        enrollment_pkg.__path__ = [str(APP / "enrollment")]
        sys.modules["toefl_house.enrollment"] = enrollment_pkg
        self.exits = _load_real(
            "toefl_house.enrollment.exits",
            APP / "enrollment/exits.py")

    def _withdraw(self, key="test-key-enrexit-wd01", pe="PE-1",
                  exit_date=None, reason="Student relocates abroad"):
        return self.exits.withdraw_enrollment(
            key, pe, exit_date or str(date.today()), reason)

    def _pending_doc(self, **overrides):
        fields = {"program_enrollment": "PE-1", "student": "STU-1",
                  "exit_kind": "Dismissal",
                  "reason": "Broke the attendance covenant",
                  "requested_by": ACTOR,
                  "requested_on": "2026-09-22 12:00:00",
                  "pinned_effective_from": str(date.today() - timedelta(days=30)),
                  "pinned_approver_role": "Academic Manager",
                  "status": "Requested"}
        fields.update(overrides)
        self.exit_doc = _Doc("EXIT-1", **fields)
        return self.exit_doc

    # --- withdraw ------------------------------------------------------

    def test_withdraw_cancels_the_enrollment_and_posts_the_exit(self):
        result = self._withdraw()
        self.assertEqual(result["status"], "Posted")
        self.assertEqual(result["exit_kind"], "Withdrawal")
        self.assertEqual(result["cancelled_course_enrollments"], 2)
        self.assertEqual(self.deleted_ces, ["CE-1", "CE-2"])
        pe = self.pe_docs["PE-1"]
        self.assertTrue(pe.cancelled)
        exit_doc = self.inserted_exits[0]
        self.assertTrue(exit_doc.inserted)
        self.assertEqual(exit_doc.status, "Posted")
        self.assertEqual(exit_doc.exit_kind, "Withdrawal")
        self.assertEqual(exit_doc.exit_date, str(date.today()))
        self.assertEqual(exit_doc.pinned_approver_role, "Academic Manager")
        self.assertEqual(exit_doc.fees_snapshot, "no Fees on record")
        self.assertEqual(exit_doc.cancelled_courses, "CE-1, CE-2")
        self.assertEqual(exit_doc.requested_by, ACTOR)
        self.assertEqual(exit_doc.approved_by, ACTOR)

    def test_withdraw_refused_without_a_policy(self):
        self.policy_rows = []
        with self.assertRaises(_ValidationError) as ctx:
            self._withdraw(key="test-key-enrexit-wd02")
        self.assertIn("fail closed until one is configured", str(ctx.exception))

    def test_withdraw_refused_for_an_unsubmitted_enrollment(self):
        self.enrollments["PE-1"]["docstatus"] = 2
        with self.assertRaises(_ValidationError) as ctx:
            self._withdraw(key="test-key-enrexit-wd03")
        self.assertIn("Only submitted program enrollments", str(ctx.exception))

    def test_withdraw_refused_for_a_future_exit_date(self):
        future = str(date.today() + timedelta(days=1))
        with self.assertRaises(_ValidationError) as ctx:
            self._withdraw(key="test-key-enrexit-wd04", exit_date=future)
        self.assertIn("cannot be in the future", str(ctx.exception))

    def test_withdraw_refused_before_the_enrollment_date(self):
        early = str(date.today() - timedelta(days=31))
        with self.assertRaises(_ValidationError) as ctx:
            self._withdraw(key="test-key-enrexit-wd05", exit_date=early)
        self.assertIn("cannot precede the enrollment date", str(ctx.exception))

    def test_withdraw_refused_while_a_dismissal_is_pending(self):
        self.existing_exits = [{"program_enrollment": "PE-1",
                                "status": "Requested"}]
        with self.assertRaises(_ValidationError) as ctx:
            self._withdraw(key="test-key-enrexit-wd06")
        self.assertIn("pending dismissal", str(ctx.exception))

    def test_withdraw_refused_after_a_posted_exit(self):
        self.existing_exits = [{"program_enrollment": "PE-1",
                                "status": "Posted"}]
        with self.assertRaises(_ValidationError) as ctx:
            self._withdraw(key="test-key-enrexit-wd07")
        self.assertIn("single-shot", str(ctx.exception))

    def test_withdraw_refused_while_submitted_fees_bill_the_enrollment(self):
        self.fees = [{"name": "FEES-1", "program_enrollment": "PE-1",
                      "docstatus": 1, "outstanding_amount": 150.0}]
        with self.assertRaises(_ValidationError) as ctx:
            self._withdraw(key="test-key-enrexit-wd08")
        self.assertIn("submitted Fees FEES-1", str(ctx.exception))
        self.assertEqual(self.inserted_exits, [])
        self.assertNotIn("PE-1", self.pe_docs)

    def test_withdraw_proceeds_past_cancelled_fees_and_snapshots_them(self):
        self.fees = [{"name": "FEES-1", "program_enrollment": "PE-1",
                      "docstatus": 2, "outstanding_amount": 0}]
        result = self._withdraw(key="test-key-enrexit-wd09")
        self.assertEqual(result["status"], "Posted")
        exit_doc = self.inserted_exits[0]
        self.assertEqual(exit_doc.fees_snapshot, "FEES-1 (Cancelled)")

    def test_withdraw_refused_without_a_reason(self):
        with self.assertRaises(_ValidationError) as ctx:
            self._withdraw(key="test-key-enrexit-wd10", reason="")
        self.assertIn("Exit reason", str(ctx.exception))

    # --- request -------------------------------------------------------

    def test_request_pins_the_governing_terms(self):
        result = self.exits.request_enrollment_dismissal(
            "test-key-enrexit-rq01", "PE-1", "Broke the attendance covenant")
        self.assertEqual(result["status"], "Requested")
        self.assertEqual(result["exit_kind"], "Dismissal")
        exit_doc = self.inserted_exits[0]
        self.assertTrue(exit_doc.inserted)
        self.assertEqual(exit_doc.pinned_approver_role, "Academic Manager")
        self.assertEqual(exit_doc.requested_by, ACTOR)
        self.assertEqual(self.deleted_ces, [])
        self.assertNotIn("PE-1", self.pe_docs)

    def test_request_refused_without_a_policy(self):
        self.policy_rows = []
        with self.assertRaises(_ValidationError) as ctx:
            self.exits.request_enrollment_dismissal(
                "test-key-enrexit-rq02", "PE-1", "Broke the attendance covenant")
        self.assertIn("fail closed until one is configured", str(ctx.exception))

    def test_request_refused_while_submitted_fees_bill_the_enrollment(self):
        self.fees = [{"name": "FEES-1", "program_enrollment": "PE-1",
                      "docstatus": 1, "outstanding_amount": 0}]
        with self.assertRaises(_ValidationError) as ctx:
            self.exits.request_enrollment_dismissal(
                "test-key-enrexit-rq03", "PE-1", "Broke the attendance covenant")
        self.assertIn("submitted Fees FEES-1", str(ctx.exception))

    def test_request_refused_when_one_is_pending(self):
        self.existing_exits = [{"program_enrollment": "PE-1",
                                "status": "Requested"}]
        with self.assertRaises(_ValidationError) as ctx:
            self.exits.request_enrollment_dismissal(
                "test-key-enrexit-rq04", "PE-1", "Broke the attendance covenant")
        self.assertIn("pending dismissal", str(ctx.exception))

    # --- approve -------------------------------------------------------

    def test_approve_posts_the_exit_on_the_decision_date(self):
        self.actor_roles = {"Enrollment Officer", "Academic Manager"}
        self._pending_doc()
        result = self.exits.approve_enrollment_dismissal(
            "test-key-enrexit-ap01", "EXIT-1")
        self.assertEqual(result["status"], "Posted")
        self.assertEqual(result["exit_date"], str(date.today()))
        self.assertEqual(self.deleted_ces, ["CE-1", "CE-2"])
        self.assertTrue(self.pe_docs["PE-1"].cancelled)
        self.assertEqual(self.exit_doc.status, "Posted")
        self.assertEqual(self.exit_doc.exit_date, str(date.today()))
        self.assertEqual(self.exit_doc.approved_by, ACTOR)
        self.assertEqual(self.exit_doc.cancelled_courses, "CE-1, CE-2")

    def test_approve_refused_without_the_approver_role(self):
        self._pending_doc()
        with self.assertRaises(_PermissionError) as ctx:
            self.exits.approve_enrollment_dismissal(
                "test-key-enrexit-ap02", "EXIT-1")
        self.assertIn("approver role", str(ctx.exception))

    def test_approve_refused_when_not_pending(self):
        self.actor_roles = {"Enrollment Officer", "Academic Manager"}
        self._pending_doc(status="Denied")
        with self.assertRaises(_ValidationError) as ctx:
            self.exits.approve_enrollment_dismissal(
                "test-key-enrexit-ap03", "EXIT-1")
        self.assertIn("not pending", str(ctx.exception))

    def test_approve_refused_when_no_longer_submitted(self):
        self.actor_roles = {"Enrollment Officer", "Academic Manager"}
        self._pending_doc()
        self.enrollments["PE-1"]["docstatus"] = 2
        with self.assertRaises(_ValidationError) as ctx:
            self.exits.approve_enrollment_dismissal(
                "test-key-enrexit-ap04", "EXIT-1")
        self.assertIn("no longer submitted", str(ctx.exception))

    def test_approve_refused_when_fees_bill_after_the_request(self):
        self.actor_roles = {"Enrollment Officer", "Academic Manager"}
        self._pending_doc()
        self.fees = [{"name": "FEES-1", "program_enrollment": "PE-1",
                      "docstatus": 1, "outstanding_amount": 150.0}]
        with self.assertRaises(_ValidationError) as ctx:
            self.exits.approve_enrollment_dismissal(
                "test-key-enrexit-ap05", "EXIT-1")
        self.assertIn("submitted Fees FEES-1", str(ctx.exception))

    # --- deny ----------------------------------------------------------

    def test_deny_records_the_decision_without_an_exit(self):
        self.actor_roles = {"Enrollment Officer", "Academic Manager"}
        self._pending_doc()
        result = self.exits.deny_enrollment_dismissal(
            "test-key-enrexit-dn01", "EXIT-1")
        self.assertEqual(result["status"], "Denied")
        self.assertEqual(self.exit_doc.status, "Denied")
        self.assertEqual(self.exit_doc.approved_by, ACTOR)
        self.assertEqual(self.deleted_ces, [])
        self.assertNotIn("PE-1", self.pe_docs)

    def test_deny_refused_without_the_approver_role(self):
        self._pending_doc()
        with self.assertRaises(_PermissionError) as ctx:
            self.exits.deny_enrollment_dismissal(
                "test-key-enrexit-dn02", "EXIT-1")
        self.assertIn("approver role", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

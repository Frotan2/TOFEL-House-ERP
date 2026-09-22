"""S1 regression: converted-student billing guard + enrollment invoice diff.

BUG-INV-01: deny_premature_invoice must allow governed finance commands
(issue_placement_fee, approve_invoice_correction) and keep denying
out-of-band invoices for converted students.
BUG-ENR-02: enroll_in_program must refuse only invoices CREATED by the
enrollment, not pre-existing customer history.

Loads the REAL security/enrollment/policy modules against a scripted frappe
stub (no hosted stack in this sandbox). Hosted proof lives in
tools/placement/native_checks.py and executes on push CI.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"
ACTOR = "finance.officer@example.com"

DECISION_DT = "TH Admission Decision"
STUDENT = "Student"
PROGRAM = "Program"
YEAR = "Academic Year"


class _PermissionError(Exception):
    pass


class _ValidationError(Exception):
    pass


class _Doc:
    def __init__(self, doctype, payload, log):
        self.doctype = doctype
        self._payload = dict(payload)
        self._log = log
        self.flags = SimpleNamespace()
        self.name = self._payload.get("name", "PE-0001")
        self.docstatus = 0

    def __getattr__(self, key):
        if key.startswith("_"):
            raise AttributeError(key)
        return self._payload.get(key)

    def insert(self, ignore_permissions=False):
        self._log.append("insert")
        return self

    def submit(self):
        self._log.append("submit")
        self.docstatus = 1
        return self


def _load_real(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


class S1GuardTests(unittest.TestCase):
    def setUp(self):
        self.log = []
        self.invoice_reads = [[], []]
        self.converted_exists = True
        self.student_names = ["STU-1"]
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))

        fake = self

        def get_all(doctype, filters=None, fields=None, pluck=None, **kwargs):
            if doctype == STUDENT:
                return list(fake.student_names)
            if doctype == "Sales Invoice":
                fake.log.append("read-invoices")
                return list(fake.invoice_reads.pop(0))
            raise AssertionError(f"unexpected get_all {doctype}")

        def get_value(doctype, name_or_filters, fieldname=None, as_dict=False, **kwargs):
            if doctype == DECISION_DT and fieldname == "student_applicant":
                return "APP-1"
            if doctype == DECISION_DT and as_dict:
                return SimpleNamespace(
                    name="ADM-1", student_applicant="APP-1", program="TH-A1",
                    academic_year="2026-27", academic_term="", placement_decision="PD-1",
                    existing_student="", status="Approved", accepted=1, conditions="",
                    native_student="STU-1", drafted_by="d@example.com",
                    reviewed_by="r@example.com", decided_by="e@example.com")
            if doctype == STUDENT and as_dict:
                return SimpleNamespace(name="STU-1", student_applicant="APP-1",
                                        customer="CUST-1")
            if doctype == STUDENT and fieldname == "customer":
                return "CUST-1"
            raise AssertionError(f"unexpected get_value {doctype} {fieldname}")

        def exists(doctype, filters):
            if doctype in (PROGRAM, YEAR):
                return True
            if doctype == DECISION_DT:
                return fake.converted_exists
            raise AssertionError(f"unexpected exists {doctype}")

        def get_doc(doctype, name=None, **kwargs):
            if isinstance(doctype, dict):
                payload = dict(doctype)
                return _Doc(payload.pop("doctype"), payload, fake.log)
            raise AssertionError(f"unexpected get_doc {doctype}")

        stub = types.ModuleType("frappe")
        stub.session = SimpleNamespace(user=ACTOR)
        stub.conf = {"toefl_house_synthetic_only": 1, "allow_tests": 1}
        stub.local = SimpleNamespace(site="placement-test.localhost")
        stub.PermissionError = _PermissionError
        stub.ValidationError = _ValidationError
        stub.get_roles = lambda user: {"Finance Officer", "Enrollment Officer"}
        stub.get_all = get_all
        stub.get_value = get_value
        stub.exists = exists
        stub.get_doc = get_doc
        stub.whitelist = lambda **kwargs: (lambda func: func)
        stub.flags = SimpleNamespace()
        stub.utils = SimpleNamespace(today=lambda: "2026-09-22")
        stub.db = SimpleNamespace(
            get_value=get_value, exists=exists, get_all=get_all,
            count=lambda doctype, filters: 0, sql=lambda *a, **k: [],
            set_value=lambda *a, **k: None)
        sys.modules["frappe"] = stub

        package = types.ModuleType("toefl_house")
        package.__path__ = [str(APP)]
        sys.modules["toefl_house"] = package
        _load_real("toefl_house.policy", APP / "policy.py")
        self.security = _load_real("toefl_house.security", APP / "security.py")

        def _name(value, label):
            if not isinstance(value, str) or not value or len(value) > 140:
                raise _ValidationError(f"{label} required")
            return value

        admission = types.ModuleType("toefl_house.admission")
        admission.DECISION_DT = DECISION_DT
        admission.PROGRAM = PROGRAM
        admission.STUDENT = STUDENT
        admission.YEAR = YEAR
        admission._name = _name
        admission._placement_row = lambda name: SimpleNamespace(name=name)
        admission._unexpired = lambda row, now=None: None
        sys.modules["toefl_house.admission"] = admission

        api = types.ModuleType("toefl_house.api")
        api._execute = lambda kind, key, payload, work: work(ACTOR)[0]
        sys.modules["toefl_house.api"] = api

        education = types.ModuleType("education")
        education.__path__ = []
        sys.modules["education"] = education
        for dotted in ("education.education", "education.education.doctype",
                       "education.education.doctype.course_enrollment"):
            module = types.ModuleType(dotted)
            module.__path__ = []
            sys.modules[dotted] = module
        leaf = types.ModuleType(
            "education.education.doctype.course_enrollment.course_enrollment")
        leaf.CourseEnrollment = type(
            "CourseEnrollment", (), {"save": lambda self, *a, **k: None})
        sys.modules[leaf.__name__] = leaf

        self.enrollment = _load_real(
            "toefl_house.enrollment", APP / "enrollment/__init__.py")

    def _invoice(self, customer="CUST-1"):
        return SimpleNamespace(customer=customer)

    def test_out_of_band_invoice_for_converted_student_denied(self):
        with self.assertRaises(_ValidationError):
            self.enrollment.deny_premature_invoice(self._invoice())

    def test_governed_billing_command_allowed_for_converted_student(self):
        for kind in ("issue_placement_fee", "approve_invoice_correction"):
            with self.subTest(kind=kind):
                with self.security.command(kind, ACTOR):
                    self.enrollment.deny_premature_invoice(self._invoice())

    def test_tuition_command_does_not_open_sales_invoice(self):
        # The exemption is doctype-scoped: a Fees command must not allow a
        # Sales Invoice through the premature-billing guard.
        with self.security.command("issue_tuition_fees", ACTOR):
            with self.assertRaises(_ValidationError):
                self.enrollment.deny_premature_invoice(self._invoice())

    def test_unconverted_customer_invoice_allowed(self):
        self.converted_exists = False
        self.enrollment.deny_premature_invoice(self._invoice())

    def test_invoice_without_customer_ignored(self):
        self.enrollment.deny_premature_invoice(self._invoice(customer=None))

    def test_enrollment_with_only_historical_invoices_succeeds(self):
        self.invoice_reads = [["INV-OLD"], ["INV-OLD"]]
        result = self.enrollment.enroll_in_program("test-key-enroll-000001", "ADM-1")
        self.assertEqual(result["program_enrollment"], "PE-0001")
        self.assertEqual(result["sales_invoice"], 0)
        # The history snapshot is taken before the native submit; the
        # after-read follows it.
        self.assertEqual(self.log, ["read-invoices", "insert", "submit", "read-invoices"])

    def test_enrollment_refuses_invoice_created_by_submit(self):
        self.invoice_reads = [["INV-OLD"], ["INV-OLD", "INV-NEW"]]
        with self.assertRaises(_ValidationError):
            self.enrollment.enroll_in_program("test-key-enroll-000002", "ADM-1")

    def test_enrollment_with_no_invoices_succeeds(self):
        self.invoice_reads = [[], []]
        result = self.enrollment.enroll_in_program("test-key-enroll-000003", "ADM-1")
        self.assertEqual(result["program_enrollment"], "PE-0001")

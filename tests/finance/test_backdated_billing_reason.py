"""New bill reasons and old receipt compatibility against real command code.

Runs the three real billing functions and the real API receipt/replay code
with an in-memory Frappe boundary. This is focused source regression proof,
not native Windows qualification or production billing.
"""
import ast
from contextlib import contextmanager, nullcontext
from datetime import date
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"
COMMANDS = ("issue_tuition_fees", "issue_placement_fee",
            "issue_tuition_installment_plan")
OP = "TH Placement Operation"
AUDIT = "TH Placement Audit Event"


class ValidationError(Exception):
    pass


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def real_functions(path, names, namespace):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(selected) == len(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)


class Harness:
    def __init__(self):
        self.today = "2026-11-20"
        self.actor = "finance@example.test"
        self.allowed = True
        self.native_remarks_supported = True
        self.placement_rate = 100
        self.records = {}
        self.bills = []
        self.events = []
        self.authorizations = []
        self.payloads = []

        package = ModuleType("toefl_house")
        package.__path__ = [str(APP)]
        sys.modules[package.__name__] = package
        self.policy = load("toefl_house.policy", APP / "policy.py")
        frappe = ModuleType("frappe")
        frappe.ValidationError = ValidationError
        frappe.DuplicateEntryError = type("DuplicateEntryError", (Exception,), {})
        frappe.whitelist = lambda **kwargs: lambda fn: fn
        frappe.utils = SimpleNamespace(today=lambda: self.today)
        frappe.conf = {"encryption_key": "synthetic-unit-test-key"}
        frappe.db = SimpleNamespace(exists=self.exists, get_value=self.get_value,
                                    sql=lambda *args: None)
        frappe.get_cached_value = lambda *args: "AFN"
        frappe.get_doc = self.get_doc
        sys.modules["frappe"] = frappe

        security = ModuleType("toefl_house.security")
        security.finance_command_active = lambda *args: True
        security.is_production = lambda: False
        security.require_operational = lambda: None
        sys.modules[security.__name__] = security
        enrollment = ModuleType("toefl_house.enrollment")
        enrollment.deny_premature_invoice = lambda *args: None
        sys.modules[enrollment.__name__] = enrollment
        scope = ModuleType("toefl_house.command_scope")
        scope.authorize_command_scope = lambda *args, **kwargs: None
        sys.modules[scope.__name__] = scope

        api = ModuleType("toefl_house.api")
        api.__dict__.update(
            frappe=frappe, json=json, OP=OP, AUDIT=AUDIT,
            authorize=self.authorize,
            KIND_ROLES={name: "Finance Officer" for name in COMMANDS},
            command=lambda *args: nullcontext(), record_synthetic_flag=lambda: 1,
            run_with_retry=lambda work: work(),
            **{name: getattr(self.policy, name) for name in
               ("digest", "canonical", "request_digest", "validate_request_key")})
        real_functions(APP / "api.py", {"_execute", "_execute_once", "_web_integer"},
                       api.__dict__)
        sys.modules[api.__name__] = api

        self.finance = load("toefl_house.finance", APP / "finance/__init__.py")
        self.finance.resolved_billable_components = lambda *args: (
            [{"fees_category": "Tuition", "amount": 1000.0}], [], 1000.0)
        policies = ModuleType("toefl_house.finance.policies")
        policies.date = date
        real_functions(APP / "finance/policies.py", {"check_posting_bounds"},
                       policies.__dict__)
        policies.governing_billing_terms = lambda: {
            "max_backdate_days": 7, "max_future_days": 0,
            "placement_fee_timing": "any", "installments_allowed": 1,
            "max_installments": 4, "installment_interval_days": 30,
            "installment_cadence": "Days"}
        policies.check_fee_timing = lambda *args: None
        policies.validate_shamsi_cadence = lambda cadence, grace: (cadence, grace)
        policies.validate_due_day = lambda *args: 0
        sys.modules[policies.__name__] = policies
        company_scope = ModuleType("toefl_house.finance.company_scope")
        company_scope.require_finance_company = lambda *args: None
        sys.modules[company_scope.__name__] = company_scope
        self.installments = load("toefl_house.finance.installments",
                                 APP / "finance/installments.py")

    def authorize(self, role):
        self.authorizations.append(role)
        if not self.allowed:
            raise PermissionError("Finance Officer required")
        return self.actor

    def exists(self, doctype, name):
        if doctype == OP:
            return (doctype, name) in self.records
        if doctype in ("Program Enrollment", "TH Placement Case", "Customer"):
            return True
        if doctype in ("Fees", "Sales Invoice"):
            return bool(self.bills)
        raise AssertionError((doctype, name))

    def get_value(self, doctype, name, fields, **kwargs):
        if doctype == OP:
            return self.records.get((doctype, name))
        if doctype == "Program Enrollment":
            return SimpleNamespace(student="STU-1", program="GE", academic_year="1405",
                                   docstatus=1)
        if doctype == "Fee Structure":
            return SimpleNamespace(program="GE", academic_year="1405", company="TOEFL House",
                                   receivable_account="Receivables", cost_center="Main")
        if doctype == "Student":
            return "Synthetic Student"
        if doctype == "Item Price":
            return self.placement_rate
        return self.records[(doctype, name)]

    def get_doc(self, payload):
        harness = self
        class Doc(SimpleNamespace):
            def insert(self, **kwargs):
                if self.doctype == OP:
                    if (OP, self.name) in harness.records:
                        raise sys.modules["frappe"].DuplicateEntryError()
                    harness.records[(OP, self.name)] = self
                elif self.doctype == AUDIT:
                    harness.events.append(self)
                else:
                    self.name = f"BILL-{len(harness.bills) + 1}"
                    harness.bills.append(self)
                    harness.records[(self.doctype, self.name)] = self
                return self

            def submit(self):
                self.docstatus = 1
                if self.doctype == "Fees":
                    self.grand_total = sum(row["amount"] for row in self.components)
                else:
                    self.grand_total = self.items[0]["rate"]
                    self.net_total = self.grand_total
                    self.discount_amount = 0
                self.outstanding_amount = self.grand_total
                return self

            def save(self, **kwargs):
                return self

        return Doc(**payload, flags=SimpleNamespace(),
                   meta=SimpleNamespace(has_field=lambda field:
                                        self.native_remarks_supported and field == "remarks"))

    def payload(self, command, posting):
        if command == "issue_placement_fee":
            return {"case": "CASE-1", "customer": "CUSTOMER-1",
                    "posting_date": posting, "due_date": "2026-11-25"}
        payload = {"program_enrollment": "ENR-1", "fee_structure": "STRUCTURE-1",
                   "posting_date": posting}
        if command == "issue_tuition_fees":
            payload["due_date"] = "2026-11-25"
        else:
            payload.update(first_due_date="2026-11-25", installments=2, shares=None)
        return payload

    def issue(self, command, posting="2026-11-20", **extra):
        module = self.installments if command.endswith("installment_plan") else self.finance
        return getattr(module, command)("reason-regression-request-01",
                                        **self.payload(command, posting), **extra)


@contextmanager
def billing_harness():
    previous = dict(sys.modules)
    for name in list(sys.modules):
        if name == "frappe" or name == "toefl_house" or name.startswith("toefl_house."):
            del sys.modules[name]
    try:
        yield Harness()
    finally:
        sys.modules.clear()
        sys.modules.update(previous)


class BackdatedBillingReasonTests(unittest.TestCase):
    def test_new_backdated_bills_require_valid_reason_before_native_writes(self):
        for command in COMMANDS:
            for reason in (None, "", "  \n", 7, False, [], "x" * 501):
                with self.subTest(command=command, reason=repr(reason)):
                    with billing_harness() as h:
                        with self.assertRaises(ValidationError):
                            h.issue(command, "2026-11-19", backdate_reason=reason)
                        self.assertEqual(h.bills, [])
                        self.assertEqual(h.events, [])

    def test_reason_is_in_receipt_audit_and_each_supported_native_document(self):
        for command in COMMANDS:
            with self.subTest(command=command), billing_harness() as h:
                result = h.issue(command, "2026-11-19", backdate_reason="  Correct prior entry  ")
                self.assertEqual(result["backdate_reason"], "Correct prior entry")
                op = next(row for (dt, _), row in h.records.items() if dt == OP)
                self.assertEqual(json.loads(op.result_json)["backdate_reason"],
                                 "Correct prior entry")
                for bill in h.bills:
                    self.assertEqual(bill.remarks, "Backdated billing reason: Correct prior entry")
                self.assertEqual(len(h.bills), 2 if command.endswith("installment_plan") else 1)
                # A changed explanation changes the event's immutable digest.
                reason_hash = h.events[0].after_hash
            with billing_harness() as h:
                h.issue(command, "2026-11-19", backdate_reason="Different explanation")
                self.assertNotEqual(reason_hash, h.events[0].after_hash)

    def test_same_day_legacy_payload_and_result_are_unchanged(self):
        for command in COMMANDS:
            for optional in ({}, {"backdate_reason": None}, {"backdate_reason": ""}):
                with self.subTest(command=command, optional=optional), billing_harness() as h:
                    result = h.issue(command, **optional)
                    self.assertNotIn("backdate_reason", result)
                    op = next(row for (dt, _), row in h.records.items() if dt == OP)
                    self.assertEqual(op.input_hash, h.policy.request_digest(
                        h.payload(command, "2026-11-20"), "synthetic-unit-test-key"))
                    self.assertTrue(all(not hasattr(bill, "remarks") for bill in h.bills))
                    if command == "issue_tuition_fees":
                        legacy_audit = [h.bills[0].name, "ENR-1", "STRUCTURE-1",
                                        "2026-11-20", "2026-11-25", {"Tuition": 1000.0}, []]
                    elif command == "issue_placement_fee":
                        legacy_audit = [h.bills[0].name, "CASE-1", "CUSTOMER-1",
                                        "2026-11-20", "2026-11-25", 100.0]
                    else:
                        legacy_audit = ["ENR-1", "STRUCTURE-1", "2026-11-20", 2, 30,
                                        "Days", 0, 0, [], [bill.name for bill in h.bills],
                                        [500.0, 500.0], []]
                    self.assertEqual(h.events[0].after_hash, h.policy.digest(legacy_audit))

    def test_completed_legacy_receipt_replays_after_date_becomes_out_of_bounds(self):
        for command in COMMANDS:
            with self.subTest(command=command), billing_harness() as h:
                original = h.issue(command)
                bill_count = len(h.bills)
                h.today = "2026-12-30"
                self.assertEqual(h.issue(command), original)
                self.assertEqual(len(h.bills), bill_count)
                self.assertEqual(len(h.events), 1)
                self.assertEqual(h.authorizations, ["Finance Officer", "Finance Officer"])

    def test_reason_replays_but_changing_reason_conflicts(self):
        for command in COMMANDS:
            with self.subTest(command=command), billing_harness() as h:
                original = h.issue(command, "2026-11-19", backdate_reason="Late entry")
                self.assertEqual(h.issue(command, "2026-11-19", backdate_reason="Late entry"),
                                 original)
                with self.assertRaisesRegex(ValidationError, "Idempotency key conflicts"):
                    h.issue(command, "2026-11-19", backdate_reason="Changed entry")
                self.assertEqual(len(h.events), 1)

    def test_reason_cannot_bypass_seven_day_or_zero_future_bound(self):
        for command in COMMANDS:
            with self.subTest(command=command), billing_harness() as h:
                self.assertEqual(h.issue(command, "2026-11-13", backdate_reason="x" * 500)
                                 ["backdate_reason"], "x" * 500)
            for posting in ("2026-11-12", "2026-11-21"):
                with self.subTest(command=command, posting=posting), billing_harness() as h:
                    with self.assertRaisesRegex(ValidationError, "more than"):
                        h.issue(command, posting, backdate_reason="Authorized explanation")
                    self.assertEqual(h.bills, [])

    def test_native_schema_without_remarks_still_has_receipt_and_event(self):
        for command in COMMANDS:
            with self.subTest(command=command), billing_harness() as h:
                h.native_remarks_supported = False
                self.assertEqual(h.issue(command, "2026-11-19", backdate_reason="Late entry")
                                 ["backdate_reason"], "Late entry")
                self.assertEqual(len(h.events), 1)
                self.assertTrue(all(not hasattr(bill, "remarks") for bill in h.bills))

    def test_finance_authorization_still_runs_before_new_or_replayed_request(self):
        for command in COMMANDS:
            with self.subTest(command=command), billing_harness() as h:
                h.allowed = False
                with self.assertRaises(PermissionError):
                    h.issue(command, "2026-11-19", backdate_reason="Late entry")
                self.assertEqual(h.bills, [])
                h.allowed = True
                h.issue(command)
                h.allowed = False
                with self.assertRaises(PermissionError):
                    h.issue(command)

    def test_placement_reason_does_not_turn_free_placement_into_a_charge(self):
        with billing_harness() as h:
            h.placement_rate = 0
            with self.assertRaisesRegex(ValidationError, "not configured as chargeable"):
                h.issue("issue_placement_fee", "2026-11-19", backdate_reason="Late entry")
            self.assertEqual(h.bills, [])

    def test_editable_billing_forms_explain_the_conditional_reason(self):
        source = (APP / "public/js/th_role_desks.js").read_text(encoding="utf-8")
        for endpoint in ("toefl_house.finance.issue_tuition_fees",
                         "toefl_house.finance.installments.issue_tuition_installment_plan"):
            fields = source.split('"' + endpoint + '": [', 1)[1].split("\n\t\t],", 1)[0]
            self.assertIn('fieldname: "posting_date"', fields)
            self.assertIn('fieldname: "backdate_reason"', fields)
            self.assertIn("Required when the posting date is earlier than today", fields)


if __name__ == "__main__":
    unittest.main()

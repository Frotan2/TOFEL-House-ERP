"""S11 regression: the billing policy mechanism (OD-NEW-03/OD-NEW-04).

The house holds exactly one billing policy; versions carry the
effective-dated owner choice of the bounds pair
``max_backdate_days`` + ``max_future_days`` plus the placement-fee
timing threshold. Reads fail closed (no row / retired / no effective
version all resolve to {}); both billing commands judge the POSTING
date against the governing bounds and the placement fee against the
governing timing; commands route through the receipted Course Owner
gate under their own kind. Loads the REAL finance policies module
with the REAL academic + configuration rules against a scripted frappe
stub; hosted CI proves the billing journey.
"""
import ast
import importlib.util
import sys
import types
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"
ACTOR = "course.owner@example.com"
COMMANDS = (
    "create_billing_policy",
    "set_billing_policy_version",
    "set_billing_policy_status",
)


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
    """A Frappe child row: dict access plus attribute read/write.

    Real child Documents are NOT dict-convertible, so owned code must
    use row.as_dict() — mirrored here.
    """

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value

    def as_dict(self):
        return dict(self)


class _PolicyDoc:
    def __init__(self, **fields):
        self._fields = dict(fields)
        self._fields.setdefault("versions", [])
        self.inserted = False
        self.saved = False

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


class _DocumentBase:
    """Stand-in for frappe's Document: attribute access only, like hosted."""


class _DocRow:
    """A faithful real-Frappe child row: attribute access plus .get().

    Real child Documents are NOT subscriptable — row["field"] raises
    TypeError on hosted Frappe (proven by the S9 qualification, the
    first journey to supersede a policy version). Owned controller code
    must read rows via row.get(...), never row[...].
    """

    def __init__(self, **fields):
        self.__dict__["_fields"] = dict(fields)

    def __getattr__(self, name):
        try:
            return self._fields[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def get(self, field, default=None):
        return self._fields.get(field, default)


def _throw(message):
    raise _ValidationError(message)


def _install_command_harness(test):
    """Install the stub frappe plus REAL rules/command modules on test."""
    test.policy_rows = []
    test.policy_doc = None
    test.execute_calls = []
    test.today = "2026-09-22"
    test.attempts = []
    test.decisions = []
    previous = dict(sys.modules)
    test.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
    fake = test

    def get_all(doctype, fields=None, filters=None, limit=None, **kwargs):
        if doctype == "TH Billing Policy":
            rows = list(fake.policy_rows)
            if limit is not None:
                rows = rows[:limit]
            return rows
        if doctype == "TH Placement Attempt":
            return [dict(row) for row in fake.attempts
                    if row["case_name"] == (filters or {}).get("case_name")]
        raise AssertionError(f"unexpected get_all {doctype}")

    def get_value(doctype, name_or_filters, fieldname=None, **kwargs):
        if doctype == "TH Billing Policy":
            assert fake.policy_doc is not None
            return fake.policy_doc.name
        raise AssertionError(f"unexpected get_value {doctype}")

    def get_doc(doctype, name=None, for_update=False, **kwargs):
        if isinstance(doctype, dict):
            payload = dict(doctype)
            doc = _PolicyDoc(name=payload.get("code"), **payload)
            fake.policy_doc = doc
            return doc
        assert doctype == "TH Billing Policy"
        assert fake.policy_doc is not None
        return fake.policy_doc

    def exists(doctype, name):
        if doctype == "TH Billing Policy":
            return False
        if doctype == "TH Placement Decision":
            names = (name or {}).get("attempt", [None, []])[1]
            return any(row["attempt"] in names for row in fake.decisions)
        raise AssertionError(f"unexpected exists {doctype}")

    from types import SimpleNamespace
    stub = types.ModuleType("frappe")
    stub.PermissionError = _PermissionError
    stub.ValidationError = _ValidationError
    stub.whitelist = lambda **kwargs: (lambda func: func)
    stub.utils = SimpleNamespace(
        today=lambda: fake.today,
        now_datetime=lambda: "2026-09-22 12:00:00")
    stub.db = SimpleNamespace(get_all=get_all, get_value=get_value,
                              exists=exists)
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

    def _execute(kind, key, payload, work):
        fake.execute_calls.append((kind, key, dict(payload)))
        return work(ACTOR)[0]

    audit.execute = _execute
    audit.latest_after_hash = lambda target: ""
    sys.modules["toefl_house.configuration.audit"] = audit
    api = types.ModuleType("toefl_house.api")
    api._execute = _execute
    sys.modules["toefl_house.api"] = api
    security = types.ModuleType("toefl_house.security")
    security.record_synthetic_flag = lambda: 1
    sys.modules["toefl_house.security"] = security
    finance_pkg = types.ModuleType("toefl_house.finance")
    finance_pkg.__path__ = [str(APP / "finance")]
    sys.modules["toefl_house.finance"] = finance_pkg
    test.policies = _load_real(
        "toefl_house.finance.policies", APP / "finance/policies.py")


class BillingPolicyTests(unittest.TestCase):
    def setUp(self):
        _install_command_harness(self)

    def _existing_policy(self, status="Active", versions=()):
        self.policy_rows = [{"name": "BILL-POL"}]
        self.policy_doc = _PolicyDoc(name="BILL-POL", code="BILL-POL",
                                     title="Billing rule", status=status,
                                     versions=[_Row(v) for v in versions])
        return self.policy_doc

    def _version(self, key, date, back=90, fut=30, timing="any"):
        return self.policies.set_billing_policy_version(
            key, "BILL-POL", date,
            "Owner opens bounded billing", back, fut, timing)

    def test_create_shell_carries_no_versions(self):
        result = self.policies.create_billing_policy(
            "test-key-billpol-create01", "BILL-POL", "Billing rule")
        self.assertEqual(result["code"], "BILL-POL")
        self.assertEqual(result["status"], "Active")
        self.assertEqual(result["version_count"], 0)
        self.assertEqual(result["governing_placement_fee_timing"], "")
        kind, _key, _payload = self.execute_calls[0]
        self.assertEqual(kind, "create_billing_policy")

    def test_second_policy_is_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self.policies.create_billing_policy(
                "test-key-billpol-create02", "BILL-TWO", "Second rule")
        self.assertIn("version it instead", str(ctx.exception))

    def test_version_append_governs_from_its_date(self):
        self._existing_policy()
        result = self._version("test-key-billpol-versn01", "2026-09-23")
        self.assertEqual(result["version_count"], 1)
        # Not yet effective today: the shell still governs nothing.
        self.assertEqual(result["governing_max_backdate_days"], "")
        self.assertEqual(self.policies.governing_billing_terms(), {})
        self.today = "2026-09-23"
        self.assertEqual(self.policies.governing_billing_terms(), {
            "effective_from": "2026-09-23",
            "max_backdate_days": 90, "max_future_days": 30,
            "placement_fee_timing": "any"})

    def test_bad_bounds_are_refused(self):
        self._existing_policy()
        for back, fut in ((-1, 30), (30, -1), (367, 30), (30, 367),
                          (True, 30), (30, False), ("90", 30), (90, 30.5)):
            with self.assertRaises(_ValidationError):
                self._version("test-key-billpol-versn02", "2026-09-23",
                              back=back, fut=fut)

    def test_bad_timing_is_refused(self):
        self._existing_policy()
        for timing in ("someday", "Verified ", "ANY", "", None):
            with self.assertRaises(_ValidationError):
                self._version("test-key-billpol-versn03", "2026-09-23",
                              timing=timing)

    def test_backdated_and_same_day_versions_refused(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-23", "max_backdate_days": 90,
            "max_future_days": 30, "placement_fee_timing": "any",
            "reason": "Owner opens bounded billing",
            "set_by": ACTOR, "set_on": "2026-09-22 12:00:00"}])
        with self.assertRaises(_ValidationError):
            self._version("test-key-billpol-versn04", "2026-09-20")
        with self.assertRaises(_ValidationError):
            self._version("test-key-billpol-versn05", "2026-09-23")

    def test_superseded_version_is_closed_not_rewritten(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-23", "max_backdate_days": 90,
            "max_future_days": 30, "placement_fee_timing": "any",
            "reason": "Owner opens bounded billing",
            "set_by": ACTOR, "set_on": "2026-09-22 12:00:00"}])
        self._version("test-key-billpol-versn06", "2026-10-01",
                      back=7, fut=7, timing="released")
        first, second = self.policy_doc.versions
        self.assertEqual(first["max_backdate_days"], 90)
        self.assertEqual(first["placement_fee_timing"], "any")
        self.assertEqual(first["superseded_on"], "2026-10-01")
        self.assertEqual(second["max_backdate_days"], 7)
        self.assertNotIn("superseded_on", second)

    def test_retire_is_the_off_switch(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-20", "max_backdate_days": 90,
            "max_future_days": 30, "placement_fee_timing": "any",
            "reason": "Owner opens bounded billing",
            "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}])
        self.assertEqual(
            self.policies.governing_billing_terms()["max_backdate_days"], 90)
        result = self.policies.set_billing_policy_status(
            "test-key-billpol-status1", "BILL-POL", 0)
        self.assertEqual(result["status"], "Retired")
        self.assertEqual(self.policies.governing_billing_terms(), {})
        self.policies.set_billing_policy_status(
            "test-key-billpol-status2", "BILL-POL", 1)
        self.assertEqual(
            self.policies.governing_billing_terms()["max_future_days"], 30)

    def test_governing_read_fails_closed_without_policy_or_version(self):
        self.assertEqual(self.policies.governing_billing_terms(), {})
        self._existing_policy()
        self.assertEqual(self.policies.governing_billing_terms(), {})


class BillingBoundsTests(unittest.TestCase):
    def setUp(self):
        _install_command_harness(self)

    def test_today_and_edges_pass(self):
        check = self.policies.check_posting_bounds
        check("2026-09-22", "2026-09-22", 90, 30)
        check("2026-06-24", "2026-09-22", 90, 30)
        check("2026-10-22", "2026-09-22", 90, 30)
        check("2026-09-22", "2026-09-22", 0, 0)

    def test_past_and_future_overflow_refused(self):
        check = self.policies.check_posting_bounds
        with self.assertRaises(ValueError) as ctx:
            check("2026-06-23", "2026-09-22", 90, 30)
        self.assertIn("more than 90 days back", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            check("2026-10-23", "2026-09-22", 90, 30)
        self.assertIn("more than 30 days forward", str(ctx.exception))
        with self.assertRaises(ValueError):
            check("2026-09-21", "2026-09-22", 0, 0)
        with self.assertRaises(ValueError):
            check("2026-09-23", "2026-09-22", 0, 0)

    def test_day_bound_vocabulary(self):
        validate = self.policies.validate_day_bound
        self.assertEqual(validate(0, "Max backdate days"), 0)
        self.assertEqual(validate(366, "Max backdate days"), 366)
        for bad in (-1, 367, True, False, "90", 90.0, None):
            with self.assertRaises(ValueError):
                validate(bad, "Max backdate days")


class BillingTimingTests(unittest.TestCase):
    def setUp(self):
        _install_command_harness(self)

    def test_any_bills_without_attempts(self):
        self.policies.check_fee_timing("CASE-1", "any")

    def test_timing_vocabulary(self):
        validate = self.policies.validate_timing
        self.assertEqual(validate("any"), "any")
        self.assertEqual(validate("released"), "released")
        for stage in ("Allocated", "Verified", "In Progress", "Sealed",
                      "Marking", "Review", "Finalized"):
            self.assertEqual(validate(stage), stage)
        for bad in ("someday", "ANY", "Released", "", None):
            with self.assertRaises(ValueError):
                validate(bad)

    def test_stage_threshold_follows_the_best_attempt(self):
        self.attempts = [
            {"case_name": "CASE-1", "name": "ATT-1", "status": "Allocated"},
            {"case_name": "CASE-1", "name": "ATT-2", "status": "Sealed"},
            {"case_name": "CASE-2", "name": "ATT-3", "status": "Finalized"}]
        check = self.policies.check_fee_timing
        check("CASE-1", "Allocated")
        check("CASE-1", "Sealed")
        with self.assertRaises(ValueError) as ctx:
            check("CASE-1", "Finalized")
        self.assertIn("once the case reaches Finalized", str(ctx.exception))
        check("CASE-2", "Finalized")
        with self.assertRaises(ValueError):
            check("CASE-9", "Allocated")

    def test_released_needs_a_decision(self):
        self.attempts = [
            {"case_name": "CASE-1", "name": "ATT-1", "status": "Finalized"}]
        check = self.policies.check_fee_timing
        with self.assertRaises(ValueError) as ctx:
            check("CASE-1", "released")
        self.assertIn("after the decision is released", str(ctx.exception))
        self.decisions = [{"attempt": "ATT-1"}]
        check("CASE-1", "released")
        self.decisions = [{"attempt": "ATT-9"}]
        with self.assertRaises(ValueError):
            check("CASE-1", "released")


class BillingPolicyGateTests(unittest.TestCase):
    """Source-level receipt-gate parity with the S5/S7/S8 policy commands."""

    def test_commands_route_through_the_receipted_gate(self):
        source = (APP / "finance/policies.py").read_text(encoding="utf-8")
        audit_source = (APP / "configuration/audit.py").read_text(encoding="utf-8")
        audit_tree = ast.parse(audit_source)
        kinds = None
        for node in ast.walk(audit_tree):
            if (isinstance(node, ast.Assign)
                    and getattr(node.targets[0], "id", "") == "KIND_AUTHORITY"):
                kinds = ast.literal_eval(node.value)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in COMMANDS:
                calls = ast.unparse(node)
                self.assertIn("configuration_audit.execute(", calls,
                              f"{node.name} must route through the receipted gate")
                self.assertIn(f"'{node.name}', request_key", calls,
                              f"{node.name} must execute under its own kind")
                self.assertEqual(kinds.get(node.name), "business_policy",
                                 f"{node.name} must bind the Course Owner authority")
                args = [a.arg for a in node.args.args]
                self.assertEqual(args[0], "request_key", f"{node.name} must be idempotent")
                position = source.index(f"def {node.name}")
                self.assertIn("@frappe.whitelist", source[max(0, position - 200):position],
                              f"{node.name} must stay whitelisted")

    def test_billing_commands_judge_the_governing_terms(self):
        source = (APP / "finance/__init__.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        def body(name):
            fn = next(n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef) and n.name == name)
            return ast.unparse(fn)

        for name in ("issue_tuition_fees", "issue_placement_fee"):
            code = body(name)
            self.assertIn("governing_billing_terms", code,
                          f"{name} must read the governing terms")
            self.assertIn("check_posting_bounds", code,
                          f"{name} must judge the posting date")
        self.assertIn("check_fee_timing", body("issue_placement_fee"),
                      "issue_placement_fee must judge the fee timing")
        self.assertNotIn("check_fee_timing", body("issue_tuition_fees"),
                         "tuition billing knows no pipeline timing")


class BillingPolicyControllerTests(unittest.TestCase):
    """The policy CONTROLLER validates real child Documents, not dicts.

    The command-layer tests above run against dict doubles, which are
    subscriptable — so they could not see a row["field"] TypeError of
    the kind the S9 hosted qualification caught on the first
    second-version append. These tests run the REAL controller
    validate against faithful non-subscriptable rows.
    """

    CONTROLLER = APP / ("finance/doctype/th_billing_policy/"
                        "th_billing_policy.py")

    def setUp(self):
        _install_command_harness(self)
        stub = sys.modules["frappe"]
        stub.throw = _throw
        stub._ = lambda message: message
        sys.modules["frappe.model"] = types.ModuleType("frappe.model")
        document_mod = types.ModuleType("frappe.model.document")
        document_mod.Document = _DocumentBase
        sys.modules["frappe.model.document"] = document_mod
        self.controller = _load_real(
            "toefl_house.finance.doctype.th_billing_policy.th_billing_policy",
            self.CONTROLLER)
        self.foundation = sys.modules["toefl_house.configuration.rules"]

    def _doc(self, versions):
        return _PolicyDoc(
            name="BILL-POL", code="BILL-POL", title="Billing rule",
            status="Active", versions=[_DocRow(**version) for version in versions])

    def _version(self, effective, superseded=None, back=90, fut=30,
                 timing="any"):
        row = {"effective_from": effective, "max_backdate_days": back,
               "max_future_days": fut, "placement_fee_timing": timing,
               "reason": "Owner opens bounded billing",
               "set_by": ACTOR, "set_on": "2026-09-22 12:00:00"}
        if superseded is not None:
            row["superseded_on"] = superseded
        return row

    def test_superseded_row_validates_without_subscript(self):
        doc = self._doc([self._version("2026-09-20", superseded="2026-09-23"),
                         self._version("2026-09-23")])
        with self.foundation.command_context("set_billing_policy_version"):
            self.controller.validate(doc)

    def test_closed_date_before_effective_is_still_refused(self):
        doc = self._doc([self._version("2026-09-23", superseded="2026-09-20")])
        with self.foundation.command_context("set_billing_policy_version"):
            with self.assertRaises(_ValidationError) as ctx:
                self.controller.validate(doc)
        self.assertIn("must fall after its effective date", str(ctx.exception))

    def test_bad_terms_in_a_row_are_refused(self):
        for version in (self._version("2026-09-23", back=-1),
                        self._version("2026-09-23", fut=367),
                        self._version("2026-09-23", timing="someday")):
            doc = self._doc([version])
            with self.foundation.command_context("set_billing_policy_version"):
                with self.assertRaises(ValueError):
                    self.controller.validate(doc)

    def test_validate_outside_a_command_is_refused_first(self):
        doc = self._doc([self._version("2026-09-23")])
        with self.assertRaises(_PermissionError):
            self.controller.validate(doc)


class BillingPolicyControllerRowAccessTests(unittest.TestCase):
    """The billing controller reads child rows without subscripts."""

    def test_version_checks_read_rows_without_subscripts(self):
        path = BillingPolicyControllerTests.CONTROLLER
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name == "before_save":
                continue
            for child in ast.walk(node):
                if (isinstance(child, ast.Subscript)
                        and isinstance(child.value, ast.Name)
                        and child.value.id == "row"):
                    self.fail(
                        f"{path.name}:{child.lineno}: child-row Documents "
                        "are not subscriptable on real Frappe; "
                        "use row.get(...)")


if __name__ == "__main__":
    unittest.main()

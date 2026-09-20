"""Lifecycle proof for the Academic Control Plane (mission §33/§45).

Drives the REAL guarded commands against an in-memory frappe backend, so the
command logic itself — gates, wiring, version appends, refusals, retry
semantics — is exercised, not just the pure rules:

    create program -> create ordered levels -> progression link
    -> enroll (fake submitted enrollment under the governing version)
    -> change the duration policy -> prove the new version governs new dates
    -> prove the historical resolution and the closed version are untouched
    -> prove deactivation is refused in business language while in use.
"""
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "apps/toefl_house/toefl_house"


class _Row(dict):
    """A child-table row; attribute writes must stick (superseded_on stamp)."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key, value):
        self[key] = value


class _Doc:
    def __init__(self, backend, doctype, payload):
        self._backend = backend
        self.doctype = doctype
        self._payload = dict(payload)
        self.flags = types.SimpleNamespace(ignore_permissions=False, ignore_links=False)
        for key, value in payload.items():
            if isinstance(value, list):
                self._payload[key] = [_Row(row) for row in value]
        self.name = self._payload.get("name")

    def __getattr__(self, key):
        try:
            return self.__dict__["_payload"][key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key, value):
        if key in ("_backend", "doctype", "_payload", "name", "flags"):
            self.__dict__[key] = value
            return
        self._payload[key] = value

    def get(self, key, default=None):
        return self._payload.get(key, default)

    def append(self, table, row):
        self._payload.setdefault(table, []).append(_Row(row))

    def set(self, field, value):
        """Mirror frappe Document.set for table replacement."""
        self._payload[field] = [_Row(row) if isinstance(row, dict) else row
                                for row in value]

    def insert(self, ignore_permissions=False):
        store = self._backend.store.setdefault(self.doctype, {})
        # Real frappe stamps docstatus 0 on insert; the fake mirrors that so
        # docstatus filters behave.
        self._payload.setdefault("docstatus", 0)
        # Real frappe keeps an explicitly assigned name (idempotency
        # receipts name themselves); the fake mirrors that.
        key = (self._payload.get("name") or self._payload.get("code")
               or self._payload.get("program_name")
               or self._payload.get("academic_year_name")
               or self._payload.get("category_name"))
        if not key:
            prefix = "EDU-FEE-" if self.doctype == "Fees" else (
                "CORR-" if self.doctype == "TH Correction Request" else (
                    "POL-" if self.doctype == "TH Correction Policy" else "EDU-FST-"))
            key = prefix + str(len(store) + 1).zfill(5)
        self.name = key
        self._payload["name"] = key
        if self.doctype == "Fees":
            # Mirror the pinned native Education Fees.calculate_total()
            # (education 93bc70757533): grand_total is the PLAIN sum of
            # component amounts. The native controller never applies the
            # child discount field — which is exactly why the finance
            # command bills net amounts (see tests/configuration/
            # test_discount_math.py and the hosted odcp-discount-* checks).
            total = 0.0
            for comp in self._payload.get("components") or []:
                total += float(comp.get("amount") or 0)
            self._payload.setdefault("grand_total", total)
            self._payload.setdefault("outstanding_amount", total)
            self._payload.setdefault("currency", "USD")
        store[key] = self
        return self

    def save(self, ignore_permissions=False):
        return self

    def submit(self):
        self._payload["docstatus"] = 1
        return self

    def cancel(self):
        self._payload["docstatus"] = 2
        return self


class _FakeFrappe:
    def __init__(self, roles, enrollments=()):
        self.session = types.SimpleNamespace(user="owner@example.com")
        self.store = {}
        self.store.setdefault("User", {})["owner@example.com"] = {
            "name": "owner@example.com", "enabled": 1}
        self.conf = {
            "toefl_house_synthetic_only": 1,
            "allow_tests": 1,
            "encryption_key": "test-secret-key-32-bytes-long!"
        }
        self.local = types.SimpleNamespace(site="placement-test.localhost")
        self._roles = set(roles)
        for index, row in enumerate(enrollments):
            self.store.setdefault("Program Enrollment", {})[f"ENR-{index}"] = dict(row)
        self.PermissionError = type("PermissionError", (Exception,), {})
        self.ValidationError = type("ValidationError", (Exception,), {})
        utils = types.ModuleType("frappe.utils")
        utils.today = lambda: "2026-09-17"
        utils.now_datetime = lambda: datetime(2026, 9, 17, 12, 0, 0)
        utils.get_datetime = lambda v=None: datetime.now() if v is None else (
            v if isinstance(v, datetime) else datetime.fromisoformat(str(v)))
        self.utils = utils

    def get_roles(self, user):
        return self._roles if user == self.session.user else set()

    def get_value(self, doctype, filters, fieldname=None, as_dict=False, for_update=False):
        store = self.store.get(doctype, {})
        if isinstance(filters, str):
            record = store.get(filters)
        else:
            record = next((doc for doc in store.values()
                           if all(doc.get(k) == v for k, v in dict(filters).items())), None)
        if record is None:
            return None
        payload = record._payload if hasattr(record, "_payload") else record
        if as_dict:
            if isinstance(fieldname, (list, tuple)):
                return _Row({f: payload.get(f) for f in fieldname})
            return _Row(payload)
        if isinstance(fieldname, str):
            return payload.get(fieldname)
        if isinstance(fieldname, (list, tuple)):
            return [payload.get(field) for field in fieldname]
        return record.name if hasattr(record, "name") else payload.get("name")

    def exists(self, doctype, filters):
        return self.get_value(doctype, filters, "name") is not None

    def count(self, doctype, filters):
        rows = [doc for doc in self.store.get(doctype, {}).values()
                if all(doc.get(k) == v for k, v in dict(filters).items())]
        return len(rows)

    def get_all(self, doctype, filters=None, fields=None, **kwargs):
        matched = []
        for doc in self.store.get(doctype, {}).values():
            payload = doc._payload if hasattr(doc, "_payload") else doc
            if all(payload.get(k) == v for k, v in dict(filters or {}).items()):
                matched.append(dict(payload))
        if not matched and filters and "parent" in filters:
            parent_dt = filters.get("parenttype")
            parent_name = filters.get("parent")
            candidates = self.store.get(parent_dt, {}).values() if parent_dt else [
                d for docs in self.store.values() for d in docs.values()
            ]
            for parent_doc in candidates:
                p_payload = parent_doc._payload if hasattr(parent_doc, "_payload") else parent_doc
                if p_payload.get("name") == parent_name:
                    for child_list in p_payload.values():
                        if isinstance(child_list, list):
                            for row in child_list:
                                if isinstance(row, dict):
                                    row_copy = dict(row)
                                    row_copy["parent"] = parent_name
                                    row_copy["parenttype"] = parent_dt
                                    matched.append(_Row(row_copy))
        return matched

    def get_doc(self, doctype, name=None, for_update=False):
        if isinstance(doctype, dict):
            payload = dict(doctype)
            return _Doc(self, payload.pop("doctype"), payload)
        if name is None:
            return _Doc(self, doctype, {"doctype": doctype})
        return self.store.get(doctype, {})[name]

    def sql(self, query, values=(), as_dict=False):
        if "SELECT @@SESSION.innodb_lock_wait_timeout" in str(query):
            return [[50]]
        return []

    def get_cached_value(self, doctype, name, fieldname):
        return self.get_value(doctype, name, fieldname)


def _load_module(roles, enrollments=()):
    fake = _FakeFrappe(roles, enrollments)
    previous = {key: sys.modules.get(key)
                for key in ("frappe", "frappe.utils", "toefl_house", "toefl_house.policy",
                            "toefl_house.academic", "toefl_house.academic.rules",
                            "toefl_house.configuration", "toefl_house.configuration.rules",
                            "toefl_house.configuration.audit", "toefl_house.transactions")}
    # Auto-loaded command modules bind `import frappe` at import time: evict
    # them so every test re-imports against ITS stub instead of inheriting
    # the first test's backend (stale gates, writes landing in the wrong
    # store, and exception classes the current fake cannot catch).
    for key in ("toefl_house.configuration", "toefl_house.configuration.rules",
                "toefl_house.configuration.audit", "toefl_house.transactions",
                "toefl_house.academic.rules"):
        sys.modules.pop(key, None)
    stub = types.ModuleType("frappe")
    for attr in ("session", "PermissionError", "ValidationError", "utils",
                 "get_roles", "get_value", "exists", "count", "get_all", "get_doc",
                 "get_cached_value", "conf", "local"):
        setattr(stub, attr, getattr(fake, attr))
    stub.whitelist = lambda **kwargs: (lambda func: func)
    stub.flags = types.SimpleNamespace()
    stub.QueryDeadlockError = type("QueryDeadlockError", (Exception,), {})
    stub.QueryTimeoutError = type("QueryTimeoutError", (Exception,), {})
    stub.DoesNotExistError = type("DoesNotExistError", (Exception,), {})
    stub.DuplicateEntryError = type("DuplicateEntryError", (Exception,), {})
    stub.db = types.SimpleNamespace(
        get_value=fake.get_value, exists=fake.exists,
        count=fake.count, get_all=fake.get_all, sql=fake.sql,
        db_type="mariadb", transaction_writes=0, _disable_transaction_control=0,
        commit=lambda: None, rollback=lambda: None)
    sys.modules["frappe"] = stub
    sys.modules["frappe.utils"] = stub.utils
    package = types.ModuleType("toefl_house")
    package.__path__ = [str(APP)]
    sys.modules["toefl_house"] = package
    policy_spec_file = APP / "policy.py"
    import importlib.util
    policy_spec = importlib.util.spec_from_file_location("toefl_house.policy", policy_spec_file)
    policy = importlib.util.module_from_spec(policy_spec)
    sys.modules["toefl_house.policy"] = policy
    policy_spec.loader.exec_module(policy)
    academic_spec = importlib.util.spec_from_file_location(
        "toefl_house.academic", APP / "academic/__init__.py")
    academic = importlib.util.module_from_spec(academic_spec)
    academic.__path__ = [str(APP / "academic")]
    sys.modules["toefl_house.academic"] = academic
    academic_spec.loader.exec_module(academic)
    try:
        yield academic, fake
    finally:
        for key, value in previous.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value


class AcademicLifecycleTests(unittest.TestCase):
    def _lifecycle(self, academic, fake):
        academic.create_program("R" * 24, "GEN-ENG", "General English",
                                "The owner typed this title.")
        academic.create_level("R" * 24, "GEN-ENG", "STARTER", "Starter", 1,
                              2, "Month", "2026-01-01")
        academic.create_level("R" * 24, "GEN-ENG", "PREP-1", "Prep One", 2,
                              2, "Month", "2026-01-01", next_level="")
        academic.set_next_level("R" * 24, "STARTER", "PREP-1")
        return academic, fake


    def test_owner_builds_a_program_and_levels_through_the_gate(self):
        for academic, fake in _load_module({"Course Owner"}):
            self._lifecycle(academic, fake)
            starter = fake.store["TH Program Level"]["STARTER"]
            prep = fake.store["TH Program Level"]["PREP-1"]
            self.assertEqual(starter.next_level, "PREP-1")
            # The level IS a native Program (the consumption anchor):
            native = fake.store["Program"]["General English — Starter"]
            self.assertEqual(native.program_abbreviation, "STARTER")
            self.assertEqual(starter.native_program, native.name)
            self.assertEqual(prep.sequence, 2)

    def test_duration_change_governs_only_new_dates(self):
        for academic, fake in _load_module({"Course Owner"}):
            self._lifecycle(academic, fake)
            academic.set_level_duration("R" * 24, "STARTER", 3, "Month",
                                        "2026-07-01", "Semester restructure")
            starter = fake.store["TH Program Level"]["STARTER"]
            versions = starter.get("durations")
            self.assertEqual(len(versions), 2)
            # The old version is CLOSED, not rewritten:
            self.assertEqual(versions[0]["duration_value"], 2)
            self.assertEqual(str(versions[0]["superseded_on"]), "2026-07-01")
            self.assertEqual(str(versions[1]["effective_from"]), "2026-07-01")
            # Resolution follows the hard rule on both sides of the boundary:
            self.assertEqual(rules_governing(versions, "2026-06-30")["duration_value"], 2)
            self.assertEqual(rules_governing(versions, "2026-07-01")["duration_value"], 3)

    def test_deactivation_is_refused_with_the_real_count(self):
        for academic, fake in _load_module(
                {"Course Owner"},
                enrollments=[{"program": "General English — Starter", "docstatus": 1},
                             {"program": "General English — Starter", "docstatus": 1}]):
            self._lifecycle(academic, fake)
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.set_level_status("R" * 24, "STARTER", 0)
            self.assertIn("2 submitted enrollment", str(ctx.exception))
            self.assertIn("cannot be deactivated", str(ctx.exception))
            # A level without enrollments retires cleanly:
            academic.set_level_status("R" * 24, "PREP-1", 0)
            self.assertEqual(fake.store["TH Program Level"]["PREP-1"].status, "Retired")

    def test_program_deactivation_refuses_while_levels_are_active(self):
        for academic, fake in _load_module({"Course Owner"}):
            self._lifecycle(academic, fake)
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.set_program_status("R" * 24, "GEN-ENG", 0)
            self.assertIn("2 active level", str(ctx.exception))

    def test_the_gate_refuses_everyone_else(self):
        for roles in (set(), {"Reception"}, {"Academic Manager"}, {"General Manager"}):
            for academic, fake in _load_module(roles):
                with self.assertRaises(fake.PermissionError):
                    academic.create_program("R" * 24, "X-1", "Anything")
                with self.assertRaises(fake.PermissionError):
                    academic.set_level_duration("R" * 24, "STARTER", 2, "Month",
                                                "2027-01-01")

    def test_validation_refusals_from_the_command_path(self):
        for academic, fake in _load_module({"Course Owner"}):
            self._lifecycle(academic, fake)
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.create_program("R" * 24, "GEN-ENG", "Duplicate")
            self.assertIn("already exists", str(ctx.exception))
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.create_level("R" * 24, "GEN-ENG", "PREP-2", "Prep Two", 1,
                                      2, "Month", "2026-01-01")
            self.assertIn("cannot share one position", str(ctx.exception))
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.set_level_duration("R" * 24, "STARTER", 2, "Month",
                                            "2025-01-01")  # before the latest version
            self.assertIn("after the latest version", str(ctx.exception))
            with self.assertRaises(fake.ValidationError):
                academic.create_level("R" * 24, "GEN-ENG", "BAD CODE!", "Bad", 3,
                                      2, "Month", "2026-01-01")


class FeeConfigurationLifecycleTests(unittest.TestCase):
    def _fee_world(self, academic, fake):
        """Program + level + year + fee types + a single company with defaults."""
        AcademicLifecycleTests()._lifecycle(academic, fake)
        academic.create_academic_year("R" * 24, "2026-27", "2026-07-01", "2027-06-30")
        fake.store.setdefault("Item Group", {})["Fee Component"] = {"name": "Fee Component"}
        fake.store.setdefault("Company", {})["TOEFL House"] = {
            "name": "TOEFL House", "default_receivable_account": "Debtors - TH"}
        for fee_type in ("Tuition Fee", "Identity Card Fee"):
            academic.create_fee_type("R" * 24, fee_type, "")
        return academic, fake

    def _world(self):
        for academic, fake in _load_module({"Course Owner"}):
            self._fee_world(academic, fake)
            yield academic, fake

    def test_owner_configures_a_fee_plan_component_by_component(self):
        for academic, fake in self._world():
            academic.set_level_fee_component("R" * 24, "STARTER", "2026-27",
                                             "Tuition Fee", 5000)
            result = academic.set_level_fee_component("R" * 24, "STARTER", "2026-27",
                                                      "Identity Card Fee", 300)
            self.assertEqual(result["total"], 5300.0)
            structure = fake.store["Fee Structure"][result["fee_structure"]]
            # The plan is the native structure keyed on the anchored program:
            starter = fake.store["TH Program Level"]["STARTER"]
            self.assertEqual(structure.program, starter.native_program)
            self.assertEqual(structure.academic_year, "2026-27")
            self.assertEqual(structure.company, "TOEFL House")
            self.assertEqual(structure.receivable_account, "Debtors - TH")
            self.assertEqual(int(structure.docstatus or 0), 0,
                             "the managed plan stays editable (Draft)")

    def test_upsert_updates_and_replays_without_duplicating(self):
        for academic, fake in self._world():
            academic.set_level_fee_component("R" * 24, "STARTER", "2026-27",
                                             "Tuition Fee", 5000)
            academic.set_level_fee_component("R" * 24, "STARTER", "2026-27",
                                             "Tuition Fee", 6000)
            result = academic.set_level_fee_component("R" * 24, "STARTER", "2026-27",
                                                      "Tuition Fee", 6000)
            self.assertTrue(result["replayed"])
            self.assertEqual(len(result["components"]), 1)
            self.assertEqual(result["total"], 6000.0)

    def test_removal_keeps_at_least_one_component(self):
        for academic, fake in self._world():
            academic.set_level_fee_component("R" * 24, "STARTER", "2026-27",
                                             "Tuition Fee", 5000)
            academic.set_level_fee_component("R" * 24, "STARTER", "2026-27",
                                             "Identity Card Fee", 300)
            result = academic.remove_level_fee_component("R" * 24, "STARTER",
                                                         "2026-27", "Identity Card Fee")
            self.assertEqual([row["category"] for row in result["components"]],
                             ["Tuition Fee"])
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.remove_level_fee_component("R" * 24, "STARTER",
                                                    "2026-27", "Tuition Fee")
            self.assertIn("at least one component", str(ctx.exception))

    def test_fee_refusals_name_the_missing_configuration(self):
        for academic, fake in self._world():
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.set_level_fee_component("R" * 24, "STARTER", "2025-26",
                                                 "Tuition Fee", 5000)
            self.assertIn("2025-26 does not exist yet", str(ctx.exception))
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.set_level_fee_component("R" * 24, "STARTER", "2026-27",
                                                 "Diploma Fee", 5000)
            self.assertIn("Diploma Fee does not exist yet", str(ctx.exception))
            # Ambiguity refuses instead of guessing:
            fake.store["Company"]["Second Co"] = {
                "name": "Second Co", "default_receivable_account": "Debtors - S2"}
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.set_level_fee_component("R" * 24, "STARTER", "2026-27",
                                                 "Tuition Fee", 5000)
            self.assertIn("More than one company", str(ctx.exception))
            # Explicit company resolves it:
            result = academic.set_level_fee_component("R" * 24, "STARTER", "2026-27",
                                                      "Tuition Fee", 5000,
                                                      company="Second Co")
            self.assertEqual(result["company"], "Second Co")

    def test_fee_commands_refuse_the_wrong_role(self):
        for roles in (set(), {"Finance Manager"}, {"Finance Officer"}):
            for academic, fake in _load_module(roles):
                with self.assertRaises(fake.PermissionError):
                    academic.set_level_fee_component("R" * 24, "STARTER", "2026-27",
                                                     "Tuition Fee", 5000)
                with self.assertRaises(fake.PermissionError):
                    academic.create_fee_type("R" * 24, "Sneaky Fee")


class DiscountConfigurationLifecycleTests(unittest.TestCase):
    def test_owner_manages_discount_rules(self):
        for academic, fake in _load_module({"Course Owner"}):
            fake.store.setdefault("Item Group", {})["Fee Component"] = {"name": "Fee Component"}
            academic.create_fee_type("R" * 24, "Tuition Fee", "")
            rule = academic.create_discount_rule(
                "R" * 24, "SCHOLARSHIP-10", "10% Merit Scholarship", 10.0,
                precedence=10, fee_category="Tuition Fee")
            self.assertEqual(rule["code"], "SCHOLARSHIP-10")
            self.assertEqual(rule["discount_percentage"], 10.0)
            self.assertEqual(rule["precedence"], 10)
            self.assertEqual(rule["status"], "Active")

            # Duplicate rejected
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.create_discount_rule(
                    "R" * 24, "SCHOLARSHIP-10", "Duplicate", 10.0)
            self.assertIn("already exists", str(ctx.exception))

            # Deactivate (retire)
            retired = academic.set_discount_rule_status("R" * 24, "SCHOLARSHIP-10", 0)
            self.assertEqual(retired["status"], "Retired")

            # Reactivate
            active = academic.set_discount_rule_status("R" * 24, "SCHOLARSHIP-10", 1)
            self.assertEqual(active["status"], "Active")

    def test_discount_commands_refuse_unauthorized_roles(self):
        for roles in (set(), {"Reception"}, {"Finance Officer"}, {"Academic Manager"}):
            for academic, fake in _load_module(roles):
                with self.assertRaises(fake.PermissionError):
                    academic.create_discount_rule(
                        "R" * 24, "RULE-1", "Rule 1", 10.0)
                with self.assertRaises(fake.PermissionError):
                    academic.set_discount_rule_status("R" * 24, "RULE-1", 0)


class AcceptanceRehearsalTests(unittest.TestCase):
    """Mission §45 Final Acceptance Rehearsal.

    Owner defines GE + 5 levels + 2-month durations + fee types + 10% scholarship
    + one progression rule; Reception->Admission->Enrollment->Finance all consume
    config automatically; later tuition change -> new enrollment uses new config,
    historical enrollment unchanged.
    """

    def test_mission_acceptance_rehearsal_end_to_end(self):
        for academic, fake in _load_module({"Course Owner", "Finance Officer", "Finance Manager"}):
            # 1. Setup prerequisite company & item group
            fake.store.setdefault("Item Group", {})["Fee Component"] = {"name": "Fee Component"}
            fake.store.setdefault("Company", {})["TOEFL House"] = {
                "name": "TOEFL House", "default_receivable_account": "Debtors - TH",
                "default_currency": "USD"}
            fake.store.setdefault("Role", {})["Finance Manager"] = {"name": "Finance Manager"}

            # 2. Owner defines GE program family
            prog = academic.create_program("R" * 24, "GEN-ENG", "General English Track",
                                           "Institutional track")
            self.assertEqual(prog["code"], "GEN-ENG")

            # 3. Owner defines 5 levels with 2-month durations
            levels = [
                ("LVL-1", "Starter", 1),
                ("LVL-2", "Elementary", 2),
                ("LVL-3", "Pre-Intermediate", 3),
                ("LVL-4", "Intermediate", 4),
                ("LVL-5", "Upper-Intermediate", 5),
            ]
            for code, title, seq in levels:
                lvl = academic.create_level("R" * 24, "GEN-ENG", code, title, seq,
                                            2, "Month", "2026-01-01")
                self.assertEqual(lvl["duration"], "2 months")

            # 4. Owner defines progression rule: LVL-1 progresses to LVL-2
            academic.set_next_level("R" * 24, "LVL-1", "LVL-2")
            self.assertEqual(fake.store["TH Program Level"]["LVL-1"].next_level, "LVL-2")

            # 5. Owner defines academic year and fee type
            academic.create_academic_year("R" * 24, "2026-27", "2026-07-01", "2027-06-30")
            academic.create_fee_type("R" * 24, "Tuition Fee", "Core tuition charge")

            # 6. Owner defines fee plan for LVL-1 (5000 Tuition Fee)
            fee_plan = academic.set_level_fee_component("R" * 24, "LVL-1", "2026-27",
                                                        "Tuition Fee", 5000)
            self.assertEqual(fee_plan["total"], 5000.0)

            # 7. Owner defines 10% scholarship discount rule (Policy A)
            disc = academic.create_discount_rule("R" * 24, "SCHOLARSHIP-10",
                                                "10% Scholarship", 10.0,
                                                precedence=10, fee_category="Tuition Fee")
            self.assertEqual(disc["discount_percentage"], 10.0)

            # 8. Load Finance and Corrections modules
            import importlib.util
            fin_spec = importlib.util.spec_from_file_location(
                "toefl_house.finance", APP / "finance/__init__.py")
            finance = importlib.util.module_from_spec(fin_spec)
            fin_spec.loader.exec_module(finance)

            corr_spec = importlib.util.spec_from_file_location(
                "toefl_house.finance.corrections", APP / "finance/corrections.py")
            corrections = importlib.util.module_from_spec(corr_spec)
            corr_spec.loader.exec_module(corrections)

            # Native Program for LVL-1:
            lvl1_doc = fake.store["TH Program Level"]["LVL-1"]
            native_prog = lvl1_doc.native_program

            # Simulate Student A enrollment
            fake.store.setdefault("Student", {})["STU-001"] = {
                "name": "STU-001", "student_name": "Student Alpha"}
            fake.store.setdefault("Program Enrollment", {})["ENR-001"] = {
                "name": "ENR-001", "student": "STU-001", "program": native_prog,
                "academic_year": "2026-27", "docstatus": 1, "enrollment_date": "2026-08-01"}

            # Finance issues tuition fees for Student A
            # (Consumes configured fee plan + discount rule automatically)
            fees_res_1 = finance.issue_tuition_fees("R" * 24, "ENR-001", fee_plan["fee_structure"],
                                                    "2026-08-02", "2026-08-30")
            fees_1 = fake.store["Fees"][fees_res_1["fees"]]
            self.assertEqual(float(fees_1.grand_total), 4500.0)  # 5000 - 10% scholarship = 4500
            self.assertEqual(len(fees_res_1.get("discounts_applied", [])), 1)
            self.assertEqual(fees_res_1["discounts_applied"][0]["rule_code"], "SCHOLARSHIP-10")

            # 9. LATER TUITION CHANGE (§45)
            # Owner changes Tuition Fee from 5000 to 6000
            updated_plan = academic.set_level_fee_component("R" * 24, "LVL-1", "2026-27",
                                                            "Tuition Fee", 6000)
            self.assertEqual(updated_plan["total"], 6000.0)

            # HISTORICAL INTEGRITY CHECK:
            # Student A's issued Fees document is UNTOUCHED
            fees_1_after = fake.store["Fees"][fees_res_1["fees"]]
            self.assertEqual(float(fees_1_after.grand_total), 4500.0)
            self.assertEqual(int(fees_1_after.docstatus), 1)

            # New Student B enrolls under the updated policy
            fake.store.setdefault("Student", {})["STU-002"] = {
                "name": "STU-002", "student_name": "Student Beta"}
            fake.store.setdefault("Program Enrollment", {})["ENR-002"] = {
                "name": "ENR-002", "student": "STU-002", "program": native_prog,
                "academic_year": "2026-27", "docstatus": 1, "enrollment_date": "2026-09-01"}

            # Student B billed under new configuration
            fees_res_2 = finance.issue_tuition_fees("K" * 24, "ENR-002", updated_plan["fee_structure"],
                                                    "2026-09-02", "2026-09-30")
            fees_2 = fake.store["Fees"][fees_res_2["fees"]]
            self.assertEqual(float(fees_2.grand_total), 5400.0)  # 6000 - 10% scholarship = 5400

            # 10. REFUND VIA CORRECTION FRAMEWORK (OD-CP-2 Option B)
            corrections.configure_correction_policy("P" * 24, "Finance Manager", 30)
            corr_req = corrections.request_fees_correction(
                "C" * 24, fees_res_2["fees"], "Student withdrew within window", 5400.0)
            self.assertEqual(corr_req["status"], "Requested")

            # Approver approves fees correction
            approved = corrections.approve_fees_correction("A" * 24, corr_req["name"])
            self.assertEqual(approved["status"], "Posted")
            self.assertEqual(approved["refunded_total"], 5400.0)

            # Native Fees doc is cancelled (docstatus 2)
            self.assertEqual(int(fees_2.docstatus), 2)
            # Student A remains submitted and unchanged
            self.assertEqual(int(fees_1.docstatus), 1)


def _foundation():
    """The real foundation rules (frappe-free; resolves in any context)."""
    from toefl_house.configuration import rules as foundation
    return foundation


class D1LifecycleTests(unittest.TestCase):
    """Lifecycle proof for the D1 assessment-policy reference structure.

    Drives the REAL D1 guarded commands against the in-memory backend:
    versionless creation (incomplete), version appends (configured),
    validation (validated/effective), staleness on new versions,
    historical resolution, retirement, and every fail-closed refusal —
    with the hash-chained audit behind each step.
    """

    def _setup(self, academic, fake):
        academic.create_program("SETUP-PROGRAM-0001", "GEN-ENG",
                                "General English", "")
        fake.store.setdefault("Grading Scale", {})["GS-1"] = {"name": "GS-1"}
        fake.store.setdefault("Assessment Plan", {})["AP-1"] = {"name": "AP-1"}
        return academic, fake

    def _events(self, fake):
        return [dict(target=doc.target, before_hash=doc.before_hash,
                     after_hash=doc.after_hash)
                for doc in fake.store.get(
                    "TH Configuration Audit Event", {}).values()]

    def _readiness(self, academic, fake, code):
        foundation = _foundation()
        policy = fake.store["TH Assessment Policy"][code]
        rows = [dict(row) for row in (policy.get("versions") or [])]
        evidence = [event for event in self._events(fake)
                    if event["target"] == policy.name]
        validations = [
            fake.store["TH Configuration Audit Event"][name]
            for name in fake.store.get("TH Configuration Audit Event", {})]
        validations = [{"after_hash": doc.after_hash} for doc in validations
                       if doc.target == policy.name
                       and doc.action == "validate_assessment_policy"]
        return foundation.compute_readiness(
            status=policy.status, versions=rows, validations=validations,
            today="2026-09-17", what="assessment policy"), rows, evidence

    def test_create_policy_is_versionless_and_incomplete(self):
        for academic, fake in _load_module({"Course Owner"}):
            self._setup(academic, fake)
            result = academic.create_assessment_policy(
                "D1-CREATE-KEY-0001", "GEN-ENG", "ASM-GEN",
                "General assessment", "")
            self.assertEqual(result["code"], "ASM-GEN")
            self.assertEqual(result["status"], "Active")
            self.assertEqual(result["version_count"], 0)
            self.assertEqual(result["governing_effective_from"], "")
            policy = fake.store["TH Assessment Policy"]["ASM-GEN"]
            self.assertEqual(policy.get("versions") or [], [])
            readiness, _rows, events = self._readiness(academic, fake, "ASM-GEN")
            self.assertEqual(readiness, "incomplete")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["before_hash"], "")
            foundation = _foundation()
            self.assertEqual(events[0]["after_hash"],
                             foundation.snapshot_digest([]))
            receipts = fake.store.get("TH Configuration Operation", {})
            self.assertEqual(len(receipts), 1)
            receipt = next(iter(receipts.values()))
            self.assertEqual(receipt.status, "Complete")
            self.assertEqual(receipt.kind, "create_assessment_policy")

    def test_replay_returns_the_recorded_result_and_conflicts_refuse(self):
        for academic, fake in _load_module({"Course Owner"}):
            self._setup(academic, fake)
            first = academic.create_assessment_policy(
                "D1-REPLAY-KEY-0001", "GEN-ENG", "ASM-GEN",
                "General assessment", "")
            replay = academic.create_assessment_policy(
                "D1-REPLAY-KEY-0001", "GEN-ENG", "ASM-GEN",
                "General assessment", "")
            self.assertEqual(replay, first)
            self.assertEqual(len(self._events(fake)), 1,
                             "a replay must not double-apply")
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.create_assessment_policy(
                    "D1-REPLAY-KEY-0001", "GEN-ENG", "ASM-GEN",
                    "A different title", "")
            self.assertIn("conflicts", str(ctx.exception))

    def test_non_owner_is_refused(self):
        for academic, fake in _load_module({"Academic Manager"}):
            with self.assertRaises(fake.PermissionError):
                academic.create_assessment_policy(
                    "D1-NONOWNER-KEY-01", "GEN-ENG", "ASM-GEN",
                    "General assessment", "")

    def test_unknown_operations_authority_is_not_a_backdoor(self):
        for academic, fake in _load_module({"Course Owner"}):
            from toefl_house.configuration import audit as configuration_audit
            with self.assertRaises(fake.PermissionError):
                configuration_audit.require_authority("operations")
            with self.assertRaises(fake.PermissionError):
                configuration_audit.require_authority("custody")
            with self.assertRaises(fake.PermissionError):
                configuration_audit.execute(
                    "invented_command", "D1-UNKNOWN-KIND-01", {}, lambda actor: None)

    def test_version_append_validate_and_staleness(self):
        for academic, fake in _load_module({"Course Owner"}):
            self._setup(academic, fake)
            academic.create_assessment_policy(
                "D1-LIFE-CREATE-0001", "GEN-ENG", "ASM-GEN",
                "General assessment", "")
            result = academic.set_assessment_policy_version(
                "D1-LIFE-VERSION-01", "ASM-GEN", "2026-01-01",
                "First structure", grading_scale="GS-1",
                assessment_plan="AP-1")
            self.assertEqual(result["version_count"], 1)
            self.assertEqual(result["governing_effective_from"], "2026-01-01")
            readiness, _rows, _events = self._readiness(
                academic, fake, "ASM-GEN")
            self.assertEqual(readiness, "configured")
            validated = academic.validate_assessment_policy(
                "D1-LIFE-VALIDATE-1", "ASM-GEN")
            self.assertEqual(validated["readiness"], "effective")
            readiness, _rows, _events = self._readiness(
                academic, fake, "ASM-GEN")
            self.assertEqual(readiness, "effective")
            # A new version stales the validation automatically.
            academic.set_assessment_policy_version(
                "D1-LIFE-VERSION-02", "ASM-GEN", "2027-01-01",
                "Second structure")
            readiness, rows, _events = self._readiness(
                academic, fake, "ASM-GEN")
            self.assertEqual(readiness, "configured")
            # The superseded row is closed, never rewritten.
            first = next(row for row in rows
                         if row["effective_from"] == "2026-01-01")
            self.assertEqual(first["superseded_on"], "2027-01-01")
            self.assertEqual(first["grading_scale"], "GS-1")
            # History resolves by date, forever.
            foundation = _foundation()
            governing_then = foundation.resolve_governing_strict(
                rows, "2026-06-01", what="assessment policy version")
            governing_later = foundation.resolve_governing_strict(
                rows, "2027-06-01", what="assessment policy version")
            self.assertEqual(governing_then["grading_scale"], "GS-1")
            self.assertIsNone(governing_later.get("grading_scale"))
            self.assertEqual(foundation.verify_chain(self._events(fake)), 4)

    def test_backdated_same_day_empty_reason_and_unknown_carrier_refuse(self):
        for academic, fake in _load_module({"Course Owner"}):
            self._setup(academic, fake)
            academic.create_assessment_policy(
                "D1-REFUSE-CREATE-01", "GEN-ENG", "ASM-GEN",
                "General assessment", "")
            academic.set_assessment_policy_version(
                "D1-REFUSE-VERSION1", "ASM-GEN", "2026-06-01",
                "First structure")
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.set_assessment_policy_version(
                    "D1-REFUSE-BACKDATE1", "ASM-GEN", "2026-01-01",
                    "Backdated attempt")
            self.assertIn("must start after the latest version",
                          str(ctx.exception))
            with self.assertRaises(fake.ValidationError):
                academic.set_assessment_policy_version(
                    "D1-REFUSE-SAMEDAY-1", "ASM-GEN", "2026-06-01",
                    "Same-day attempt")
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.set_assessment_policy_version(
                    "D1-REFUSE-NOREASON1", "ASM-GEN", "2027-01-01", "   ")
            self.assertIn("required", str(ctx.exception))
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.set_assessment_policy_version(
                    "D1-REFUSE-NOSCALE-1", "ASM-GEN", "2027-01-01",
                    "Unknown carrier", grading_scale="NO-SUCH-SCALE")
            self.assertIn("does not exist", str(ctx.exception))
            readiness, _rows, _events = self._readiness(
                academic, fake, "ASM-GEN")
            self.assertEqual(readiness, "configured")

    def test_retire_reactivate_and_validate_refusals(self):
        for academic, fake in _load_module({"Course Owner"}):
            self._setup(academic, fake)
            academic.create_assessment_policy(
                "D1-STATUS-CREATE-01", "GEN-ENG", "ASM-GEN",
                "General assessment", "")
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.validate_assessment_policy(
                    "D1-STATUS-VALID-001", "ASM-GEN")
            self.assertIn("no versions yet", str(ctx.exception))
            academic.set_assessment_policy_version(
                "D1-STATUS-VERSION1", "ASM-GEN", "2026-01-01",
                "First structure")
            academic.validate_assessment_policy(
                "D1-STATUS-VALID-002", "ASM-GEN")
            retired = academic.set_assessment_policy_status(
                "D1-STATUS-RETIRE-01", "ASM-GEN", "0")
            self.assertEqual(retired["status"], "Retired")
            readiness, _rows, _events = self._readiness(
                academic, fake, "ASM-GEN")
            self.assertEqual(readiness, "retired")
            with self.assertRaises(fake.ValidationError):
                academic.validate_assessment_policy(
                    "D1-STATUS-VALID-003", "ASM-GEN")
            with self.assertRaises(fake.ValidationError):
                academic.set_assessment_policy_version(
                    "D1-STATUS-VERSION2", "ASM-GEN", "2027-01-01",
                    "Attempt on retired policy")
            reactivated = academic.set_assessment_policy_status(
                "D1-STATUS-REACT-001", "ASM-GEN", "1")
            self.assertEqual(reactivated["status"], "Active")
            readiness, _rows, _events = self._readiness(
                academic, fake, "ASM-GEN")
            self.assertEqual(readiness, "effective")

    def test_retired_family_blocks_policy_changes(self):
        for academic, fake in _load_module({"Course Owner"}):
            self._setup(academic, fake)
            academic.create_assessment_policy(
                "D1-FAMILY-CREATE-01", "GEN-ENG", "ASM-GEN",
                "General assessment", "")
            academic.set_program_status("D1-FAMILY-RETIRE-1", "GEN-ENG", "0")
            with self.assertRaises(fake.ValidationError):
                academic.create_assessment_policy(
                    "D1-FAMILY-CREATE-02", "GEN-ENG", "ASM-GEN-2",
                    "Second policy", "")
            with self.assertRaises(fake.ValidationError):
                academic.set_assessment_policy_version(
                    "D1-FAMILY-VERSION1", "ASM-GEN", "2026-01-01",
                    "Attempt on retired family")
            with self.assertRaises(fake.ValidationError):
                academic.validate_assessment_policy(
                    "D1-FAMILY-VALID-001", "ASM-GEN")

    def test_unknown_policy_duplicate_code_and_carrier_repair(self):
        for academic, fake in _load_module({"Course Owner"}):
            self._setup(academic, fake)
            with self.assertRaises(fake.ValidationError):
                academic.set_assessment_policy_version(
                    "D1-UNKNOWN-POL-001", "NO-SUCH-POLICY", "2026-01-01",
                    "Attempt on unknown policy")
            academic.create_assessment_policy(
                "D1-DUP-CREATE-00001", "GEN-ENG", "ASM-GEN",
                "General assessment", "")
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.create_assessment_policy(
                    "D1-DUP-CREATE-00002", "GEN-ENG", "ASM-GEN",
                    "Duplicate code", "")
            self.assertIn("already exists", str(ctx.exception))
            academic.set_assessment_policy_version(
                "D1-REPAIR-VERSION-01", "ASM-GEN", "2026-01-01",
                "First structure", grading_scale="GS-1")
            del fake.store["Grading Scale"]["GS-1"]
            with self.assertRaises(fake.ValidationError) as ctx:
                academic.validate_assessment_policy(
                    "D1-REPAIR-VALID-001", "ASM-GEN")
            self.assertIn("no longer exists", str(ctx.exception))


class CommandOnlyBoundaryTests(unittest.TestCase):
    """Native writes refuse; guarded commands pass (the A1 boundary).

    Loads the REAL controllers against the stub backend and runs the
    fake's insert/save through them — mirroring real frappe, where the
    controller validate fires on every write path, including the
    ignore_permissions writes the commands themselves make.
    """

    CONTROLLERS = {
        "TH Assessment Policy":
            APP / "academic/doctype/th_assessment_policy/th_assessment_policy.py",
        "TH Configuration Operation":
            APP / "operations/doctype/th_configuration_operation/th_configuration_operation.py",
        "TH Configuration Audit Event":
            APP / "operations/doctype/th_configuration_audit_event/th_configuration_audit_event.py",
    }

    def _controllers(self):
        """Import the real controllers against the CURRENT stub frappe.

        Yields {doctype: module}; restores sys.modules afterwards so no
        stub-bound controller leaks into other tests. Must run inside a
        _load_module loop, since the stub backend is per-test.
        """
        import importlib.util
        stub = sys.modules["frappe"]
        if not hasattr(stub, "_"):
            stub._ = lambda message: message
        if not hasattr(stub, "throw"):
            def _throw(message, exc=None):
                raise stub.ValidationError(message)
            stub.throw = _throw
        added = []
        try:
            model = types.ModuleType("frappe.model")
            model.__path__ = []
            document = types.ModuleType("frappe.model.document")
            document.Document = object
            for key, module in (("frappe.model", model),
                                ("frappe.model.document", document)):
                if key not in sys.modules:
                    sys.modules[key] = module
                    added.append(key)
            loaded = {}
            for index, (doctype, path) in enumerate(
                    self.CONTROLLERS.items()):
                name = f"boundary_controller_{index}"
                spec = importlib.util.spec_from_file_location(name, path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                added.append(name)
                spec.loader.exec_module(module)
                loaded[doctype] = module
            yield loaded
        finally:
            for key in added:
                sys.modules.pop(key, None)

    def _hooked_writes(self, loaded):
        """Run the fake's insert/save through the real controller guards."""
        original_insert, original_save = _Doc.insert, _Doc.save

        def _checked(doc):
            controller = loaded.get(doc.doctype)
            if controller is not None:
                if "get_doc_before_save" not in doc.__dict__:
                    object.__setattr__(
                        doc, "get_doc_before_save", lambda: None)
                controller.validate(doc)

        def insert(doc_self, ignore_permissions=False):
            _checked(doc_self)
            return original_insert(
                doc_self, ignore_permissions=ignore_permissions)

        def save(doc_self, ignore_permissions=False):
            _checked(doc_self)
            return original_save(
                doc_self, ignore_permissions=ignore_permissions)

        _Doc.insert, _Doc.save = insert, save
        try:
            yield
        finally:
            _Doc.insert, _Doc.save = original_insert, original_save

    def test_execute_establishes_the_command_context(self):
        for academic, fake in _load_module({"Course Owner"}):
            from toefl_house.configuration import audit as configuration_audit
            from toefl_house.configuration import rules as foundation
            seen = []

            def work(actor):
                seen.append(foundation.active_command())
                return {"ok": True}, {"target": "BOUNDARY-PROBE",
                                     "before_hash": "",
                                     "after_hash": "probe-hash"}

            result = configuration_audit.execute(
                "create_assessment_policy", "BOUNDARY-CONTEXT-01",
                {"probe": True}, work)
            self.assertEqual(result, {"ok": True})
            self.assertEqual(seen, ["create_assessment_policy"])
            self.assertIsNone(
                foundation.active_command(),
                "the context must not leak past the command")

    def test_guarded_commands_pass_and_native_writes_refuse(self):
        for academic, fake in _load_module({"Course Owner"}):
            academic.create_program("SETUP-PROGRAM-0001", "GEN-ENG",
                                    "General English", "")
            fake.store.setdefault("Grading Scale", {})["GS-1"] = {
                "name": "GS-1"}
            for loaded in self._controllers():
                for _hooked in self._hooked_writes(loaded):
                    academic.create_assessment_policy(
                        "BOUNDARY-CREATE-01", "GEN-ENG", "ASM-GEN",
                        "General assessment", "")
                    academic.set_assessment_policy_version(
                        "BOUNDARY-VERSION-01", "ASM-GEN", "2026-01-01",
                        "First structure", grading_scale="GS-1")
                    policy = fake.store["TH Assessment Policy"]["ASM-GEN"]
                    self.assertEqual(len(policy.get("versions")), 1)
                    self.assertEqual(len(fake.store.get(
                        "TH Configuration Audit Event", {})), 2)
                    # THE A1 SHAPE: a rules-valid native version append —
                    # sound date, known carrier, real reason — must
                    # refuse in business language instead of landing
                    # ledger-silent, with or without ignore_permissions.
                    saved = list(policy.get("versions"))
                    for kwargs in ({}, {"ignore_permissions": True}):
                        policy.append("versions", {
                            "effective_from": "2027-01-01",
                            "grading_scale": "GS-1",
                            "reason": "Native edit",
                            "set_by": "owner@example.com"})
                        with self.assertRaises(
                                fake.PermissionError, msg=repr(kwargs)) as ctx:
                            policy.save(**kwargs)
                        self.assertIn("guided Course Owner actions",
                                      str(ctx.exception))
                        # A refused save writes nothing: restore the
                        # in-memory doc to its saved state.
                        policy.set("versions", saved)
                    # A forged receipt and a forged event refuse the same
                    # way, and the refusal lands before any persistence.
                    operations = len(fake.store.get(
                        "TH Configuration Operation", {}))
                    events = len(fake.store.get(
                        "TH Configuration Audit Event", {}))
                    receipt = fake.get_doc({
                        "doctype": "TH Configuration Operation",
                        "name": "FORGED", "kind": "create_assessment_policy",
                        "actor": "owner@example.com",
                        "input_hash": "x" * 64, "status": "Complete",
                        "result_json": "{}"})
                    with self.assertRaises(fake.PermissionError):
                        receipt.insert(ignore_permissions=True)
                    event = fake.get_doc({
                        "doctype": "TH Configuration Audit Event",
                        "actor": "owner@example.com", "operation": "FORGED",
                        "action": "forged", "target": "ASM-GEN",
                        "after_hash": "y"})
                    with self.assertRaises(fake.PermissionError):
                        event.insert(ignore_permissions=True)
                    self.assertEqual(len(fake.store.get(
                        "TH Configuration Operation", {})), operations)
                    self.assertEqual(len(fake.store.get(
                        "TH Configuration Audit Event", {})), events)

    def test_data_rules_still_bind_inside_commands(self):
        for academic, fake in _load_module({"Course Owner"}):
            from toefl_house.configuration import rules as foundation
            for loaded in self._controllers():
                policy = fake.get_doc({
                    "doctype": "TH Assessment Policy", "code": "ASM-X",
                    "title": "No family", "family": "",
                    "status": "Active"})
                # Authorization first: the same invalid doc meets the
                # refusal outside a command, its data error inside one.
                with self.assertRaises(fake.PermissionError):
                    loaded["TH Assessment Policy"].validate(policy)
                with foundation.command_context("create_assessment_policy"):
                    with self.assertRaises(
                            fake.ValidationError) as ctx:
                        loaded["TH Assessment Policy"].validate(policy)
                self.assertIn("program family", str(ctx.exception))
                reasonless = fake.get_doc({
                    "doctype": "TH Assessment Policy", "code": "ASM-X",
                    "title": "No reason", "family": "GEN-ENG",
                    "status": "Active", "versions": [
                        {"effective_from": "2026-01-01", "reason": ""}]})
                with self.assertRaises(fake.PermissionError):
                    loaded["TH Assessment Policy"].validate(reasonless)
                with foundation.command_context(
                        "set_assessment_policy_version"):
                    with self.assertRaises(ValueError) as ctx:
                        loaded["TH Assessment Policy"].validate(reasonless)
                self.assertIn("Version reason is required",
                              str(ctx.exception))
                receipt = fake.get_doc({
                    "doctype": "TH Configuration Operation",
                    "status": "Forged"})
                with self.assertRaises(fake.PermissionError):
                    loaded["TH Configuration Operation"].validate(receipt)
                with foundation.command_context("create_assessment_policy"):
                    with self.assertRaises(
                            fake.ValidationError):
                        loaded["TH Configuration Operation"].validate(receipt)
                event = fake.get_doc({
                    "doctype": "TH Configuration Audit Event",
                    "actor": "owner@example.com", "operation": "OP-1",
                    "action": "create_assessment_policy",
                    "after_hash": "y"})
                object.__setattr__(
                    event, "get_doc_before_save", lambda: None)
                with self.assertRaises(fake.PermissionError):
                    loaded["TH Configuration Audit Event"].validate(event)
                with foundation.command_context("create_assessment_policy"):
                    with self.assertRaises(
                            fake.ValidationError) as ctx:
                        loaded["TH Configuration Audit Event"].validate(
                            event)
                self.assertIn("target", str(ctx.exception))


def rules_governing(versions, on_date):
    """Resolve through the real pure rules (imported fresh, no frappe needed)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "academic_rules", APP / "academic/rules.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve_duration(versions, on_date)


if __name__ == "__main__":
    unittest.main()

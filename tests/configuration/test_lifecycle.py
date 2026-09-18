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
        for key, value in payload.items():
            if isinstance(value, list):
                self._payload[key] = [_Row(row) for row in value]
        self.name = None

    def __getattr__(self, key):
        try:
            return self.__dict__["_payload"][key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key, value):
        if key in ("_backend", "doctype", "_payload", "name"):
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
        key = (self._payload.get("code") or self._payload.get("program_name")
               or self._payload.get("academic_year_name")
               or self._payload.get("category_name"))
        if not key:
            key = "EDU-FST-" + str(len(store) + 1).zfill(5)
        self.name = key
        self._payload["name"] = key
        store[key] = self
        return self

    def save(self, ignore_permissions=False):
        return self


class _FakeFrappe:
    def __init__(self, roles, enrollments=()):
        self.session = types.SimpleNamespace(user="owner@example.com")
        self.store = {}
        self._roles = set(roles)
        for index, row in enumerate(enrollments):
            self.store.setdefault("Program Enrollment", {})[f"ENR-{index}"] = dict(row)
        self.PermissionError = type("PermissionError", (Exception,), {})
        self.ValidationError = type("ValidationError", (Exception,), {})
        utils = types.ModuleType("frappe.utils")
        utils.today = lambda: "2026-09-17"
        utils.now_datetime = lambda: datetime(2026, 9, 17, 12, 0, 0)
        self.utils = utils

    def get_roles(self, user):
        return self._roles if user == self.session.user else set()

    def get_value(self, doctype, filters, fieldname):
        store = self.store.get(doctype, {})
        if isinstance(filters, str):
            record = store.get(filters)
        else:
            record = next((doc for doc in store.values()
                           if all(doc.get(k) == v for k, v in dict(filters).items())), None)
        if record is None:
            return None
        if isinstance(fieldname, str):
            return record.get(fieldname)
        return [record.get(field) for field in fieldname]

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
        return matched

    def get_doc(self, doctype, name=None, for_update=False):
        if isinstance(doctype, dict):
            payload = dict(doctype)
            return _Doc(self, payload.pop("doctype"), payload)
        if name is None:
            return _Doc(self, doctype, {"doctype": doctype})
        return self.store.get(doctype, {})[name]


def _load_module(roles, enrollments=()):
    fake = _FakeFrappe(roles, enrollments)
    previous = {key: sys.modules.get(key)
                for key in ("frappe", "frappe.utils", "toefl_house", "toefl_house.policy",
                            "toefl_house.academic", "toefl_house.academic.rules")}
    stub = types.ModuleType("frappe")
    for attr in ("session", "PermissionError", "ValidationError", "utils",
                 "get_roles", "get_value", "exists", "count", "get_all", "get_doc"):
        setattr(stub, attr, getattr(fake, attr))
    stub.whitelist = lambda **kwargs: (lambda func: func)
    stub.db = types.SimpleNamespace(
        get_value=fake.get_value, exists=fake.exists,
        count=fake.count, get_all=fake.get_all)
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

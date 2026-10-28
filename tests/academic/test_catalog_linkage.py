"""S12 regression: the catalog linkage mechanism (OD-NEW-09).

The house holds exactly one catalog linkage policy; versions carry
the effective-dated owner choice of enforcement — ``advisory`` leaves
intake unjudged, ``enforcing`` refuses new enrollments into retired
levels' programs. Reads fail closed (no row / retired / no effective
version all resolve to {}); native programs no level maps stay allowed
under both; commands route through the receipted Course Owner gate
under their own kind. Loads the REAL academic catalog-linkage module
with the REAL academic + configuration rules against a scripted frappe
stub; hosted CI proves the linkage journey.
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
    "create_catalog_linkage_policy",
    "set_catalog_linkage_version",
    "set_catalog_linkage_status",
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
    test.levels = {}
    previous = dict(sys.modules)
    test.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
    fake = test

    def get_all(doctype, fields=None, filters=None, limit=None, **kwargs):
        assert doctype == "TH Catalog Linkage Policy"
        rows = list(fake.policy_rows)
        if limit is not None:
            rows = rows[:limit]
        return rows

    def get_value(doctype, name_or_filters, fieldname=None, **kwargs):
        if doctype == "TH Catalog Linkage Policy":
            assert fake.policy_doc is not None
            return fake.policy_doc.name
        if doctype == "TH Program Level":
            program = (name_or_filters or {}).get("native_program")
            return fake.levels.get(program)
        raise AssertionError(f"unexpected get_value {doctype}")

    def get_doc(doctype, name=None, for_update=False, **kwargs):
        if isinstance(doctype, dict):
            payload = dict(doctype)
            doc = _PolicyDoc(name=payload.get("code"), **payload)
            fake.policy_doc = doc
            return doc
        assert doctype == "TH Catalog Linkage Policy"
        assert fake.policy_doc is not None
        return fake.policy_doc

    def exists(doctype, name):
        if doctype == "TH Catalog Linkage Policy":
            return False
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
    test.linkage = _load_real(
        "toefl_house.academic.catalog_linkage",
        APP / "academic/catalog_linkage.py")


class CatalogLinkagePolicyTests(unittest.TestCase):
    def setUp(self):
        _install_command_harness(self)

    def _existing_policy(self, status="Active", versions=()):
        self.policy_rows = [{"name": "LINK-POL"}]
        self.policy_doc = _PolicyDoc(name="LINK-POL", code="LINK-POL",
                                     title="Linkage rule", status=status,
                                     versions=[_Row(v) for v in versions])
        return self.policy_doc

    def _version(self, key, date, enforcement="enforcing"):
        return self.linkage.set_catalog_linkage_version(
            key, "LINK-POL", date,
            "Owner opens catalog linkage", enforcement)

    def test_create_shell_carries_no_versions(self):
        result = self.linkage.create_catalog_linkage_policy(
            "test-key-linkpol-create01", "LINK-POL", "Linkage rule")
        self.assertEqual(result["code"], "LINK-POL")
        self.assertEqual(result["status"], "Active")
        self.assertEqual(result["version_count"], 0)
        self.assertEqual(result["governing_enforcement"], "")
        kind, _key, _payload = self.execute_calls[0]
        self.assertEqual(kind, "create_catalog_linkage_policy")

    def test_second_policy_is_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self.linkage.create_catalog_linkage_policy(
                "test-key-linkpol-create02", "LINK-TWO", "Second rule")
        self.assertIn("version it instead", str(ctx.exception))

    def test_version_append_governs_from_its_date(self):
        self._existing_policy()
        result = self._version("test-key-linkpol-versn01", "2026-09-23")
        self.assertEqual(result["version_count"], 1)
        # Not yet effective today: the shell still governs nothing.
        self.assertEqual(result["governing_enforcement"], "")
        self.assertEqual(self.linkage.governing_linkage_terms(), {})
        self.today = "2026-09-23"
        self.assertEqual(self.linkage.governing_linkage_terms(), {
            "effective_from": "2026-09-23", "enforcement": "enforcing"})

    def test_bad_enforcement_is_refused(self):
        self._existing_policy()
        for enforcement in ("off", "ENFORCING", "enforcing ", "", None):
            with self.assertRaises(_ValidationError):
                self._version("test-key-linkpol-versn02", "2026-09-23",
                              enforcement=enforcement)

    def test_backdated_and_same_day_versions_refused(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-23", "enforcement": "enforcing",
            "reason": "Owner opens catalog linkage",
            "set_by": ACTOR, "set_on": "2026-09-22 12:00:00"}])
        with self.assertRaises(_ValidationError):
            self._version("test-key-linkpol-versn03", "2026-09-20")
        with self.assertRaises(_ValidationError):
            self._version("test-key-linkpol-versn04", "2026-09-23")

    def test_superseded_version_is_closed_not_rewritten(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-23", "enforcement": "enforcing",
            "reason": "Owner opens catalog linkage",
            "set_by": ACTOR, "set_on": "2026-09-22 12:00:00"}])
        self._version("test-key-linkpol-versn05", "2026-10-01",
                      enforcement="advisory")
        first, second = self.policy_doc.versions
        self.assertEqual(first["enforcement"], "enforcing")
        self.assertEqual(first["superseded_on"], "2026-10-01")
        self.assertEqual(second["enforcement"], "advisory")
        self.assertNotIn("superseded_on", second)

    def test_retire_is_the_off_switch(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-20", "enforcement": "enforcing",
            "reason": "Owner opens catalog linkage",
            "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}])
        self.assertEqual(
            self.linkage.governing_linkage_terms()["enforcement"],
            "enforcing")
        result = self.linkage.set_catalog_linkage_status(
            "test-key-linkpol-status1", "LINK-POL", 0)
        self.assertEqual(result["status"], "Retired")
        self.assertEqual(self.linkage.governing_linkage_terms(), {})
        self.linkage.set_catalog_linkage_status(
            "test-key-linkpol-status2", "LINK-POL", 1)
        self.assertEqual(
            self.linkage.governing_linkage_terms()["enforcement"],
            "enforcing")

    def test_governing_read_fails_closed_without_policy_or_version(self):
        self.assertEqual(self.linkage.governing_linkage_terms(), {})
        self._existing_policy()
        self.assertEqual(self.linkage.governing_linkage_terms(), {})


class CatalogLinkageGateTests(unittest.TestCase):
    def setUp(self):
        _install_command_harness(self)
        self._existing_policy()

    def _existing_policy(self, enforcement="enforcing"):
        self.policy_rows = [{"name": "LINK-POL"}]
        self.policy_doc = _PolicyDoc(
            name="LINK-POL", code="LINK-POL", title="Linkage rule",
            status="Active", versions=[_Row({
                "effective_from": "2026-09-20", "enforcement": enforcement,
                "reason": "Owner opens catalog linkage",
                "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"})])

    def _level(self, code, status):
        from types import SimpleNamespace
        return SimpleNamespace(code=code, status=status)

    def test_enforcing_refuses_retired_levels_only(self):
        self.levels = {"PROG-OLD": self._level("LVL-OLD", "Retired"),
                       "PROG-NEW": self._level("LVL-NEW", "Active")}
        check = self.linkage.check_intake_open
        with self.assertRaises(ValueError) as ctx:
            check("PROG-OLD")
        self.assertIn("LVL-OLD", str(ctx.exception))
        self.assertIn("retired", str(ctx.exception))
        check("PROG-NEW")

    def test_unmapped_programs_stay_allowed_when_enforcing(self):
        self.levels = {}
        self.linkage.check_intake_open("PROG-NATIVE-ONLY")

    def test_advisory_judges_nothing(self):
        self._existing_policy(enforcement="advisory")
        self.levels = {"PROG-OLD": self._level("LVL-OLD", "Retired")}
        self.linkage.check_intake_open("PROG-OLD")
        self.linkage.check_intake_open("PROG-NATIVE-ONLY")

    def test_gate_fails_closed_without_governing_terms(self):
        self.policy_rows = []
        self.policy_doc = None
        with self.assertRaises(ValueError) as ctx:
            self.linkage.check_intake_open("PROG-NEW")
        self.assertIn("No active catalog linkage policy", str(ctx.exception))

    def test_enforcement_vocabulary(self):
        validate = self.linkage.validate_enforcement
        self.assertEqual(validate("advisory"), "advisory")
        self.assertEqual(validate("enforcing"), "enforcing")
        for bad in ("off", "ENFORCING", "enforcing ", "", None):
            with self.assertRaises(ValueError):
                validate(bad)


class CatalogLinkageCommandGateTests(unittest.TestCase):
    """Source-level receipt-gate parity with the S5/S7/S8 policy commands."""

    def test_commands_route_through_the_receipted_gate(self):
        source = (APP / "academic/catalog_linkage.py").read_text(encoding="utf-8")
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

    def test_enrollment_judges_the_catalog_before_locking(self):
        source = (APP / "enrollment/__init__.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "enroll_in_program")
        code = ast.unparse(fn)
        self.assertIn("check_intake_open", code,
                      "enroll_in_program must judge the catalog linkage")
        self.assertLess(code.index("check_intake_open"),
                        code.index("_existing_enrollment"),
                        "the linkage refusal must precede the duplicate lock")


class CatalogLinkageControllerTests(unittest.TestCase):
    """The policy CONTROLLER validates real child Documents, not dicts.

    The command-layer tests above run against dict doubles, which are
    subscriptable — so they could not see a row["field"] TypeError of
    the kind the S9 hosted qualification caught on the first
    second-version append. These tests run the REAL controller
    validate against faithful non-subscriptable rows.
    """

    CONTROLLER = APP / ("academic/doctype/th_catalog_linkage_policy/"
                        "th_catalog_linkage_policy.py")

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
            "toefl_house.academic.doctype.th_catalog_linkage_policy.th_catalog_linkage_policy",
            self.CONTROLLER)
        self.foundation = sys.modules["toefl_house.configuration.rules"]

    def _doc(self, versions):
        return _PolicyDoc(
            name="LINK-POL", code="LINK-POL", title="Linkage rule",
            status="Active", versions=[_DocRow(**version) for version in versions])

    def _version(self, effective, superseded=None, enforcement="enforcing"):
        row = {"effective_from": effective, "enforcement": enforcement,
               "reason": "Owner opens catalog linkage",
               "set_by": ACTOR, "set_on": "2026-09-22 12:00:00"}
        if superseded is not None:
            row["superseded_on"] = superseded
        return row

    def test_superseded_row_validates_without_subscript(self):
        doc = self._doc([self._version("2026-09-20", superseded="2026-09-23"),
                         self._version("2026-09-23")])
        with self.foundation.command_context("set_catalog_linkage_version"):
            self.controller.validate(doc)

    def test_closed_date_before_effective_is_still_refused(self):
        doc = self._doc([self._version("2026-09-23", superseded="2026-09-20")])
        with self.foundation.command_context("set_catalog_linkage_version"):
            with self.assertRaises(_ValidationError) as ctx:
                self.controller.validate(doc)
        self.assertIn("must fall after its effective date", str(ctx.exception))

    def test_bad_enforcement_in_a_row_is_refused(self):
        doc = self._doc([self._version("2026-09-23", enforcement="off")])
        with self.foundation.command_context("set_catalog_linkage_version"):
            with self.assertRaises(ValueError):
                self.controller.validate(doc)

    def test_validate_outside_a_command_is_refused_first(self):
        doc = self._doc([self._version("2026-09-23")])
        with self.assertRaises(_PermissionError):
            self.controller.validate(doc)


class CatalogLinkageControllerRowAccessTests(unittest.TestCase):
    """The linkage controller reads child rows without subscripts."""

    def test_version_checks_read_rows_without_subscripts(self):
        path = CatalogLinkageControllerTests.CONTROLLER
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

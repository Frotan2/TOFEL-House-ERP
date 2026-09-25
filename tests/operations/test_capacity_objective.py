"""TH Capacity Objective mechanism (decision classification track 3, 2026-09-25).

Category B of the standing rule: the numeric capacity/availability
objectives (O-D8N: concurrency profile, data scale, workload mix,
availability objective) are owner numbers, never engineering constants.
The carrier holds exactly one objective; versions carry the effective-
dated owner choice of the four numbers.
Reads fail closed (no row / retired / no effective version all resolve to
{}); commands route through the receipted Course Owner gate under their
own kinds. Loads the REAL operations capacity_objective module, the REAL parent
controller and the REAL academic + configuration rules against a
scripted frappe stub; hosted CI proves the journey. A static guard also
pins the observability module to zero delivery primitives.
"""
import ast
import importlib.util
import json
import re
import sys
import types
import unittest
from types import SimpleNamespace
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "apps/toefl_house/toefl_house"
MODULE = APP / "operations/capacity_objective.py"
CONTROLLER = APP / ("operations/doctype/th_capacity_objective/"
                    "th_capacity_objective.py")
POLICY_JSON = APP / ("operations/doctype/th_capacity_objective/"
                     "th_capacity_objective.json")
VERSION_JSON = APP / ("operations/doctype/th_capacity_objective_version/"
                      "th_capacity_objective_version.json")
D8_VALIDATOR = REPO / "tools/foundation/d8_validate.py"
ACTOR = "course.owner@example.com"
POLICY = "TH Capacity Objective"
COMMANDS = (
    "create_capacity_objective",
    "set_capacity_objective_version",
    "set_capacity_objective_status",
    "validate_capacity_objective",
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


class _DocRow:
    """A faithful real-Frappe child row: attribute access plus .get().

    Real child Documents are NOT subscriptable — row["field"] raises
    TypeError on hosted Frappe. Owned controller code must read rows via
    row.get(...), never row[...].
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


def _throw(message):
    raise _ValidationError(message)


def _install_command_harness(test):
    """Install the stub frappe plus REAL rules/command modules on test."""
    test.policy_rows = []
    test.policy_doc = None
    test.execute_calls = []
    test.today = "2026-09-25"
    previous = dict(sys.modules)
    test.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
    fake = test

    def get_all(doctype, fields=None, filters=None, limit=None, **kwargs):
        assert doctype == POLICY
        return list(fake.policy_rows)

    def get_value(doctype, name_or_filters, fieldname=None, **kwargs):
        if doctype == POLICY:
            assert fake.policy_doc is not None
            return fake.policy_doc.name
        raise AssertionError(f"unexpected get_value {doctype}")

    def get_doc(doctype, name=None, for_update=False, **kwargs):
        if isinstance(doctype, dict):
            payload = dict(doctype)
            doc = _PolicyDoc(name=payload.get("code"), **payload)
            fake.policy_doc = doc
            return doc
        assert doctype == POLICY
        assert fake.policy_doc is not None
        return fake.policy_doc

    def exists(doctype, name):
        if doctype == POLICY:
            return False
        raise AssertionError(f"unexpected exists {doctype}")

    stub = types.ModuleType("frappe")
    stub.PermissionError = _PermissionError
    stub.ValidationError = _ValidationError
    stub.whitelist = lambda **kwargs: (lambda func: func)
    stub.throw = _throw
    stub._ = lambda message: message
    stub.utils = SimpleNamespace(
        today=lambda: fake.today,
        now_datetime=lambda: "2026-09-25 12:00:00")
    stub.db = SimpleNamespace(get_all=get_all, get_value=get_value,
                              exists=exists)
    stub.get_doc = get_doc
    model = types.ModuleType("frappe.model")
    document = types.ModuleType("frappe.model.document")
    document.Document = type("Document", (), {})
    model.document = document
    stub.model = model
    sys.modules["frappe"] = stub
    sys.modules["frappe.utils"] = stub.utils
    sys.modules["frappe.model"] = model
    sys.modules["frappe.model.document"] = document

    package = types.ModuleType("toefl_house")
    package.__path__ = [str(APP)]
    sys.modules["toefl_house"] = package
    academic_pkg = types.ModuleType("toefl_house.academic")
    academic_pkg.__path__ = [str(APP / "academic")]
    sys.modules["toefl_house.academic"] = academic_pkg
    config_pkg = types.ModuleType("toefl_house.configuration")
    config_pkg.__path__ = [str(APP / "configuration")]
    sys.modules["toefl_house.configuration"] = config_pkg
    operations_pkg = types.ModuleType("toefl_house.operations")
    operations_pkg.__path__ = [str(APP / "operations")]
    sys.modules["toefl_house.operations"] = operations_pkg
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

    test.capacity_objective = _load_real("toefl_house.operations.capacity_objective", MODULE)
    test.controller = _load_real(
        "toefl_house.operations.doctype.th_capacity_objective."
        "th_capacity_objective", CONTROLLER)
    test.foundation = sys.modules["toefl_house.configuration.rules"]


class CapacityObjectivePolicyTests(unittest.TestCase):
    def setUp(self):
        _install_command_harness(self)

    def _existing_policy(self, status="Active", versions=()):
        self.policy_rows = [{"name": "CAP-OBJ"}]
        self.policy_doc = _PolicyDoc(name="CAP-OBJ", code="CAP-OBJ",
                                     title="Objective shell", status=status,
                                     versions=[_Row(v) for v in versions])
        return self.policy_doc

    def _version(self, key, date, users=40, documents=50000, share=70,
                 availability=99.5):
        return self.capacity_objective.set_capacity_objective_version(
            key, "CAP-OBJ", date,
            "Owner sets the capacity objective",
            users, documents, share, availability)

    # --- guarded commands --------------------------------------------
    def test_create_shell_carries_no_versions(self):
        result = self.capacity_objective.create_capacity_objective(
            "test-key-capobj-create01", "CAP-OBJ", "Objective shell")
        self.assertEqual(result["code"], "CAP-OBJ")
        self.assertEqual(result["status"], "Active")
        self.assertEqual(result["version_count"], 0)
        self.assertEqual(result["governing_concurrent_users_target"], "")
        kind, _key, _payload = self.execute_calls[0]
        self.assertEqual(kind, "create_capacity_objective")

    def test_second_policy_is_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self.capacity_objective.create_capacity_objective(
                "test-key-capobj-create02", "CAP-OBJ-2", "Second shell")
        self.assertIn("version it instead", str(ctx.exception))

    def test_version_append_governs_from_its_date(self):
        self._existing_policy()
        result = self._version("test-key-capobj-versn01", "2026-09-28")
        self.assertEqual(result["version_count"], 1)
        # Not yet effective today: the shell still governs nothing.
        self.assertEqual(result["governing_concurrent_users_target"], "")
        self.assertEqual(self.capacity_objective.governing_capacity_objective(), {})
        self.today = "2026-09-28"
        terms = self.capacity_objective.governing_capacity_objective()
        self.assertEqual(terms["effective_from"], "2026-09-28")
        self.assertEqual(terms["concurrent_users_target"], 40)
        self.assertEqual(terms["document_scale_target"], 50000)
        self.assertEqual(terms["read_share_percent"], 70)
        self.assertEqual(terms["availability_target_percent"], 99.5)

    def test_users_and_documents_are_bounded(self):
        self._existing_policy()
        for bad in (None, 0, -3, 100001, True, "many"):
            with self.subTest(bad=bad):
                with self.assertRaises(_ValidationError) as ctx:
                    self._version("test-key-capobj-versn02", "2026-09-28",
                                  users=bad)
                self.assertIn("Concurrent users target must be a whole "
                              "number", str(ctx.exception))
        for bad in (None, 0, 1000000001, True, "huge"):
            with self.subTest(bad=bad):
                with self.assertRaises(_ValidationError) as ctx:
                    self._version("test-key-capobj-versn03", "2026-09-28",
                                  documents=bad)
                self.assertIn("Document scale target must be a whole "
                              "number", str(ctx.exception))

    def test_read_share_is_a_percent(self):
        self._existing_policy()
        for bad in (-1, 101, True, "most"):
            with self.subTest(bad=bad):
                with self.assertRaises(_ValidationError) as ctx:
                    self._version("test-key-capobj-versn04", "2026-09-28",
                                  share=bad)
                self.assertIn("Read share percent must be a whole number",
                              str(ctx.exception))

    def test_availability_is_a_positive_percent(self):
        self._existing_policy()
        for bad in (0, -10, 100.01, "high", None):
            with self.subTest(bad=bad):
                with self.assertRaises(_ValidationError) as ctx:
                    self._version("test-key-capobj-versn05", "2026-09-28",
                                  availability=bad)
                self.assertIn("Availability target percent must be a "
                              "number", str(ctx.exception))

    def test_numeric_strings_are_coerced_not_assumed(self):
        self._existing_policy()
        result = self._version("test-key-capobj-versn06", "2026-09-28",
                               users="40", documents="50000", share="70",
                               availability="99.5")
        self.assertEqual(result["version_count"], 1)
        row = self.policy_doc.versions[0]
        self.assertEqual(row["concurrent_users_target"], 40)
        self.assertEqual(row["document_scale_target"], 50000)
        self.assertEqual(row["read_share_percent"], 70)
        self.assertEqual(row["availability_target_percent"], 99.5)

    def test_backdated_and_same_day_versions_refused(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-28", "concurrent_users_target": 40,
            "document_scale_target": 50000, "read_share_percent": 70,
            "availability_target_percent": 99.5,
            "reason": "Owner sets the capacity objective",
            "set_by": ACTOR, "set_on": "2026-09-25 12:00:00"}])
        with self.assertRaises(_ValidationError):
            self._version("test-key-capobj-versn09", "2026-09-20")
        with self.assertRaises(_ValidationError):
            self._version("test-key-capobj-versn10", "2026-09-28")

    def test_superseded_version_is_closed_not_rewritten(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-28", "concurrent_users_target": 40,
            "document_scale_target": 50000, "read_share_percent": 70,
            "availability_target_percent": 99.5,
            "reason": "Owner sets the capacity objective",
            "set_by": ACTOR, "set_on": "2026-09-25 12:00:00"}])
        self._version("test-key-capobj-versn11", "2026-10-01",
                      users=60, documents=80000)
        first, second = self.policy_doc.versions
        self.assertEqual(first["concurrent_users_target"], 40)
        self.assertEqual(first["superseded_on"], "2026-10-01")
        self.assertEqual(second["concurrent_users_target"], 60)
        self.assertEqual(second["document_scale_target"], 80000)
        self.assertNotIn("superseded_on", second)

    def test_retire_is_the_off_switch(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-20", "concurrent_users_target": 40,
            "document_scale_target": 50000, "read_share_percent": 70,
            "availability_target_percent": 99.5,
            "reason": "Owner sets the capacity objective",
            "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}])
        self.assertEqual(
            self.capacity_objective.governing_capacity_objective()[
                "concurrent_users_target"],
            40)
        result = self.capacity_objective.set_capacity_objective_status(
            "test-key-capobj-status1", "CAP-OBJ", 0)
        self.assertEqual(result["status"], "Retired")
        self.assertEqual(self.capacity_objective.governing_capacity_objective(), {})
        self.capacity_objective.set_capacity_objective_status(
            "test-key-capobj-status2", "CAP-OBJ", 1)
        self.assertEqual(
            self.capacity_objective.governing_capacity_objective()[
                "document_scale_target"],
            50000)

    def test_governing_read_fails_closed_without_policy_or_version(self):
        self.assertEqual(self.capacity_objective.governing_capacity_objective(), {})
        self._existing_policy()
        self.assertEqual(self.capacity_objective.governing_capacity_objective(), {})

    # --- validate command --------------------------------------------
    def test_validate_requires_versions(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self.capacity_objective.validate_capacity_objective(
                "test-key-capobj-valid01", "CAP-OBJ")
        self.assertIn("no versions yet", str(ctx.exception))

    def test_validate_rechecks_every_stored_row(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-20", "concurrent_users_target": 0,
            "document_scale_target": 50000, "read_share_percent": 70,
            "availability_target_percent": 99.5,
            "reason": "Owner sets the capacity objective",
            "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}])
        with self.assertRaises(_ValidationError) as ctx:
            self.capacity_objective.validate_capacity_objective(
                "test-key-capobj-valid02", "CAP-OBJ")
        self.assertIn("Concurrent users target must be a whole number",
                      str(ctx.exception))
        self._existing_policy(versions=[{
            "effective_from": "2026-09-20", "concurrent_users_target": 40,
            "document_scale_target": 50000, "read_share_percent": 70,
            "availability_target_percent": None,
            "reason": "Owner sets the capacity objective",
            "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}])
        with self.assertRaises(_ValidationError) as ctx:
            self.capacity_objective.validate_capacity_objective(
                "test-key-capobj-valid03", "CAP-OBJ")
        self.assertIn("Availability target percent must be a number",
                      str(ctx.exception))

    def test_validate_snapshot_recovers_readiness(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-28", "concurrent_users_target": 40,
            "document_scale_target": 50000, "read_share_percent": 70,
            "availability_target_percent": 99.5,
            "reason": "Owner sets the capacity objective",
            "set_by": ACTOR, "set_on": "2026-09-25 12:00:00"}])
        result = self.capacity_objective.validate_capacity_objective(
            "test-key-capobj-valid04", "CAP-OBJ")
        # Latest version starts after today: validated, not yet effective.
        self.assertEqual(result["readiness"], "validated")
        kind, _key, _payload = self.execute_calls[-1]
        self.assertEqual(kind, "validate_capacity_objective")

    def test_all_four_commands_route_through_the_receipted_gate(self):
        self.capacity_objective.create_capacity_objective(
            "test-key-capobj-route01", "CAP-OBJ", "Objective shell")
        self.policy_rows = [{"name": "CAP-OBJ"}]
        self.policy_doc = _PolicyDoc(name="CAP-OBJ", code="CAP-OBJ",
                                     title="Objective shell", status="Active",
                                     versions=[])
        self.capacity_objective.set_capacity_objective_version(
            "test-key-capobj-route02", "CAP-OBJ", "2026-09-28",
            "Owner sets the capacity objective", 40, 50000, 70, 99.5)
        self.capacity_objective.set_capacity_objective_status(
            "test-key-capobj-route03", "CAP-OBJ", 0)
        self.capacity_objective.set_capacity_objective_status(
            "test-key-capobj-route04", "CAP-OBJ", 1)
        seen = [call[0] for call in self.execute_calls]
        self.assertEqual(seen, [
            "create_capacity_objective",
            "set_capacity_objective_version",
            "set_capacity_objective_status",
            "set_capacity_objective_status",
        ])

    # --- controller seam ----------------------------------------------
    def _doc(self, versions=()):
        return _PolicyDoc(code="CAP-OBJ", title="Objective shell",
                          status="Active", description="",
                          versions=[_DocRow(**v) for v in versions])

    def test_validate_outside_a_command_is_refused_first(self):
        with self.assertRaises(_PermissionError) as ctx:
            self.controller.validate(self._doc())
        self.assertIn("guarded Course Owner commands", str(ctx.exception))

    def test_inside_a_command_the_rules_bind(self):
        # A good document validates quietly inside a real command context.
        with self.foundation.command_context(
                "set_capacity_objective_version"):
            self.controller.validate(self._doc(versions=[{
                "effective_from": "2026-09-28",
                "concurrent_users_target": 40,
                "document_scale_target": 50000,
                "read_share_percent": 70,
                "availability_target_percent": 99.5,
                "reason": "Owner sets the capacity objective",
                "set_by": ACTOR, "set_on": "2026-09-25 12:00:00"}]))

    def test_two_versions_sharing_one_effective_date_refused(self):
        doc = self._doc(versions=[
            {"effective_from": "2026-09-28", "concurrent_users_target": 40,
             "document_scale_target": 50000, "read_share_percent": 70,
             "availability_target_percent": 99.5,
             "reason": "first version"},
            {"effective_from": "2026-09-28", "concurrent_users_target": 40,
             "document_scale_target": 50000, "read_share_percent": 70,
             "availability_target_percent": 99.5,
             "reason": "second version"}])
        with self.foundation.command_context("set_capacity_objective_version"):
            with self.assertRaises(_ValidationError) as ctx:
                self.controller.validate(doc)
        self.assertIn("cannot share one effective date", str(ctx.exception))

    def test_closed_date_before_effective_is_refused(self):
        doc = self._doc(versions=[{
            "effective_from": "2026-09-28", "concurrent_users_target": 40,
            "document_scale_target": 50000, "read_share_percent": 70,
            "availability_target_percent": 99.5,
            "reason": "a reason",
            "superseded_on": "2026-09-27"}])
        with self.foundation.command_context("set_capacity_objective_version"):
            with self.assertRaises(_ValidationError) as ctx:
                self.controller.validate(doc)
        self.assertIn("must fall after", str(ctx.exception))

    def test_row_reads_never_use_subscripts(self):
        # Real child rows are not subscriptable; owned code must not index them.
        for module in (MODULE, CONTROLLER):
            with self.subTest(module=module.name):
                bad = re.findall(r"\brow\[", module.read_text(encoding="utf-8"))
                self.assertEqual(bad, [])


class CapacityObjectiveWiringTests(unittest.TestCase):
    """The carrier's registries and doctype invariants, asserted statically."""

    @classmethod
    def setUpClass(cls):
        cls.policy_json = json.loads(POLICY_JSON.read_text(encoding="utf-8"))
        cls.version_json = json.loads(VERSION_JSON.read_text(encoding="utf-8"))
        namespace = {}
        exec(compile((APP / "hooks.py").read_text(encoding="utf-8"),
                     "hooks.py", "exec"), namespace)
        cls.hooks = namespace
        cls.module_source = MODULE.read_text(encoding="utf-8")
        cls.audit_source = (APP / "configuration/audit.py").read_text(
            encoding="utf-8")
        cls.permissions_source = (APP / "permissions.py").read_text(
            encoding="utf-8")
        cls.desk_init_source = (APP / "desk/__init__.py").read_text(
            encoding="utf-8")

    # --- doctype invariants (configuration-plane layer 2) --------------
    def test_policy_json_is_a_governance_carrier(self):
        doc = self.policy_json
        self.assertEqual(doc["module"], "Operations")
        self.assertEqual(doc["autoname"], "field:code")
        self.assertEqual(doc.get("track_changes"), 1)
        fields = {field["fieldname"]: field for field in doc["fields"]}
        code = fields["code"]
        self.assertEqual(code.get("unique"), 1)
        self.assertEqual(code.get("set_only_once"), 1)
        self.assertEqual(code.get("reqd"), 1)
        self.assertEqual(fields["status"].get("options"), "Active\nRetired")
        self.assertEqual(fields["versions"].get("options"),
                         "TH Capacity Objective Version")

    def test_no_delete_permission_anywhere(self):
        for doctype in (self.policy_json, self.version_json):
            for perm in doctype.get("permissions", []):
                self.assertNotIn("delete", perm,
                                 f"{doctype['name']} grants delete to "
                                 f"{perm.get('role')}")

    def test_course_owner_is_the_only_writer(self):
        writers = [perm["role"] for perm in self.policy_json["permissions"]
                   if perm.get("write")]
        self.assertEqual(writers, ["Course Owner"])

    def test_version_json_shape(self):
        doc = self.version_json
        self.assertEqual(doc.get("istable"), 1)
        self.assertEqual(doc.get("permissions"), [])
        fields = {field["fieldname"]: field for field in doc["fields"]}
        for name in ("concurrent_users_target", "document_scale_target",
                     "read_share_percent"):
            self.assertEqual(fields[name].get("fieldtype"), "Int", name)
            self.assertEqual(fields[name].get("reqd"), 1, name)
        availability = fields["availability_target_percent"]
        self.assertEqual(availability.get("fieldtype"), "Float")
        self.assertEqual(availability.get("reqd"), 1)
        # No owner number ships: no default is pinned on any value field.
        for name in ("concurrent_users_target", "document_scale_target",
                     "read_share_percent", "availability_target_percent",
                     "reason", "effective_from"):
            self.assertNotIn("default", fields[name],
                             f"{name} must not carry a default value")

    def test_policy_index_web_pages_matches_siblings(self):
        # Consistency with the existing configuration carriers.
        sibling = json.loads((APP / "teaching/doctype/"
                              "th_attendance_correction_policy/"
                              "th_attendance_correction_policy.json")
                             .read_text(encoding="utf-8"))
        for key in ("engine", "allow_rename", "naming_rule",
                    "index_web_pages_for_search", "row_format",
                    "sort_field", "sort_order", "track_changes"):
            self.assertEqual(self.policy_json.get(key), sibling.get(key), key)

    # --- registry wiring ------------------------------------------------
    def test_permission_hooks_are_wired(self):
        self.assertEqual(
            self.hooks["has_permission"].get(POLICY),
            "toefl_house.permissions.configuration_has_permission")
        self.assertEqual(
            self.hooks["permission_query_conditions"].get(POLICY),
            "toefl_house.permissions.configuration_query")
        events = self.hooks["doc_events"].get(POLICY)
        self.assertIsNotNone(events, "doc_events missing the carrier")
        validate_path = events.get("validate", "")
        self.assertIn(
            "operations.doctype.th_capacity_objective."
            "th_capacity_objective.validate", validate_path)
        module_path = validate_path.rsplit(".", 1)[0]
        relative = module_path.replace("toefl_house.", "", 1).replace(".", "/")
        self.assertTrue((APP / (relative + ".py")).exists(),
                        "doc_events points at a missing controller")

    def test_governance_registry_includes_the_carrier(self):
        match = re.search(r"^GOVERNANCE_DOCTYPES = (\{.*?\})",
                          self.permissions_source, re.S | re.M)
        self.assertTrue(match, "GOVERNANCE_DOCTYPES missing")
        governance = set(ast.literal_eval(match.group(1)))
        self.assertIn(POLICY, governance)

    def test_command_kinds_are_bound_to_the_business_policy_authority(self):
        kinds = ast.literal_eval(
            re.search(r"^KIND_AUTHORITY = (\{.*?^\})", self.audit_source,
                      re.S | re.M).group(1))
        for kind in COMMANDS:
            self.assertEqual(kinds.get(kind), "business_policy", kind)

    def test_module_and_registries_agree_on_command_kinds(self):
        tree = ast.parse(self.module_source)
        whitelisted = {node.name for node in tree.body
                       if isinstance(node, ast.FunctionDef)
                       and not node.name.startswith("_")
                       and node.name not in
                       ("validate_terms", "governing_capacity_objective")}
        self.assertEqual(whitelisted, set(COMMANDS))

    def test_desk_projection_is_bounded(self):
        self.assertIn('("configuration", "TH Capacity Objective")',
                      self.desk_init_source)
        self.assertIn(
            '("configuration", "TH Capacity Objective Version")',
            self.desk_init_source)
        # The owner-entered numbers are business intent — the desk shows
        # all four, only from governing versions, never synthesizing any.
        version_projection = self.desk_init_source.split(
            '("configuration", "TH Capacity Objective Version")', 1)[1]
        closing = version_projection.index("],")
        for name in ("concurrent_users_target", "document_scale_target",
                     "read_share_percent", "availability_target_percent"):
            self.assertIn(name, version_projection[:closing], name)

    def test_no_owner_value_is_synthesized_anywhere(self):
        # The bounded ceilings are technical input bounds, not values.
        self.assertIn("CONCURRENT_USERS_MAX = 100000", self.module_source)
        self.assertIn("DOCUMENT_SCALE_MAX = 1000000000", self.module_source)
        # The resolver returns exactly configured terms, never substitutes.
        self.assertIn("return {}", self.module_source)
        # No objective number is embedded as a default anywhere.
        self.assertNotIn("default_capacity", self.module_source)

    def test_release_gate_never_reads_business_settings(self):
        # PERMANENT RULE: the D8 capacity/availability gate is a
        # release-authorization control and is never configured from any
        # business setting. Pin the validator to zero Frappe coupling —
        # it evaluates static JSON contracts only and can never read the
        # TH Capacity Objective carrier or any site data.
        validator_source = D8_VALIDATOR.read_text(encoding="utf-8")
        self.assertNotIn("frappe", validator_source)
        self.assertNotIn("TH Capacity Objective", validator_source)


if __name__ == "__main__":
    unittest.main()

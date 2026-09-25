"""D7 metric-stewardship policy mechanism (decision classification, 2026-09-25).

Category B of the standing rule: named metric stewards and disclosure
rules for derived metrics are owner policy, never engineering constants.
The carrier holds exactly one policy; versions carry the effective-dated
owner choice of the D7 term pair — ``steward_role`` + ``disclosure_rules``.
Reads fail closed (no row / retired / no effective version all resolve to
{}); commands route through the receipted Course Owner gate under their
own kinds. Loads the REAL operations metric-stewardship module, the REAL
parent controller and the REAL academic + configuration rules against a
scripted frappe stub; hosted CI proves the journey.
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
MODULE = APP / "operations/metric_stewardship.py"
CONTROLLER = APP / ("operations/doctype/th_metric_stewardship_policy/"
                    "th_metric_stewardship_policy.py")
POLICY_JSON = APP / ("operations/doctype/th_metric_stewardship_policy/"
                     "th_metric_stewardship_policy.json")
VERSION_JSON = APP / ("operations/doctype/th_metric_stewardship_policy_version/"
                      "th_metric_stewardship_policy_version.json")
ACTOR = "course.owner@example.com"
POLICY = "TH Metric Stewardship Policy"
COMMANDS = (
    "create_metric_stewardship_policy",
    "set_metric_stewardship_policy_version",
    "set_metric_stewardship_policy_status",
    "validate_metric_stewardship_policy",
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
    test.role_exists = True
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
        if doctype == "Role":
            return fake.role_exists
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

    test.stewardship = _load_real("toefl_house.operations.metric_stewardship",
                                  MODULE)
    test.controller = _load_real(
        "toefl_house.operations.doctype.th_metric_stewardship_policy."
        "th_metric_stewardship_policy", CONTROLLER)
    test.foundation = sys.modules["toefl_house.configuration.rules"]


class MetricStewardshipPolicyTests(unittest.TestCase):
    def setUp(self):
        _install_command_harness(self)

    def _existing_policy(self, status="Active", versions=()):
        self.policy_rows = [{"name": "MET-STEW-POL"}]
        self.policy_doc = _PolicyDoc(name="MET-STEW-POL", code="MET-STEW-POL",
                                     title="Stewardship rule", status=status,
                                     versions=[_Row(v) for v in versions])
        return self.policy_doc

    def _version(self, key, date, role="General Manager",
                 rules_text="Derived metrics carry grain and provenance labels "
                            "and are readable by management roles only."):
        return self.stewardship.set_metric_stewardship_policy_version(
            key, "MET-STEW-POL", date,
            "Owner opens metric stewardship", role, rules_text)

    # --- guarded commands --------------------------------------------
    def test_create_shell_carries_no_versions(self):
        result = self.stewardship.create_metric_stewardship_policy(
            "test-key-metstew-create01", "MET-STEW-POL", "Stewardship rule")
        self.assertEqual(result["code"], "MET-STEW-POL")
        self.assertEqual(result["status"], "Active")
        self.assertEqual(result["version_count"], 0)
        self.assertEqual(result["governing_steward_role"], "")
        kind, _key, _payload = self.execute_calls[0]
        self.assertEqual(kind, "create_metric_stewardship_policy")

    def test_second_policy_is_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self.stewardship.create_metric_stewardship_policy(
                "test-key-metstew-create02", "MET-STEW-TWO", "Second rule")
        self.assertIn("version it instead", str(ctx.exception))

    def test_version_append_governs_from_its_date(self):
        self._existing_policy()
        result = self._version("test-key-metstew-versn01", "2026-09-28")
        self.assertEqual(result["version_count"], 1)
        # Not yet effective today: the shell still governs nothing.
        self.assertEqual(result["governing_steward_role"], "")
        self.assertEqual(self.stewardship.governing_stewardship(), {})
        self.today = "2026-09-28"
        terms = self.stewardship.governing_stewardship()
        self.assertEqual(terms["effective_from"], "2026-09-28")
        self.assertEqual(terms["steward_role"], "General Manager")
        self.assertIn("grain and provenance labels", terms["disclosure_rules"])

    def test_unknown_steward_role_is_refused(self):
        self._existing_policy()
        self.role_exists = False
        with self.assertRaises(_ValidationError) as ctx:
            self._version("test-key-metstew-versn02", "2026-09-28",
                          role="No Such Role")
        self.assertIn("Unknown steward role", str(ctx.exception))

    def test_empty_and_overlong_disclosure_rules_are_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self._version("test-key-metstew-versn03", "2026-09-28",
                          rules_text="   ")
        self.assertIn("Disclosure rules are required", str(ctx.exception))
        with self.assertRaises(_ValidationError) as ctx:
            self._version("test-key-metstew-versn04", "2026-09-28",
                          rules_text="x" * 2001)
        self.assertIn("at most 2000 characters", str(ctx.exception))

    def test_backdated_and_same_day_versions_refused(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-28", "steward_role": "General Manager",
            "disclosure_rules": "disclosure text",
            "reason": "Owner opens metric stewardship",
            "set_by": ACTOR, "set_on": "2026-09-25 12:00:00"}])
        with self.assertRaises(_ValidationError):
            self._version("test-key-metstew-versn05", "2026-09-20")
        with self.assertRaises(_ValidationError):
            self._version("test-key-metstew-versn06", "2026-09-28")

    def test_superseded_version_is_closed_not_rewritten(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-28", "steward_role": "General Manager",
            "disclosure_rules": "first disclosure",
            "reason": "Owner opens metric stewardship",
            "set_by": ACTOR, "set_on": "2026-09-25 12:00:00"}])
        self._version("test-key-metstew-versn07", "2026-10-01",
                      role="Academic Manager", rules_text="second disclosure")
        first, second = self.policy_doc.versions
        self.assertEqual(first["disclosure_rules"], "first disclosure")
        self.assertEqual(first["superseded_on"], "2026-10-01")
        self.assertEqual(second["steward_role"], "Academic Manager")
        self.assertNotIn("superseded_on", second)

    def test_retire_is_the_off_switch(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-20", "steward_role": "General Manager",
            "disclosure_rules": "disclosure text",
            "reason": "Owner opens metric stewardship",
            "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}])
        self.assertEqual(
            self.stewardship.governing_stewardship()["steward_role"],
            "General Manager")
        result = self.stewardship.set_metric_stewardship_policy_status(
            "test-key-metstew-status1", "MET-STEW-POL", 0)
        self.assertEqual(result["status"], "Retired")
        self.assertEqual(self.stewardship.governing_stewardship(), {})
        self.stewardship.set_metric_stewardship_policy_status(
            "test-key-metstew-status2", "MET-STEW-POL", 1)
        self.assertEqual(
            self.stewardship.governing_stewardship()["disclosure_rules"],
            "disclosure text")

    def test_governing_read_fails_closed_without_policy_or_version(self):
        self.assertEqual(self.stewardship.governing_stewardship(), {})
        self._existing_policy()
        self.assertEqual(self.stewardship.governing_stewardship(), {})

    # --- validate command --------------------------------------------
    def test_validate_requires_versions(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self.stewardship.validate_metric_stewardship_policy(
                "test-key-metstew-valid01", "MET-STEW-POL")
        self.assertIn("no versions yet", str(ctx.exception))

    def test_validate_rechecks_every_referenced_role(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-20", "steward_role": "General Manager",
            "disclosure_rules": "disclosure text",
            "reason": "Owner opens metric stewardship",
            "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}])
        self.role_exists = False
        with self.assertRaises(_ValidationError) as ctx:
            self.stewardship.validate_metric_stewardship_policy(
                "test-key-metstew-valid02", "MET-STEW-POL")
        self.assertIn("no longer exists", str(ctx.exception))

    def test_validate_snapshot_recovers_readiness(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-28", "steward_role": "General Manager",
            "disclosure_rules": "disclosure text",
            "reason": "Owner opens metric stewardship",
            "set_by": ACTOR, "set_on": "2026-09-25 12:00:00"}])
        result = self.stewardship.validate_metric_stewardship_policy(
            "test-key-metstew-valid03", "MET-STEW-POL")
        # Latest version starts after today: validated, not yet effective.
        self.assertEqual(result["readiness"], "validated")
        kind, _key, _payload = self.execute_calls[-1]
        self.assertEqual(kind, "validate_metric_stewardship_policy")

    def test_all_four_commands_route_through_the_receipted_gate(self):
        self.stewardship.create_metric_stewardship_policy(
            "test-key-metstew-route01", "MET-STEW-POL", "Stewardship rule")
        self.policy_rows = [{"name": "MET-STEW-POL"}]
        self.policy_doc = _PolicyDoc(name="MET-STEW-POL", code="MET-STEW-POL",
                                     title="Stewardship rule", status="Active",
                                     versions=[])
        self.stewardship.set_metric_stewardship_policy_version(
            "test-key-metstew-route02", "MET-STEW-POL", "2026-09-28",
            "Owner opens metric stewardship", "General Manager",
            "disclosure text")
        self.stewardship.set_metric_stewardship_policy_status(
            "test-key-metstew-route03", "MET-STEW-POL", 0)
        self.stewardship.set_metric_stewardship_policy_status(
            "test-key-metstew-route04", "MET-STEW-POL", 1)
        seen = [call[0] for call in self.execute_calls]
        self.assertEqual(seen, [
            "create_metric_stewardship_policy",
            "set_metric_stewardship_policy_version",
            "set_metric_stewardship_policy_status",
            "set_metric_stewardship_policy_status",
        ])

    # --- controller seam ----------------------------------------------
    def _doc(self, versions=()):
        return _PolicyDoc(code="MET-STEW-POL", title="Stewardship rule",
                          status="Active", description="",
                          versions=[_DocRow(**v) for v in versions])

    def test_validate_outside_a_command_is_refused_first(self):
        with self.assertRaises(_PermissionError) as ctx:
            self.controller.validate(self._doc())
        self.assertIn("guarded Course Owner commands", str(ctx.exception))

    def test_inside_a_command_the_rules_bind(self):
        # A good document validates quietly inside a real command context.
        with self.foundation.command_context(
                "set_metric_stewardship_policy_version"):
            self.controller.validate(self._doc(versions=[{
                "effective_from": "2026-09-28",
                "steward_role": "General Manager",
                "disclosure_rules": "disclosure text",
                "reason": "Owner opens metric stewardship",
                "set_by": ACTOR, "set_on": "2026-09-25 12:00:00"}]))

    def test_two_versions_sharing_one_effective_date_refused(self):
        doc = self._doc(versions=[
            {"effective_from": "2026-09-28", "steward_role": "General Manager",
             "disclosure_rules": "first", "reason": "first version"},
            {"effective_from": "2026-09-28", "steward_role": "General Manager",
             "disclosure_rules": "second", "reason": "second version"}])
        with self.foundation.command_context("set_metric_stewardship_policy_version"):
            with self.assertRaises(_ValidationError) as ctx:
                self.controller.validate(doc)
        self.assertIn("cannot share one effective date", str(ctx.exception))

    def test_closed_date_before_effective_is_refused(self):
        doc = self._doc(versions=[{
            "effective_from": "2026-09-28", "steward_role": "General Manager",
            "disclosure_rules": "text", "reason": "a reason",
            "superseded_on": "2026-09-27"}])
        with self.foundation.command_context("set_metric_stewardship_policy_version"):
            with self.assertRaises(_ValidationError) as ctx:
                self.controller.validate(doc)
        self.assertIn("must fall after", str(ctx.exception))

    def test_row_reads_never_use_subscripts(self):
        # Real child rows are not subscriptable; owned code must not index them.
        for module in (MODULE, CONTROLLER):
            with self.subTest(module=module.name):
                bad = re.findall(r"\brow\[", module.read_text(encoding="utf-8"))
                self.assertEqual(bad, [])


class MetricStewardshipWiringTests(unittest.TestCase):
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
                         "TH Metric Stewardship Policy Version")

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
        steward = fields["steward_role"]
        self.assertEqual(steward.get("fieldtype"), "Link")
        self.assertEqual(steward.get("options"), "Role")
        self.assertEqual(steward.get("reqd"), 1)
        self.assertEqual(fields["disclosure_rules"].get("reqd"), 1)
        # No owner value ships: no default is pinned on any value field.
        for name in ("steward_role", "disclosure_rules", "reason",
                     "effective_from"):
            self.assertNotIn("default", fields[name],
                             f"{name} must not carry a default value")

    def test_hsbc_policy_index_web_pages_matches_siblings(self):
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
            "operations.doctype.th_metric_stewardship_policy."
            "th_metric_stewardship_policy.validate", validate_path)
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
                       ("validate_terms", "governing_stewardship")}
        self.assertEqual(whitelisted, set(COMMANDS))

    def test_desk_projection_is_bounded(self):
        self.assertIn('("configuration", "TH Metric Stewardship Policy")',
                      self.desk_init_source)
        self.assertIn(
            '("configuration", "TH Metric Stewardship Policy Version")',
            self.desk_init_source)

    def test_no_owner_value_is_synthesized_anywhere(self):
        # The bounded text cap is a technical input bound, not a value.
        self.assertIn("DISCLOSURE_RULES_MAX = 2000", self.module_source)
        # The resolver returns exactly configured terms, never substitutes.
        self.assertIn("return {}", self.module_source)
        # No disclosure/steward literal is embedded as a default anywhere.
        self.assertNotIn("default_steward", self.module_source)


if __name__ == "__main__":
    unittest.main()

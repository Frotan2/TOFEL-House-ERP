"""TH Alerting Policy mechanism (decision classification track 2, 2026-09-25).

Category B of the standing rule: selecting an alert receiver — and the
retention/escalation policy around it — is owner policy, never an
engineering constant (observability RECEIVER BOUNDARY). The carrier holds
exactly one policy; versions carry the effective-dated owner choice of
channel kind + receiver reference + retention (+ optional escalation).
Reads fail closed (no row / retired / no effective version all resolve to
{}); commands route through the receipted Course Owner gate under their
own kinds. Loads the REAL operations alerting module, the REAL parent
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
MODULE = APP / "operations/alerting.py"
CONTROLLER = APP / ("operations/doctype/th_alerting_policy/"
                    "th_alerting_policy.py")
POLICY_JSON = APP / ("operations/doctype/th_alerting_policy/"
                     "th_alerting_policy.json")
VERSION_JSON = APP / ("operations/doctype/th_alerting_policy_version/"
                      "th_alerting_policy_version.json")
OBSERVABILITY = APP / "observability.py"
ACTOR = "course.owner@example.com"
POLICY = "TH Alerting Policy"
COMMANDS = (
    "create_alerting_policy",
    "set_alerting_policy_version",
    "set_alerting_policy_status",
    "validate_alerting_policy",
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

    test.alerting = _load_real("toefl_house.operations.alerting", MODULE)
    test.controller = _load_real(
        "toefl_house.operations.doctype.th_alerting_policy."
        "th_alerting_policy", CONTROLLER)
    test.foundation = sys.modules["toefl_house.configuration.rules"]


class AlertingPolicyTests(unittest.TestCase):
    def setUp(self):
        _install_command_harness(self)

    def _existing_policy(self, status="Active", versions=()):
        self.policy_rows = [{"name": "ALERT-POL"}]
        self.policy_doc = _PolicyDoc(name="ALERT-POL", code="ALERT-POL",
                                     title="Receiver rule", status=status,
                                     versions=[_Row(v) for v in versions])
        return self.policy_doc

    def _version(self, key, date, channel="Email",
                 reference="ops-alerts@example.com", retention=30,
                 escalate=None):
        return self.alerting.set_alerting_policy_version(
            key, "ALERT-POL", date, "Owner selects the alert receiver",
            channel, reference, retention, escalate)

    # --- guarded commands --------------------------------------------
    def test_create_shell_carries_no_versions(self):
        result = self.alerting.create_alerting_policy(
            "test-key-alert-create01", "ALERT-POL", "Receiver rule")
        self.assertEqual(result["code"], "ALERT-POL")
        self.assertEqual(result["status"], "Active")
        self.assertEqual(result["version_count"], 0)
        self.assertEqual(result["governing_channel_kind"], "")
        kind, _key, _payload = self.execute_calls[0]
        self.assertEqual(kind, "create_alerting_policy")

    def test_second_policy_is_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self.alerting.create_alerting_policy(
                "test-key-alert-create02", "ALERT-POL-2", "Second rule")
        self.assertIn("version it instead", str(ctx.exception))

    def test_version_append_governs_from_its_date(self):
        self._existing_policy()
        result = self._version("test-key-alert-versn01", "2026-09-28")
        self.assertEqual(result["version_count"], 1)
        # Not yet effective today: the shell still governs nothing.
        self.assertEqual(result["governing_channel_kind"], "")
        self.assertEqual(self.alerting.governing_alerting_policy(), {})
        self.today = "2026-09-28"
        terms = self.alerting.governing_alerting_policy()
        self.assertEqual(terms["effective_from"], "2026-09-28")
        self.assertEqual(terms["channel_kind"], "Email")
        self.assertEqual(terms["receiver_reference"], "ops-alerts@example.com")
        self.assertEqual(terms["retention_days"], 30)

    def test_unknown_channel_kind_is_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self._version("test-key-alert-versn02", "2026-09-28",
                          channel="Pigeon")
        self.assertIn("Channel kind must be one of Email / Webhook / "
                      "Dashboard", str(ctx.exception))

    def test_empty_and_overlong_receiver_reference_are_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self._version("test-key-alert-versn03", "2026-09-28",
                          reference="   ")
        self.assertIn("Receiver reference is required", str(ctx.exception))
        with self.assertRaises(_ValidationError) as ctx:
            self._version("test-key-alert-versn04", "2026-09-28",
                          reference="x" * 141)
        self.assertIn("at most 140 characters", str(ctx.exception))

    def test_retention_is_required_and_bounded(self):
        self._existing_policy()
        for bad in (None, 0, -5, 3651, True, "soon"):
            with self.subTest(bad=bad):
                with self.assertRaises(_ValidationError) as ctx:
                    self._version("test-key-alert-versn05", "2026-09-28",
                                  retention=bad)
                self.assertIn("Retention days must be a whole number "
                              "between 1 and 3650", str(ctx.exception))
        # A digit string is coerced, stored as the integer.
        result = self._version("test-key-alert-versn06", "2026-09-28",
                               retention="45")
        self.assertEqual(result["version_count"], 1)
        row = self.policy_doc.versions[0]
        self.assertEqual(row["retention_days"], 45)

    def test_escalation_is_optional_and_bounded(self):
        self._existing_policy()
        result = self._version("test-key-alert-versn07", "2026-09-28",
                               escalate="60")
        row = self.policy_doc.versions[0]
        self.assertEqual(row["escalate_after_minutes"], 60)
        for bad in (0, 525601, "later"):
            with self.subTest(bad=bad):
                with self.assertRaises(_ValidationError) as ctx:
                    self._version("test-key-alert-versn08", "2026-10-01",
                                  escalate=bad)
                self.assertIn("Escalate-after minutes must be a whole "
                              "number", str(ctx.exception))
        self.assertEqual(result["version_count"], 1)

    def test_backdated_and_same_day_versions_refused(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-28", "channel_kind": "Email",
            "receiver_reference": "ops-alerts@example.com",
            "retention_days": 30,
            "reason": "Owner selects the alert receiver",
            "set_by": ACTOR, "set_on": "2026-09-25 12:00:00"}])
        with self.assertRaises(_ValidationError):
            self._version("test-key-alert-versn09", "2026-09-20")
        with self.assertRaises(_ValidationError):
            self._version("test-key-alert-versn10", "2026-09-28")

    def test_superseded_version_is_closed_not_rewritten(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-28", "channel_kind": "Email",
            "receiver_reference": "first@example.com", "retention_days": 30,
            "reason": "Owner selects the alert receiver",
            "set_by": ACTOR, "set_on": "2026-09-25 12:00:00"}])
        self._version("test-key-alert-versn11", "2026-10-01",
                      channel="Webhook",
                      reference="https://hooks.example.test/alerts",
                      retention=90)
        first, second = self.policy_doc.versions
        self.assertEqual(first["receiver_reference"], "first@example.com")
        self.assertEqual(first["superseded_on"], "2026-10-01")
        self.assertEqual(second["channel_kind"], "Webhook")
        self.assertEqual(second["retention_days"], 90)
        self.assertNotIn("superseded_on", second)

    def test_retire_is_the_off_switch(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-20", "channel_kind": "Email",
            "receiver_reference": "ops-alerts@example.com",
            "retention_days": 30,
            "reason": "Owner selects the alert receiver",
            "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}])
        self.assertEqual(
            self.alerting.governing_alerting_policy()["channel_kind"],
            "Email")
        result = self.alerting.set_alerting_policy_status(
            "test-key-alert-status1", "ALERT-POL", 0)
        self.assertEqual(result["status"], "Retired")
        self.assertEqual(self.alerting.governing_alerting_policy(), {})
        self.alerting.set_alerting_policy_status(
            "test-key-alert-status2", "ALERT-POL", 1)
        self.assertEqual(
            self.alerting.governing_alerting_policy()["receiver_reference"],
            "ops-alerts@example.com")

    def test_governing_read_fails_closed_without_policy_or_version(self):
        self.assertEqual(self.alerting.governing_alerting_policy(), {})
        self._existing_policy()
        self.assertEqual(self.alerting.governing_alerting_policy(), {})

    # --- validate command --------------------------------------------
    def test_validate_requires_versions(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self.alerting.validate_alerting_policy(
                "test-key-alert-valid01", "ALERT-POL")
        self.assertIn("no versions yet", str(ctx.exception))

    def test_validate_rechecks_every_stored_row(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-20", "channel_kind": "Pigeon",
            "receiver_reference": "ops-alerts@example.com",
            "retention_days": 30,
            "reason": "Owner selects the alert receiver",
            "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}])
        with self.assertRaises(_ValidationError) as ctx:
            self.alerting.validate_alerting_policy(
                "test-key-alert-valid02", "ALERT-POL")
        self.assertIn("Channel kind must be one of", str(ctx.exception))
        self._existing_policy(versions=[{
            "effective_from": "2026-09-20", "channel_kind": "Email",
            "receiver_reference": "ops-alerts@example.com",
            "retention_days": None,
            "reason": "Owner selects the alert receiver",
            "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}])
        with self.assertRaises(_ValidationError) as ctx:
            self.alerting.validate_alerting_policy(
                "test-key-alert-valid03", "ALERT-POL")
        self.assertIn("Retention days must be a whole number",
                      str(ctx.exception))

    def test_validate_snapshot_recovers_readiness(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-28", "channel_kind": "Email",
            "receiver_reference": "ops-alerts@example.com",
            "retention_days": 30,
            "reason": "Owner selects the alert receiver",
            "set_by": ACTOR, "set_on": "2026-09-25 12:00:00"}])
        result = self.alerting.validate_alerting_policy(
            "test-key-alert-valid04", "ALERT-POL")
        # Latest version starts after today: validated, not yet effective.
        self.assertEqual(result["readiness"], "validated")
        kind, _key, _payload = self.execute_calls[-1]
        self.assertEqual(kind, "validate_alerting_policy")

    def test_all_four_commands_route_through_the_receipted_gate(self):
        self.alerting.create_alerting_policy(
            "test-key-alert-route01", "ALERT-POL", "Receiver rule")
        self.policy_rows = [{"name": "ALERT-POL"}]
        self.policy_doc = _PolicyDoc(name="ALERT-POL", code="ALERT-POL",
                                     title="Receiver rule", status="Active",
                                     versions=[])
        self.alerting.set_alerting_policy_version(
            "test-key-alert-route02", "ALERT-POL", "2026-09-28",
            "Owner selects the alert receiver", "Email",
            "ops-alerts@example.com", 30)
        self.alerting.set_alerting_policy_status(
            "test-key-alert-route03", "ALERT-POL", 0)
        self.alerting.set_alerting_policy_status(
            "test-key-alert-route04", "ALERT-POL", 1)
        seen = [call[0] for call in self.execute_calls]
        self.assertEqual(seen, [
            "create_alerting_policy",
            "set_alerting_policy_version",
            "set_alerting_policy_status",
            "set_alerting_policy_status",
        ])

    # --- controller seam ----------------------------------------------
    def _doc(self, versions=()):
        return _PolicyDoc(code="ALERT-POL", title="Receiver rule",
                          status="Active", description="",
                          versions=[_DocRow(**v) for v in versions])

    def test_validate_outside_a_command_is_refused_first(self):
        with self.assertRaises(_PermissionError) as ctx:
            self.controller.validate(self._doc())
        self.assertIn("guarded Course Owner commands", str(ctx.exception))

    def test_inside_a_command_the_rules_bind(self):
        # A good document validates quietly inside a real command context.
        with self.foundation.command_context(
                "set_alerting_policy_version"):
            self.controller.validate(self._doc(versions=[{
                "effective_from": "2026-09-28",
                "channel_kind": "Email",
                "receiver_reference": "ops-alerts@example.com",
                "retention_days": 30,
                "reason": "Owner selects the alert receiver",
                "set_by": ACTOR, "set_on": "2026-09-25 12:00:00"}]))

    def test_two_versions_sharing_one_effective_date_refused(self):
        doc = self._doc(versions=[
            {"effective_from": "2026-09-28", "channel_kind": "Email",
             "receiver_reference": "a@example.com", "retention_days": 30,
             "reason": "first version"},
            {"effective_from": "2026-09-28", "channel_kind": "Email",
             "receiver_reference": "b@example.com", "retention_days": 60,
             "reason": "second version"}])
        with self.foundation.command_context("set_alerting_policy_version"):
            with self.assertRaises(_ValidationError) as ctx:
                self.controller.validate(doc)
        self.assertIn("cannot share one effective date", str(ctx.exception))

    def test_closed_date_before_effective_is_refused(self):
        doc = self._doc(versions=[{
            "effective_from": "2026-09-28", "channel_kind": "Email",
            "receiver_reference": "a@example.com", "retention_days": 30,
            "reason": "a reason",
            "superseded_on": "2026-09-27"}])
        with self.foundation.command_context("set_alerting_policy_version"):
            with self.assertRaises(_ValidationError) as ctx:
                self.controller.validate(doc)
        self.assertIn("must fall after", str(ctx.exception))

    def test_row_reads_never_use_subscripts(self):
        # Real child rows are not subscriptable; owned code must not index them.
        for module in (MODULE, CONTROLLER):
            with self.subTest(module=module.name):
                bad = re.findall(r"\brow\[", module.read_text(encoding="utf-8"))
                self.assertEqual(bad, [])


class AlertingWiringTests(unittest.TestCase):
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
                         "TH Alerting Policy Version")

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
        channel = fields["channel_kind"]
        self.assertEqual(channel.get("fieldtype"), "Select")
        self.assertEqual(channel.get("options"), "Email\nWebhook\nDashboard")
        self.assertEqual(channel.get("reqd"), 1)
        self.assertEqual(fields["receiver_reference"].get("reqd"), 1)
        self.assertEqual(fields["retention_days"].get("fieldtype"), "Int")
        self.assertEqual(fields["retention_days"].get("reqd"), 1)
        self.assertEqual(fields["escalate_after_minutes"].get("fieldtype"),
                         "Int")
        self.assertNotEqual(fields["escalate_after_minutes"].get("reqd"), 1)
        # SMS is deliberately not offered: no native mechanism exists.
        self.assertNotIn("SMS", channel.get("options"))
        # No owner value ships: no default is pinned on any value field.
        for name in ("channel_kind", "receiver_reference", "retention_days",
                     "escalate_after_minutes", "reason", "effective_from"):
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
            "operations.doctype.th_alerting_policy."
            "th_alerting_policy.validate", validate_path)
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
                       ("validate_terms", "governing_alerting_policy")}
        self.assertEqual(whitelisted, set(COMMANDS))

    def test_desk_projection_is_bounded(self):
        self.assertIn('("configuration", "TH Alerting Policy")',
                      self.desk_init_source)
        self.assertIn(
            '("configuration", "TH Alerting Policy Version")',
            self.desk_init_source)
        # The owner-provided receiver destination stays on the document;
        # the desk names the channel and terms, never the destination.
        version_projection = self.desk_init_source.split(
            '("configuration", "TH Alerting Policy Version")', 1)[1]
        closing = version_projection.index("],")
        self.assertNotIn("receiver_reference",
                         version_projection[:closing])

    def test_no_owner_value_is_synthesized_anywhere(self):
        # The bounded ceilings are technical input bounds, not values.
        self.assertIn("RECEIVER_REFERENCE_MAX = 140", self.module_source)
        self.assertIn("RETENTION_DAYS_MAX = 3650", self.module_source)
        # The resolver returns exactly configured terms, never substitutes.
        self.assertIn("return {}", self.module_source)
        # No receiver literal is embedded as a default anywhere.
        self.assertNotIn("default_receiver", self.module_source)

    def test_observability_stays_delivery_free(self):
        # The RECEIVER BOUNDARY is binding: conditions are generated,
        # never delivered. Pin the observability module to zero delivery
        # primitives — a real receiver is owner-selected policy plus a
        # real-environment proof, neither of which exists in that module.
        observability_source = OBSERVABILITY.read_text(encoding="utf-8")
        for forbidden in ("publish_realtime", "enqueue", "sendmail",
                          "smtplib", "requests.post"):
            self.assertNotIn(forbidden, observability_source)
        self.assertIn("RECEIVER BOUNDARY", observability_source)


if __name__ == "__main__":
    unittest.main()

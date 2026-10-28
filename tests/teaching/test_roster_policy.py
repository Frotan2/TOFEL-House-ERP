"""S8 regression: the roster-change policy mechanism (OD-NEW-05).

The house holds exactly one roster-change policy; versions carry the
effective-dated owner choice of a single facet — ``changes_allowed_until``,
the last date on which mid-term roster changes may execute. Reads fail
closed (no row / retired / no effective version all resolve to ""); commands
route through the receipted Course Owner gate under their own kind. Loads
the REAL teaching policies module with the REAL academic + configuration
rules against a scripted frappe stub; hosted CI proves the roster journey.
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
    "create_roster_change_policy",
    "set_roster_change_policy_version",
    "set_roster_change_policy_status",
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


class RosterPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy_rows = []
        self.policy_doc = None
        self.execute_calls = []
        self.today = "2026-09-22"
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
        fake = self

        def get_all(doctype, fields=None, filters=None, limit=None, **kwargs):
            assert doctype == "TH Roster Change Policy"
            return list(fake.policy_rows)

        def get_value(doctype, name_or_filters, fieldname=None, **kwargs):
            if doctype == "TH Roster Change Policy":
                assert fake.policy_doc is not None
                return fake.policy_doc.name
            raise AssertionError(f"unexpected get_value {doctype}")

        def get_doc(doctype, name=None, for_update=False, **kwargs):
            if isinstance(doctype, dict):
                payload = dict(doctype)
                doc = _PolicyDoc(name=payload.get("code"), **payload)
                fake.policy_doc = doc
                return doc
            assert doctype == "TH Roster Change Policy"
            assert fake.policy_doc is not None
            return fake.policy_doc

        from types import SimpleNamespace
        stub = types.ModuleType("frappe")
        stub.PermissionError = _PermissionError
        stub.ValidationError = _ValidationError
        stub.whitelist = lambda **kwargs: (lambda func: func)
        stub.utils = SimpleNamespace(
            today=lambda: fake.today,
            now_datetime=lambda: "2026-09-22 12:00:00")
        stub.db = SimpleNamespace(get_all=get_all, get_value=get_value,
                                  exists=lambda *a, **k: False)
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
        teaching_pkg = types.ModuleType("toefl_house.teaching")
        teaching_pkg.__path__ = [str(APP / "teaching")]
        sys.modules["toefl_house.teaching"] = teaching_pkg
        self.policies = _load_real("toefl_house.teaching.policies",
                                   APP / "teaching/policies.py")

    def _existing_policy(self, status="Active", versions=()):
        self.policy_rows = [{"name": "ROSTER-POL"}]
        self.policy_doc = _PolicyDoc(name="ROSTER-POL", code="ROSTER-POL",
                                     title="Roster rule", status=status,
                                     versions=[_Row(v) for v in versions])
        return self.policy_doc

    def test_create_shell_carries_no_versions(self):
        result = self.policies.create_roster_change_policy(
            "test-key-roster-create01", "ROSTER-POL", "Roster rule")
        self.assertEqual(result["code"], "ROSTER-POL")
        self.assertEqual(result["status"], "Active")
        self.assertEqual(result["version_count"], 0)
        self.assertEqual(result["governing_changes_allowed_until"], "")
        kind, _key, _payload = self.execute_calls[0]
        self.assertEqual(kind, "create_roster_change_policy")

    def test_second_policy_is_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self.policies.create_roster_change_policy(
                "test-key-roster-create02", "ROSTER-TWO", "Second rule")
        self.assertIn("version it instead", str(ctx.exception))

    def test_version_append_governs_from_its_date(self):
        self._existing_policy()
        result = self.policies.set_roster_change_policy_version(
            "test-key-roster-versn01", "ROSTER-POL", "2026-09-23",
            "Owner opens mid-term roster fixes", "2026-10-15")
        self.assertEqual(result["version_count"], 1)
        # Not yet effective today: the shell still governs nothing.
        self.assertEqual(result["governing_changes_allowed_until"], "")
        self.today = "2026-09-23"
        self.assertEqual(self.policies.governing_cutoff_date(), "2026-10-15")

    def test_cutoff_before_effective_is_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self.policies.set_roster_change_policy_version(
                "test-key-roster-versn02", "ROSTER-POL", "2026-09-23",
                "Owner tries a cutoff that precedes the start", "2026-09-20")
        self.assertIn("retire the policy", str(ctx.exception))

    def test_backdated_and_same_day_versions_refused(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-23",
            "changes_allowed_until": "2026-10-15",
            "reason": "Owner opens mid-term roster fixes",
            "set_by": ACTOR, "set_on": "2026-09-22 12:00:00"}])
        with self.assertRaises(_ValidationError):
            self.policies.set_roster_change_policy_version(
                "test-key-roster-versn03", "ROSTER-POL", "2026-09-20",
                "Backdated change", "2026-10-15")
        with self.assertRaises(_ValidationError):
            self.policies.set_roster_change_policy_version(
                "test-key-roster-versn04", "ROSTER-POL", "2026-09-23",
                "Same-day change", "2026-10-15")

    def test_superseded_version_is_closed_not_rewritten(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-23",
            "changes_allowed_until": "2026-10-15",
            "reason": "Owner opens mid-term roster fixes",
            "set_by": ACTOR, "set_on": "2026-09-22 12:00:00"}])
        self.policies.set_roster_change_policy_version(
            "test-key-roster-versn05", "ROSTER-POL", "2026-10-01",
            "Owner extends the roster window", "2026-11-01")
        first, second = self.policy_doc.versions
        self.assertEqual(first["changes_allowed_until"], "2026-10-15")
        self.assertEqual(first["superseded_on"], "2026-10-01")
        self.assertNotIn("superseded_on", second)

    def test_retire_is_the_off_switch(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-20",
            "changes_allowed_until": "2026-10-15",
            "reason": "Owner opens mid-term roster fixes",
            "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}])
        self.assertEqual(self.policies.governing_cutoff_date(), "2026-10-15")
        result = self.policies.set_roster_change_policy_status(
            "test-key-roster-status1", "ROSTER-POL", 0)
        self.assertEqual(result["status"], "Retired")
        self.assertEqual(self.policies.governing_cutoff_date(), "")
        self.policies.set_roster_change_policy_status(
            "test-key-roster-status2", "ROSTER-POL", 1)
        self.assertEqual(self.policies.governing_cutoff_date(), "2026-10-15")

    def test_governing_read_fails_closed_without_policy_or_version(self):
        self.assertEqual(self.policies.governing_cutoff_date(), "")
        self._existing_policy()
        self.assertEqual(self.policies.governing_cutoff_date(), "")


class RosterPolicyGateTests(unittest.TestCase):
    """Source-level receipt-gate parity with the S5/S7 policy commands."""

    def test_commands_route_through_the_receipted_gate(self):
        source = (APP / "teaching/policies.py").read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()

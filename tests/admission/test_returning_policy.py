"""S7 regression: the returning-student policy mechanism (OD-NEW-01/B).

The house holds exactly one returning-student policy; versions carry
the effective-dated owner choice, and only executable modes may be
recorded. Reads fail closed (no row / retired / no effective version
all resolve to ""); commands route through the receipted Course Owner
gate under their own kind. Loads the REAL admission policies module
with the REAL academic + configuration rules against a scripted frappe
stub; hosted CI proves the full returning journey.
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
    "create_returning_student_policy",
    "set_returning_student_policy_version",
    "set_returning_student_policy_status",
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


class ReturningPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy_rows = []
        self.policy_doc = None
        self.execute_calls = []
        self.today = "2026-09-22"
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
        fake = self

        def get_all(doctype, fields=None, filters=None, limit=None, **kwargs):
            assert doctype == "TH Returning Student Policy"
            return list(fake.policy_rows)

        def get_value(doctype, name_or_filters, fieldname=None, **kwargs):
            if doctype == "TH Returning Student Policy":
                assert fake.policy_doc is not None
                return fake.policy_doc.name
            raise AssertionError(f"unexpected get_value {doctype}")

        def get_doc(doctype, name=None, for_update=False, **kwargs):
            if isinstance(doctype, dict):
                payload = dict(doctype)
                doc = _PolicyDoc(name=payload.get("code"), **payload)
                fake.policy_doc = doc
                return doc
            assert doctype == "TH Returning Student Policy"
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
        admission_pkg = types.ModuleType("toefl_house.admission")
        admission_pkg.__path__ = [str(APP / "admission")]
        sys.modules["toefl_house.admission"] = admission_pkg
        self.policies = _load_real("toefl_house.admission.policies",
                                   APP / "admission/policies.py")

    def _existing_policy(self, status="Active", versions=()):
        self.policy_rows = [{"name": "RET-POL"}]
        self.policy_doc = _PolicyDoc(name="RET-POL", code="RET-POL",
                                     title="Returning rule", status=status,
                                     versions=[_Row(v) for v in versions])
        return self.policy_doc

    def test_create_shell_carries_no_versions(self):
        result = self.policies.create_returning_student_policy(
            "test-key-retpol-create01", "RET-POL", "Returning rule")
        self.assertEqual(result["code"], "RET-POL")
        self.assertEqual(result["status"], "Active")
        self.assertEqual(result["version_count"], 0)
        self.assertEqual(result["governing_mode"], "")
        kind, _key, _payload = self.execute_calls[0]
        self.assertEqual(kind, "create_returning_student_policy")

    def test_second_policy_is_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self.policies.create_returning_student_policy(
                "test-key-retpol-create02", "RET-TWO", "Second rule")
        self.assertIn("version it instead", str(ctx.exception))

    def test_version_append_governs_from_its_date(self):
        self._existing_policy()
        result = self.policies.set_returning_student_policy_version(
            "test-key-retpol-versn01", "RET-POL", "2026-09-23",
            "Owner enables placement-per-term returns", "placement_per_term")
        self.assertEqual(result["version_count"], 1)
        # Not yet effective today: the shell still governs nothing.
        self.assertEqual(result["governing_mode"], "")
        self.today = "2026-09-23"
        self.assertEqual(self.policies.governing_returning_mode(), "placement_per_term")

    def test_unknown_mode_is_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self.policies.set_returning_student_policy_version(
                "test-key-retpol-versn02", "RET-POL", "2026-09-23",
                "Owner tries a lane with no intake command", "returning_lane")
        self.assertIn("placement_per_term", str(ctx.exception))

    def test_backdated_and_same_day_versions_refused(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-23", "mode": "placement_per_term",
            "reason": "Owner enables placement-per-term returns",
            "set_by": ACTOR, "set_on": "2026-09-22 12:00:00"}])
        with self.assertRaises(_ValidationError):
            self.policies.set_returning_student_policy_version(
                "test-key-retpol-versn03", "RET-POL", "2026-09-20",
                "Backdated change", "placement_per_term")
        with self.assertRaises(_ValidationError):
            self.policies.set_returning_student_policy_version(
                "test-key-retpol-versn04", "RET-POL", "2026-09-23",
                "Same-day change", "placement_per_term")

    def test_superseded_version_is_closed_not_rewritten(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-23", "mode": "placement_per_term",
            "reason": "Owner enables placement-per-term returns",
            "set_by": ACTOR, "set_on": "2026-09-22 12:00:00"}])
        self.policies.set_returning_student_policy_version(
            "test-key-retpol-versn05", "RET-POL", "2026-10-01",
            "Owner re-affirms the mode", "placement_per_term")
        first, second = self.policy_doc.versions
        self.assertEqual(first["mode"], "placement_per_term")
        self.assertEqual(first["superseded_on"], "2026-10-01")
        self.assertNotIn("superseded_on", second)

    def test_retire_is_the_off_switch(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-20", "mode": "placement_per_term",
            "reason": "Owner enables placement-per-term returns",
            "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}])
        self.assertEqual(self.policies.governing_returning_mode(), "placement_per_term")
        result = self.policies.set_returning_student_policy_status(
            "test-key-retpol-status1", "RET-POL", 0)
        self.assertEqual(result["status"], "Retired")
        self.assertEqual(self.policies.governing_returning_mode(), "")
        self.policies.set_returning_student_policy_status(
            "test-key-retpol-status2", "RET-POL", 1)
        self.assertEqual(self.policies.governing_returning_mode(), "placement_per_term")

    def test_governing_read_fails_closed_without_policy_or_version(self):
        self.assertEqual(self.policies.governing_returning_mode(), "")
        self._existing_policy()
        self.assertEqual(self.policies.governing_returning_mode(), "")


class ReturningPolicyGateTests(unittest.TestCase):
    """Source-level receipt-gate parity with the S5 catalog commands."""

    def test_commands_route_through_the_receipted_gate(self):
        source = (APP / "admission/policies.py").read_text(encoding="utf-8")
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

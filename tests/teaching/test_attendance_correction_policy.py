"""S9 regression: the attendance-correction policy mechanism (OD-NEW-06).

The house holds exactly one attendance-correction policy; versions
carry the effective-dated owner choice of the D3 term pair —
``approver_role`` + ``correction_window_days``. Reads fail closed (no
row / retired / no effective version all resolve to {}); commands
route through the receipted Course Owner gate under their own kind.
Loads the REAL teaching attendance-corrections module with the REAL
academic + configuration rules against a scripted frappe stub; hosted
CI proves the correction journey.
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
    "create_attendance_correction_policy",
    "set_attendance_correction_policy_version",
    "set_attendance_correction_policy_status",
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


POLICY_CONTROLLERS = (
    APP / "academic/doctype/th_assessment_policy/th_assessment_policy.py",
    APP / "academic/doctype/th_program_level/th_program_level.py",
    APP / "admission/doctype/th_returning_student_policy/th_returning_student_policy.py",
    APP / "teaching/doctype/th_attendance_correction_policy/th_attendance_correction_policy.py",
    APP / "teaching/doctype/th_roster_change_policy/th_roster_change_policy.py",
    APP / "enrollment/doctype/th_enrollment_exit_policy/th_enrollment_exit_policy.py",
    APP / "finance/doctype/th_billing_policy/th_billing_policy.py",
    APP / "academic/doctype/th_catalog_linkage_policy/th_catalog_linkage_policy.py",
)


class AttendanceCorrectionPolicyTests(unittest.TestCase):
    def setUp(self):
        _install_command_harness(self)
    def _existing_policy(self, status="Active", versions=()):
        self.policy_rows = [{"name": "ATT-CORR-POL"}]
        self.policy_doc = _PolicyDoc(name="ATT-CORR-POL", code="ATT-CORR-POL",
                                     title="Correction rule", status=status,
                                     versions=[_Row(v) for v in versions])
        return self.policy_doc

    def _version(self, key, date, role="Teaching Auditor", days=7):
        return self.corrections.set_attendance_correction_policy_version(
            key, "ATT-CORR-POL", date,
            "Owner opens attendance corrections", role, days)

    def test_create_shell_carries_no_versions(self):
        result = self.corrections.create_attendance_correction_policy(
            "test-key-attcorr-create01", "ATT-CORR-POL", "Correction rule")
        self.assertEqual(result["code"], "ATT-CORR-POL")
        self.assertEqual(result["status"], "Active")
        self.assertEqual(result["version_count"], 0)
        self.assertEqual(result["governing_approver_role"], "")
        kind, _key, _payload = self.execute_calls[0]
        self.assertEqual(kind, "create_attendance_correction_policy")

    def test_second_policy_is_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self.corrections.create_attendance_correction_policy(
                "test-key-attcorr-create02", "ATT-CORR-TWO", "Second rule")
        self.assertIn("version it instead", str(ctx.exception))

    def test_version_append_governs_from_its_date(self):
        self._existing_policy()
        result = self._version("test-key-attcorr-versn01", "2026-09-23")
        self.assertEqual(result["version_count"], 1)
        # Not yet effective today: the shell still governs nothing.
        self.assertEqual(result["governing_approver_role"], "")
        self.assertEqual(self.corrections.governing_correction_terms(), {})
        self.today = "2026-09-23"
        self.assertEqual(self.corrections.governing_correction_terms(), {
            "effective_from": "2026-09-23",
            "approver_role": "Teaching Auditor", "window_days": 7})

    def test_unknown_approver_role_is_refused(self):
        self._existing_policy()
        self.role_exists = False
        with self.assertRaises(_ValidationError) as ctx:
            self._version("test-key-attcorr-versn02", "2026-09-23",
                          role="No Such Role")
        self.assertIn("Unknown approver role", str(ctx.exception))

    def test_bad_window_is_refused(self):
        self._existing_policy()
        with self.assertRaises(_ValidationError) as ctx:
            self._version("test-key-attcorr-versn03", "2026-09-23", days=-1)
        self.assertIn("Correction window", str(ctx.exception))

    def test_backdated_and_same_day_versions_refused(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-23", "approver_role": "Teaching Auditor",
            "correction_window_days": 7,
            "reason": "Owner opens attendance corrections",
            "set_by": ACTOR, "set_on": "2026-09-22 12:00:00"}])
        with self.assertRaises(_ValidationError):
            self._version("test-key-attcorr-versn04", "2026-09-20")
        with self.assertRaises(_ValidationError):
            self._version("test-key-attcorr-versn05", "2026-09-23")

    def test_superseded_version_is_closed_not_rewritten(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-23", "approver_role": "Teaching Auditor",
            "correction_window_days": 7,
            "reason": "Owner opens attendance corrections",
            "set_by": ACTOR, "set_on": "2026-09-22 12:00:00"}])
        self._version("test-key-attcorr-versn06", "2026-10-01",
                      role="Academic Manager", days=14)
        first, second = self.policy_doc.versions
        self.assertEqual(first["correction_window_days"], 7)
        self.assertEqual(first["superseded_on"], "2026-10-01")
        self.assertEqual(second["approver_role"], "Academic Manager")
        self.assertNotIn("superseded_on", second)

    def test_retire_is_the_off_switch(self):
        self._existing_policy(versions=[{
            "effective_from": "2026-09-20", "approver_role": "Teaching Auditor",
            "correction_window_days": 7,
            "reason": "Owner opens attendance corrections",
            "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}])
        self.assertEqual(
            self.corrections.governing_correction_terms()["approver_role"],
            "Teaching Auditor")
        result = self.corrections.set_attendance_correction_policy_status(
            "test-key-attcorr-status1", "ATT-CORR-POL", 0)
        self.assertEqual(result["status"], "Retired")
        self.assertEqual(self.corrections.governing_correction_terms(), {})
        self.corrections.set_attendance_correction_policy_status(
            "test-key-attcorr-status2", "ATT-CORR-POL", 1)
        self.assertEqual(
            self.corrections.governing_correction_terms()["window_days"], 7)

    def test_governing_read_fails_closed_without_policy_or_version(self):
        self.assertEqual(self.corrections.governing_correction_terms(), {})
        self._existing_policy()
        self.assertEqual(self.corrections.governing_correction_terms(), {})





def _install_command_harness(test):
    """Install the stub frappe plus REAL rules/command modules on test."""
    test.policy_rows = []
    test.policy_doc = None
    test.execute_calls = []
    test.today = "2026-09-22"
    test.role_exists = True
    previous = dict(sys.modules)
    test.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
    fake = test

    def get_all(doctype, fields=None, filters=None, limit=None, **kwargs):
        assert doctype == "TH Attendance Correction Policy"
        return list(fake.policy_rows)

    def get_value(doctype, name_or_filters, fieldname=None, **kwargs):
        if doctype == "TH Attendance Correction Policy":
            assert fake.policy_doc is not None
            return fake.policy_doc.name
        raise AssertionError(f"unexpected get_value {doctype}")

    def get_doc(doctype, name=None, for_update=False, **kwargs):
        if isinstance(doctype, dict):
            payload = dict(doctype)
            doc = _PolicyDoc(name=payload.get("code"), **payload)
            fake.policy_doc = doc
            return doc
        assert doctype == "TH Attendance Correction Policy"
        assert fake.policy_doc is not None
        return fake.policy_doc

    def exists(doctype, name):
        if doctype == "Role":
            return fake.role_exists
        if doctype == "TH Attendance Correction Policy":
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
    teaching_pkg = types.ModuleType("toefl_house.teaching")
    teaching_pkg.__path__ = [str(APP / "teaching")]
    from contextlib import nullcontext
    teaching_pkg._roster_read = nullcontext
    sys.modules["toefl_house.teaching"] = teaching_pkg
    test.corrections = _load_real(
        "toefl_house.teaching.attendance_corrections",
        APP / "teaching/attendance_corrections.py")
class AttendanceCorrectionPolicyGateTests(unittest.TestCase):
    """Source-level receipt-gate parity with the S5/S7/S8 policy commands."""

    def test_commands_route_through_the_receipted_gate(self):
        source = (APP / "teaching/attendance_corrections.py").read_text(encoding="utf-8")
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


class ControllerChildRowSemanticsTests(unittest.TestCase):
    """The policy CONTROLLER validates real child Documents, not dicts.

    The command-layer tests above run against dict doubles, which are
    subscriptable — so they could not see the row["superseded_on"]
    TypeError that the S9 hosted qualification caught on the first
    second-version append. These tests run the REAL controller
    validate against faithful non-subscriptable rows.
    """

    CONTROLLER = APP / ("teaching/doctype/th_attendance_correction_policy/"
                        "th_attendance_correction_policy.py")

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
            "toefl_house.teaching.doctype.th_attendance_correction_policy."
            "th_attendance_correction_policy", self.CONTROLLER)
        self.foundation = sys.modules["toefl_house.configuration.rules"]

    def _doc(self, versions):
        return _PolicyDoc(
            name="ATT-CORR-POL", code="ATT-CORR-POL", title="Correction rule",
            status="Active", versions=[_DocRow(**version) for version in versions])

    def _version(self, effective, superseded=None):
        row = {"effective_from": effective, "approver_role": "Teaching Auditor",
               "correction_window_days": 7,
               "reason": "Owner opens attendance corrections",
               "set_by": ACTOR, "set_on": "2026-09-19 12:00:00"}
        if superseded is not None:
            row["superseded_on"] = superseded
        return row

    def test_superseded_row_validates_without_subscript(self):
        doc = self._doc([self._version("2026-09-20", superseded="2026-09-23"),
                         self._version("2026-09-23")])
        with self.foundation.command_context(
                "set_attendance_correction_policy_version"):
            self.controller.validate(doc)

    def test_closed_date_before_effective_is_still_refused(self):
        doc = self._doc([self._version("2026-09-23", superseded="2026-09-20")])
        with self.foundation.command_context(
                "set_attendance_correction_policy_version"):
            with self.assertRaises(_ValidationError) as ctx:
                self.controller.validate(doc)
        self.assertIn("must fall after its effective date", str(ctx.exception))

    def test_validate_outside_a_command_is_refused_first(self):
        doc = self._doc([self._version("2026-09-23")])
        with self.assertRaises(_PermissionError):
            self.controller.validate(doc)


class PolicyControllerRowAccessTests(unittest.TestCase):
    """No policy controller may subscript a child row it iterates.

    before_save is the single exception: its rows come from
    frappe.db.get_all, which returns plain dicts on every backend.
    """

    def test_version_checks_read_rows_without_subscripts(self):
        for path in POLICY_CONTROLLERS:
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

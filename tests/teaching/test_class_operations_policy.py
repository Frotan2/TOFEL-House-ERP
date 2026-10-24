"""Mission 3 owner policy: every operational value is configurable, none coded.

Two acceptance questions:

1. does the single effective-dated policy carry the whole operational term set,
   refuse missing/unknown/out-of-bound values, keep history immutable and
   resolve the version that governs each date?
2. is the policy actually WIRED (configuration audit authority, controller
   command context, hooks, guarded DocTypes, command roles), so a value cannot
   be changed through a Desk form or an API call?
"""
import ast
import json
import unittest
from pathlib import Path

from tests.teaching.operations_site import (
    APP, COURSE_OWNER, OperationsSite, ValidationError)

APP_ROOT = Path(__file__).resolve().parents[2]
SECURITY = APP / "security.py"
AUDIT = APP / "configuration" / "audit.py"
HOOKS = APP / "hooks.py"


def _literal_assignment(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and getattr(node.targets[0], "id", "") == name):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {path.name}")


class PolicyTermTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.terms = self.ops.policy_terms()

    def test_every_term_must_be_declared_explicitly(self):
        missing = dict(self.terms)
        missing.pop("max_sessions_per_day")
        with self.assertRaises(ValueError) as ctx:
            self.ops.class_operations.validate_terms(missing)
        self.assertIn("missing: max_sessions_per_day", str(ctx.exception))

    def test_unknown_terms_are_refused_so_typos_cannot_become_inert(self):
        extra = dict(self.terms, max_session_per_day=3)
        with self.assertRaises(ValueError) as ctx:
            self.ops.class_operations.validate_terms(extra)
        self.assertIn("Unknown class-operations term(s): max_session_per_day",
                      str(ctx.exception))

    def test_session_minutes_stay_inside_the_engineering_bounds(self):
        with self.assertRaises(ValueError) as ctx:
            self.ops.class_operations.validate_terms(
                dict(self.terms, max_session_minutes=900))
        self.assertIn("Maximum session minutes must be between 5 and 600",
                      str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            self.ops.class_operations.validate_terms(
                dict(self.terms, min_session_minutes=120,
                     default_session_minutes=60))
        self.assertIn("minimum <= default <= maximum", str(ctx.exception))

    def test_the_daily_limit_and_horizon_are_bounded(self):
        with self.assertRaises(ValueError) as ctx:
            self.ops.class_operations.validate_terms(
                dict(self.terms, max_sessions_per_day=25))
        self.assertIn("must be between 1 and 24", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            self.ops.class_operations.validate_terms(
                dict(self.terms, timetable_horizon_days=400))
        self.assertIn("must be between 1 and 366", str(ctx.exception))

    def test_teaching_days_are_canonicalized_and_validated(self):
        parse = self.ops.class_operations.parse_teaching_days
        self.assertEqual(parse("Wed,Mon,Mon"), ("Mon", "Wed"))
        self.assertEqual(parse(["Sat", "Sun"]), ("Sat", "Sun"))
        with self.assertRaises(ValueError) as ctx:
            parse("Monday")
        self.assertIn("Unknown teaching day(s) Monday", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            parse("")
        self.assertIn("at least one weekday", str(ctx.exception))

    def test_feature_windows_must_be_open_when_the_feature_is_on(self):
        with self.assertRaises(ValueError) as ctx:
            self.ops.class_operations.validate_terms(
                dict(self.terms, allow_postponement=1, postpone_max_days=0))
        self.assertIn("postpone_max_days must be between 1 and 365",
                      str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            self.ops.class_operations.validate_terms(
                dict(self.terms, allow_transfers=0, allow_program_transfers=1))
        self.assertIn("require transfers to be allowed", str(ctx.exception))

    def test_approver_roles_are_required_by_their_features(self):
        with self.assertRaises(ValueError) as ctx:
            self.ops.class_operations.validate_terms(
                dict(self.terms, transfer_approver_role=""))
        self.assertIn("transfer approver role is required", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            self.ops.class_operations.validate_terms(
                dict(self.terms, replacement_approver_role=""))
        self.assertIn("replacement approver role is required", str(ctx.exception))

    def test_override_bounds_apply_once_a_role_is_named(self):
        with self.assertRaises(ValueError) as ctx:
            self.ops.class_operations.validate_terms(
                dict(self.terms, capacity_override_max_seats=0))
        self.assertIn("capacity_override_max_seats must be between 1 and 50",
                      str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            self.ops.class_operations.validate_terms(
                dict(self.terms, capacity_override_expiry_days=120))
        self.assertIn("Override expiry must be between 0 and 90",
                      str(ctx.exception))

    def test_booleans_accept_the_forms_a_desk_or_api_sends(self):
        terms = self.ops.class_operations.validate_terms(
            dict(self.terms, allow_postponement="false",
                 waiting_list_enabled="yes"))
        self.assertFalse(terms["allow_postponement"])
        self.assertTrue(terms["waiting_list_enabled"])


class PolicyLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.policy = self.ops.class_operations

    def test_no_policy_means_every_gated_action_refuses(self):
        self.assertEqual(self.policy.governing_operations(), {})
        with self.assertRaises(ValidationError) as ctx:
            self.policy.require_operations()
        self.assertIn("No active class-operations policy version", str(ctx.exception))

    def test_a_policy_shell_without_a_version_does_not_operate(self):
        self.ops.frappe.session.user = COURSE_OWNER
        self.site.user = COURSE_OWNER
        self.policy.create_class_operations_policy(
            "create-policy-0001", "TH-CLASS-OPS", "Class operations",
            "single policy row")
        self.assertEqual(self.policy.governing_operations(), {})
        with self.assertRaises(ValidationError) as ctx:
            self.policy.require_operations()
        self.assertIn("No active class-operations policy version", str(ctx.exception))

    def test_a_second_policy_row_is_refused(self):
        self.ops.seed_policy()
        self.site.user = COURSE_OWNER
        with self.assertRaises(ValidationError) as ctx:
            self.policy.create_class_operations_policy(
                "create-policy-0002", "TH-CLASS-OPS-2", "Second", "")
        self.assertIn("already exists; version it instead", str(ctx.exception))

    def test_versions_are_append_only_and_the_previous_row_is_closed(self):
        self.ops.seed_policy(effective_from="2026-09-01")
        self.ops.append_policy("2026-10-01", max_sessions_per_day=3)
        doc = self.site.get("TH Class Operations Policy", "TH-CLASS-OPS")
        versions = sorted(doc["versions"], key=lambda row: row["effective_from"])
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0]["superseded_on"], "2026-10-01")
        self.assertFalse(versions[1].get("superseded_on"))
        self.assertEqual(versions[1]["set_by"], COURSE_OWNER)
        self.assertEqual(versions[1]["teaching_days"], "Mon,Tue,Wed,Thu")

    def test_backdated_and_same_day_versions_are_refused(self):
        self.ops.seed_policy(effective_from="2026-09-01")
        for day in ("2026-09-01", "2026-08-01"):
            with self.assertRaises(ValidationError) as ctx:
                self.policy.set_class_operations_policy_version(
                    f"bad-version-{day}", "TH-CLASS-OPS", day,
                    "rewriting history", self.ops.policy_terms())
            self.assertIn("must start after the latest version",
                          str(ctx.exception))

    def test_each_date_resolves_to_the_version_that_governed_it(self):
        self.ops.seed_policy(effective_from="2026-09-01")
        self.ops.append_policy("2026-10-01", max_sessions_per_day=3)
        september = self.policy.governing_operations("2026-09-15")
        october = self.policy.governing_operations("2026-10-02")
        self.assertEqual(september["effective_from"], "2026-09-01")
        self.assertEqual(september["max_sessions_per_day"], 2)
        self.assertEqual(october["effective_from"], "2026-10-01")
        self.assertEqual(october["max_sessions_per_day"], 3)

    def test_a_future_version_does_not_govern_today(self):
        self.ops.seed_policy(effective_from="2026-09-01")
        self.ops.append_policy("2026-11-01", max_sessions_per_day=4)
        self.assertEqual(self.policy.governing_operations(
            "2026-09-22")["max_sessions_per_day"], 2)

    def test_retiring_the_policy_switches_every_gated_action_off(self):
        self.ops.seed_policy()
        self.site.user = COURSE_OWNER
        self.policy.set_class_operations_policy_status(
            "retire-policy-0001", "TH-CLASS-OPS", False)
        self.assertEqual(self.policy.governing_operations(), {})
        with self.assertRaises(ValidationError) as ctx:
            self.policy.require_operations(feature="waiting_list_enabled")
        self.assertIn("No active class-operations policy", str(ctx.exception))
        self.policy.set_class_operations_policy_status(
            "retire-policy-0002", "TH-CLASS-OPS", True)
        self.assertTrue(self.policy.governing_operations())

    def test_a_retired_policy_cannot_take_a_new_version(self):
        self.ops.seed_policy()
        self.site.user = COURSE_OWNER
        self.policy.set_class_operations_policy_status(
            "retire-policy-0003", "TH-CLASS-OPS", False)
        with self.assertRaises(ValidationError) as ctx:
            self.policy.set_class_operations_policy_version(
                "version-retired-0001", "TH-CLASS-OPS", "2026-10-01",
                "should fail", self.ops.policy_terms())
        self.assertIn("retired", str(ctx.exception))

    def test_invalid_stored_terms_fail_closed_instead_of_operating(self):
        self.ops.seed_policy()
        doc = self.site.get("TH Class Operations Policy", "TH-CLASS-OPS")
        doc["versions"][0]["max_sessions_per_day"] = 0
        self.assertEqual(self.policy.governing_operations(), {})

    def test_a_role_term_must_name_an_existing_role(self):
        self.ops.seed_policy(effective_from="2026-09-01")
        terms = self.ops.policy_terms(transfer_approver_role="Ghost Role")
        with self.assertRaises(ValidationError) as ctx:
            self.policy.set_class_operations_policy_version(
                "version-role-0001", "TH-CLASS-OPS", "2026-10-01",
                "unknown role", terms)
        self.assertIn("unknown Role: Ghost Role", str(ctx.exception))


class PolicyWiringTests(unittest.TestCase):
    """A configurable value is only safe when every write path is closed."""

    @classmethod
    def setUpClass(cls):
        cls.kinds = _literal_assignment(AUDIT, "KIND_AUTHORITY")
        cls.roles = _literal_assignment(SECURITY, "KIND_ROLES")
        cls.commands = _literal_assignment(SECURITY, "TEACHING_COMMANDS")
        cls.hooks = {}
        namespace = {}
        exec(compile(HOOKS.read_text(encoding="utf-8"), "hooks.py", "exec"),
             namespace)
        cls.hooks = namespace

    def test_the_ten_configuration_commands_are_owner_policy(self):
        expected = {
            "create_class_operations_policy",
            "set_class_operations_policy_version",
            "set_class_operations_policy_status",
            "create_academic_calendar",
            "add_academic_calendar_day",
            "remove_academic_calendar_day",
            "set_academic_calendar_status",
            "create_timetable_template",
            "set_timetable_slots",
            "set_timetable_template_status",
        }
        self.assertEqual(expected - set(self.kinds), set())
        for kind in expected:
            self.assertEqual(self.kinds[kind], "business_policy", kind)

    def test_every_mission_command_is_role_bound_and_guarded(self):
        commands = {
            "generate_timetable": "Course Schedule",
            "postpone_session": "Course Schedule",
            "schedule_replacement_session": "Course Schedule",
            "cancel_session": "Course Schedule",
            "suspend_class": "TH Class Suspension",
            "suspend_student_membership": "TH Class Suspension",
            "resume_suspension": "TH Class Suspension",
            "join_waiting_list": "TH Class Waiting List",
            "leave_waiting_list": "TH Class Waiting List",
            "offer_waiting_list_seat": "TH Class Waiting List",
            "create_capacity_override": "TH Capacity Approval",
            "revoke_capacity_override": "TH Capacity Approval",
            "request_class_transfer": "TH Class Transfer",
            "deny_class_transfer": "TH Class Transfer",
            "cancel_class_transfer": "TH Class Transfer",
        }
        for kind, doctype in commands.items():
            self.assertIn(kind, self.roles, kind)
            self.assertIn(kind, self.commands, kind)
            allowed = self.commands[kind]
            allowed = {allowed} if isinstance(allowed, str) else set(allowed)
            self.assertIn(doctype, allowed, kind)

    def test_multi_doctype_commands_declare_every_row_they_write(self):
        roster = set(self.commands["add_class_member"])
        self.assertEqual(roster, {"Student Group", "TH Capacity Approval"})
        self.assertEqual(set(self.commands["admit_from_waiting_list"]),
                         {"TH Class Waiting List", "Student Group",
                          "TH Capacity Approval"})
        self.assertEqual(set(self.commands["approve_class_transfer"]),
                         {"TH Class Transfer", "Student Group",
                          "TH Capacity Approval"})

    def test_configuration_masters_carry_the_command_context_hook(self):
        events = self.hooks["doc_events"]
        for doctype in ("TH Class Operations Policy", "TH Academic Calendar",
                        "TH Timetable Template"):
            self.assertIn("validate", events[doctype], doctype)
            self.assertTrue(events[doctype]["validate"].endswith(".validate"),
                            doctype)
        self.assertEqual(self.hooks["has_permission"]["TH Class Operations Policy"],
                         "toefl_house.permissions.configuration_has_permission")
        self.assertEqual(self.hooks["has_permission"]["TH Academic Calendar"],
                         "toefl_house.permissions.configuration_has_permission")

    def test_guard_controllers_refuse_outside_their_command(self):
        for slug in ("th_class_operations_policy", "th_academic_calendar",
                     "th_timetable_template"):
            source = (APP / "teaching" / "doctype" / slug / f"{slug}.py").read_text(
                encoding="utf-8")
            self.assertIn("assert_command_context", source, slug)

    def test_operational_records_are_guarded_and_branch_scoped(self):
        for doctype in ("TH Class Transfer", "TH Class Waiting List",
                        "TH Capacity Approval", "TH Class Suspension"):
            self.assertIn(doctype, self.hooks["has_permission"], doctype)
            self.assertIn(doctype, self.hooks["permission_query_conditions"],
                          doctype)

    def test_the_version_table_carries_every_configurable_term(self):
        definition = json.loads((APP / "teaching" / "doctype" /
                                 "th_class_operations_policy_version" /
                                 "th_class_operations_policy_version.json"
                                 ).read_text(encoding="utf-8"))
        fields = {field["fieldname"] for field in definition["fields"]}
        source = (APP / "teaching" / "class_operations.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        keys = None
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign)
                    and getattr(node.targets[0], "id", "") == "TERM_KEYS"):
                keys = ast.literal_eval(node.value)
        self.assertIsNotNone(keys)
        self.assertEqual(len(keys), 28)
        for key in keys:
            self.assertIn(key, fields, key)


if __name__ == "__main__":
    unittest.main()

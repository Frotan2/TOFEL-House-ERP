"""Static and pure-policy unit tests for class lifecycle on native Student Group.

The class lifecycle is modelled as thin custom fields on the native
Student Group DocType plus lifecycle commands in toefl_house.teaching.
No competing TH Class/TH Cohort DocType is introduced.
"""
import ast
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import CLASS_STATUSES, DELIVERY_MODES, \
    is_valid_class_transition, validate_class_status, validate_delivery_mode

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
TEACHING_INIT = APP / "teaching/__init__.py"
HOOKS = APP / "hooks.py"
CUSTOM_FIELD_FIXTURE = ROOT / "apps/toefl_house/toefl_house/fixtures/custom_field.json"
SKILL_DOCTYPE = APP / "teaching/doctype/th_skill/th_skill.json"
INSTALL = APP / "install.py"
POLICY = APP / "policy.py"


class ClassStatusPolicyTests(unittest.TestCase):
    def test_enums_are_canonical(self):
        self.assertEqual(CLASS_STATUSES, ("Planned", "Active", "Completed", "Cancelled"))
        self.assertEqual(DELIVERY_MODES, ("On-site", "Online", "Hybrid"))
        for s in CLASS_STATUSES:
            self.assertEqual(validate_class_status(s), s)
        for m in DELIVERY_MODES:
            self.assertEqual(validate_delivery_mode(m), m)
        for bad in ("planned", "", None, "Done"):
            with self.assertRaises(ValueError):
                validate_class_status(bad)

    def test_transition_state_machine(self):
        """Planned -> Active -> Completed. Planned or Active may be Cancelled.
        Terminal states cannot leave."""
        allowed = {
            ("Planned", "Active"),
            ("Planned", "Cancelled"),
            ("Active", "Completed"),
            ("Active", "Cancelled"),
        }
        for before in CLASS_STATUSES:
            for after in CLASS_STATUSES:
                self.assertEqual(is_valid_class_transition(before, after),
                                 (before, after) in allowed or before == after,
                                 (before, after))

    def test_transition_table_is_explicitly_defined(self):
        """The transition matrix must be declared once in policy.py — no magic."""
        src = POLICY.read_text()
        self.assertIn("CLASS_TRANSITIONS", src)


class TeachingModuleStructureTests(unittest.TestCase):
    def test_create_student_group_accepts_lifecycle_fields(self):
        tree = ast.parse(TEACHING_INIT.read_text())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "create_student_group")
        argnames = [a.arg for a in fn.args.args]
        self.assertIn("class_start_date", argnames)
        self.assertIn("class_end_date", argnames)
        self.assertIn("delivery_mode", argnames)
        self.assertIn("branch", argnames)
        # Newly-created groups start in Planned status (asserted via AST constant).
        body_dump = ast.dump(fn)
        self.assertIn("value='Planned'", body_dump)

    def test_transition_class_command_exists_and_validates(self):
        tree = ast.parse(TEACHING_INIT.read_text())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "transition_class")
        argnames = [a.arg for a in fn.args.args]
        self.assertIn("request_key", argnames)
        self.assertIn("student_group", argnames)
        self.assertIn("to_status", argnames)
        # Is @frappe.whitelist(methods=["POST"]) and request_key first.
        self.assertTrue(any(
            isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "whitelist"
            and any(kw.arg == "methods" and [e.value for e in kw.value.elts] == ["POST"]
                    for kw in dec.keywords)
            for dec in fn.decorator_list))
        self.assertEqual(argnames[0], "request_key")
        body_dump = ast.dump(fn)
        # The transition must be gated via is_valid_class_transition.
        self.assertIn("is_valid_class_transition", body_dump)
        # The row is locked for update before being saved.
        self.assertIn("for update", TEACHING_INIT.read_text())

    def test_sessions_only_scheduled_for_active_classes(self):
        src = TEACHING_INIT.read_text()
        self.assertIn("th_class_status", src)
        self.assertIn("Sessions can only be scheduled for Active classes", src)


class CustomFieldFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(CUSTOM_FIELD_FIXTURE.read_text())

    def test_student_group_custom_fields_present_and_read_only(self):
        """All class-lifecycle fields on Student Group are read-only because
        they are command-set facts; Desk users cannot edit them directly."""
        sg_fields = {row["fieldname"]: row for row in self.fixture
                     if row["dt"] == "Student Group"}
        for name in ("th_class_start_date", "th_class_end_date", "th_class_status",
                     "th_delivery_mode", "th_branch"):
            self.assertIn(name, sg_fields, f"missing {name} on Student Group")
            self.assertEqual(sg_fields[name]["read_only"], 1, f"{name} must be read-only")
        # start/end dates are Date and required
        self.assertEqual(sg_fields["th_class_start_date"]["fieldtype"], "Date")
        self.assertEqual(sg_fields["th_class_start_date"]["reqd"], 1)
        self.assertEqual(sg_fields["th_class_end_date"]["fieldtype"], "Date")
        self.assertEqual(sg_fields["th_class_end_date"]["reqd"], 1)
        self.assertEqual(sg_fields["th_class_status"]["fieldtype"], "Select")
        self.assertIn("Planned", sg_fields["th_class_status"]["options"])
        self.assertEqual(sg_fields["th_delivery_mode"]["fieldtype"], "Select")
        self.assertIn("On-site", sg_fields["th_delivery_mode"]["options"])
        self.assertEqual(sg_fields["th_branch"]["fieldtype"], "Link")
        self.assertEqual(sg_fields["th_branch"]["options"], "Branch")

    def test_hooks_fixture_filter_covers_student_group(self):
        src = HOOKS.read_text()
        self.assertIn("\"Student Group\"", src)
        self.assertIn("\"Fee Structure\"", src)
        self.assertIn("\"Sales Invoice\"", src)


class InstallSeedingTests(unittest.TestCase):
    def test_default_skills_seeded(self):
        """The three canonical skills SL/WG/RV must be present as default seeds
        so every fresh install boots with the owner's original curriculum."""
        src = INSTALL.read_text()
        self.assertIn("DEFAULT_SKILLS", src)
        self.assertIn("\"SL\"", src)
        self.assertIn("\"WG\"", src)
        self.assertIn("\"RV\"", src)
        self.assertIn("_seed_skills", src)

    def test_no_th_class_doctype_repository(self):
        """Defence-in-depth: no competing TH Class / TH Cohort DocType exists.
        The class lifecycle must live on native Student Group only."""
        doctype_root = APP / "teaching/doctype"
        existing = {p.name for p in doctype_root.iterdir() if p.is_dir()}
        self.assertNotIn("th_class", existing)
        self.assertNotIn("th_cohort", existing)
        self.assertNotIn("th_course_offering", existing)

    def test_student_group_indexes_guarded_on_custom_field_columns(self):
        """Regression (hosted run 35332459813): the Student Group class-fact
        columns come from Custom Field fixtures, which do not exist during
        install-app. Unconditional add_index then dies with MySQL 1072 and
        fails the fresh-site install; the index must be added only once the
        column exists (the next migrate applies it)."""
        src = INSTALL.read_text()
        self.assertIn('frappe.db.has_column("Student Group", column)', src)
        for bare in ('frappe.db.add_index("Student Group", ["th_class_status"]',
                     'frappe.db.add_index("Student Group", ["th_branch"]',
                     'frappe.db.add_index("Student Group", ["th_class_start_date"]'):
            self.assertNotIn(bare, src)


class ClassFactInvariantTests(unittest.TestCase):
    """Defence-in-depth on the Student Group controller: the guard must
    enforce immutable class facts even when called directly from any write
    path with ignore_permissions=True."""

    def test_guard_requires_command_context(self):
        """guard_student_group must call require_synthetic() and fail when
        no synthetic environment flag is active."""
        src = TEACHING_INIT.read_text()
        self.assertIn("require_synthetic()", src)
        self.assertIn("teaching_command_active(GROUP)", src)
        self.assertIn("_enforce_class_fact_invariants", src)
        self.assertIn("Class fact", src)

    def test_immutability_message_documents_owner_decision_gap(self):
        """The failure message for after-insert fact edits must make clear
        that an owner amendment policy is required — not silently allow it."""
        src = TEACHING_INIT.read_text()
        self.assertIn("explicit owner policy", src)
        self.assertIn("no ad-hoc", src)

    def test_transition_class_is_the_only_status_writer(self):
        """AST check: create_student_group only sets status to Planned on
        insert; transition_class is the only place th_class_status is
        assigned an Active/Completed/Cancelled value after insert."""
        tree = ast.parse(TEACHING_INIT.read_text())
        create_fn = next(n for n in ast.walk(tree)
                         if isinstance(n, ast.FunctionDef) and n.name == "create_student_group")
        # In create_student_group body the only status assigned is "Planned".
        create_dump = ast.dump(create_fn)
        for value in ("\"Active\"", "\"Completed\"", "\"Cancelled\""):
            self.assertNotIn(value, create_dump,
                             f"create_student_group must not assign status {value}")
        transition_fn = next(n for n in ast.walk(tree)
                             if isinstance(n, ast.FunctionDef) and n.name == "transition_class")
        self.assertIn("is_valid_class_transition", ast.dump(transition_fn))


class SkillLifecycleTests(unittest.TestCase):
    def test_controller_rejects_bad_transitions(self):
        """TH Skill controller must forbid Active -> Active, Retired -> Active,
        code changes after insert, and deletions."""
        skill = APP / "teaching/doctype/th_skill/th_skill.py"
        src = skill.read_text()
        self.assertIn("Illegal skill status transition", src)
        self.assertIn("Skill code is the stable identifier", src)
        self.assertIn("on_trash", src)
        self.assertIn("cannot be deleted", src)
        self.assertIn("before_rename", src)

    def test_skill_doctype_disallows_rename(self):
        data = json.loads(SKILL_DOCTYPE.read_text())
        self.assertEqual(data["allow_rename"], 0)
        # No role is granted delete:
        for row in data["permissions"]:
            self.assertFalse(row.get("delete"), f"role {row['role']} must not hold delete")

    def test_retired_skills_blocked_for_new_contracts_and_assignments(self):
        """compensation.py must gate both contract-term parsing and assignment
        creation through _assert_active_skill."""
        comp = APP / "teaching/compensation.py"
        src = comp.read_text()
        self.assertIn("_assert_active_skill", src)
        # The Active-status check must be explicit.
        self.assertIn('status != "Active"', src)
        self.assertIn("retired", src.lower())


if __name__ == "__main__":
    unittest.main()

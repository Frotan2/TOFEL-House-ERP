"""Pure local checks for the D2 teaching-compensation slice.

Covers the pure policy layer (contract validators, window overlap,
payable computation) and the static wiring (command roles, protected
doctypes, read-containment kinds, hooks coverage, doctype JSON shape).
Hosted runtime acceptance lives in tools/placement/native_checks.py.
"""
import ast
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import (ADJUSTMENT_TYPES, COMPENSATION_MODELS, TEACHING_SKILLS,
                                compute_skill_payable, validate_compensation_model,
                                validate_effective_window, validate_optional_amount,
                                validate_payable_quantity, validate_positive_amount,
                                validate_skill, windows_overlap)

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
SECURITY = APP / "security.py"
HOOKS = APP / "hooks.py"
COMPENSATION = APP / "teaching/compensation.py"
DOCTYPES = {
    "TH Instructor Contract": APP / "teaching/doctype/th_instructor_contract/th_instructor_contract.json",
    "TH Contract Skill Term": APP / "teaching/doctype/th_contract_skill_term/th_contract_skill_term.json",
    "TH Contract Adjustment": APP / "teaching/doctype/th_contract_adjustment/th_contract_adjustment.json",
    "TH Teaching Assignment": APP / "teaching/doctype/th_teaching_assignment/th_teaching_assignment.json",
}
COMMANDS = {
    "create_teaching_contract": "Finance Officer",
    "revise_teaching_contract": "Finance Officer",
    "assign_teaching_skill": "Teaching Scheduler",
    "end_teaching_assignment": "Teaching Scheduler",
    "calculate_teaching_compensation": "Finance Officer",
}


class SkillVocabularyTests(unittest.TestCase):
    def test_owner_skill_areas_only(self):
        self.assertEqual(TEACHING_SKILLS, ("Speaking & Listening", "Writing & Grammar",
                                           "Reading & Vocabulary"))
        for skill in TEACHING_SKILLS:
            self.assertEqual(validate_skill(skill), skill)
        for bad in ("speaking & listening", "Listening", "", None, 7):
            with self.assertRaises(ValueError):
                validate_skill(bad)

    def test_models_and_adjustment_types(self):
        self.assertEqual(COMPENSATION_MODELS, ("Fixed Salary", "Skill-Based", "Hybrid"))
        for model in COMPENSATION_MODELS:
            self.assertEqual(validate_compensation_model(model), model)
        with self.assertRaises(ValueError):
            validate_compensation_model("Per Class")
        self.assertEqual(ADJUSTMENT_TYPES, ("Bonus", "Deduction"))


class AmountTests(unittest.TestCase):
    def test_positive_bounded(self):
        self.assertEqual(validate_positive_amount(100, "Rate"), 100.0)
        self.assertEqual(validate_positive_amount(0.01, "Rate"), 0.01)
        for bad in (0, -1, True, "5", None, 10 ** 10):
            with self.assertRaises(ValueError):
                validate_positive_amount(bad, "Rate")

    def test_optional_amounts(self):
        for empty in (None, "", 0):
            self.assertIsNone(validate_optional_amount(empty, "Minimum"))
        self.assertEqual(validate_optional_amount(250, "Minimum"), 250.0)
        with self.assertRaises(ValueError):
            validate_optional_amount(-3, "Minimum")

    def test_payable_quantity(self):
        self.assertEqual(validate_payable_quantity(1), 1)
        self.assertEqual(validate_payable_quantity(10 ** 6), 10 ** 6)
        for bad in (0, -1, 2.5, True, "4", None, 10 ** 7):
            with self.assertRaises(ValueError):
                validate_payable_quantity(bad)


class WindowTests(unittest.TestCase):
    def test_effective_window(self):
        self.assertEqual(validate_effective_window("2026-01-01", ""), ("2026-01-01", None))
        self.assertEqual(validate_effective_window("2026-01-01", "2026-06-30"),
                         ("2026-01-01", "2026-06-30"))
        with self.assertRaises(ValueError):
            validate_effective_window("2026-06-30", "2026-01-01")
        with self.assertRaises(ValueError):
            validate_effective_window("01/01/2026", "")

    def test_overlap_truth_table(self):
        self.assertTrue(windows_overlap("2026-01-01", None, "2026-06-01", "2026-06-30"))
        self.assertTrue(windows_overlap("2026-01-01", "2026-12-31", "2026-12-31", None))
        self.assertFalse(windows_overlap("2026-01-01", "2026-06-30", "2026-07-01", None))
        self.assertFalse(windows_overlap("2026-07-01", None, "2026-01-01", "2026-06-30"))
        self.assertTrue(windows_overlap("2026-03-01", None, "2026-01-01", None))


class PayableTests(unittest.TestCase):
    def test_contract_terms_applied(self):
        self.assertEqual(compute_skill_payable(40, 12.5), 500.0)
        self.assertEqual(compute_skill_payable(40, 12.5, minimum=600), 600.0)
        self.assertEqual(compute_skill_payable(40, 12.5, maximum=450), 450.0)
        # two-decimal currency rounding is the only rounding applied
        self.assertEqual(compute_skill_payable(3, 33.333), 100.0)

    def test_bounds_rejected(self):
        with self.assertRaises(ValueError):
            compute_skill_payable(0, 10)
        with self.assertRaises(ValueError):
            compute_skill_payable(10, 0)
        with self.assertRaises(ValueError):
            compute_skill_payable(10, 10, minimum=500, maximum=100)


def _kind_roles():
    tree = ast.parse(SECURITY.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "KIND_ROLES":
            return {k.value: v.value for k, v in zip(node.value.keys, node.value.values)}
    raise AssertionError("KIND_ROLES missing")


def _doctypes_set():
    tree = ast.parse(SECURITY.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DOCTYPES":
            return {elt.value for elt in node.value.elts}
    raise AssertionError("DOCTYPES missing")


class WiringTests(unittest.TestCase):
    def test_command_roles(self):
        roles = _kind_roles()
        for kind, role in COMMANDS.items():
            self.assertEqual(roles.get(kind), role, kind)

    def test_protected_doctypes(self):
        doctypes = _doctypes_set()
        self.assertIn("TH Instructor Contract", doctypes)
        self.assertIn("TH Teaching Assignment", doctypes)

    def test_read_containment_hooks(self):
        hooks = HOOKS.read_text()
        for doctype in ("TH Instructor Contract", "TH Teaching Assignment"):
            self.assertIn(f'"{doctype}"', hooks)
        self.assertIn('("TH Instructor Contract", "contract")', hooks)
        self.assertIn('("TH Teaching Assignment", "assignment")', hooks)

    def test_commands_are_post_whitelisted_with_request_key(self):
        tree = ast.parse(COMPENSATION.read_text())
        seen = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in COMMANDS:
                decorated = any(
                    isinstance(dec, ast.Call)
                    and getattr(dec.func, "attr", "") == "whitelist"
                    and any(kw.arg == "methods" and [e.value for e in kw.value.elts] == ["POST"]
                            for kw in dec.keywords)
                    for dec in node.decorator_list)
                self.assertTrue(decorated, node.name)
                self.assertEqual(node.args.args[0].arg, "request_key", node.name)
                seen[node.name] = True
        self.assertEqual(set(seen), set(COMMANDS))

    def test_calculation_path_is_native_additional_salary_only(self):
        """The only doctypes the module ever creates are the two TH facts and
        the native Additional Salary payroll input — no slip/engine writes."""
        import re
        source = COMPENSATION.read_text()
        self.assertIn('ADDITIONAL_SALARY = "Additional Salary"', source)
        created = set()
        for match in re.finditer(r"doctype=([A-Z_]+|\"[^\"]+\")", source):
            created.add(match.group(1))
        self.assertLessEqual(created, {"ADDITIONAL_SALARY", "CONTRACT", "ASSIGNMENT"})
        self.assertIn("ADDITIONAL_SALARY", created)


class DocTypeShapeTests(unittest.TestCase):
    def test_json_shape(self):
        for name, path in DOCTYPES.items():
            data = json.loads(path.read_text())
            self.assertEqual(data["name"], name)
            self.assertEqual(data["module"], "Teaching")
            child = name in ("TH Contract Skill Term", "TH Contract Adjustment")
            self.assertEqual(bool(data.get("istable")), child, name)
            if child:
                self.assertEqual(data["permissions"], [])
            else:
                self.assertEqual(data["autoname"], "hash")
                for row in data["permissions"]:
                    self.assertNotIn("write", {k for k, v in row.items() if v == 1 and k != "role"},
                                     "no role may hold direct write")
            fields = {f["fieldname"] for f in data["fields"]}
            if name == "TH Instructor Contract":
                self.assertLessEqual(
                    {"instructor", "employee", "compensation_model", "assignment_basis",
                     "payment_frequency", "effective_start", "effective_end", "conditions",
                     "supersedes", "status", "skill_terms", "adjustments", "synthetic"}, fields)
            if name == "TH Teaching Assignment":
                self.assertLessEqual(
                    {"student_group", "skill", "instructor", "contract", "course_schedule",
                     "effective_start", "effective_end", "synthetic"}, fields)
            if name == "TH Contract Skill Term":
                self.assertLessEqual(
                    {"skill", "unit_of_payment", "rate", "payable_quantity",
                     "minimum_amount", "maximum_amount"}, fields)
            if name == "TH Contract Adjustment":
                self.assertLessEqual(
                    {"adjustment_type", "amount", "effective_date", "approver", "reason"}, fields)

    def test_skill_selects_use_owner_vocabulary(self):
        for name in ("TH Contract Skill Term", "TH Teaching Assignment"):
            data = json.loads(DOCTYPES[name].read_text())
            skill = next(f for f in data["fields"] if f["fieldname"] == "skill")
            self.assertEqual(skill["options"].split("\n"), list(TEACHING_SKILLS))

    def test_controller_invariants_wired(self):
        controllers = (APP / "controllers.py").read_text()
        self.assertIn('self.doctype == "TH Instructor Contract"', controllers)
        self.assertIn('self.doctype == "TH Teaching Assignment"', controllers)
        for doctype in ("TH Instructor Contract", "TH Teaching Assignment"):
            py = DOCTYPES[doctype].with_suffix("").with_name(
                DOCTYPES[doctype].stem + ".py").read_text()
            self.assertIn("ProtectedRecord", py)


if __name__ == "__main__":
    unittest.main()

"""The Course Owner configures grades with numbers, not JSON or source edits."""
import ast
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "toefl_house"))
from toefl_house.setup_presets.preset import load_preset
from toefl_house.setup_presets.assessment_facets import build_assessment_facets

SOURCE = (ROOT / "apps/toefl_house/toefl_house/setup_presets/owner_policy_forms.py")


def build():
    module = ast.parse(SOURCE.read_text(encoding="utf-8"))
    functions = [n for n in module.body
                 if isinstance(n, ast.FunctionDef)
                 and n.name in ("initial_assessment_values", "whole_number",
                                "graded_template_family_codes")]
    assert len(functions) == 3
    context = {"load_preset": load_preset, "build_assessment_facets": build_assessment_facets,
               "Decimal": Decimal, "InvalidOperation": InvalidOperation}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"),
         context)
    return context["initial_assessment_values"]


class HumanAcademicSetupTests(unittest.TestCase):
    def test_ge_eap_are_initialized_from_scalar_numbers_only(self):
        create = build()
        for family in ("GEN-ENG", "EAP"):
            with self.subTest(family=family):
                facets = create(family, f"{family}-ASSESS-01", 60, 7)
                self.assertEqual(len(facets), 7)
                self.assertEqual(facets["pass_rules"]["overall"],
                                 {"kind": "percent", "value": 60})
                self.assertEqual(facets["retakes"]["wait_days"], 7)
                self.assertEqual(facets["retakes"]["max_attempts"], 2)
                self.assertEqual(facets["retakes"]["governing"], "best")
                self.assertEqual(sum(row["weight"] for row in facets["weights"]), 100)
                self.assertIn(f"{family}-ASSESS-01",
                              [row["policy"] for row in
                               facets["progression"]["requires"]
                               if row["kind"] == "assessment_pass"])

    def test_new_owner_numbers_change_policy_not_source_code(self):
        create = build()
        newer = create("GEN-ENG", "GEN-ENG-ASSESS-02", "65.0", 10.0)
        self.assertEqual(newer["pass_rules"]["overall"]["value"], 65)
        self.assertEqual(newer["retakes"]["wait_days"], 10)
        old = create("GEN-ENG", "GEN-ENG-ASSESS-01", 60, 7)
        self.assertEqual(old["pass_rules"]["overall"]["value"], 60)
        self.assertEqual(old["retakes"]["wait_days"], 7)

    def test_invalid_numeric_values_are_not_applied(self):
        create = build()
        for bad_pass, bad_wait in (
            (0, 7), (101, 7), ("60.5", 7), (True, 7),
            (60, 6), (60, 366), (60, "7.5"), (60, False),
        ):
            with self.subTest(pass_score=bad_pass, wait_days=bad_wait):
                with self.assertRaises(ValueError):
                    create("EAP", "EAP-ASSESS-01", bad_pass, bad_wait)

    def test_skill_weights_are_validated_and_sum_to_exactly_100(self):
        module = ast.parse(SOURCE.read_text(encoding="utf-8"))
        selected = [n for n in module.body if isinstance(n, ast.FunctionDef)
                    and n.name in ("whole_number", "numeric_skill_distribution")]
        self.assertEqual(len(selected), 2)
        namespace = {
            "Decimal": Decimal, "InvalidOperation": InvalidOperation,
            "SKILL_PREFIX": {
                "speaking": "SPK", "listening": "LST", "writing": "WRT",
                "reading": "RDG", "grammar": "GRM", "vocabulary": "VOC",
            },
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]),
                     str(SOURCE), "exec"), namespace)
        calculate = namespace["numeric_skill_distribution"]
        rows = calculate(25, 20, 20, 15, 10, 10, 40)
        self.assertEqual(len(rows), 12)
        self.assertEqual(sum(row["weight"] for row in rows), 100)
        self.assertEqual(next(row["weight"] for row in rows
                              if row["component"] == "SPK-CA"), 10)
        self.assertEqual(next(row["weight"] for row in rows
                              if row["component"] == "SPK-FINAL"), 15)
        self.assertEqual(sum(row["weight"] for row in rows
                             if row["component"].endswith("-CA")), 40)
        self.assertEqual(sum(row["weight"] for row in rows
                             if row["component"].endswith("-FINAL")), 60)
        revised = calculate(20, 20, 20, 20, 10, 10, 30)
        self.assertEqual(sum(row["weight"] for row in revised
                             if row["component"].endswith("-CA")), 30)
        for invalid in (
            (25, 20, 20, 15, 10, 9, 40),
            (25, 20, 20, 15, 10, 10, 0),
            (25, 20, 20, 15, 10, 10, 100),
            (25, 20, 20, 15, -10, 30, 40),
            (25, 20, 20, 15, 10.5, 9.5, 40),
        ):
            with self.subTest(values=invalid), self.assertRaises(ValueError):
                calculate(*invalid)

    def test_no_code_weight_editor_is_guarded_and_versioned(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("def revise_grading_weights(", source)
        self.assertIn("skill_weights=weights", source)
        self.assertIn("_owner()", source)
        academic = (ROOT / "apps/toefl_house/toefl_house/academic/__init__.py").read_text(
            encoding="utf-8")
        self.assertIn("if skill_weights is not None:", academic)
        self.assertIn('carried["weights"] = rules.canonical_facet(', academic)
        self.assertIn("configuration_rules.check_appends(", academic)

    def test_specialist_courses_refuse_grade_based_promotion(self):
        create = build()
        for family in ("SPECIAL-SPEAKING", "TOEFL-PREP", "UNKNOWN"):
            with self.subTest(family=family), self.assertRaises(ValueError):
                create(family, "UNKNOWN-ASSESS-01", 60, 7)

    def test_backend_preserves_native_authority_and_existing_version_history(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('@frappe.whitelist(methods=["POST"])', source)
        self.assertIn("_owner()", source)
        self.assertIn("docstatus", source)
        self.assertIn("academic.set_assessment_policy_version(", source)
        self.assertNotIn("ignore_permissions=True", source)
        self.assertNotIn("frappe.db.commit(", source)

    def test_gui_offers_numbers_not_grading_json_to_owner(self):
        js = (ROOT / "apps/toefl_house/toefl_house/public/js/th_role_desks.js").read_text(
            encoding="utf-8")
        desk = (ROOT / "apps/toefl_house/toefl_house/desk/setup.py").read_text(
            encoding="utf-8")
        self.assertIn('fieldname: "grade_a"', js)
        self.assertIn('fieldname: "grade_d"', js)
        self.assertIn('fieldname: "passing_score"', js)
        self.assertIn('fieldname: "retake_wait_days"', js)
        self.assertIn("args.intervals = JSON.stringify(", js)
        self.assertNotIn("Grade thresholds (prefilled JSON", js)
        self.assertIn("Set up grading (simple form)", desk)


if __name__ == "__main__":
    unittest.main()

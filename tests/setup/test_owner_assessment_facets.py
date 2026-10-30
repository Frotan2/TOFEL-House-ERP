"""The generated academic facets must pass the real Frappe-free validator."""
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
sys.path.insert(0, str(APP_ROOT))

# D2: academic/rules is pure, but the toefl_house.academic package
# __init__ imports frappe. Register a stub academic package pointing
# at the real directory so only rules loads, then restore the
# previous entry (the imported module stays bound).
import types as _types  # noqa: E402
_previous_academic = sys.modules.get("toefl_house.academic")  # noqa: E402
_academic = _types.ModuleType("toefl_house.academic")  # noqa: E402
_academic.__path__ = [str(APP_ROOT / "toefl_house" / "academic")]
sys.modules["toefl_house.academic"] = _academic
from toefl_house.academic import rules  # noqa: E402
from toefl_house.setup_presets.assessment_facets import (  # noqa: E402
    build_assessment_facets,
)
from toefl_house.setup_presets.preset import load_preset  # noqa: E402
if _previous_academic is None:
    sys.modules.pop("toefl_house.academic", None)
else:
    sys.modules["toefl_house.academic"] = _previous_academic


class TestProposedAssessmentFacets(unittest.TestCase):
    def test_all_programs_pass_native_pure_facet_validation(self):
        for program in (p["code"] for p in load_preset()["programs"]):
            with self.subTest(program=program):
                facets = build_assessment_facets(program)
                clean = rules.validate_policy_facets(facets)
                self.assertEqual(sum(row["weight"] for row in clean["weights"]), 100)
                if program in ("GEN-ENG", "EAP"):
                    self.assertEqual(set(clean), set(rules.ASSESSMENT_FACETS))
                    self.assertEqual(clean["pass_rules"]["overall"]["value"], 60)
                    self.assertEqual(clean["progression"]["requires"][1]["role"],
                                     "Academic Manager")
                    self.assertEqual(clean["retakes"]["max_attempts"], 2)
                    self.assertEqual(clean["retakes"]["wait_days"], 7)
                    self.assertEqual(clean["retakes"]["governing"], "best")
                else:
                    self.assertNotIn("pass_rules", clean)
                    self.assertNotIn("progression", clean)
                    self.assertNotIn("retakes", clean)

    def test_general_english_covers_five_levels(self):
        facets = build_assessment_facets("GEN-ENG")
        self.assertEqual(len(facets["components"]), 12)
        self.assertEqual(len(facets["weights"]), 12)
        self.assertEqual(facets["level_mapping"]["levels"], [
            "PRE-STARTER", "STARTER", "PREP-1", "PREP-2", "PREP-3"])

    def test_speaking_specialization_and_concurrent_program(self):
        facets = build_assessment_facets("SPECIAL-SPEAKING")
        self.assertEqual({c["code"] for c in facets["components"]},
                         {"SPK-CA", "SPK-FINAL"})
        self.assertEqual([w["weight"] for w in facets["weights"]], [40, 60])

    def test_toefl_assesses_four_skills_not_official_toefl_score(self):
        facets = build_assessment_facets("TOEFL-PREP")
        self.assertEqual(len(facets["components"]), 8)
        self.assertEqual(len(facets["weights"]), 8)
        self.assertEqual(sum(w["weight"] for w in facets["weights"]
                             if w["component"].endswith("-CA")), 40)
        self.assertEqual(sum(w["weight"] for w in facets["weights"]
                             if w["component"].endswith("-FINAL")), 60)

    def test_specialist_courses_never_generate_automatic_pass_fail_or_promotion(self):
        preset = load_preset()
        for family in preset["programs"]:
            if family["progression_kind"] == "sequential":
                continue
            with self.subTest(code=family["code"]):
                facets = build_assessment_facets(family["code"], preset)
                self.assertNotIn("pass_rules", facets)
                self.assertNotIn("progression", facets)
                self.assertNotIn("retakes", facets)

    def test_unknown_program_refused(self):
        with self.assertRaises(ValueError):
            build_assessment_facets("UNKNOWN")


if __name__ == "__main__":
    unittest.main()

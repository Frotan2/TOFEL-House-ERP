"""The generated academic facets must pass the real Frappe-free validator."""
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
sys.path.insert(0, str(APP_ROOT))

from toefl_house.academic import rules  # noqa: E402
from toefl_house.setup_presets.assessment_facets import (  # noqa: E402
    build_assessment_facets,
)
from toefl_house.setup_presets.preset import load_preset  # noqa: E402


class TestProposedAssessmentFacets(unittest.TestCase):
    def test_all_programs_pass_native_pure_facet_validation(self):
        for program in (p["code"] for p in load_preset()["programs"]):
            with self.subTest(program=program):
                facets = build_assessment_facets(program)
                clean = rules.validate_policy_facets(facets)
                self.assertEqual(set(clean), set(rules.ASSESSMENT_FACETS))
                self.assertEqual(sum(row["weight"] for row in clean["weights"]), 100)
                self.assertEqual(clean["pass_rules"]["overall"]["value"], 65)
                self.assertEqual(clean["progression"]["requires"][1]["role"],
                                 "Academic Manager")

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

    def test_unknown_program_refused(self):
        with self.assertRaises(ValueError):
            build_assessment_facets("UNKNOWN")


if __name__ == "__main__":
    unittest.main()

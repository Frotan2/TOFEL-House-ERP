"""Offline safety tests for the TOEFL House setup preset (no Frappe site)."""
import copy
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
sys.path.insert(0, str(APP_ROOT))

from toefl_house.setup_presets.preset import (  # noqa: E402
    load_preset, preview_catalog, validate_preset,
)


class TestInitialSetupPreset(unittest.TestCase):
    def setUp(self):
        self.preset = load_preset()

    def test_has_four_programs_eleven_levels(self):
        self.assertEqual(len(self.preset["programs"]), 4)
        self.assertEqual(sum(len(p["levels"]) for p in self.preset["programs"]), 11)

    def test_pre_starter_and_toefl_fees(self):
        all_levels = {level["code"]: level for p in self.preset["programs"]
                      for level in p["levels"]}
        self.assertEqual((all_levels["PRE-STARTER"]["duration_months"],
                          all_levels["PRE-STARTER"]["semester_tuition_afn"]), (1, 500))
        self.assertEqual((all_levels["TOEFL-PREP-4M"]["duration_months"],
                          all_levels["TOEFL-PREP-4M"]["semester_tuition_afn"]), (4, 7000))
        self.assertEqual(all_levels["EAP-3"]["semester_tuition_afn"], 2000)
        self.assertEqual(all_levels["PREP-2"]["semester_tuition_afn"], 1000)

    def test_continuous_and_final_are_40_60(self):
        assessment = self.preset["assessment"]
        self.assertEqual(sum(assessment["skills_weight_percent"].values()), 100)
        self.assertEqual(sum(assessment["continuous_subweights_percent"].values()), 40)
        self.assertEqual(assessment["final_exam_percent"], 60)

    def test_no_auto_enable_tax_backup_or_discounts(self):
        self.assertFalse(self.preset["backup"]["enabled"])
        self.assertFalse(self.preset["tax"]["enabled_for_student_fee_billing"])
        self.assertTrue(self.preset["discounts"]["templates_are_inactive_by_default"])
        self.assertTrue(self.preset["discounts"]["hundred_percent_only_student_specific"])

    def test_online_one_to_one_monthly_student_fee_not_instructor_salary(self):
        online = self.preset["online_one_to_one"]
        self.assertEqual(online["teacher_student_ratio"], "1:1")
        tuition = online["tuition"]
        self.assertEqual(tuition["period"], "one_calendar_month")
        self.assertTrue(tuition["separate_from_on_site_semester_fee_structure"])
        self.assertTrue(tuition["needs_owner_approved_student_contract"])
        self.assertEqual(tuition["suggested_monthly_afn"]["general_english"], 5000)
        self.assertEqual(tuition["suggested_monthly_afn"]["eap_min"], 6000)
        self.assertEqual(tuition["suggested_monthly_afn"]["eap_max"], 7000)
        self.assertEqual(tuition["suggested_monthly_afn"]["toefl_preparation"], 9000)
        self.assertTrue(online["instructor_pay"]["no_payroll_posting_during_setup"])
        self.assertTrue(online["instructor_pay"][
            "never_derive_payroll_automatically_from_student_tuition"])
        self.assertTrue(online["financial_controls"]["no_auto_invoice_without_contract_and_authorization"])

    def test_reject_online_monthly_fee_reclassified_as_semester(self):
        altered = copy.deepcopy(self.preset)
        altered["online_one_to_one"]["tuition"]["period"] = "one_semester"
        with self.assertRaisesRegex(ValueError, "monthly student tuition"):
            validate_preset(altered)

    def test_reject_online_payroll_derived_from_student_fee(self):
        altered = copy.deepcopy(self.preset)
        altered["online_one_to_one"]["instructor_pay"][
            "never_derive_payroll_automatically_from_student_tuition"] = False
        with self.assertRaisesRegex(ValueError, "authorized payroll"):
            validate_preset(altered)

    def test_reject_online_invoice_without_contract_approval(self):
        altered = copy.deepcopy(self.preset)
        altered["online_one_to_one"]["financial_controls"][
            "no_auto_invoice_without_contract_and_authorization"] = False
        with self.assertRaisesRegex(ValueError, "payroll controls"):
            validate_preset(altered)

    def test_reject_duplicate_level_code(self):
        duplicate = copy.deepcopy(self.preset)
        duplicate["programs"][1]["levels"][0]["code"] = "PRE-STARTER"
        with self.assertRaisesRegex(ValueError, "Duplicate level"):
            validate_preset(duplicate)

    def test_reject_unauthorized_automatic_tax(self):
        changed = copy.deepcopy(self.preset)
        changed["tax"]["enabled_for_student_fee_billing"] = True
        with self.assertRaisesRegex(ValueError, "tax and backup"):
            validate_preset(changed)

    def test_reject_blanket_discount(self):
        changed = copy.deepcopy(self.preset)
        changed["discounts"]["templates_are_inactive_by_default"] = False
        with self.assertRaisesRegex(ValueError, "discount"):
            validate_preset(changed)

    def test_no_site_mutation_on_preview(self):
        state = {"programs": {}, "levels": {}, "years": {},
                 "fee_categories": [], "tuition": {}}
        copy_before = copy.deepcopy(state)
        result = preview_catalog(state, self.preset)
        self.assertEqual(state, copy_before)
        self.assertFalse(result["ready_to_apply"])
        self.assertEqual(result["counts"]["create"], 28)
        self.assertEqual(result["counts"]["review"], 0)

    def test_existing_mismatched_level_requires_review(self):
        state = {"programs": {"GEN-ENG": {"title": "General English"}},
                 "levels": {"PRE-STARTER": {
                     "title": "Pre-Starter", "family": "GEN-ENG",
                     "duration_months": 2}},
                 "tuition": {"PRE-STARTER": {"1405": 800}}}
        result = preview_catalog(state, self.preset)
        issues = {action["code"] for action in result["actions"]
                  if action["status"] == "review"}
        self.assertIn("PRE-STARTER", issues)
        self.assertIn("PRE-STARTER@1405", issues)

    def test_legacy_level_code_never_leads_to_duplicate_program(self):
        state = {"programs": {"GEN-ENG": {"title": "General English"}},
                 "levels": {"PREP-ONE": {
                     "title": "Prep 1", "family": "GEN-ENG",
                     "duration_months": 2}},
                 "tuition": {"PREP-ONE": {"1405": 1000}}}
        result = preview_catalog(state, self.preset)
        steps = [row for row in result["actions"] if row["code"] in
                 ("PREP-1", "PREP-1@1405")]
        self.assertEqual({row["status"] for row in steps}, {"review"})
        self.assertIn("PREP-ONE", steps[0]["details"])
        self.assertFalse(result["ready_to_apply"])

    def test_wrong_native_next_level_blocks_automatic_setup(self):
        state = {"programs": {"GEN-ENG": {"title": "General English",
                                          "status": "Active"}},
                 "levels": {"STARTER": {
                     "title": "Starter", "family": "GEN-ENG",
                     "duration_months": 2, "native_program": "EDU-PROGRAM",
                     "status": "Active", "next_level": "PREP-2"}}}
        result = preview_catalog(state, self.preset)
        problem = next(row for row in result["actions"]
                       if row["kind"] == "level" and row["code"] == "STARTER")
        self.assertEqual(problem["status"], "review")

    def test_missing_native_program_anchor_is_not_match(self):
        state = {"levels": {"PRE-STARTER": {
            "title": "Pre-Starter", "family": "GEN-ENG",
            "duration_months": 1, "native_program": "",
            "status": "Active", "next_level": "STARTER"}}}
        result = preview_catalog(state, self.preset)
        problem = next(row for row in result["actions"]
                       if row["kind"] == "level" and row["code"] == "PRE-STARTER")
        self.assertEqual(problem["status"], "review")

    def test_retired_program_cannot_be_treated_as_ready(self):
        result = preview_catalog({"programs": {"GEN-ENG": {
            "title": "General English", "status": "Retired"}}}, self.preset)
        problem = next(row for row in result["actions"]
                       if row["kind"] == "program" and row["code"] == "GEN-ENG")
        self.assertEqual(problem["status"], "review")

    def test_alias_conflict_is_invalid(self):
        changed = copy.deepcopy(self.preset)
        changed["programs"][0]["levels"][2]["existing_site_aliases"] = ["STARTER"]
        with self.assertRaisesRegex(ValueError, "alias conflicts"):
            validate_preset(changed)

    def test_history_and_live_finance_are_not_updated(self):
        result = preview_catalog({"programs": {}}, self.preset)
        self.assertEqual(result["mode"], "READ_ONLY_PREVIEW")
        self.assertIn("Windows backup and isolated restore acceptance",
                      result["pending_decisions"])


if __name__ == "__main__":
    unittest.main()

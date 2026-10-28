"""Decision reconciliation tests: user-approved facts vs safe first-run preset.

These tests do not create actual Fee, Student, Salary Slip, tax,
backup or other operational records.  The canonical owner decisions remain
historical, and the addendum is a qualified, explicit supersession only.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / "apps" / "toefl_house"
sys.path.insert(0, str(APP_ROOT))

from toefl_house.setup_presets.assessment_facets import (  # noqa: E402
    build_assessment_facets,
)
from toefl_house.setup_presets.preset import (  # noqa: E402
    load_preset, validate_preset,
)


class Approved20261028DecisionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preset = load_preset()
        cls.owner = json.loads((ROOT / "docs" / "owner-decisions.json").read_text(
            encoding="utf-8"))["owner_policy_addenda_2026_10_28"]

    def test_pass_and_grading_agree_with_recorded_owner_authority(self):
        approved = self.owner["academic"]
        assessed = self.preset["assessment"]
        self.assertEqual(assessed["overall_pass_percent"],
                         approved["pass_threshold_pct"])
        thresholds = {r["grade"]: r["min_percent"] for r in
                      assessed["grading_scale"]["grade_thresholds"]}
        self.assertEqual(thresholds,
                         approved["grading_scale_proposed_by_engineer_and_owner_delegated"])
        self.assertEqual(assessed["continuous_subweights_percent"],
                         approved["marks"]["continuous_breakdown"])
        self.assertEqual(assessed["continuous_percent"], 40)
        self.assertEqual(assessed["final_exam_percent"], 60)

    def test_retakes_are_capped_at_one_repeat_and_best_outcome_proposed(self):
        approved = self.owner["academic"]["retake"]
        retake = self.preset["assessment"]["retake"]
        self.assertEqual(retake["max_total_attempts"], approved["max_total_attempts"])
        self.assertEqual(retake["wait_days"], approved["wait_days_min"])
        self.assertEqual(retake["governing"], approved["governing_selection"])
        self.assertTrue(retake["never_replace_original_mark"])

    def test_paid_paper_and_speaking_placement_are_explicit(self):
        policy = self.preset["assessment"]["placement"]
        self.assertEqual(policy["fee_afn_per_attempt"],
                         self.owner["academic"]["placement"]["fee_afn"])
        self.assertTrue(policy["paper_exam_component"])
        self.assertTrue(policy["face_to_face_speaking_component"])
        self.assertTrue(policy["payment_required_before_assessment"])
        self.assertTrue(policy["receipt_via_native_education_and_finance"])

    def test_no_late_join_pro_rata_or_automatic_discounts(self):
        billing = self.preset["fee_policy"]
        self.assertTrue(billing["late_join_full_original_course_fee"])
        self.assertTrue(billing["no_automatic_prorating_for_late_join"])
        self.assertTrue(billing["installment_amounts_must_sum_to_net_tuition"])
        self.assertTrue(billing["installment_engine_must_support_unequal_approved_installments"])
        self.assertEqual(billing["payment_grace_days"], 5)
        self.assertTrue(self.preset["discounts"]["templates_are_inactive_by_default"])

    def test_discount_approvers_and_staff_relatives_are_not_expanded(self):
        matrix = self.preset["discounts"]["approval_matrix"]
        self.assertEqual(matrix["pct_5_10_15_20"], "General Manager")
        self.assertEqual(matrix["pct_50"], "Course Owner")
        self.assertEqual(matrix["pct_100"], "Course Owner")
        family = self.preset["discounts"]["staff_family_full_waiver_relationships"]
        self.assertEqual(set(family), {"spouse", "children", "parents"})
        self.assertIn("siblings", self.preset["discounts"][
            "staff_family_full_waiver_excluded_relationships"])

    def test_same_level_transfers_and_refunds_do_not_bypass_approval(self):
        classes = self.preset["class_operations"]
        self.assertEqual((classes["configurable_capacity_min"],
                          classes["configurable_capacity_max"]), (15, 30))
        self.assertEqual(classes["transfer_authorizer"], "Academic Manager")
        self.assertTrue(classes["transfer_requires_separate_d5_supersession_and_live_permissions"])
        refunds = self.preset["refunds"]
        self.assertEqual(refunds["approve_refund_role"], "General Manager")
        self.assertEqual(refunds["execute_native_refund_role"], "Finance Manager")
        self.assertEqual(refunds["refund_amount_and_eligibility_formula_status"],
                         "APPROVED_CASE_BY_CASE_GENERAL_MANAGER")
        self.assertTrue(refunds["cumulative_refunds_cannot_exceed_actual_collections"])
        self.assertTrue(refunds["approver_and_payer_must_be_different_people"])
        self.assertTrue(refunds["no_auto_payout_on_approval"])
        self.assertTrue(refunds["live_workflow_is_not_enabled_by_this_preset"])

    def test_online_tuition_renews_from_individual_start_not_first_of_month(self):
        tuition = self.preset["online_one_to_one"]["tuition"]
        self.assertEqual(tuition["period"], "one_calendar_month")
        self.assertIn("individual start date", tuition["contract_month_basis"])
        self.assertEqual(self.preset["tax"]["legal_entity_type"], "natural_person")
        self.assertFalse(self.preset["tax"]["enabled_for_student_fee_billing"])
        self.assertFalse(self.preset["backup"]["enabled"])

    def test_official_name_matches_owner_confirmed_license_spelling(self):
        org = self.preset["institution"]
        self.assertEqual(org["legal_display_name_supplied"], "The TOEFL House")
        self.assertEqual(org["dari_display_name"], "خانه موفقیت")
        self.assertTrue(org["official_english_name_owner_confirmed"])
        self.assertEqual(self.owner["tax_legal_identity"]["english_name_supplied"],
                         "The TOEFL House")
        self.assertTrue(org["production_company_must_be_verified_from_license"])

    def test_refunds_remain_separate_from_book_credit_notes(self):
        refund = self.owner["student_operations"]["refund"]
        self.assertEqual(refund["approving_role"], "General Manager")
        self.assertEqual(refund["paying_role"], "Finance Manager")
        self.assertFalse(refund["owner_approval_ordinary_case"])
        self.assertEqual(refund["amount_eligibility_and_refund_window"],
                         "CASE_BY_CASE_GENERAL_MANAGER_APPROVAL_NO_FIXED_AUTO_REFUND_WINDOW")
        self.assertTrue(refund["approved_refund_cannot_exceed_unreturned_verified_paid_amount"])

    def test_specialist_courses_no_mandatory_progression(self):
        for program in self.preset["programs"]:
            if program["progression_kind"] == "sequential":
                continue
            facets = build_assessment_facets(program["code"], self.preset)
            self.assertNotIn("pass_rules", facets)
            self.assertNotIn("progression", facets)
            self.assertNotIn("retakes", facets)

    def test_conflicting_thresholds_rejected(self):
        import copy
        changed = copy.deepcopy(self.preset)
        changed["assessment"]["grading_scale"]["grade_thresholds"][3][
            "min_percent"] = 65
        with self.assertRaisesRegex(ValueError, "pass-grade threshold"):
            validate_preset(changed)

    def test_original_deferred_releases_not_silently_authorized(self):
        self.assertEqual(self.owner["release"]["production_status"],
                         "HOLD_UNTIL_NATIVE_WINDOWS_FINANCE_RECOVERY_INDEPENDENT_ACCEPTANCE")
        self.assertFalse(self.owner["release"]["modifies_main"])


if __name__ == "__main__":
    unittest.main()

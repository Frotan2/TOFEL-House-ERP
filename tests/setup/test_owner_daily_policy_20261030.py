"""Owner-approved current daily setup contracts, not production activation.

These offline checks prevent an old candidate preset from silently bringing
back double EAP tuition or four-month TOEFL defaults. No staff account,
student data, or financial document is created here.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "toefl_house"))
from toefl_house.setup_presets.preset import load_preset  # noqa: E402


class OwnerDailyPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT / "docs" / "owner-decisions.json").read_text(
            encoding="utf-8"))["owner_policy_addenda_2026_10_30_daily_setup"]
        cls.preset = load_preset()

    def test_ge_eap_monthly_500_never_charged_as_2000_semester(self):
        approved = self.policy["onsite_ge_eap"]
        self.assertEqual(approved["monthly_fee_afn"], 500)
        self.assertEqual(approved["two_month_total_afn"], 1000)
        for program in self.preset["programs"]:
            if program["code"] not in ("GEN-ENG", "EAP"):
                continue
            for level in program["levels"]:
                with self.subTest(level=level["code"]):
                    self.assertEqual(level["semester_tuition_afn"],
                                     approved["monthly_fee_afn"] * level["duration_months"])
                    self.assertIn(level["duration_months"], (1, 2))

    def test_specialist_duration_and_legacy_code_not_misrepresented(self):
        specialist = self.policy["specialist_courses"]
        programs = {item["code"]: item for item in self.preset["programs"]}
        self.assertEqual(programs["SPECIAL-SPEAKING"]["levels"][0]["duration_months"],
                         specialist["special_speaking_months"])
        toefl = programs["TOEFL-PREP"]["levels"][0]
        self.assertEqual(toefl["code"], "TOEFL-PREP-2M")
        self.assertEqual(toefl["duration_months"],
                         specialist["toefl_preparation_months"])
        self.assertIn("TOEFL-PREP-4M", toefl["existing_site_aliases"])
        self.assertEqual(specialist["tuition_status"],
                         "REQUIRES_OWNER_PRICE_VERIFICATION_BEFORE_LIVE_BILLING")

    def test_initial_staff_and_production_are_not_silently_enabled(self):
        staff = self.policy["staff_accounts"]
        self.assertEqual(staff["initial_login_count_including_existing_owner"], 6)
        self.assertTrue(staff["official_emails_not_available"])
        self.assertFalse(staff["invent_real_email_addresses"])
        self.assertFalse(staff["send_unrequested_invitations"])
        self.assertFalse(staff["additional_owner_logins"])
        self.assertFalse(self.preset["backup"]["enabled"])
        self.assertEqual(self.policy["delivery"]["production_state"],
                         "REJECT_UNTIL_EXACT_HEAD_CI_REAL_WINDOWS_INDEPENDENT_REVIEW_BACKUP_RECOVERY_ACCEPTANCE")


if __name__ == "__main__":
    unittest.main()

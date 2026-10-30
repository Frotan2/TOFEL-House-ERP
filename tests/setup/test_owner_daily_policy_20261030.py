"""Owner-approved current daily setup contracts, not production activation.

These offline checks prevent an old candidate preset from silently bringing
back the superseded EAP tuition or two-month TOEFL defaults. No staff account,
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

    def test_ge_and_eap_have_distinct_owner_confirmed_semester_fees(self):
        approved = self.policy["onsite_ge_eap"]
        self.assertEqual(approved["ge_monthly_fee_afn"], 500)
        self.assertEqual(approved["eap_monthly_fee_afn"], 1000)
        self.assertEqual(approved["ge_two_month_total_afn"], 1000)
        self.assertEqual(approved["eap_two_month_total_afn"], 2000)
        for program in self.preset["programs"]:
            if program["code"] not in ("GEN-ENG", "EAP"):
                continue
            for level in program["levels"]:
                with self.subTest(level=level["code"]):
                    self.assertEqual(level["semester_tuition_afn"],
                                     approved["ge_monthly_fee_afn" if program["code"] == "GEN-ENG" else "eap_monthly_fee_afn"] * level["duration_months"])
                    self.assertIn(level["duration_months"], (1, 2))

    def test_specialist_duration_and_legacy_code_not_misrepresented(self):
        specialist = self.policy["specialist_courses"]
        programs = {item["code"]: item for item in self.preset["programs"]}
        self.assertEqual(programs["SPECIAL-SPEAKING"]["levels"][0]["duration_months"],
                         specialist["special_speaking_months"])
        self.assertEqual(specialist["special_speaking_semester_count"], 1)
        self.assertEqual(specialist["special_speaking_semester_fee_afn"], 2000)
        self.assertEqual(specialist["toefl_semester_fee_afn"], 7000)
        self.assertTrue(all(p["initial_tuition_approved"] for p in self.preset["programs"]))
        toefl = programs["TOEFL-PREP"]["levels"][0]
        self.assertEqual(toefl["code"], "TOEFL-PREP-4M")
        self.assertEqual(toefl["duration_months"],
                         specialist["toefl_preparation_months"])
        self.assertIn("TOEFL-PREP-2M", toefl["existing_site_aliases"])
        self.assertEqual(specialist["tuition_status"],
                         "OWNER_CONFIRMED_CONFIGURATION_ONLY_NOT_PRODUCTION_AUTHORIZATION")

    def test_latest_timetable_and_retake_are_the_owner_confirmed_values(self):
        timetable = self.policy["timetable"]
        self.assertEqual(timetable, self.preset["daily_timetable"])
        self.assertEqual(timetable["status"], "OWNER_CONFIRMED")
        self.assertEqual(timetable["session_minutes"], 70)
        self.assertEqual(timetable["normal_break_minutes"], 10)
        self.assertEqual(timetable["break_after_first_morning_session_minutes"], 20)
        self.assertEqual(self.preset["institution"]["working_hours_local"],
                         {"start": "06:20", "end": "17:50"})
        self.assertEqual(self.policy["assessment_retake_governing"]["value"], "best")
        def minutes(clock):
            h, m = map(int, clock.split(":"))
            return h * 60 + m
        sessions = timetable["sessions"]
        self.assertEqual([r["code"] for r in sessions], [f"S{i:03d}" for i in range(1, 8)])
        for track in ("male", "female"):
            for index, row in enumerate(sessions):
                window = row[track]
                self.assertEqual(minutes(window["end"]) - minutes(window["start"]), 70)
                self.assertFalse(minutes(window["start"]) < 13 * 60
                                 and minutes(window["end"]) > 12 * 60)
                if index in (1, 2, 3, 5, 6):
                    self.assertEqual(minutes(window["start"]) - minutes(sessions[index - 1][track]["end"]),
                                     20 if index == 1 else 10)
        for index, row in enumerate(sessions):
            self.assertEqual(minutes(row["female"]["start"]) - minutes(row["male"]["start"]),
                             10 if index < 4 else -10)
        self.assertEqual(sessions[-1]["male"]["end"], "17:50")
        self.assertEqual(sessions[-1]["female"]["end"], "17:40")
        self.assertEqual(self.policy["rooms"]["numbers"], list(range(2, 18)))

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

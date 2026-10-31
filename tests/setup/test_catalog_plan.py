"""Offline tests for dry-run only first-install command planning."""
import copy
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
sys.path.insert(0, str(APP_ROOT))

from toefl_house.setup_presets.catalog_plan import (  # noqa: E402
    action_request_key, prepare_catalog_plan,
)
from toefl_house.setup_presets.preset import load_preset  # noqa: E402


class TestSetupCatalogPlanner(unittest.TestCase):
    def setUp(self):
        self.preset = load_preset()

    def test_blank_site_commands_are_ordered_and_never_execute(self):
        snapshot = {"programs": {}, "levels": {}, "years": {},
                    "fee_categories": [], "tuition": {}}
        before = copy.deepcopy(snapshot)
        plan = prepare_catalog_plan(snapshot, self.preset)
        self.assertEqual(snapshot, before)
        self.assertFalse(plan["permitted_to_execute"])
        self.assertEqual(plan["mode"], "REQUIRES_EXPLICIT_OWNER_AUTHORIZATION")
        self.assertEqual(plan["count"], 35)
        actions = plan["actions"]
        kinds = [x["operation"] for x in actions]
        self.assertEqual(kinds.count("create_academic_year"), 1)
        self.assertEqual(kinds.count("create_program"), 4)
        self.assertEqual(kinds.count("create_level"), 11)
        self.assertTrue(all(action["duration_unit"] == "Solar Hijri Month"
                            for action in actions if action["operation"] == "create_level"))
        self.assertEqual(kinds.count("set_next_level"), 7)
        self.assertEqual(kinds.count("create_fee_type"), 1)
        self.assertEqual(kinds.count("set_level_fee_component"), 11)
        self.assertLess(kinds.index("create_program"), kinds.index("create_level"))
        self.assertLess(kinds.index("create_level"), kinds.index("set_next_level"))
        self.assertLess(kinds.index("create_fee_type"), kinds.index("set_level_fee_component"))
        self.assertEqual({x["operation"] for x in actions}.intersection(
            {"issue_tuition_fees", "create_discount_rule", "set_backup_enabled",
             "publish_assessment_results", "create_salary_slip"}), set())

    def test_existing_identical_records_plan_no_writes(self):
        p = self.preset
        snapshot = {
            "programs": {f["code"]: {"title": f["title"]} for f in p["programs"]},
            "levels": {level["code"]: {
                "family": f["code"], "title": level["title"],
                "duration_months": level["duration_months"]}
                for f in p["programs"] for level in f["levels"]},
            "years": {y["name"]: {"start": y["start"], "end": y["end"]}
                      for y in p["academic_years"]},
            "fee_categories": [p["fee_policy"]["category"]],
            "tuition": {l["code"]: {y["name"]: l["semester_tuition_afn"]}
                        for f in p["programs"]
                        for l in f["levels"] for y in p["academic_years"]},
        }
        self.assertEqual(prepare_catalog_plan(snapshot, p)["actions"], [])

    def test_unapproved_specialist_prices_never_become_auto_setup_actions(self):
        unapproved = copy.deepcopy(self.preset)
        for family in unapproved["programs"]:
            if family["code"] in ("SPECIAL-SPEAKING", "TOEFL-PREP"):
                family["initial_tuition_approved"] = False
        plan = prepare_catalog_plan({"programs": {}, "levels": {}, "years": {},
                                     "fee_categories": [], "tuition": {}}, unapproved)
        generated = {action.get("level") for action in plan["actions"]
                     if action["operation"] == "set_level_fee_component"}
        self.assertNotIn("TOEFL-PREP-4M", generated)
        self.assertNotIn("SPECIAL-SPEAKING-2M", generated)
        self.assertEqual(plan["preview"]["counts"]["deferred"], 2)
        # Any historical preset Fee Structure for an unapproved specialist
        # needs an explicit Owner/Finance review rather than silent reuse.
        with self.assertRaisesRegex(ValueError, "conflicts"):
            prepare_catalog_plan({"tuition": {"TOEFL-PREP-4M": {"1405": 7000}}},
                                 unapproved)

    def test_mismatched_existing_fee_is_not_overwritten(self):
        snapshot = {"tuition": {"STARTER": {"1405": 1234}}}
        with self.assertRaisesRegex(ValueError, "conflicts"):
            prepare_catalog_plan(snapshot, self.preset)

    def test_orphan_native_course_cannot_be_duplicated_on_fresh_site(self):
        for title in ("General English — Prep 1",
                      "TOEFL Preparation — TOEFL Preparation"):
            with self.subTest(title=title):
                with self.assertRaisesRegex(ValueError, "conflicts"):
                    prepare_catalog_plan({"native_course_titles": [title]},
                                         self.preset)

    def test_initial_preset_has_no_legacy_migration_aliases(self):
        self.assertEqual(self.preset["installation_profile"],
                         "FRESH_SITE_NO_PRIOR_COURSE_HISTORY")
        self.assertFalse(any("existing_site_aliases" in level
                             for p in self.preset["programs"] for level in p["levels"]))
        self.assertFalse(self.preset["initial_operational_data"]["legacy_data_import_enabled"])

    def test_stable_bounded_idempotency_keys(self):
        action = {"operation": "create_academic_year", "name": "1405",
                  "start_date": "2026-03-21", "end_date": "2027-03-20"}
        key = action_request_key(self.preset["preset_id"], action)
        self.assertEqual(key, action_request_key(self.preset["preset_id"], copy.deepcopy(action)))
        self.assertTrue(key.startswith("OWNERSETUP-"))
        self.assertLessEqual(len(key), 96)
        changed = dict(action, name="1406")
        self.assertNotEqual(key, action_request_key(self.preset["preset_id"], changed))


if __name__ == "__main__":
    unittest.main()

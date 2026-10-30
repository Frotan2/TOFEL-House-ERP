"""New-institute setup contract: no historical, migrated or demo business data.

The Owner explicitly confirmed TOEFL House has never used this ERP for real
operations. This test keeps the initial package a fresh catalog, not a
migration or a demo database. It does not activate production.
"""
import copy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "toefl_house"))
from toefl_house.setup_presets.preset import load_preset, validate_preset  # noqa: E402
from toefl_house.setup_presets.catalog_plan import prepare_catalog_plan  # noqa: E402


class FreshInstituteSetupTests(unittest.TestCase):
    def setUp(self):
        self.preset = load_preset()

    def test_empty_site_is_the_only_initial_customer_data_profile(self):
        self.assertEqual(self.preset["installation_profile"],
                         "FRESH_SITE_NO_PRIOR_COURSE_HISTORY")
        initial = self.preset["initial_operational_data"]
        for key, value in initial.items():
            with self.subTest(key=key):
                self.assertIs(value, False) if isinstance(value, bool) else self.assertEqual(value, 0)
        self.assertEqual(len(self.preset["programs"]), 4)
        self.assertEqual(sum(len(p["levels"]) for p in self.preset["programs"]), 11)
        self.assertFalse(any("existing_site_aliases" in level
                             for family in self.preset["programs"]
                             for level in family["levels"]))

    def test_any_nonzero_history_or_demo_import_is_rejected(self):
        for key in ("students", "student_applicants", "enrollments", "classes",
                    "attendance_records", "issued_fees", "payment_entries",
                    "salary_slips", "assessment_results"):
            data = copy.deepcopy(self.preset)
            data["initial_operational_data"][key] = 1
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "zero business history"):
                validate_preset(data)
        for key in ("legacy_data_import_enabled", "demo_data_in_customer_package"):
            data = copy.deepcopy(self.preset)
            data["initial_operational_data"][key] = True
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "zero business history"):
                validate_preset(data)

    def test_clean_plan_does_not_create_operational_or_historical_documents(self):
        plan = prepare_catalog_plan({
            "programs": {}, "levels": {}, "years": {}, "fee_categories": [],
            "tuition": {}, "native_program_titles": [],
            "native_program_abbreviations": [], "native_course_titles": [],
        }, self.preset)
        self.assertEqual(plan["count"], 35)
        self.assertFalse(plan["permitted_to_execute"])
        self.assertEqual({x["operation"] for x in plan["actions"]},
                         {"create_academic_year", "create_program", "create_level",
                          "set_next_level", "create_fee_type", "set_level_fee_component"})
        for forbidden in ("Student", "Program Enrollment", "Fees", "Payment Entry",
                          "Salary Slip", "Academic Result"):
            self.assertIn(forbidden, plan["excluded"])

    def test_customer_packager_refuses_runtime_data_in_release(self):
        packager = (ROOT / "product/windows/Prepare Customer Package.ps1").read_text(
            encoding="utf-8")
        builder = (ROOT / "tools/release/Build Customer Installer.ps1").read_text(
            encoding="utf-8")
        self.assertIn('Join-Path $packageRoot "product\\data"', packager)
        self.assertIn('throw "The customer package unexpectedly contains product data."', packager)
        self.assertIn("Join-Path $packageRoot 'product\\data'", builder)
        self.assertIn("throw 'Customer data must never be packaged.'", builder)

    def test_owner_setup_apply_requires_verified_release_preflight_and_post(self):
        backend = (ROOT / "apps/toefl_house/toefl_house/setup_presets/api.py").read_text(
            encoding="utf-8")
        installer = (ROOT / "apps/toefl_house/toefl_house/setup_presets/installer.py").read_text(
            encoding="utf-8")
        client = (ROOT / "apps/toefl_house/toefl_house/public/js/th_role_desks.js").read_text(
            encoding="utf-8")
        self.assertIn("preview[\"fresh_installation\"]", backend)
        self.assertIn("_qualified_site()", backend)
        self.assertIn("_finance_preconditions()", backend)
        self.assertIn('fresh.can_initialize === true', client)
        self.assertIn("frappe.confirm(", client)
        self.assertIn('type: "POST"', client)
        self.assertIn("expected_plan_hash: data.plan_hash", client)
        self.assertIn('confirmation: "APPLY_TO_NEW_COURSE_SITE"', client)
        self.assertIn("def initialize_owner_catalog(", installer)
        self.assertIn("preview_digest(snapshot)", installer)
        self.assertIn("_qualified_site()", installer)
        self.assertNotIn("frappe.db.commit(", installer)


if __name__ == "__main__":
    unittest.main()

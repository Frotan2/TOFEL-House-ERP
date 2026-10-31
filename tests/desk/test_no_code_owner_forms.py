"""The customer/owner workspaces must not require source, JSON or code IDs.

Server methods retain native authority and strict structured validators.
These tests inspect the shipped UI and optionally parse its real JavaScript.
"""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUI = ROOT / "apps/toefl_house/toefl_house/public/js/th_role_desks.js"
SETUP = ROOT / "apps/toefl_house/toefl_house/desk/setup.py"
ASSESSMENT = ROOT / "apps/toefl_house/toefl_house/academic/__init__.py"


class NoCodeOwnerFormsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gui = GUI.read_text(encoding="utf-8")
        cls.setup = SETUP.read_text(encoding="utf-8")

    @unittest.skipUnless(shutil.which("node"), "Node is not on this test runner")
    def test_javascript_passes_real_syntax_validation(self):
        completed = subprocess.run(
            ["node", "--check", str(GUI)], capture_output=True, text=True,
            timeout=30, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr[:2000])

    def test_grade_scale_is_numeric_and_json_is_internal_only(self):
        for key in ("grade_a", "grade_b", "grade_c", "grade_d"):
            self.assertIn(f'fieldname: "{key}"', self.gui)
        self.assertNotIn("Grade thresholds (prefilled JSON", self.gui)
        self.assertIn("args.intervals = JSON.stringify(", self.gui)
        self.assertIn("thresholds[index - 1] > n", self.gui)

    def test_initial_ge_eap_assessment_has_simple_controls(self):
        self.assertIn("Set up grading (simple form)", self.setup)
        for key in ("passing_score", "retake_wait_days", "effective_from"):
            self.assertIn(f'fieldname: "{key}"', self.gui)
        self.assertIn(
            "toefl_house.setup_presets.owner_policy_forms.configure_initial_assessment",
            self.gui)
        self.assertIn("Change passing mark / retake wait", self.setup)
        self.assertNotIn("ordered = [version_action] + facet_actions", self.setup)

    def test_ordinary_course_and_policy_names_generate_internal_ids(self):
        self.assertIn("const automaticCode =", self.gui)
        self.assertIn('fields.some((field) => field.fieldname === "code")', self.gui)
        self.assertIn('fields = fields.filter((field) => field.fieldname !== "code")', self.gui)
        self.assertIn("args.code = code;", self.gui)
        self.assertIn("Short English name (only if the title is in Dari)", self.gui)

    def test_billing_uses_afghan_month_selects_and_numeric_inputs(self):
        self.assertIn('label: "Installment schedule"', self.gui)
        self.assertIn('default: "Solar Hijri Month"', self.gui)
        self.assertIn('fieldname: "max_installments"', self.gui)
        self.assertIn('fieldname: "payment_grace_days"', self.gui)
        self.assertIn("args.installment_due_day = monthly ? due : 0;", self.gui)

    def test_salary_contract_forms_do_not_show_json(self):
        self.assertIn("const teachingContractForm =", self.gui)
        self.assertIn('!["skill_terms", "adjustments"].includes(field.fieldname)', self.gui)
        self.assertIn('fieldname: "skill_" + index', self.gui)
        self.assertIn('fieldname: "adjustment_amount_" + index', self.gui)
        self.assertIn("args.skill_terms = JSON.stringify(terms);", self.gui)
        self.assertIn("args.adjustments = JSON.stringify(adjustments);", self.gui)
        self.assertIn("Re-enter ALL approved skills", self.gui)

    def test_setup_home_has_real_navigation_and_no_command_line_steps(self):
        self.assertIn("Start your course in simple steps", self.gui)
        for label in ("1. Courses and tuition", "2. Academic and billing rules",
                      "3. Rooms, teachers and timetables",
                      "4. Finance and daily work", "5. Review before opening"):
            self.assertIn(label, self.gui)
        self.assertIn('routeToSource(route)', self.gui)
        self.assertIn("never a request to edit JSON, scripts or database tables", self.gui)

    def test_teacher_marks_attendance_only_through_student_dropdowns(self):
        self.assertIn(
            'fields.filter((field) => field.fieldname !== "statuses")',
            self.gui)
        self.assertIn('statuses[member.student] = values[key];', self.gui)
        self.assertIn('args.statuses = JSON.stringify(statuses);', self.gui)
        self.assertIn("new Set(ids).size !== ids.length", self.gui)

    def test_no_code_weight_forms_are_shared_and_validated(self):
        self.assertIn("const ACADEMIC_WEIGHT_FIELDS = Object.freeze(", self.gui)
        self.assertIn("...ACADEMIC_WEIGHT_FIELDS", self.gui)
        self.assertIn('fieldname: "continuous_percent"', self.gui)
        self.assertIn('fieldname: "vocabulary"', self.gui)
        self.assertIn("values_.reduce((sum, value) => sum + value, 0) !== 100",
                      self.gui)
        self.assertIn("Change skill / exam weights", self.setup)

    def test_native_owner_master_choices_and_retries_remain_secure(self):
        self.assertIn("owner_policy_forms.owner_form_options", self.gui)
        self.assertIn('type: "GET"', self.gui)
        self.assertIn("const requestKey = newRequestKey();", self.gui)
        self.assertIn("const args = { request_key: requestKey };", self.gui)
        self.assertIn("__owner_choice:grading_scale__", self.gui)
        self.assertIn("__owner_choice:fee_category__", self.gui)

    def test_native_assessment_backend_still_validates_versioned_changes(self):
        source = ASSESSMENT.read_text(encoding="utf-8")
        self.assertIn("passing_score=None, retake_wait_days=None", source)
        self.assertIn("configuration_rules.check_appends(", source)
        self.assertIn('rules.canonical_facet("retakes", retakes)', source)
        self.assertIn('rules.validate_policy_facets(carried)', source)


if __name__ == "__main__":
    unittest.main()

"""Validate native grading scale creation inputs and Owner-only audit gate."""
import json
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
sys.path.insert(0, str(APP_ROOT))
from toefl_house.setup_presets.grading_rules import normalize_intervals  # noqa: E402


class GradingScaleValidationTests(unittest.TestCase):
    def test_owner_grading_scale_round_trip(self):
        rows = [{"grade_code": "F", "threshold": 0},
                {"grade_code": "C", "threshold": 70},
                {"grade_code": "A", "threshold": 90},
                {"grade_code": "B", "threshold": 80},
                {"grade_code": "D", "threshold": 65}]
        expected = normalize_intervals(rows)
        self.assertEqual([row["grade_code"] for row in expected],
                         ["A", "B", "C", "D", "F"])
        self.assertEqual(expected[-1]["threshold"], 0)
        self.assertEqual(normalize_intervals(json.dumps(rows)), expected)

    def test_reject_duplicate_grade_and_threshold(self):
        cases = [
            [{"grade_code": "A", "threshold": 90},
             {"grade_code": "A", "threshold": 0}],
            [{"grade_code": "A", "threshold": 90},
             {"grade_code": "F", "threshold": 90}],
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, "Duplicate"):
                normalize_intervals(case)

    def test_refuse_missing_zero_threshold(self):
        with self.assertRaisesRegex(ValueError, "threshold zero"):
            normalize_intervals([{"grade_code": "A", "threshold": 90},
                                 {"grade_code": "B", "threshold": 80}])

    def test_refuse_nan_infinity_bool_and_invalid_percent(self):
        for number in ("NaN", "Infinity", -1, 100.1, True, "not a score"):
            with self.subTest(number=number), self.assertRaises(ValueError):
                normalize_intervals([{"grade_code": "A", "threshold": number},
                                     {"grade_code": "F", "threshold": 0}])

    def test_reject_low_quality_or_extra_fields(self):
        cases = [
            [{"grade_code": "a", "threshold": 90}, {"grade_code": "F", "threshold": 0}],
            [{"grade_code": "A", "threshold": 90, "description": "<html>"},
             {"grade_code": "F", "threshold": 0}],
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                normalize_intervals(case)

    def test_native_configuration_is_owner_gated_and_only_creates_new_scale(self):
        app = APP_ROOT / "toefl_house"
        source = (app / "setup_presets/native_grading_scale.py").read_text(encoding="utf-8")
        audit = (app / "configuration/audit.py").read_text(encoding="utf-8")
        self.assertIn('"create_owner_grading_scale": "business_policy"', audit)
        self.assertIn('configuration_audit.execute(', source)
        self.assertIn('"create_owner_grading_scale", request_key', source)
        self.assertIn('@frappe.whitelist(methods=["POST"])', source)
        self.assertIn('frappe.db.exists("Grading Scale", name)', source)
        self.assertIn('doc.insert(ignore_permissions=True)', source)
        self.assertIn('doc.submit()', source)
        self.assertIn('int(doc.docstatus or 0) != 1', source)
        self.assertNotIn('frappe.db.commit(', source)
        self.assertNotIn('set_user_roles', source)
        self.assertNotIn('frappe.db.set_value("Grading Scale"', source)


if __name__ == "__main__":
    unittest.main()

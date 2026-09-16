"""Pure local unit checks for internal placement decision / course mapping.

These do NOT qualify native Frappe behavior (the hosted native checks do that).
"""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import (ATTEMPT_TRANSITIONS, can_read, recommend_course,
                                validate_course_map, validate_policy)


def course_map():
    return {
        "algorithm": "course-map-v1",
        "entries": [{
            "internal_level": "SYN-LEVEL-GENERAL",
            "course_code": "SYN-COURSE-GENERAL",
            "match": "any_correct",
        }],
    }


def score(presented=9, correct=1, incorrect=0, missing=8):
    return {"presented": presented, "correct": correct,
            "incorrect": incorrect, "missing": missing}


class CourseMapValidationTests(unittest.TestCase):
    def test_valid_map(self):
        self.assertEqual(validate_course_map(course_map()), course_map())

    def test_exact_fields(self):
        for field in course_map():
            value = course_map(); value.pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_course_map(value)
        value = course_map(); value["cutoff"] = 70
        with self.assertRaises(ValueError):
            validate_course_map(value)

    def test_algorithm_and_match_are_fixture_only(self):
        value = course_map(); value["algorithm"] = "cefr-v1"
        with self.assertRaises(ValueError):
            validate_course_map(value)
        value = course_map(); value["entries"][0]["match"] = "any_evidence"
        with self.assertRaises(ValueError):
            validate_course_map(value)

    def test_synthetic_codes_required(self):
        value = course_map(); value["entries"][0]["internal_level"] = "B1"
        with self.assertRaises(ValueError):
            validate_course_map(value)
        value = course_map(); value["entries"][0]["course_code"] = "TOEFL-101"
        with self.assertRaises(ValueError):
            validate_course_map(value)

    def test_entry_shape(self):
        value = course_map(); value["entries"][0]["percent"] = 70
        with self.assertRaises(ValueError):
            validate_course_map(value)
        value = course_map(); value["entries"] = []
        with self.assertRaises(ValueError):
            validate_course_map(value)

    def test_policy_fields_unchanged(self):
        policy = {"result_validity_days": 90, "retest_wait_days": 14,
                  "release_working_days": 2, "appeal_working_days": 5, "retention_years": 3}
        self.assertEqual(validate_policy(policy), policy)
        extra = dict(policy, course_map=course_map())
        with self.assertRaises(ValueError):
            validate_policy(extra)


class RecommendCourseTests(unittest.TestCase):
    def test_any_correct_maps_synthetic_course(self):
        result = recommend_course(score(), course_map())
        self.assertEqual(result["algorithm"], "course-map-v1")
        self.assertEqual(result["internal_level"], "SYN-LEVEL-GENERAL")
        self.assertEqual(result["course_code"], "SYN-COURSE-GENERAL")
        self.assertNotIn("percent", result)
        self.assertNotIn("cefr", result)
        self.assertNotIn("toefl", result)
        self.assertNotIn("composite", result)

    def test_all_missing_fails_closed(self):
        with self.assertRaises(ValueError):
            recommend_course(score(presented=9, correct=0, incorrect=0, missing=9), course_map())

    def test_zero_correct_fails_closed(self):
        with self.assertRaises(ValueError):
            recommend_course(score(presented=9, correct=0, incorrect=1, missing=8), course_map())

    def test_completeness_mismatch_fails_closed(self):
        with self.assertRaises(ValueError):
            recommend_course(score(presented=9, correct=1, incorrect=0, missing=0), course_map())

    def test_rejects_composite_claims_on_score(self):
        value = score(); value["percent"] = 70
        with self.assertRaises(ValueError):
            recommend_course(value, course_map())

    def test_invalid_map_fails_closed(self):
        bad = copy.deepcopy(course_map()); bad["entries"][0]["match"] = "any_evidence"
        with self.assertRaises(ValueError):
            recommend_course(score(), bad)


class DecisionReadBoundaryTests(unittest.TestCase):
    def test_releaser_reads_decision_not_manifest_or_key(self):
        roles = ["Placement Releaser"]
        for kind in ("case", "attempt", "response", "score", "decision"):
            with self.subTest(kind=kind):
                self.assertTrue(can_read(kind, roles, "rel", "someone"))
        self.assertFalse(can_read("manifest", roles, "rel", "someone"))
        self.assertFalse(can_read("key", roles, "rel", "rel"))
        self.assertFalse(can_read("guard", roles, "rel", "someone"))
        self.assertFalse(can_read("course_map", roles, "rel", "someone", "Published"))

    def test_reviewer_does_not_read_decision(self):
        self.assertFalse(can_read("decision", ["Placement Reviewer"], "r", "someone"))

    def test_assessor_does_not_read_decision(self):
        self.assertFalse(can_read("decision", ["Placement Assessor"], "a", "someone"))

    def test_invigilator_does_not_read_decision(self):
        self.assertFalse(can_read("decision", ["Placement Invigilator"], "i", "someone"))

    def test_author_does_not_read_decision(self):
        self.assertFalse(can_read("decision", ["Placement Author"], "a", "a"))

    def test_auditor_reads_decision_and_published_course_map(self):
        self.assertTrue(can_read("decision", ["Placement Auditor"], "a", "someone"))
        self.assertTrue(can_read("course_map", ["Placement Auditor"], "a", "b", "Published"))
        self.assertFalse(can_read("course_map", ["Placement Auditor"], "a", "b", "Draft"))

    def test_author_reads_own_course_map_draft(self):
        self.assertTrue(can_read("course_map", ["Placement Author"], "a", "a", "Draft"))
        self.assertFalse(can_read("course_map", ["Placement Author"], "a", "b", "Draft"))

    def test_attempt_transitions_unchanged(self):
        self.assertEqual(ATTEMPT_TRANSITIONS, {
            ("Allocated", "Verified"),
            ("Verified", "In Progress"),
            ("In Progress", "Sealed"),
            ("Sealed", "Marking"),
            ("Marking", "Review"),
            ("Review", "Finalized"),
        })


if __name__ == "__main__":
    unittest.main()

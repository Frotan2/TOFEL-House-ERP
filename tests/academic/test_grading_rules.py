"""Offline tests for the deterministic grading engine.

``toefl_house.academic.grading`` is deliberately frappe-free, so the whole
rule set is exercised here without a site: components and weights, the native
grading scale, pass rules, missing marks, progression evidence and retake
windows. Every academic number in these tests comes from a *configured*
policy — the engine has no defaults — so the assertions double as a check
that nothing in the code invents a threshold.
"""
import json
import unittest
from decimal import Decimal

from tests.academic._harness import load_pure_modules

grading = load_pure_modules("academic.grading")
policy = load_pure_modules("policy")


def configure(**overrides):
    """A complete, Owner-configured policy version (no engine defaults).

    Facets go through the real ``parse_facets`` seam, exactly as the stored
    canonical JSON of a policy version does, so a facet set the Course Owner
    could never save cannot be graded here either.
    """
    values = {
        "components": [
            {"code": "LISTENING", "title": "Listening", "maximum_score": 30},
            {"code": "READING", "title": "Reading", "maximum_score": 20},
        ],
        "weights": [
            {"component": "LISTENING", "weight": 60},
            {"component": "READING", "weight": 40},
        ],
        "pass_rules": {"components": [],
                       "overall": {"kind": "percent", "value": 60}},
    }
    values.update(overrides)
    return grading.parse_facets({
        name: (None if value is None else json.dumps(value, sort_keys=True))
        for name, value in values.items()})


SCALE = [{"threshold": 85, "grade_code": "A"},
         {"threshold": 70, "grade_code": "B"},
         {"threshold": 55, "grade_code": "C"}]


def marks(listening=24.0, reading=16.0, **extra):
    values = {"LISTENING": {"mark": listening}, "READING": {"mark": reading}}
    values.update(extra)
    return values


class WeightedResultTests(unittest.TestCase):
    def test_component_contributions_are_weighted_and_explained(self):
        snapshot = grading.compute_result(configure(), marks(), SCALE)
        self.assertEqual(snapshot["algorithm"], "th-grading-v1")
        self.assertEqual(snapshot["weight_total"], 100.0)
        listening, reading = snapshot["components"]
        self.assertEqual(listening["percent"], 80.0)
        self.assertEqual(listening["weighted_percent"], 48.0)
        self.assertEqual(reading["weighted_percent"], 32.0)
        self.assertEqual(snapshot["overall_percent"], 80.0)
        self.assertEqual(snapshot["grade_code"], "B")
        self.assertEqual(snapshot["outcome"], "Pass")
        self.assertTrue(snapshot["passed"])
        self.assertTrue(any("Component LISTENING" in row
                            for row in snapshot["explanations"]))
        self.assertTrue(any("Weighted overall" in row
                            for row in snapshot["explanations"]))

    def test_weights_are_normalised_rather_than_assumed_to_sum_to_100(self):
        snapshot = grading.compute_result(
            configure(weights=[{"component": "LISTENING", "weight": 1},
                            {"component": "READING", "weight": 3}]),
            marks(), SCALE)
        self.assertEqual(snapshot["weight_total"], 4.0)
        self.assertEqual(snapshot["overall_percent"], 80.0)

    def test_the_same_inputs_produce_byte_identical_snapshots(self):
        first = grading.compute_result(configure(), marks(), SCALE)
        second = grading.compute_result(configure(), marks(), SCALE)
        self.assertEqual(grading.snapshot_json(first),
                         grading.snapshot_json(second))
        self.assertEqual(grading.snapshot_digest(first),
                         grading.snapshot_digest(second))

    def test_integer_and_float_marks_hash_identically(self):
        whole = grading.compute_result(configure(), marks(24, 16), SCALE)
        fractional = grading.compute_result(configure(), marks(24.0, 16.0), SCALE)
        self.assertEqual(grading.snapshot_digest(whole),
                         grading.snapshot_digest(fractional))

    def test_scale_rows_hash_identically_in_any_order(self):
        forward = grading.compute_result(configure(), marks(), SCALE)
        backward = grading.compute_result(configure(), marks(), list(reversed(SCALE)))
        self.assertEqual(grading.snapshot_digest(forward),
                         grading.snapshot_digest(backward))

    def test_rounding_is_one_quantized_step_and_documented(self):
        # 1/3 of the component marks with a 33.3333% component percentage.
        snapshot = grading.compute_result(
            configure(components=[{"code": "ESSAY", "title": "Essay",
                                "maximum_score": 3}],
                   weights=[{"component": "ESSAY", "weight": 100}],
                   pass_rules={"components": [],
                               "overall": {"kind": "percent", "value": 60}}),
            {"ESSAY": {"mark": 1}}, SCALE)
        self.assertEqual(snapshot["quantization"], "4dp round-half-up")
        self.assertEqual(snapshot["components"][0]["percent"], 33.3333)
        self.assertEqual(snapshot["overall_percent"], 33.3333)
        self.assertEqual(snapshot["grade_code"], "")
        self.assertEqual(snapshot["outcome"], "Fail")


class GradeScaleTests(unittest.TestCase):
    def test_grade_is_the_highest_configured_threshold(self):
        self.assertEqual(grading.grade_for(SCALE, 90), "A")
        self.assertEqual(grading.grade_for(SCALE, 85), "A")
        self.assertEqual(grading.grade_for(SCALE, 84.9999), "B")
        self.assertEqual(grading.grade_for(SCALE, 55), "C")

    def test_below_every_threshold_there_is_no_grade(self):
        self.assertEqual(grading.grade_for(SCALE, 54.9), "")

    def test_no_scale_at_all_produces_no_grade(self):
        self.assertEqual(grading.grade_for([], 90), "")
        self.assertEqual(grading.grade_for(None, 90), "")

    def test_an_interval_without_a_code_is_an_integrity_fault(self):
        with self.assertRaises(ValueError):
            grading.grade_for([{"threshold": 50, "grade_code": ""}], 90)


class MissingMarkTests(unittest.TestCase):
    def test_a_missing_mark_makes_the_result_incomplete_never_a_pass(self):
        snapshot = grading.compute_result(
            configure(), {"LISTENING": {"mark": 30}}, SCALE)
        self.assertEqual(snapshot["outcome"], "Incomplete")
        self.assertFalse(snapshot["passed"])
        self.assertIsNone(snapshot["overall_percent"])
        self.assertEqual(snapshot["missing"], ["READING"])
        self.assertTrue(any("no mark" in row for row in snapshot["explanations"]))

    def test_a_recorded_missing_reason_travels_into_the_snapshot(self):
        snapshot = grading.compute_result(
            configure(),
            {"LISTENING": {"mark": 24},
             "READING": {"mark": None, "missing_reason": "Medical absence"}},
            SCALE)
        self.assertEqual(snapshot["outcome"], "Incomplete")
        self.assertEqual(snapshot["components"][1]["missing_reason"],
                         "Medical absence")
        self.assertTrue(any("Medical absence" in row
                            for row in snapshot["explanations"]))

    def test_a_component_pass_rule_is_not_met_without_a_mark(self):
        snapshot = grading.compute_result(
            configure(pass_rules={"components": [
                {"component": "READING",
                 "minimum": {"kind": "percent", "value": 50}}],
                "overall": {"kind": "percent", "value": 60}}),
            {"LISTENING": {"mark": 30}}, SCALE)
        checks = {row["scope"]: row for row in snapshot["checks"]}
        self.assertFalse(checks["READING"]["met"])
        self.assertEqual(snapshot["outcome"], "Incomplete")


class PassRuleTests(unittest.TestCase):
    def test_the_overall_percent_rule_decides_pass_and_fail(self):
        rules_ = configure(pass_rules={
            "components": [], "overall": {"kind": "percent", "value": 60}})
        self.assertEqual(
            grading.compute_result(rules_, marks(18, 12), SCALE)["outcome"],
            "Pass")  # 60%
        failing = grading.compute_result(rules_, marks(17.9, 12), SCALE)
        self.assertEqual(failing["outcome"], "Fail")
        self.assertEqual(failing["checks"][0]["actual"], "59.8%")

    def test_a_grade_rule_uses_the_native_scale_codes(self):
        snapshot = grading.compute_result(
            configure(pass_rules={"components": [],
                               "overall": {"kind": "grade", "value": "A"}}),
            marks(), SCALE)
        self.assertEqual(snapshot["grade_code"], "B")
        self.assertEqual(snapshot["outcome"], "Fail")
        self.assertEqual(snapshot["checks"][0]["target"], "grade A")

    def test_a_component_minimum_is_enforced_beyond_the_overall_total(self):
        rules_ = configure(pass_rules={
            "components": [{"component": "READING",
                            "minimum": {"kind": "percent", "value": 90}}],
            "overall": {"kind": "percent", "value": 60}})
        # 24/30 and 16/20 -> 80% overall, but Reading is only 80%.
        snapshot = grading.compute_result(rules_, marks(), SCALE)
        self.assertEqual(snapshot["outcome"], "Fail")
        checks = {row["scope"]: row for row in snapshot["checks"]}
        self.assertFalse(checks["READING"]["met"])
        self.assertTrue(checks["overall"]["met"])

    def test_a_pass_rule_for_an_unconfigured_component_is_refused(self):
        with self.assertRaises(ValueError):
            grading.compute_result(
                configure(pass_rules={"components": [
                    {"component": "SPEAKING",
                     "minimum": {"kind": "percent", "value": 60}}],
                    "overall": {"kind": "percent", "value": 60}}),
                marks(), SCALE)


class UnconfiguredPolicyTests(unittest.TestCase):
    def test_missing_facets_are_named_not_defaulted(self):
        state = grading.policy_state(configure(weights=None), SCALE)
        self.assertFalse(state["configured"])
        self.assertIn("weights", state["missing"])
        self.assertTrue(any("Course Owner" in row
                            for row in state["explanations"]))

    def test_computing_on_an_unconfigured_policy_raises(self):
        with self.assertRaises(ValueError) as raised:
            grading.compute_result(configure(components=None), marks(), SCALE)
        self.assertIn("components", str(raised.exception))

    def test_a_facet_set_the_owner_could_not_configure_is_refused(self):
        with self.assertRaises(ValueError):
            configure(weights=[{"component": "SPEAKING", "weight": 100}])

    def test_an_unweighted_component_is_named(self):
        state = grading.policy_state(
            configure(weights=[{"component": "LISTENING", "weight": 100}]), SCALE)
        self.assertFalse(state["configured"])
        self.assertIn("weights for READING", state["missing"])

    def test_zero_total_weight_is_refused(self):
        state = grading.policy_state(
            configure(weights=[{"component": "LISTENING", "weight": 0},
                            {"component": "READING", "weight": 0}]), SCALE)
        self.assertFalse(state["configured"])
        self.assertIn("a positive weight total", state["missing"])

    def test_a_policy_without_a_native_scale_cannot_produce_a_grade(self):
        state = grading.policy_state(configure(), [])
        self.assertFalse(state["configured"])
        self.assertIn("grading scale intervals", state["missing"])
        with self.assertRaises(ValueError):
            grading.compute_result(configure(), marks(), [])


class MarkIntegrityTests(unittest.TestCase):
    def test_a_mark_above_the_component_maximum_is_refused(self):
        with self.assertRaises(ValueError) as raised:
            grading.compute_result(configure(), marks(listening=30.5), SCALE)
        self.assertIn("exceeds the configured maximum", str(raised.exception))

    def test_a_negative_mark_is_refused(self):
        with self.assertRaises(ValueError):
            grading.compute_result(configure(), marks(reading=-1), SCALE)

    def test_a_non_numeric_mark_is_refused(self):
        with self.assertRaises(ValueError):
            grading.compute_result(configure(), marks(reading="sixteen"), SCALE)


class ProgressionEvidenceTests(unittest.TestCase):
    progression = {"target": "next", "requires": [
        {"kind": "assessment_pass", "policy": "GEN-ENG"},
        {"kind": "attendance", "minimum_percent": 75},
        {"kind": "approval", "role": "Academic Manager"}]}

    def test_all_met_evidence_is_eligible_with_explanations(self):
        state = grading.evaluate_progression(
            self.progression, outcome="Pass", attendance_percent=90,
            approval_roles={"Academic Manager"})
        self.assertTrue(state["eligible"])
        self.assertTrue(state["approval_required"])
        self.assertEqual([row["kind"] for row in state["requirements"]],
                         ["assessment_pass", "attendance", "approval"])
        self.assertTrue(all(row["met"] for row in state["requirements"]))
        self.assertTrue(any("Attendance: needs 75%" in row
                            for row in state["reasons"]))

    def test_a_failed_assessment_blocks_eligibility(self):
        state = grading.evaluate_progression(
            self.progression, outcome="Fail", attendance_percent=90,
            approval_roles={"Academic Manager"})
        self.assertFalse(state["eligible"])
        self.assertFalse(state["requirements"][0]["met"])

    def test_an_incomplete_result_blocks_eligibility(self):
        state = grading.evaluate_progression(
            self.progression, outcome="Incomplete", attendance_percent=90,
            approval_roles={"Academic Manager"})
        self.assertFalse(state["eligible"])

    def test_attendance_below_the_configured_minimum_blocks_eligibility(self):
        state = grading.evaluate_progression(
            self.progression, outcome="Pass", attendance_percent=50,
            approval_roles={"Academic Manager"})
        self.assertFalse(state["eligible"])
        self.assertEqual(state["requirements"][1]["actual"], 50.0)

    def test_no_attendance_record_is_not_a_pass(self):
        state = grading.evaluate_progression(
            self.progression, outcome="Pass", attendance_percent=None,
            approval_roles={"Academic Manager"})
        self.assertFalse(state["eligible"])
        self.assertTrue(any("no attendance records" in row
                            for row in state["reasons"]))

    def test_the_configured_approval_role_must_be_held(self):
        state = grading.evaluate_progression(
            self.progression, outcome="Pass", attendance_percent=90,
            approval_roles={"Instructor"})
        self.assertFalse(state["eligible"])
        self.assertTrue(any("does not hold the role" in row
                            for row in state["reasons"]))

    def test_a_progression_without_approval_fails_closed(self):
        state = grading.evaluate_progression(
            {"target": "next", "requires": [
                {"kind": "assessment_pass", "policy": "GEN-ENG"}]},
            outcome="Pass", attendance_percent=100, approval_roles=set())
        self.assertFalse(state["eligible"])
        self.assertFalse(state["approval_required"])

    def test_no_progression_facet_fails_closed(self):
        with self.assertRaises(ValueError):
            grading.evaluate_progression(None, outcome="Pass",
                                         attendance_percent=90,
                                         approval_roles={"Academic Manager"})

    def test_an_unknown_requirement_is_refused(self):
        with self.assertRaises(ValueError):
            grading.evaluate_progression(
                {"target": "next", "requires": [{"kind": "vibes"}]},
                outcome="Pass", attendance_percent=90, approval_roles=set())


class RetakeTests(unittest.TestCase):
    retakes = {"max_attempts": 2, "wait_days": 14, "scope": "full",
               "governing": "latest"}

    def test_a_first_attempt_after_the_wait_is_allowed(self):
        state = grading.retake_state(self.retakes, attempts_made=1,
                                     last_attempt_on="2026-09-01",
                                     on_date="2026-09-20")
        self.assertTrue(state["allowed"])

    def test_the_wait_window_is_enforced(self):
        state = grading.retake_state(self.retakes, attempts_made=1,
                                     last_attempt_on="2026-09-01",
                                     on_date="2026-09-10")
        self.assertFalse(state["allowed"])
        self.assertEqual(state["wait_until"], "2026-09-15")

    def test_the_attempt_limit_is_enforced(self):
        state = grading.retake_state(self.retakes, attempts_made=2,
                                     last_attempt_on="2026-01-01",
                                     on_date="2026-12-01")
        self.assertFalse(state["allowed"])

    def test_no_retake_facet_fails_closed(self):
        with self.assertRaises(ValueError):
            grading.retake_state(None, attempts_made=1, last_attempt_on="",
                                 on_date="2026-09-01")

    def test_scope_and_governing_travel_with_the_permission(self):
        state = grading.retake_state(self.retakes, attempts_made=1,
                                     last_attempt_on="2026-09-01",
                                     on_date="2026-10-01")
        self.assertEqual(state["scope"], "full")
        self.assertEqual(state["governing"], "latest")


class SnapshotTests(unittest.TestCase):
    def test_the_snapshot_carries_the_policy_and_scale_evidence(self):
        snapshot = grading.compute_result(configure(), marks(), SCALE)
        self.assertEqual(snapshot["grading_scale_intervals"],
                         [{"threshold": 85.0, "grade_code": "A"},
                          {"threshold": 70.0, "grade_code": "B"},
                          {"threshold": 55.0, "grade_code": "C"}])
        self.assertEqual(snapshot["weights"],
                         {"LISTENING": 60.0, "READING": 40.0})

    def test_the_digest_is_a_sha256_of_the_canonical_snapshot(self):
        snapshot = grading.compute_result(configure(), marks(), SCALE)
        self.assertEqual(grading.snapshot_digest(snapshot),
                         policy.digest(snapshot))
        self.assertEqual(len(grading.snapshot_digest(snapshot)), 64)

    def test_decimal_inputs_from_a_stored_snapshot_still_compute(self):
        snapshot = grading.compute_result(
            configure(), {"LISTENING": {"mark": Decimal("24")},
                       "READING": {"mark": Decimal("16.0")}}, SCALE)
        self.assertEqual(snapshot["overall_percent"], 80.0)


if __name__ == "__main__":
    unittest.main()

"""Synthetic progression journeys: eligibility, decisions, overrides, intake.

Progression is where an academic result becomes a right to move on, so these
tests pin the whole governed path with the REAL ``academic.progression``
module: the configured policy, the required approval role, one decision per
result, retake limits, senior overrides that never rewrite eligibility, and
the native Program Enrollment gate that refuses an unauthorized promotion.
"""
import json
import unittest

from tests.academic._harness import ValidationError
from tests.academic.test_assessment_workflow import (GENERAL_MANAGER, INSTRUCTOR,
                                                     MANAGER, OUTSIDER, AcademicCase)

PROGRAMME_DIRECTOR = "programme.director@example.test"


class ProgressionCase(AcademicCase):
    def setUp(self):
        super().setUp()
        self.h.grant(PROGRAMME_DIRECTOR, ["Academic Manager", "Programme Director"])
        self.h.store.seed("User", {"email": PROGRAMME_DIRECTOR, "enabled": 1},
                          name=PROGRAMME_DIRECTOR)
        self.h.store.seed("Program Enrollment",
                          {"student": "SYN-STU-1", "program": "SYN-GEN-ENG",
                           "academic_year": "SYN-AY-2026", "docstatus": 1},
                          name="PE-1")

    def results(self, **kwargs):
        self.published_book(**kwargs)
        return {row["student"]: row for row in self.h.store.find("TH Academic Result")}

    def decide(self, result, decision="Promote", reason="Annual progression review",
               actor=MANAGER, key=None):
        self.h.acting_as(actor)
        return self.h.progression.decide_progression(
            key or f"key-decide-{decision}", result, decision, reason)

    def fail_the_class(self, **kwargs):
        book = self.book(**kwargs)
        self.h.record(book["name"], self.h.full_marks(listening=12.0, reading=6.0))
        self.h.acting_as(INSTRUCTOR)
        self.h.assessment.submit_assessment_book("key-fail-submit", book["name"])
        self.h.acting_as(MANAGER)
        self.h.assessment.review_assessment_book("key-fail-review", book["name"], "Review")
        self.h.assessment.approve_assessment_book("key-fail-approve", book["name"])
        self.h.assessment.publish_assessment_results("key-fail-publish", book["name"])
        return {row["student"]: row for row in self.h.store.find("TH Academic Result")}


class DecisionTests(ProgressionCase):
    def test_promote_records_the_next_level_and_the_evidence(self):
        result = self.results()["SYN-STU-1"]
        decision = self.decide(result["name"])
        self.assertEqual(decision["decision"], "Promote")
        self.assertEqual(decision["status"], "Approved")
        self.assertEqual(decision["from_level"], "SYN-GE-1")
        self.assertEqual(decision["to_level"], "SYN-GE-2")
        self.assertTrue(decision["eligible"])
        stored = self.h.store.load("TH Progression Decision", decision["name"])
        self.assertEqual(stored.get("decided_by"), MANAGER)
        self.assertEqual(len(stored.get("eligibility_digest")), 64)
        snapshot = json.loads(stored.get("eligibility_json"))
        self.assertEqual(snapshot["algorithm"], "th-progression-v1")
        self.assertEqual([row["kind"] for row in snapshot["eligibility"]["requirements"]],
                         ["assessment_pass", "attendance", "approval"])
        self.assertFalse(snapshot["override_used"])

    def test_a_progression_decision_never_enrolls_by_itself(self):
        before = len(self.h.store.find("Program Enrollment"))
        result = self.results()["SYN-STU-1"]
        self.decide(result["name"])
        self.assertEqual(len(self.h.store.find("Program Enrollment")), before)

    def test_promote_is_refused_for_a_failed_result(self):
        result = self.fail_the_class()["SYN-STU-1"]
        with self.assertRaises(ValidationError) as ctx:
            self.decide(result["name"])
        self.assertIn("Progression is not eligible", str(ctx.exception))
        self.assertIn("outcome Fail", str(ctx.exception))

    def test_repeat_is_the_governed_response_to_a_failure(self):
        result = self.fail_the_class()["SYN-STU-1"]
        decision = self.decide(result["name"], decision="Repeat",
                               reason="Student repeats the level next term")
        self.assertEqual(decision["decision"], "Repeat")
        self.assertEqual(decision["to_level"], "SYN-GE-1")
        self.assertFalse(decision["eligible"])

    def test_a_permitted_retake_is_recorded_without_promoting(self):
        # The mission policy bounds the facet: at most one retake and at
        # least seven days after publication, whatever the facet says. The
        # facet here says wait_days 0 / max_attempts 3, so the mission
        # floor/cap govern instead — the decision is allowed only once
        # seven days have elapsed since publication (2026-10-24), and it
        # does not promote.
        self.h.seed_policy("SYN-GEN-ENG", effective_from="2026-10-01",
                           retakes={"max_attempts": 3, "wait_days": 0,
                                    "scope": "full", "governing": "latest"})
        result = self.fail_the_class(effective_from="2026-10-01")["SYN-STU-1"]
        self.h.today = "2026-10-31"
        decision = self.decide(result["name"], decision="Retake",
                               reason="One permitted retake of the level test")
        self.assertEqual(decision["decision"], "Retake")
        self.assertEqual(decision["to_level"], "SYN-GE-1")
        self.assertFalse(self.h.progression.next_level_eligibility(
            "SYN-STU-1", "SYN-GEN-ENG-2")["eligible"])

    def test_retake_is_refused_while_the_wait_window_is_open(self):
        self.h.seed_policy("SYN-GEN-ENG", effective_from="2026-10-01",
                           retakes={"max_attempts": 2, "wait_days": 14,
                                    "scope": "full", "governing": "latest"})
        result = self.fail_the_class(effective_from="2026-10-01")["SYN-STU-1"]
        with self.assertRaises(ValidationError) as ctx:
            self.decide(result["name"], decision="Retake", reason="Immediate retake")
        self.assertIn("retake wait ends on", str(ctx.exception))

    def test_retake_fails_closed_without_configured_retake_rules(self):
        self.h.seed_policy("SYN-GEN-ENG", effective_from="2026-10-01",
                           facets_override={"retakes": None})
        result = self.fail_the_class(effective_from="2026-10-01")["SYN-STU-1"]
        with self.assertRaises(ValidationError) as ctx:
            self.decide(result["name"], decision="Retake",
                        reason="Retake with no configured rules")
        self.assertIn("configures no retake rules", str(ctx.exception))

    def test_only_one_decision_per_result(self):
        result = self.results()["SYN-STU-1"]
        self.decide(result["name"])
        with self.assertRaises(ValidationError) as ctx:
            self.decide(result["name"], key="key-decide-again")
        self.assertIn("duplicate progression is refused", str(ctx.exception))

    def test_a_decision_on_a_superseded_result_is_refused(self):
        book = self.published_book()
        first = self.h.store.find("TH Academic Result",
                                  filters={"student": "SYN-STU-1"})[0]
        self.h.acting_as(MANAGER)
        self.h.assessment.correct_published_result(
            "key-revise-progression", book["name"], "SYN-STU-1",
            "Moderation changed the outcome",
            marks=[{"component": "READING", "mark": 12}])
        with self.assertRaises(ValidationError) as ctx:
            self.decide(first["name"])
        self.assertIn("is Superseded", str(ctx.exception))

    def test_correcting_an_approved_result_revokes_next_level_eligibility(self):
        book = self.published_book()
        first = self.h.store.find("TH Academic Result",
                                  filters={"student": "SYN-STU-1"})[0]
        decision = self.decide(first["name"], key="key-decide-before-correction")
        self.assertEqual(decision["decision"], "Promote")
        self.assertTrue(self.h.progression.next_level_eligibility(
            "SYN-STU-1", "SYN-GEN-ENG-2")["eligible"])
        self.h.acting_as(MANAGER)
        self.h.assessment.correct_published_result(
            "key-revise-after-promotion", book["name"], "SYN-STU-1",
            "Correct the published mark and withdraw the former evidence",
            marks=[{"component": "READING", "mark": 12}])
        eligibility = self.h.progression.next_level_eligibility(
            "SYN-STU-1", "SYN-GEN-ENG-2")
        self.assertTrue(eligibility["required"])
        self.assertFalse(eligibility["eligible"])
        self.assertIn("superseded", " ".join(eligibility["reasons"]).lower())
        with self.assertRaises(ValidationError):
            self.h.progression.enrollment_gate("SYN-STU-1", "SYN-GEN-ENG-2")

    def test_progression_requires_the_policy_configured_approval_role(self):
        self.h.seed_policy(
            "SYN-DIRECTOR", levels=("SYN-GE-1",),
            progression={"target": "next", "requires": [
                {"kind": "assessment_pass", "policy": "SYN-DIRECTOR"},
                {"kind": "approval", "role": "Programme Director"}]})
        result = self.results(policy="SYN-DIRECTOR")["SYN-STU-1"]
        with self.assertRaises(ValidationError) as ctx:
            self.decide(result["name"])
        self.assertIn("Programme Director", str(ctx.exception))
        allowed = self.decide(result["name"], actor=PROGRAMME_DIRECTOR,
                              key="key-decide-director")
        self.assertEqual(allowed["decision"], "Promote")

    def test_an_unconfigured_progression_facet_fails_closed(self):
        self.seed_policy_without_progression()
        result = self.results(policy="SYN-NO-PROGRESSION")["SYN-STU-1"]
        with self.assertRaises(ValidationError) as ctx:
            self.decide(result["name"])
        self.assertIn("configures no progression rules", str(ctx.exception))

    def seed_policy_without_progression(self):
        self.h.seed_policy("SYN-NO-PROGRESSION", levels=("SYN-GE-1",),
                           facets_override={"progression": None})

    def test_promote_without_a_configured_next_level_is_refused(self):
        self.h.store.docs["TH Program Level"]["SYN-GE-1"]["next_level"] = ""
        result = self.results()["SYN-STU-1"]
        with self.assertRaises(ValidationError) as ctx:
            self.decide(result["name"])
        self.assertIn("record Complete instead", str(ctx.exception))

    def test_complete_when_the_catalog_has_a_next_level_is_refused(self):
        result = self.results()["SYN-STU-1"]
        with self.assertRaises(ValidationError) as ctx:
            self.decide(result["name"], decision="Complete",
                        reason="Believed the programme ended")
        self.assertIn("record Promote instead", str(ctx.exception))

    def test_instructors_and_outsiders_cannot_decide(self):
        result = self.results()["SYN-STU-1"]
        for actor in (INSTRUCTOR, OUTSIDER):
            with self.assertRaises(Exception):
                self.decide(result["name"], actor=actor,
                            key=f"key-decide-{actor}")

    def test_a_decision_reason_is_mandatory(self):
        result = self.results()["SYN-STU-1"]
        with self.assertRaises(ValidationError):
            self.decide(result["name"], reason=" ")


class OverrideTests(ProgressionCase):
    def test_a_senior_override_records_the_unmet_requirements(self):
        result = self.fail_the_class()["SYN-STU-1"]
        self.h.acting_as(GENERAL_MANAGER)
        decision = self.h.progression.override_progression(
            "key-override-1", result["name"], "Promote",
            "Owner-approved compassionate progression")
        self.assertTrue(decision["override_used"])
        self.assertFalse(decision["eligible"])
        self.assertEqual(decision["to_level"], "SYN-GE-2")
        stored = self.h.store.load("TH Progression Decision", decision["name"])
        snapshot = json.loads(stored.eligibility_json)
        self.assertTrue(snapshot["override_used"])
        self.assertTrue(snapshot["overridden_requirements"])
        self.assertEqual(stored.get("override_reason"),
                         "Owner-approved compassionate progression")

    def test_an_override_is_refused_when_the_requirements_are_met(self):
        # The policy names the General Manager as the approving role, so the
        # senior actor's own approval satisfies the last requirement and there
        # is nothing left to override.
        self.h.seed_policy("SYN-GM-APPROVES", levels=("SYN-GE-1",),
                           progression={"target": "next", "requires": [
                               {"kind": "assessment_pass",
                                "policy": "SYN-GM-APPROVES"},
                               {"kind": "attendance", "minimum_percent": 75},
                               {"kind": "approval", "role": "General Manager"}]})
        result = self.results(policy="SYN-GM-APPROVES")["SYN-STU-1"]
        self.h.acting_as(GENERAL_MANAGER)
        with self.assertRaises(ValidationError) as ctx:
            self.h.progression.override_progression(
                "key-override-unneeded", result["name"], "Promote",
                "No reason to override")
        self.assertIn("already met", str(ctx.exception))

    def test_an_academic_manager_cannot_override(self):
        result = self.fail_the_class()["SYN-STU-1"]
        self.h.acting_as(MANAGER)
        with self.assertRaises(Exception):
            self.h.progression.override_progression(
                "key-override-manager", result["name"], "Promote",
                "Manager tries to override")

    def test_an_override_is_not_available_for_repeat(self):
        result = self.fail_the_class()["SYN-STU-1"]
        self.h.acting_as(GENERAL_MANAGER)
        with self.assertRaises(ValidationError) as ctx:
            self.h.progression.override_progression(
                "key-override-repeat", result["name"], "Repeat",
                "No override needed")
        self.assertIn("require no override", str(ctx.exception))


class EnrollmentEligibilityTests(ProgressionCase):
    def test_a_first_enrollment_is_not_gated(self):
        state = self.h.progression.next_level_eligibility("SYN-STU-2", "SYN-GEN-ENG")
        self.assertFalse(state["required"])
        self.assertTrue(state["eligible"])
        self.assertEqual(self.h.progression.enrollment_gate("SYN-STU-2",
                                                            "SYN-GEN-ENG")["eligible"],
                         True)

    def test_an_unmapped_program_is_not_gated(self):
        state = self.h.progression.next_level_eligibility("SYN-STU-1", "SYN-NOT-MAPPED")
        self.assertFalse(state["required"])
        self.assertIn("not mapped to a program level", state["reasons"][0])

    def test_a_successor_level_needs_an_approved_decision(self):
        state = self.h.progression.next_level_eligibility("SYN-STU-1", "SYN-GEN-ENG-2")
        self.assertTrue(state["required"])
        self.assertFalse(state["eligible"])
        self.assertIn("No approved progression decision", state["reasons"][0])
        with self.assertRaises(ValidationError) as ctx:
            self.h.progression.enrollment_gate("SYN-STU-1", "SYN-GEN-ENG-2")
        self.assertIn("is refused", str(ctx.exception))

    def test_an_approved_promotion_admits_the_successor_level(self):
        result = self.results()["SYN-STU-1"]
        self.decide(result["name"])
        state = self.h.progression.next_level_eligibility("SYN-STU-1", "SYN-GEN-ENG-2")
        self.assertTrue(state["required"])
        self.assertTrue(state["eligible"])
        self.assertEqual(state["level"], "SYN-GE-2")
        self.h.progression.enrollment_gate("SYN-STU-1", "SYN-GEN-ENG-2")

    def test_a_repeat_decision_does_not_admit_the_successor_level(self):
        result = self.fail_the_class()["SYN-STU-1"]
        self.decide(result["name"], decision="Repeat", reason="Repeat the level")
        state = self.h.progression.next_level_eligibility("SYN-STU-1", "SYN-GEN-ENG-2")
        self.assertFalse(state["eligible"])
        self.assertIn("records Repeat", state["reasons"][0])

    def test_a_student_without_a_prior_level_enrollment_is_not_gated(self):
        state = self.h.progression.next_level_eligibility("SYN-STU-3", "SYN-GEN-ENG-2")
        self.assertFalse(state["required"])
        self.assertTrue(state["eligible"])

    def test_progression_state_projects_results_and_decisions(self):
        result = self.results()["SYN-STU-1"]
        self.decide(result["name"])
        state = self.h.progression.progression_state("SYN-STU-1", "SYN-GEN-ENG-2")
        self.assertEqual(len(state["results"]), 1)
        self.assertEqual(state["decisions"][0]["decision"], "Promote")
        self.assertTrue(state["next_level"]["eligible"])


class HistoricalProgressionTests(ProgressionCase):
    def test_a_later_policy_does_not_change_an_existing_decision(self):
        result = self.results()["SYN-STU-1"]
        decision = self.decide(result["name"])
        before = self.h.store.load("TH Progression Decision", decision["name"])
        digest_before = before.get("eligibility_digest")
        self.h.seed_policy("SYN-GEN-ENG", effective_from="2026-10-01",
                           progression={"target": "next", "requires": [
                               {"kind": "assessment_pass", "policy": "SYN-GEN-ENG"},
                               {"kind": "attendance", "minimum_percent": 100},
                               {"kind": "approval", "role": "Academic Manager"}]})
        after = self.h.store.load("TH Progression Decision", decision["name"])
        self.assertEqual(after.get("eligibility_digest"), digest_before)
        self.assertEqual(after.get("policy_effective_from"), "2026-09-01")
        snapshot = json.loads(after.eligibility_json)
        attendance = [row for row in snapshot["eligibility"]["requirements"]
                      if row["kind"] == "attendance"][0]
        self.assertEqual(attendance["target"], 75)

    def test_a_decision_is_judged_against_the_results_pinned_version(self):
        result = self.results()["SYN-STU-2"]  # 50% attendance
        self.h.seed_policy("SYN-GEN-ENG", effective_from="2026-10-01",
                           progression={"target": "next", "requires": [
                               {"kind": "assessment_pass", "policy": "SYN-GEN-ENG"},
                               {"kind": "attendance", "minimum_percent": 10},
                               {"kind": "approval", "role": "Academic Manager"}]})
        with self.assertRaises(ValidationError) as ctx:
            self.decide(result["name"])
        self.assertIn("Attendance", str(ctx.exception))
        self.assertIn("needs 75%", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

"""Adversarial retake and best-attempt progression tests.

These tests pin the mission policy on top of the REAL academic modules
(``assessment``, ``progression``, ``grading``) against the scripted store:
at most one retake, only after a failed first attempt, at least seven days
after the original publication, no book bypassing those rules, best valid
published attempt governing progression, and original scores never changed
or deleted. A correction publishes a new superseding revision; it never
resets the retake count and never creates a new attempt ordinal.
"""
import unittest

from tests.academic._harness import ValidationError, load_pure_modules
from tests.academic.test_assessment_workflow import (
    GENERAL_MANAGER, INSTRUCTOR, MANAGER, OUTSIDER, AcademicCase)

grading = load_pure_modules("academic.grading")

# Harness site date at publication: every published result in these tests
# carries published_on 2026-10-24 12:00:00 unless the test moves the clock.
PUBLISHED = "2026-10-24"
DAY_7 = "2026-10-31"
DAY_14 = "2026-11-07"


def marks_for(scores):
    """scores: {student: (listening, reading)} -> mark rows for all components."""
    rows = []
    for student, (listening, reading) in scores.items():
        rows.append({"student": student, "component": "LISTENING", "mark": listening})
        rows.append({"student": student, "component": "READING", "mark": reading})
    return rows


PASS = (24.0, 16.0)      # 80% overall
BETTER = (27.0, 18.0)    # 90% overall
WORSE_FAIL = (15.0, 10.0)  # 50% overall
FAIL = (12.0, 6.0)       # 36% overall


class RetakeCase(AcademicCase):
    def setUp(self):
        super().setUp()
        self.counter = 0
        # Mission-policy retakes facet: one retake, seven-day wait, best governs.
        self.h.seed_policy("SYN-GEN-ENG", effective_from="2026-10-01",
                           retakes={"max_attempts": 2, "wait_days": 7,
                                    "scope": "full", "governing": "best"})
        # STU-1 holds a predecessor-level enrollment, so next-level
        # eligibility is genuinely gated (without it the gate returns
        # "not required" and every eligibility assertion would be vacuous).
        self.h.store.seed("Program Enrollment",
                          {"student": "SYN-STU-1", "program": "SYN-GEN-ENG",
                           "academic_year": "SYN-AY-2026", "docstatus": 1},
                          name="PE-1")

    def key(self, label):
        self.counter += 1
        return f"key-retake-{label}-{self.counter}"

    def publish(self, scores, effective_from="2026-10-01", policy="SYN-GEN-ENG"):
        """Open, mark, submit, review, approve and publish one book."""
        book = self.book(key=self.key("open"), effective_from=effective_from,
                         policy=policy)
        self.h.record(book["name"], marks_for(scores), key=self.key("marks"))
        self.h.acting_as(INSTRUCTOR)
        self.h.assessment.submit_assessment_book(self.key("submit"), book["name"])
        self.h.acting_as(MANAGER)
        self.h.assessment.review_assessment_book(self.key("review"), book["name"],
                                                 "Review")
        self.h.assessment.approve_assessment_book(self.key("approve"), book["name"])
        self.h.assessment.publish_assessment_results(self.key("publish"), book["name"])
        return book

    def results_for(self, student):
        return {row["attempt"]: row for row in
                self.h.store.find("TH Academic Result",
                                  filters={"student": student, "status": "Published"})}

    def decide(self, result, decision, reason, actor=MANAGER):
        self.h.acting_as(actor)
        return self.h.progression.decide_progression(
            self.key("decide"), result, decision, reason)

    def fail_book(self):
        return self.publish({"SYN-STU-1": FAIL, "SYN-STU-2": FAIL,
                             "SYN-STU-3": FAIL})

    def retake_decision(self, result, reason="One permitted retake"):
        return self.decide(result, "Retake", reason)


class PureSelectionTests(unittest.TestCase):
    def attempt(self, name, percent, status="Published", published="2026-10-24",
                attempt=1):
        return {"name": name, "status": status, "outcome": "Pass",
                "overall_percent": percent, "published_on": published,
                "attempt": attempt}

    def test_best_is_the_highest_published_percent(self):
        rows = [self.attempt("R1", 80.0, attempt=1),
                self.attempt("R2", 90.0, attempt=2),
                self.attempt("R3", 70.0, attempt=3)]
        self.assertEqual(grading.select_best_attempt(rows)["name"], "R2")

    def test_superseded_draft_and_cancelled_attempts_are_never_selected(self):
        rows = [self.attempt("OLD", 99.0, status="Superseded", attempt=1),
                self.attempt("DRAFT", 98.0, status="Draft", attempt=2),
                self.attempt("CANC", 97.0, status="Cancelled", attempt=3),
                self.attempt("LIVE", 60.0, attempt=4)]
        self.assertEqual(grading.select_best_attempt(rows)["name"], "LIVE")

    def test_an_attempt_without_a_percent_is_not_valid(self):
        rows = [self.attempt("NOPCT", None, attempt=1),
                self.attempt("LIVE", 55.0, attempt=2)]
        self.assertEqual(grading.select_best_attempt(rows)["name"], "LIVE")

    def test_ties_go_to_the_earliest_published_attempt(self):
        rows = [self.attempt("LATER", 80.0, published="2026-11-01", attempt=2),
                self.attempt("EARLIER", 80.0, published="2026-10-24", attempt=1)]
        self.assertEqual(grading.select_best_attempt(rows)["name"], "EARLIER")

    def test_no_valid_attempt_returns_none(self):
        self.assertIsNone(grading.select_best_attempt(
            [self.attempt("OLD", 99.0, status="Superseded")]))
        self.assertIsNone(grading.select_best_attempt([]))


class PureRetakeGateTests(unittest.TestCase):
    def gate(self, **overrides):
        kwargs = dict(outcome="Fail", attempts_made=1,
                      last_attempt_on=PUBLISHED, on_date=DAY_7)
        kwargs.update(overrides)
        return grading.retake_gate({"max_attempts": 2, "wait_days": 7,
                                    "scope": "full", "governing": "best"}, **kwargs)

    def test_a_pass_is_never_retaken(self):
        state = self.gate(outcome="Pass")
        self.assertFalse(state["allowed"])
        self.assertIn("failed attempt", state["reason"])

    def test_six_days_after_publication_is_refused(self):
        state = self.gate(on_date="2026-10-30")
        self.assertFalse(state["allowed"])
        self.assertEqual(state["wait_until"], DAY_7)

    def test_exactly_seven_days_after_publication_is_allowed(self):
        self.assertTrue(self.gate()["allowed"])

    def test_the_seven_day_floor_overrides_a_shorter_facet_wait(self):
        state = grading.retake_gate({"max_attempts": 2, "wait_days": 0,
                                     "scope": "full", "governing": "best"},
                                    outcome="Fail", attempts_made=1,
                                    last_attempt_on=PUBLISHED, on_date="2026-10-30")
        self.assertFalse(state["allowed"])
        self.assertEqual(state["wait_until"], DAY_7)

    def test_a_stricter_facet_wait_still_governs(self):
        state = grading.retake_gate({"max_attempts": 2, "wait_days": 14,
                                     "scope": "full", "governing": "best"},
                                    outcome="Fail", attempts_made=1,
                                    last_attempt_on=PUBLISHED, on_date=DAY_7)
        self.assertFalse(state["allowed"])
        self.assertEqual(state["wait_until"], DAY_14)

    def test_the_one_retake_cap_overrides_a_looser_facet_limit(self):
        state = self.gate(attempts_made=2)
        self.assertFalse(state["allowed"])
        self.assertIn("permitted attempts", state["reason"])

    def test_a_prior_retake_decision_blocks_a_second(self):
        state = self.gate(prior_retake=True)
        self.assertFalse(state["allowed"])
        self.assertIn("already been approved", state["reason"])

    def test_an_existing_retake_attempt_blocks_a_further_one(self):
        state = self.gate(retake_exists=True)
        self.assertFalse(state["allowed"])
        self.assertIn("already exists", state["reason"])

    def test_no_retake_facet_fails_closed(self):
        with self.assertRaises(ValueError):
            grading.retake_gate(None, outcome="Fail", attempts_made=1,
                                last_attempt_on=PUBLISHED, on_date=DAY_7)


class DecisionGateTests(RetakeCase):
    def test_a_retake_after_a_pass_is_refused(self):
        self.publish({"SYN-STU-1": PASS, "SYN-STU-2": PASS,
                             "SYN-STU-3": PASS})
        result = self.results_for("SYN-STU-1")[1]
        with self.assertRaises(ValidationError) as ctx:
            self.retake_decision(result["name"])
        self.assertIn("failed attempt", str(ctx.exception))

    def test_an_early_retake_decision_is_refused(self):
        self.fail_book()
        result = self.results_for("SYN-STU-1")[1]
        with self.assertRaises(ValidationError) as ctx:
            self.retake_decision(result["name"])
        self.assertIn("retake wait ends on", str(ctx.exception))
        self.assertIn(DAY_7, str(ctx.exception))

    def test_a_retake_decision_on_exactly_day_seven_is_allowed(self):
        self.fail_book()
        result = self.results_for("SYN-STU-1")[1]
        self.h.today = DAY_7
        decision = self.retake_decision(result["name"])
        self.assertEqual(decision["decision"], "Retake")
        self.assertEqual(decision["to_level"], "SYN-GE-1")

    def test_a_second_retake_decision_on_the_same_result_is_refused(self):
        self.fail_book()
        result = self.results_for("SYN-STU-1")[1]
        self.h.today = DAY_7
        self.retake_decision(result["name"])
        with self.assertRaises(ValidationError) as ctx:
            self.retake_decision(result["name"], reason="Second retake")
        self.assertIn("already recorded", str(ctx.exception))

    def test_a_second_retake_decision_after_a_correction_is_refused(self):
        book = self.fail_book()
        result = self.results_for("SYN-STU-1")[1]
        self.h.today = DAY_7
        self.retake_decision(result["name"])
        self.h.acting_as(MANAGER)
        self.h.assessment.correct_published_result(
            self.key("correct"), book["name"], "SYN-STU-1",
            "Moderation adjusted a mark but the outcome is still Fail",
            marks=[{"component": "READING", "mark": 8.0}])
        revised = self.results_for("SYN-STU-1")[1]
        self.assertNotEqual(revised["name"], result["name"])
        self.assertEqual(revised["outcome"], "Fail")
        with self.assertRaises(ValidationError) as ctx:
            self.retake_decision(revised["name"], reason="Retake after correction")
        self.assertIn("already been approved", str(ctx.exception))

    def test_unauthorized_actors_cannot_record_a_retake_decision(self):
        self.fail_book()
        result = self.results_for("SYN-STU-1")[1]
        self.h.today = DAY_7
        for actor in (INSTRUCTOR, OUTSIDER, GENERAL_MANAGER):
            with self.assertRaises(Exception):
                self.decide(result["name"], "Retake", "Unauthorized retake",
                            actor=actor)

    def test_an_override_cannot_be_used_for_a_retake(self):
        self.fail_book()
        result = self.results_for("SYN-STU-1")[1]
        self.h.acting_as(GENERAL_MANAGER)
        with self.assertRaises(ValidationError) as ctx:
            self.h.progression.override_progression(
                self.key("override"), result["name"], "Retake",
                "Override used as a retake")
        self.assertIn("require no override", str(ctx.exception))


class BookGateTests(RetakeCase):
    def test_a_further_book_without_any_retake_decision_is_refused(self):
        self.fail_book()
        self.h.today = DAY_7
        with self.assertRaises(ValidationError) as ctx:
            self.book(key=self.key("open2"))
        self.assertIn("No approved retake", str(ctx.exception))

    def test_a_further_book_after_a_pass_is_refused(self):
        self.publish({"SYN-STU-1": PASS, "SYN-STU-2": PASS, "SYN-STU-3": PASS})
        self.h.today = DAY_7
        with self.assertRaises(ValidationError) as ctx:
            self.book(key=self.key("open2"))
        self.assertIn("No approved retake", str(ctx.exception))

    def test_a_second_book_under_one_retake_decision_is_refused(self):
        self.fail_book()
        result = self.results_for("SYN-STU-1")[1]
        self.h.today = DAY_7
        self.retake_decision(result["name"])
        second = self.book(key=self.key("open2"))
        self.assertEqual(second["attempt"], 2)
        with self.assertRaises(ValidationError) as ctx:
            self.book(key=self.key("open3"))
        self.assertIn("already in progress", str(ctx.exception))

    def test_a_preopened_book_cannot_publish_as_an_unauthorized_retake(self):
        first = self.book(key=self.key("open1"))
        second = self.book(key=self.key("open2"))
        # Publish the first book (all fail); the second book was opened
        # before any result existed, so it opened freely — but publishing
        # it now would be an unauthorized further attempt.
        self.h.record(first["name"], self.h.full_marks(listening=12.0, reading=6.0),
                      key=self.key("marks1"))
        self.h.acting_as(INSTRUCTOR)
        self.h.assessment.submit_assessment_book(self.key("submit1"), first["name"])
        self.h.acting_as(MANAGER)
        self.h.assessment.review_assessment_book(self.key("review1"), first["name"],
                                                 "Review")
        self.h.assessment.approve_assessment_book(self.key("approve1"), first["name"])
        self.h.assessment.publish_assessment_results(self.key("publish1"),
                                                     first["name"])
        self.h.record(second["name"], self.h.full_marks(), key=self.key("marks2"))
        self.h.acting_as(INSTRUCTOR)
        self.h.assessment.submit_assessment_book(self.key("submit2"), second["name"])
        self.h.acting_as(MANAGER)
        self.h.assessment.review_assessment_book(self.key("review2"), second["name"],
                                                 "Review")
        self.h.assessment.approve_assessment_book(self.key("approve2"), second["name"])
        with self.assertRaises(ValidationError) as ctx:
            self.h.assessment.publish_assessment_results(self.key("publish2"),
                                                         second["name"])
        self.assertIn("No approved retake", str(ctx.exception))

    def test_a_book_gate_wait_is_enforced_from_the_original_publication(self):
        # A separate policy with a 14-day wait governs this book, so the
        # book gate must refuse before 2026-11-07 and allow on it, even
        # though a Retake decision is already recorded in the store (the
        # decision is seeded directly to isolate the book gate from the
        # decision gate, which would itself refuse before day 14).
        self.h.seed_policy("SYN-WAIT14", effective_from="2026-10-01",
                           retakes={"max_attempts": 2, "wait_days": 14,
                                    "scope": "full", "governing": "best"})
        self.publish({"SYN-STU-1": FAIL, "SYN-STU-2": FAIL, "SYN-STU-3": FAIL},
                     policy="SYN-WAIT14")
        result = self.results_for("SYN-STU-1")[1]
        self.h.store.seed("TH Progression Decision",
                          {"student": "SYN-STU-1", "student_group": "SYN-GRP-1",
                           "academic_result": result["name"], "decision": "Retake",
                           "status": "Approved", "from_level": "SYN-GE-1",
                           "to_level": "SYN-GE-1", "policy": "SYN-WAIT14",
                           "policy_effective_from": "2026-10-01",
                           "decided_by": MANAGER, "decided_on": "2026-11-03"},
                          name="DEC-SEED-1")
        self.h.today = "2026-11-03"
        with self.assertRaises(ValidationError) as ctx:
            self.book(key=self.key("open2"), policy="SYN-WAIT14",
                      effective_from="2026-10-01")
        self.assertIn("retake wait ends on", str(ctx.exception))
        self.h.today = DAY_14
        second = self.book(key=self.key("open2"), policy="SYN-WAIT14",
                           effective_from="2026-10-01")
        self.assertEqual(second["attempt"], 2)


class LegitimateRetakeTests(RetakeCase):
    def test_a_legitimate_single_retake_works_end_to_end(self):
        self.fail_book()
        result = self.results_for("SYN-STU-1")[1]
        self.h.today = DAY_7
        self.retake_decision(result["name"])
        self.publish({"SYN-STU-1": PASS, "SYN-STU-2": PASS, "SYN-STU-3": PASS})
        retaken = self.results_for("SYN-STU-1")[2]
        self.assertEqual(retaken["outcome"], "Pass")
        decision = self.decide(retaken["name"], "Promote", "Retake passed")
        self.assertEqual(decision["decision"], "Promote")
        self.assertEqual(decision["to_level"], "SYN-GE-2")
        self.assertTrue(self.h.progression.next_level_eligibility(
            "SYN-STU-1", "SYN-GEN-ENG-2")["eligible"])

    def test_a_third_attempt_is_refused_even_after_a_passed_retake(self):
        self.fail_book()
        result = self.results_for("SYN-STU-1")[1]
        self.h.today = DAY_7
        self.retake_decision(result["name"])
        self.publish({"SYN-STU-1": PASS, "SYN-STU-2": PASS, "SYN-STU-3": PASS})
        retaken = self.results_for("SYN-STU-1")[2]
        with self.assertRaises(ValidationError) as ctx:
            self.retake_decision(retaken["name"], reason="Second retake")
        self.assertIn("failed attempt", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            self.book(key=self.key("open3"))
        self.assertIn("No approved retake", str(ctx.exception))


class BestAttemptTests(RetakeCase):
    def _two_attempts(self, first_scores, second_scores):
        """Book 1, then a book 2 authorized by STU-2's retake decision."""
        self.publish(first_scores)
        stu2_first = self.results_for("SYN-STU-2")[1]
        self.h.today = DAY_7
        self.retake_decision(stu2_first["name"], reason="STU-2 retakes")
        self.publish(second_scores)
        return self.results_for("SYN-STU-1")

    def test_a_worse_later_attempt_cannot_be_promoted(self):
        results = self._two_attempts(
            {"SYN-STU-1": PASS, "SYN-STU-2": FAIL, "SYN-STU-3": PASS},
            {"SYN-STU-1": WORSE_FAIL, "SYN-STU-2": PASS, "SYN-STU-3": PASS})
        best = results[1]
        worse = results[2]
        self.assertEqual(best["outcome"], "Pass")
        self.assertEqual(worse["outcome"], "Fail")
        with self.assertRaises(ValidationError) as ctx:
            self.decide(worse["name"], "Promote", "Promote the worse attempt")
        self.assertIn(best["name"], str(ctx.exception))
        self.assertIn("best published attempt", str(ctx.exception))
        decision = self.decide(best["name"], "Promote", "Promote the best attempt")
        self.assertEqual(decision["decision"], "Promote")
        self.assertTrue(self.h.progression.next_level_eligibility(
            "SYN-STU-1", "SYN-GEN-ENG-2")["eligible"])

    def test_eligibility_follows_the_best_attempt_not_the_latest_decision(self):
        # Promote STU-1 on the first (then best) attempt BEFORE the retake
        # book for STU-2 is published; only afterwards does a better
        # attempt appear for STU-1.
        self.publish({"SYN-STU-1": PASS, "SYN-STU-2": FAIL, "SYN-STU-3": PASS})
        best_first = self.results_for("SYN-STU-1")[1]
        stu2_first = self.results_for("SYN-STU-2")[1]
        self.h.today = DAY_7
        decision = self.decide(best_first["name"], "Promote",
                               "Promote before the retake book")
        self.assertEqual(decision["decision"], "Promote")
        self.assertTrue(self.h.progression.next_level_eligibility(
            "SYN-STU-1", "SYN-GEN-ENG-2")["eligible"])
        self.retake_decision(stu2_first["name"], reason="STU-2 retakes")
        self.publish({"SYN-STU-1": BETTER, "SYN-STU-2": PASS, "SYN-STU-3": PASS})
        # A better attempt is now published with no decision on it: the
        # earlier Promote no longer admits, because eligibility follows
        # the best attempt's decision, not the latest decision.
        state = self.h.progression.next_level_eligibility(
            "SYN-STU-1", "SYN-GEN-ENG-2")
        self.assertFalse(state["eligible"])
        self.assertIn("best published attempt", " ".join(state["reasons"]))
        with self.assertRaises(ValidationError):
            self.decide(best_first["name"], "Promote", "Promote the old best")
        better = self.results_for("SYN-STU-1")[2]
        self.decide(better["name"], "Promote", "Promote the new best attempt")
        self.assertTrue(self.h.progression.next_level_eligibility(
            "SYN-STU-1", "SYN-GEN-ENG-2")["eligible"])

    def test_a_repeat_on_a_worse_attempt_is_refused(self):
        results = self._two_attempts(
            {"SYN-STU-1": PASS, "SYN-STU-2": FAIL, "SYN-STU-3": PASS},
            {"SYN-STU-1": WORSE_FAIL, "SYN-STU-2": PASS, "SYN-STU-3": PASS})
        with self.assertRaises(ValidationError) as ctx:
            self.decide(results[2]["name"], "Repeat", "Repeat the worse attempt")
        self.assertIn("best published attempt", str(ctx.exception))


class CorrectionTests(RetakeCase):
    def test_a_correction_supersedes_without_changing_the_original(self):
        book = self.fail_book()
        original = self.results_for("SYN-STU-1")[1]
        self.h.acting_as(MANAGER)
        revised = self.h.assessment.correct_published_result(
            self.key("correct"), book["name"], "SYN-STU-1",
            "Moderation corrected the reading mark",
            marks=[{"component": "READING", "mark": 8.0}])
        self.assertEqual(revised["revision"], 2)
        self.assertEqual(revised["supersedes"], original["name"])
        stored_original = self.h.store.load("TH Academic Result", original["name"])
        self.assertEqual(stored_original.status, "Superseded")
        self.assertEqual(stored_original.outcome, "Fail")
        self.assertEqual(stored_original.overall_percent, 36.0)
        current = self.results_for("SYN-STU-1")[1]
        self.assertEqual(current["name"], revised["name"])
        self.assertEqual(current["attempt"], 1)
        self.assertEqual(current["outcome"], "Fail")
        # The correction did not consume the retake: one retake is still
        # available once the wait has elapsed.
        self.h.today = DAY_7
        decision = self.retake_decision(current["name"])
        self.assertEqual(decision["decision"], "Retake")

    def test_a_corrected_pass_is_selected_and_the_superseded_fail_is_not(self):
        book = self.fail_book()
        original = self.results_for("SYN-STU-1")[1]
        self.h.acting_as(MANAGER)
        revised = self.h.assessment.correct_published_result(
            self.key("correct"), book["name"], "SYN-STU-1",
            "Moderation corrected the reading mark to full marks",
            marks=[{"component": "READING", "mark": 20.0}])
        self.assertEqual(revised["outcome"], "Pass")
        best = self.h.progression._best_published_attempt("SYN-STU-1", "SYN-GE-1")
        self.assertEqual(best.get("name"), revised["name"])
        with self.assertRaises(ValidationError) as ctx:
            self.retake_decision(revised["name"], reason="Retake a corrected pass")
        self.assertIn("failed attempt", str(ctx.exception))
        stored_original = self.h.store.load("TH Academic Result", original["name"])
        self.assertEqual(stored_original.overall_percent, 36.0)


if __name__ == "__main__":
    unittest.main()

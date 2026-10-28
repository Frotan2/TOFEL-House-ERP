"""Synthetic assessment journeys: configuration -> marks -> approval -> results.

The REAL ``toefl_house.academic.assessment`` command module runs against the
scripted store in ``_harness`` with the REAL security gate, so every journey
below exercises the same authorization, pinning, validation and publication
code the hosted site runs. Negative cases are first-class: an unauthorized
mark, a premature publication, a replayed publication, an unconfigured
policy and a cross-class read each have their own test.
"""
import json
import sys
import types
import unittest
from tests.academic import _harness
from tests.academic._harness import Harness, ValidationError

MANAGER = "academic.manager@example.test"
INSTRUCTOR = "instructor.one@example.test"
OTHER_INSTRUCTOR = "instructor.two@example.test"
GENERAL_MANAGER = "general.manager@example.test"
OUTSIDER = "outsider@example.test"


class AcademicCase(unittest.TestCase):
    """Shared harness setup: one institute, one class, one policy version."""

    def setUp(self):
        self.h = Harness(self)
        self.addCleanup(self.h.close)
        self.h.seed_world()
        self.h.seed_policy()
        self.frappe = self.h.frappe

    def book(self, **kwargs):
        return self.h.open_book(**kwargs)

    def submitted_book(self, **kwargs):
        book = self.book(**kwargs)
        self.h.record(book["name"], self.h.full_marks())
        self.h.acting_as(INSTRUCTOR)
        self.h.assessment.submit_assessment_book("key-submit-1", book["name"])
        return book

    def reviewed_book(self, **kwargs):
        book = self.submitted_book(**kwargs)
        self.h.acting_as(MANAGER)
        self.h.assessment.review_assessment_book("key-review-1", book["name"], "Review")
        return book

    def approved_book(self, **kwargs):
        book = self.reviewed_book(**kwargs)
        self.h.acting_as(MANAGER)
        self.h.assessment.approve_assessment_book("key-approve-1", book["name"])
        return book

    def published_book(self, **kwargs):
        book = self.approved_book(**kwargs)
        self.h.acting_as(MANAGER)
        return self.h.assessment.publish_assessment_results("key-publish-1", book["name"])

    def listening_only(self):
        return [row for row in self.h.full_marks() if row["component"] == "LISTENING"]

    def status_of(self, name):
        return self.h.store.docs["TH Assessment Book"][name]["status"]

    def results(self):
        return self.h.store.find("TH Academic Result")


class ConfigurationJourneyTests(AcademicCase):
    def test_opening_a_book_pins_the_governing_policy_version(self):
        book = self.book()
        self.assertEqual(book["status"], "Open")
        self.assertEqual(book["policy_effective_from"], "2026-09-01")
        self.assertEqual(book["attempt"], 1)
        stored = self.h.store.docs["TH Assessment Book"][book["name"]]
        self.assertEqual(len(stored["policy_digest"]), 64)
        self.assertEqual(stored["grading_scale"], "SYN-SCALE")
        self.assertEqual(stored["opened_by"], MANAGER)

    def test_policy_change_does_not_open_duplicate_first_assessment(self):
        first = self.book(key="key-open-1")
        original_digest = self.h.store.docs["TH Assessment Book"][first["name"]][
            "policy_digest"]
        self.h.seed_policy("SYN-GEN-ENG", effective_from="2026-10-01",
                           weights=[{"component": "LISTENING", "weight": 50},
                                    {"component": "READING", "weight": 50}])
        with self.assertRaises(ValidationError):
            self.book(key="key-open-2", effective_from="2026-10-01")
        self.assertEqual(
            self.h.store.docs["TH Assessment Book"][first["name"]]["policy_digest"],
            original_digest)

    def test_unconfigured_weights_are_refused_with_the_owner_step_named(self):
        self.h.seed_policy("SYN-NO-WEIGHTS", effective_from="2026-09-01",
                           facets_override={"weights": None})
        with self.assertRaises(ValidationError) as ctx:
            self.book(policy="SYN-NO-WEIGHTS", key="key-no-weights")
        self.assertIn("no weights configured", str(ctx.exception))
        self.assertIn("Course Owner", str(ctx.exception))
        self.assertEqual(self.h.store.docs["TH Assessment Book"], {})

    def test_unconfigured_pass_rules_are_refused(self):
        self.h.seed_policy("SYN-NO-PASS", effective_from="2026-09-01",
                           facets_override={"pass_rules": None})
        with self.assertRaises(ValidationError) as ctx:
            self.book(policy="SYN-NO-PASS", key="key-no-pass")
        self.assertIn("no pass_rules configured", str(ctx.exception))

    def test_a_policy_that_governs_no_level_is_refused(self):
        self.h.seed_policy("SYN-UNMAPPED", effective_from="2026-09-01",
                           facets_override={"level_mapping": None})
        with self.assertRaises(ValidationError) as ctx:
            self.book(policy="SYN-UNMAPPED", key="key-unmapped")
        self.assertIn("configures no level mapping", str(ctx.exception))

    def test_a_policy_cannot_govern_a_level_it_does_not_name(self):
        self.h.seed_policy("SYN-EAP", effective_from="2026-09-01",
                           levels=("SYN-EAP-1",))
        with self.assertRaises(ValidationError) as ctx:
            self.book(policy="SYN-EAP", key="key-eap")
        self.assertIn("does not govern level SYN-GE-1", str(ctx.exception))

    def test_a_retired_policy_governs_nothing_new(self):
        self.h.seed_policy("SYN-RETIRED", effective_from="2026-09-01",
                           status="Retired")
        with self.assertRaises(ValidationError) as ctx:
            self.book(policy="SYN-RETIRED", key="key-retired")
        self.assertIn("is retired", str(ctx.exception))

    def test_a_class_without_a_program_level_is_refused(self):
        self.h.store.docs["Student Group"]["SYN-GRP-1"]["program"] = "SYN-UNKNOWN"
        with self.assertRaises(ValidationError) as ctx:
            self.book(key="key-no-level")
        self.assertIn("not mapped to a program level", str(ctx.exception))

    def test_an_unknown_native_plan_is_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            self.book(plan="SYN-MISSING-PLAN", key="key-bad-plan")
        self.assertIn("Unknown native assessment plan", str(ctx.exception))

    def test_only_academic_staff_can_open_a_book(self):
        for actor in (INSTRUCTOR, OUTSIDER, GENERAL_MANAGER):
            with self.assertRaises(Exception) as ctx:
                self.book(actor=actor, key=f"key-open-{actor}")
            # The refusal is the shared security gate's, not a role check
            # scattered through the academic module.
            self.assertIn("non-administrator actor is required",
                          str(ctx.exception))
        self.assertEqual(self.h.store.docs["TH Assessment Book"], {})

    def test_an_unpublished_first_attempt_cannot_be_duplicated(self):
        first = self.book(key="key-open-1")
        self.assertEqual(first["attempt"], 1)
        with self.assertRaises(ValidationError):
            self.book(key="key-open-2")


class MarkEntryTests(AcademicCase):
    def test_the_assigned_instructor_records_marks(self):
        book = self.book()
        result = self.h.record(book["name"], self.h.full_marks())
        self.assertEqual(result["recorded"], 6)
        self.assertEqual(result["mark_count"], 6)
        self.assertEqual(result["status"], "Open")

    def test_another_instructor_cannot_record_marks(self):
        book = self.book()
        with self.assertRaises(Exception) as ctx:
            self.h.record(book["name"], self.h.full_marks(), actor=OTHER_INSTRUCTOR)
        self.assertIn("not assigned to this class", str(ctx.exception))
        self.assertEqual(self.h.store.docs["TH Assessment Book"][book["name"]]
                         .get("marks", []), [])

    def test_academic_staff_and_outsiders_cannot_record_marks(self):
        book = self.book()
        for actor in (MANAGER, OUTSIDER):
            with self.assertRaises(Exception):
                self.h.record(book["name"], self.h.full_marks(), actor=actor)

    def test_a_login_without_an_instructor_record_is_refused(self):
        book = self.book()
        self.h.grant(INSTRUCTOR, ["Instructor"])
        self.h.store.docs["Employee"]["EMP-1"]["status"] = "Left"
        with self.assertRaises(Exception) as ctx:
            self.h.record(book["name"], self.h.full_marks())
        self.assertIn("not linked to an instructor record", str(ctx.exception))

    def test_a_student_outside_the_roster_is_refused(self):
        book = self.book()
        with self.assertRaises(ValidationError) as ctx:
            self.h.record(book["name"], [{"student": "SYN-STU-9",
                                          "component": "LISTENING", "mark": 10}])
        self.assertIn("not on this class's active roster", str(ctx.exception))

    def test_a_component_outside_the_pinned_policy_is_refused(self):
        book = self.book()
        with self.assertRaises(ValidationError) as ctx:
            self.h.record(book["name"], [{"student": "SYN-STU-1",
                                          "component": "SPEAKING", "mark": 10}])
        self.assertIn("not part of the pinned policy version", str(ctx.exception))

    def test_a_mark_above_the_component_maximum_is_refused(self):
        book = self.book()
        with self.assertRaises(ValidationError) as ctx:
            self.h.record(book["name"], [{"student": "SYN-STU-1",
                                          "component": "READING", "mark": 21}])
        self.assertIn("must be between 0 and 20", str(ctx.exception))

    def test_a_negative_mark_is_refused(self):
        book = self.book()
        with self.assertRaises(ValidationError):
            self.h.record(book["name"], [{"student": "SYN-STU-1",
                                          "component": "READING", "mark": -1}])

    def test_a_blank_row_needs_a_missing_reason(self):
        book = self.book()
        with self.assertRaises(ValidationError) as ctx:
            self.h.record(book["name"], [{"student": "SYN-STU-1",
                                          "component": "READING", "mark": None}])
        self.assertIn("Record a mark or a missing reason", str(ctx.exception))

    def test_a_mark_and_a_missing_reason_cannot_coexist(self):
        book = self.book()
        with self.assertRaises(ValidationError):
            self.h.record(book["name"], [{"student": "SYN-STU-1",
                                          "component": "READING", "mark": 10,
                                          "missing_reason": "Absent"}])

    def test_a_duplicate_row_is_refused_and_never_overwritten(self):
        book = self.book()
        self.h.record(book["name"], [{"student": "SYN-STU-1",
                                      "component": "READING", "mark": 10}])
        with self.assertRaises(ValidationError) as ctx:
            self.h.record(book["name"], [{"student": "SYN-STU-1",
                                          "component": "READING", "mark": 19}],
                          key="key-duplicate")
        self.assertIn("already exists", str(ctx.exception))
        marks = self.h.store.docs["TH Assessment Book"][book["name"]]["marks"]
        self.assertEqual([row["mark"] for row in marks], [10.0])

    def test_unknown_row_keys_are_refused(self):
        book = self.book()
        with self.assertRaises(ValidationError) as ctx:
            self.h.record(book["name"], [{"student": "SYN-STU-1",
                                          "component": "READING", "mark": 10,
                                          "grade": "A"}])
        self.assertIn("Unknown mark row keys", str(ctx.exception))

    def test_a_submitted_book_accepts_no_new_marks(self):
        book = self.submitted_book()
        with self.assertRaises(ValidationError) as ctx:
            self.h.record(book["name"], [{"student": "SYN-STU-1",
                                          "component": "READING", "mark": 10}])
        self.assertIn("an academic correction needs its own command",
                      str(ctx.exception))

    def test_an_unknown_book_is_refused(self):
        self.h.acting_as(INSTRUCTOR)
        with self.assertRaises(ValidationError) as ctx:
            self.h.assessment.record_assessment_marks(
                "key-unknown", "BOOK-DOES-NOT-EXIST",
                [{"student": "SYN-STU-1", "component": "READING", "mark": 10}])
        self.assertIn("Unknown assessment book", str(ctx.exception))


class ApprovalJourneyTests(AcademicCase):
    def test_the_full_journey_reaches_published_results(self):
        book = self.book()
        self.h.record(book["name"], self.h.full_marks())
        self.h.acting_as(INSTRUCTOR)
        submitted = self.h.assessment.submit_assessment_book("key-s1", book["name"])
        self.assertEqual(submitted["status"], "Submitted")
        self.h.acting_as(MANAGER)
        self.h.assessment.review_assessment_book("key-r1", book["name"], "Review")
        self.assertEqual(self.status_of(book["name"]), "Reviewed")
        self.h.assessment.approve_assessment_book("key-a1", book["name"])
        self.assertEqual(self.status_of(book["name"]), "Approved")
        published = self.h.assessment.publish_assessment_results("key-p1", book["name"])
        self.assertEqual(published["status"], "Published")
        self.assertEqual(published["published"], 3)
        self.assertEqual(published["outcomes"], {"Pass": 3, "Fail": 0, "Incomplete": 0})
        self.assertEqual(len(self.results()), 3)
        stored = self.h.store.docs["TH Assessment Book"][book["name"]]
        self.assertEqual(stored["published_by"], MANAGER)
        self.assertEqual(stored["submitted_by"], INSTRUCTOR)
        self.assertEqual(stored["reviewed_by"], MANAGER)
        self.assertEqual(stored["approved_by"], MANAGER)

    def test_each_published_result_carries_a_transparent_snapshot(self):
        self.published_book()
        for row in self.results():
            snapshot = json.loads(row["snapshot_json"])
            self.assertEqual(snapshot["algorithm"], "th-grading-v1")
            self.assertEqual(snapshot["policy"]["policy"], "SYN-GEN-ENG")
            self.assertEqual(snapshot["policy"]["effective_from"], "2026-09-01")
            self.assertEqual(snapshot["weight_total"], 100.0)
            self.assertEqual(snapshot["outcome"], "Pass")
            self.assertEqual(row["grade_code"], "B")
            self.assertEqual(row["overall_percent"], 80.0)
            self.assertEqual(len(row["components"]), 2)
            self.assertEqual(row["components"][0]["pass_met"], 0)
            self.assertEqual(len(row["snapshot_digest"]), 64)
            self.assertTrue(snapshot["explanations"])
            self.assertEqual(row["status"], "Published")
            self.assertEqual(row["revision"], 1)

    def test_attendance_comes_from_native_attendance(self):
        self.published_book()
        by_student = {row["student"]: row for row in self.results()}
        self.assertEqual(by_student["SYN-STU-1"]["attendance_percent"], 100.0)
        self.assertEqual(by_student["SYN-STU-2"]["attendance_percent"], 50.0)
        self.assertIsNone(by_student["SYN-STU-3"]["attendance_percent"])

    def test_submission_is_refused_while_marks_are_missing(self):
        book = self.book()
        self.h.record(book["name"], self.h.full_marks(students=["SYN-STU-1"]))
        self.h.acting_as(INSTRUCTOR)
        with self.assertRaises(ValidationError) as ctx:
            self.h.assessment.submit_assessment_book("key-submit-gap", book["name"])
        self.assertIn("Marks are incomplete", str(ctx.exception))
        self.assertEqual(self.status_of(book["name"]), "Open")

    def test_a_recorded_missing_reason_satisfies_submission(self):
        book = self.book()
        self.h.record(book["name"], self.listening_only())
        self.h.record(book["name"], [
            {"student": student, "component": "READING",
             "missing_reason": "Absent - medical certificate"} for student in self.h.students])
        self.h.acting_as(INSTRUCTOR)
        self.h.assessment.submit_assessment_book("key-submit-missing", book["name"])
        self.assertEqual(self.status_of(book["name"]), "Submitted")

    def test_a_missing_mark_publishes_an_incomplete_result_never_a_pass(self):
        book = self.book()
        self.h.record(book["name"], self.listening_only())
        self.h.record(book["name"], [
            {"student": student, "component": "READING",
             "missing_reason": "Absent - medical certificate"} for student in self.h.students])
        self.h.acting_as(INSTRUCTOR)
        self.h.assessment.submit_assessment_book("key-s", book["name"])
        self.h.acting_as(MANAGER)
        self.h.assessment.review_assessment_book("key-r", book["name"], "Review")
        self.h.assessment.approve_assessment_book("key-a", book["name"])
        self.h.assessment.publish_assessment_results("key-p", book["name"])
        for row in self.results():
            self.assertEqual(row["outcome"], "Incomplete")
            self.assertFalse(row["passed"])
            self.assertIsNone(row["overall_percent"])
            self.assertEqual(row["grade_code"], "")
            snapshot = json.loads(row["snapshot_json"])
            self.assertEqual(snapshot["missing"], ["READING"])

    def test_a_failing_student_is_published_as_fail_not_withheld(self):
        book = self.book()
        self.h.record(book["name"], self.h.full_marks(listening=12.0, reading=6.0))
        self.h.acting_as(INSTRUCTOR)
        self.h.assessment.submit_assessment_book("key-s", book["name"])
        self.h.acting_as(MANAGER)
        self.h.assessment.review_assessment_book("key-r", book["name"], "Review")
        self.h.assessment.approve_assessment_book("key-a", book["name"])
        published = self.h.assessment.publish_assessment_results("key-p", book["name"])
        self.assertEqual(published["outcomes"], {"Pass": 0, "Fail": 3, "Incomplete": 0})
        self.assertEqual({row["grade_code"] for row in self.results()}, {""})

    def test_approval_requires_a_completed_review(self):
        book = self.submitted_book()
        self.h.acting_as(MANAGER)
        with self.assertRaises(ValidationError) as ctx:
            self.h.assessment.approve_assessment_book("key-approve-early", book["name"])
        self.assertIn("Only a reviewed book can be approved", str(ctx.exception))

    def test_publication_requires_approval(self):
        book = self.reviewed_book()
        self.h.acting_as(MANAGER)
        with self.assertRaises(ValidationError) as ctx:
            self.h.assessment.publish_assessment_results("key-publish-early", book["name"])
        self.assertIn("approval is required first", str(ctx.exception))
        self.assertEqual(self.results(), [])

    def test_the_submitting_instructor_cannot_review_the_same_book(self):
        book = self.book()
        self.h.record(book["name"], self.h.full_marks())
        self.h.acting_as(INSTRUCTOR)
        self.h.assessment.submit_assessment_book("key-s", book["name"])
        self.h.grant(INSTRUCTOR, ["Instructor", "Academic Manager"])
        self.h.acting_as(INSTRUCTOR)
        with self.assertRaises(Exception) as ctx:
            self.h.assessment.review_assessment_book("key-r", book["name"], "Review")
        self.assertIn("cannot review the same book", str(ctx.exception))

    def test_the_submitter_cannot_approve_the_same_book(self):
        book = self.book()
        self.h.record(book["name"], self.h.full_marks())
        self.h.grant(INSTRUCTOR, ["Instructor", "Academic Manager"])
        self.h.acting_as(INSTRUCTOR)
        self.h.assessment.submit_assessment_book("key-s", book["name"])
        self.h.acting_as(MANAGER)
        self.h.assessment.review_assessment_book("key-r", book["name"], "Review")
        self.h.acting_as(INSTRUCTOR)
        with self.assertRaises(Exception) as ctx:
            self.h.assessment.approve_assessment_book("key-a", book["name"])
        self.assertIn("cannot approve the same book", str(ctx.exception))

    def test_returning_a_book_needs_a_note_and_reopens_it_for_marks(self):
        book = self.submitted_book()
        self.h.acting_as(MANAGER)
        with self.assertRaises(ValidationError) as ctx:
            self.h.assessment.review_assessment_book("key-return-1", book["name"], "Return")
        self.assertIn("requires a note", str(ctx.exception))
        self.h.assessment.review_assessment_book("key-return-2", book["name"], "Return",
                                                 note="Recheck student 2's reading")
        self.assertEqual(self.status_of(book["name"]), "Returned")
        self.h.record(book["name"], [{"student": "SYN-STU-1", "component": "READING",
                                      "mark": 15}], key="key-marks-return")
        returned = self.h.store.docs["TH Assessment Book"][book["name"]]
        log = returned["corrections"][-1]
        self.assertEqual((log["previous_mark"], log["new_mark"]), (16.0, 15.0))
        self.assertEqual(log["reason"], "Recheck student 2's reading")
        self.h.acting_as(INSTRUCTOR)
        self.h.assessment.submit_assessment_book("key-resubmit", book["name"])
        self.assertEqual(self.status_of(book["name"]), "Submitted")

    def test_a_review_action_must_be_review_or_return(self):
        book = self.submitted_book()
        self.h.acting_as(MANAGER)
        with self.assertRaises(ValidationError) as ctx:
            self.h.assessment.review_assessment_book("key-bad-action", book["name"],
                                                     "Approve")
        self.assertIn("must be Review or Return", str(ctx.exception))

    def test_academic_correction_logs_the_previous_mark(self):
        book = self.submitted_book()
        self.h.acting_as(MANAGER)
        corrected = self.h.assessment.correct_assessment_mark(
            "key-correct", book["name"], "SYN-STU-1", "READING", 14,
            reason="Moderation: answer sheet mis-scanned")
        self.assertEqual(corrected["corrected"], ["SYN-STU-1", "READING"])
        stored = self.h.store.docs["TH Assessment Book"][book["name"]]
        log = stored["corrections"][-1]
        self.assertEqual(log["previous_mark"], 16.0)
        self.assertEqual(log["new_mark"], 14.0)
        self.assertEqual(log["corrected_by"], MANAGER)
        self.assertEqual(log["reason"], "Moderation: answer sheet mis-scanned")

    def test_only_academic_staff_correct_marks(self):
        book = self.submitted_book()
        with self.assertRaises(Exception):
            self.h.acting_as(INSTRUCTOR)
            self.h.assessment.correct_assessment_mark(
                "key-correct-instructor", book["name"], "SYN-STU-1", "READING", 14,
                reason="Self-correction")

    def test_a_correction_cannot_exceed_the_component_maximum(self):
        book = self.submitted_book()
        self.h.acting_as(MANAGER)
        with self.assertRaises(ValidationError):
            self.h.assessment.correct_assessment_mark(
                "key-correct-max", book["name"], "SYN-STU-1", "READING", 25,
                reason="Typo")

    def test_a_published_book_is_never_published_twice(self):
        book = self.published_book()
        self.h.acting_as(MANAGER)
        with self.assertRaises(ValidationError) as ctx:
            self.h.assessment.publish_assessment_results("key-publish-again",
                                                         book["name"])
        self.assertIn("already published", str(ctx.exception))
        self.assertEqual(len(self.results()), 3)


class PublicationTests(AcademicCase):
    def test_an_approved_book_publishes_one_result_per_roster_student(self):
        published = self.published_book()
        self.assertEqual(published["published"], 3)
        self.assertEqual({row["student"] for row in self.results()},
                         set(self.h.students))
        for row in self.results():
            self.assertEqual(row["book"], published["name"])
            self.assertEqual(row["policy"], "SYN-GEN-ENG")
            self.assertEqual(row["policy_effective_from"], "2026-09-01")
            self.assertEqual(row["attempt"], 1)
            self.assertEqual(row["native_assessment_result"], "")

    def test_publication_requires_an_approving_actor(self):
        book = self.approved_book()
        self.h.store.docs["TH Assessment Book"][book["name"]]["approved_by"] = ""
        self.h.acting_as(MANAGER)
        with self.assertRaises(ValidationError) as ctx:
            self.h.assessment.publish_assessment_results("key-publish-nobody",
                                                         book["name"])
        self.assertIn("requires a recorded approval", str(ctx.exception))

    def test_results_read_back_through_the_state_projection(self):
        published = self.published_book()
        state = self.h.assessment.assessment_state(published["name"])
        self.assertEqual(state["status"], "Published")
        self.assertEqual(len(state["results"]), 3)
        self.assertEqual(len(state["marks"]), 6)
        self.assertEqual(state["mark_count"], 6)


class CorrectedResultTests(AcademicCase):
    def test_a_correction_publishes_a_new_revision_and_preserves_the_old(self):
        published = self.published_book()
        first = [row for row in self.results() if row["student"] == "SYN-STU-1"][0]
        old_digest = first["snapshot_digest"]
        self.h.acting_as(MANAGER)
        corrected = self.h.assessment.correct_published_result(
            "key-correct-published", published["name"], "SYN-STU-1",
            "Moderation changed the reading mark",
            marks=[{"component": "READING", "mark": 14}])
        self.assertEqual(corrected["revision"], 2)
        self.assertEqual(corrected["supersedes"], first["name"])
        results = self.results()
        self.assertEqual(len(results), 4)
        superseded = [row for row in results if row["name"] == first["name"]][0]
        self.assertEqual(superseded["status"], "Superseded")
        self.assertEqual(superseded["snapshot_digest"], old_digest)
        self.assertEqual(superseded["overall_percent"], 80.0)
        self.assertEqual(superseded["superseded_by"], corrected["name"])
        revisions = [row for row in results if row["student"] == "SYN-STU-1"
                     and row["status"] == "Published"]
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0]["revision"], 2)
        book = self.h.store.docs["TH Assessment Book"][published["name"]]
        self.assertTrue(any(row["reason"].startswith("Moderation")
                            for row in book["corrections"]))
        self.assertEqual(book["status"], "Published")

    def test_a_published_correction_carries_the_corrected_mark(self):
        book = self.book()
        self.h.record(book["name"], self.h.full_marks(listening=15.0, reading=10.0))
        self.h.acting_as(INSTRUCTOR)
        self.h.assessment.submit_assessment_book("key-s", book["name"])
        self.h.acting_as(MANAGER)
        self.h.assessment.review_assessment_book("key-r", book["name"], "Review")
        self.h.assessment.approve_assessment_book("key-a", book["name"])
        self.h.assessment.publish_assessment_results("key-p", book["name"])
        before = [row for row in self.results() if row["student"] == "SYN-STU-1"][0]
        self.assertEqual(before["outcome"], "Fail")
        self.assertEqual(before["overall_percent"], 50.0)
        corrected = self.h.assessment.correct_published_result(
            "key-correct-outcome", book["name"], "SYN-STU-1",
            "Moderation recorded a second marked script",
            marks=[{"component": "LISTENING", "mark": 30}])
        self.assertEqual(corrected["outcome"], "Pass")
        self.assertEqual(corrected["overall_percent"], 80.0)
        self.assertEqual(corrected["grade_code"], "B")
        book_row = self.h.store.docs["TH Assessment Book"][book["name"]]
        log = [row for row in book_row["corrections"]
               if row["component"] == "LISTENING"][-1]
        self.assertEqual((log["previous_mark"], log["new_mark"]), (15.0, 30.0))

    def test_a_published_correction_can_record_a_missing_mark(self):
        published = self.published_book()
        self.h.acting_as(MANAGER)
        corrected = self.h.assessment.correct_published_result(
            "key-correct-missing", published["name"], "SYN-STU-1",
            "Script lost after publication",
            marks=[{"component": "READING", "missing_reason": "Script lost"}])
        self.assertEqual(corrected["outcome"], "Incomplete")
        self.assertIsNone(corrected["overall_percent"])

    def test_a_published_correction_cannot_exceed_the_native_maximum(self):
        published = self.published_book()
        self.h.acting_as(MANAGER)
        with self.assertRaises(ValidationError):
            self.h.assessment.correct_published_result(
                "key-correct-too-high", published["name"], "SYN-STU-1", "Typo",
                marks=[{"component": "READING", "mark": 21}])

    def test_only_a_published_book_has_results_to_correct(self):
        book = self.approved_book()
        self.h.acting_as(MANAGER)
        with self.assertRaises(ValidationError) as ctx:
            self.h.assessment.correct_published_result(
                "key-correct-unpublished", book["name"], "SYN-STU-1", "Too early")
        self.assertIn("Only a published book has published results",
                      str(ctx.exception))

    def test_a_correction_that_changes_nothing_is_refused(self):
        published = self.published_book()
        self.h.acting_as(MANAGER)
        with self.assertRaises(ValidationError) as ctx:
            self.h.assessment.correct_published_result(
                "key-correct-noop", published["name"], "SYN-STU-1",
                "Believed the mark was wrong")
        self.assertIn("changes no published mark", str(ctx.exception))

    def test_a_correction_needs_a_reason(self):
        published = self.published_book()
        self.h.acting_as(MANAGER)
        with self.assertRaises(ValidationError):
            self.h.assessment.correct_published_result(
                "key-correct-noreason", published["name"], "SYN-STU-1", " ")


class NativeIntegrationTests(AcademicCase):
    def setUp(self):
        super().setUp()
        self.h.store.seed("Assessment Criteria", {}, name="Listening")
        self.h.store.seed("Assessment Criteria", {}, name="Reading")
        self.plan = self.h.seed_native_plan()

    def test_publication_writes_one_submitted_native_result_per_student(self):
        self.published_book(plan=self.plan)
        native = self.h.store.find("Assessment Result")
        self.assertEqual(len(native), 3)
        self.assertEqual({row["docstatus"] for row in native}, {1})
        for row in native:
            self.assertEqual(row["assessment_plan"], self.plan)
            self.assertEqual(row["student_group"], "SYN-GRP-1")
            self.assertEqual(row["maximum_score"], 50.0)
        for result in self.results():
            self.assertTrue(result["native_assessment_result"])

    def test_a_native_result_maps_components_to_native_criteria(self):
        self.published_book(plan=self.plan)
        native = self.h.store.find("Assessment Result", limit=1)[0]
        details = native["details"]
        self.assertEqual([row["assessment_criteria"] for row in details],
                         ["Listening", "Reading"])
        self.assertEqual([row["score"] for row in details], [24.0, 16.0])


class PermissionTests(AcademicCase):
    def test_no_academic_command_is_available_to_an_outsider(self):
        book = self.submitted_book()
        self.h.acting_as(OUTSIDER)
        calls = [
            lambda: self.h.assessment.open_assessment_book("k1", "SYN-GRP-1", "SYN-GEN-ENG"),
            lambda: self.h.assessment.submit_assessment_book("k2", book["name"]),
            lambda: self.h.assessment.review_assessment_book("k3", book["name"], "Review"),
            lambda: self.h.assessment.approve_assessment_book("k4", book["name"]),
            lambda: self.h.assessment.publish_assessment_results("k5", book["name"]),
        ]
        for call in calls:
            with self.assertRaises(Exception):
                call()

    def test_an_instructor_cannot_approve_or_publish(self):
        book = self.submitted_book()
        with self.assertRaises(Exception):
            self.h.acting_as(INSTRUCTOR)
            self.h.assessment.approve_assessment_book("k-approve", book["name"])
        with self.assertRaises(Exception):
            self.h.assessment.publish_assessment_results("k-publish", book["name"])
        self.assertEqual(self.results(), [])


class ReadScopeTests(unittest.TestCase):
    """The read matrix and class scoping, checked on the real policy module."""

    def setUp(self):
        self.h = Harness(self)
        self.addCleanup(self.h.close)
        self.h.seed_world()
        self.h.seed_policy()
        from toefl_house import policy
        self.policy = policy

    def test_only_academic_roles_read_books_and_results(self):
        can_read = self.policy.can_read
        self.assertTrue(can_read("assessment_book", ["Academic Manager"], "a", "x", ""))
        self.assertTrue(can_read("assessment_book", ["Instructor"], "a", "x", ""))
        self.assertFalse(can_read("assessment_book", ["Finance Officer"], "a", "x", ""))
        self.assertTrue(can_read("academic_result", ["Academic Manager"], "a", "x", ""))
        self.assertTrue(can_read("academic_result", ["Enrollment Officer"], "a", "x", ""))
        self.assertFalse(can_read("academic_result", ["Finance Officer"], "a", "x", ""))
        self.assertTrue(can_read("progression_decision", ["Academic Manager"], "a", "x", ""))
        self.assertFalse(can_read("progression_decision", ["Instructor"], "a", "x", ""))

    def test_an_outsider_reads_no_academic_kind(self):
        self.assertFalse(self.policy.can_read("assessment_book", [], "a", "x", ""))
        self.assertFalse(self.policy.can_read("academic_result", [], "a", "x", ""))

    def test_an_instructor_list_is_restricted_to_their_classes(self):
        from toefl_house import permissions
        clause = permissions.query("assessment_book", "instructor.one@example.test")
        # The scope is resolved natively (TH Teaching Assignment -> Instructor
        # -> Employee.user_id) inside SQL, so the clause names the login rather
        # than the class: another instructor's classes can never match.
        self.assertIn("IN (SELECT ta.student_group FROM `tabTH Teaching Assignment`",
                      clause)
        self.assertIn("emp.user_id = 'instructor.one@example.test'", clause)
        self.assertNotIn("instructor.two@example.test", clause)

    def test_an_academic_manager_list_is_unrestricted_by_class(self):
        from toefl_house import permissions
        self.assertEqual(permissions.query("assessment_book", MANAGER), "1=1")

    def test_an_outsider_list_query_matches_nothing(self):
        from toefl_house import permissions
        self.assertEqual(permissions.query("assessment_book", OUTSIDER), "1=0")

    def test_an_instructor_cannot_read_another_classs_book(self):
        from toefl_house import permissions
        own = _doc("TH Assessment Book", {"student_group": "SYN-GRP-1", "status": "Open"})
        other = _doc("TH Assessment Book", {"student_group": "SYN-GRP-2", "status": "Open"})
        self.assertTrue(permissions.has_permission(
            own, "read", user="instructor.one@example.test"))
        self.assertFalse(permissions.has_permission(
            other, "read", user="instructor.one@example.test"))
        self.assertTrue(permissions.has_permission(
            other, "read", user=MANAGER))


class ControllerImmutabilityTests(AcademicCase):
    """A published result is frozen even outside the command path."""

    def _controller(self, slug, class_name):
        module = _load_controller(slug)
        return getattr(module, class_name)

    def test_retake_student_cannot_be_changed_after_book_opening(self):
        controller = self._controller("th_assessment_book", "THAssessmentBook")
        document = controller.__new__(controller)
        values = {field: "unchanged" for field in controller.IMMUTABLE}
        values["retake_student"] = "SYN-STU-2"
        document.__dict__["_values"] = values
        document.get = lambda field, default=None: values.get(field, default)
        document.get_doc_before_save = lambda: types.SimpleNamespace(
            get=lambda field, default=None: (
                "SYN-STU-1" if field == "retake_student"
                else values.get(field, default)))
        with self.assertRaises(Exception) as ctx:
            document.validate()
        self.assertIn("immutable", str(ctx.exception).lower())

    def test_a_published_result_is_immutable(self):
        controller = self._controller("th_academic_result", "THAcademicResult")
        document = controller.__new__(controller)
        document.__dict__["_values"] = {"outcome": "Pass", "status": "Published"}
        document.get = lambda field, default=None: document._values.get(field, default)
        document.get_doc_before_save = lambda: types.SimpleNamespace(
            outcome="Fail", status="Published",
            get=lambda field, default=None: "Fail")
        with self.assertRaises(Exception) as ctx:
            document.validate()
        self.assertIn("immutable", str(ctx.exception))

    def test_a_superseded_result_can_never_be_reopened(self):
        controller = self._controller("th_academic_result", "THAcademicResult")
        document = controller.__new__(controller)
        document.__dict__["_values"] = {"status": "Published"}
        document.get = lambda field, default=None: document._values.get(field, default)
        document.get_doc_before_save = lambda: types.SimpleNamespace(
            status="Superseded", get=lambda field, default=None: "Superseded")
        with self.assertRaises(Exception) as ctx:
            document.validate()
        self.assertIn("superseded result is final", str(ctx.exception).lower())

    def test_a_progression_decision_is_immutable(self):
        controller = self._controller("th_progression_decision",
                                      "THProgressionDecision")
        document = controller.__new__(controller)
        document.__dict__["_values"] = {"decision": "Promote"}
        document.get = lambda field, default=None: document._values.get(field, default)
        document.get_doc_before_save = lambda: types.SimpleNamespace(
            decision="Repeat", get=lambda field, default=None: "Repeat")
        with self.assertRaises(Exception):
            document.validate()


def _doc(doctype, values):
    doc = _harness.Doc(None, doctype, values, name="SYN-NAME")
    return doc


def _load_controller(slug):
    """Import one DocType controller over a no-op protected base.

    ``ProtectedRecord.validate`` is the command-containment seam and is
    covered by the command-path tests; here only the controller's own
    immutability rules are under test.
    """
    path = (_harness.APP / "toefl_house" / "academic" / "doctype" / slug
            / f"{slug}.py")
    name = f"tests.academic.probe_{slug}"
    sys.modules.pop(name, None)
    import importlib.util

    saved = sys.modules.get("toefl_house.controllers")
    controllers = types.ModuleType("toefl_house.controllers")

    class ProtectedRecord:
        def validate(self):
            pass

    controllers.ProtectedRecord = ProtectedRecord
    sys.modules["toefl_house.controllers"] = controllers
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if saved is None:
            sys.modules.pop("toefl_house.controllers", None)
        else:
            sys.modules["toefl_house.controllers"] = saved


if __name__ == "__main__":
    unittest.main()

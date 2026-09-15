"""Pure local unit checks for increment-4 delivery projection and clocks.

These do NOT qualify native Frappe behavior (the hosted native checks do that).
"""
from datetime import datetime, timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import (ATTEMPT_TRANSITIONS, attempt_deadline, can_read,
                                deadline_reached, project_form)


def _form():
    return {
        "attempt": "ATT-1",
        "case": "CASE-1",
        "subject": "synthetic-candidate@example.test",
        "algorithm": "allocation-v1",
        "seed": "a" * 64,
        "pool_digest": "b" * 64,
        "sections": [{"id": "s1", "skill": "Grammar", "minutes": 10, "item_count": 2}],
        "items": [
            {"order": 1, "occurrence_id": "O001", "item": "IT-1", "family": "SYN-FAM-1",
             "section": "s1", "skill": "Grammar", "difficulty": "Entry",
             "question_type": "Single Choice", "option_order": ["b", "a"]},
            {"order": 2, "occurrence_id": "O002", "item": "IT-2", "family": "SYN-FAM-2",
             "section": "s1", "skill": "Grammar", "difficulty": "Core",
             "question_type": "True False", "option_order": None},
        ],
    }


def _catalog():
    return {
        "IT-1": {"prompt": "SYNTHETIC: choose a fixture option.", "question_type": "Single Choice",
                 "options": [{"id": "a", "text": "Fixture A"}, {"id": "b", "text": "Fixture B"}]},
        "IT-2": {"prompt": "SYNTHETIC: true or false fixture.", "question_type": "True False",
                 "options": [{"id": "true", "text": "True"}, {"id": "false", "text": "False"}]},
    }


class DeliveryProjectionTests(unittest.TestCase):
    def test_projection_strips_seed_key_and_item_identity(self):
        projection = project_form(_form(), _catalog())
        self.assertEqual(projection["attempt"], "ATT-1")
        self.assertEqual(projection["case"], "CASE-1")
        self.assertNotIn("seed", projection)
        self.assertNotIn("algorithm", projection)
        self.assertNotIn("pool_digest", projection)
        first, second = projection["items"]
        self.assertEqual(first["options"], [{"id": "b", "text": "Fixture B"},
                                            {"id": "a", "text": "Fixture A"}])
        self.assertEqual(second["options"], [{"id": "true", "text": "True"},
                                             {"id": "false", "text": "False"}])
        for item in projection["items"]:
            self.assertNotIn("family", item)
            self.assertNotIn("item", item)
            self.assertNotIn("answer", item)
            self.assertNotIn("seed", item)

    def test_catalog_must_not_include_answers(self):
        catalog = _catalog()
        catalog["IT-1"] = dict(catalog["IT-1"], answer="a")
        with self.assertRaises(ValueError) as ctx:
            project_form(_form(), catalog)
        self.assertIn("answers", str(ctx.exception))

    def test_missing_catalog_item_fails_closed(self):
        with self.assertRaises(ValueError):
            project_form(_form(), {"IT-1": _catalog()["IT-1"]})


class ClockTests(unittest.TestCase):
    def test_deadline_is_started_plus_total_minutes(self):
        started = datetime(2026, 9, 15, 10, 0, 0)
        self.assertEqual(attempt_deadline(started, 45), datetime(2026, 9, 15, 10, 45, 0))

    def test_deadline_reached_at_boundary(self):
        started = datetime(2026, 9, 15, 10, 0, 0)
        deadline = attempt_deadline(started, 1)
        self.assertFalse(deadline_reached(started, deadline))
        self.assertTrue(deadline_reached(deadline, deadline))
        self.assertTrue(deadline_reached(deadline + timedelta(seconds=1), deadline))

    def test_clock_inputs_are_typed(self):
        with self.assertRaises(ValueError):
            attempt_deadline("2026-09-15", 10)
        with self.assertRaises(ValueError):
            attempt_deadline(datetime(2026, 9, 15), 0)
        with self.assertRaises(ValueError):
            deadline_reached("now", datetime(2026, 9, 15))

    def test_attempt_transitions_are_forward_only(self):
        self.assertEqual(ATTEMPT_TRANSITIONS, {
            ("Allocated", "Verified"),
            ("Verified", "In Progress"),
            ("In Progress", "Sealed"),
            ("Sealed", "Marking"),
            ("Marking", "Review"),
            ("Review", "Finalized"),
        })


class DeliveryReadBoundaryTests(unittest.TestCase):
    def test_invigilator_reads_session_records_not_manifest(self):
        roles = ["Placement Invigilator"]
        for kind in ("case", "attempt", "exposure", "response"):
            with self.subTest(kind=kind):
                self.assertTrue(can_read(kind, roles, "i", "someone"))
        self.assertFalse(can_read("manifest", roles, "i", "someone"))
        self.assertFalse(can_read("guard", roles, "i", "someone"))
        self.assertFalse(can_read("key", roles, "i", "i"))
        self.assertFalse(can_read("item", roles, "i", "someone", "Published"))

    def test_author_still_reads_no_session_records(self):
        for kind in ("case", "attempt", "manifest", "exposure", "response"):
            with self.subTest(kind=kind):
                self.assertFalse(can_read(kind, ["Placement Author"], "a", "a"))

    def test_auditor_reads_response_and_manifest(self):
        self.assertTrue(can_read("response", ["Placement Auditor"], "a", "someone"))
        self.assertTrue(can_read("manifest", ["Placement Auditor"], "a", "someone"))

    def test_publisher_still_reads_manifest(self):
        self.assertTrue(can_read("manifest", ["Placement Publisher"], "p", "someone"))
        self.assertTrue(can_read("response", ["Placement Publisher"], "p", "someone"))

    def test_increment1_3_boundaries_unchanged(self):
        self.assertTrue(can_read("item", ["Placement Publisher"], "p", "a", "Draft"))
        self.assertFalse(can_read("key", ["Placement Auditor"], "a", "a"))
        self.assertTrue(can_read("key", ["Placement Author"], "a", "a"))
        self.assertFalse(can_read("guard", ["Placement Publisher"], "p", "x"))
        self.assertFalse(can_read("operation", ["Placement Publisher"], "p", "x"))
        self.assertFalse(can_read("case", ["Placement Author"], "a", "a"))


if __name__ == "__main__":
    unittest.main()

"""Pure local unit checks for increment-5 objective scoring.

These do NOT qualify native Frappe behavior (the hosted native checks do that).
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import ATTEMPT_TRANSITIONS, can_read
from toefl_house.scoring import SCORER_VERSION, ScoringUnavailable, score


def _form():
    return {
        "attempt": "ATT-1",
        "items": [
            {"order": 1, "item": "IT-1", "skill": "Grammar", "question_type": "Single Choice"},
            {"order": 2, "item": "IT-2", "skill": "Grammar", "question_type": "True False"},
            {"order": 3, "item": "IT-3", "skill": "Listening", "question_type": "Single Choice"},
        ],
    }


def _keys():
    return {
        "IT-1": {"answer": "b", "key_version": 1, "content_hash": "h1"},
        "IT-2": {"answer": "true", "key_version": 1, "content_hash": "h2"},
        "IT-3": {"answer": "o1", "key_version": 2, "content_hash": "h3"},
    }


def _responses(one="b", two="true", three_missing=True):
    rows = {
        1: {"option_id": one, "missing": 0, "revision": 1},
        2: {"option_id": two, "missing": 0, "revision": 1},
    }
    if three_missing:
        rows[3] = {"option_id": "", "missing": 1, "revision": 1}
    else:
        rows[3] = {"option_id": "o1", "missing": 0, "revision": 1}
    return rows


class ObjectiveScorerTests(unittest.TestCase):
    def test_exact_match_and_missing_is_not_zero(self):
        result = score(_form(), _responses(), _keys())
        self.assertEqual(result["algorithm"], SCORER_VERSION)
        self.assertEqual(result["presented"], 3)
        self.assertEqual(result["correct"], 2)
        self.assertEqual(result["incorrect"], 0)
        self.assertEqual(result["missing"], 1)
        self.assertEqual(result["correct"] + result["incorrect"] + result["missing"], 3)
        self.assertEqual([item["outcome"] for item in result["items"]],
                         ["correct", "correct", "missing"])
        self.assertEqual(result["by_skill"]["Grammar"]["missing"], 0)
        self.assertEqual(result["by_skill"]["Listening"]["missing"], 1)
        self.assertEqual(result["by_skill"]["Listening"]["incorrect"], 0)
        self.assertEqual(result["by_skill"]["Listening"]["correct"], 0)
        blob = str(result)
        self.assertNotIn("answer", result)
        self.assertNotIn("IT-1", blob)
        self.assertNotIn("seed", result)
        for item in result["items"]:
            self.assertNotIn("item", item)
            self.assertNotIn("family", item)
            self.assertNotIn("option_id", item)
            self.assertNotIn("answer", item)

    def test_incorrect_is_not_a_negative_mark(self):
        result = score(_form(), _responses(one="a", two="false", three_missing=False), _keys())
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["incorrect"], 2)
        self.assertEqual(result["missing"], 0)
        self.assertTrue(all(item["outcome"] != "missing" for item in result["items"]))

    def test_missing_with_option_fails_closed(self):
        rows = _responses()
        rows[3]["option_id"] = "o1"
        with self.assertRaises(ScoringUnavailable):
            score(_form(), rows, _keys())

    def test_unsupported_type_fails_closed(self):
        form = _form()
        form["items"][0] = dict(form["items"][0], question_type="Matching")
        with self.assertRaises(ScoringUnavailable) as ctx:
            score(form, _responses(), _keys())
        self.assertIn("Unsupported question type", str(ctx.exception))

    def test_missing_key_fails_closed(self):
        keys = _keys()
        del keys["IT-3"]
        with self.assertRaises(ScoringUnavailable):
            score(_form(), _responses(), keys)

    def test_missing_response_fails_closed(self):
        rows = _responses()
        del rows[3]
        with self.assertRaises(ScoringUnavailable):
            score(_form(), rows, _keys())


class ScoringReadBoundaryTests(unittest.TestCase):
    def test_assessor_reads_score_not_manifest_or_key(self):
        roles = ["Placement Assessor"]
        for kind in ("case", "attempt", "response", "score"):
            with self.subTest(kind=kind):
                self.assertTrue(can_read(kind, roles, "s", "someone"))
        self.assertFalse(can_read("manifest", roles, "s", "someone"))
        self.assertFalse(can_read("key", roles, "s", "s"))
        self.assertFalse(can_read("guard", roles, "s", "someone"))
        self.assertFalse(can_read("item", roles, "s", "someone", "Published"))

    def test_invigilator_does_not_read_scores(self):
        self.assertFalse(can_read("score", ["Placement Invigilator"], "i", "someone"))

    def test_author_still_reads_no_score(self):
        self.assertFalse(can_read("score", ["Placement Author"], "a", "a"))

    def test_auditor_and_publisher_read_scores(self):
        self.assertTrue(can_read("score", ["Placement Auditor"], "a", "someone"))
        self.assertTrue(can_read("score", ["Placement Publisher"], "p", "someone"))

    def test_sealed_to_marking_is_the_only_new_transition(self):
        self.assertEqual(ATTEMPT_TRANSITIONS, {
            ("Allocated", "Verified"),
            ("Verified", "In Progress"),
            ("In Progress", "Sealed"),
            ("Sealed", "Marking"),
        })


if __name__ == "__main__":
    unittest.main()

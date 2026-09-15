"""Pure local unit checks for increment-6 independent review.

These do NOT qualify native Frappe behavior (the hosted native checks do that).
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import ATTEMPT_TRANSITIONS, can_read


class ReviewReadBoundaryTests(unittest.TestCase):
    def test_reviewer_reads_score_not_manifest_or_key(self):
        roles = ["Placement Reviewer"]
        for kind in ("case", "attempt", "response", "score"):
            with self.subTest(kind=kind):
                self.assertTrue(can_read(kind, roles, "r", "someone"))
        self.assertFalse(can_read("manifest", roles, "r", "someone"))
        self.assertFalse(can_read("key", roles, "r", "r"))
        self.assertFalse(can_read("guard", roles, "r", "someone"))
        self.assertFalse(can_read("item", roles, "r", "someone", "Published"))

    def test_assessor_still_cannot_read_manifest(self):
        self.assertFalse(can_read("manifest", ["Placement Assessor"], "s", "someone"))

    def test_author_still_reads_no_score(self):
        self.assertFalse(can_read("score", ["Placement Author"], "a", "a"))

    def test_invigilator_does_not_read_scores(self):
        self.assertFalse(can_read("score", ["Placement Invigilator"], "i", "someone"))

    def test_marking_to_review_is_the_only_new_transition(self):
        self.assertEqual(ATTEMPT_TRANSITIONS, {
            ("Allocated", "Verified"),
            ("Verified", "In Progress"),
            ("In Progress", "Sealed"),
            ("Sealed", "Marking"),
            ("Marking", "Review"),
        })


if __name__ == "__main__":
    unittest.main()

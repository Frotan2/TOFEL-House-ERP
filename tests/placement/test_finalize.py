"""Pure local unit checks for increment-7 independent finalization.

These do NOT qualify native Frappe behavior (the hosted native checks do that).
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import ATTEMPT_TRANSITIONS, can_read


class FinalizeReadBoundaryTests(unittest.TestCase):
    def test_reviewer_still_reads_score_not_manifest_or_key(self):
        roles = ["Placement Reviewer"]
        for kind in ("case", "attempt", "response", "score"):
            with self.subTest(kind=kind):
                self.assertTrue(can_read(kind, roles, "r", "someone"))
        self.assertFalse(can_read("manifest", roles, "r", "someone"))
        self.assertFalse(can_read("key", roles, "r", "r"))
        self.assertFalse(can_read("guard", roles, "r", "someone"))

    def test_author_still_reads_no_score(self):
        self.assertFalse(can_read("score", ["Placement Author"], "a", "a"))

    def test_invigilator_does_not_read_scores(self):
        self.assertFalse(can_read("score", ["Placement Invigilator"], "i", "someone"))

    def test_review_to_finalized_is_the_only_new_transition(self):
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

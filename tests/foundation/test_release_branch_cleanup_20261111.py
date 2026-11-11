"""Synthetic, no-network tests for exact-SHA maintenance branch retirement."""
import unittest
from unittest.mock import patch

from tools.maintenance import retire_release_branches_20261111 as cleanup


class ReleaseRetirementTests(unittest.TestCase):
    def setUp(self):
        self.number, self.branch, self.sha = cleanup.CANDIDATES[0]
        self.pr = {
            "number": self.number, "state": "closed",
            "merged_at": "2026-11-11T00:00:00Z",
            "base": {"ref": "main"},
            "head": {"repo": {"full_name": cleanup.REPO},
                     "ref": self.branch, "sha": self.sha},
        }
        self.ref = {"ref": "refs/heads/" + self.branch,
                    "object": {"sha": self.sha}}

    def test_current_known_candidates_unique_and_exact(self):
        self.assertEqual(len(cleanup.CANDIDATES), 8)
        names = [b for _, b, _ in cleanup.CANDIDATES]
        self.assertEqual(len(set(names)), len(names))
        self.assertNotIn("main", names)
        self.assertNotIn(cleanup.SELF_BRANCH, names)
        self.assertTrue(all(len(sha) == 40 for _, _, sha in cleanup.CANDIDATES))

    def test_unmodified_merged_head_is_eligible(self):
        self.assertTrue(cleanup.is_eligible(self.pr, cleanup.CANDIDATES[0], self.ref, []))

    def test_any_unmerged_or_different_head_is_refused(self):
        for changes in ({"merged_at": None}, {"state": "open"}, {"number": 999},
                        {"base": {"ref": "oracle"}}):
            with self.subTest(changes=changes):
                self.assertFalse(cleanup.is_eligible(
                    {**self.pr, **changes}, cleanup.CANDIDATES[0], self.ref, []))
        for changes in ({"sha": "f" * 40}, {"ref": "main"},
                        {"repo": {"full_name": "other/other"}}):
            with self.subTest(changes=changes):
                self.assertFalse(cleanup.is_eligible(
                    {**self.pr, "head": {**self.pr["head"], **changes}},
                    cleanup.CANDIDATES[0], self.ref, []))

    def test_branch_ref_movement_and_open_pr_refused(self):
        self.assertFalse(cleanup.is_eligible(
            self.pr, cleanup.CANDIDATES[0],
            {"ref": self.ref["ref"], "object": {"sha": "f" * 40}}, []))
        self.assertFalse(cleanup.is_eligible(
            self.pr, cleanup.CANDIDATES[0], self.ref, [{"head": {"ref": self.branch}}]))

    def test_never_construct_main_or_untrusted_ref(self):
        for bad in ("main", "refs/heads/main", "../other", "", "not..safe"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cleanup.ref_path(bad)
        self.assertEqual(cleanup.ref_path(self.branch), "/git/ref/heads/" + self.branch)

    def test_full_inventory_must_be_complete(self):
        with patch.object(cleanup, "api", return_value=[{}] * 100):
            with self.assertRaisesRegex(RuntimeError, "complete"):
                cleanup.list_page("/branches")

    def test_main_and_no_open_prs_are_preconditions(self):
        with patch.object(cleanup, "list_page", return_value=[{"number": 1}]):
            with self.assertRaisesRegex(RuntimeError, "Open pull"):
                cleanup.candidate_plan("a" * 40)

    def test_missing_merged_cleanup_pr_refuses(self):
        with (patch.object(cleanup, "list_page", return_value=[]),
              patch.object(cleanup, "api", return_value=[])):
            with self.assertRaisesRegex(RuntimeError, "cleanup PR"):
                cleanup.candidate_plan("a" * 40)

    def test_unexpected_branch_refuses_before_archival(self):
        self_pr = {**self.pr, "number": 163, "head": {
            "repo": {"full_name": cleanup.REPO}, "ref": cleanup.SELF_BRANCH,
            "sha": "b" * 40}}
        with (patch.object(cleanup, "api", return_value=[self_pr]),
              patch.object(cleanup, "list_page", side_effect=[
                  [], [{"name": "main", "commit": {"sha": "a" * 40}},
                       {"name": "new-agent-work", "commit": {"sha": "c" * 40}}]
              ])):
            with self.assertRaisesRegex(RuntimeError, "Unexpected branch"):
                cleanup.candidate_plan("a" * 40)


if __name__ == "__main__":
    unittest.main()

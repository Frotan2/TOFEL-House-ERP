"""Negative branch-deletion safety contracts."""
import importlib.util
from pathlib import Path
import unittest

src = Path(__file__).resolve().parents[2] / "tools/maintenance/retire_merged_branches.py"
spec = importlib.util.spec_from_file_location("retire_merged_branches", src)
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


class RetireMergedBranchesSafetyTests(unittest.TestCase):
    def setUp(self):
        self.branch = "fix/already-merged"
        self.sha = "a" * 40
        self.pr = {"state": "closed", "merged_at": "2026-10-24T12:00:00Z",
                   "head": {"repo": {"full_name": cleanup.REPOSITORY},
                            "ref": self.branch, "sha": self.sha}}
        self.ref = {"ref": "refs/heads/" + self.branch, "object": {"sha": self.sha}}

    def eligible(self, pr=None, ref=None, opened=None, branch=None):
        return cleanup.eligible(self.pr if pr is None else pr,
                                self.ref if ref is None else ref,
                                [] if opened is None else opened,
                                self.branch if branch is None else branch, self.sha)[0]

    def test_valid_unchanged_merged_pr(self):
        self.assertTrue(self.eligible())

    def test_never_delete_unmerged(self):
        self.assertFalse(self.eligible(pr={**self.pr, "merged_at": None}))

    def test_never_delete_branch_with_new_commits(self):
        self.assertFalse(self.eligible(ref={**self.ref, "object": {"sha": "b" * 40}}))

    def test_never_delete_open_pr_branch(self):
        self.assertFalse(self.eligible(opened=[{"head": {
            "repo": {"full_name": cleanup.REPOSITORY}, "ref": self.branch}}]))

    def test_never_delete_main(self):
        self.assertFalse(self.eligible(branch="main"))

    def test_never_delete_other_repository(self):
        self.assertFalse(self.eligible(pr={**self.pr, "head": {
            "repo": {"full_name": "someone/else"}, "ref": self.branch, "sha": self.sha}}))

    def test_allowlist_exact_shas_no_duplicates(self):
        names = [branch for _, branch, _ in cleanup.CANDIDATES]
        self.assertEqual(len(names), len(set(names)))
        self.assertNotIn("main", names)
        self.assertTrue(all(len(sha) == 40 for _, _, sha in cleanup.CANDIDATES))


if __name__ == "__main__":
    unittest.main()

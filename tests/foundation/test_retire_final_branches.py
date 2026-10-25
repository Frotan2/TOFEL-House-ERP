"""Contract tests for the final exact-head retirement plan (no network calls)."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "maintenance" / "retire_final_branches.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("retire_final_branches", SCRIPT)
retire = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retire)


class FinalBranchRetirementTests(unittest.TestCase):
    def setUp(self):
        retire.TOKEN = "fake-test-token"
        self.branch = "arena/bef6fb1b-tofel-house-erp"
        self.sha = "09607131f42bb5e21d0a4f6a06247570e4a65258"
        self.ref = {"ref": "refs/heads/" + self.branch,
                    "object": {"sha": self.sha}}
        self.source = {
            "state": "closed", "merged_at": None,
            "head": {"repo": {"full_name": retire.REPOSITORY},
                     "ref": self.branch, "sha": self.sha},
        }
        self.replacement = {
            "state": "closed", "merged_at": "2026-10-24T14:34:53Z",
            "base": {"ref": "main"},
        }

    def fetch(self, path, token):
        if path.startswith("/git/ref/heads/"):
            return self.ref
        if path == "/pulls/61":
            return self.source
        if path == "/pulls/62":
            return self.replacement
        raise AssertionError("Unexpected API request: " + path)

    def test_audited_candidates_are_exact_and_never_main(self):
        self.assertEqual(len(retire.CANDIDATES), 21)
        names = [record[1] for record in retire.CANDIDATES]
        self.assertEqual(len(set(names)), len(names))
        self.assertNotIn("main", names)
        self.assertNotIn(retire.SELF_BRANCH, names)
        self.assertTrue(all(len(record[2]) == 40 for record in retire.CANDIDATES))
        self.assertTrue(any(record[3] == 69 for record in retire.CANDIDATES))
        self.assertIn((74, "fix/owner-desk-plain-language-native-20261025",
                       "2bfbca38e573bfb8d0fdfb2820fe14c7e9555231", None),
                      retire.CANDIDATES)

    def test_closed_superseded_branch_requires_merged_replacement(self):
        with patch.object(retire, "api", side_effect=self.fetch):
            ok, reason = retire.permitted(61, self.branch, self.sha, 62, [])
        self.assertTrue(ok, reason)

    def test_open_pr_head_is_never_deleted(self):
        opened = [{"head": {"repo": {"full_name": retire.REPOSITORY},
                            "ref": self.branch}}]
        with patch.object(retire, "api", side_effect=AssertionError("API should not run")):
            ok, reason = retire.permitted(61, self.branch, self.sha, 62, opened)
        self.assertFalse(ok)
        self.assertIn("open PR", reason)

    def test_sha_movement_fails_closed(self):
        moved = dict(self.ref, object={"sha": "f" * 40})

        def fake(path, token):
            return moved if path.startswith("/git/ref/heads/") else self.fetch(path, token)

        with patch.object(retire, "api", side_effect=fake):
            ok, reason = retire.permitted(61, self.branch, self.sha, 62, [])
        self.assertFalse(ok)
        self.assertIn("changed", reason)

    def test_superseded_source_must_be_closed(self):
        source = dict(self.source, state="open")

        def fake(path, token):
            return source if path == "/pulls/61" else self.fetch(path, token)

        with patch.object(retire, "api", side_effect=fake):
            ok, reason = retire.permitted(61, self.branch, self.sha, 62, [])
        self.assertFalse(ok)
        self.assertIn("not closed", reason)

    def test_replacement_must_actually_be_merged(self):
        replacement = dict(self.replacement, merged_at=None)

        def fake(path, token):
            return replacement if path == "/pulls/62" else self.fetch(path, token)

        with patch.object(retire, "api", side_effect=fake):
            with self.assertRaisesRegex(RuntimeError, "has not merged"):
                retire.permitted(61, self.branch, self.sha, 62, [])

    def test_self_cleanup_name_is_not_implicitly_authorized(self):
        with self.assertRaises(ValueError):
            retire.ref_path("main")
        with self.assertRaises(ValueError):
            retire.ref_path("refs/heads/main")


if __name__ == "__main__":
    unittest.main()

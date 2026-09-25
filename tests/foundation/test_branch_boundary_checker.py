"""Contract for tools/foundation/branch_boundary.py.

A rotation has to change the branch name in every workflow and in the
canonical pin. Land those two edits in separate commits and every boundary
gate goes red at once, for bookkeeping and nothing else — which is what took
four gates down at 2deba87, invisibly, because the only record was
"Process completed with exit code 1".

The rotation itself cannot be automated: advancing the provenance pins needs
the run id of the previous branch's last recorded rejection, a measured fact
that must never be invented. The check can be, so these tests pin it.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools"))

from branch_boundary import (branch_filters, check_tree, mismatch,  # noqa: E402
                             ref_guards, workflow_paths)
from session_branch import ACTIVE_BRANCH, ACTIVE_REF  # noqa: E402

NEW = "arena/01a0cd90-tofel-house-erp"
OLD = "arena/01a0c987-tofel-house-erp"


def workflow(branch, ref):
    return (f"on:\n  push:\n    branches: [{branch}]\n"
            f"jobs:\n  x:\n    if: github.ref == '{ref}'\n    steps: []\n")


class MismatchTests(unittest.TestCase):
    def test_a_consistent_workflow_reports_no_problem(self):
        self.assertIsNone(mismatch(workflow(NEW, "refs/heads/" + NEW), NEW,
                                   "refs/heads/" + NEW))

    def test_a_push_filter_disagreement_names_both_literals(self):
        """The 2deba87 shape: workflows rotated, pin not yet."""
        problem = mismatch(workflow(NEW, "refs/heads/" + NEW), OLD, "refs/heads/" + OLD)
        self.assertIsNotNone(problem)
        self.assertIn(NEW, problem)
        self.assertIn(OLD, problem)
        self.assertIn("push filter", problem)

    def test_a_ref_guard_disagreement_is_named_separately(self):
        problem = mismatch(workflow(NEW, "refs/heads/" + OLD), NEW, "refs/heads/" + NEW)
        self.assertIn("github.ref guard", problem)
        self.assertNotIn("push filter", problem)

    def test_both_disagreements_are_reported_together(self):
        problem = mismatch(workflow(OLD, "refs/heads/" + OLD), NEW, "refs/heads/" + NEW)
        self.assertIn("push filter", problem)
        self.assertIn("github.ref guard", problem)

    def test_a_workflow_with_no_boundary_has_nothing_to_disagree_with(self):
        text = "on:\n  workflow_dispatch:\njobs:\n  x:\n    steps: []\n"
        self.assertIsNone(mismatch(text, NEW, "refs/heads/" + NEW))
        self.assertEqual(branch_filters(text), [])
        self.assertEqual(ref_guards(text), [])


class ParsingTests(unittest.TestCase):
    def test_inline_branch_filter(self):
        self.assertEqual(branch_filters("  push:\n    branches: [abc]\n"), ["abc"])

    def test_yaml_list_branch_filter(self):
        text = "  push:\n    branches:\n      - abc\n      - def\n"
        self.assertEqual(branch_filters(text), ["abc", "def"])

    def test_a_list_filter_does_not_swallow_the_next_key(self):
        text = "  push:\n    branches:\n      - abc\n    paths:\n      - x\n"
        self.assertEqual(branch_filters(text), ["abc"])

    def test_ref_guard_in_single_and_double_quotes(self):
        self.assertEqual(ref_guards("if: github.ref == 'refs/heads/a'\n"),
                         ["refs/heads/a"])
        self.assertEqual(ref_guards('if: github.ref == "refs/heads/b"\n'),
                         ["refs/heads/b"])


class TreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".github" / "workflows").mkdir(parents=True)

    def _write(self, name, branch, ref):
        path = self.root / ".github" / "workflows" / name
        path.write_text(workflow(branch, ref), encoding="utf-8")
        return path

    def test_only_disagreeing_workflows_are_reported(self):
        self._write("good.yml", NEW, "refs/heads/" + NEW)
        self._write("bad.yml", OLD, "refs/heads/" + OLD)
        report = check_tree(self.root, NEW, "refs/heads/" + NEW)
        self.assertEqual(len(report), 1)
        self.assertIn("bad.yml", report[0])
        self.assertNotIn("good.yml", report[0])

    def test_the_report_is_empty_when_every_workflow_agrees(self):
        self._write("a.yml", NEW, "refs/heads/" + NEW)
        self._write("b.yml", NEW, "refs/heads/" + NEW)
        self.assertEqual(check_tree(self.root, NEW, "refs/heads/" + NEW), [])

    def test_the_cli_fails_and_explains_on_a_mismatch(self):
        self._write("bad.yml", OLD, "refs/heads/" + OLD)
        (self.root / "tools").mkdir()
        (self.root / "tools" / "session_branch.py").write_text(
            f'ACTIVE_BRANCH = "{NEW}"\nACTIVE_REF = "refs/heads/" + ACTIVE_BRANCH\n',
            encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "foundation" / "branch_boundary.py"),
             "--root", str(self.root)],
            capture_output=True, text=True)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("bad.yml", completed.stderr)
        # The remedy has to be stated, not just the symptom.
        self.assertIn("same commit", completed.stderr)

    def test_the_cli_passes_on_a_consistent_tree(self):
        self._write("good.yml", NEW, "refs/heads/" + NEW)
        (self.root / "tools").mkdir()
        (self.root / "tools" / "session_branch.py").write_text(
            f'ACTIVE_BRANCH = "{NEW}"\nACTIVE_REF = "refs/heads/" + ACTIVE_BRANCH\n',
            encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "foundation" / "branch_boundary.py"),
             "--root", str(self.root)],
            capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)


class RealTreeTests(unittest.TestCase):
    """The repository as it stands must already satisfy the check."""

    def test_every_workflow_agrees_with_the_canonical_pin(self):
        self.assertEqual(check_tree(ROOT, ACTIVE_BRANCH, ACTIVE_REF), [])

    def test_the_checker_covers_more_than_one_workflow(self):
        self.assertGreater(len(workflow_paths(ROOT)), 1)

    def test_the_cli_passes_on_this_repository(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "foundation" / "branch_boundary.py")],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()

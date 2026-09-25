"""Keep active hosted qualifications bound to the Arena session branch."""
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from session_branch import ACTIVE_BRANCH as BRANCH, ACTIVE_REF as REF  # noqa: E402
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
from branch_boundary import mismatch  # noqa: E402


class CurrentBranchQualificationTests(unittest.TestCase):
    def test_checkout_is_the_active_session_branch(self):
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), BRANCH)

    def test_foundation_workflows_trigger_and_gate_the_active_branch(self):
        for workflow in (
            "foundation-runtime.yml",
            "foundation-runner.yml",
            "foundation-frontend-review.yml",
            "placement-content.yml",
        ):
            source = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
            self.assertIn(f"branches: [{BRANCH}]", source,
                          f"{workflow}: {mismatch(source, BRANCH, REF)}")
            self.assertIn(f"github.ref == '{REF}'", source,
                          f"{workflow}: {mismatch(source, BRANCH, REF)}")
            self.assertNotIn("arena/01a09bf3-tofel-house-erp", source, workflow)

        recovery = (ROOT / ".github/workflows/placement-evidence.yml").read_text(encoding="utf-8")
        self.assertNotIn("    push:", recovery)
        self.assertIn("  workflow_dispatch:", recovery)
        self.assertIn(f"github.ref == '{REF}'", recovery,
                      mismatch(recovery, BRANCH, REF))
        self.assertNotIn("arena/01a09bf3-tofel-house-erp", recovery)

    def test_hosted_tools_accept_only_the_active_ref_for_current_runs(self):
        runtime = (ROOT / "tools/foundation/runtime_install.py").read_text(encoding="utf-8")
        frontend = (ROOT / "tools/foundation/frontend_experiment.py").read_text(encoding="utf-8")
        for source, label in ((runtime, "runtime"), (frontend, "frontend")):
            self.assertIn("from session_branch import ACTIVE_REF", source, label)
            self.assertNotIn("arena/01a09bf3-tofel-house-erp", source, label)
            self.assertNotIn("arena/01a0a942-tofel-house-erp", source, label)
        self.assertIn("--initial-branch", runtime)
        self.assertIn("ACTIVE_REF.removeprefix", runtime)

    def test_shared_runner_and_evidence_transport_allow_the_active_ref(self):
        runner = (ROOT / "tools/foundation/runner_probe.py").read_text(encoding="utf-8")
        publisher = (ROOT / "tools/foundation/publish_evidence.py").read_text(encoding="utf-8")
        self.assertIn("AUTHORIZED_REFS = (ACTIVE_REF,)", runner)
        self.assertIn("if os.environ.get(\"GITHUB_REF\") != ACTIVE_REF", publisher)

    def test_runtime_install_emits_a_one_line_error_annotation_on_failure(self):
        """Job logs EOF here. Annotations are the only hosted diagnostic.

        A multi-line stderr dump never becomes an annotation. The helper must
        emit ``::error::`` as a single line so the next Foundation runtime
        failure is readable.
        """
        sys.path.insert(0, str(ROOT / "tools" / "foundation"))
        from runtime_install import hosted_failure_annotations
        lines = hosted_failure_annotations("clone-frappe: exit 128\nwarning: foo",
                                           "clone-frappe")
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertTrue(line.startswith("::error "), line)
            self.assertNotIn("\n", line)
        self.assertIn("last failed check: clone-frappe", lines[0])
        self.assertIn("clone-frappe: exit 128 warning: foo", lines[1])
        runtime = (ROOT / "tools/foundation/runtime_install.py").read_text(encoding="utf-8")
        self.assertIn("hosted_failure_annotations(", runtime)
        self.assertIn("print(line, flush=True)", runtime)


if __name__ == "__main__":
    unittest.main()

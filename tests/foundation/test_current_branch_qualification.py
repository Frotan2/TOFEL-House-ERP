"""Keep active hosted qualifications bound to the Arena session branch."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
BRANCH = "arena/01a0a942-tofel-house-erp"
REF = "refs/heads/" + BRANCH


class CurrentBranchQualificationTests(unittest.TestCase):
    def test_foundation_workflows_trigger_and_gate_the_active_branch(self):
        for workflow in (
            "foundation-runtime.yml",
            "foundation-runner.yml",
            "foundation-frontend-review.yml",
        ):
            source = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
            self.assertIn(f"branches: [{BRANCH}]", source, workflow)
            self.assertIn(f"github.ref == '{REF}'", source, workflow)
            self.assertNotIn("arena/01a09bf3-tofel-house-erp", source, workflow)

    def test_hosted_tools_accept_only_the_active_ref_for_current_runs(self):
        runtime = (ROOT / "tools/foundation/runtime_install.py").read_text(encoding="utf-8")
        frontend = (ROOT / "tools/foundation/frontend_experiment.py").read_text(encoding="utf-8")
        for source, label in ((runtime, "runtime"), (frontend, "frontend")):
            self.assertIn(REF, source, label)
            self.assertNotIn("arena/01a09bf3-tofel-house-erp", source, label)
        self.assertIn("--initial-branch", runtime)
        self.assertIn(BRANCH, runtime)

    def test_shared_runner_and_evidence_transport_allow_the_active_ref(self):
        runner = (ROOT / "tools/foundation/runner_probe.py").read_text(encoding="utf-8")
        publisher = (ROOT / "tools/foundation/publish_evidence.py").read_text(encoding="utf-8")
        self.assertIn(f'"{REF}"', runner)
        self.assertIn(f'"{REF}"', publisher)


if __name__ == "__main__":
    unittest.main()

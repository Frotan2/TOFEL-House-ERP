"""Contract for the whole-repository owned-suite gate.

Every other workflow in this repository is path-filtered to the tooling it
qualifies, which means no single run exercised the whole owned test tree: a
change under `apps/**` never ran `tests/d8`, and a change under `tools/**` never
ran the domain suites. `.github/workflows/owned-suite.yml` closes that gap.

These checks keep the gate honest: it must cover the entire `tests/` tree (so a
new test directory is picked up automatically rather than having to be
registered), it must not silently narrow its trigger, and it must keep asserting
that the D8 gate is BLOCKED and production is REJECT.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from session_branch import ACTIVE_BRANCH, ACTIVE_REF  # noqa: E402

WORKFLOW_PATH = ROOT / ".github/workflows/owned-suite.yml"
WORKFLOW = WORKFLOW_PATH.read_text(encoding="utf-8")


class OwnedSuiteWorkflowTests(unittest.TestCase):
    def test_workflow_exists_and_is_bound_to_the_active_branch_and_pull_requests(self):
        self.assertIn(f"branches: [{ACTIVE_BRANCH}]", WORKFLOW)
        self.assertIn(f"github.ref == '{ACTIVE_REF}'", WORKFLOW)
        self.assertIn("pull_request:", WORKFLOW,
                      "the owned suite must gate pull requests, not only pushes")

    def test_it_discovers_the_whole_test_tree_rather_than_named_directories(self):
        """A new tests/<area> must be covered without editing the workflow."""
        self.assertIn("python3 -m unittest discover -s tests -t .", WORKFLOW)
        areas = sorted(p.name for p in (ROOT / "tests").iterdir()
                       if p.is_dir() and not p.name.startswith("__"))
        self.assertTrue(areas, "no test areas found")
        for area in areas:
            self.assertNotIn(f"discover -s tests/{area}", WORKFLOW,
                             f"tests/{area} is enumerated individually; whole-tree "
                             "discovery already covers it and enumeration rots")

    def test_every_test_area_is_actually_discoverable(self):
        """Guard the discovery root itself, not just the workflow text."""
        import unittest as ut

        def walk(suite):
            for item in suite:
                if isinstance(item, ut.TestSuite):
                    yield from walk(item)
                else:
                    yield item.id()

        suite = ut.defaultTestLoader.discover(
            start_dir=str(ROOT / "tests"), top_level_dir=str(ROOT))
        ids = list(walk(suite))
        self.assertTrue(ids, "whole-tree discovery collected no tests")
        for area in ("admission", "d8", "enrollment", "finance", "foundation",
                     "placement", "teaching"):
            self.assertTrue(any(name.startswith(f"tests.{area}.") for name in ids),
                            f"tests/{area} was not collected by whole-tree discovery")

    def test_it_runs_both_node_suites(self):
        self.assertIn("node tests/foundation/test_realtime_guard.cjs", WORKFLOW)
        self.assertIn("node tests/foundation/test_command_pages.cjs", WORKFLOW)

    def test_static_analysis_is_version_and_hash_pinned(self):
        self.assertIn("ruff==0.16.8 --hash=sha256:", WORKFLOW)
        self.assertIn("--require-hashes", WORKFLOW)
        self.assertIn("--no-deps", WORKFLOW)
        # Installed into an isolated venv, never into the runner's Python.
        self.assertIn("python3 -m venv .foundation/lint-venv", WORKFLOW)
        self.assertIn('test "$(.foundation/lint-venv/bin/ruff --version)" = "ruff 0.16.8"', WORKFLOW)
        self.assertIn(".foundation/lint-venv/bin/ruff check .", WORKFLOW)
        self.assertNotIn("pip install ruff", WORKFLOW)

    def test_it_asserts_the_release_posture_is_unchanged(self):
        self.assertIn('report["d8_gate_state"] == "BLOCKED"', WORKFLOW)
        self.assertIn('report["production_state"] == "REJECT"', WORKFLOW)
        self.assertIn('report["production_enabled"] is False', WORKFLOW)
        self.assertIn('report["checkout_branch_matches_active"]', WORKFLOW)
        self.assertIn('"UPSTREAM-BLOCKED / REJECT"', WORKFLOW)

    def test_permissions_and_action_pins_are_minimal(self):
        self.assertIn("contents: read", WORKFLOW)
        self.assertNotIn("contents: write", WORKFLOW)
        self.assertNotIn("actions: write", WORKFLOW)
        self.assertNotIn("checks: write", WORKFLOW)
        self.assertIn("actions/checkout@11d5960a326750d5838078e36cf38b85af677262", WORKFLOW)
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", WORKFLOW)
        self.assertIn("persist-credentials: false", WORKFLOW)
        self.assertIn("timeout-minutes:", WORKFLOW)


if __name__ == "__main__":
    unittest.main()

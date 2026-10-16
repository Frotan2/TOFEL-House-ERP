"""Tripwire for GHSA-fgmj-fm8m-jvvx (echarts), re-triaged 2026-10-15 (erratum E5).

The NOT_REACHABLE disposition depends on echarts being absent from every
shipped frozen dependency tree. The upstream trees are external, so the
offline check verifies the recorded evidence and the frozen-install controls
that keep the latent route closed. Re-run the reproduction in the evidence
README when a pinned SHA, a frappe-ui range, or a frozen-install control changes.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/engineering/evidence/sec-deps-01/echarts-presence-2026-10-15"
TREE_NAMES = ("erpnext", "education", "payments", "hrms", "frappe")
SKIP_DIRS = {".git", "docs", "tests", "node_modules", "__pycache__"}
BINARY_SUFFIXES = {".pyc", ".png", ".jpg", ".gz", ".br", ".zip"}


class EchartsPresenceTests(unittest.TestCase):
    def setUp(self):
        self.record = json.loads((EVIDENCE / "results.json").read_text(encoding="utf-8"))

    def test_every_pinned_tree_recorded_zero_echarts_hits(self):
        trees = self.record["trees"]
        for name in TREE_NAMES:
            matches = [key for key in trees if key.startswith(name + "@")]
            self.assertEqual(len(matches), 1, name)
            self.assertEqual(trees[matches[0]]["lock_or_manifest_hits"], 0, name)
            self.assertEqual(trees[matches[0]]["source_hits"], 0, name)

    def test_repository_tracked_code_has_no_echarts(self):
        for path in ROOT.rglob("*"):
            relative = path.relative_to(ROOT)
            if not path.is_file() or any(part in SKIP_DIRS for part in relative.parts):
                continue
            if path.suffix in BINARY_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            self.assertNotIn("echarts", text.lower(), str(relative))

    def test_frozen_install_controls_remain_in_place(self):
        # Without a frozen install, the education caret range can resolve frappe-ui 0.1.278 (echarts).
        dockerfile = (ROOT / "product/app.Dockerfile").read_text(encoding="utf-8")
        runtime = (ROOT / "tools/foundation/runtime_install.py").read_text(encoding="utf-8")
        self.assertIn("--install.frozen-lockfile true", dockerfile)
        self.assertIn("--install.frozen-lockfile true", runtime)

    def test_latent_route_is_recorded_not_hidden(self):
        education_key = next(k for k in self.record["trees"] if k.startswith("education@"))
        education = self.record["trees"][education_key]
        self.assertEqual(education["frappe_ui_range"], "^0.1.17")
        self.assertEqual(education["frappe_ui_locked"], "0.1.31")
        self.assertEqual(self.record["frappe_ui_0_1_278_declares_echarts"], "^5.6.0")
        self.assertEqual(self.record["disposition"], "NOT_REACHABLE")


if __name__ == "__main__":
    unittest.main()

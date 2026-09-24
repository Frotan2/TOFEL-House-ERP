"""The SEC-DEPS-01 per-finding analysis must cover exactly the hosted finding set."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/engineering/evidence/phase-2/hosted/sec-deps-01-advisories-35852307687.json"
ANALYSIS = ROOT / "docs/engineering/evidence/sec-deps-01/per-finding-remediation-analysis-2026-09-23.json"
CLASSES = {"build_time_only", "dev_server_only_not_run_in_production", "shipped_to_browser_desk",
           "shipped_to_browser_education_portal_out_of_launch_scope", "server_runtime_node_realtime",
           "server_runtime_python", "install_time_only"}


class PerFindingAnalysisTests(unittest.TestCase):
    def setUp(self):
        if not SOURCE.exists():
            self.skipTest("hosted SEC-DEPS-01 advisories artifact not present in this sandbox")
        self.source = json.loads(SOURCE.read_text())
        self.analysis = json.loads(ANALYSIS.read_text())

    def test_every_hosted_finding_is_analysed_exactly_once(self):
        expected = {(k, a.split("(")[0]) for k, v in self.source["packages"].items() for a in v["advisories"]}
        got = [(p["package"], a["id"]) for p in self.analysis["packages"] for a in p["advisories"]]
        self.assertEqual(len(got), len(set(got)))
        self.assertEqual(set(got), expected)
        self.assertEqual(self.analysis["totals"]["advisory_matches"], 102)
        self.assertEqual(sum(self.analysis["totals"]["by_reachability"].values()), 102)

    def test_each_package_answers_all_four_questions(self):
        for p in self.analysis["packages"]:
            self.assertIn(p["reachability"], CLASSES, p["package"])
            self.assertTrue(p["reachability_evidence"].strip(), p["package"])
            self.assertIn("official_v16_upgrade_resolves", p)
            self.assertIn("safe_upgrade_without_vendor_patch", p)

    def test_no_finding_is_claimed_fixed_without_changed_inputs(self):
        # A claimed fix must correspond to a changed matrix pin; none was changed.
        for p in self.analysis["packages"]:
            self.assertFalse(p["official_v16_upgrade_resolves"], p["package"])
            self.assertFalse(p["safe_upgrade_without_vendor_patch"], p["package"])


if __name__ == "__main__":
    unittest.main()

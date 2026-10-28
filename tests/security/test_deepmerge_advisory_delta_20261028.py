"""Regression protection for the 2026-10-28 deepmerge advisory disposition.

The verdict is explicitly limited to the pinned Education/HRMS source paths.
A future advisory or a different package must not reuse this exception.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
import advisory_triage as triage  # noqa: E402

DELTA_PATH = (ROOT / "docs/engineering/evidence/sec-deps-01"
              / "advisory-delta-2026-10-28/delta-dispositions.json")


class DeepmergeAdvisoryDeltaTests(unittest.TestCase):
    def test_delta_is_additive_and_evidence_backed(self):
        data = json.loads(DELTA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(data["date"], "2026-10-28")
        self.assertEqual(data["kind"], "additive_advisory_delta_no_register_mutation")
        self.assertEqual(len(data["packages"]), 1)
        pkg = data["packages"][0]
        self.assertEqual(pkg["package"], "npm:deepmerge@4.3.1")
        self.assertEqual(len(pkg["advisories"]), 1)
        item = pkg["advisories"][0]
        self.assertEqual(item["id"], "GHSA-gcqx-w48m-w2h4")
        self.assertEqual(item["runtime_disposition"], "NOT_REACHABLE")
        self.assertIn("CVE-2026-93753", item["aliases"])
        self.assertIn("1243505", item["aliases"])
        evidence = item["runtime_disposition_evidence"]
        for token in ("93bc7075", "a4768b44", "prosemirror-trailing-node",
                      "@remirror/core-helpers", "@rollup/plugin-node-resolve",
                      "internally constructed"):
            self.assertIn(token, evidence)

    def test_exact_npm_id_and_ghsa_alias_close_only_the_pinned_package(self):
        loaded = triage.load_triage()
        self.assertIn("advisory-delta-2026-10-28", loaded["deltas"])
        for aid in (1243505, "GHSA-gcqx-w48m-w2h4", "CVE-2026-93753"):
            with self.subTest(advisory=aid):
                # No GHSA-bearing URL fallback: the submitted identifier
                # alone must resolve to this exact package record.
                finding = {"id": aid, "url": "", "severity": "low"}
                result = triage.triage_npm({"deepmerge": [finding]}, loaded)
                self.assertEqual(result["untriaged"], [])
                self.assertEqual(result["closed"], 1)
                self.assertEqual(result["open"], 0)
                self.assertEqual(result["findings"][0]["disposition"],
                                 "NOT_REACHABLE")
                self.assertEqual(triage.overall_status(npm_result=result),
                                 "pass")

    def test_no_other_package_borrows_the_deepmerge_exception(self):
        loaded = triage.load_triage()
        self.assertIsNone(triage.disposition_for_finding(
            loaded, package="unrelated-package",
            advisories=["GHSA-gcqx-w48m-w2h4"]))
        finding = {"id": 1243505,
                   "url": "https://github.com/advisories/GHSA-gcqx-w48m-w2h4"}
        result = triage.triage_npm({"unrelated-package": [finding]}, loaded)
        self.assertEqual(result["open"], 1)
        self.assertEqual(result["findings"][0]["disposition"], "REGRESSION")

    def test_new_deepmerge_advisory_still_fails_closed(self):
        loaded = triage.load_triage()
        self.assertIsNone(triage.disposition_for_finding(
            loaded, package="deepmerge", advisories=["GHSA-zzzz-zzzz-zzzz"]))
        finding = {"id": 99999999,
                   "url": "https://github.com/advisories/GHSA-zzzz-zzzz-zzzz"}
        result = triage.triage_npm({"deepmerge": [finding]}, loaded)
        self.assertEqual(result["open"], 1)
        self.assertEqual(len(result["untriaged"]), 1)

    def test_original_september_register_remains_unchanged_in_scope(self):
        previous = triage.load_triage(include_deltas=False)
        self.assertIsNone(triage.disposition_for_finding(
            previous, package="deepmerge",
            advisories=["GHSA-gcqx-w48m-w2h4"]))


if __name__ == "__main__":
    unittest.main()

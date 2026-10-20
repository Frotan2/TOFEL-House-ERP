"""Owner-accepted residual risks in the advisory gate (2026-10-20).

Only the two named (package, advisory) pairs may be overridden, and only while the cited owner decision
exists and says ACCEPT. Accepted findings are visible, not closed, and never count as open.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.foundation import advisory_triage as t

ROOT = Path(__file__).resolve().parents[2]
SHOWDOWN = "GHSA-rmmh-p597-ppvv"
TIPTAP = "GHSA-cp6q-959q-f8rh"
OTHER_BSD = "GHSA-vhrc-hgrq-x75r"  # a BROWSER_SELF_DENIAL record that must stay open


def _npm(pkg, adv_id):
    return {pkg: [{"id": adv_id, "url": "https://github.com/advisories/" + adv_id, "title": "", "severity": "moderate"}]}


class OwnerAcceptedRiskTests(unittest.TestCase):
    def setUp(self):
        self.triage = t.load_triage()

    def test_pinned_pairs_are_accepted_by_their_decisions(self):
        res = t.triage_npm(_npm("showdown@2.1.0", SHOWDOWN), self.triage)
        f = res["findings"][0]
        self.assertEqual(f["disposition"], "OWNER_ACCEPTED_RISK")
        self.assertFalse(f["pass"], "accepted is not closed")
        self.assertEqual(res["accepted"], 1)
        self.assertEqual(res["open"], 0)
        self.assertIn("OD-2026-10-20-A", f["disposition_evidence"])
        self.assertEqual(t.overall_status(npm_result=res), "pass")

    def test_tiptap_pair_is_accepted_under_its_decision(self):
        res = t.triage_npm(_npm("@tiptap/core@2.27.3", TIPTAP), self.triage)
        self.assertEqual(res["findings"][0]["disposition"], "OWNER_ACCEPTED_RISK")
        self.assertEqual(t.overall_status(npm_result=res), "pass")

    def test_other_browser_self_denial_records_stay_open(self):
        res = t.triage_npm(_npm("some-pkg@1.0.0", OTHER_BSD), self.triage)
        if res["findings"]:
            self.assertNotEqual(res["findings"][0]["disposition"], "OWNER_ACCEPTED_RISK")
        self.assertEqual(t.overall_status(npm_result=res), "fail" if res["findings"] else "pass")

    def test_same_advisory_under_another_package_is_not_overridden(self):
        rec = self.triage["by_id"][t._norm(SHOWDOWN)]
        out = t.owner_accepted_override(rec, "npm:some-other-package@1.0.0")
        self.assertEqual(out["runtime_disposition"], "BROWSER_SELF_DENIAL")

    def test_missing_or_rejecting_decision_blocks_the_override(self):
        rec = dict(self.triage["by_id"][t._norm(SHOWDOWN)])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "owner-decisions.json"
            path.write_text(json.dumps({"domain_gate_decisions": [
                {"id": "OD-2026-10-20-A", "decision": "SHOWDOWN: KEEP OPEN"}]}), encoding="utf-8")
            with patch.object(t, "OWNER_DECISIONS_PATH", path):
                out = t.owner_accepted_override(rec, "npm:showdown@2.1.0")
                self.assertEqual(out["runtime_disposition"], "BROWSER_SELF_DENIAL")
                path.write_text(json.dumps({"domain_gate_decisions": []}), encoding="utf-8")
                out = t.owner_accepted_override(rec, "npm:showdown@2.1.0")
                self.assertEqual(out["runtime_disposition"], "BROWSER_SELF_DENIAL")

    def test_missing_decision_file_blocks_the_override(self):
        rec = dict(self.triage["by_id"][t._norm(SHOWDOWN)])
        with patch.object(t, "OWNER_DECISIONS_PATH", Path("/nonexistent/owner-decisions.json")):
            self.assertEqual(t.owner_accepted_override(rec, "npm:showdown@2.1.0")["runtime_disposition"], "BROWSER_SELF_DENIAL")

    def test_the_immutable_register_is_not_edited_by_the_override(self):
        rec = self.triage["by_id"][t._norm(SHOWDOWN)]
        before = dict(rec)
        t.owner_accepted_override(rec, "npm:showdown@2.1.0")
        self.assertEqual(rec, before)

    def test_the_cited_decisions_are_recorded_in_the_owner_file(self):
        decisions = json.loads((ROOT / "docs/owner-decisions.json").read_text(encoding="utf-8"))
        ids = {e["id"]: e["decision"] for e in decisions["domain_gate_decisions"]}
        for decision_id in set(t.OWNER_ACCEPTED_RISKS.values()):
            self.assertIn(decision_id, ids)
            self.assertIn("ACCEPT", ids[decision_id].upper())


if __name__ == "__main__":
    unittest.main()

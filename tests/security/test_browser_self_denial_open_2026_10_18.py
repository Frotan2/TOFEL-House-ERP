"""Owner decision OD-2026-10-18-A: every BROWSER_SELF_DENIAL record stays OPEN.

The 2026-10-18 review found none of the six BROWSER_SELF_DENIAL records upheld as written. The owner
decided that nothing is closed on paper review. These tests pin that decision in the gate itself, so the
audit cannot report a BROWSER_SELF_DENIAL match as closed until a runtime check changes the decision.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

import advisory_triage as t  # noqa: E402


class BrowserSelfDenialOpenTests(unittest.TestCase):
    def test_browser_self_denial_is_not_a_closed_disposition(self):
        self.assertNotIn("BROWSER_SELF_DENIAL", t.CLOSED_DISPOSITIONS)
        self.assertEqual(t.OWNER_OPEN_DISPOSITIONS, frozenset({"BROWSER_SELF_DENIAL"}))

    def test_closed_set_keeps_the_other_closed_dispositions(self):
        self.assertEqual(
            t.CLOSED_DISPOSITIONS,
            frozenset({"MITIGATED", "NOT_REACHABLE", "BUILD_ONLY", "DEV_ONLY", "INSTALL_ONLY"}))

    def test_a_browser_self_denial_match_fails_the_gate(self):
        triage = t.load_triage()
        source = json.loads((ROOT / "docs/engineering/evidence/sec-deps-01/"
                             "per-finding-remediation-analysis-2026-09-23.json").read_text())
        package, adv = next((pkg["package"], adv) for pkg in source["packages"]
                            for adv in pkg["advisories"]
                            if adv["runtime_disposition"] == "BROWSER_SELF_DENIAL"
                            and pkg["package"].startswith("npm:"))
        name = t._package_basename(package)
        res = t.triage_npm({name: [{"id": adv["id"], "url": "https://example.com/" + adv["id"],
                                    "title": adv["id"], "severity": adv.get("severity", "?")}]}, triage)
        self.assertEqual(res["untriaged"], [])
        self.assertEqual(res["open"], 1)
        self.assertEqual(res["findings"][0]["disposition"], "BROWSER_SELF_DENIAL")
        self.assertFalse(res["findings"][0]["pass"])
        self.assertEqual(t.overall_status(npm_result=res), "fail")

if __name__ == "__main__":
    unittest.main()

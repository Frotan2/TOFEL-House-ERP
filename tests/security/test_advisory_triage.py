"""SEC-DEPS-01 triage loader: every raw finding must map to a closed
disposition or be surfaced as REGRESSION. New advisories must not silently
pass; pre-existing triaged advisories must not fail closed."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
import advisory_triage as t  # noqa: E402


TRIAGE = json.loads((ROOT / "docs/engineering/evidence/sec-deps-01/per-finding-remediation-analysis-2026-09-23.json").read_text())
CLOSED = {"MITIGATED","NOT_REACHABLE","BUILD_ONLY","DEV_ONLY","INSTALL_ONLY","BROWSER_SELF_DENIAL"}


class AdvisoryTriageTests(unittest.TestCase):
    def test_every_recorded_advisory_is_indexed(self):
        triage = t.load_triage()
        missing = []
        for pkg in TRIAGE["packages"]:
            for adv in pkg["advisories"]:
                if t._norm(adv["id"]) not in triage["by_id"]:
                    missing.append((pkg["package"], adv["id"]))
        self.assertEqual(missing, [], f"advisories missing from index: {missing}")

    def test_recorded_dispositions_are_recognised(self):
        bad = []
        for pkg in TRIAGE["packages"]:
            for adv in pkg["advisories"]:
                if adv["runtime_disposition"] not in CLOSED | {"OWNER_DECISION_REQUIRED","BLOCKED"}:
                    bad.append((pkg["package"], adv["id"], adv["runtime_disposition"]))
        self.assertEqual(bad, [], f"unknown dispositions: {bad}")

    def test_all_102_advisories_close_under_triage(self):
        """The triage report claims 102 advisories with zero OPEN; verify
        the loader actually resolves each one to a closed disposition."""
        triage = t.load_triage()
        npm = {}
        py = []
        for pkg in TRIAGE["packages"]:
            base = pkg["package"]
            if base.startswith("npm:"):
                name = base.split(":",1)[1].split("@",1)[0]
                npm.setdefault(name, [])
                for adv in pkg["advisories"]:
                    npm[name].append({"id":adv["id"],"url":"https://example.com/"+adv["id"],
                                      "title":adv["id"]+": "+adv.get("summary",""),"severity":adv.get("severity","?")})
            else:
                name = base.split(":",1)[1].split("@",1)[0]
                for adv in pkg["advisories"]:
                    py.append({"package":{"name":name,"ecosystem":"PyPI"},"version":"0",
                               "id":adv["id"],"aliases":adv.get("aliases",[])})
        nres = t.triage_npm(npm, triage)
        pres = t.triage_python(py, triage)
        self.assertEqual(nres["untriaged"], [], "npm advisories did not all resolve")
        self.assertEqual(pres["untriaged"], [], "python advisories did not all resolve")
        self.assertEqual(nres["open"], 0)
        self.assertEqual(pres["open"], 0)
        self.assertEqual(t.overall_status(npm_result=nres, py_result=pres), "pass")

    def test_a_brand_new_advisory_is_a_regression(self):
        triage = t.load_triage()
        res = t.triage_npm({"made-up-pkg":[{"id":999999,"url":"https://example.com/GHSA-zzzz-zzzz-zzzz",
                                             "title":"CVE-9999-0000 newly disclosed","severity":"critical"}]}, triage)
        self.assertEqual(len(res["untriaged"]), 1)
        self.assertEqual(res["untriaged"][0]["disposition"], "REGRESSION")
        self.assertEqual(t.overall_status(npm_result=res), "fail")

    def test_known_advisory_carries_evidence(self):
        triage = t.load_triage()
        rec = t.disposition_for_finding(triage, package="ws", advisories=["GHSA-3h5v-q93c-6h6q"])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["runtime_disposition"], "MITIGATED")
        self.assertTrue(rec.get("runtime_disposition_evidence"))


if __name__ == "__main__":
    unittest.main()

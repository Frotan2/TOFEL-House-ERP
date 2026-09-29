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


class AdvisoryDeltaTests(unittest.TestCase):
    """Dated, additive deltas extend the immutable 2026-09-23 register."""

    DELTA = json.loads((ROOT / "docs/engineering/evidence/sec-deps-01/advisory-delta-2026-09-29"
                        "/delta-dispositions.json").read_text())

    def test_delta_register_is_loaded_and_dated(self):
        triage = t.load_triage()
        self.assertIn("advisory-delta-2026-09-29", triage["deltas"])
        self.assertGreaterEqual(triage["delta_advisories"], 3)
        self.assertEqual(self.DELTA["date"], "2026-09-29")

    def test_new_2026_09_29_advisories_resolve_to_recorded_dispositions(self):
        triage = t.load_triage()
        findings = [{"package": {"name": "oauthlib", "ecosystem": "PyPI"}, "version": "3.3.1",
                     "id": "GHSA-hj66-6f7g-4r5v", "aliases": []},
                    {"package": {"name": "oauthlib", "ecosystem": "PyPI"}, "version": "3.3.1",
                     "id": "GHSA-xpv3-w29h-x7cv", "aliases": ["CVE-2026-49265"]},
                    {"package": {"name": "pyjwt", "ecosystem": "PyPI"}, "version": "2.13.0",
                     "id": "GHSA-w6j9-cwv2-h6wq", "aliases": []}]
        res = t.triage_python(findings, triage)
        self.assertEqual(res["untriaged"], [])
        self.assertEqual(res["open"], 0)
        self.assertEqual(t.overall_status(py_result=res), "pass")
        dispositions = {(f["package"], f["id"]): f["disposition"] for f in res["findings"]}
        self.assertEqual(dispositions[("oauthlib", "GHSA-hj66-6f7g-4r5v")], "NOT_REACHABLE")
        self.assertEqual(dispositions[("oauthlib", "GHSA-xpv3-w29h-x7cv")], "NOT_REACHABLE")
        self.assertEqual(dispositions[("pyjwt", "GHSA-w6j9-cwv2-h6wq")], "NOT_REACHABLE")

    def test_delta_dispositions_are_closed_and_evidence_backed(self):
        for pkg in self.DELTA["packages"]:
            self.assertTrue(pkg["package"].startswith("py:"))
            for adv in pkg["advisories"]:
                self.assertIn(adv["runtime_disposition"],
                              {"MITIGATED", "NOT_REACHABLE", "BUILD_ONLY", "DEV_ONLY",
                               "INSTALL_ONLY", "BROWSER_SELF_DENIAL"})
                self.assertTrue(adv["runtime_disposition_evidence"])
                self.assertIn("988e54f3", adv["runtime_disposition_evidence"])

    def test_related_cve_aliases_also_resolve(self):
        triage = t.load_triage()
        rec = t.disposition_for_finding(triage, package="py:oauthlib@3.3.1",
                                        advisories=["CVE-2026-49265"])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["runtime_disposition"], "NOT_REACHABLE")

    def test_unknown_stay_regressions_even_with_deltas_loaded(self):
        triage = t.load_triage()
        rec = t.disposition_for_finding(triage, package="py:oauthlib@3.3.1",
                                        advisories=["GHSA-zzzz-zzzz-zzzz"])
        self.assertIsNone(rec)

    def test_no_delta_may_redefine_a_covered_advisory(self):
        # The real delta file only adds ids; a redefinition attempt must fail loud.
        real = t.load_triage()
        bad_pkg = {"package": "npm:ws@8.11.0", "advisories": [
            {"id": "GHSA-3h5v-q93c-6h6q", "runtime_disposition": "NOT_REACHABLE"}]}
        # sanity: that id is truly covered by the existing register
        self.assertIn(t._norm("GHSA-3h5v-q93c-6h6q"), real["by_id"])
        import copy
        with self.assertRaises(SystemExit):
            t._index_package(real["by_id"], copy.deepcopy(real["by_package"]),
                             bad_pkg, fail_on_covered=True, source="test")


class AdvisoryDeltaSeptember30Tests(unittest.TestCase):
    """The 2026-09-30 delta closes the markdown-it linkify DoS surfaced by
    hosted foundation-runtime run 36628837943 (both advisory audits exit 1)."""

    DELTA = json.loads((ROOT / "docs/engineering/evidence/sec-deps-01/advisory-delta-2026-09-30"
                        "/delta-dispositions.json").read_text())

    def test_delta_register_is_loaded_and_dated(self):
        triage = t.load_triage()
        self.assertIn("advisory-delta-2026-09-30", triage["deltas"])
        self.assertEqual(self.DELTA["date"], "2026-09-30")

    def test_markdown_it_linkify_advisory_resolves_via_npm_triage(self):
        triage = t.load_triage()
        res = t.triage_npm({"markdown-it": [
            {"id": 999999, "severity": "moderate", "title": "markdown-it linkify quadratic DoS",
             "url": "https://github.com/advisories/GHSA-253c-mchw-3w2r"}]}, triage)
        self.assertEqual(res["untriaged"], [])
        self.assertEqual(res["open"], 0)
        self.assertEqual(t.overall_status(npm_result=res), "pass")
        finding = res["findings"][0]
        self.assertEqual(finding["disposition"], "NOT_REACHABLE")
        self.assertIn("linkify", finding["disposition_evidence"])

    def test_delta_disposition_is_closed_and_evidence_backed(self):
        pkg, = self.DELTA["packages"]
        self.assertEqual(pkg["package"], "npm:markdown-it@14.0.0")
        adv, = pkg["advisories"]
        self.assertEqual(adv["id"], "GHSA-253c-mchw-3w2r")
        self.assertEqual(adv["runtime_disposition"], "NOT_REACHABLE")
        evidence = adv["runtime_disposition_evidence"]
        for anchor in ("93bc7075", "a4768b44", "dist/index.js:347", "dist/markdown-it.js"):
            self.assertIn(anchor, evidence)

    def test_unknown_stay_regressions(self):
        triage = t.load_triage()
        res = t.triage_npm({"markdown-it": [
            {"id": 1, "severity": "high",
             "url": "https://github.com/advisories/GHSA-zzzz-zzzz-zzzz"}]}, triage)
        self.assertEqual(len(res["untriaged"]), 1)
        self.assertEqual(res["findings"][0]["disposition"], "REGRESSION")

    def test_delta_may_not_redefine_the_2026_09_29_delta_or_register(self):
        # markdown-it siblings registered earlier must stay defined exactly once.
        triage = t.load_triage()
        self.assertIn(t._norm("GHSA-6v5v-wf23-fmfq"), triage["by_id"])
        delta_ids = {t._norm(adv["id"]) for pkg in self.DELTA["packages"] for adv in pkg["advisories"]}
        self.assertNotIn(t._norm("GHSA-6v5v-wf23-fmfq"), delta_ids)
        self.assertNotIn(t._norm("GHSA-38c4-r59v-3vqw"), delta_ids)


if __name__ == "__main__":
    unittest.main()

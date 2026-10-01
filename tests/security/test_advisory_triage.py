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


class AdvisoryDeltaSeptember30Part2Tests(unittest.TestCase):
    """The second 2026-09-30 delta closes the 13-advisory batch surfaced by
    hosted run 36668343658 (9 pyjwt, 3 brace-expansion, 1 moment)."""

    DELTA = json.loads((ROOT / "docs/engineering/evidence/sec-deps-01/advisory-delta-2026-09-30-2"
                        "/delta-dispositions.json").read_text())

    PYJWT_IDS = ["GHSA-2gx3-rcp4-g85q", "GHSA-8wjv-2p76-3863", "GHSA-9j54-fg26-wv3r",
                 "GHSA-9v7f-9g4p-ffgj", "GHSA-ffc3-869f-jxw9", "GHSA-hxm8-2xgr-2p9m",
                 "GHSA-p4g4-x82p-q773", "GHSA-r6x4-923q-g947", "GHSA-w2cx-738m-mc7w"]
    NPM_IDS = ["GHSA-6j4f-fj2g-mc7p", "GHSA-q2hr-2g5m-vwhr", "GHSA-qhr7-859c-m2p7",
               "GHSA-4p3w-j4w9-5jqw"]

    def test_delta_register_is_loaded_and_complete(self):
        triage = t.load_triage()
        self.assertIn("advisory-delta-2026-09-30-2", triage["deltas"])
        recorded = {adv["id"] for pkg in self.DELTA["packages"] for adv in pkg["advisories"]}
        self.assertEqual(recorded, set(self.PYJWT_IDS) | set(self.NPM_IDS))
        self.assertEqual(self.DELTA["date"], "2026-09-30")

    def test_all_nine_pyjwt_advisories_close_not_reachable(self):
        triage = t.load_triage()
        findings = [{"package": {"name": "pyjwt", "ecosystem": "PyPI"}, "version": "2.13.0",
                     "id": aid, "aliases": []} for aid in self.PYJWT_IDS]
        res = t.triage_python(findings, triage)
        self.assertEqual(res["untriaged"], [])
        self.assertEqual(res["open"], 0)
        self.assertEqual(t.overall_status(py_result=res), "pass")
        for finding in res["findings"]:
            self.assertEqual(finding["disposition"], "NOT_REACHABLE")
            self.assertTrue(finding["disposition_evidence"])

    def test_all_four_npm_advisories_close_not_reachable(self):
        triage = t.load_triage()
        advisories = {}
        for aid in self.NPM_IDS[:3]:
            advisories.setdefault("brace-expansion", []).append(
                {"id": 1, "severity": "high", "url": f"https://github.com/advisories/{aid}"})
        advisories["moment"] = [{"id": 2, "severity": "moderate",
                                 "url": f"https://github.com/advisories/{self.NPM_IDS[3]}"}]
        res = t.triage_npm(advisories, triage)
        self.assertEqual(res["untriaged"], [])
        self.assertEqual(res["open"], 0)
        self.assertEqual(t.overall_status(npm_result=res), "pass")
        for finding in res["findings"]:
            self.assertEqual(finding["disposition"], "NOT_REACHABLE")

    def test_delta_dispositions_are_closed_and_evidence_backed(self):
        for pkg in self.DELTA["packages"]:
            for adv in pkg["advisories"]:
                self.assertEqual(adv["runtime_disposition"], "NOT_REACHABLE")
                evidence = adv["runtime_disposition_evidence"]
                self.assertTrue(evidence)
        mixed_alg = [adv for pkg in self.DELTA["packages"] for adv in pkg["advisories"]
                     if adv["id"] in {"GHSA-ffc3-869f-jxw9", "GHSA-p4g4-x82p-q773",
                                      "GHSA-r6x4-923q-g947", "GHSA-w2cx-738m-mc7w"}]
        for adv in mixed_alg:
            self.assertIn("HS256", adv["runtime_disposition_evidence"])

    def test_unknown_stay_regressions(self):
        triage = t.load_triage()
        res = t.triage_python([{"package": {"name": "pyjwt", "ecosystem": "PyPI"},
                                "version": "2.13.0", "id": "GHSA-zzzz-zzzz-zzzz",
                                "aliases": []}], triage)
        self.assertEqual(len(res["untriaged"]), 1)
        self.assertEqual(res["findings"][0]["disposition"], "REGRESSION")

    def test_cve_aliases_also_resolve(self):
        triage = t.load_triage()
        for aid, cve in (("GHSA-2gx3-rcp4-g85q", "CVE-2026-101917"),
                         ("GHSA-4p3w-j4w9-5jqw", "CVE-2026-17495")):
            self.assertIn(t._norm(aid), triage["by_id"])
            aliases = {t._norm(a) for a in (triage["by_id"][t._norm(aid)].get("aliases") or [])}
            self.assertIn(t._norm(cve), aliases)

    def test_no_overlap_with_prior_deltas_or_register(self):
        part2_ids = {t._norm(adv["id"]) for pkg in self.DELTA["packages"] for adv in pkg["advisories"]}
        prior_delta_ids = {"GHSA-hj66-6f7g-4r5v", "GHSA-xpv3-w29h-x7cv", "GHSA-w6j9-cwv2-h6wq",
                           "GHSA-253c-mchw-3w2r"}
        self.assertFalse(part2_ids & {t._norm(a) for a in prior_delta_ids})


class AdvisoryDeltaSeptember30Part3Tests(unittest.TestCase):
    """The third 2026-09-30 delta closes the two pyjwt advisories surfaced by run 36745670524."""

    DELTA = json.loads((ROOT / "docs/engineering/evidence/sec-deps-01/advisory-delta-2026-09-30-3"
                        "/delta-dispositions.json").read_text())
    EXPECTED = {"GHSA-jwrc-g2q2-pq5p": "NOT_REACHABLE", "GHSA-42vr-xj54-vc7v": "MITIGATED"}

    def test_both_findings_close_with_their_recorded_disposition(self):
        triage = t.load_triage()
        self.assertIn("advisory-delta-2026-09-30-3", triage["deltas"])
        findings = [{"package": {"name": "pyjwt", "ecosystem": "PyPI"}, "version": "2.13.0",
                     "id": aid, "aliases": []} for aid in self.EXPECTED]
        res = t.triage_python(findings, triage)
        self.assertEqual(res["untriaged"], [])
        self.assertEqual(t.overall_status(py_result=res), "pass")
        got = {f["id"]: f["disposition"] for f in res["findings"]}
        self.assertEqual(got, self.EXPECTED)

    def test_evidence_names_the_containing_handler_and_the_key_only_regex(self):
        by_id = {a["id"]: a for pkg in self.DELTA["packages"] for a in pkg["advisories"]}
        self.assertIn("except Exception", by_id["GHSA-42vr-xj54-vc7v"]["runtime_disposition_evidence"])
        self.assertIn("prepare_key", by_id["GHSA-jwrc-g2q2-pq5p"]["runtime_disposition_evidence"])


class AdvisoryDeltaOctober01Tests(unittest.TestCase):
    """The 2026-10-01 delta closes the PyJWT options-reuse advisory surfaced by run 36809316528."""

    DELTA = json.loads((ROOT / "docs/engineering/evidence/sec-deps-01/advisory-delta-2026-10-01"
                        "/delta-dispositions.json").read_text())

    def test_the_finding_closes_as_not_reachable(self):
        triage = t.load_triage()
        self.assertIn("advisory-delta-2026-10-01", triage["deltas"])
        findings = [{"package": {"name": "pyjwt", "ecosystem": "PyPI"}, "version": "2.13.0",
                     "id": "GHSA-gvp8-978c-rx2q", "aliases": []}]
        res = t.triage_python(findings, triage)
        self.assertEqual(res["untriaged"], [])
        self.assertEqual(t.overall_status(py_result=res), "pass")
        self.assertEqual({f["id"]: f["disposition"] for f in res["findings"]},
                         {"GHSA-gvp8-978c-rx2q": "NOT_REACHABLE"})

    def test_evidence_names_the_inline_per_call_options_and_the_call_sites(self):
        adv = self.DELTA["packages"][0]["advisories"][0]
        evidence = adv["runtime_disposition_evidence"]
        for needle in ("inline literal", "oauth.py:446-454", "oauth.py:467-475", "utils/oauth.py:200"):
            self.assertIn(needle, evidence)
        self.assertIsNone(adv["first_patched"])


if __name__ == "__main__":
    unittest.main()

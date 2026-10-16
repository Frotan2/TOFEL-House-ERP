"""Withdrawals may only tighten a covered advisory record (ERRATUM E6 mechanism)."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
import advisory_triage as t  # noqa: E402

REGISTER = {"packages": [{
    "package": "npm:example-lib@1.0.0",
    "advisories": [{"id": "GHSA-aaaa-bbbb-cccc", "runtime_disposition": "NOT_REACHABLE",
                    "runtime_disposition_evidence": "register premise", "aliases": []}],
}]}


def _delta(withdraws, packages=()):
    return {"packages": list(packages), "withdraws": list(withdraws)}


class WithdrawalTests(unittest.TestCase):
    def _load(self, delta):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "per-finding.json"
            base.write_text(json.dumps(REGISTER))
            (Path(tmp) / "advisory-delta-2026-10-15").mkdir()
            (Path(tmp) / "advisory-delta-2026-10-15" / "delta-dispositions.json").write_text(json.dumps(delta))
            return t.load_triage(base)

    def _item(self, **overrides):
        item = {"id": "GHSA-aaaa-bbbb-cccc", "package": "example-lib", "to": "BLOCKED",
                "erratum": "ERRATUM-test#e6", "reason": "premise invalid"}
        item.update(overrides)
        return item

    def test_withdrawal_tightens_and_keeps_the_original_disposition(self):
        triage = self._load(_delta([self._item()]))
        rec = triage["by_id"][t._norm("GHSA-aaaa-bbbb-cccc")]
        self.assertEqual(rec["runtime_disposition"], "BLOCKED")
        self.assertEqual(rec["withdrawn_from"], "NOT_REACHABLE")
        self.assertEqual(rec["withdrawn_by"]["erratum"], "ERRATUM-test#e6")
        self.assertEqual(rec["runtime_disposition_evidence"], "register premise")
        self.assertNotIn(rec["runtime_disposition"], t.CLOSED_DISPOSITIONS)
        # the package index shares the same record, so a package lookup sees the withdrawal too
        self.assertIs(triage["by_package"]["example-lib"][0], rec)

    def test_unknown_advisory_is_rejected(self):
        with self.assertRaises(SystemExit):
            self._load(_delta([self._item(id="GHSA-zzzz-zzzz-zzzz")]))

    def test_withdrawal_cannot_move_to_a_closed_disposition(self):
        for target in ("NOT_REACHABLE", "MITIGATED", "BUILD_ONLY", "DEV_ONLY", "INSTALL_ONLY",
                       "BROWSER_SELF_DENIAL", "BOGUS"):
            with self.subTest(target=target), self.assertRaises(SystemExit):
                self._load(_delta([self._item(to=target)]))

    def test_withdrawal_requires_erratum_and_reason(self):
        for field in ("erratum", "reason"):
            with self.subTest(field=field), self.assertRaises(SystemExit):
                self._load(_delta([self._item(**{field: ""})]))

    def test_withdrawal_must_name_the_same_package(self):
        with self.assertRaises(SystemExit):
            self._load(_delta([self._item(package="other-lib")]))

    def test_withdrawal_only_delta_adds_no_advisory_ids(self):
        triage = self._load(_delta([self._item()]))
        self.assertEqual(len(triage["by_id"]), 1)  # the register's single id; nothing added
        self.assertEqual(triage["delta_advisories"], 0)

    def test_the_real_2026_10_15_delta_withdraws_vhrc_only(self):
        triage = t.load_triage()
        self.assertEqual([w["id"] for w in triage["withdrawals"]], ["GHSA-vhrc-hgrq-x75r"])
        rec = triage["by_id"][t._norm("GHSA-vhrc-hgrq-x75r")]
        self.assertEqual(rec["runtime_disposition"], "BLOCKED")
        self.assertEqual(rec["withdrawn_from"], "BROWSER_SELF_DENIAL")


class UndispositionedWithdrawnAdvisoriesTests(unittest.TestCase):
    """Review item 4: two withdrawn advisories were undispositioned in the register."""

    def test_both_ids_are_build_only_with_withdrawal_evidence(self):
        triage = t.load_triage()
        for ghsa, pkg, withdrawn in (("GHSA-gv7w-rqvm-qjhr", "esbuild", "2026-06-17"),
                                     ("GHSA-8p5q-j9m2-g8wr", "lodash", "2021-10-01")):
            with self.subTest(ghsa=ghsa):
                rec = triage["by_id"][t._norm(ghsa)]
                self.assertEqual(rec["runtime_disposition"], "BUILD_ONLY")
                self.assertTrue(rec["package"].startswith("npm:" + pkg + "@"))
                self.assertIn(withdrawn, rec["runtime_disposition_evidence"])
                self.assertIn("withdrawn", rec["runtime_disposition_evidence"].lower())
                self.assertEqual(rec["source_delta"], "advisory-delta-2026-10-15")


class PyPaMirrorTests(unittest.TestCase):
    """Run 38899033333 (head 61c4c42) surfaced two PyPA mirror ids as untriaged.

    They mirror GHSA ids already dispositioned in the 2026-10-09 delta, with the same range.
    """

    def _finding(self, package, version, pid, aliases):
        return {"package": {"name": package, "ecosystem": "PyPI"}, "version": version,
                "id": pid, "aliases": aliases}

    def test_ci_style_findings_resolve_to_their_mirrored_disposition(self):
        triage = t.load_triage()
        cases = [
            ("weasyprint", "68.0", "PYSEC-2026-4311", ["CVE-2026-106443", "GHSA-r543-q48m-4c9j"],
             "MITIGATED"),
            ("werkzeug", "3.1.6", "PYSEC-2026-4312", ["CVE-2026-102598", "GHSA-g6x2-hccm-hh4m"],
             "NOT_REACHABLE"),
        ]
        for package, version, pid, aliases, expected in cases:
            with self.subTest(pid=pid):
                res = t.triage_python([self._finding(package, version, pid, aliases)], triage)
                self.assertEqual(res["untriaged"], [])
                self.assertEqual(res["findings"][0]["disposition"], expected)


if __name__ == "__main__":
    unittest.main()

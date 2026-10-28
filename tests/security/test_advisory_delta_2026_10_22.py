"""2026-10-22 npm advisory delta and bundle-evidence regression."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
import advisory_triage as triage  # noqa: E402

DELTA = ROOT / "docs/engineering/evidence/sec-deps-01/advisory-delta-2026-10-22"


class October22AdvisoryDeltaTests(unittest.TestCase):
    def test_eight_new_development_path_records_are_dev_only(self):
        loaded = triage.load_triage()
        cases = (
            ("launch-editor", "1242627"),
            ("launch-editor", "1242656"),
            ("launch-editor", "1242663"),
            ("vite", "1242622"),
            ("vite", "1242651"),
            ("vite", "1242658"),
            ("vite", "1242724"),
            ("vite", "1242730"),
        )
        for package, finding_id in cases:
            with self.subTest(package=package, finding_id=finding_id):
                record = triage.disposition_for_finding(
                    loaded, package=package, finding_id=finding_id)
                self.assertIsNotNone(record)
                self.assertEqual(record["runtime_disposition"], "DEV_ONLY")
                self.assertEqual(record["source_delta"], "advisory-delta-2026-10-22")
                self.assertIn("production", record["runtime_disposition_evidence"].lower())

    def test_bundle_evidence_is_supporting_not_a_waiver(self):
        evidence = json.loads((DELTA / "production-bundle-evidence.json").read_text())
        self.assertEqual(evidence["source_run"], 39829102419)
        self.assertEqual(evidence["source_artifact_id"], 12449413937)
        self.assertEqual(
            evidence["artifact_file_sha256"],
            "8abd22e33e5cf2d51fe3b23f506eaa8a3c5b77a713f169ee5100b891c4ef5203",
        )
        self.assertEqual(
            evidence["advisory_artifact_file_sha256"],
            "a39f446facc88f8409df2b185d7cebc89b71871cb8297426896336ed8765614d",
        )
        self.assertEqual(
            {row["npm_id"]: row["ghsa"] for row in evidence["newly_mapped_advisories"]},
            {1242724: "GHSA-9jrq-w75r-8gcw", 1242730: "GHSA-rq7h-c2jc-7f22"},
        )
        self.assertEqual(evidence["status"], "pass")
        self.assertEqual(
            sorted(evidence["absent_packages"]),
            ["launch-editor", "markdown-it", "vite"],
        )
        self.assertIn("not a vulnerability waiver", evidence["scope"])

    def test_late_vite_ids_resolve_by_numeric_id_and_ghsa_alias(self):
        loaded = triage.load_triage()
        for finding_id, ghsa in (
            ("1242724", "GHSA-9jrq-w75r-8gcw"),
            ("1242730", "GHSA-rq7h-c2jc-7f22"),
        ):
            by_id = triage.disposition_for_finding(
                loaded, package="vite", finding_id=finding_id)
            by_alias = triage.disposition_for_finding(
                loaded, package="vite", advisories=[ghsa])
            self.assertEqual(by_id["runtime_disposition"], "DEV_ONLY")
            self.assertEqual(by_alias["runtime_disposition"], "DEV_ONLY")

    def test_markdown_it_is_fixed_not_dispositioned_here(self):
        delta = json.loads((DELTA / "delta-dispositions.json").read_text())
        packages = [p["package"] for p in delta["packages"]]
        self.assertFalse(any("markdown-it" in package for package in packages))


if __name__ == "__main__":
    unittest.main()

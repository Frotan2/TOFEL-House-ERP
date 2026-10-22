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
    def test_six_new_editor_launch_records_are_dev_only(self):
        loaded = triage.load_triage()
        cases = (
            ("launch-editor", "1242627"),
            ("launch-editor", "1242656"),
            ("launch-editor", "1242663"),
            ("vite", "1242622"),
            ("vite", "1242651"),
            ("vite", "1242658"),
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
        self.assertEqual(evidence["source_run"], 39597802134)
        self.assertEqual(
            evidence["artifact_file_sha256"],
            "79f7d1ba34e351d403cae22f4458138a0babfe71e6989a948cecdb7c8d896957",
        )
        self.assertEqual(evidence["status"], "pass")
        self.assertEqual(
            sorted(evidence["absent_packages"]),
            ["launch-editor", "markdown-it", "vite"],
        )
        self.assertIn("not a vulnerability waiver", evidence["scope"])

    def test_markdown_it_is_fixed_not_dispositioned_here(self):
        delta = json.loads((DELTA / "delta-dispositions.json").read_text())
        packages = [p["package"] for p in delta["packages"]]
        self.assertFalse(any("markdown-it" in package for package in packages))


if __name__ == "__main__":
    unittest.main()

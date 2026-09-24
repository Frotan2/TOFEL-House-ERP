"""SEC-DEPS-01 readable-audit slice: advisory ids must survive as annotations."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "foundation"))
from runtime_install import (ANNOTATION_MAX_LINES, ANNOTATION_TEXT_LIMIT,  # noqa: E402
                             advisory_finding_annotations)

PREFIX = "::warning file=tools/foundation/runtime_install.py::"


def stack(py=(), npm=()):
    return {"python": {"osv": {"findings": list(py)}},
            "node": {"finding_summary": list(npm)}}


class AdvisoryAnnotationTests(unittest.TestCase):
    def test_public_ids_are_preferred_from_aliases_and_urls(self):
        lines = advisory_finding_annotations(stack(
            py=[{"package": "pypdf", "version": "3.1", "id": "PYSEC-2099-1",
                 "aliases": ["GHSA-aaaa-bbbb-cccc"], "severity": "HIGH"}],
            npm=[{"package": "lodash", "installed_versions": ["4.17.0"], "id": 1234,
                  "url": "https://github.com/advisories/GHSA-dddd-eeee-ffff",
                  "severity": "moderate"}]), None)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(PREFIX + "advisory matches=2 in 2 packages: "))
        self.assertIn("py:pypdf@3.1 GHSA-aaaa-bbbb-cccc(high)", lines[0])
        self.assertLess(lines[0].index("py:"), lines[0].index("npm:"))
        self.assertIn("npm:lodash@4.17.0 GHSA-dddd-eeee-ffff(moderate)", lines[0])

    def test_no_findings_no_annotation_and_missing_reports_are_tolerated(self):
        self.assertEqual(advisory_finding_annotations(stack(), {"advisories": {}}), [])
        self.assertEqual(advisory_finding_annotations(None, None), [])

    def test_frontend_advisories_are_named(self):
        lines = advisory_finding_annotations(None, {"advisories": {
            "axios": [{"id": 99, "url": "https://github.com/advisories/GHSA-1111-2222-3333",
                       "severity": "high"}]}})
        self.assertIn("fe:axios GHSA-1111-2222-3333(high)", lines[0])

    def test_lines_are_single_bounded_and_truncation_is_stated(self):
        many = [{"package": f"pkg{i:03d}", "version": "1.0", "id": f"GHSA-{i:04d}-xxxx-yyyy",
                 "severity": "LOW"} for i in range(400)]
        lines = advisory_finding_annotations(stack(py=many), None)
        self.assertLessEqual(len(lines), ANNOTATION_MAX_LINES)
        for line in lines:
            self.assertNotIn("\n", line)
            self.assertLessEqual(len(line) - len(PREFIX), ANNOTATION_TEXT_LIMIT)
        self.assertRegex(lines[-1], r"\+\d+ packages not shown$")

    def test_grouped_by_package_worst_first_and_frontend_dedup(self):
        lines = advisory_finding_annotations(stack(npm=[
            {"package": "a", "installed_versions": ["1"], "id": "GHSA-low1", "severity": "low"},
            {"package": "b", "installed_versions": ["2"], "id": "GHSA-crit", "severity": "critical"},
            {"package": "b", "installed_versions": ["2"], "id": "GHSA-mod1", "severity": "moderate"}]),
            {"advisories": {"b": [{"id": "GHSA-crit", "severity": "critical"}],
                            "c": [{"id": "GHSA-fe01", "severity": "high"}]}})
        text = lines[0]
        self.assertIn("advisory matches=4 in 3 packages", text)
        self.assertIn("npm:b@2 GHSA-crit(critical),GHSA-mod1(moderate)", text)
        self.assertLess(text.index("npm:b@2"), text.index("npm:a@1"))
        self.assertNotIn("fe:b", text)
        self.assertIn("fe:c GHSA-fe01(high)", text)

    def test_ids_are_never_invented(self):
        lines = advisory_finding_annotations(stack(
            py=[{"package": "x", "version": "1", "id": None}]), None)
        self.assertIn("unidentified", lines[0])

    def test_runtime_emits_annotations_from_its_own_reports(self):
        source = (Path(__file__).resolve().parents[2]
                  / "tools/foundation/runtime_install.py").read_text()
        self.assertIn("advisory_finding_annotations(*audits)", source)
        self.assertIn('"stack-dependency-audit.json", "frontend-advisories.json"', source)


if __name__ == "__main__":
    unittest.main()

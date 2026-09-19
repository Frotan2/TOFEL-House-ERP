"""Guard the evidence-driven rejection of unsupported SEC-DEPS candidate inputs."""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DependencyRemediationCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = json.loads((ROOT / "docs/engineering/foundation-version-matrix.json").read_text())
        cls.components = {component["name"]: component for component in cls.matrix["components"]}
        cls.assessment = json.loads((ROOT / "docs/engineering/evidence/phase-2/"
                                     "dependency-remediation-candidate-assessment-2026-09-16.json").read_text())

    def test_assessment_keeps_baseline_unmodified_and_rejects_a_fabricated_candidate(self):
        self.assertTrue(self.assessment["baseline_unchanged"])
        self.assertEqual(self.assessment["status"], "rejected_no_credible_official_candidate")
        self.assertFalse(self.assessment["candidate_execution"]["built"])
        self.assertEqual(self.assessment["production_recommendation"], "REJECT")

    def test_official_review_hashes_match_the_current_pinned_dependency_inputs(self):
        for name in ("frappe", "erpnext", "education"):
            expected = self.components[name]["source_file_sha256"]
            observed = self.assessment["official_input_review"][name]["dependency_input_sha256"]
            for path, digest in observed.items():
                self.assertEqual(expected[path], digest, name + "/" + path)

    def test_unresolved_python_and_node_inputs_rule_out_a_clean_candidate(self):
        blockers = {item["package"]: item for item in self.assessment["python_remediation_blockers"]}
        self.assertEqual(set(blockers), {"pdfkit", "pypdf", "weasyprint", "setuptools"})
        self.assertIsNone(blockers["pdfkit"]["first_patched_version"])
        self.assertEqual(blockers["setuptools"]["first_patched_version"], "83.0.0")
        self.assertIn("<82.0.0", blockers["setuptools"]["blocker"])
        node = self.assessment["node_remediation_blocker"]
        self.assertEqual((node["observed_entries"], node["observed_packages"]), (97, 36))
        self.assertIn("would not be an officially released compatible", node["blocker"])


class DependencyRemediationReverificationTests(unittest.TestCase):
    """The 2026-09-19 live re-verification must carry the same verdict with
    fresh evidence: same blockers, same REJECT, newly observed upstream state."""

    @classmethod
    def setUpClass(cls):
        cls.assessment = json.loads((ROOT / "docs/engineering/evidence/phase-2/"
                                     "dependency-remediation-candidate-assessment-2026-09-19.json").read_text())

    def test_reverification_keeps_baseline_unmodified_and_rejects_a_fabricated_candidate(self):
        self.assertEqual(self.assessment["observed_date"], "2026-09-19")
        self.assertTrue(self.assessment["baseline_unchanged"])
        self.assertEqual(self.assessment["status"], "rejected_no_credible_official_candidate")
        self.assertFalse(self.assessment["candidate_execution"]["built"])
        self.assertEqual(self.assessment["production_recommendation"], "REJECT")

    def test_reverification_carries_the_same_blocker_set(self):
        blockers = {item["package"]: item for item in self.assessment["python_remediation_blockers"]}
        self.assertEqual(set(blockers), {"pdfkit", "pypdf", "weasyprint", "setuptools"})
        self.assertIsNone(blockers["pdfkit"]["first_patched_version"])
        self.assertEqual(blockers["setuptools"]["first_patched_version"], "83.0.0")
        node = self.assessment["node_remediation_blocker"]
        self.assertEqual((node["observed_entries"], node["observed_packages"]), (97, 36))

    def test_reverification_records_fresh_live_observations(self):
        review = self.assessment["official_input_review"]
        pins = review["frappe"]["pins_at_tag"]
        self.assertEqual((pins["pypdf"], pins["WeasyPrint"], pins["pdfkit"]),
                         ("==6.15.0", "==68.0", "~=1.0.0"))
        self.assertEqual(review["hrms"]["newest_non_prerelease"]["tag"], "v16.19.0")
        self.assertIn("byte-identical", review["hrms"]["comparison"])
        self.assertEqual(review["bench"]["constraint"], "setuptools>=71.0.0,<82.0.0")
        fresh = self.assessment["baseline_evidence"]["fresh_hosted_confirmation"]
        self.assertEqual(fresh["run"], "35450528487")
        self.assertEqual(fresh["conclusion"], "failure")
        self.assertIn("NOT established", self.assessment["reachability_notes"]["pdfkit"])


if __name__ == "__main__":
    unittest.main()

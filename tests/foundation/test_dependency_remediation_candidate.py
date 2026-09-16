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


if __name__ == "__main__":
    unittest.main()

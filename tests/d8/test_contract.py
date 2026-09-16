"""Structural D8 operations contract tests; no infrastructure is contacted."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("d8_validate", ROOT / "tools/foundation/d8_validate.py")
d8 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d8)


class D8ContractTests(unittest.TestCase):
    def setUp(self):
        self.matrix = json.loads(d8.MATRIX_PATH.read_text())
        self.template = json.loads(d8.TEMPLATE_PATH.read_text())

    def test_template_is_explicitly_blocked_and_production_disabled(self):
        report = d8.run(d8.TEMPLATE_PATH)
        self.assertEqual(report["d8_gate_state"], "BLOCKED")
        self.assertEqual(report["production_state"], "REJECT")
        self.assertFalse(report["production_enabled"])
        self.assertTrue(report["unresolved_owner_decisions"])
        self.assertEqual(report["sec_deps"], "UPSTREAM-BLOCKED / REJECT")
        self.assertTrue(report["checkout_branch_matches_active"])

    def test_matrix_has_one_explicit_decision_record_per_area(self):
        ids = [item["id"] for item in self.matrix["decisions"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("D8-OWNERSHIP-CHARTER", ids)
        self.assertIn("D8-SECURITY-DEPENDENCY", ids)
        self.assertEqual(self.matrix["production_state"], "REJECT")
        self.assertEqual(self.matrix["overall_gate_state"], "BLOCKED")

    def test_production_enablement_is_fail_closed(self):
        invalid = copy.deepcopy(self.template)
        invalid["production_enabled"] = True
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            json.dump(invalid, handle)
            handle.flush()
            with self.assertRaises(d8.ContractError):
                d8.run(Path(handle.name))

    def test_not_selected_owner_values_are_rejected(self):
        invalid = copy.deepcopy(self.template)
        invalid["owner_selections"]["D8-CAPACITY-AVAILABILITY"]["values"] = {
            "concurrency_profile_reference": "invented-value"
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            json.dump(invalid, handle)
            handle.flush()
            with self.assertRaises(d8.ContractError):
                d8.run(Path(handle.name))

    def test_unknown_contract_field_is_rejected(self):
        invalid = copy.deepcopy(self.template)
        invalid["provider"] = "must-not-be-invented"
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            json.dump(invalid, handle)
            handle.flush()
            with self.assertRaises(d8.ContractError):
                d8.run(Path(handle.name))


if __name__ == "__main__":
    unittest.main()

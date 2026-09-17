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


class ActiveBranchEvidenceTests(unittest.TestCase):
    """A rotated active branch may have no hosted run; that absence is validated.

    The previous validator required `active_branch_qualification.foundation_runtime.run`
    to equal a pinned run id. A branch rotation therefore could not be recorded
    without asserting a run that never happened on the new branch. These tests pin
    the replacement: the absence is explicit, carries no execution identity, and
    cannot be filled in by re-labelling an older branch's evidence.
    """

    def setUp(self):
        self.ledger = json.loads(d8.LEDGER_PATH.read_text())
        self.active = self.ledger["active_branch_qualification"]
        self.assertEqual(self.active["branch"], d8.ACTIVE_BRANCH)

    def _run_with(self, mutate):
        ledger = copy.deepcopy(self.ledger)
        mutate(ledger)
        original = d8.LEDGER_PATH
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            json.dump(ledger, handle)
            handle.flush()
            d8.LEDGER_PATH = Path(handle.name)
            try:
                return d8.run(d8.TEMPLATE_PATH)
            finally:
                d8.LEDGER_PATH = original

    def test_active_branch_records_an_explicit_absence_of_execution(self):
        self.assertEqual(self.active["hosted_execution_state"], d8.ACTIVE_RUNTIME_NOT_EXECUTED)
        self.assertEqual(d8.ACTIVE_RUNTIME_STATE, d8.ACTIVE_RUNTIME_NOT_EXECUTED)
        self.assertIsNone(d8.ACTIVE_RUNTIME_RUN)
        for key in d8.EXECUTION_EVIDENCE_KEYS:
            self.assertNotIn(key, self.active, f"{key} must be empty while NOT_EXECUTED")
        self.assertEqual(self.active["production_state"], "REJECT")
        self.assertFalse(self.active["production_authorized"])

    def test_report_discloses_that_the_active_branch_has_no_hosted_run(self):
        report = d8.run(d8.TEMPLATE_PATH)
        self.assertEqual(report["active_branch_hosted_execution"], d8.ACTIVE_RUNTIME_NOT_EXECUTED)
        self.assertIn("has NO hosted execution", report["warning"])
        self.assertEqual(report["production_state"], "REJECT")
        self.assertEqual(report["d8_gate_state"], "BLOCKED")

    def test_a_not_executed_block_may_not_carry_run_identity(self):
        for field in ("run", "runtime_check", "head_sha", "report_sha256", "commit"):
            with self.subTest(field=field):
                def mutate(ledger, field=field):
                    ledger["active_branch_qualification"]["evidence"] = {field: "35122242581"}
                with self.assertRaises(d8.ContractError):
                    self._run_with(mutate)

    def test_a_not_executed_block_may_not_populate_evidence_subblocks(self):
        for key in d8.EXECUTION_EVIDENCE_KEYS:
            with self.subTest(key=key):
                def mutate(ledger, key=key):
                    ledger["active_branch_qualification"][key] = {"status": "fail_reject"}
                with self.assertRaises(d8.ContractError):
                    self._run_with(mutate)

    def test_claiming_execution_the_boundary_does_not_record_is_rejected(self):
        def mutate(ledger):
            ledger["active_branch_qualification"]["hosted_execution_state"] = "EXECUTED"
        original = d8.ACTIVE_RUNTIME_STATE
        d8.ACTIVE_RUNTIME_STATE = "NOT_EXECUTED_ON_THIS_BRANCH"
        try:
            with self.assertRaises(d8.ContractError):
                self._run_with(mutate)
        finally:
            d8.ACTIVE_RUNTIME_STATE = original

    def test_a_not_executed_block_may_not_relax_the_production_posture(self):
        def mutate(ledger):
            ledger["active_branch_qualification"]["production_state"] = "APPROVED"
        with self.assertRaises(d8.ContractError):
            self._run_with(mutate)

    def test_each_previous_session_branch_keeps_its_own_pinned_run(self):
        self.assertEqual(d8.PRIOR_ACTIVE_RUNTIME_RUN, "35122242581")
        self.assertEqual(d8.EARLIER_ACTIVE_RUNTIME_RUN, "35090904508")
        prior = self.ledger["prior_active_branch_provenance"]
        earlier = self.ledger["earlier_active_branch_provenance"]
        self.assertEqual(prior["branch"], d8.PRIOR_ACTIVE_BRANCH)
        self.assertEqual(earlier["branch"], d8.EARLIER_ACTIVE_BRANCH)
        for block in (prior, earlier):
            self.assertEqual(block["classification"], "historical_provenance")
            self.assertEqual(block["foundation_runtime"]["status"], "fail_reject")

    def test_the_pinned_prior_run_belongs_to_the_previous_branch_not_the_active_one(self):
        """The evidence that could be re-labelled genuinely is another branch's.

        This is why the explicit-absence state matters: run 35122242581 executed
        on the previous session branch, so presenting it as an execution on the
        active branch would be false. The validator blocks that by refusing any
        execution identity inside a NOT_EXECUTED block (asserted above) and by
        refusing an EXECUTED claim the session boundary does not record.
        """
        runtime = self.ledger["prior_active_branch_provenance"]["foundation_runtime"]
        self.assertEqual(runtime["run"], d8.PRIOR_ACTIVE_RUNTIME_RUN)
        self.assertEqual(runtime["head_branch"], d8.PRIOR_ACTIVE_BRANCH)
        self.assertNotEqual(runtime["head_branch"], d8.ACTIVE_BRANCH)
        # None of that run's identifiers may appear in the active block.
        serialized = json.dumps(self.active)
        for field, value in runtime.items():
            if isinstance(value, str) and len(value) >= 8 and field != "head_branch":
                self.assertNotIn(value, serialized,
                                 f"prior-branch {field} leaked into the active block")


if __name__ == "__main__":
    unittest.main()

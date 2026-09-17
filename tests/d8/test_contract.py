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
    """The active branch now carries real hosted evidence, and it must stay honest.

    This class originally pinned the opposite situation: a rotated branch with no
    hosted run at all, where the danger was that the absence would be filled in by
    re-labelling an older branch's run. All five named workflows have since been
    genuinely re-executed on this branch, so the block records observed results.

    Both dangers are still tested. The EXECUTED path is pinned to one exact run id
    that must be a REJECT while SEC-DEPS-01 is open, so it cannot be swapped for a
    passing run. The NOT_EXECUTED path keeps its own guards, driven here by forcing
    that state explicitly, so a future rotation back to it is still fail-closed.
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

    def _run_forcing_not_executed(self, mutate):
        """Drive the NOT_EXECUTED guards with both sides of the state consistent."""
        ledger = copy.deepcopy(self.ledger)
        block = ledger["active_branch_qualification"]
        block["hosted_execution_state"] = d8.ACTIVE_RUNTIME_NOT_EXECUTED
        for key in d8.EXECUTION_EVIDENCE_KEYS:
            block.pop(key, None)
        mutate(ledger)
        original_path, original_state = d8.LEDGER_PATH, d8.ACTIVE_RUNTIME_STATE
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            json.dump(ledger, handle)
            handle.flush()
            d8.LEDGER_PATH = Path(handle.name)
            d8.ACTIVE_RUNTIME_STATE = d8.ACTIVE_RUNTIME_NOT_EXECUTED
            try:
                return d8.run(d8.TEMPLATE_PATH)
            finally:
                d8.LEDGER_PATH = original_path
                d8.ACTIVE_RUNTIME_STATE = original_state

    # --- the EXECUTED path -------------------------------------------------

    def test_active_branch_records_its_real_hosted_execution(self):
        self.assertEqual(self.active["hosted_execution_state"], "EXECUTED")
        self.assertEqual(d8.ACTIVE_RUNTIME_STATE, "EXECUTED")
        runtime = self.active["foundation_runtime"]
        self.assertEqual(runtime["run"], d8.ACTIVE_RUNTIME_RUN)
        self.assertEqual(runtime["head_branch"], d8.ACTIVE_BRANCH)
        self.assertEqual(runtime["head_sha"], self.active["qualification_commit"])
        # Every evidence subblock the validator knows about must be present.
        for key in d8.EXECUTION_EVIDENCE_KEYS:
            self.assertIn(key, self.active, f"{key} is missing from the active block")

    def test_the_active_runtime_must_be_a_reject_while_sec_deps_01_is_open(self):
        self.assertEqual(self.active["foundation_runtime"]["status"], "fail_reject")
        for flag in ("phase2_gate_passed", "security_gate_passed",
                     "product_implementation_authorized"):
            self.assertIs(self.active["foundation_runtime"][flag], False, flag)
        self.assertEqual(self.active["production_state"], "REJECT")
        self.assertFalse(self.active["production_authorized"])

    def test_the_active_runtime_run_may_not_be_swapped_for_another(self):
        """The pin is asserted by value, so a different run cannot be substituted."""
        def mutate(ledger):
            ledger["active_branch_qualification"]["foundation_runtime"]["run"] = "35122242581"
        with self.assertRaises(d8.ContractError):
            self._run_with(mutate)

    def test_the_active_runtime_may_not_claim_a_pass(self):
        def mutate(ledger):
            ledger["active_branch_qualification"]["foundation_runtime"]["status"] = "pass"
        with self.assertRaises(d8.ContractError):
            self._run_with(mutate)

    def test_the_active_runtime_gate_flags_may_not_be_relaxed(self):
        for flag in ("phase2_gate_passed", "security_gate_passed",
                     "product_implementation_authorized"):
            with self.subTest(flag=flag):
                def mutate(ledger, flag=flag):
                    ledger["active_branch_qualification"]["foundation_runtime"][flag] = True
                with self.assertRaises(d8.ContractError):
                    self._run_with(mutate)

    def test_report_discloses_the_execution_without_relaxing_any_gate(self):
        report = d8.run(d8.TEMPLATE_PATH)
        self.assertEqual(report["active_branch_hosted_execution"], "EXECUTED")
        # The absence warning must be gone, and no gate may have moved because of it.
        self.assertNotIn("has NO hosted execution", report["warning"])
        self.assertEqual(report["production_state"], "REJECT")
        self.assertEqual(report["d8_gate_state"], "BLOCKED")
        self.assertEqual(report["sec_deps"], "UPSTREAM-BLOCKED / REJECT")

    # --- the NOT_EXECUTED path, still fail-closed -------------------------

    def test_a_not_executed_block_may_not_carry_run_identity(self):
        for field in ("run", "runtime_check", "head_sha", "report_sha256", "commit"):
            with self.subTest(field=field):
                def mutate(ledger, field=field):
                    ledger["active_branch_qualification"]["evidence"] = {field: "35122242581"}
                with self.assertRaises(d8.ContractError):
                    self._run_forcing_not_executed(mutate)

    def test_a_not_executed_block_may_not_populate_evidence_subblocks(self):
        for key in d8.EXECUTION_EVIDENCE_KEYS:
            with self.subTest(key=key):
                def mutate(ledger, key=key):
                    ledger["active_branch_qualification"][key] = {"status": "fail_reject"}
                with self.assertRaises(d8.ContractError):
                    self._run_forcing_not_executed(mutate)

    def test_a_not_executed_block_may_not_relax_the_production_posture(self):
        def mutate(ledger):
            ledger["active_branch_qualification"]["production_state"] = "APPROVED"
        with self.assertRaises(d8.ContractError):
            self._run_forcing_not_executed(mutate)

    def test_claiming_execution_the_boundary_does_not_record_is_rejected(self):
        def mutate(ledger):
            ledger["active_branch_qualification"]["hosted_execution_state"] = "EXECUTED"
        original = d8.ACTIVE_RUNTIME_STATE
        d8.ACTIVE_RUNTIME_STATE = d8.ACTIVE_RUNTIME_NOT_EXECUTED
        try:
            with self.assertRaises(d8.ContractError):
                self._run_with(mutate)
        finally:
            d8.ACTIVE_RUNTIME_STATE = original

    def test_claiming_no_execution_the_boundary_does_record_is_rejected(self):
        """The mirror image: dropping back to an absence is equally a drift."""
        def mutate(ledger):
            ledger["active_branch_qualification"]["hosted_execution_state"] = (
                d8.ACTIVE_RUNTIME_NOT_EXECUTED)
        with self.assertRaises(d8.ContractError):
            self._run_with(mutate)

    # --- provenance separation -------------------------------------------

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

    def test_no_identifier_of_a_previous_branch_run_leaks_into_the_active_block(self):
        """Re-labelling another branch's run as this branch's is still blocked.

        Only execution *identity* is compared. Status enums such as
        ``fail_reject`` legitimately recur across branches - two honest REJECTs on
        different branches should not be reported as leakage - whereas a run id,
        commit, check id or report digest appearing in both would mean the active
        block is citing another branch's execution.
        """
        serialized = json.dumps(self.active)
        for label, block in (("prior", self.ledger["prior_active_branch_provenance"]),
                             ("earlier", self.ledger["earlier_active_branch_provenance"])):
            runtime = block["foundation_runtime"]
            self.assertEqual(runtime["run"],
                             d8.PRIOR_ACTIVE_RUNTIME_RUN if label == "prior"
                             else d8.EARLIER_ACTIVE_RUNTIME_RUN)
            self.assertNotEqual(runtime["head_branch"], d8.ACTIVE_BRANCH)
            for field, value in runtime.items():
                # `head_branch` is excluded deliberately: the active block *names*
                # the previous branch as its rotation origin, which is provenance
                # and not a claim that the run happened here.
                if field not in d8.EXECUTION_IDENTITY_FIELDS or not isinstance(value, str):
                    continue
                if field == "head_branch":
                    continue
                self.assertNotIn(value, serialized,
                                 f"{label}-branch {field} leaked into the active block")

    def test_the_active_run_id_is_not_any_previous_branch_run(self):
        self.assertNotIn(d8.ACTIVE_RUNTIME_RUN,
                         (d8.PRIOR_ACTIVE_RUNTIME_RUN, d8.EARLIER_ACTIVE_RUNTIME_RUN),
                         "the active branch pins a run that belongs to an earlier branch")


if __name__ == "__main__":
    unittest.main()

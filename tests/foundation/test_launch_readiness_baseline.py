# -*- coding: utf-8 -*-
"""The owner re-baseline of 2026-09-19 separates two different questions.

``production_state`` asks whether every selected gate is independently evidenced
on the exact SHA. ``local_launch_readiness`` asks the question in section 9 of
the directive: can staff run ordinary daily operations on the selected
local-server + Tailscale deployment today? Conflating them is what kept the
product trapped in a pre-production state, because enterprise hardening items
were indistinguishable from launch-critical ones.

The re-baseline was required to classify gates, not to soften them. These tests
hold that line: no gate state may change as a side effect of classification, and
the readiness rollup must be derived from the matrix rather than asserted by
hand, so it cannot drift out of agreement with the gates it summarises.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs/engineering/d8-production-operations-decision-matrix.json"

VALID = ("launch_critical", "operational_hardening", "future_scope")

# Recorded at the moment of the re-baseline. Any change here is a real change to
# the product's stated posture and must be a deliberate, reviewed edit - not a
# side effect of adding a gate or reclassifying one.
STATES_AT_REBASELINE = {
    "domain-qualification": "PASS",
    "authorization-isolation": "PASS",
    "dependency-security": "REJECT",
    "recovery": "BLOCKED",
    "backup-restore": "BLOCKED",
    "upgrade-rollback": "BLOCKED",
    "realtime": "PASS",
    "observability": "BLOCKED",
    "ownership": "PASS",
    "topology-edge-session": "BLOCKED",
    "capacity-availability": "BLOCKED",
    "durability": "BLOCKED",
    "change-control": "BLOCKED",
    "production-authorization": "REJECT",
}


class LaunchReadinessBaselineTests(unittest.TestCase):

    def setUp(self):
        self.matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        self.gates = self.matrix["release_gate_matrix"]

    def test_every_gate_carries_a_valid_launch_classification(self):
        for gate in self.gates:
            self.assertIn(gate["launch_classification"], VALID, gate["id"])
            self.assertIn("§1", gate["launch_classification_basis"],
                          f"{gate['id']} cites no clause of the owner directive")

    def test_classification_did_not_soften_any_gate_state(self):
        """The re-baseline may classify; it may not quietly improve a result."""
        observed = {g["id"]: g["state"] for g in self.gates}
        self.assertEqual(observed, STATES_AT_REBASELINE)

    def test_overall_posture_is_unchanged(self):
        self.assertEqual(self.matrix["production_state"], "REJECT")
        self.assertEqual(self.matrix["overall_gate_state"], "BLOCKED")
        self.assertEqual(self.matrix["security_dependency_state"],
                         "UPSTREAM-BLOCKED / REJECT")

    def test_the_rollup_is_derived_not_hand_typed(self):
        """Recompute the summary from the gates; drift is a failure."""
        readiness = self.matrix["local_launch_readiness"]
        lc = [g for g in self.gates
              if g["launch_classification"] == "launch_critical"]
        self.assertEqual(readiness["launch_critical_satisfied"],
                         sorted(g["id"] for g in lc if g["state"] == "PASS"))
        self.assertEqual(readiness["launch_critical_unsatisfied"],
                         sorted(g["id"] for g in lc if g["state"] != "PASS"))
        self.assertEqual(readiness["launch_critical_gate_count"], len(lc))
        self.assertEqual(
            readiness["deferred_operational_hardening"],
            sorted(g["id"] for g in self.gates
                   if g["launch_classification"] == "operational_hardening"))

    def test_an_unsatisfied_launch_critical_gate_forbids_a_ready_verdict(self):
        """Readiness must follow the gates, never be asserted over them."""
        readiness = self.matrix["local_launch_readiness"]
        if readiness["launch_critical_unsatisfied"]:
            self.assertNotIn("READY", readiness["verdict"].replace("NOT YET READY", ""))
            self.assertEqual(readiness["verdict"], "NOT YET READY")

    def test_deferring_a_gate_does_not_claim_it_passes(self):
        """Hardening/future classification is a scope statement, not a waiver."""
        for gate in self.gates:
            if gate["launch_classification"] in ("operational_hardening",
                                                 "future_scope"):
                self.assertNotEqual(gate["state"], "WAIVED", gate["id"])
                self.assertNotIn("waiv", gate["scope"].lower(), gate["id"])

    def test_dependency_security_stays_launch_critical(self):
        """§8: an unreadable advisory report is a limitation, not an all-clear.

        Keeping this launch-critical is what stops the evidence gap from being
        reclassified away as future work.
        """
        gate = next(g for g in self.gates
                    if g["id"] == "dependency-security")
        self.assertEqual(gate["launch_classification"], "launch_critical")
        self.assertEqual(gate["state"], "REJECT")
        self.assertIn("evidence-limited", gate["launch_classification_note"])


if __name__ == "__main__":
    unittest.main()


class SecurityDependencyEvidenceTests(unittest.TestCase):
    """Section 8: an unreadable advisory report is neither a finding nor a clean
    result. Both directions are fabrications, so both are pinned here."""

    def setUp(self):
        self.matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        self.detail = self.matrix["security_dependency_state_detail"]

    def test_recording_the_detail_did_not_change_the_state(self):
        self.assertEqual(self.matrix["security_dependency_state"],
                         "UPSTREAM-BLOCKED / REJECT")
        self.assertEqual(self.detail["state"], "UPSTREAM-BLOCKED / REJECT")
        self.assertTrue(self.detail["state_unchanged_by_this_record"])

    def test_the_limitation_is_classified_as_a_limitation(self):
        self.assertIn("EVIDENCE AND INSPECTION LIMITATION",
                      self.detail["classification"])
        self.assertIn("NOT A DEMONSTRATED EXPLOITABLE FINDING",
                      self.detail["classification"])
        self.assertIn("NOT AN ALL-CLEAR", self.detail["classification"])

    def test_known_and_unknown_are_separated_not_blurred(self):
        self.assertTrue(self.detail["what_is_known"])
        self.assertTrue(self.detail["what_is_not_known"])
        joined_known = " ".join(self.detail["what_is_known"])
        self.assertNotIn("no vulnerabilit", joined_known.lower(),
                         "the known list must not smuggle in a clean result")

    def test_no_advisory_identifiers_are_invented(self):
        """A fabricated CVE would be the most dangerous possible content here."""
        import re
        blob = json.dumps(self.detail)
        self.assertEqual(re.findall(r"CVE-\d{4}-\d+", blob), [])

    def test_the_owner_position_is_recorded_as_the_owners(self):
        self.assertEqual(self.detail["owner_position"]["date"], "2026-09-19")
        self.assertIn("Owner's decision, not an engineering default",
                      self.detail["owner_position"]["effect"])

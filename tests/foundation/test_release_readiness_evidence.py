"""Run the bounded release-readiness evidence harness in a disposable workspace."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/foundation/release_readiness_evidence.py"
spec = importlib.util.spec_from_file_location("release_readiness_evidence", SCRIPT)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class ReleaseReadinessEvidenceTests(unittest.TestCase):
    def test_reproducible_bounded_evidence_and_fail_closed_release_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = evidence.run_evidence(
                output=root / "release-readiness-evidence.json",
                artifact_dir=root / "artifacts",
            )
        self.assertEqual(report["baseline_commit"], "14cd64e")
        self.assertEqual(report["production_state"], "REJECT")
        self.assertFalse(report["production_enabled"])
        self.assertEqual(report["security_dependency_state"], "UPSTREAM-BLOCKED / REJECT")
        self.assertEqual(report["proofs"]["encrypted_versioned_backup"]["status"], "PASS / BOUNDED")
        self.assertEqual(report["proofs"]["restore_on_another_system"]["status"], "PASS / BOUNDED")
        self.assertEqual(report["proofs"]["durable_db_and_file_preservation"]["status"], "PASS / BOUNDED")
        self.assertEqual(report["proofs"]["offboarding_emergency_revocation"]["status"], "PASS / BOUNDED")
        self.assertEqual(report["proofs"]["branch_isolation"]["status"], "BLOCKED / NOT PROVEN")
        self.assertEqual(report["release_gate_state"]["backup_restore"], "BLOCKED / ENCRYPTED BACKUP RESTORED WITH A CUSTODY-RETRIEVED KEY AND BOTH KEYS ROTATED; OFF-SITE DESTINATION, VERSIONING, RETENTION AND TRUST-BOUNDARY CUSTODY NOT PROVEN")
        self.assertEqual(report["release_gate_state"]["recovery"], "BLOCKED / SEPARATE-SYSTEM REHEARSAL AND KEY RETRIEVAL FROM SEPARATE CUSTODY EXECUTED; SESSION REVOCATION AND MEASURED RPO/RTO NOT PROVEN")
        self.assertEqual(report["release_gate_state"]["production_authorization"], "REJECT")
        # Executing sub-probes may refine the wording after the slash, but it may
        # never drop the fail-closed prefix. Run 35179445639 executed key custody
        # and rotation; that is why these two strings changed, and neither gate
        # changed state.
        for gate, state in report["release_gate_state"].items():
            self.assertTrue(state.startswith("BLOCKED") or state.startswith("REJECT")
                            or state.startswith("PASS / SCOPED"),
                            gate + " lost its fail-closed prefix: " + state)
        self.assertTrue(report["release_gate_state"]["backup_restore"].startswith("BLOCKED"))
        self.assertTrue(report["release_gate_state"]["recovery"].startswith("BLOCKED"))


if __name__ == "__main__":
    unittest.main()

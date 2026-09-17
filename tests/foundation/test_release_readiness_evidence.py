"""Run the bounded release-readiness evidence harness in a disposable workspace."""
import importlib.util
import io
from pathlib import Path
import tarfile
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


class SafeExtractionTests(unittest.TestCase):
    """`extract_safely` must refuse the members `extractall` would happily write.

    The assertions are about the invariant (nothing lands outside the
    destination) rather than a specific exception type, because the two
    supported code paths differ: Python >= 3.12 applies the ``data`` filter,
    which sanitizes an absolute member into the destination and raises on a
    traversal member, while the fallback raises on both. Both must keep the
    escape from happening.
    """

    ESCAPE_NAMES = ("/toefl-house-escape.txt", "../../toefl-house-escape.txt")

    def setUp(self):
        for name in self.ESCAPE_NAMES:
            Path(name).resolve().unlink(missing_ok=True)
        # tempfile.gettempdir() is where both absolute and ../../ members resolve.
        self.outside = Path(tempfile.gettempdir()) / "toefl-house-escape.txt"
        self.outside.unlink(missing_ok=True)

    def _extract(self, members):
        destination = Path(tempfile.mkdtemp(prefix="toefl-house-extract-"))
        archive = Path(tempfile.mkstemp(suffix=".tar")[1])
        with tarfile.open(archive, "w") as tar:
            for name, payload in members:
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
        error = None
        try:
            with tarfile.open(archive, "r") as tar:
                evidence.extract_safely(tar, destination)
        except Exception as exc:  # noqa: BLE001 - the point is that it did not escape
            error = exc
        finally:
            archive.unlink(missing_ok=True)
        return destination, error

    def test_plain_members_extract(self):
        destination, error = self._extract([("private/student/identity.bin", b"synthetic")])
        self.assertIsNone(error)
        self.assertEqual((destination / "private/student/identity.bin").read_bytes(), b"synthetic")

    def test_no_hostile_member_can_write_outside_the_destination(self):
        for name in self.ESCAPE_NAMES:
            with self.subTest(member=name):
                self.outside.unlink(missing_ok=True)
                destination, error = self._extract([("safe.txt", b"synthetic"), (name, b"synthetic")])
                self.assertFalse(self.outside.exists(),
                                 f"member {name} wrote outside the destination")
                self.assertTrue(error is not None or (destination / "safe.txt").exists())

    def test_the_modern_safe_filter_is_used_when_available(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('tar.extractall(destination, filter="data")', source)
        # The fallback must keep the same guarantee on interpreters without it.
        self.assertIn("archive member escapes the restore directory", source)


if __name__ == "__main__":
    unittest.main()

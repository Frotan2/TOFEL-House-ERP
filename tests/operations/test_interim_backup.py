# -*- coding: utf-8 -*-
"""Interim backup policy (owner directive section 2).

The point of these tests is that the backup must refuse to be misleading. A
backup on the same volume as the live data, a rotation that silently expires
everything, or an artifact reported as verified without a digest comparison
would each satisfy "a backup exists" while providing none of the protection the
requirement is actually about.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.operations.interim_backup import (  # noqa: E402
    LIMITATIONS,
    BackupPolicyError,
    RetentionPolicy,
    assert_different_volume,
    backup_manifest,
    classify_generation,
    restore_procedure,
    retention_plan,
    run_backup,
    verify_artifact,
    write_sidecar,
)


class VolumeSeparationTests(unittest.TestCase):

    def test_same_volume_is_refused_not_warned(self):
        """A same-volume copy provides none of the required protection."""
        with tempfile.TemporaryDirectory() as root:
            live = os.path.join(root, "live")
            backup = os.path.join(root, "backup")
            os.makedirs(live)
            os.makedirs(backup)
            with self.assertRaises(BackupPolicyError):
                assert_different_volume(live, backup)

    def test_a_genuinely_different_volume_is_accepted(self):
        # /proc and / are reliably distinct filesystems on the runner image.
        if not os.path.isdir("/proc"):
            self.skipTest("no separate /proc filesystem available")
        evidence = assert_different_volume("/proc", "/")
        self.assertTrue(evidence["different_volume"])
        self.assertNotEqual(evidence["active_st_dev"], evidence["backup_st_dev"])


class RotationTests(unittest.TestCase):

    def test_rotation_is_predictable_and_newest_first(self):
        names = [f"db-2026-09-{d:02d}-daily.sql.gz.enc" for d in range(1, 21)]
        plan = retention_plan(names, RetentionPolicy(daily=14, weekly=0, monthly=0))
        self.assertEqual(len(plan["keep"]), 14)
        self.assertEqual(len(plan["expire"]), 6)
        self.assertIn("db-2026-09-20-daily.sql.gz.enc", plan["keep"])
        self.assertIn("db-2026-09-01-daily.sql.gz.enc", plan["expire"])

    def test_generations_are_bucketed_independently(self):
        names = ["db-monthly-01.enc", "db-monthly-02.enc",
                 "db-weekly-01.enc", "db-daily-01.enc"]
        self.assertEqual(classify_generation("db-monthly-02.enc"), "monthly")
        self.assertEqual(classify_generation("db-weekly-01.enc"), "weekly")
        self.assertEqual(classify_generation("db-daily-01.enc"), "daily")
        plan = retention_plan(names, RetentionPolicy(1, 1, 1))
        self.assertEqual(len(plan["expire"]), 1)

    def test_a_bad_plan_reports_expiry_instead_of_deleting(self):
        """Retention never destroys backups as a side effect."""
        plan = retention_plan(["a-daily.enc"], RetentionPolicy(0, 0, 0))
        self.assertEqual(plan["keep"], [])
        self.assertEqual(plan["expire"], ["a-daily.enc"])

    def test_the_plan_is_deterministic(self):
        names = ["z-daily.enc", "a-daily.enc", "m-daily.enc"]
        self.assertEqual(retention_plan(names, RetentionPolicy(2, 0, 0)),
                         retention_plan(list(reversed(names)),
                                        RetentionPolicy(2, 0, 0)))


class IntegrityTests(unittest.TestCase):

    def test_a_matching_digest_verifies(self):
        with tempfile.TemporaryDirectory() as root:
            artifact = os.path.join(root, "backup.enc")
            with open(artifact, "wb") as handle:
                handle.write(b"cipher bytes")
            from tools.operations.interim_backup import digest_file
            verdict = verify_artifact(artifact, digest_file(artifact))
            self.assertTrue(verdict["verified"])

    def test_a_corrupted_artifact_does_not_verify(self):
        with tempfile.TemporaryDirectory() as root:
            artifact = os.path.join(root, "backup.enc")
            with open(artifact, "wb") as handle:
                handle.write(b"cipher bytes")
            verdict = verify_artifact(artifact, "0" * 64)
            self.assertFalse(verdict["verified"])
            self.assertNotEqual(verdict["observed_sha256"], verdict["expected_sha256"])

    def test_a_missing_artifact_is_not_reported_as_verified(self):
        verdict = verify_artifact("/nonexistent/backup.enc", "0" * 64)
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "missing")


class HonestyTests(unittest.TestCase):

    def test_the_limitations_travel_with_the_artifact(self):
        manifest = backup_manifest(
            artifacts=[], retention=RetentionPolicy(),
            volume_evidence={"different_volume": True}, restore_command="restore.sh")
        self.assertEqual(manifest["classification"],
                         "INTERIM_PRODUCTION_BACKUP_NOT_DISASTER_RECOVERY")
        joined = " ".join(manifest["limitations"])
        for risk in ("theft", "fire", "site loss", "ransomware"):
            self.assertIn(risk, joined)
        self.assertIn("NOT YET BUILT", joined)

    def test_source_states_the_limitations_too(self):
        text = (ROOT / "tools/operations/interim_backup.py").read_text()
        self.assertIn("interim production\nbackup", text.replace("**", ""))
        self.assertTrue(len(LIMITATIONS) >= 3)

    def test_the_restore_procedure_verifies_before_restoring(self):
        steps = restore_procedure()
        verify_at = next(i for i, s in enumerate(steps) if "sha256" in s)
        restore_at = next(i for i, s in enumerate(steps) if "Restore the database" in s)
        self.assertLess(verify_at, restore_at,
                        "verification must precede the restore, not follow it")
        self.assertTrue(any("never over the live one" in s for s in steps))


class ExecutedBackupRunTests(unittest.TestCase):
    """Actually run the backup path, including real encryption.

    A stubbed encryption call would prove nothing about whether the produced
    artifact can be decrypted, so these use the real openssl binary when the
    runner has one.
    """

    def _passphrase(self, root):
        path = os.path.join(root, "passphrase")
        with open(path, "w") as handle:
            handle.write("test-passphrase-not-a-secret\n")
        os.chmod(path, 0o600)
        return path

    def test_an_executed_backup_is_encrypted_digestible_and_leaves_no_plaintext(self):
        import shutil
        if shutil.which("openssl") is None:
            self.skipTest("openssl not available")
        with tempfile.TemporaryDirectory() as root:
            dest = os.path.join(root, "backups")
            passphrase = self._passphrase(root)
            run = run_backup(
                backup_root=dest, label="db-2026-09-19-daily",
                dump_command=["printf", "INSERT INTO t VALUES (1);\n"],
                passphrase_file=passphrase,
                volume_evidence={"different_volume": True, "injected": True})
            self.assertTrue(run.encrypted)
            self.assertTrue(os.path.isfile(run.cipher_path))
            self.assertFalse(os.path.isfile(os.path.join(dest, "db-2026-09-19-daily.plain")),
                             "plaintext must not survive the run")
            self.assertEqual(run.volume_evidence["injected"], True)
            with open(run.cipher_path, "rb") as handle:
                self.assertNotIn(b"INSERT INTO", handle.read(),
                                 "artifact is not actually encrypted")

    def test_the_encrypted_artifact_can_be_decrypted_back(self):
        import shutil
        import subprocess
        if shutil.which("openssl") is None:
            self.skipTest("openssl not available")
        with tempfile.TemporaryDirectory() as root:
            dest = os.path.join(root, "backups")
            passphrase = self._passphrase(root)
            payload = b"INSERT INTO `tabUser` VALUES ('Administrator');\n"
            run = run_backup(
                backup_root=dest, label="db-restore-check",
                dump_command=["printf", payload.decode()],
                passphrase_file=passphrase,
                volume_evidence={"different_volume": True, "injected": True})
            out = os.path.join(root, "restored.sql")
            subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
                            "-iter", "200000", "-in", run.cipher_path, "-out", out,
                            "-pass", f"file:{passphrase}"], check=True,
                           capture_output=True)
            with open(out, "rb") as handle:
                self.assertEqual(handle.read(), payload)

    def test_a_failing_dump_aborts_without_leaving_a_partial_artifact(self):
        with tempfile.TemporaryDirectory() as root:
            dest = os.path.join(root, "backups")
            os.makedirs(dest)
            with self.assertRaises(Exception):
                run_backup(
                    backup_root=dest, label="db-bad",
                    dump_command=["false"],
                    volume_evidence={"different_volume": True, "injected": True})
            leftovers = [p for p in os.listdir(dest)
                         if p.endswith(".enc") or p.endswith(".plain")]
            self.assertEqual(leftovers, [])

    def test_same_volume_is_refused_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as root:
            live = os.path.join(root, "live")
            dest = os.path.join(root, "backups")
            os.makedirs(live)
            with self.assertRaises(BackupPolicyError):
                run_backup(
                    backup_root=dest, label="db-samevol",
                    dump_command=["printf", "should-not-run\n"],
                    active_data_root=live)
            self.assertFalse(os.path.isdir(dest),
                             "destination must not be created after a volume refusal")

    def test_the_sidecar_carries_limitations_and_the_digest(self):
        import json
        import shutil
        if shutil.which("openssl") is None:
            self.skipTest("openssl not available")
        with tempfile.TemporaryDirectory() as root:
            dest = os.path.join(root, "backups")
            passphrase = self._passphrase(root)
            run = run_backup(
                backup_root=dest, label="db-sidecar",
                dump_command=["printf", "payload\n"],
                passphrase_file=passphrase,
                volume_evidence={"different_volume": True, "injected": True})
            sidecar = write_sidecar(run, RetentionPolicy(),
                                    restore_command="see restore_procedure()")
            payload = json.loads(Path(sidecar).read_text())
            self.assertEqual(payload["classification"],
                             "INTERIM_PRODUCTION_BACKUP_NOT_DISASTER_RECOVERY")
            self.assertEqual(payload["artifacts"][0]["sha256"], run.cipher_digest)
            self.assertTrue(payload["volume_evidence"]["different_volume"])
            joined = " ".join(payload["limitations"])
            self.assertIn("ransomware", joined)


class OperatorCliTests(unittest.TestCase):

    def test_print_restore_procedure_exits_zero(self):
        from tools.operations.interim_backup import main
        self.assertEqual(main(["--print-restore-procedure"]), 0)

    def test_a_run_without_dump_command_is_refused(self):
        from tools.operations.interim_backup import main
        with self.assertRaises(SystemExit):
            main(["--active-data-root", "/", "--backup-root", "/tmp",
                  "--label", "x"])


if __name__ == "__main__":
    unittest.main()

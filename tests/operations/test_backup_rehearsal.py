"""Backup-restore rehearsal harness contract.

The technical rehearsal (tools/operations/backup_rehearsal.py) exercises every
guard in interim_backup end-to-end using a synthetic dump command — no MariaDB
or frappe dependency. These regression tests pin that the rehearsal really
exercises the encrypt/decrypt round-trip, the tamper detection, the live-root
refusal, and that it refuses to invent RPO/RTO numbers or off-site claims on
the Owner's behalf.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))

from tools.operations import backup_rehearsal  # noqa: E402


class BackupRehearsalTests(unittest.TestCase):
    def test_rehearsal_exercises_every_guard_and_passes(self):
        with tempfile.TemporaryDirectory() as scratch:
            out = Path(scratch) / "report.json"
            with contextlib.redirect_stdout(io.StringIO()):
                rc = backup_rehearsal.main([
                    "--scratch", scratch, "--payload-bytes", "65536",
                    "--output", str(out),
                ])
            self.assertEqual(rc, 0)
            report = json.loads(out.read_text())
            self.assertEqual(report["status"], "pass")
            check_names = {c["name"] for c in report["checks"]}
            for required in (
                "synthetic-dump-encrypted-and-plain-removed",
                "sidecar-carries-limitations-and-both-digests",
                "restore-into-live-root-refused",
                "restore-verifies-then-decrypts-byte-identical",
                "restore-command-receives-the-plaintext-dump",
                "tampered-cipher-refused-before-decrypt",
            ):
                self.assertIn(required, check_names,
                              f"rehearsal missing guard check {required!r}")
            self.assertEqual(
                report["classification"],
                "INTERIM_PRODUCTION_BACKUP_NOT_DISASTER_RECOVERY")

    def test_rehearsal_round_trips_the_dump_byte_identically(self):
        with tempfile.TemporaryDirectory() as scratch:
            report = backup_rehearsal.run_rehearsal(scratch, payload_size=131072)
            self.assertEqual(report["status"], "pass")
            # Cipher must exist and plaintext must be absent.
            cipher = Path(report["cipher_path"])
            self.assertTrue(cipher.is_file())
            backup_dir = cipher.parent
            self.assertFalse((backup_dir / "db-daily.plain").exists())
            # The restored file must match the original plaintext by digest,
            # and the cipher digest must differ from the plaintext digest
            # (i.e. encryption was actually applied).
            self.assertNotEqual(report["plaintext_sha256"], report["cipher_sha256"])
            decrypted = Path(backup_dir.parent / "staging") / (cipher.name + ".restored")
            self.assertTrue(decrypted.is_file())
            # Round-tripped bytes must be byte-identical (header + filler).
            import hashlib
            loaded = (Path(report["scratch"]) / "loaded-into-fresh-db.sql").read_bytes()
            self.assertIn(b"CREATE TABLE", loaded)  # SQL marker present
            self.assertEqual(
                hashlib.sha256(loaded).hexdigest(), report["plaintext_sha256"])
            self.assertGreaterEqual(len(loaded), 131072)
            self.assertEqual(report["plaintext_bytes"], len(loaded))

    def test_rehearsal_does_not_invent_rpo_rto_or_offsite_claims(self):
        """The harness must not claim RPO/RTO or off-site coverage.

        Those are Owner policy decisions (B12/D14). Any code path that
        silently claims them is a regression, because the evidence package
        would overstate what has actually been built.
        """
        with tempfile.TemporaryDirectory() as scratch:
            report = backup_rehearsal.run_rehearsal(scratch, payload_size=4096)
            text = json.dumps(report)
            # No numeric RPO/RTO should be asserted; the report must flag
            # the owner-decision items explicitly rather than claim a value.
            for forbidden in ("\"rpo_minutes\"", "\"rto_minutes\"",
                              "\"off_site_replicated\": true",
                              "\"offsite_destination\": \"",  # must not have a destination value
                              "\"custodian_identities\": [",  # must not list identities
                              ):
                self.assertNotIn(forbidden, text,
                                 f"rehearsal must not fabricate {forbidden}")
            joined = " ".join(report["owner_decisions_required"]).lower()
            for keyword in ("rpo", "rto", "off-site", "custody"):
                self.assertIn(keyword, joined,
                              f"owner decision for {keyword!r} missing from report")

    def test_scratch_directory_is_isolated_from_repo(self):
        """The rehearsal must not write anywhere outside its scratch tree."""
        with tempfile.TemporaryDirectory() as scratch:
            before = set()
            for dirpath, _dirs, files in os.walk(ROOT / "tools/operations"):
                for f in files:
                    before.add(str(Path(dirpath) / f))
            backup_rehearsal.run_rehearsal(scratch, payload_size=4096)
            after = set()
            for dirpath, _dirs, files in os.walk(ROOT / "tools/operations"):
                for f in files:
                    after.add(str(Path(dirpath) / f))
            self.assertEqual(before, after,
                             "rehearsal created/removed files under tools/operations")


if __name__ == "__main__":
    unittest.main()

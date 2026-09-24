"""Tests for tools.operations.backup_policy: NOT_CONFIGURED defaults, audit
log append/read, magic-byte verifiers, idempotency helper."""
import gzip
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.operations.backup_policy import (  # noqa: E402
    NOT_CONFIGURED, default_policy, load_policy,
    append_audit, read_audit, existing_sidecar_matches,
    verify_artifact_header,
)


class PolicyStateTests(unittest.TestCase):
    def test_default_policy_every_field_is_not_configured(self):
        p = default_policy()
        for field, value in p.as_dict().items():
            self.assertEqual(value, NOT_CONFIGURED, f"{field} should be NOT_CONFIGURED")
        self.assertFalse(p.is_fully_configured())

    def test_policy_load_partial_keeps_unconfigured(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "policy.json"
            f.write_text(json.dumps({"rpo_hours": 24, "rto_hours": 8}))
            p = load_policy(f)
            self.assertEqual(p.rpo_hours, 24)
            self.assertEqual(p.rto_hours, 8)
            self.assertEqual(p.offsite_destination, NOT_CONFIGURED)
            self.assertFalse(p.is_fully_configured())

    def test_policy_load_fully_configured(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "policy.json"
            f.write_text(json.dumps({
                "rpo_hours": 24, "rto_hours": 8,
                "offsite_destination": "rsync://offsite.example/backups",
                "custodian_identities": ["alice", "bob"],
                "schedule": {"daily": "02:00"},
                "retention_overrides": {"daily": 7},
            }))
            p = load_policy(f)
            self.assertTrue(p.is_fully_configured())


class AuditLogTests(unittest.TestCase):
    def test_append_and_read_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            append_audit(d, {"action": "backup", "artifact": "a.enc"})
            append_audit(d, {"action": "restore", "artifact": "a.enc"})
            entries = read_audit(d)
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["action"], "backup")
            self.assertEqual(entries[1]["action"], "restore")
            for e in entries:
                self.assertIn("timestamp_utc", e)
                self.assertIn("hostname", e)
                self.assertIn("euid", e)


class MagicByteTests(unittest.TestCase):
    def test_gzip_sql_dump_is_recognised(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "dump.sql.gz"
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
                gz.write(b"-- MariaDB dump 10.19\nCREATE TABLE x (id INT);\nINSERT INTO x VALUES (1);\n")
            p.write_bytes(buf.getvalue())
            out = verify_artifact_header(p, "database")
            self.assertTrue(out["verified_by_magic"], out)
            self.assertEqual(out["format"], "gzip")

    def test_plain_sql_dump_is_recognised(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "dump.sql"
            p.write_text("-- MySQL dump\nCREATE TABLE y (id INT);\n")
            out = verify_artifact_header(p, "database")
            self.assertTrue(out["verified_by_magic"], out)
            self.assertEqual(out["format"], "plain")

    def test_tar_archive_is_recognised_by_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/"hi.txt").write_text("hello")
            tar = root/"a.tar"
            with tarfile.open(tar, "w") as tf:
                tf.add(root/"hi.txt", arcname="hi.txt")
            out = verify_artifact_header(tar, "files")
            self.assertTrue(out["verified_by_magic"], out)
            self.assertEqual(out["format"], "tar")

    def test_truncated_garbage_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "junk"
            p.write_bytes(b"\x00" * 512 + b"garbage")
            self.assertFalse(verify_artifact_header(p, "database")["verified_by_magic"])
            self.assertFalse(verify_artifact_header(p, "files")["verified_by_magic"])


class IdempotencyTests(unittest.TestCase):
    def test_existing_sidecar_matches_digest(self):
        with tempfile.TemporaryDirectory() as d:
            cipher = Path(d) / "a.enc"
            cipher.write_bytes(b"hello")
            sidecar = cipher.with_suffix(".enc.manifest.json")
            import hashlib
            digest = hashlib.sha256(b"hello").hexdigest()
            sidecar.write_text(json.dumps({"artifacts":[{"sha256": digest}]}))
            self.assertTrue(existing_sidecar_matches(cipher, digest))
            self.assertFalse(existing_sidecar_matches(cipher, "0"*64))
            # missing sidecar -> False
            sidecar.unlink()
            self.assertFalse(existing_sidecar_matches(cipher, digest))


if __name__ == "__main__":
    unittest.main()

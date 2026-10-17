"""Partial native publication (F7, windows-backup-readiness README, 2026-10-17).

Synthetic files only. The GPG packet check is replaced by a no-op here because `gpg` is not
installed in the sandbox; the real packet check stays covered by its own suite and remains
UNVERIFIED on a real gpg binary. Everything else in `_verify_and_publish` runs for real:
name checks, the pre-existence guard, the site-config key match, and the no-overwrite link.

`test_partial_publish_leaves_orphan_until_owner_decides_f7` pins CURRENT behaviour. It is not
an endorsement: when the owner decides how partial sets are handled (F7), this test must be
updated in the same change as the fix.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "product") not in sys.path:
    sys.path.insert(0, str(ROOT / "product"))


def load_backup():
    spec = importlib.util.spec_from_file_location(
        "product_backup_publish_under_test", ROOT / "product" / "backup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BACKUP = load_backup()
SET = "20261017_090000-toeflhouse_localhost"
KEY = "synthetic-key-0001"


class PartialPublishTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.staging = root / "staging"
        self.destination = root / "backups"
        self.staging.mkdir()
        self.destination.mkdir()
        self.names = {
            "database": f"{SET}{BACKUP.BACKUP_SUFFIXES['database']}",
            "public_files": f"{SET}{BACKUP.BACKUP_SUFFIXES['public_files']}",
            "private_files": f"{SET}{BACKUP.BACKUP_SUFFIXES['private_files']}",
            "site_config": f"{SET}{BACKUP.CONFIG_MARKER}.json",
        }
        for role, name in self.names.items():
            body = (json.dumps({"backup_encryption_key": KEY}) if role == "site_config"
                    else f"synthetic {role}")
            (self.staging / name).write_text(body, encoding="utf-8")
        self.result = types.SimpleNamespace(
            backup_path_db=str(self.staging / self.names["database"]),
            backup_path_files=str(self.staging / self.names["public_files"]),
            backup_path_private_files=str(self.staging / self.names["private_files"]),
            backup_path_conf=str(self.staging / self.names["site_config"]),
        )
        self.original_publish = BACKUP._publish_without_overwrite

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, publish_side_effect):
        calls = []

        def publish(source, destination):
            calls.append(destination.name)
            publish_side_effect(len(calls), source, destination, self.original_publish)

        # Synthetic stand-in for the real gpg packet check (gpg is not installed here).
        with patch.object(BACKUP, "_assert_gpg_encrypted", lambda *a, **k: None), \
                patch.object(BACKUP, "_publish_without_overwrite", side_effect=publish):
            return BACKUP._verify_and_publish(self.result, self.staging, self.destination, KEY)

    def _destination_names(self):
        return sorted(p.name for p in self.destination.iterdir())

    def test_partial_publish_leaves_orphan_until_owner_decides_f7(self):
        def fail_second(index, source, destination, original):
            if index == 2:
                raise BACKUP.BackupInputError("synthetic copy failure on second artifact")
            original(source, destination)

        with self.assertRaises(BACKUP.BackupInputError):
            self._run(fail_second)

        # Current behaviour: the first artifact stays, with no sidecar and no rollback.
        self.assertEqual(self._destination_names(), [self.names["database"]])
        # The plaintext key sidecar is published last, so it was never written.
        self.assertNotIn(self.names["site_config"], self._destination_names())

    def test_failure_on_first_copy_leaves_destination_empty(self):
        def fail_first(index, source, destination, original):
            raise BACKUP.BackupInputError("synthetic copy failure on first artifact")

        with self.assertRaises(BACKUP.BackupInputError):
            self._run(fail_first)
        self.assertEqual(self._destination_names(), [])

    def test_preexisting_destination_name_refuses_before_any_write(self):
        (self.destination / self.names["private_files"]).write_text("older set", encoding="utf-8")

        def should_not_run(index, source, destination, original):
            raise AssertionError("publish must not start when any destination name exists")

        with self.assertRaises(BACKUP.BackupInputError) as caught:
            self._run(should_not_run)
        self.assertIn("pre-existing", str(caught.exception))
        self.assertEqual(self._destination_names(), [self.names["private_files"]])
        self.assertEqual((self.destination / self.names["private_files"]).read_text(encoding="utf-8"),
                         "older set")


if __name__ == "__main__":
    unittest.main()

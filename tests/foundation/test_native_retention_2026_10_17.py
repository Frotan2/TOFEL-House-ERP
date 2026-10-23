"""Native backup retention (F1 with owner decision D17) and F7 interaction.

Synthetic files in temporary directories only. Nothing here touches a real backup folder,
site, key, or Owner policy. The Owner policy is passed in explicitly.
"""
from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "product") not in sys.path:
    sys.path.insert(0, str(ROOT / "product"))


def load_backup():
    spec = importlib.util.spec_from_file_location(
        "product_backup_retention_under_test", ROOT / "product" / "backup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BACKUP = load_backup()
SITE = "toeflhouse_localhost"
DELETE = BACKUP.RETENTION_DELETE_BEYOND_KEEP
PRESERVE = BACKUP.RETENTION_PRESERVE_ALL


def set_name(stamp):
    return f"{stamp}-{SITE}"


def make_set(folder: Path, stamp: str, *, sidecar=True):
    name = set_name(stamp)
    (folder / f"{name}{BACKUP.BACKUP_SUFFIXES['database']}").write_text("synthetic db")
    (folder / f"{name}{BACKUP.BACKUP_SUFFIXES['public_files']}").write_text("synthetic files")
    (folder / f"{name}{BACKUP.BACKUP_SUFFIXES['private_files']}").write_text("synthetic private")
    if sidecar:
        (folder / f"{name}{BACKUP.CONFIG_MARKER}.json").write_text('{"backup_encryption_key": "synthetic"}')
    return name


def names_in(folder: Path):
    return sorted(p.name for p in folder.iterdir())


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name) / "backups"
        self.folder.mkdir()
        self.stamps = ["20261011_010000", "20261012_010000", "20261013_010000",
                       "20261014_010000", "20261015_010000"]
        self.sets = [make_set(self.folder, s) for s in self.stamps]  # oldest first

    def tearDown(self):
        self._tmp.cleanup()

    def _count_remaining_sets(self):
        return {name for name in self.sets if (self.folder / f"{name}{BACKUP.CONFIG_MARKER}.json").exists()}

    def test_keeps_newest_complete_sets_and_removes_older_ones(self):
        newest = self.sets[-1]
        result = BACKUP.rotate_native_sets(self.folder, keep_count=3, protect_set=newest)
        self.assertEqual(result["kept"], [self.sets[4], self.sets[3], self.sets[2]])
        self.assertEqual(sorted(result["removed"]), sorted([self.sets[0], self.sets[1]]))
        self.assertEqual(self._count_remaining_sets(), {self.sets[2], self.sets[3], self.sets[4]})
        for name in (self.sets[0], self.sets[1]):
            self.assertFalse(any(p.name.startswith(name) for p in self.folder.iterdir()), name)

    def test_site_config_sidecar_is_removed_before_encrypted_artifacts(self):
        removal_order = []
        original_unlink = Path.unlink

        def recording_unlink(path, *args, **kwargs):
            removal_order.append(path.name)
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", recording_unlink):
            BACKUP.rotate_native_sets(self.folder, keep_count=4, protect_set=self.sets[-1])
        first_set = [n for n in removal_order if n.startswith(self.sets[0])]
        self.assertEqual(len(first_set), 4)
        self.assertIn(BACKUP.CONFIG_MARKER, first_set[0])
        self.assertTrue(all(BACKUP.CONFIG_MARKER not in n for n in first_set[1:]))

    def test_incomplete_orphan_is_preserved_and_not_counted(self):
        orphan = set_name("20261001_010000")
        (self.folder / f"{orphan}{BACKUP.BACKUP_SUFFIXES['database']}").write_text("orphan db")
        result = BACKUP.rotate_native_sets(self.folder, keep_count=2, protect_set=self.sets[-1])
        self.assertEqual(result["kept"], [self.sets[4], self.sets[3]])
        self.assertTrue((self.folder / f"{orphan}{BACKUP.BACKUP_SUFFIXES['database']}").exists())
        self.assertNotIn(orphan, result["removed"])

    @unittest.skipUnless(os.name == "posix",
                         "symlink policy is exercised on the Linux product filesystem")
    def test_symlinked_artifact_makes_set_incomplete_and_is_never_followed(self):
        outside = Path(self._tmp.name) / "outside-secret.txt"
        outside.write_text("must survive")
        link = self.folder / f"{self.sets[0]}{BACKUP.BACKUP_SUFFIXES['private_files']}"
        link.unlink()
        link.symlink_to(outside)
        result = BACKUP.rotate_native_sets(self.folder, keep_count=2, protect_set=self.sets[-1])
        self.assertNotIn(self.sets[0], result["removed"])
        self.assertTrue(link.is_symlink())
        self.assertEqual(outside.read_text(), "must survive")

    def test_non_timestamped_complete_set_is_never_deleted(self):
        manual = "manual-snapshot-toeflhouse_localhost"
        for suffix in BACKUP.BACKUP_SUFFIXES.values():
            (self.folder / f"{manual}{suffix}").write_text("manual")
        (self.folder / f"{manual}{BACKUP.CONFIG_MARKER}.json").write_text("{}")
        BACKUP.rotate_native_sets(self.folder, keep_count=2, protect_set=self.sets[-1])
        self.assertTrue((self.folder / f"{manual}{BACKUP.CONFIG_MARKER}.json").exists())

    def test_protected_current_set_outside_keep_refuses_before_any_deletion(self):
        before = names_in(self.folder)
        with self.assertRaises(BACKUP.BackupInputError) as caught:
            BACKUP.rotate_native_sets(self.folder, keep_count=2, protect_set=self.sets[0])
        self.assertEqual(caught.exception.safe_code, "native-retention-would-drop-current")
        self.assertEqual(names_in(self.folder), before)

    def test_keep_count_must_be_a_configured_integer_of_at_least_two(self):
        before = names_in(self.folder)
        for bad in (None, 0, 1, True, False, "3", 2.0, -5):
            with self.subTest(keep=bad), self.assertRaises(BACKUP.BackupInputError) as caught:
                BACKUP.rotate_native_sets(self.folder, keep_count=bad, protect_set=self.sets[-1])
            self.assertEqual(caught.exception.safe_code, "native-retention-keep-count-invalid")
            self.assertEqual(names_in(self.folder), before)

    def test_interrupted_deletion_leaves_an_incomplete_set_that_later_runs_preserve(self):
        real_unlink = Path.unlink
        calls = {"count": 0}

        def failing_unlink(path, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("synthetic interruption")
            return real_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", failing_unlink):
            with self.assertRaises(BACKUP.BackupInputError) as caught:
                BACKUP.rotate_native_sets(self.folder, keep_count=4, protect_set=self.sets[-1])
        self.assertEqual(caught.exception.safe_code, "native-retention-interrupted")
        # The sidecar of the oldest set went first, so that set is now incomplete.
        self.assertFalse((self.folder / f"{self.sets[0]}{BACKUP.CONFIG_MARKER}.json").exists())
        # A later run neither counts nor deletes that incomplete set.
        result = BACKUP.rotate_native_sets(self.folder, keep_count=4, protect_set=self.sets[-1])
        self.assertNotIn(self.sets[0], result["removed"])
        self.assertTrue((self.folder / f"{self.sets[0]}{BACKUP.BACKUP_SUFFIXES['database']}").exists())


class PolicyApplicationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name) / "backups"
        self.folder.mkdir()
        self.sets = [make_set(self.folder, s) for s in
                     ["20261011_010000", "20261012_010000", "20261013_010000"]]

    def tearDown(self):
        self._tmp.cleanup()

    def _all_present(self):
        return all((self.folder / f"{n}{BACKUP.CONFIG_MARKER}.json").exists() for n in self.sets)

    def test_unconfigured_or_unrecognised_policy_deletes_nothing(self):
        cases = [None, {}, {"configured": False, "status": "NOT CONFIGURED"},
                 {"configured": True, "retention_behavior": "", "retention_versions": 2},
                 {"configured": True, "retention_behavior": "Delete everything", "retention_versions": 2},
                 {"configured": "yes", "retention_behavior": DELETE, "retention_versions": 2}]
        for policy in cases:
            with self.subTest(policy=policy):
                status = BACKUP._apply_native_retention(self.folder, self.sets[-1], policy=policy)
                self.assertIn("no native sets were deleted", status)
                self.assertTrue(self._all_present())

    def test_preserve_all_deletes_nothing(self):
        status = BACKUP._apply_native_retention(
            self.folder, self.sets[-1],
            policy={"configured": True, "retention_behavior": PRESERVE, "retention_versions": 2})
        self.assertEqual(status, "preserve all valid native sets")
        self.assertTrue(self._all_present())

    def test_delete_mode_uses_the_owner_keep_count(self):
        status = BACKUP._apply_native_retention(
            self.folder, self.sets[-1],
            policy={"configured": True, "retention_behavior": DELETE, "retention_versions": 2})
        self.assertIn("removed 1", status)
        self.assertFalse((self.folder / f"{self.sets[0]}{BACKUP.CONFIG_MARKER}.json").exists())
        self.assertTrue((self.folder / f"{self.sets[1]}{BACKUP.CONFIG_MARKER}.json").exists())

    def test_owner_policy_strings_match_owner_configuration(self):
        source = (ROOT / "apps/toefl_house/toefl_house/operations/owner_configuration.py").read_text(encoding="utf-8")
        preserve = re.search(r'RETENTION_PRESERVE_ALL = "([^"]+)"', source).group(1)
        delete = re.search(r'RETENTION_DELETE_BEYOND_KEEP = "([^"]+)"', source).group(1)
        self.assertEqual(BACKUP.RETENTION_PRESERVE_ALL, preserve)
        self.assertEqual(BACKUP.RETENTION_DELETE_BEYOND_KEEP, delete)
        minimum = int(re.search(r"MIN_BACKUP_VERSIONS = (\d+)", source).group(1))
        self.assertEqual(BACKUP.MIN_RETAINED_SETS, minimum)


class WiringTests(unittest.TestCase):
    def test_retention_runs_after_verified_publish_and_before_frappe_teardown(self):
        source = (ROOT / "product/backup.py").read_text(encoding="utf-8")
        publish_at = source.index("published_set = _verify_and_publish(")
        retention_at = source.index("retention_status = _apply_native_retention(destination_dir, published_set)")
        teardown_at = source.index("frappe.destroy()")
        self.assertLess(publish_at, retention_at)
        self.assertLess(retention_at, teardown_at)

    def test_main_reports_retention_status_without_changing_the_success_message(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(BACKUP, "_native_backup", return_value="kept 2 complete set(s); removed 1 older complete set(s)"):
            status = BACKUP.main([], stdout, stderr)
        self.assertEqual(status, 0)
        self.assertIn("GPG encryption verified", stdout.getvalue())
        self.assertIn("Native retention: kept 2 complete set(s)", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

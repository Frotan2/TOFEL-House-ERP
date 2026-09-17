"""Static and behavioural contract for versioned rollback (P5).

The isolated upgrade experiment proved a Frappe patch upgrade moves a site forward
while the other applications stay pinned, and recorded its own scope as "not
rollback". This is the other direction, and it is held to a higher standard than
"the command exited zero":

* the version identity has to be reproduced from the checked-out revision, because
  ``bench version`` on a development checkout reports a string plus ``HEAD`` that
  does not distinguish adjacent commits;
* the artifact a rollback deploys has to be byte-identical to the one registered
  when it was built, and an artifact that was never registered cannot pass;
* state created before the upgrade has to survive with an unchanged ``creation``
  timestamp, since a row that was deleted and re-created matches on content while
  differing on identity;
* the rollback plan is composed from native primitives and says so, because Frappe
  has no rollback command and its migrations are forward-only;
* backup artifacts are located by role with globs that allow the ``-enc`` suffix
  Frappe appends when System Settings encrypts backups.

Boundary with the existing coverage: ``runtime_upgrade.py`` is the forward
direction and stays as it is. Nothing here upgrades a release gate; the PASS comes
from the hosted operational-boundary run, never from this file.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

import operational_rollback as rollback  # noqa: E402

OLD = "33bf510b17afcaaa857ed38b921d8e9e50dcd232"
NEW = "988e54f3c4c291e2077a83809663f123731abe76"


class VersionIdentity(unittest.TestCase):
    def test_the_revision_is_what_makes_an_identity(self):
        identity = rollback.version_identity(OLD, "frappe 16.33.0 HEAD", ["erpnext", "frappe"])
        self.assertEqual(identity["revision"], OLD)
        self.assertTrue(identity["recorded"])
        self.assertEqual(identity["installed_apps"], ["erpnext", "frappe"])

    def test_an_empty_revision_is_not_a_recorded_identity(self):
        self.assertFalse(rollback.version_identity("")["recorded"])
        self.assertFalse(rollback.version_identity(None)["recorded"])

    def test_the_bench_version_string_is_corroboration_not_the_discriminator(self):
        # Two different commits of the same release report the same string.
        a = rollback.version_identity(OLD, "frappe 16.33.1 HEAD")
        b = rollback.version_identity(NEW, "frappe 16.33.1 HEAD")
        self.assertEqual(a["bench_version"], b["bench_version"])
        self.assertNotEqual(a["revision"], b["revision"])


class RollbackVerdict(unittest.TestCase):
    def test_matching_version_and_digest_is_proven(self):
        verdict = rollback.rollback_verdict("frappe 16.33.1 HEAD", "frappe 16.33.1 HEAD",
                                            "abc123", "abc123")
        self.assertEqual(verdict["verdict"], "ROLLBACK RESTORED THE PRIOR VERSIONED ARTIFACT")
        self.assertTrue(verdict["version_restored"])
        self.assertTrue(verdict["artifact_is_the_same_bytes"])

    def test_a_version_mismatch_fails_closed(self):
        verdict = rollback.rollback_verdict("frappe 16.33.1 HEAD", "frappe 16.34.0 HEAD",
                                            "abc123", "abc123")
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertEqual(verdict["reason"], "version mismatch")

    def test_a_digest_mismatch_fails_closed(self):
        verdict = rollback.rollback_verdict("frappe 16.33.1 HEAD", "frappe 16.33.1 HEAD",
                                            "abc123", "def456")
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertEqual(verdict["reason"], "artifact digest mismatch")

    def test_empty_observations_fail_closed(self):
        self.assertEqual(rollback.rollback_verdict("", "", "", "")["verdict"], "NOT PROVEN")
        self.assertEqual(rollback.rollback_verdict("v1", "v1", "", "")["verdict"], "NOT PROVEN")

    def test_the_real_revision_pair_is_distinguished(self):
        self.assertEqual(rollback.rollback_verdict(OLD, OLD, "d", "d")["verdict"],
                         "ROLLBACK RESTORED THE PRIOR VERSIONED ARTIFACT")
        self.assertEqual(rollback.rollback_verdict(OLD, NEW, "d", "d")["verdict"], "NOT PROVEN")


class ArtifactRegistry(unittest.TestCase):
    def test_an_entry_is_registered_only_with_a_digest(self):
        self.assertTrue(rollback.artifact_entry("database", "abc", 10, "sql.gz")["registered"])
        self.assertFalse(rollback.artifact_entry("database", "", 10, "sql.gz")["registered"])

    def test_identical_digests_match(self):
        built = {"database": rollback.artifact_entry("database", "abc", 10, "sql.gz")}
        deployed = {"database": rollback.artifact_entry("database", "abc", 10, "sql.gz")}
        verdict = rollback.artifacts_match(built, deployed)
        self.assertEqual(verdict["verdict"], "ARTIFACTS ARE THE SAME BYTES")
        self.assertTrue(verdict["all_byte_identical"])

    def test_a_substituted_artifact_is_caught(self):
        built = {"database": rollback.artifact_entry("database", "abc", 10, "sql.gz")}
        deployed = {"database": rollback.artifact_entry("database", "def", 10, "sql.gz")}
        verdict = rollback.artifacts_match(built, deployed)
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertEqual(verdict["mismatched"], ["database"])

    def test_an_unregistered_artifact_cannot_pass(self):
        verdict = rollback.artifacts_match({}, {"database": {"sha256": "abc"}})
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertTrue(verdict["per_artifact"]["database"]["missing"])

    def test_an_empty_registry_is_not_a_pass(self):
        self.assertEqual(rollback.artifacts_match({}, {})["verdict"], "NOT PROVEN")

    def test_the_registry_digest_is_stable_and_order_independent(self):
        entries = {"b": {"sha256": "2"}, "a": {"sha256": "1"}}
        reordered = {"a": {"sha256": "1"}, "b": {"sha256": "2"}}
        self.assertEqual(rollback.registry_digest(entries),
                         rollback.registry_digest(reordered))
        self.assertNotEqual(rollback.registry_digest(entries),
                            rollback.registry_digest({"a": {"sha256": "9"}}))


class DataPreservationVerdict(unittest.TestCase):
    def before(self):
        return {"ToDo-1": {"description": "synthetic pre-upgrade marker",
                           "creation": "2026-09-17 08:00:00.000000"}}

    def test_unchanged_content_and_identity_is_preserved(self):
        verdict = rollback.data_preservation_verdict(self.before(), self.before())
        self.assertEqual(verdict["verdict"], "STATE PRESERVED")
        self.assertTrue(verdict["preserved"])
        self.assertEqual(verdict["records_compared"], 1)

    def test_a_missing_record_fails_closed(self):
        verdict = rollback.data_preservation_verdict(self.before(), {})
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertEqual(verdict["missing_after_rollback"], ["ToDo-1"])
        self.assertIn("missing", verdict["reason"])

    def test_changed_content_fails_closed(self):
        after = {"ToDo-1": {"description": "tampered", "creation": "2026-09-17 08:00:00.000000"}}
        verdict = rollback.data_preservation_verdict(self.before(), after)
        self.assertEqual(verdict["content_changed"], ["ToDo-1"])
        self.assertEqual(verdict["verdict"], "NOT PROVEN")

    def test_a_recreated_row_is_caught_by_its_creation_timestamp(self):
        # Content equal, identity different: exactly what a delete-and-reinsert looks like.
        after = {"ToDo-1": {"description": "synthetic pre-upgrade marker",
                            "creation": "2026-09-17 09:30:00.000000"}}
        verdict = rollback.data_preservation_verdict(self.before(), after)
        self.assertEqual(verdict["creation_timestamp_changed"], ["ToDo-1"])
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertIn("recreated rather than preserved", verdict["reason"])

    def test_comparing_nothing_is_not_a_pass(self):
        self.assertEqual(rollback.data_preservation_verdict({}, {})["verdict"], "NOT PROVEN")


class RollbackPlan(unittest.TestCase):
    def setUp(self):
        self.plan = rollback.rollback_steps(
            site="rollback.localhost", backup_database="/backups/db.sql.gz",
            backup_public_files="/backups/files.tar",
            backup_private_files="/backups/private.tar",
            from_revision=NEW, to_revision=OLD, app_dir="/bench/apps/frappe",
            remote="https://github.com/frappe/frappe")

    def test_it_does_not_claim_a_native_rollback_command(self):
        self.assertFalse(self.plan["native_rollback_command_available"])
        self.assertIn("bench restore", self.plan["composed_from"])

    def test_the_source_goes_back_before_the_data_is_restored(self):
        def order_of(needle):
            return next(step["order"] for step in self.plan["steps"]
                        if needle in " ".join(step["command"]))

        self.assertEqual(order_of("checkout"), 2)
        self.assertEqual(order_of("restore"), 5)
        self.assertLess(order_of("checkout"), order_of("restore"),
                        "restoring data under newer code would leave schema and code apart")
        self.assertLess(order_of("setup requirements"), order_of("restore"),
                        "the dependency set has to match the code before data is restored")
        self.assertEqual(len(self.plan["steps"]), 6)
        self.assertEqual([step["order"] for step in self.plan["steps"]], [1, 2, 3, 4, 5, 6])

    def test_the_revision_is_confirmed_not_assumed(self):
        commands = [" ".join(step["command"]) for step in self.plan["steps"]]
        self.assertTrue(any("rev-parse HEAD" in command for command in commands))

    def test_dependencies_are_reinstalled_to_undo_the_upgrade(self):
        commands = [" ".join(step["command"]) for step in self.plan["steps"]]
        self.assertTrue(any("setup requirements" in command for command in commands))

    def test_the_file_artifacts_travel_with_the_database(self):
        restore = next(step["command"] for step in self.plan["steps"]
                       if "restore" in step["command"])
        self.assertIn("--with-public-files", restore)
        self.assertIn("--with-private-files", restore)
        self.assertIn("/backups/db.sql.gz", restore)

    def test_a_database_only_rollback_omits_the_file_flags(self):
        plan = rollback.rollback_steps(
            site="s", backup_database="/b/db.sql.gz", from_revision=NEW, to_revision=OLD,
            app_dir="/a", remote="r")
        restore = next(step["command"] for step in plan["steps"] if "restore" in step["command"])
        self.assertNotIn("--with-public-files", restore)
        self.assertNotIn("--with-private-files", restore)

    def test_the_plan_is_serialisable_so_it_can_be_recorded_as_evidence(self):
        self.assertEqual(json.loads(json.dumps(self.plan))["to_revision"], OLD)


class BackupArtifactDiscovery(unittest.TestCase):
    """Frappe appends ``-enc`` to every artifact name when backups are encrypted."""

    def write(self, directory, names):
        for name in names:
            (directory / name).write_bytes(b"payload-" + name.encode())
        return directory

    def test_plain_backup_names_are_found_by_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self.write(Path(tmp), [
                "20260917_080000-rollback_localhost-database.sql.gz",
                "20260917_080000-rollback_localhost-files.tar",
                "20260917_080000-rollback_localhost-private-files.tar",
                "20260917_080000-rollback_localhost-site_config_backup.json"])
            found = rollback.find_backup_artifacts(directory)
            self.assertEqual(sorted(found), ["database", "private_files", "public_files",
                                             "site_config"])
            self.assertIn("-database.sql.gz", found["database"]["name"])
            self.assertTrue(found["database"]["sha256"])
            self.assertEqual(found["database"]["bytes"],
                             len(b"payload-20260917_080000-rollback_localhost-database.sql.gz"))

    def test_encrypted_backup_names_are_also_found(self):
        # A glob written for "-database.sql.gz" alone misses every encrypted backup.
        with tempfile.TemporaryDirectory() as tmp:
            directory = self.write(Path(tmp), [
                "20260917_080000-rollback_localhost-database-enc.sql.gz",
                "20260917_080000-rollback_localhost-files-enc.tar",
                "20260917_080000-rollback_localhost-private-files-enc.tar"])
            found = rollback.find_backup_artifacts(directory)
            self.assertEqual(found["database"]["name"],
                             "20260917_080000-rollback_localhost-database-enc.sql.gz")
            self.assertIn("-enc", found["private_files"]["name"])

    def test_private_and_public_file_archives_are_not_confused(self):
        # ``*-files.tar`` also matches ``-private-files.tar``, so they must be split.
        with tempfile.TemporaryDirectory() as tmp:
            directory = self.write(Path(tmp), [
                "20260917_080000-s-files.tar",
                "20260917_080000-s-private-files.tar"])
            found = rollback.find_backup_artifacts(directory)
            self.assertNotIn("private", found["public_files"]["name"])
            self.assertIn("private", found["private_files"]["name"])
            self.assertNotEqual(found["public_files"]["sha256"],
                                found["private_files"]["sha256"])

    def test_selection_follows_mtime_not_the_filename(self):
        # Frappe names backups with a timestamp, so sorting by name usually agrees
        # with sorting by mtime - which would hide a wrong implementation. Touching
        # the earlier-named file separates the two, and it must then be selected.
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            earlier_named = directory / "20260101_000000-s-database.sql.gz"
            later_named = directory / "20260917_080000-s-database.sql.gz"
            earlier_named.write_bytes(b"old")
            later_named.write_bytes(b"new")
            earlier_named.touch()
            found = rollback.find_backup_artifacts(directory)
            self.assertEqual(found["database"]["name"], earlier_named.name)
            self.assertEqual(len(found["database"]["candidates"]), 2)

    def test_an_empty_directory_yields_no_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(rollback.find_backup_artifacts(Path(tmp)), {})

    def test_digests_are_real_sha256_over_the_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x-database.sql.gz"
            path.write_bytes(b"known")
            self.assertEqual(rollback.sha256_file(path), rollback.sha256_file(path))
            import hashlib
            self.assertEqual(rollback.sha256_file(path),
                             hashlib.sha256(b"known").hexdigest())


if __name__ == "__main__":
    unittest.main()

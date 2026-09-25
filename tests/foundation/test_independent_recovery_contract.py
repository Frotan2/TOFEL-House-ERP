"""Static and guard contract for independent-system recovery (P3).

Same-host restore is not independent recovery, and the release gates were BLOCKED
precisely because every prior restore ran on one machine against one live
database. These guards keep the two halves honest:

* the source must really destroy its own site through the native command, after
  recording that the state was fully present;
* the target must refuse to report success unless the host identity it observes
  differs from the source's, so a same-machine run cannot be relabelled;
* the backup payload must be an explicit allowlist, because ``bench backup``
  writes a ``*-site_config.json`` holding the database password and the site
  encryption key next to the dumps;
* the encrypted-field limitation must be asserted rather than hidden;
* usability must be proven through a live HTTP stack, not by reading files back.

They cannot execute the probes (that needs two disposable Docker-capable hosted
runners). The PASS comes from the hosted run pair, never from this file.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools"))

import runtime_independent_data as data  # noqa: E402
import runtime_independent_target as target  # noqa: E402
from session_branch import ACTIVE_BRANCH, ACTIVE_REF  # noqa: E402
from branch_boundary import mismatch  # noqa: E402
from bench_bootstrap import (Probe, dmi_product_uuid,  # noqa: E402
                               machine_identity)

SOURCE = (ROOT / "tools/foundation/runtime_independent_source.py").read_text(encoding="utf-8")
TARGET = (ROOT / "tools/foundation/runtime_independent_target.py").read_text(encoding="utf-8")
DATA = (ROOT / "tools/foundation/runtime_independent_data.py").read_text(encoding="utf-8")
USABILITY = (ROOT / "tools/foundation/runtime_independent_usability.py").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "tools/foundation/bench_bootstrap.py").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/foundation-independent-recovery.yml").read_text(encoding="utf-8")
PROBES = {"source": SOURCE, "target": TARGET, "data": DATA, "usability": USABILITY,
          "bootstrap": BOOTSTRAP}

MINIMAL_ENV = {"PATH": "/usr/bin:/bin"}


def run_guarded(script, *args, env=None):
    return subprocess.run([sys.executable, str(ROOT / "tools/foundation" / script), *args],
                          capture_output=True, text=True, cwd=str(ROOT),
                          env=env or MINIMAL_ENV)


class ContainmentTests(unittest.TestCase):
    """Executed: every entry point must fail closed off a hosted runner."""

    def test_source_probe_refuses_to_run_outside_a_hosted_runner(self):
        completed = run_guarded("runtime_independent_source.py")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("ephemeral Actions runner", completed.stderr + completed.stdout)

    def test_target_probe_refuses_to_run_outside_a_hosted_runner(self):
        completed = run_guarded("runtime_independent_target.py")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("ephemeral Actions runner", completed.stderr + completed.stdout)

    def test_data_script_refuses_to_run_outside_a_hosted_runner(self):
        for args in (("create", "source.localhost"), ("verify", "recovered.localhost")):
            completed = run_guarded("runtime_independent_data.py", *args)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Disposable hosted independent-recovery sites only",
                          completed.stderr + completed.stdout)

    def test_data_script_refuses_any_other_site_even_on_a_runner(self):
        """Guarded on the (action, site) pair, not just on the runner."""
        hosted = dict(MINIMAL_ENV, GITHUB_ACTIONS="true")
        for args in (("create", "recovered.localhost"), ("verify", "source.localhost"),
                     ("create", "foundation.localhost"), ("drop", "source.localhost"),
                     ("verify", "")):
            completed = run_guarded("runtime_independent_data.py", *args, env=hosted)
            self.assertNotEqual(completed.returncode, 0, args)
            self.assertIn("Disposable hosted independent-recovery sites only",
                          completed.stderr + completed.stdout)

    def test_usability_script_refuses_to_run_outside_a_hosted_runner(self):
        completed = run_guarded("runtime_independent_usability.py", "recovered.localhost")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Disposable hosted independent-recovery target site only",
                      completed.stderr + completed.stdout)

    def test_data_script_guards_before_importing_the_application(self):
        """The guard must run before ``import frappe``, not after side effects."""
        self.assertLess(DATA.index('raise SystemExit("Disposable hosted'),
                        DATA.index("import frappe"))


class NoMockTests(unittest.TestCase):
    def test_no_mocks_stubs_or_simulated_services_anywhere(self):
        for label, text in PROBES.items():
            for forbidden in ("unittest.mock", "from unittest import mock", "import mock",
                              "fakeredis", "testcontainers", "MagicMock", "patch(",
                              "docker-compose.yml.mock"):
                self.assertNotIn(forbidden, text, label + " uses " + forbidden)

    def test_probes_declare_they_are_not_simulations(self):
        self.assertIn('"mocks_or_simulations_used": False', SOURCE)
        self.assertIn('"mocks_or_simulations_used": False', TARGET)

    def test_containers_are_distinct_from_other_probes(self):
        """No shared container names, so no cross-probe state can leak in."""
        self.assertIn('MARIADB_CONTAINER = "foundation-indep-mariadb"', BOOTSTRAP)
        self.assertNotIn("foundation-mariadb\"", BOOTSTRAP)
        for name in ("foundation-indep-redis-queue", "foundation-indep-redis-cache"):
            self.assertIn(name, BOOTSTRAP)

    def test_services_are_real_pinned_containers(self):
        self.assertIn('"start-mariadb", "run", "--detach", "--name", MARIADB_CONTAINER', BOOTSTRAP)
        self.assertIn('return self.run(name, ["docker", *args], **kwargs)', BOOTSTRAP)
        self.assertIn("image_digest", BOOTSTRAP)
        self.assertIn('if "@sha256:" not in digest', BOOTSTRAP)
        self.assertIn("foundation-version-matrix.json", BOOTSTRAP)


class IndependenceTests(unittest.TestCase):
    """Judged from infrastructure facts, never from labels the platform reuses."""

    def _host(self, **overrides):
        host = {"hostname": "fv-abc123", "kernel_boot_id": "boot-1",
                "docker_daemon_id": "daemon-1", "dmi_product_uuid": "vm-1",
                "runner_name": "GitHub Actions 1", "job": "source", "run_id": "1"}
        host.update(overrides)
        return host

    def _other(self, **overrides):
        host = {"hostname": "fv-xyz789", "kernel_boot_id": "boot-2",
                "docker_daemon_id": "daemon-2", "dmi_product_uuid": "vm-2",
                "runner_name": "GitHub Actions 2", "job": "target", "run_id": "1"}
        host.update(overrides)
        return host

    def test_separate_systems_are_independent(self):
        verdict = target.independence_verdict(self._host(), self._other())
        self.assertTrue(verdict["independent"])
        self.assertTrue(verdict["kernel_boot_id_differs"])
        self.assertTrue(verdict["docker_daemon_id_differs"])
        self.assertFalse(verdict["shared_filesystem"])
        self.assertFalse(verdict["shared_containers"])
        self.assertFalse(verdict["shared_volumes"])
        self.assertEqual(verdict["shared_backup_channel"], "github-actions-artifact-only")

    def test_an_identical_hostname_does_not_defeat_independence(self):
        """Observed in hosted run 35143620884: both halves reported runnervmlun5p
        while their boot ids, runner names and Docker daemon ids all differed.
        Requiring a hostname to differ would reject genuinely separate VMs."""
        verdict = target.independence_verdict(
            self._host(hostname="runnervmlun5p", runner_name="GitHub Actions 1000002453"),
            self._other(hostname="runnervmlun5p", runner_name="GitHub Actions 1000002454"))
        self.assertTrue(verdict["hostname_matches"])
        self.assertFalse(verdict["hostname_used_as_a_discriminator"])
        self.assertTrue(verdict["independent"])

    def test_the_hostname_note_records_why_it_is_not_a_discriminator(self):
        verdict = target.independence_verdict(self._host(), self._other())
        self.assertIn("reuses generated hostnames", verdict["hostname_note"])
        self.assertIn("35143620884", verdict["hostname_note"])
        self.assertIn("never as proof of separation or of sameness", verdict["hostname_note"])

    def test_a_shared_kernel_boot_id_defeats_independence(self):
        """One live kernel is one live system, whatever the other labels say."""
        verdict = target.independence_verdict(self._host(), self._other(kernel_boot_id="boot-1"))
        self.assertFalse(verdict["kernel_boot_id_differs"])
        self.assertFalse(verdict["independent"])

    def test_a_shared_container_runtime_does_not_defeat_independence(self):
        """Run 35168111875: the runner image ships a pre-generated daemon key, so
        equal daemon ids on two separate VMs are expected and prove nothing."""
        verdict = target.independence_verdict(self._host(), self._other(docker_daemon_id="daemon-1"))
        self.assertFalse(verdict["docker_daemon_id_differs"])
        self.assertFalse(verdict["docker_daemon_id_used_as_a_discriminator"])
        self.assertIn("pre-generated daemon key", verdict["docker_daemon_id_note"])
        self.assertIn("35168111875", verdict["docker_daemon_id_note"])
        self.assertTrue(verdict["independent"])

    def test_a_shared_agent_registration_defeats_independence(self):
        """Two jobs on one VM share one runner agent."""
        verdict = target.independence_verdict(self._host(), self._other(runner_name="GitHub Actions 1"))
        self.assertFalse(verdict["runner_name_differs"])
        self.assertFalse(verdict["independent"])

    def test_the_hypervisor_identifier_is_recorded_as_corroboration(self):
        verdict = target.independence_verdict(self._host(), self._other())
        self.assertTrue(verdict["dmi_product_uuid_available"])
        self.assertTrue(verdict["dmi_product_uuid_differs"])

    def test_an_unreadable_hypervisor_identifier_is_never_faked(self):
        source = self._host()
        del source["dmi_product_uuid"]
        verdict = target.independence_verdict(source, self._other())
        self.assertFalse(verdict["dmi_product_uuid_available"])
        self.assertFalse(verdict["dmi_product_uuid_differs"])
        # Corroboration only; independence rests on the two real discriminators.
        self.assertTrue(verdict["independent"])

    def test_dmi_probe_returns_a_value_or_none_and_never_raises(self):
        """Executed: an unreadable identifier must be None, not a fabricated value."""
        value = dmi_product_uuid()
        self.assertTrue(value is None or (isinstance(value, str) and value.strip()))
        self.assertIn('"sudo", "-n", "cat"', BOOTSTRAP)
        self.assertIn("rather than pretending to be evidence", BOOTSTRAP)

    def test_missing_identifiers_fail_closed_rather_than_counting_as_different(self):
        for key in ("kernel_boot_id", "runner_name"):
            source, other = self._host(), self._other()
            del source[key]
            del other[key]
            self.assertFalse(target.independence_verdict(source, other)["independent"], key)

    def test_an_empty_identifier_is_not_treated_as_evidence(self):
        for empty in ("", None):
            verdict = target.independence_verdict(self._host(kernel_boot_id=empty), self._other())
            self.assertFalse(verdict["kernel_boot_id_differs"])
            self.assertFalse(verdict["independent"])

    def test_verdict_records_both_identities_for_audit(self):
        verdict = target.independence_verdict(self._host(), self._other())
        for key in ("source_hostname", "target_hostname", "source_job", "target_job",
                    "source_run_id", "target_run_id", "source_runner_name",
                    "target_runner_name"):
            self.assertIn(key, verdict)

    def test_target_fails_closed_when_the_verdict_is_not_independent(self):
        self.assertIn('if not report["independence"]["independent"]:', TARGET)
        self.assertIn("this is not an independent", TARGET)

    def test_independence_is_judged_after_the_runtime_identifier_is_known(self):
        self.assertLess(TARGET.index('report["machine_identity"]["docker_daemon_id"]'),
                        TARGET.index("independence_verdict(identity"))

    def test_both_halves_record_the_container_runtime_identifier(self):
        for label, text in (("source", SOURCE), ("target", TARGET)):
            self.assertIn('report["machine_identity"]["docker_daemon_id"]', text, label)
        self.assertIn('"docker-daemon-id"', BOOTSTRAP)
        self.assertIn("reusable label", BOOTSTRAP)

    def test_machine_identity_records_a_per_boot_identifier_when_present(self):
        """Executed: the primary discriminator must be read from the kernel."""
        identity = machine_identity()
        boot_id = Path("/proc/sys/kernel/random/boot_id")
        if boot_id.exists():
            self.assertEqual(identity["kernel_boot_id"], boot_id.read_text().strip())
        else:
            self.assertNotIn("kernel_boot_id", identity)

    def test_machine_identity_publishes_no_network_address(self):
        identity = machine_identity()
        self.assertTrue(identity["hostname"])
        for key in identity:
            self.assertNotIn("ip", key.lower())
            self.assertNotIn("address", key.lower())


class SharedStateAbsenceTests(unittest.TestCase):
    """Separation is also observed functionally, not only inferred from ids."""

    def test_the_target_observes_the_absence_of_source_state(self):
        self.assertIn('"no_shared_state_observed"', TARGET)
        self.assertIn("source-database-absent-from-target-datastore", TARGET)
        self.assertIn('identity["source_lab_path"]', TARGET)
        self.assertIn('identity["source_database_name"]', TARGET)

    def test_any_visible_source_state_fails_closed(self):
        self.assertIn("The target can see the source's private state", TARGET)
        self.assertIn('if source_lab.exists() or source_archived.exists() or schema_count != "0":',
                      TARGET)

    def test_the_database_check_queries_the_server_not_the_filesystem(self):
        self.assertIn("information_schema.schemata", TARGET)

    def test_the_source_publishes_what_the_target_must_not_be_able_to_see(self):
        self.assertIn('"source_lab_path": str(lab)', SOURCE)
        self.assertIn('"source_database_name": db_name', SOURCE)

    def test_the_absence_check_runs_before_the_restore(self):
        self.assertLess(TARGET.index("source-database-absent-from-target-datastore"),
                        TARGET.index('"restore-database-and-files"'))


class DestructiveTriggerTests(unittest.TestCase):
    def test_source_destroys_the_site_with_the_native_command(self):
        self.assertIn('"drop-site", SITE, "--db-root-password"', SOURCE)
        self.assertNotIn("rm -rf", SOURCE)
        self.assertNotIn("DROP DATABASE", SOURCE)

    def test_source_proves_state_was_present_before_destruction(self):
        for key in ("site_directory_exists", "database_present", "private_file_present",
                    "public_file_present"):
            self.assertIn(key, SOURCE)
        self.assertIn('raise RuntimeError("Source state was not fully present before destruction")',
                      SOURCE)

    def test_source_proves_destruction_actually_happened(self):
        self.assertIn('raise RuntimeError("Destructive trigger did not actually remove '
                      'the source site")', SOURCE)
        self.assertIn('post["database_present"] != "0"', SOURCE)

    def test_database_presence_is_checked_against_the_server_not_the_filesystem(self):
        self.assertIn("information_schema.schemata", SOURCE)
        self.assertIn("database-present-before-destruction", SOURCE)
        self.assertIn("database-present-after-destruction", SOURCE)

    def test_destruction_leaves_no_second_dump_on_the_source(self):
        """--no-backup, and any archived directory is recorded, not hidden."""
        self.assertIn('"--no-backup"', SOURCE)
        self.assertIn('report["archived_site_directories_on_source_only"]', SOURCE)
        self.assertIn("so the independent system cannot reach it", SOURCE)

    def test_the_archive_path_is_the_one_frappe_actually_uses(self):
        """frappe moves the site to <bench>/archived/sites; the wrong path would
        silently report an empty archive and misrepresent the evidence."""
        self.assertIn('archived = bench_dir / "archived" / "sites"', SOURCE)
        self.assertNotIn('"sites" / "archived_sites"', SOURCE)

    def test_target_states_the_source_was_already_destroyed(self):
        self.assertIn('report["source_site_was_destroyed_before_recovery"] = True', TARGET)
        self.assertIn('report["recovery_depends_on_the_staged_backup"] = True', SOURCE)


class SecretExclusionTests(unittest.TestCase):
    def test_payload_is_an_explicit_allowlist(self):
        self.assertEqual(sorted(target.EXPECTED_PAYLOAD),
                         ["database.sql.gz", "manifest.json", "private-files.tar",
                          "public-files.tar", "source-identity.json"])
        self.assertIn('if staged_files != sorted(STAGED_NAMES):', SOURCE)

    def test_site_config_is_never_staged(self):
        """bench writes it beside the dumps; it holds the db password and key."""
        self.assertIn("site_config", SOURCE)
        self.assertIn('raise RuntimeError("A site config was staged', SOURCE)
        self.assertNotIn("site_config.json", target.EXPECTED_PAYLOAD)
        self.assertIn('"backup_site_config_excluded"', SOURCE)

    def test_staged_text_is_scanned_for_generated_secrets(self):
        self.assertIn("A generated secret appears in staged", SOURCE)
        self.assertIn("The site encryption key appears in staged", SOURCE)

    def test_target_rejects_unexpected_payload_files(self):
        self.assertIn("Unexpected files arrived with the payload", TARGET)

    def test_manifest_holds_only_fingerprints_never_secret_values(self):
        self.assertIn('"source_key_sha256": hashlib.sha256(key.encode()).hexdigest()', DATA)
        self.assertIn('"ciphertext_sha256"', DATA)
        self.assertIn("names_sha256", DATA)
        self.assertIn("content_sha256", DATA)
        self.assertNotIn('"encryption_key": key', DATA)
        self.assertNotIn('"password": secret', DATA)
        self.assertIn("it never holds a password, an encryption key or a", DATA)

    def test_no_hardcoded_credentials_in_any_probe(self):
        for label, text in PROBES.items():
            self.assertNotIn("admin = \"", text, label)
            self.assertNotIn("password = \"", text, label)
        self.assertIn("secrets.token_urlsafe", SOURCE)
        self.assertIn("secrets.token_urlsafe", TARGET)

    def test_passwords_are_masked_and_redacted(self):
        self.assertIn("probe.mask(value)", SOURCE)
        self.assertIn("probe.mask(value)", TARGET)
        self.assertIn("probe.redact(json.dumps(report", TARGET)
        self.assertIn("probe.redact(json.dumps(report", SOURCE)

    def test_admin_password_reaches_the_usability_check_by_environment_only(self):
        self.assertIn('os.environ["FOUNDATION_ADMIN_PASSWORD"]', TARGET)
        self.assertIn('os.environ["FOUNDATION_ADMIN_PASSWORD"]', USABILITY)
        self.assertIn("never written to the report", USABILITY)


class PayloadIntegrityTests(unittest.TestCase):
    def setUp(self):
        self._original = target.PAYLOAD
        self._tmp = tempfile.TemporaryDirectory()
        target.PAYLOAD = Path(self._tmp.name)

    def tearDown(self):
        target.PAYLOAD = self._original
        self._tmp.cleanup()

    def _write_payload(self, names=target.EXPECTED_PAYLOAD):
        for name in names:
            (target.PAYLOAD / name).write_bytes(b"synthetic " + name.encode())

    def test_digests_are_the_real_file_digests(self):
        self._write_payload()
        observed = target.payload_digests()
        self.assertEqual(observed["database.sql.gz"]["bytes"], len(b"synthetic database.sql.gz"))
        self.assertEqual(len(observed["database.sql.gz"]["sha256"]), 64)
        self.assertEqual(set(observed), set(target.EXPECTED_PAYLOAD))

    def test_a_missing_payload_file_fails_closed(self):
        self._write_payload([n for n in target.EXPECTED_PAYLOAD if n != "private-files.tar"])
        with self.assertRaises(RuntimeError) as caught:
            target.payload_digests()
        self.assertIn("missing private-files.tar", str(caught.exception))

    def test_an_unexpected_payload_file_fails_closed(self):
        self._write_payload()
        (target.PAYLOAD / "20260101_120000-site_config.json").write_text('{"encryption_key": 1}')
        with self.assertRaises(RuntimeError) as caught:
            target.payload_digests()
        self.assertIn("Unexpected files arrived", str(caught.exception))

    def test_target_compares_every_archive_against_the_source_record(self):
        self.assertIn('for label in ("database.sql.gz", "private-files.tar", '
                      '"public-files.tar"):', TARGET)
        self.assertIn('identity["backup_sha256"][label]', TARGET)
        self.assertIn('identity["backup_bytes"][label]', TARGET)
        self.assertIn("does not match the source digest", TARGET)
        self.assertIn("size does not match the source", TARGET)


class RecoveryMechanismTests(unittest.TestCase):
    def test_target_restores_through_the_native_command(self):
        self.assertIn('"restore", str(PAYLOAD / "database.sql.gz")', TARGET)
        self.assertIn('"--with-public-files"', TARGET)
        self.assertIn('"--with-private-files"', TARGET)
        self.assertIn('"--admin-password"', TARGET)
        self.assertIn('"restore-migrate"', TARGET)

    def test_the_target_sets_its_own_admin_credential_with_the_native_command(self):
        """``bench restore --admin-password`` does not apply on the restore path:
        hosted run 35168996127 restored and verified, then login returned 401."""
        self.assertIn('"set-admin-password", admin_password', TARGET)
        self.assertIn("set-admin-password-on-recovered-site", TARGET)
        self.assertIn("returned 401", TARGET)
        self.assertIn('report["admin_credential_is_the_targets_own"]', TARGET)

    def test_no_source_credential_is_needed_to_recover(self):
        self.assertIn('"source_admin_password_transferred": False', TARGET)
        self.assertNotIn("site_config", " ".join(target.EXPECTED_PAYLOAD))

    def test_the_credential_is_set_before_usability_is_proven(self):
        self.assertLess(TARGET.index("set-admin-password-on-recovered-site"),
                        TARGET.index("prove-recovered-application-usable-over-http"))

    def test_restore_is_not_given_the_source_encryption_key(self):
        """The native option exists and is deliberately not used."""
        start = TARGET.index('"restore-database-and-files"')
        end = TARGET.index('"restore-migrate"')
        self.assertNotIn("--encryption-key", TARGET[start:end])
        self.assertIn('"native_option_available": "--encryption-key"', TARGET)
        self.assertIn('"used": False', TARGET)
        self.assertIn("Plaintext key material must not travel through an artifact", TARGET)

    def test_target_rebuilds_the_same_pinned_sources_as_the_source(self):
        self.assertIn('clone_pinned_sources(\n            probe, components, source_dir, '
                      '("frappe", "erpnext"))', TARGET)
        self.assertIn('identity["source_revisions"]', TARGET)
        self.assertIn("different source revisions than the source", TARGET)

    def test_target_creates_its_own_empty_site_before_restoring(self):
        self.assertIn('label="new-empty-site-on-independent-system"', TARGET)
        self.assertLess(TARGET.index("new-empty-site-on-independent-system"),
                        TARGET.index("restore-database-and-files"))

    def test_verify_asserts_records_not_just_their_count(self):
        self.assertIn("names_sha256", DATA)
        self.assertIn("recovered record names differ", DATA)
        self.assertIn("recovered {len(names)} of {expected['count']} records", DATA)

    def test_verify_asserts_file_bytes_documents_and_privacy_flags(self):
        self.assertIn("on_disk_sha256", DATA)
        self.assertIn("Recovered file content differs", DATA)
        self.assertIn("File document was not recovered", DATA)
        self.assertIn("File privacy flag changed", DATA)
        self.assertIn("File size changed", DATA)

    def test_both_halves_use_the_same_script_so_the_comparison_is_cross_machine(self):
        self.assertIn("runtime_independent_data.py", SOURCE)
        self.assertIn("runtime_independent_data.py", TARGET)
        self.assertIn("not between two interpretations of the same data", DATA)


class NativeCommandContractTests(unittest.TestCase):
    """Flags checked against the pinned frappe/bench sources, not guessed.

    frappe v16.33.1 (988e54f) ``backup`` accepts ``--with-files`` and ``--compress``;
    ``restore`` accepts ``--db-root-password``, ``--admin-password``,
    ``--with-public-files``, ``--with-private-files`` and ``--encryption-key``;
    ``drop-site`` accepts ``--db-root-password`` and ``--no-backup``.
    """

    def test_archives_are_tar_because_compression_is_not_requested(self):
        """frappe picks .tgz only when --compress is passed; the globs depend on it."""
        self.assertNotIn('"--compress"', SOURCE)
        for pattern in ('"*-database.sql.gz"', '"*-private-files.tar"', '"*-files.tar"'):
            self.assertIn(pattern, SOURCE)
        self.assertIn('"private" / "backups"', SOURCE)

    def test_public_archive_glob_excludes_the_private_one(self):
        self.assertIn('"-private-files" not in p.name', SOURCE)

    def test_the_bench_directory_is_the_working_directory_for_dump_and_restore(self):
        """Archive members are sites-relative, which is what --strip 2 assumes."""
        for label, text, step in (("source", SOURCE, '"backup-with-files"'),
                                  ("target", TARGET, '"restore-database-and-files"')):
            start = text.index(step)
            self.assertIn("cwd=bench_dir", text[start:start + 700], label)
        self.assertIn("--strip 2", TARGET)
        self.assertIn("cwd MUST be the bench directory", SOURCE)

    def test_both_halves_use_the_same_native_site_commands(self):
        for flag in ('"--db-type", "mariadb"', '"--mariadb-user-host-login-scope", "%"',
                     '"--db-root-password"', '"--admin-password"'):
            self.assertIn(flag, BOOTSTRAP)

    def test_restore_receives_both_file_archives(self):
        self.assertIn('"--with-public-files", str(PAYLOAD / "public-files.tar")', TARGET)
        self.assertIn('"--with-private-files", str(PAYLOAD / "private-files.tar")', TARGET)


class MariaDbClientTests(unittest.TestCase):
    """Ubuntu's Oracle ``mysqldump`` queries ``COLUMN_STATISTICS``, MariaDB lacks it.

    Hosted run 35142455523 failed at ``backup-with-files`` with MySQL error 1109
    for exactly this reason, after everything through ``create-synthetic-state``
    had passed.
    """

    def test_both_halves_install_mariadb_client(self):
        for label, text in (("source", SOURCE), ("target", TARGET)):
            self.assertIn("install_mariadb_client(probe)", text, label)

    def test_the_client_is_installed_before_the_dump_and_before_the_restore(self):
        self.assertLess(SOURCE.index("install_mariadb_client(probe)"),
                        SOURCE.index('"backup-with-files"'))
        self.assertLess(TARGET.index("install_mariadb_client(probe)"),
                        TARGET.index('"restore-database-and-files"'))

    def test_installation_matches_the_proven_harness(self):
        proven = (ROOT / "tools/foundation/runtime_install.py").read_text(encoding="utf-8")
        for package in ('"mariadb-client"', '"file"'):
            self.assertIn(package, BOOTSTRAP)
            self.assertIn(package, proven)
        self.assertIn("--no-install-recommends", BOOTSTRAP)

    def test_a_missing_dump_binary_fails_closed_with_the_reason(self):
        self.assertIn('shutil.which("mariadb-dump")', BOOTSTRAP)
        self.assertIn("error 1109", BOOTSTRAP)
        self.assertIn("COLUMN_STATISTICS", BOOTSTRAP)

    def test_the_reason_is_recorded_in_the_evidence(self):
        self.assertIn('"preferred_over_mysqldump_because"', BOOTSTRAP)
        self.assertIn('probe.report["mariadb_client"]', BOOTSTRAP)

    def test_frappe_resolution_order_is_what_makes_this_necessary(self):
        """Documented from frappe/database/__init__.py at the pinned commit."""
        self.assertIn('which("mariadb-dump") or which("mysqldump")', BOOTSTRAP)


class EncryptedFieldLimitationTests(unittest.TestCase):
    """The gap P4 must close is asserted, explained and never hidden."""

    def test_key_material_is_deliberately_not_transferred(self):
        self.assertIn("Plaintext key material must not", SOURCE)
        self.assertIn("it is never staged", SOURCE)
        self.assertIn("because the key was never", DATA)

    def test_a_successful_decryption_on_the_target_is_treated_as_failure(self):
        self.assertIn("which would mean ", DATA)
        self.assertIn("source key material travelled with the backup", DATA)

    def test_limitation_compares_key_fingerprints_not_key_values(self):
        self.assertIn("source_key_sha256", DATA)
        self.assertIn("target_key_sha256", DATA)
        self.assertIn('"keys_differ"', DATA)
        self.assertIn('"decrypts_on_target": False', DATA)
        self.assertNotIn('"encryption_key":', DATA)

    def test_target_generates_the_key_before_reading_it(self):
        """Frappe creates the key lazily; reading first would mask the result."""
        self.assertIn("lazily, so reading site_config.json before any key access", DATA)
        tail = DATA[DATA.rindex("get_encryption_key()"):]
        self.assertIn('read_text())["encryption_key"]', tail)
        self.assertLess(tail.index("get_encryption_key()"),
                        tail.index('read_text())["encryption_key"]'))

    def test_target_surfaces_the_limitation_in_its_own_report(self):
        self.assertIn('"encrypted_field_limitation"', TARGET)
        self.assertIn("separately controlled external key custody", TARGET)

    def test_ciphertext_is_still_verified_to_have_survived(self):
        self.assertIn("ciphertext_recovered_intact", DATA)
        self.assertIn("ciphertext_sha256", DATA)


class CiphertextAccessTests(unittest.TestCase):
    """``frappe.db.get_value`` appends ``ORDER BY creation``, which ``__Auth`` lacks.

    That is MySQL error 1054, and it failed the hosted source run at
    ``create-synthetic-state``. The ciphertext must be read with the native
    parameterized query the encryption-key probe already uses.
    """

    def test_the_broken_access_pattern_is_not_used(self):
        self.assertNotIn('get_value("__Auth"', DATA)
        self.assertIn("SELECT `password` FROM `__Auth`", DATA)
        self.assertIn("MySQL error 1054", DATA)

    def test_a_tuple_row_yields_the_value(self):
        self.assertEqual(data.first_ciphertext([("cipher",)], "User.A.x"), "cipher")

    def test_a_list_row_yields_the_value(self):
        self.assertEqual(data.first_ciphertext([["cipher"]], "User.A.x"), "cipher")

    def test_a_scalar_row_yields_the_value(self):
        self.assertEqual(data.first_ciphertext(["cipher"], "User.A.x"), "cipher")

    def test_no_rows_is_an_absent_ciphertext_not_an_empty_one(self):
        for rows in ([], None):
            with self.assertRaises(AssertionError) as caught:
                data.first_ciphertext(rows, "User.A.x")
            self.assertIn("No ciphertext row exists", str(caught.exception))

    def test_an_empty_value_is_rejected_rather_than_reported_as_recovered(self):
        for value in (None, "", b""):
            with self.assertRaises(AssertionError) as caught:
                data.first_ciphertext([(value,)], "User.A.x")
            self.assertIn("empty value", str(caught.exception))

    def test_the_failure_names_the_field_being_read(self):
        with self.assertRaises(AssertionError) as caught:
            data.first_ciphertext([], "User.Administrator.api_secret")
        self.assertIn("User.Administrator.api_secret", str(caught.exception))


class NginxContractTests(unittest.TestCase):
    """Public files must be served the way the pinned bench template serves them."""

    def setUp(self):
        self.conf = target.nginx_conf(Path("/tmp/lab"), Path("/tmp/bench"))

    def test_root_is_the_sites_directory_with_public_try_files(self):
        self.assertIn("root /tmp/bench/sites;", self.conf)
        self.assertIn("try_files /recovered.localhost/public/$uri @webserver;", self.conf)

    def test_site_is_resolved_from_a_host_whitelist(self):
        self.assertIn("map $host $foundation_site { default ''; recovered.localhost "
                      "recovered.localhost; }", self.conf)
        self.assertIn("if ($foundation_site = '') { return 444; }", self.conf)

    def test_proxy_forwards_the_site_name_and_host(self):
        self.assertIn("proxy_set_header X-Frappe-Site-Name $foundation_site;", self.conf)
        self.assertIn("proxy_set_header Host $http_host;", self.conf)
        self.assertIn("proxy_pass http://127.0.0.1:8000;", self.conf)

    def test_risky_public_uploads_are_forced_to_download(self):
        self.assertIn("^/files/.*.(htm|html|svg|xml)", self.conf)
        self.assertIn('add_header Content-disposition "attachment";', self.conf)

    def test_config_is_validated_before_the_proxy_starts(self):
        self.assertIn('"nginx-config-check", ["nginx", "-t", "-c", str(proxy_conf)]', TARGET)
        self.assertLess(TARGET.index("nginx-config-check"), TARGET.index("public-proxy"))

    def test_private_files_are_not_served_statically(self):
        self.assertNotIn("private/files", self.conf)

    def test_permitted_private_files_are_served_only_through_the_internal_location(self):
        """frappe answers with X-Accel-Redirect to /protected/<site-relative path>;
        without this location the response would be an empty 200."""
        self.assertIn("location ~ ^/protected/(.*) {", self.conf)
        self.assertIn("internal;", self.conf)
        self.assertIn("try_files /recovered.localhost/$1 =404;", self.conf)

    def test_the_proxy_asks_the_application_to_offload_private_files(self):
        self.assertIn("proxy_set_header X-Use-X-Accel-Redirect True;", self.conf)

    def test_protected_is_declared_before_the_public_file_rules(self):
        """nginx uses the first matching regex location."""
        self.assertLess(self.conf.index("^/protected/"), self.conf.index("^/files/"))


class UsabilityTests(unittest.TestCase):
    def test_requests_name_the_recovered_site(self):
        """Frappe resolves the site from the Host header."""
        self.assertIn('session.headers["Host"] = host', USABILITY)
        self.assertIn("host=SITE", USABILITY)
        self.assertIn('"host_header": SITE', USABILITY)

    def test_login_and_session_are_verified_not_assumed(self):
        self.assertIn("/api/method/login", USABILITY)
        self.assertIn("frappe.auth.get_logged_user", USABILITY)
        self.assertIn("Session is not authenticated as Administrator", USABILITY)

    def test_a_source_created_record_is_read_back_over_http(self):
        self.assertIn("synthetic-independent-recovery-", USABILITY)
        self.assertIn("all_source_records_listed", USABILITY)
        self.assertIn("Recovered record content differs", USABILITY)

    def test_the_listing_is_filtered_so_a_page_cap_cannot_fake_a_shortfall(self):
        self.assertIn('"filters": json.dumps(', USABILITY)
        self.assertIn("an unfiltered list could be", USABILITY)
        self.assertIn("Source records not listed over HTTP", USABILITY)

    def test_both_files_are_downloaded_and_digest_compared(self):
        self.assertIn("for file_name in (PRIVATE_FILE, PUBLIC_FILE):", USABILITY)
        self.assertIn("served_sha256_matches_manifest", USABILITY)
        self.assertIn("Served file content differs from the manifest", USABILITY)

    def test_privacy_boundary_is_proven_with_an_anonymous_caller(self):
        self.assertIn("anonymous = session_for(requests, base_url)", USABILITY)
        self.assertIn("Private file was served without authentication", USABILITY)
        self.assertIn("private_denied_without_session", USABILITY)
        self.assertIn("public_served_anonymously_with_matching_content", USABILITY)

    def test_an_anonymous_private_fetch_must_not_follow_redirects_into_success(self):
        self.assertIn("allow_redirects=False", USABILITY)

    def test_readiness_is_polled_not_slept_on(self):
        self.assertIn("did not answer ping within 240s", USABILITY)
        self.assertIn("time.sleep(2)", USABILITY)

    def test_target_fails_if_usability_does_not_pass(self):
        self.assertIn('if usability["status"] != "pass":', TARGET)
        self.assertIn("Recovered application was not usable over HTTP", TARGET)

    def test_backend_failure_during_startup_is_detected(self):
        self.assertIn("exited immediately with", TARGET)

    def test_only_synthetic_data_is_used(self):
        self.assertIn("synthetic-independent-recovery-", DATA)
        self.assertIn("synthetic private content", DATA)
        self.assertIn("synthetic public content", DATA)
        self.assertIn("no real business data", DATA)


class EvidenceHonestyTests(unittest.TestCase):
    def test_target_states_what_it_does_not_prove(self):
        for limitation in ("different cloud provider, region or physical datacentre",
                           "external key custody",
                           "Recovery time and recovery point objectives",
                           "Off-site or air-gapped backup storage",
                           "TLS termination and the Tailscale boundary",
                           "synthetic"):
            self.assertIn(limitation, TARGET)

    def test_neither_half_claims_production_qualification(self):
        for label in ("source", "target"):
            self.assertNotIn("production ready", PROBES[label])
            self.assertNotIn("PRODUCTION QUALIFIED", PROBES[label])

    def test_scope_declares_the_synthetic_boundary(self):
        self.assertIn("real backup of synthetic ", SOURCE)
        self.assertIn("synthetic data only", TARGET)
        self.assertIn("no real business data", DATA)

    def test_failures_are_written_out_and_propagate_as_exit_codes(self):
        for text in (SOURCE, TARGET):
            self.assertIn('report["status"] = "fail"', text)
            self.assertIn('return 0 if report["status"] == "pass" else 1', text)

    def test_teardown_never_masks_the_result(self):
        self.assertIn("Best-effort teardown; never masks the real result.", BOOTSTRAP)
        self.assertIn("cleanup((MARIADB_CONTAINER", TARGET)
        self.assertIn("cleanup((MARIADB_CONTAINER", SOURCE)

    def test_secret_file_is_removed(self):
        self.assertIn("secret_file.unlink(missing_ok=True)", SOURCE)
        self.assertIn("secret_file.unlink(missing_ok=True)", TARGET)
        self.assertIn("secret_file.chmod(0o600)", SOURCE)


class BootstrapBehaviourTests(unittest.TestCase):
    """Executed against the real Probe, which needs no Docker."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.report = {"checks": [], "status": "running"}
        self.probe = Probe(self.report, Path(self._tmp.name), Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_extra_env_reaches_the_child_without_mutating_this_process(self):
        """Regression: MYSQL_PWD was assigned into os.environ only *after* the
        pre-destruction query had already run, so `docker exec --env MYSQL_PWD`
        forwarded nothing and the check could not authenticate."""
        out = self.probe.run(
            "env-check",
            [sys.executable, "-c", "import os;print(os.environ['FOUNDATION_CONTRACT_VAR'])"],
            env={"FOUNDATION_CONTRACT_VAR": "sent"})
        self.assertEqual(out, "sent")
        self.assertNotIn("FOUNDATION_CONTRACT_VAR", os.environ)
        self.assertEqual(self.report["checks"][0]["exit_code"], 0)

    def test_a_command_without_extra_env_inherits_the_process_environment(self):
        os.environ["FOUNDATION_INHERITED_VAR"] = "inherited"
        try:
            out = self.probe.run(
                "inherit-check",
                [sys.executable, "-c", "import os;print(os.environ['FOUNDATION_INHERITED_VAR'])"])
            self.assertEqual(out, "inherited")
        finally:
            del os.environ["FOUNDATION_INHERITED_VAR"]

    def test_nonzero_exit_fails_closed_and_is_recorded(self):
        with self.assertRaises(RuntimeError):
            self.probe.run("failing", [sys.executable, "-c", "import sys;sys.exit(3)"])
        self.assertEqual(self.report["status"], "fail")
        self.assertEqual(self.report["checks"][-1]["exit_code"], 3)
        self.assertIn("output_tail", self.report["checks"][-1])

    def test_allow_failure_records_without_raising(self):
        out = self.probe.run("tolerated", [sys.executable, "-c", "import sys;sys.exit(1)"],
                             allow_failure=True)
        self.assertEqual(out, "")
        self.assertEqual(self.report["checks"][-1]["status"], "fail")

    def test_masked_values_are_redacted_from_recorded_output(self):
        self.probe.mask("s3cret-contract-value")
        self.probe.run("leaky", [sys.executable, "-c", "print('s3cret-contract-value')"])
        serialized = json.dumps(self.report)
        self.assertNotIn("s3cret-contract-value", serialized)
        self.assertIn("[REDACTED]", serialized)

    def test_quiet_success_is_not_recorded_but_quiet_failure_is(self):
        self.probe.run("silent", [sys.executable, "-c", "pass"], quiet=True)
        self.assertEqual(self.report["checks"], [])
        with self.assertRaises(RuntimeError):
            self.probe.run("loud-failure", [sys.executable, "-c", "import sys;sys.exit(2)"],
                           quiet=True)
        self.assertEqual(len(self.report["checks"]), 1)

    def test_written_evidence_is_redacted(self):
        self.probe.mask("s3cret-contract-value")
        destination = Path(self._tmp.name) / "out.txt"
        self.probe.write(destination, "contains s3cret-contract-value here")
        self.assertNotIn("s3cret-contract-value", destination.read_text())

    def test_evidence_directory_is_created_on_construction(self):
        nested = Path(self._tmp.name) / "deep" / "evidence"
        Probe({}, nested, Path(self._tmp.name))
        self.assertTrue(nested.is_dir())


class CredentialHandlingTests(unittest.TestCase):
    def test_the_database_credential_is_available_before_the_first_query(self):
        self.assertIn('db_env = {"MYSQL_PWD": root_password}', SOURCE)
        self.assertLess(SOURCE.index('db_env = {"MYSQL_PWD"'),
                        SOURCE.index("database-present-before-destruction"))
        self.assertEqual(SOURCE.count("quiet=True, env=db_env)"), 2)

    def test_no_probe_assigns_credentials_into_the_process_environment(self):
        self.assertNotIn('os.environ["MYSQL_PWD"]', SOURCE)
        self.assertNotIn('os.environ["MYSQL_PWD"]', TARGET)
        self.assertNotIn("os.environ.update", BOOTSTRAP)

    def test_bootstrap_merges_rather_than_replaces_the_environment(self):
        self.assertIn("environment = dict(os.environ, **env) if env else None", BOOTSTRAP)
        self.assertIn("env=environment", BOOTSTRAP)


class WorkflowContractTests(unittest.TestCase):
    def test_workflow_is_restricted_to_the_active_branch(self):
        # Read from the canonical pin so a rotation cannot strand a stale branch here.
        self.assertIn(f"if: github.ref == '{ACTIVE_REF}'", WORKFLOW,
                      mismatch(WORKFLOW, ACTIVE_BRANCH, ACTIVE_REF))
        self.assertIn(f"branches: [{ACTIVE_BRANCH}]", WORKFLOW,
                      mismatch(WORKFLOW, ACTIVE_BRANCH, ACTIVE_REF))
        self.assertEqual(WORKFLOW.count("if: github.ref =="), 2)

    def test_two_jobs_run_and_the_target_depends_on_the_source(self):
        self.assertIn("\n  source:", WORKFLOW)
        self.assertIn("\n  target:", WORKFLOW)
        self.assertIn("needs: source", WORKFLOW)
        self.assertEqual(WORKFLOW.count("runs-on: ubuntu-24.04"), 2)

    def test_the_artifact_is_the_only_channel_between_the_systems(self):
        self.assertIn("actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f", WORKFLOW)
        self.assertIn("actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131", WORKFLOW)
        self.assertIn("independent-recovery-payload-", WORKFLOW)
        self.assertLess(WORKFLOW.index("upload-artifact"), WORKFLOW.index("download-artifact"))

    def test_payload_upload_is_restricted_to_the_staged_directory(self):
        self.assertIn("path: .foundation/independent-recovery/payload/", WORKFLOW)
        self.assertIn("if-no-files-found: error", WORKFLOW)

    def test_workflow_uses_pinned_action_references(self):
        self.assertIn("actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09", WORKFLOW)
        self.assertIn("actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38", WORKFLOW)
        self.assertIn("persist-credentials: false", WORKFLOW)
        self.assertNotIn("@v4\n", WORKFLOW)
        self.assertNotIn("@main", WORKFLOW)

    def test_workflow_permissions_are_minimal(self):
        self.assertIn("contents: read", WORKFLOW)
        self.assertIn("checks: write", WORKFLOW)
        self.assertNotIn("contents: write", WORKFLOW)
        self.assertNotIn("actions: write", WORKFLOW)

    def test_contract_tests_run_before_the_probe(self):
        self.assertLess(WORKFLOW.index("Test independent-recovery contract guards"),
                        WORKFLOW.index("python3 tools/foundation/runtime_independent_source.py"))

    def test_both_halves_publish_and_retain_evidence_including_failures(self):
        self.assertIn("publish_evidence.py\n          "
                      ".foundation/independent-source-evidence/source-result.json", WORKFLOW)
        self.assertIn("publish_evidence.py\n          "
                      ".foundation/independent-target-evidence/target-result.json", WORKFLOW)
        self.assertEqual(WORKFLOW.count("if: always()"), 5)
        self.assertEqual(WORKFLOW.count("retention-days: 14"), 3)

    def test_both_halves_establish_a_compatible_runtime_first(self):
        self.assertEqual(WORKFLOW.count("python3 tools/foundation/runner_probe.py"), 2)

    def test_jobs_are_time_bounded(self):
        self.assertEqual(WORKFLOW.count("timeout-minutes: 60"), 2)


if __name__ == "__main__":
    unittest.main()

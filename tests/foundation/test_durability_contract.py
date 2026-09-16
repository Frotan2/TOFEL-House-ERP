"""Static and guard contract for the real MariaDB/Redis durability probe.

The D8 durability gate was BLOCKED because nothing had ever executed a MariaDB
or Redis restart, a crash or volume-loss probe, or AOF/RDB persistence
verification. The only restart evidence was Gunicorn/RQ process replacement,
which explicitly excludes the datastore.

These guards keep ``tools/foundation/runtime_durability.py`` honest: it must use
real pinned containers with named volumes, must exercise restart AND SIGKILL
crash AND container destruction, must compare exact before/after state, must
include a negative control, and must not claim more than it proves.

They cannot execute the probe (that needs a disposable Docker-capable hosted
runner). The PASS comes from the hosted durability run, never from this file.
"""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from runtime_durability import extract_innodb_section  # noqa: E402

PROBE = (ROOT / "tools/foundation/runtime_durability.py").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/foundation-durability.yml").read_text(encoding="utf-8")
MATRIX = (ROOT / "docs/engineering/foundation-version-matrix.json").read_text(encoding="utf-8")


class ContainmentTests(unittest.TestCase):
    def test_probe_refuses_to_run_outside_a_hosted_runner(self):
        """Executed: the guard must fail closed on any non-Actions machine."""
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools/foundation/runtime_durability.py")],
            capture_output=True, text=True, cwd=str(ROOT), env={"PATH": "/usr/bin:/bin"})
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("ephemeral Actions runner", completed.stderr + completed.stdout)

    def test_probe_requires_reviewed_image_digests(self):
        self.assertIn('if not digest or "@sha256:" not in digest:', PROBE)
        self.assertIn('components[name]["image_digest"]', PROBE)
        # Digests come from the version matrix, never from a mutable tag.
        self.assertIn("foundation-version-matrix.json", PROBE)
        self.assertNotIn("mariadb:11.8.9", PROBE)
        self.assertNotIn("redis:8.6.6", PROBE)
        self.assertIn("sha256:2d2f4095530294735a857cfe22bb101e19b0849b416911c796ec4aa81b164a62", MATRIX)
        self.assertIn("sha256:75934ddb37bfaebe3b4082ba673cac39f66495244134f33dd0a502ce03cdcd36", MATRIX)


class RealServiceTests(unittest.TestCase):
    def test_no_mocks_stubs_or_simulated_services_are_imported(self):
        for forbidden in ("unittest.mock", "from unittest import mock", "import mock",
                          "fakeredis", "testcontainers", "docker-compose.yml.mock",
                          "MagicMock", "patch("):
            self.assertNotIn(forbidden, PROBE)
        self.assertIn('"mocks_or_simulations_used": False', PROBE)

    def test_mariadb_runs_as_a_real_container_with_a_named_volume(self):
        self.assertIn('"docker", "run", "--detach", "--name", MARIADB_CONTAINER', PROBE)
        self.assertIn('"--volume", MARIADB_VOLUME + ":/var/lib/mysql"', PROBE)
        self.assertIn('"docker", "volume", "create", volume', PROBE)
        self.assertIn("MARIADB_VOLUME = \"foundation-durability-mariadb-data\"", PROBE)

    def test_redis_runs_as_a_real_container_with_a_named_volume(self):
        self.assertIn('"--volume", REDIS_VOLUME + ":/data"', PROBE)
        self.assertIn("REDIS_VOLUME = \"foundation-durability-redis-data\"", PROBE)

    def test_durability_settings_are_explicit_and_read_back_from_the_server(self):
        """Configured on the command line AND verified in force at runtime."""
        for setting in ('"--innodb-flush-log-at-trx-commit=1"', '"--sync-binlog=1"',
                        '"--log-bin=mariadb-bin"', '"--appendonly", "yes"',
                        '"--appendfsync", "always"', '"--save", "900", "1"'):
            self.assertIn(setting, PROBE)
        self.assertIn('sql("SELECT @@innodb_flush_log_at_trx_commit;")', PROBE)
        self.assertIn('sql("SELECT @@sync_binlog;")', PROBE)
        self.assertIn('sql("SELECT @@log_bin;")', PROBE)
        self.assertIn('redis_cli("INFO", "persistence")', PROBE)
        # The probe must refuse to continue if the settings did not take effect.
        self.assertIn('if pre["redis"]["aof_enabled"] != "1":', PROBE)
        self.assertIn('if pre["mariadb"]["innodb_flush_log_at_trx_commit"] != "1":', PROBE)


class ScenarioCoverageTests(unittest.TestCase):
    def test_all_three_disruption_scenarios_are_executed(self):
        self.assertIn('"docker", "restart", "--time", "30", MARIADB_CONTAINER', PROBE)
        self.assertIn('"docker", "restart", "--time", "30", REDIS_CONTAINER', PROBE)
        self.assertIn('"docker", "kill", "--signal=KILL", MARIADB_CONTAINER', PROBE)
        self.assertIn('"docker", "kill", "--signal=KILL", REDIS_CONTAINER', PROBE)
        self.assertIn('"docker", "rm", "--force", container', PROBE)
        self.assertIn("scenario_1_graceful_restart", PROBE)
        self.assertIn("scenario_2_sigkill_crash_recovery", PROBE)
        self.assertIn("scenario_3_container_destruction", PROBE)

    def test_scenarios_run_in_the_required_order(self):
        start = PROBE.index('run("start-mariadb"')
        pre = PROBE.index('report["pre_state"] = {')
        restart = PROBE.index('"docker", "restart", "--time", "30", MARIADB_CONTAINER')
        kill = PROBE.index('"docker", "kill", "--signal=KILL", MARIADB_CONTAINER')
        destroy = PROBE.index('"docker", "rm", "--force", container')
        recreate = PROBE.index('run("recreate-mariadb-from-volume"')
        control = PROBE.index("negative_control_volume_loss")
        self.assertLess(start, pre)
        self.assertLess(pre, restart, "pre-state must be captured before disruption")
        self.assertLess(restart, kill)
        self.assertLess(kill, destroy)
        self.assertLess(destroy, recreate)
        self.assertLess(recreate, control)

    def test_a_negative_control_proves_data_lived_in_the_volume(self):
        """Without it, survival could be luck rather than durability."""
        self.assertIn('"docker", "volume", "rm", MARIADB_VOLUME', PROBE)
        self.assertIn('run("create-empty-mariadb-volume"', PROBE)
        self.assertIn("confirms_data_lived_in_the_volume", PROBE)
        self.assertIn('raise RuntimeError("Negative control failed: data survived complete volume loss")', PROBE)

    def test_binlog_rotation_is_enforced_not_merely_recorded(self):
        """Each MariaDB start rotates a new binary log, so a strictly increasing
        count independently proves the server really restarted. Observed on the
        first successful run as 000001 -> 000002 -> 000003 -> 000004 -> 000005."""
        self.assertIn("def assert_binlog_rotated(label, state):", PROBE)
        self.assertIn('raise RuntimeError(\n                    label + ": binary log did not rotate', PROBE)
        self.assertEqual(PROBE.count('"binlog_rotations_observed"'), 3,
                         "one enforced call per disruption scenario")
        self.assertEqual(PROBE.count("assert_binlog_rotated("), 4,
                         "definition plus one enforced call per scenario")
        self.assertIn("binlog_rotation_progression", PROBE)

    def test_crash_scenario_requires_server_side_log_corroboration(self):
        """The first successful run captured no InnoDB log lines because the
        filter was too narrow; the scenario must not pass on data integrity
        alone without any server-side evidence that recovery happened."""
        self.assertIn('"docker", "logs", "--tail", "600", MARIADB_CONTAINER', PROBE)
        for marker in ('"innodb"', '"recovery"', '"redo"', '"rollback"',
                       '"ready for connections"', '"shutdown"'):
            self.assertIn(marker, PROBE)
        self.assertIn('"log_lines_captured"', PROBE)
        self.assertIn("SHOW ENGINE INNODB STATUS", PROBE)
        self.assertIn('raise RuntimeError(\n                "Crash scenario has neither InnoDB recovery log lines nor an "', PROBE)

    def test_crash_and_startup_log_lines_are_never_merged(self):
        """A broadened filter once matched only '[Entrypoint]: Starting temporary
        server' and reported it under innodb_recovery_messages, which overstated
        the evidence. Startup noise must be recorded separately."""
        self.assertIn('crash_markers = ("innodb", "recovery", "crash", "redo", "rollback", "roll back")', PROBE)
        self.assertIn('startup_markers = ("ready for connections", "shutdown", "starting", "entrypoint")', PROBE)
        self.assertIn('"innodb_recovery_messages": innodb_lines', PROBE)
        self.assertIn('"server_startup_messages": startup_lines', PROBE)
        self.assertIn('"innodb_status_log_section": log_section', PROBE)
        self.assertIn("never mistaken for recovery evidence", PROBE)

    def test_innodb_force_recovery_must_be_zero(self):
        """Any other value makes crash recovery skip work and voids the scenario."""
        self.assertIn('sql("SELECT @@innodb_force_recovery;")', PROBE)
        self.assertIn('if pre["mariadb"]["innodb_force_recovery"] != "0":', PROBE)
        self.assertIn('raise RuntimeError("innodb_force_recovery was not 0, so crash recovery would be bypassed")', PROBE)

    def test_recreation_is_proven_to_produce_new_containers(self):
        self.assertIn("{{.Id}}", PROBE)
        self.assertIn("new_containers_created", PROBE)
        self.assertIn('raise RuntimeError("Container destruction did not actually replace the containers")', PROBE)


class ExactStateTests(unittest.TestCase):
    def test_committed_state_is_compared_exactly_not_approximately(self):
        self.assertIn("COALESCE(SUM(CRC32(CONCAT_WS('|', id, payload))), 0)", PROBE)
        self.assertIn('"committed_row_count"', PROBE)
        self.assertIn('"payload_crc32_sum"', PROBE)
        self.assertIn('if state["mariadb"]["payload_crc32_sum"] != pre["mariadb"]["payload_crc32_sum"]:', PROBE)
        self.assertIn("committed_value_sha256", PROBE)
        self.assertIn("queue_head_sha256", PROBE)

    def test_an_open_uncommitted_transaction_is_held_and_proved_invisible(self):
        self.assertIn("START TRANSACTION;", PROBE)
        self.assertIn("uncommitted-crash-probe", PROBE)
        self.assertIn("subprocess.Popen(", PROBE)
        self.assertIn('"uncommitted_visible"', PROBE)
        self.assertIn('if pre["mariadb"]["uncommitted_visible"] != "0":', PROBE)
        self.assertIn("uncommitted_row_absent_after_crash", PROBE)
        self.assertIn("uncommitted_row_absent_after_recovery", PROBE)

    def test_survival_is_asserted_after_every_scenario(self):
        self.assertEqual(PROBE.count('assert_survived('), 4,
                         "definition plus one call per disruption scenario")
        self.assertIn('assert_survived("graceful restart", state)', PROBE)
        self.assertIn('assert_survived("crash recovery", state)', PROBE)
        self.assertIn('assert_survived("volume persistence after container destruction", state)', PROBE)

    def test_pre_state_is_verified_before_scenarios_begin(self):
        self.assertIn('if pre["mariadb"]["committed_row_count"] != COMMITTED_ROWS:', PROBE)
        self.assertIn('if pre["redis"]["dbsize"] < 2 or pre["redis"]["queue_length"] != COMMITTED_ROWS:', PROBE)
        self.assertIn('"docker", "exec", REDIS_CONTAINER, "redis-cli", *args', PROBE)


class SecretHygieneTests(unittest.TestCase):
    def test_root_password_is_masked_and_never_reported(self):
        self.assertIn('print("::add-mask::" + root_password, flush=True)', PROBE)
        self.assertIn("secrets.token_urlsafe(32)", PROBE)
        self.assertIn("secret_file.chmod(0o600)", PROBE)
        self.assertIn("MARIADB_ROOT_PASSWORD_FILE=/run/secrets/db-password", PROBE)
        # Supplied through a bind-mounted secret file, not a command-line flag.
        self.assertNotIn("--password=", PROBE)
        self.assertNotIn("MARIADB_ROOT_PASSWORD=", PROBE)

    def test_every_written_report_is_redacted(self):
        self.assertIn('report_path.write_text(redact(json.dumps(report, indent=2)) + "\\n")', PROBE)
        self.assertIn('return (text or "").replace(root_password, "[REDACTED]")', PROBE)
        self.assertIn("secret_file.unlink(missing_ok=True)", PROBE)

    def test_containers_and_volumes_are_cleaned_up(self):
        self.assertIn('["docker", "rm", "--force", container]', PROBE)
        self.assertIn('["docker", "volume", "rm", "--force", volume]', PROBE)


class EvidenceHonestyTests(unittest.TestCase):
    def test_probe_states_what_it_does_not_prove(self):
        self.assertIn("not_proven_by_this_probe", PROBE)
        for limitation in ("Host or region loss", "High availability", "Application-level workflow",
                           "Backup archive integrity", "owner-selected durability reference"):
            self.assertIn(limitation, PROBE)

    def test_probe_scope_excludes_application_workflow_claims(self):
        self.assertIn("synthetic data only, not application workflow proof", PROBE)
        self.assertNotIn("production_authorization", PROBE)
        self.assertNotIn("production_enabled", PROBE)

    def test_index_and_platform_digests_are_both_recorded(self):
        """They legitimately differ; recording both prevents a false mismatch."""
        self.assertIn('"index_digest"', PROBE)
        self.assertIn("resolved_platform_digests", PROBE)
        self.assertIn("{{json .RepoDigests}}", PROBE)


INNODB_STATUS_FIXTURE = """=====================================
2026-09-16 18:58:01 INNODB MONITOR OUTPUT
=====================================
-----------------
BACKGROUND THREAD
-----------------
srv_master_thread loops: 12
-------------------------------------
SEMAPHORES
-------------------------------------
OS WAIT ARRAY INFO: reservation count 5
---
LOG
---
Log sequence number 98765
Log flushed up to 98765
Last checkpoint at 98765
0 pending log flushes, 0 pending chkp writes
----------------------
BUFFER POOL AND MEMORY
----------------------
Total large memory allocated 68157440
"""


class InnodbStatusParserTests(unittest.TestCase):
    """Executed against a realistic fixture.

    This caught a real defect: the first implementation stopped on the dash rule
    that *closes* the header, so it returned only ['LOG'].
    """

    def test_extracts_only_the_requested_section_body(self):
        self.assertEqual(extract_innodb_section(INNODB_STATUS_FIXTURE, "LOG"), [
            "Log sequence number 98765", "Log flushed up to 98765",
            "Last checkpoint at 98765",
            "0 pending log flushes, 0 pending chkp writes"])

    def test_does_not_leak_past_the_end_of_the_section(self):
        for line in extract_innodb_section(INNODB_STATUS_FIXTURE, "LOG"):
            self.assertNotIn("BUFFER POOL", line)
            self.assertNotIn("Total large memory", line)
        self.assertNotIn("LOG", extract_innodb_section(INNODB_STATUS_FIXTURE, "LOG"))

    def test_handles_headers_with_different_rule_widths(self):
        self.assertEqual(extract_innodb_section(INNODB_STATUS_FIXTURE, "SEMAPHORES"),
                         ["OS WAIT ARRAY INFO: reservation count 5"])
        self.assertEqual(extract_innodb_section(INNODB_STATUS_FIXTURE, "BACKGROUND THREAD"),
                         ["srv_master_thread loops: 12"])

    def test_missing_section_and_empty_input_return_empty(self):
        self.assertEqual(extract_innodb_section(INNODB_STATUS_FIXTURE, "NONEXISTENT"), [])
        self.assertEqual(extract_innodb_section("", "LOG"), [])
        self.assertEqual(extract_innodb_section(None, "LOG"), [])

    def test_unclosed_header_is_not_matched(self):
        self.assertEqual(extract_innodb_section("---\nLOG\nLog sequence number 1\n", "LOG"), [])

    def test_lines_are_truncated_and_capped(self):
        self.assertEqual(extract_innodb_section("---\nLOG\n---\n" + "x" * 400 + "\n", "LOG"),
                         ["x" * 200])
        many = "---\nLOG\n---\n" + "".join(f"line {i}\n" for i in range(50))
        self.assertEqual(len(extract_innodb_section(many, "LOG")), 20)


class WorkflowContractTests(unittest.TestCase):
    def test_workflow_is_restricted_to_the_active_branch(self):
        self.assertIn("if: github.ref == 'refs/heads/arena/01a0aafe-tofel-house-erp'", WORKFLOW)
        self.assertIn("branches: [arena/01a0aafe-tofel-house-erp]", WORKFLOW)

    def test_workflow_publishes_and_retains_evidence_including_failures(self):
        self.assertIn("if: always()", WORKFLOW)
        self.assertIn("publish_evidence.py .foundation/durability-evidence/durability-result.json", WORKFLOW)
        self.assertIn("if-no-files-found: error", WORKFLOW)
        self.assertIn("retention-days: 14", WORKFLOW)

    def test_workflow_runs_the_contract_tests_before_the_probe(self):
        self.assertLess(WORKFLOW.index("Test durability contract guards"),
                        WORKFLOW.index("python3 tools/foundation/runtime_durability.py"))

    def test_workflow_uses_pinned_action_references(self):
        self.assertIn("actions/checkout@11d5960a326750d5838078e36cf38b85af677262", WORKFLOW)
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", WORKFLOW)
        self.assertIn("persist-credentials: false", WORKFLOW)

    def test_workflow_permissions_are_minimal(self):
        self.assertIn("contents: read", WORKFLOW)
        self.assertIn("checks: write", WORKFLOW)
        self.assertNotIn("contents: write", WORKFLOW)
        self.assertNotIn("actions: write", WORKFLOW)


if __name__ == "__main__":
    unittest.main()

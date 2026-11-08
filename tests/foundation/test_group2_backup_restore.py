"""Group 2 (backup/restore/data loss) regression tests for main@4b14adf8.

Covers, with stubs and fixtures only (never a real GPG key, bench, or
live site):

* U-04: backup GPG verification must actually decrypt with the recorded key.
* U-03: a production restore's pre-restore preservation set must be fresh
  and decryptable (database fully, file archives as valid tar) before the
  in-progress marker or any live-data mutation. Single-use consumption
  still happens first, by design: a refused request stays spent.
* U-05: the staged database artifact is decrypt-probed and both staged
  file archives pass a tar-header check before native _restore(force=True).
* U-02: the post-migration census counts Fees, Program Enrollment, Student
  Applicant and verified TH policy masters, and the Fees grand_total sum
  must match exactly before and after. Refinement: every census doctype
  is also hashed per record (canonical SHA-256 over name + key fields),
  so a migration that swaps amounts between two Fees rows — same count,
  same sum — is refused.
* U-01: apply rebinds only evidence the authorize phase recorded, and
  defaults backup_dir exactly as _evaluate does, so a migration=="none"
  release with backup_required=False can apply.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))
sys.path.insert(0, str(ROOT / "tests" / "foundation"))

import native_gpg  # noqa: E402
import update_engine as engine  # noqa: E402
from test_update_engine import FAKE_BENCH, NOW, UpdateFixture  # noqa: E402

NOW_UTC = datetime.now(timezone.utc)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tar_header_bytes() -> bytes:
    header = bytearray(512)
    header[257:262] = b"ustar"
    header[263:265] = b"00"
    return bytes(header)


class FakeDecryptStdin:
    def __init__(self):
        self.written = []

    def write(self, data: bytes) -> int:
        self.written.append(data)
        return len(data)

    def close(self) -> None:
        pass


def make_popen(*, returncode=0, stdout_bytes=b"", stderr_bytes=b""):
    """A Popen stand-in recording argv/stdin for probe assertions."""
    calls = []

    class FakePopen:
        def __init__(self, arguments, **kwargs):
            self.arguments = list(arguments)
            self.stdin = FakeDecryptStdin()
            self.stdout = io.BytesIO(stdout_bytes)
            self.stderr = io.BytesIO(stderr_bytes)
            calls.append(self)

        def wait(self) -> int:
            return returncode

    FakePopen.calls = calls
    return FakePopen


class NativeGpgProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="group2-probe-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.artifact = self.tmp / "artifact-enc"
        self.artifact.write_bytes(b"synthetic encrypted artifact")

    def test_bad_passphrase_shape_fails_without_a_child_process(self):
        with patch.object(native_gpg.subprocess, "Popen") as popen:
            with self.assertRaises(native_gpg.GpgProbeError):
                native_gpg.probe_gpg_decrypt(self.artifact, "bad\nkey")
        popen.assert_not_called()

    def test_child_process_failure_is_a_probe_error_with_a_safe_category(self):
        popen = make_popen(returncode=2, stderr_bytes=b"gpg: bad passphrase\n")
        with patch.object(native_gpg.subprocess, "Popen", popen):
            with self.assertRaises(native_gpg.GpgProbeError) as caught:
                native_gpg.probe_gpg_decrypt(self.artifact, "synthetic-key")
        self.assertEqual(caught.exception.category, "bad-passphrase")
        self.assertNotIn("synthetic-key", " ".join(popen.calls[0].arguments))
        self.assertNotIn("--passphrase", popen.calls[0].arguments)
        self.assertEqual(popen.calls[0].stdin.written, [b"synthetic-key\n"])

    def test_tar_header_check_refuses_decryptable_non_tar_payload(self):
        popen = make_popen(stdout_bytes=b"x" * 1024)
        with patch.object(native_gpg.subprocess, "Popen", popen):
            with self.assertRaises(native_gpg.GpgProbeError) as caught:
                native_gpg.probe_gpg_decrypt(self.artifact, "synthetic-key",
                                             expect_tar=True)
        self.assertEqual(caught.exception.category, "invalid-tar-header")
        # The same payload passes a plain decrypt probe: the header rule
        # applies to file archives only, never to the database artifact.
        with patch.object(native_gpg.subprocess, "Popen", popen):
            native_gpg.probe_gpg_decrypt(self.artifact, "synthetic-key")

    def test_valid_tar_header_passes(self):
        popen = make_popen(stdout_bytes=tar_header_bytes() + b"payload")
        with patch.object(native_gpg.subprocess, "Popen", popen):
            native_gpg.probe_gpg_decrypt(self.artifact, "synthetic-key",
                                         expect_tar=True)


class BackupDecryptProbeTests(unittest.TestCase):
    def setUp(self):
        self.backup = load_module("group2_backup_under_test", PRODUCT / "backup.py")
        self.tmp = Path(tempfile.mkdtemp(prefix="group2-backup-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.artifact = self.tmp / "20261001-database-enc.sql.gz"
        self.artifact.write_bytes(b"synthetic encrypted database")
        self.key = "synthetic-backup-key"

    def _packet_run(self, return_value):
        return patch.object(self.backup, "probe_gpg_packets", return_value=return_value)

    def test_packet_check_alone_no_longer_suffices(self):
        packet = types.SimpleNamespace(returncode=0, stdout=b"gpg: :symkey enc packet:\n",
                                       stderr=b"")
        popen = make_popen(returncode=2, stderr_bytes=b"gpg: bad passphrase\n")
        with self._packet_run(packet):
            with patch.object(native_gpg.subprocess, "Popen", popen):
                with self.assertRaises(self.backup.BackupInputError) as caught:
                    self.backup._assert_gpg_encrypted(self.artifact, "database", self.key)
        self.assertEqual(caught.exception.safe_code, "gpg-database-decrypt-failed")
        self.assertEqual(caught.exception.safe_category, "bad-passphrase")
        self.assertNotIn(self.key, str(caught.exception))

    def test_decryptable_artifact_passes(self):
        packet = types.SimpleNamespace(returncode=0, stdout=b"gpg: :symkey enc packet:\n",
                                       stderr=b"")
        popen = make_popen(stdout_bytes=b"discarded plaintext")
        with self._packet_run(packet):
            with patch.object(native_gpg.subprocess, "Popen", popen):
                self.backup._assert_gpg_encrypted(self.artifact, "database", self.key)
        self.assertEqual(len(popen.calls), 1)


def _restore_site(tmp: Path, restore, site: str, backup_set: str):
    backup_dir = restore.SITES_DIR / site / "private" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for role, suffix in restore.BACKUP_SUFFIXES.items():
        path = backup_dir / f"{backup_set}{suffix}"
        path.write_bytes(f"synthetic {backup_set} {role}".encode())
        paths[role] = path
    return paths


@contextlib.contextmanager
def _null_transport(*args, **kwargs):
    yield


def _write_receipt(restore, backup_dir: Path, backup_set: str, *,
                   created_utc=None, artifacts=None):
    """Write a hash-bound backup receipt for a fixture set (test helper).

    Mirrors the receipt product/backup.py issues for a verified set, so
    the restore gate can be exercised without running a native backup.
    """
    paths = {role: backup_dir / f"{backup_set}{suffix}"
             for role, suffix in restore.BACKUP_SUFFIXES.items()}
    created = created_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if artifacts is None:
        hashes = restore._artifact_hashes(paths)
        artifacts = [{"role": role, "name": paths[role].name,
                      "sha256": hashes[role], "bytes": paths[role].stat().st_size}
                     for role in restore.BACKUP_SUFFIXES]
    receipt = {"schema_version": 2, "backup_set": backup_set,
               "created_utc": created, "encrypted": True, "verified": True,
               "artifacts": artifacts}
    from native_gpg import authenticate_backup_receipt
    authenticate_backup_receipt(receipt, "synthetic-key")
    (backup_dir / f"{backup_set}-receipt.json").write_text(
        json.dumps(receipt), encoding="utf-8")
    return receipt


class PreRestorePreservationTests(unittest.TestCase):
    """U-03: the preservation set is proven before any live mutation."""

    def setUp(self):
        self.restore = load_module("group2_restore_under_test", PRODUCT / "restore.py")
        self.tmp = Path(tempfile.mkdtemp(prefix="group2-prerestore-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.restore.SITES_DIR = self.tmp / "sites"
        self.site = "toeflhouse.localhost"
        self.restore.SITE_NAME = self.site
        self.restore.PRODUCTION_SITE = self.site
        self.state = self.tmp / "state"
        self.target_set = "20261028-target"
        self.current_set = "20261028-current"
        _restore_site(self.tmp, self.restore, self.site, self.target_set)
        self.pre_paths = _restore_site(self.tmp, self.restore, self.site, self.current_set)
        self.backup_dir = self.restore.SITES_DIR / self.site / "private" / "backups"
        # The pre-restore set carries a fresh, hash-bound receipt: the
        # restore gate trusts the receipt, never the files' mtimes.
        _write_receipt(self.restore, self.backup_dir, self.current_set)
        self.env = patch.dict(os.environ, {
            "RESTORE_STATE_DIR": str(self.state),
            "RESTORE_TRUST_STORE": str(self.tmp / "trust-store.json"),
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def _run_production(self, *, popen):
        receipt = self.backup_dir / f"{self.current_set}-receipt.json"
        digest = (hashlib.sha256(receipt.read_bytes()).hexdigest()
                  if receipt.exists() else "0" * 64)
        with patch.object(self.restore, "validate_emergency_authorization",
                          return_value=("a" * 32, [], digest)):
            with patch.object(native_gpg.subprocess, "Popen", popen):
                with patch.object(self.restore, "_run_native_restore") as native:
                    self.restore._native_restore(
                        self.site, self.target_set, "synthetic-key",
                        "synthetic-db-password", "synthetic-admin-password",
                        target="production",
                        pre_restore_backup_set=self.current_set,
                        authorization={}, signature_1=None, signature_2=None)
                    return native

    def test_wrong_key_pre_restore_set_is_refused_before_any_live_mutation(self):
        popen = make_popen(returncode=2, stderr_bytes=b"gpg: bad passphrase\n")
        with self.assertRaises(self.restore.RestoreInputError):
            self._run_production(popen=popen)
        state_dir = self.state / self.site
        # Single-use by design: a validated request stays spent even when
        # the preservation probe refuses it. But no marker, no audit
        # "started" record, and no native restore may follow a failed probe.
        self.assertTrue((state_dir / ("a" * 32 + ".json")).exists())
        self.assertFalse((state_dir / "in-progress.json").exists())
        self.assertFalse((state_dir / "audit.jsonl").exists())

    def test_fresh_mtime_with_stale_receipt_is_refused_before_any_mutation(self):
        # Group C refinement of the 24h recency gate: a fresh mtime proves
        # nothing when the receipt is stale — the receipt decides.
        stale = (NOW_UTC - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _write_receipt(self.restore, self.backup_dir, self.current_set,
                       created_utc=stale)
        popen = make_popen(stdout_bytes=tar_header_bytes())
        with self.assertRaises(self.restore.RestoreInputError) as caught:
            self._run_production(popen=popen)
        self.assertIn("stale", str(caught.exception))

    def test_missing_receipt_is_refused_before_any_mutation(self):
        (self.backup_dir / f"{self.current_set}-receipt.json").unlink()
        popen = make_popen(stdout_bytes=tar_header_bytes())
        with self.assertRaises(self.restore.RestoreInputError) as caught:
            self._run_production(popen=popen)
        self.assertIn("receipt", str(caught.exception))

    def test_old_mtime_with_fresh_receipt_reaches_native_restore(self):
        # The receipt decides, not the mtime: 25-hour-old files with a
        # fresh hash-bound receipt and a passing probe are accepted.
        stale = NOW_UTC - timedelta(hours=25)
        for path in self.pre_paths.values():
            os.utime(path, (stale.timestamp(), stale.timestamp()))
        popen = make_popen(stdout_bytes=tar_header_bytes())
        native = self._run_production(popen=popen)
        native.assert_called_once()
        self.assertEqual(len(popen.calls), 3)

    def test_fresh_decryptable_pre_restore_set_reaches_native_restore(self):
        popen = make_popen(stdout_bytes=tar_header_bytes())
        native = self._run_production(popen=popen)
        native.assert_called_once()
        self.assertEqual(len(popen.calls), 3)

    def test_non_tar_pre_restore_file_archive_is_refused(self):
        popen = make_popen(stdout_bytes=b"not a tar header" * 64)
        with self.assertRaises(self.restore.RestoreInputError):
            self._run_production(popen=popen)


class StagedRestoreProbeTests(unittest.TestCase):
    """U-05: staged artifacts are probed before native _restore(force=True)."""

    def setUp(self):
        self.restore = load_module("group2_restore_staged_under_test", PRODUCT / "restore.py")
        self.tmp = Path(tempfile.mkdtemp(prefix="group2-staged-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.restore.SITES_DIR = self.tmp / "sites"
        self.site = "toeflhouse-restore.localhost"
        self.backup_set = "20261008-test"
        _restore_site(self.tmp, self.restore, self.site, self.backup_set)
        self.calls = []

    def _run(self, *, popen):
        frappe = types.ModuleType("frappe")
        frappe.__path__ = []
        frappe.conf = types.SimpleNamespace(db_type="mariadb")
        frappe.init = lambda name, sites_path=".": None
        frappe.destroy = lambda: None
        frappe.utils = types.ModuleType("frappe.utils")
        frappe.utils.__path__ = []
        frappe.utils.execute_in_shell = lambda *a, **k: (b"", b"")
        commands = types.ModuleType("frappe.commands")
        commands.__path__ = []
        site_commands = types.ModuleType("frappe.commands.site")

        def native_restore(**kwargs):
            self.calls.append(kwargs)

        site_commands._restore = native_restore
        synchronization = types.ModuleType("frappe.utils.synchronization")

        @contextlib.contextmanager
        def filelock(name, timeout):
            yield

        synchronization.filelock = filelock
        modules = {
            "frappe": frappe,
            "frappe.commands": commands,
            "frappe.commands.site": site_commands,
            "frappe.utils": frappe.utils,
            "frappe.utils.synchronization": synchronization,
        }
        with patch.dict(sys.modules, modules):
            with patch.object(native_gpg.subprocess, "Popen", popen):
                with patch.object(self.restore, "safe_mariadb_credential_transport",
                                  _null_transport):
                    with patch.object(self.restore, "safe_gpg_transport", _null_transport):
                        # Use the actual verified backup bytes as the
                        # gate-time digest source; never bypass the mandatory
                        # post-stage content verification in restore.py.
                        source = self.restore.SITES_DIR / self.site / "private" / "backups"
                        hashes = self.restore._artifact_hashes({
                            role: source / (self.backup_set + suffix)
                            for role, suffix in self.restore.BACKUP_SUFFIXES.items()
                        })
                        self.restore._run_native_restore(
                            self.site, self.backup_set, "synthetic-key",
                            "synthetic-db-password", "synthetic-admin-password",
                            expected_hashes=hashes)

    def test_probe_failure_blocks_native_restore(self):
        popen = make_popen(returncode=2, stderr_bytes=b"gpg: bad passphrase\n")
        with self.assertRaises(self.restore.RestoreInputError):
            self._run(popen=popen)
        self.assertEqual(self.calls, [])

    def test_probe_success_reaches_native_restore_with_force(self):
        popen = make_popen(stdout_bytes=tar_header_bytes())
        self._run(popen=popen)
        self.assertEqual(len(self.calls), 1)
        self.assertIs(self.calls[0]["force"], True)
        self.assertEqual(len(popen.calls), 3)


class CensusHashCanonicalisationTests(unittest.TestCase):
    """Refinement of U-02: per-record identity, not counts + one sum.

    A migration that swaps amounts between two Fees rows keeps every count
    and the exact grand_total sum, so the old census passes it. The new
    per-row canonical hash must change when any hashed cell changes, must
    be stable under row reordering and under equivalent number spellings
    (100 vs 100.0 vs "100.00"), and must be deterministic.
    """

    def test_same_cells_in_any_order_hash_the_same(self):
        rows = [["FEE-1", "100.00", 1], ["FEE-2", "200.00", 1]]
        self.assertEqual(engine._census_digest(rows),
                         engine._census_digest(list(reversed(rows))))

    def test_equivalent_number_spellings_hash_the_same(self):
        numeric = frozenset({1, 2})  # grand_total and docstatus, not name
        self.assertEqual(engine._census_row_digest(
            ["FEE-1", "100.00", 1], numeric_columns=numeric),
            engine._census_row_digest(["FEE-1", 100, 1], numeric_columns=numeric))
        self.assertEqual(engine._census_row_digest(
            ["FEE-1", "100.00", 1], numeric_columns=numeric),
            engine._census_row_digest(["FEE-1", 100.0, 1], numeric_columns=numeric))

    def test_one_changed_cell_changes_the_digest(self):
        before = engine._census_digest([["FEE-1", "100.00", 1],
                                        ["FEE-2", "200.00", 1]])
        swapped = engine._census_digest([["FEE-1", "200.00", 1],
                                         ["FEE-2", "100.00", 1]])
        self.assertNotEqual(before, swapped)
        renamed = engine._census_digest([["FEE-9", "100.00", 1],
                                         ["FEE-2", "200.00", 1]])
        self.assertNotEqual(before, renamed)

    def test_numeric_looking_text_identifiers_do_not_collide(self):
        for left, right in (("007", "7"), ("1e2", "100"), (None, ""),
                            ("a\\x1fb", "a\\x1fbc")):
            self.assertNotEqual(engine._census_row_digest([left, "Alice"]),
                                engine._census_row_digest([right, "Alice"]))

    def test_declared_numeric_columns_still_normalise_decimal_wire_formats(self):
        positions = frozenset({1, 2})
        canonical = engine._census_row_digest(["FEE-007", "100.00", 1],
                                              numeric_columns=positions)
        self.assertEqual(canonical, engine._census_row_digest(
            ["FEE-007", 100, "1.0"], numeric_columns=positions))
        self.assertNotEqual(canonical, engine._census_row_digest(
            ["FEE-7", 100, "1"], numeric_columns=positions))
        with self.assertRaises(ValueError):
            engine._census_row_digest(["FEE-007", "broken", 1],
                                      numeric_columns=positions)

    def test_census_hashes_refuses_unreadable_answers(self):
        runner = engine.BenchRunner("bench", Path("/tmp"), timeout=60)

        def malformed(arguments, *, timeout=None):
            return types.SimpleNamespace(returncode=0, stdout="not a report\n")

        with patch.object(runner, "_run", side_effect=malformed):
            with self.assertRaises(engine.UpdateError):
                runner.census_hashes("toeflhouse.localhost")


class CensusAndFeesTotalTests(unittest.TestCase):
    def test_census_covers_fees_enrollments_applicants_and_th_masters(self):
        for doctype in ("Fees", "Program Enrollment", "Student Applicant",
                        "TH Billing Policy", "TH Program Level",
                        "TH Assessment Policy", "TH Discount Rule",
                        "TH Level Duration", "TH Enrollment Exit Policy",
                        "TH Correction Policy"):
            self.assertIn(doctype, engine.CENSUS_DOCTYPES)

    def test_fees_total_parses_and_refuses_unreadable_answers(self):
        runner = engine.BenchRunner("bench", Path("/tmp"), timeout=60)

        def ok(arguments, *, timeout=None):
            return types.SimpleNamespace(returncode=0, stdout='[["TH_CENSUS", "12345.67"]]\n')

        with patch.object(runner, "_run", side_effect=ok):
            self.assertEqual(runner.fees_total("toeflhouse.localhost"), "12345.67")

        def failing(arguments, *, timeout=None):
            return types.SimpleNamespace(returncode=1, stdout="")

        with patch.object(runner, "_run", side_effect=failing):
            with self.assertRaises(engine.UpdateError):
                runner.fees_total("toeflhouse.localhost")

        def malformed(arguments, *, timeout=None):
            return types.SimpleNamespace(returncode=0, stdout="not a report\n")

        with patch.object(runner, "_run", side_effect=malformed):
            with self.assertRaises(engine.UpdateError):
                runner.fees_total("toeflhouse.localhost")


class ApplyHarness:
    """Minimal ApplyTests-equivalent harness for Group 2 apply cases."""

    def __init__(self, tmp: Path, *, fixture_kwargs=None):
        self.tmp = tmp
        self.fixture = UpdateFixture(tmp / "fixture", **(fixture_kwargs or {}))
        observer = patch.object(engine, "_observe_host",
                                side_effect=self.fixture.live_observation)
        observer.start()
        self._observer = observer
        self.sites_dir = self.fixture.data / "sites"
        self.bench = tmp / "fake-bench.py"
        self.bench.write_text(FAKE_BENCH, encoding="utf-8")
        self.bench.chmod(0o755)
        self.state = {
            "migrate_calls": 0,
            "counts": {"Student": 12, "Student Group": 3, "Course": 4, "Program": 2,
                       "Sales Invoice": 20, "Payment Entry": 18, "Attendance": 200,
                       "Salary Slip": 5, "Employee": 6, "User": 4, "Role": 9,
                       "Fees": 7, "Program Enrollment": 11, "Student Applicant": 5,
                       "TH Billing Policy": 2, "TH Program Level": 6,
                       "TH Assessment Policy": 3, "TH Discount Rule": 4,
                       "TH Level Duration": 6, "TH Enrollment Exit Policy": 1,
                       "TH Correction Policy": 2},
            "fees_total": "12345.67",
            "apps": list(engine.REQUIRED_APPS),
            "pages": list(engine.ROLE_DESK_PAGES),
            "orphans": {"Sales Invoice Item": 0, "Payment Entry Reference": 0},
            "mutations": {},
        }
        self.state_path = tmp / "bench-state.json"
        self.log_path = tmp / "bench-log.jsonl"
        self.write_state()
        os.environ["TH_TEST_BENCH_STATE"] = str(self.state_path)
        os.environ["TH_TEST_BENCH_LOG"] = str(self.log_path)

    def cleanup(self):
        self._observer.stop()
        os.environ.pop("TH_TEST_BENCH_STATE", None)
        os.environ.pop("TH_TEST_BENCH_LOG", None)

    def write_state(self):
        self.state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def transaction(self):
        decision = self.fixture.preflight()
        if decision["decision"] != "allow":
            raise AssertionError(f"preflight refused: {decision['blockers']}")
        authorized = self.fixture.authorize(decision["transaction"])
        if authorized["decision"] != "allow":
            raise AssertionError(f"authorize refused: {authorized['blockers']}")
        return authorized["transaction"]

    def apply_request(self, transaction):
        return {
            "action": "apply",
            "site": engine.SITE_NAME,
            "product_root": str(self.fixture.product_root),
            "manifest": self.fixture.manifest_rel,
            "signature": self.fixture.signature_rel,
            "trust_store": self.fixture.trust_store_rel,
            "sites_dir": str(self.sites_dir),
            "bench": str(self.bench),
            "host_updater_version": "2026.10.24",
            "migrate_replays": 2,
            "command_timeout_seconds": 120,
            "transaction": transaction,
            "archive": str((self.fixture.staging / "toefl-house-erp-app.tar")
                           .relative_to(self.fixture.product_root)),
            "backup_receipt": self.fixture.receipt_rel,
            "backup_dir": str(self.fixture.backup_dir.relative_to(self.fixture.product_root)),
            "recovery_authorization": self.fixture.authorization_rel,
            "recovery_signature": self.fixture.authorization_signature_rel,
            "recovery_signature_2": self.fixture.authorization_signature_2_rel,
        }

    def apply(self, request):
        self.fixture.live_applying = True
        self.fixture.live_transaction_id = request["transaction"]["transaction_id"]
        try:
            return engine.apply_update(request, now=NOW, state_dir=self.fixture.state_dir)
        finally:
            self.fixture.live_applying = False


class ApplyGroup2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="group2-apply-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def _harness(self, **kwargs):
        harness = ApplyHarness(self.tmp, **kwargs)
        self.addCleanup(harness.cleanup)
        return harness

    @staticmethod
    def _codes(report):
        return {item["code"] for item in report["blockers"]}

    def test_fees_count_loss_fails_the_update(self):
        harness = self._harness()
        harness.state["mutations"] = {"Fees": -1}
        harness.write_state()
        report = harness.apply(harness.apply_request(harness.transaction()))
        self.assertEqual(report["status"], "failed")
        self.assertIn("apply.records_lost", self._codes(report))

    def test_swapped_fees_amounts_pass_old_checks_but_fail_the_per_record_hash(self):
        # Refinement of U-02. Two Fees rows swap grand_total (100 <-> 200):
        # the count is unchanged and the exact sum is unchanged, so the old
        # census (counts + Fees.grand_total sum) passes. The per-row
        # canonical hash must refuse the migration anyway.
        # Explicit rows use the engine's Fees column order:
        # name, student, program_enrollment, grand_total,
        # outstanding_amount, posting_date, docstatus.
        harness = self._harness()
        harness.state["rows"] = {"Fees": [
            ["FEE-001", "STU-1", "PE-1", "100.00", "100.00", "2026-09-01", 1],
            ["FEE-002", "STU-2", "PE-2", "200.00", "200.00", "2026-09-01", 1],
        ]}
        harness.state["row_swaps"] = [{"doctype": "Fees", "column": 3,
                                       "a": "FEE-001", "b": "FEE-002"}]
        harness.write_state()
        report = harness.apply(harness.apply_request(harness.transaction()))
        # The old checks are blind to the swap: same count, same sum.
        self.assertEqual(report["counts_before"]["Fees"],
                         report["counts_after"]["Fees"])
        self.assertEqual(report["fees_total_before"], report["fees_total_after"])
        # The new per-record check refuses it.
        self.assertEqual(report["status"], "failed")
        self.assertIn("apply.records_lost", self._codes(report))
        self.assertNotEqual(report["census_hashes_before"]["Fees"],
                            report["census_hashes_after"]["Fees"])

    def test_fees_sum_change_fails_the_update(self):
        harness = self._harness()
        harness.state["fees_total_delta"] = "-0.01"
        harness.write_state()
        report = harness.apply(harness.apply_request(harness.transaction()))
        self.assertEqual(report["status"], "failed")
        self.assertIn("apply.records_lost", self._codes(report))
        self.assertEqual(report["fees_total_before"], "12345.67")
        # Migrate replays twice, so the -0.01 delta applies twice.
        self.assertEqual(report["fees_total_after"], "12345.65")

    def test_new_census_doctypes_and_fees_sum_survive_a_clean_apply(self):
        harness = self._harness()
        report = harness.apply(harness.apply_request(harness.transaction()))
        self.assertEqual(report["status"], "succeeded", report["blockers"])
        self.assertEqual(report["counts_after"]["Fees"], 7)
        self.assertEqual(report["counts_after"]["Program Enrollment"], 11)
        self.assertEqual(report["counts_after"]["Student Applicant"], 5)
        self.assertEqual(report["counts_after"]["TH Billing Policy"], 2)
        self.assertEqual(report["fees_total_before"], "12345.67")
        self.assertEqual(report["fees_total_after"], "12345.67")
        self.assertEqual(report["census_hashes_before"], report["census_hashes_after"])
        for doctype in engine.CENSUS_DOCTYPES:
            self.assertRegex(report["census_hashes_before"][doctype], r"^[0-9a-f]{64}$")

    def test_apply_without_backup_dir_uses_the_site_backup_folder(self):
        harness = self._harness()
        request = harness.apply_request(harness.transaction())
        del request["backup_dir"]
        report = harness.apply(request)
        self.assertEqual(report["status"], "succeeded", report["blockers"])

    def test_no_backup_no_recovery_release_applies(self):
        harness = self._harness(fixture_kwargs={"migration": "none", "reversible": True,
                                                "recovery_required": False})
        fixture = harness.fixture
        requirements = {**fixture.manifest["requirements"],
                        "backup": {"required": False, "max_age_hours": 24,
                                   "require_restore_verification": False},
                        "recovery_authorization": {"required": False, "max_age_hours": 168}}
        database = {**fixture.manifest["database"], "migration": "none",
                    "reversible": True, "requires_verified_backup": False}
        fixture.manifest = fixture.build_manifest(requirements=requirements,
                                                  database=database)
        fixture.manifest_rel, fixture.signature_rel = fixture.write_signed_manifest(
            fixture.manifest, "update")
        transaction = harness.transaction()
        self.assertIsNone(transaction["evidence"]["backup_receipt_sha256"])
        self.assertIsNone(transaction["evidence"]["recovery_authorization_sha256"])
        request = harness.apply_request(transaction)
        request["backup_receipt"] = ""
        request["recovery_authorization"] = ""
        request["recovery_signature"] = ""
        request["recovery_signature_2"] = ""
        del request["backup_dir"]
        report = harness.apply(request)
        self.assertEqual(report["status"], "succeeded", report["blockers"])

    def test_tampered_receipt_is_still_refused_when_evidence_exists(self):
        harness = self._harness()
        transaction = harness.transaction()
        receipt = harness.fixture.product_root / harness.fixture.receipt_rel
        receipt.write_bytes(receipt.read_bytes() + b" ")
        report = harness.apply(harness.apply_request(transaction))
        self.assertEqual(report["status"], "failed")
        self.assertIn("apply.evidence_mismatch", self._codes(report))


if __name__ == "__main__":
    unittest.main()

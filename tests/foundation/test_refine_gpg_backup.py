"""Group C refinement tests: GPG verification hardening + backup safety.

Covers, with stubs, fake gpg binaries on PATH, and real gpg only with
synthetic passphrases and synthetic data (never a real key or backup):

* GPG probe failure injection: hanging gpg (must time out and refuse),
  huge/endless output (must be capped and refused, not OOM or hang),
  killed process (non-zero exit => refused), corrupt ciphertext
  (refused), stderr flood (must not deadlock), and no partial plaintext
  left behind on any failure path (the probe creates no file).
* Transport / list-packets timeouts: a hung child refuses, never hangs.
* POSIX child resource limits: CPU/memory caps applied where safe.
* Backup receipts: backup.py issues a hash-bound receipt; restore.py
  validates it and trusts it — never a filesystem mtime — for
  freshness. Fresh mtime + stale/corrupt receipt => refused; old mtime
  + valid fresh receipt => accepted. The mtime freshness decision is
  gone (pinned by assertion).
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))
sys.path.insert(0, str(ROOT / "tests" / "foundation"))

import native_gpg  # noqa: E402

NOW_UTC = datetime.now(timezone.utc)
GPG = shutil.which("gpg")


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


class RecordingPopen:
    """Popen stand-in recording argv/kwargs; configurable exit/output."""

    def __init__(self, arguments, **kwargs):
        self.arguments = list(arguments)
        self.kwargs = dict(kwargs)
        self.thread_count_at_spawn = threading.active_count()
        self.stdin = FakeDecryptStdin()
        self.stdout = io.BytesIO(getattr(self, "stdout_bytes", b""))
        self.stderr = io.BytesIO(getattr(self, "stderr_bytes", b""))
        self.returncode = getattr(self, "returncode_value", 0)

    def wait(self) -> int:
        return self.returncode


def make_recording_popen(*, returncode=0, stdout_bytes=b"", stderr_bytes=b""):
    class _Popen(RecordingPopen):
        pass

    # Class bodies cannot see the enclosing function's locals, so the
    # per-case values are attached as class attributes after creation.
    _Popen.stdout_bytes = stdout_bytes
    _Popen.stderr_bytes = stderr_bytes
    _Popen.returncode_value = returncode

    calls = []
    orig_init = _Popen.__init__

    def _init(self, arguments, **kwargs):
        orig_init(self, arguments, **kwargs)
        calls.append(self)

    _Popen.__init__ = _init
    _Popen.calls = calls
    return _Popen


class HangingPopen:
    """A child that never exits until killed (failure injection)."""

    def __init__(self, arguments, **kwargs):
        self.arguments = list(arguments)
        self.kwargs = dict(kwargs)
        self.stdin = FakeDecryptStdin()
        self.stdout = io.BytesIO(b"")
        self.stderr = io.BytesIO(b"")
        self._done = threading.Event()
        self.killed = False
        self.kill_calls = 0

    def wait(self) -> int:
        self._done.wait()
        return 0

    def kill(self) -> None:
        self.kill_calls += 1
        self.killed = True
        self._done.set()


class _EndlessStdout:
    def read(self, size=-1):
        return b"x" * (size if size and size > 0 else 65536)


class EndlessOutputPopen(HangingPopen):
    """A child streaming endless plaintext until killed."""

    def __init__(self, arguments, **kwargs):
        super().__init__(arguments, **kwargs)
        self.stdout = _EndlessStdout()


def make_fake_gpg_script(directory: Path, body: str) -> Path:
    path = directory / "gpg"
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


class ProbeFailureInjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="refine-gpg-probe-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.artifact = self.tmp / "artifact-enc"
        self.artifact.write_bytes(b"synthetic encrypted artifact")

    def test_hanging_gpg_times_out_and_is_refused(self):
        start = time.monotonic()
        with patch.object(native_gpg.subprocess, "Popen", HangingPopen):
            with self.assertRaises(native_gpg.GpgProbeError) as caught:
                native_gpg.probe_gpg_decrypt(self.artifact, "synthetic-key",
                                             timeout=2)
        elapsed = time.monotonic() - start
        self.assertEqual(caught.exception.category, "probe-timeout")
        self.assertLess(elapsed, 10)
        self.assertEqual(list(self.tmp.iterdir()), [self.artifact])

    def test_hanging_gpg_is_killed(self):
        calls = []

        class _Popen(HangingPopen):
            def __init__(self, arguments, **kwargs):
                super().__init__(arguments, **kwargs)
                calls.append(self)

        with patch.object(native_gpg.subprocess, "Popen", _Popen):
            with self.assertRaises(native_gpg.GpgProbeError):
                native_gpg.probe_gpg_decrypt(self.artifact, "synthetic-key",
                                             timeout=2)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].killed)
        self.assertGreaterEqual(calls[0].kill_calls, 1)

    def test_endless_output_is_capped_and_refused(self):
        start = time.monotonic()
        with patch.object(native_gpg.subprocess, "Popen", EndlessOutputPopen):
            with self.assertRaises(native_gpg.GpgProbeError) as caught:
                native_gpg.probe_gpg_decrypt(
                    self.artifact, "synthetic-key", timeout=30,
                    max_plaintext_bytes=1024 * 1024)
        elapsed = time.monotonic() - start
        self.assertEqual(caught.exception.category, "output-limit-exceeded")
        self.assertLess(elapsed, 10)
        self.assertEqual(list(self.tmp.iterdir()), [self.artifact])

    def test_fast_exiting_child_cannot_bypass_output_limit(self):
        # The waiter can finish before the stdout reader sees overflow.
        # A successful exit code must never overrule the final drain cap.
        popen = make_recording_popen(
            returncode=0, stdout_bytes=b"plaintext" * 512)
        with patch.object(native_gpg.subprocess, "Popen", popen):
            with self.assertRaises(native_gpg.GpgProbeError) as caught:
                native_gpg.probe_gpg_decrypt(
                    self.artifact, "synthetic-key",
                    max_plaintext_bytes=1024)
        self.assertEqual(caught.exception.category, "output-limit-exceeded")

    def test_nonfinite_timeouts_are_rejected_without_starting_child(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=str(bad)):
                with patch.object(native_gpg.subprocess, "Popen") as child:
                    with self.assertRaises(native_gpg.GpgProbeError):
                        native_gpg.probe_gpg_decrypt(
                            self.artifact, "synthetic-key", timeout=bad)
                child.assert_not_called()

    def test_adaptive_gpg_budget_supports_large_backup_without_unbounded_io(self):
        gib = 1024 ** 3
        seconds, cap = native_gpg.probe_budget_for_encrypted_size(
            40 * gib)
        self.assertGreater(seconds, native_gpg.PROBE_TIMEOUT_SECONDS)
        self.assertLessEqual(
            seconds, native_gpg.PROBE_MAX_ADAPTIVE_TIMEOUT_SECONDS)
        self.assertGreater(cap, native_gpg.PROBE_MAX_PLAINTEXT_BYTES)
        self.assertLessEqual(
            cap, native_gpg.PROBE_MAX_ADAPTIVE_PLAINTEXT_BYTES)
        # Malformed sizes do not trigger probing at all.
        for bad in (0, -1, True, "40"):
            with self.subTest(size=bad), self.assertRaises(ValueError):
                native_gpg.probe_budget_for_encrypted_size(bad)

    def test_packet_probe_captures_metadata_without_argv_secret(self):
        popen = make_recording_popen(
            stdout_bytes=b"gpg: :symkey enc packet:\n",
            stderr_bytes=b"safe diagnostic")
        with patch.object(native_gpg.subprocess, "Popen", popen):
            result = native_gpg.probe_gpg_packets(
                self.artifact, "synthetic-key", timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b":symkey enc packet:", result.stdout)
        self.assertNotIn("synthetic-key", " ".join(popen.calls[0].arguments))
        self.assertEqual(popen.calls[0].stdin.written, [b"synthetic-key\n"])

    def test_packet_probe_refuses_fast_exit_oversize(self):
        packet_flood = b"x" * (native_gpg.GPG_PACKET_STDOUT_MAX_BYTES + 1)
        popen = make_recording_popen(stdout_bytes=packet_flood)
        with patch.object(native_gpg.subprocess, "Popen", popen):
            with self.assertRaises(native_gpg.GpgProbeError) as caught:
                native_gpg.probe_gpg_packets(
                    self.artifact, "synthetic-key", timeout=5)
        self.assertEqual(caught.exception.category, "output-limit-exceeded")

    def test_packet_probe_refuses_and_kills_hanging_child(self):
        with patch.object(native_gpg.subprocess, "Popen", HangingPopen):
            with self.assertRaises(native_gpg.GpgProbeError) as caught:
                native_gpg.probe_gpg_packets(
                    self.artifact, "synthetic-key", timeout=1)
        self.assertEqual(caught.exception.category, "probe-timeout")

    def test_killed_process_is_refused(self):
        popen = make_recording_popen(returncode=-9)
        with patch.object(native_gpg.subprocess, "Popen", popen):
            with self.assertRaises(native_gpg.GpgProbeError) as caught:
                native_gpg.probe_gpg_decrypt(self.artifact, "synthetic-key")
        self.assertEqual(caught.exception.category, "unclassified")
        popen = make_recording_popen(returncode=1,
                                     stderr_bytes=b"gpg: bad passphrase\n")
        with patch.object(native_gpg.subprocess, "Popen", popen):
            with self.assertRaises(native_gpg.GpgProbeError) as caught:
                native_gpg.probe_gpg_decrypt(self.artifact, "synthetic-key")
        self.assertEqual(caught.exception.category, "bad-passphrase")

    def test_corrupt_ciphertext_is_refused(self):
        popen = make_recording_popen(
            returncode=2, stderr_bytes=b"gpg: no valid OpenPGP data found\n")
        with patch.object(native_gpg.subprocess, "Popen", popen):
            with self.assertRaises(native_gpg.GpgProbeError) as caught:
                native_gpg.probe_gpg_decrypt(self.artifact, "synthetic-key")
        self.assertEqual(caught.exception.category, "no-valid-openpgp-data")

    def test_probe_spawns_its_own_session_with_limits_where_safe(self):
        popen = make_recording_popen(stdout_bytes=tar_header_bytes())
        with patch.object(native_gpg.subprocess, "Popen", popen):
            native_gpg.probe_gpg_decrypt(self.artifact, "synthetic-key",
                                         expect_tar=True)
        self.assertEqual(len(popen.calls), 1)
        self.assertIs(popen.calls[0].kwargs.get("start_new_session"), True)
        if popen.calls[0].thread_count_at_spawn == 1:
            self.assertIn("preexec_fn", popen.calls[0].kwargs)

    @unittest.skipUnless(os.name == "posix" and native_gpg.resource is not None,
                         "POSIX resource limits only")
    def test_child_limits_set_cpu_and_memory_caps(self):
        code = (
            "import resource, sys; sys.path.insert(0, %r); "
            "import native_gpg; native_gpg._gpg_child_limits(); "
            "print(resource.getrlimit(resource.RLIMIT_CPU)); "
            "print(resource.getrlimit(resource.RLIMIT_AS))" % str(PRODUCT)
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        cpu, memory = result.stdout.strip().splitlines()
        self.assertEqual(cpu, "(1800, 1800)")
        self.assertEqual(memory, "(536870912, 536870912)")


class ProbeRealChildTests(unittest.TestCase):
    """The same failure modes against real child processes via PATH fakes.

    The old probe deadlocked on the stderr-flood script (it drained
    stdout first while the child blocked on a full stderr pipe) and hung
    forever on the sleeping script; both must now return promptly.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="refine-gpg-real-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.bin_dir = self.tmp / "bin"
        self.bin_dir.mkdir()
        self.artifact = self.tmp / "artifact-enc"
        self.artifact.write_bytes(b"synthetic encrypted artifact")
        self.env = patch.dict(os.environ, {
            "PATH": str(self.bin_dir) + os.pathsep + os.environ.get("PATH", ""),
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def assert_child_pipes_closed(self, operation):
        real_popen = subprocess.Popen
        children = []

        def tracked_popen(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            return child

        try:
            with patch.object(native_gpg.subprocess, "Popen", side_effect=tracked_popen):
                return operation()
        finally:
            self.assertTrue(children, "the probe did not spawn its expected child")
            for child in children:
                if child.poll() is None:
                    native_gpg._terminate_process(child)
                    child.wait(timeout=5)
                for stream_name in ("stdin", "stdout", "stderr"):
                    stream = getattr(child, stream_name)
                    self.assertTrue(stream.closed, f"child {stream_name} pipe leaked")

    def test_stderr_flood_does_not_deadlock(self):
        make_fake_gpg_script(
            self.bin_dir,
            "head -c 204800 /dev/zero >&2\n"
            "printf 'plain-decrypted-bytes'\n"
            "exit 0\n")
        start = time.monotonic()
        self.assert_child_pipes_closed(
            lambda: native_gpg.probe_gpg_decrypt(
                self.artifact, "synthetic-key", timeout=10))
        self.assertLess(time.monotonic() - start, 10)

    def test_hanging_real_gpg_times_out_and_is_refused(self):
        make_fake_gpg_script(self.bin_dir, "sleep 30\n")
        start = time.monotonic()
        with self.assertRaises(native_gpg.GpgProbeError) as caught:
            self.assert_child_pipes_closed(
                lambda: native_gpg.probe_gpg_decrypt(
                    self.artifact, "synthetic-key", timeout=2))
        self.assertEqual(caught.exception.category, "probe-timeout")
        self.assertLess(time.monotonic() - start, 10)

    def test_endless_real_output_is_capped_and_refused(self):
        make_fake_gpg_script(self.bin_dir, "yes 'decrypted-plaintext-line'\n")
        start = time.monotonic()
        with self.assertRaises(native_gpg.GpgProbeError) as caught:
            self.assert_child_pipes_closed(
                lambda: native_gpg.probe_gpg_decrypt(
                    self.artifact, "synthetic-key", timeout=30,
                    max_plaintext_bytes=1024 * 1024))
        self.assertEqual(caught.exception.category, "output-limit-exceeded")
        self.assertLess(time.monotonic() - start, 10)

    def test_packet_probe_closes_child_pipes(self):
        make_fake_gpg_script(
            self.bin_dir,
            "printf 'gpg: :symkey enc packet:\\n'\n"
            "exit 0\n")
        result = self.assert_child_pipes_closed(
            lambda: native_gpg.probe_gpg_packets(
                self.artifact, "synthetic-key", timeout=10))
        self.assertEqual(result.returncode, 0)
        self.assertIn(b":symkey enc packet:", result.stdout)


@unittest.skipUnless(GPG is not None, "real gpg binary is required")
class ProbeRealGpgTests(unittest.TestCase):
    """End-to-end probe against the real gpg binary, synthetic data only."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="refine-gpg-real-gpg-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.plain = self.tmp / "plain.txt"
        self.plain.write_bytes(b"synthetic backup plaintext " * 100)
        self.cipher = self.tmp / "plain.txt.gpg"
        gnupg_home = self.tmp / "gnupg"
        gnupg_home.mkdir(mode=0o700)
        env = {**os.environ, "GNUPGHOME": str(gnupg_home),
               "HOME": str(self.tmp)}
        result = subprocess.run(
            ["gpg", "--batch", "--yes", "--passphrase-fd", "0",
             "--pinentry-mode", "loopback", "-c",
             "-o", str(self.cipher), str(self.plain)],
            input=b"synthetic-key\n", capture_output=True, timeout=60, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_gpg_round_trip_passes_and_wrong_key_is_refused(self):
        native_gpg.probe_gpg_decrypt(self.cipher, "synthetic-key")
        with self.assertRaises(native_gpg.GpgProbeError):
            native_gpg.probe_gpg_decrypt(self.cipher, "wrong-key")

    def test_real_gpg_packet_listing_validates_a_synthetic_ciphertext(self):
        # Prove that the bounded replacement produces the exact packet
        # marker the native backup verifier relies on, using real GPG and
        # generated disposable ciphertext (no customer data or secrets).
        packet = native_gpg.probe_gpg_packets(
            self.cipher, "synthetic-key", timeout=15)
        self.assertEqual(packet.returncode, 0, packet.stderr)
        self.assertIn(b":symkey enc packet:", packet.stdout + packet.stderr)
        self.assertLessEqual(
            len(packet.stdout), native_gpg.GPG_PACKET_STDOUT_MAX_BYTES)
        self.assertLessEqual(
            len(packet.stderr), native_gpg.GPG_PACKET_STDERR_MAX_BYTES)

    def test_real_gpg_corrupt_ciphertext_is_refused(self):
        data = bytearray(self.cipher.read_bytes())
        data[len(data) // 2] ^= 0xFF
        corrupt = self.tmp / "corrupt.gpg"
        corrupt.write_bytes(bytes(data))
        with self.assertRaises(native_gpg.GpgProbeError):
            native_gpg.probe_gpg_decrypt(corrupt, "synthetic-key")


class TransportTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.key = "synthetic-key"
        self.utils = type("Utils", (), {})()
        self.frappe = type("Frappe", (), {"utils": self.utils})()
        self.calls = []

        def original_execute(command, verbose=False, low_priority=False,
                             check_exit_code=False):
            return b"native stderr", b"native stdout"

        self.utils.execute_in_shell = original_execute

    def _command(self):
        return (f"gpg --yes --passphrase {self.key} --pinentry-mode loopback "
                "-c /tmp/native-file")

    def test_transport_passes_a_timeout_to_the_child(self):
        def fake_run(arguments, **kwargs):
            self.calls.append((arguments, kwargs))
            return type("Result", (), {"returncode": 0, "stdout": b"",
                                       "stderr": b""})()

        with patch.object(native_gpg.subprocess, "run", side_effect=fake_run):
            with native_gpg.safe_gpg_transport(self.frappe, self.key):
                self.utils.execute_in_shell(self._command())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][1]["timeout"],
                         native_gpg.GPG_TRANSPORT_TIMEOUT_SECONDS)
        self.assertIs(self.calls[0][1].get("start_new_session"), True)

    def test_transport_timeout_is_a_fail_closed_refusal(self):
        def hanging_run(arguments, **kwargs):
            raise subprocess.TimeoutExpired(cmd=arguments, timeout=kwargs["timeout"])

        with patch.object(native_gpg.subprocess, "run", side_effect=hanging_run):
            with native_gpg.safe_gpg_transport(self.frappe, self.key):
                with self.assertRaises(RuntimeError) as caught:
                    self.utils.execute_in_shell(self._command())
        self.assertIn("sensitive diagnostics were withheld", str(caught.exception))
        self.assertNotIn(self.key, str(caught.exception))


class ListPacketsTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.backup = load_module("refine_backup_under_test", PRODUCT / "backup.py")
        self.tmp = Path(tempfile.mkdtemp(prefix="refine-list-packets-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.artifact = self.tmp / "artifact-enc"
        self.artifact.write_bytes(b"synthetic encrypted artifact")

    def test_list_packets_uses_bounded_size_scaled_timeout(self):
        calls = []
        def fake_run(*args, **kwargs):
            calls.append(kwargs)
            return type("Result", (), {
                "returncode": 0,
                "stdout": b":symkey enc packet:\\n",
                "stderr": b"",
            })()
        # No 40 GiB artifact is allocated: simulate its disk size at the
        # boundary only, while recording the actual GPG process timeout.
        original_stat = Path.stat
        def large_stat(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if path == self.artifact:
                return type("Stat", (), {"st_size": 40 * 1024 ** 3})()
            return result
        with patch.object(self.backup, "probe_gpg_packets", side_effect=fake_run):
            with patch.object(Path, "stat", large_stat):
                with patch.object(self.backup, "probe_gpg_decrypt"):
                    self.backup._assert_gpg_encrypted(
                        self.artifact, "database", "synthetic-key")
        self.assertEqual(len(calls), 1)
        self.assertGreater(calls[0]["timeout"], 120)
        self.assertLessEqual(calls[0]["timeout"], 1800)

    def test_packet_output_overflow_refuses_backup(self):
        with patch.object(
                self.backup, "probe_gpg_packets",
                side_effect=native_gpg.GpgProbeError("output-limit-exceeded")):
            with self.assertRaises(self.backup.BackupInputError) as caught:
                self.backup._assert_gpg_encrypted(
                    self.artifact, "database", "synthetic-key")
        self.assertEqual(caught.exception.safe_code, "gpg-database-probe-error")
        self.assertEqual(caught.exception.safe_category, "output-limit-exceeded")

    def test_list_packets_timeout_is_a_fail_closed_refusal(self):
        def hanging_run(*args, **kwargs):
            raise native_gpg.GpgProbeError("probe-timeout")

        with patch.object(self.backup, "probe_gpg_packets", side_effect=hanging_run):
            with self.assertRaises(self.backup.BackupInputError) as caught:
                self.backup._assert_gpg_encrypted(
                    self.artifact, "database", "synthetic-key")
        self.assertEqual(caught.exception.safe_code, "gpg-database-probe-timeout")
        self.assertEqual(caught.exception.safe_category, "probe-timeout")


def _restore_site(restore, sites_dir: Path, site: str, backup_set: str):
    backup_dir = sites_dir / site / "private" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for role, suffix in restore.BACKUP_SUFFIXES.items():
        path = backup_dir / f"{backup_set}{suffix}"
        path.write_bytes(f"synthetic {backup_set} {role}".encode())
        paths[role] = path
    return paths


class BackupReceiptTests(unittest.TestCase):
    """Receipt issuance (backup.py) and validation (restore.py) agree."""

    def setUp(self):
        self.backup = load_module("refine_backup_receipt_under_test",
                                  PRODUCT / "backup.py")
        self.restore = load_module("refine_restore_receipt_under_test",
                                   PRODUCT / "restore.py")
        self.tmp = Path(tempfile.mkdtemp(prefix="refine-receipt-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.sites = self.tmp / "sites"
        self.site = "toeflhouse.localhost"
        self.backup_set = "20261105-000000-test"
        self.backup_key = "synthetic-backup-key-for-receipt-tests"
        self.paths = _restore_site(self.restore, self.sites, self.site,
                                   self.backup_set)
        self.backup_dir = self.paths["database"].parent

    def test_receipt_constants_agree_across_modules(self):
        self.assertEqual(self.backup.BACKUP_RECEIPT_SUFFIX,
                         self.restore.BACKUP_RECEIPT_SUFFIX)
        self.assertEqual(self.backup.BACKUP_RECEIPT_SCHEMA_VERSION,
                         self.restore.BACKUP_RECEIPT_SCHEMA_VERSION)
        self.assertEqual(self.backup.BACKUP_RECEIPT_MAX_BYTES,
                         self.restore.BACKUP_RECEIPT_MAX_BYTES)

    def test_issued_receipt_validates(self):
        self.backup.issue_backup_receipt(self.backup_dir, self.backup_set,
                                         self.paths, self.backup_key)
        receipt, _ = self.restore._validate_pre_restore_receipt(
            self.paths, self.backup_set, self.backup_key)
        self.assertEqual(receipt["backup_set"], self.backup_set)
        self.assertTrue(receipt["encrypted"] and receipt["verified"])

    def test_receipt_refuses_wrong_backup_secret(self):
        self.backup.issue_backup_receipt(self.backup_dir, self.backup_set,
                                         self.paths, self.backup_key)
        with self.assertRaises(self.restore.RestoreInputError) as caught:
            self.restore._validate_pre_restore_receipt(
                self.paths, self.backup_set, "different-synthetic-key")
        self.assertIn("authenticity", str(caught.exception))

    def test_receipt_metadata_tampering_invalidates_authenticator(self):
        path = self.backup.issue_backup_receipt(
            self.backup_dir, self.backup_set, self.paths, self.backup_key)
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["created_utc"] = "2026-11-08T00:00:00Z"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaises(self.restore.RestoreInputError) as caught:
            self.restore._validate_pre_restore_receipt(
                self.paths, self.backup_set, self.backup_key)
        self.assertIn("authenticity", str(caught.exception))

    def test_unsigned_legacy_receipt_is_not_accepted_for_recovery(self):
        receipt = self._write_receipt()
        receipt.pop("authentication")
        (self.backup_dir / f"{self.backup_set}-receipt.json").write_text(
            json.dumps(receipt), encoding="utf-8")
        with self.assertRaises(self.restore.RestoreInputError) as caught:
            self.restore._validate_pre_restore_receipt(
                self.paths, self.backup_set, self.backup_key)
        self.assertIn("authenticity", str(caught.exception))

    def test_duplicate_json_keys_are_refused(self):
        path = self.backup_dir / f"{self.backup_set}-receipt.json"
        path.write_text('{"schema_version":2,"schema_version":2}',
                        encoding="utf-8")
        with self.assertRaises(self.restore.RestoreInputError):
            self.restore._validate_pre_restore_receipt(
                self.paths, self.backup_set, self.backup_key)

    def test_receipt_refuses_overwrite(self):
        self.backup.issue_backup_receipt(self.backup_dir, self.backup_set,
                                         self.paths, self.backup_key)
        with self.assertRaises(self.backup.BackupInputError):
            self.backup.issue_backup_receipt(self.backup_dir, self.backup_set,
                                             self.paths, self.backup_key)

    def _write_receipt(self, *, created_utc=None, artifacts=None,
                       encrypted=True, verified=True, backup_set=None):
        created = created_utc or NOW_UTC.strftime("%Y-%m-%dT%H:%M:%SZ")
        if artifacts is None:
            hashes = self.restore._artifact_hashes(self.paths)
            artifacts = [{"role": role, "name": self.paths[role].name,
                          "sha256": hashes[role],
                          "bytes": self.paths[role].stat().st_size}
                         for role in self.restore.BACKUP_SUFFIXES]
        receipt = {"schema_version": self.backup.BACKUP_RECEIPT_SCHEMA_VERSION,
                   "backup_set": backup_set or self.backup_set,
                   "created_utc": created, "encrypted": encrypted,
                   "verified": verified, "artifacts": artifacts}
        self.backup.authenticate_backup_receipt(receipt, self.backup_key)
        (self.backup_dir / f"{self.backup_set}-receipt.json").write_text(
            json.dumps(receipt), encoding="utf-8")
        return receipt

    def test_fresh_mtime_with_stale_receipt_is_refused(self):
        stale = (NOW_UTC - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_receipt(created_utc=stale)
        with self.assertRaises(self.restore.RestoreInputError) as caught:
            self.restore._validate_pre_restore_receipt(
                self.paths, self.backup_set, self.backup_key)
        self.assertIn("stale", str(caught.exception))

    def test_old_mtime_with_fresh_receipt_is_accepted(self):
        self._write_receipt()
        stale = NOW_UTC - timedelta(hours=25)
        for path in self.paths.values():
            os.utime(path, (stale.timestamp(), stale.timestamp()))
        receipt, _ = self.restore._validate_pre_restore_receipt(
            self.paths, self.backup_set, self.backup_key)
        self.assertEqual(receipt["backup_set"], self.backup_set)

    def test_missing_receipt_is_refused(self):
        with self.assertRaises(self.restore.RestoreInputError) as caught:
            self.restore._validate_pre_restore_receipt(
                self.paths, self.backup_set, self.backup_key)
        self.assertIn("receipt", str(caught.exception))

    def test_corrupt_receipt_is_refused(self):
        (self.backup_dir / f"{self.backup_set}-receipt.json").write_text(
            "{not json", encoding="utf-8")
        with self.assertRaises(self.restore.RestoreInputError):
            self.restore._validate_pre_restore_receipt(
                self.paths, self.backup_set, self.backup_key)

    def test_tampered_artifact_hash_is_refused(self):
        hashes = self.restore._artifact_hashes(self.paths)
        artifacts = [{"role": role, "name": self.paths[role].name,
                      "sha256": hashes[role],
                      "bytes": self.paths[role].stat().st_size}
                     for role in self.restore.BACKUP_SUFFIXES]
        artifacts[0]["sha256"] = "0" * 64
        self._write_receipt(artifacts=artifacts)
        with self.assertRaises(self.restore.RestoreInputError) as caught:
            self.restore._validate_pre_restore_receipt(
                self.paths, self.backup_set, self.backup_key)
        self.assertIn("changed after receipt", str(caught.exception))

    def test_changed_artifact_after_receipt_is_refused(self):
        self._write_receipt()
        self.paths["database"].write_bytes(b"tampered bytes, different size")
        with self.assertRaises(self.restore.RestoreInputError) as caught:
            self.restore._validate_pre_restore_receipt(
                self.paths, self.backup_set, self.backup_key)
        self.assertIn("changed after receipt", str(caught.exception))

    def test_receipt_for_another_set_is_refused(self):
        self._write_receipt(backup_set="20261104-000000-other")
        with self.assertRaises(self.restore.RestoreInputError):
            self.restore._validate_pre_restore_receipt(
                self.paths, self.backup_set, self.backup_key)

    def test_future_receipt_is_refused(self):
        future = (NOW_UTC + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_receipt(created_utc=future)
        with self.assertRaises(self.restore.RestoreInputError):
            self.restore._validate_pre_restore_receipt(
                self.paths, self.backup_set, self.backup_key)

    def test_unverified_receipt_is_refused(self):
        self._write_receipt(verified=False)
        with self.assertRaises(self.restore.RestoreInputError):
            self.restore._validate_pre_restore_receipt(
                self.paths, self.backup_set, self.backup_key)

    def test_mtime_freshness_decision_is_gone(self):
        import inspect

        self.assertFalse(hasattr(self.restore, "_check_pre_restore_recency"))
        self.assertNotIn("PRE_RESTORE_MAX_AGE_SECONDS",
                         Path(PRODUCT / "restore.py").read_text())
        self.assertNotIn("st_mtime",
                         inspect.getsource(self.restore._validate_pre_restore_receipt))


class ReceiptRotationTests(unittest.TestCase):
    def setUp(self):
        self.backup = load_module("refine_backup_rotation_under_test",
                                  PRODUCT / "backup.py")
        self.tmp = Path(tempfile.mkdtemp(prefix="refine-rotation-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.native_dir = self.tmp / "backups"
        self.native_dir.mkdir()
        self.sets = ["20261101_000000-set-a", "20261102_000000-set-b",
                     "20261103_000000-set-c"]
        for name in self.sets:
            for suffix in self.backup.BACKUP_SUFFIXES.values():
                (self.native_dir / f"{name}{suffix}").write_bytes(b"synthetic")
            (self.native_dir / f"{name}-site_config_backup-enc.json").write_text(
                "{}", encoding="utf-8")
            self.backup.issue_backup_receipt(
                self.native_dir, name,
                {role: self.native_dir / f"{name}{suffix}"
                 for role, suffix in self.backup.BACKUP_SUFFIXES.items()},
                "synthetic-backup-key-for-receipt-tests")

    def test_rotation_removes_the_oldest_set_including_its_receipt(self):
        result = self.backup.rotate_native_sets(
            self.native_dir, keep_count=2, protect_set=self.sets[2])
        self.assertEqual(result["removed"], [self.sets[0]])
        self.assertFalse((self.native_dir / f"{self.sets[0]}-receipt.json").exists())
        for name in self.sets[1:]:
            self.assertTrue((self.native_dir / f"{name}-receipt.json").is_file())

    def test_receiptless_historical_sets_stay_rotatable(self):
        (self.native_dir / f"{self.sets[0]}-receipt.json").unlink()
        result = self.backup.rotate_native_sets(
            self.native_dir, keep_count=2, protect_set=self.sets[2])
        self.assertEqual(result["removed"], [self.sets[0]])


if __name__ == "__main__":
    unittest.main()

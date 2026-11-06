"""Credential-safe transport for Frappe's native GPG backup helpers.

The pinned Frappe source interpolates ``backup_encryption_key`` into a shell
string as ``gpg --yes --passphrase <key>``. This narrow adapter preserves
Frappe's own backup/restore implementation while replacing only that exact
GPG transport: the passphrase goes to GPG's stdin descriptor 0, never to a
shell or child argument list. All unrelated Frappe shell commands retain their
native execution path.
"""
from __future__ import annotations

from contextlib import contextmanager
import math
import os
import shlex
import signal
import subprocess
import threading
import time

try:
    import resource
except ImportError:  # pragma: no cover - non-POSIX platforms
    resource = None


_GPG_DIAGNOSTIC_CATEGORIES = (
    (b"no valid openpgp data", "no-valid-openpgp-data"),
    (b"invalid packet", "invalid-packet"),
    (b"no such file or directory", "input-missing"),
    (b"permission denied", "permission-denied"),
    (b"bad passphrase", "bad-passphrase"),
    (b"invalid option", "invalid-option"),
    (b"unknown option", "invalid-option"),
    (b"operation not permitted", "operation-not-permitted"),
    (b"inappropriate ioctl", "terminal-unavailable"),
    (b"no pinentry", "pinentry-unavailable"),
    (b"no gpg-agent", "agent-unavailable"),
)


def safe_gpg_diagnostic_category(output: bytes | str) -> str:
    """Map known GPG errors to non-sensitive categories; never return raw text."""
    if isinstance(output, str):
        output = output.encode("utf-8", "replace")
    if not isinstance(output, bytes):
        return "unclassified"
    lowered = output.lower()
    return next((category for marker, category in _GPG_DIAGNOSTIC_CATEGORIES
                 if marker in lowered), "unclassified")


_PREFIX = "gpg --yes --passphrase "
_SAFE_GPG_PREFIX = [
    "gpg", "--batch", "--yes", "--passphrase-fd", "0", "--pinentry-mode", "loopback",
]

# Hardening for every GPG child process (Group C refinement of the Group 2
# decrypt probe). The probe used to drain stdout fully and only then read
# stderr, with no timeout: a child that filled the stderr pipe while the
# parent waited on stdout deadlocked forever, and a hanging or endlessly
# streaming child never returned at all. Every GPG child now runs in its
# own session with a wall-clock timeout, POSIX resource limits where safe,
# and a cap on what the parent retains or reads.
PROBE_TIMEOUT_SECONDS = 120
# Minimum budget for small artifacts. The former fixed 2 GiB output cap
# refused legitimate full-site archives above 2 GiB even while streaming
# securely; a fixed 120 s deadline likewise penalized large native backups.
# Larger archives receive a *bounded* allowance based on their encrypted
# byte count, never an unlimited stdout stream or an unlimited wait.
PROBE_MAX_PLAINTEXT_BYTES = 2 * 1024 * 1024 * 1024
PROBE_MAX_ADAPTIVE_PLAINTEXT_BYTES = 512 * 1024 * 1024 * 1024
PROBE_MAX_ADAPTIVE_TIMEOUT_SECONDS = 1800
PROBE_PLAINTEXT_EXPANSION = 16
PROBE_ASSUMED_INPUT_BYTES_PER_SECOND = 24 * 1024 * 1024
PROBE_MAX_DIAGNOSTIC_BYTES = 1024 * 1024
PROBE_MAX_CPU_SECONDS = 1800
PROBE_MAX_MEMORY_BYTES = 512 * 1024 * 1024
GPG_TRANSPORT_TIMEOUT_SECONDS = 1800
GPG_LIST_PACKETS_TIMEOUT_SECONDS = 120
GPG_PACKET_STDOUT_MAX_BYTES = 4 * 1024 * 1024
GPG_PACKET_STDERR_MAX_BYTES = 1024 * 1024


def probe_budget_for_encrypted_size(ciphertext_bytes: int) -> tuple[int, int]:
    """Compute a bounded (seconds, plaintext bytes) GPG verify budget.

    Decryption writes plaintext only to a bounded streaming/discard pipe.
    Ciphertext size is NOT proof of the plaintext's size (GPG compression
    can expand it), so a generous expansion allowance is combined with a
    hard cap and a strict wall-clock cap. The caller still verifies the
    entire decryption; an over-limit result is never accepted as success.
    """
    if (type(ciphertext_bytes) is not int or ciphertext_bytes <= 0):
        raise ValueError("encrypted artifact size must be a positive integer")
    seconds = min(
        PROBE_MAX_ADAPTIVE_TIMEOUT_SECONDS,
        max(PROBE_TIMEOUT_SECONDS,
            (ciphertext_bytes + PROBE_ASSUMED_INPUT_BYTES_PER_SECOND - 1)
            // PROBE_ASSUMED_INPUT_BYTES_PER_SECOND))
    plaintext = min(
        PROBE_MAX_ADAPTIVE_PLAINTEXT_BYTES,
        max(PROBE_MAX_PLAINTEXT_BYTES,
            ciphertext_bytes * PROBE_PLAINTEXT_EXPANSION))
    return seconds, plaintext


def _gpg_child_limits():
    """POSIX resource limits applied in the GPG child before exec.

    Only ever used as ``preexec_fn``: CPU time, then address space. GPG
    streams plaintext, so its memory stays flat regardless of artifact
    size; a 512 MiB address-space cap leaves ample headroom while still
    stopping a runaway child from exhausting the host. A limit that
    cannot be set is skipped — the wall-clock timeout and output cap
    still bind the child.
    """
    if resource is None:
        return
    for limit_name, limit_value in (
            ("RLIMIT_CPU", PROBE_MAX_CPU_SECONDS),
            ("RLIMIT_AS", PROBE_MAX_MEMORY_BYTES)):
        limit = getattr(resource, limit_name, None)
        if limit is None:
            continue
        try:
            resource.setrlimit(limit, (limit_value, limit_value))
        except (ValueError, OSError):
            pass


def gpg_spawn_options():
    """Options shared by every GPG child process.

    The child runs in its own session, so a timeout kill reaches the
    whole process group, not just the direct child. ``preexec_fn`` is
    unsafe while other threads run (the child inherits locks held at
    fork time), so the POSIX limits are only requested from a
    single-threaded caller; the timeout and output caps apply regardless.
    """
    options = {"start_new_session": True}
    if (os.name == "posix" and resource is not None
            and threading.active_count() == 1):
        options["preexec_fn"] = _gpg_child_limits
    return options


def _terminate_process(process) -> None:
    """Kill a GPG child and its process group; never raise.

    The child runs in its own session (see gpg_spawn_options), so the
    group kill also reaches any helper the child spawned. Stand-ins used
    by the test suite may lack ``pid``/``kill``; both are optional here.
    """
    pid = getattr(process, "pid", None)
    if pid is not None:
        try:
            os.killpg(pid, signal.SIGKILL)
            return
        except (OSError, AttributeError, ProcessLookupError):
            pass
    try:
        process.kill()
    except Exception:
        pass


class _StreamDrain(threading.Thread):
    """Drain one child pipe in the background, capping what is kept.

    ``limit`` caps the total bytes read before the drain stops early and
    flags over-limit; ``keep`` caps the bytes retained (diagnostics).
    Plaintext is discarded as it arrives — it is never stored — except
    for the first 512 bytes, which the tar-header check needs.
    """

    def __init__(self, stream, *, limit: int, keep: int):
        super().__init__(daemon=True)
        self._stream = stream
        self._limit = limit
        self._keep = keep
        self.total = 0
        self.head = b""
        self.kept = b""
        self.over_limit = False
        self.read_error = False

    def run(self) -> None:
        try:
            while True:
                chunk = self._stream.read(64 * 1024)
                if not chunk:
                    break
                self.total += len(chunk)
                if len(self.head) < 512:
                    self.head += chunk[:512 - len(self.head)]
                if len(self.kept) < self._keep:
                    self.kept += chunk[:self._keep - len(self.kept)]
                if self.total > self._limit:
                    self.over_limit = True
                    break
        except Exception:
            self.read_error = True


def _wait_for_process(process, outcome: dict) -> None:
    try:
        outcome["returncode"] = process.wait()
    except Exception:
        outcome["error"] = True


class GpgProbeError(ValueError):
    """A GPG decrypt probe failed. ``category`` is a fixed safe label only;
    raw child output is never carried, so it cannot leak paths or secrets."""

    def __init__(self, category: str = "unclassified"):
        self.category = category
        super().__init__("GPG decrypt probe failed; sensitive diagnostics were withheld")


def probe_gpg_decrypt(path, passphrase: str, *, expect_tar: bool = False,
                      timeout: float | None = None,
                      max_plaintext_bytes: int | None = None) -> None:
    """Decrypt ``path`` with ``passphrase`` over stdin and discard the output.

    The plaintext is streamed and discarded in bounded chunks, never stored
    in memory or on disk: a wrong key, corrupt data, or a truncated archive
    fails here, before any caller mutates live data. With ``expect_tar`` the
    first 512 decrypted bytes must also carry the ``ustar`` magic of a tar
    header, so a decryptable but non-tar payload is refused as well. Raises
    :class:`GpgProbeError` on every failure, including an unusable
    passphrase shape; the passphrase itself never appears in argv or output.

    Hardening (Group C): stdout and stderr are drained concurrently by
    background threads, so a child that floods stderr can no longer
    deadlock the parent; the child is killed on timeout or when the
    decrypted plaintext exceeds ``max_plaintext_bytes`` (categories
    ``probe-timeout`` / ``output-limit-exceeded``), and POSIX CPU/memory
    limits apply where safe. A timeout, kill, or over-limit child is
    always a refusal — never a partial success — and this probe creates
    no file, so no partial plaintext can be left behind on any path.
    """
    if (not isinstance(passphrase, str) or not passphrase or not passphrase.isascii()
            or any(char in passphrase for char in "\x00\r\n")):
        raise GpgProbeError("probe-error")
    try:
        ciphertext_bytes = os.stat(path).st_size
        default_timeout, default_limit = probe_budget_for_encrypted_size(
            ciphertext_bytes)
    except (OSError, ValueError, TypeError):
        raise GpgProbeError("probe-error") from None
    if timeout is None:
        timeout = default_timeout
    if max_plaintext_bytes is None:
        max_plaintext_bytes = default_limit
    if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
            or not math.isfinite(timeout) or timeout <= 0
            or timeout > PROBE_MAX_ADAPTIVE_TIMEOUT_SECONDS
            or type(max_plaintext_bytes) is not int
            or not 0 < max_plaintext_bytes <= PROBE_MAX_ADAPTIVE_PLAINTEXT_BYTES):
        raise GpgProbeError("probe-error")
    arguments = [
        "gpg", "--batch", "--yes", "--passphrase-fd", "0",
        "--pinentry-mode", "loopback", "-d", str(path),
    ]
    try:
        process = subprocess.Popen(
            arguments,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **gpg_spawn_options(),
        )
    except Exception:
        raise GpgProbeError("probe-error") from None
    stdout_drain = _StreamDrain(process.stdout, limit=max_plaintext_bytes, keep=0)
    stderr_drain = _StreamDrain(process.stderr, limit=PROBE_MAX_DIAGNOSTIC_BYTES,
                                keep=PROBE_MAX_DIAGNOSTIC_BYTES)
    wait_outcome: dict = {}
    waiter = threading.Thread(target=_wait_for_process, args=(process, wait_outcome),
                              daemon=True)
    timed_out = False
    over_limit = False
    try:
        try:
            process.stdin.write((passphrase + "\n").encode("ascii"))
            process.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            # GPG already exited (for example, on unreadable input). The
            # exit code below still decides the outcome; never retry.
            pass
        stdout_drain.start()
        stderr_drain.start()
        waiter.start()
        deadline = time.monotonic() + timeout
        while waiter.is_alive():
            waiter.join(timeout=0.2)
            if stdout_drain.over_limit or stderr_drain.over_limit:
                over_limit = True
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
        if timed_out or over_limit:
            _terminate_process(process)
            waiter.join(timeout=5)
        else:
            # The child exited; both drains finish at EOF. Bound the wait
            # so a pathological pipe cannot hang the caller after exit.
            stdout_drain.join(timeout=5)
            stderr_drain.join(timeout=5)
            if stdout_drain.is_alive() or stderr_drain.is_alive():
                _terminate_process(process)
                raise GpgProbeError("probe-error")
            # A fast child may exit *before* the first waiter-loop
            # iteration. Its drain threads may then discover an output
            # overflow after the loop has ended. Always inspect their
            # final status after the bounded joins, or a fast-exit
            # oversized decrypted stream is falsely accepted.
            if stdout_drain.over_limit or stderr_drain.over_limit:
                over_limit = True
    except GpgProbeError:
        raise
    except Exception:
        _terminate_process(process)
        raise GpgProbeError("probe-error") from None
    if over_limit:
        raise GpgProbeError("output-limit-exceeded")
    if timed_out:
        raise GpgProbeError("probe-timeout")
    if (wait_outcome.get("error") or stdout_drain.read_error
            or stderr_drain.read_error):
        raise GpgProbeError("probe-error")
    returncode = wait_outcome.get("returncode")
    if returncode != 0:
        raise GpgProbeError(safe_gpg_diagnostic_category(stderr_drain.kept))
    if expect_tar and (len(stdout_drain.head) < 512
                       or stdout_drain.head[257:262] != b"ustar"):
        raise GpgProbeError("invalid-tar-header")


def probe_gpg_packets(path, passphrase: str, *, timeout: float):
    """Inspect GPG packet metadata with bounded pipes and wall-clock time.

    subprocess.run(capture_output=True) previously retained unbounded GPG
    packet output in RAM. A malformed archive may produce enormous output;
    even a child exiting successfully must not bypass the final drain cap.
    The caller consumes the bounded packet marker and safe diagnostics only.
    """
    if (not isinstance(passphrase, str) or not passphrase or not passphrase.isascii()
            or any(c in passphrase for c in "\x00\r\n")
            or isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or not 0 < timeout <= PROBE_MAX_ADAPTIVE_TIMEOUT_SECONDS):
        raise GpgProbeError("probe-error")
    args = [
        "gpg", "--batch", "--passphrase-fd", "0", "--pinentry-mode", "loopback",
        "--list-packets", str(path)]
    try:
        process = subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, **gpg_spawn_options())
    except Exception:
        raise GpgProbeError("probe-error") from None
    stdout_drain = _StreamDrain(
        process.stdout, limit=GPG_PACKET_STDOUT_MAX_BYTES,
        keep=GPG_PACKET_STDOUT_MAX_BYTES)
    stderr_drain = _StreamDrain(
        process.stderr, limit=GPG_PACKET_STDERR_MAX_BYTES,
        keep=GPG_PACKET_STDERR_MAX_BYTES)
    outcome: dict = {}
    waiter = threading.Thread(
        target=_wait_for_process, args=(process, outcome), daemon=True)
    timed_out = False
    over_limit = False
    try:
        try:
            process.stdin.write((passphrase + "\n").encode("ascii"))
            process.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass
        stdout_drain.start()
        stderr_drain.start()
        waiter.start()
        deadline = time.monotonic() + timeout
        while waiter.is_alive():
            waiter.join(timeout=0.2)
            if stdout_drain.over_limit or stderr_drain.over_limit:
                over_limit = True
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
        if timed_out or over_limit:
            _terminate_process(process)
            waiter.join(timeout=5)
        else:
            stdout_drain.join(timeout=5)
            stderr_drain.join(timeout=5)
            if stdout_drain.is_alive() or stderr_drain.is_alive():
                _terminate_process(process)
                raise GpgProbeError("probe-error")
            # The child may exit before the first loop iteration.
            over_limit = stdout_drain.over_limit or stderr_drain.over_limit
    except GpgProbeError:
        raise
    except Exception:
        _terminate_process(process)
        raise GpgProbeError("probe-error") from None
    if over_limit:
        raise GpgProbeError("output-limit-exceeded")
    if timed_out:
        raise GpgProbeError("probe-timeout")
    if (stdout_drain.read_error or stderr_drain.read_error
            or outcome.get("error")
            or type(outcome.get("returncode")) is not int):
        raise GpgProbeError("probe-error")
    return subprocess.CompletedProcess(
        args=["gpg", "--list-packets"], returncode=outcome["returncode"],
        stdout=stdout_drain.kept, stderr=stderr_drain.kept)


def _contains_passphrase_option(command) -> bool:
    if isinstance(command, str):
        return "--passphrase" in command
    if isinstance(command, (list, tuple)):
        return any("--passphrase" in str(part) for part in command)
    return False


def _safe_gpg_arguments(command: str, passphrase: str) -> list[str]:
    if not command.startswith(_PREFIX):
        raise ValueError
    if (not isinstance(passphrase, str) or not passphrase or not passphrase.isascii()
            or any(char in passphrase for char in "\x00\r\n")):
        raise ValueError

    tail = command[len(_PREFIX):]
    if (not tail.startswith(passphrase)
            or len(tail) == len(passphrase)
            or not tail[len(passphrase)].isspace()):
        raise ValueError

    # Remove the secret before tokenization. Any quotes, whitespace, or shell
    # metacharacters in the passphrase are never parsed as command syntax.
    command_without_secret = (
        "gpg --batch --yes --passphrase-fd 0" + tail[len(passphrase):]
    )
    arguments = shlex.split(command_without_secret, posix=True)
    if arguments[:len(_SAFE_GPG_PREFIX)] != _SAFE_GPG_PREFIX:
        raise ValueError

    operation = arguments[len(_SAFE_GPG_PREFIX):]
    encryption = len(operation) == 2 and operation[0] == "-c" and bool(operation[1])
    decryption = (
        len(operation) == 4
        and operation[0] == "-o" and bool(operation[1])
        and operation[2] == "-d" and bool(operation[3])
    )
    if not (encryption or decryption):
        raise ValueError
    return arguments


@contextmanager
def safe_gpg_transport(frappe, passphrase_or_provider):
    """Temporarily route native GPG passphrases over stdin, not argv.

    The pinned ``frappe.utils.execute_in_shell`` signature is preserved. Other
    shell commands are delegated unchanged. Only Frappe's exact native
    symmetric encrypt/decrypt command shapes are accepted; an unexpected
    passphrase-bearing command fails closed without echoing its contents.
    ``passphrase_or_provider`` may be a string or zero-argument callable.
    """
    original = frappe.utils.execute_in_shell

    def execute(command, verbose=False, low_priority=False, check_exit_code=False):
        if not _contains_passphrase_option(command):
            return original(
                command,
                verbose=verbose,
                low_priority=low_priority,
                check_exit_code=check_exit_code,
            )
        if not isinstance(command, str):
            raise RuntimeError(
                "Unsupported native GPG invocation; sensitive diagnostics were withheld")

        try:
            passphrase = (passphrase_or_provider()
                          if callable(passphrase_or_provider)
                          else passphrase_or_provider)
            arguments = _safe_gpg_arguments(command, passphrase)
        except Exception:
            raise RuntimeError(
                "Native GPG invocation was refused; sensitive diagnostics were withheld") from None

        run_options = {
            "input": (passphrase + "\n").encode("ascii"),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "check": False,
            # A hung GPG child must fail the operation, never hang the
            # caller: subprocess.run kills the child on timeout and
            # TimeoutExpired below refuses it. The child also runs in its
            # own session with POSIX limits where safe (see
            # gpg_spawn_options); low_priority keeps its own preexec step.
            "timeout": GPG_TRANSPORT_TIMEOUT_SECONDS,
            **gpg_spawn_options(),
        }
        if low_priority:
            base_preexec = run_options.pop("preexec_fn", None)

            def _preexec_with_limits(base=base_preexec):
                if base is not None:
                    base()
                os.nice(10)

            run_options["preexec_fn"] = _preexec_with_limits
        try:
            result = subprocess.run(arguments, **run_options)
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "Native GPG transport failed; sensitive diagnostics were withheld") from None
        except Exception:
            raise RuntimeError(
                "Native GPG transport failed; sensitive diagnostics were withheld") from None

        # Preserve the return contract, but never forward raw child output to
        # a console/transcript: diagnostics may contain command context that
        # must be reviewed through the approved secure procedure.
        if check_exit_code and result.returncode:
            message = "Native GPG command failed; sensitive diagnostics were withheld"
            command_failed = getattr(frappe, "CommandFailedError", RuntimeError)
            if command_failed is RuntimeError:
                raise RuntimeError(message)
            raise command_failed(message, "", "")
        return result.stderr, result.stdout

    frappe.utils.execute_in_shell = execute
    try:
        yield
    finally:
        frappe.utils.execute_in_shell = original

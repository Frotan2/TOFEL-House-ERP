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
import os
import shlex
import subprocess


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
        }
        if low_priority:
            run_options["preexec_fn"] = lambda: os.nice(10)
        try:
            result = subprocess.run(arguments, **run_options)
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

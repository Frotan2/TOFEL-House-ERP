#!/usr/bin/env python3
"""Run the pinned native Frappe restore with credentials supplied on stdin.

This is a thin adapter around ``frappe.commands.site._restore`` from the
pinned framework. It accepts only a site and a safe backup-set name plus the
restore credentials in a JSON document read from stdin. The backup key is
sent to native GPG over stdin; native MariaDB client passwords use a temporary
mode-0600 option file instead of child argv. Native Frappe remains the restore
authority.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import traceback

from native_db import safe_mariadb_credential_transport
from native_gpg import safe_gpg_diagnostic_category, safe_gpg_transport

BENCH_DIR = Path(os.environ.get("BENCH_DIR", "/home/frappe/bench"))
SITES_DIR = BENCH_DIR / "sites"
SITE_NAME = os.environ.get("SITE_NAME", "toeflhouse.localhost")
MAX_PAYLOAD_BYTES = 128 * 1024
BACKUP_SUFFIXES = {
    "database": "-database-enc.sql.gz",
    "public_files": "-files-enc.tar",
    "private_files": "-private-files-enc.tar",
}


class RestoreInputError(ValueError):
    """Invalid or incomplete secret-bearing restore input."""


_SAFE_CAPTURED_EXCEPTION_TYPES = (
    "FileNotFoundError", "PermissionError", "IsADirectoryError", "NotADirectoryError",
    "CommandFailedError", "CalledProcessError", "OperationalError", "InterfaceError",
    "SystemExit", "RuntimeError", "ValueError", "OSError",
)


class NativeRestoreError(RuntimeError):
    """Sanitized native-restore failure with allowlisted diagnostic details."""

    def __init__(self, failure_type: str, failure_frames: tuple[str, ...],
                 failure_errno: int | None, failure_category: str,
                 reported_failure_type: str | None):
        self.failure_type = (failure_type if re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]{0,63}", failure_type) else "Exception")
        self.failure_frames = tuple(failure_frames[:6])
        self.failure_errno = (failure_errno if type(failure_errno) is int
                              and 0 <= failure_errno <= 65535 else None)
        self.failure_category = failure_category
        self.reported_failure_type = reported_failure_type
        super().__init__("native Frappe restore failed; sensitive diagnostics were withheld")


def _captured_failure_type(output: str) -> str | None:
    matches = [name for name in _SAFE_CAPTURED_EXCEPTION_TYPES
               if re.search(r"\b" + re.escape(name) + r"\b", output)]
    return matches[0] if len(matches) == 1 else None


def _captured_os_error_code(output: str) -> int | None:
    matches = re.findall(r"\[Errno ([0-9]{1,5})\]", output)
    if len(matches) != 1:
        return None
    code = int(matches[0])
    return code if code <= 65535 else None


def _native_restore_failure(error: BaseException, captured_output: str) -> NativeRestoreError:
    """Keep only exception class, numeric OS code, safe GPG category and frames."""
    failure_type = type(error).__name__
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", failure_type):
        failure_type = "Exception"
    frames = []
    for frame in traceback.extract_tb(error.__traceback__)[-6:]:
        if (re.fullmatch(r"[A-Za-z0-9_<>.-]{1,128}", frame.name)
                and type(frame.lineno) is int and 1 <= frame.lineno <= 999999):
            frames.append(f"{frame.name}:{frame.lineno}")
    error_number = getattr(error, "errno", None)
    if type(error_number) is not int or not 0 <= error_number <= 65535:
        error_number = _captured_os_error_code(captured_output)
    gpg_lines = [line for line in captured_output.splitlines()
                 if re.search(r"\bgpg(?:\[[^]]+\])?:", line, re.IGNORECASE)]
    category = safe_gpg_diagnostic_category("\n".join(gpg_lines))
    reported_type = _captured_failure_type(captured_output)
    return NativeRestoreError(failure_type, tuple(frames), error_number, category,
                              reported_type)


def _read_payload(stdin) -> dict:
    raw = stdin.read(MAX_PAYLOAD_BYTES + 1)
    if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise RestoreInputError("restore input exceeds its safe size limit")
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RestoreInputError("restore input is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RestoreInputError("restore input must be a JSON object")
    return payload


def _validate_payload(payload: dict) -> tuple[str, str, str, str, str]:
    site = payload.get("site")
    backup_set = payload.get("backup_set")
    encryption_key = payload.get("encryption_key")
    db_root_password = payload.get("db_root_password")
    admin_password = payload.get("admin_password")
    if site != SITE_NAME or not isinstance(site, str):
        raise RestoreInputError("restore site does not match the configured product site")
    if not isinstance(backup_set, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", backup_set):
        raise RestoreInputError("restore backup-set name is invalid")
    for value, label in ((encryption_key, "Frappe backup key"),
                         (db_root_password, "MariaDB root password"),
                         (admin_password, "Administrator password")):
        if not isinstance(value, str) or not value or "\x00" in value:
            raise RestoreInputError(f"{label} is missing or invalid")
    if (not encryption_key.isascii() or len(encryption_key) > 4096
            or any(char in encryption_key for char in "\r\n")):
        raise RestoreInputError("Frappe backup key is missing or invalid")
    return site, backup_set, encryption_key, db_root_password, admin_password


def _sha256_stream(stream) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def _same_file_state(left, right) -> bool:
    return (left.st_dev, left.st_ino, left.st_size, left.st_mtime_ns,
            left.st_ctime_ns) == (
                right.st_dev, right.st_ino, right.st_size, right.st_mtime_ns,
                right.st_ctime_ns)


def _stage_restore_artifacts(paths: dict[str, Path], temporary_root: Path) -> dict[str, Path]:
    """Give native Frappe disposable copies, never the preserved backup set.

    The pinned native ``decrypt_backup`` renames an encrypted file and writes
    plaintext at its original path during restore. Keep those mutations inside
    an ephemeral /tmp directory so a failed or interrupted restore cannot
    rename, replace, or leave plaintext beside the Owner's encrypted backups.
    """
    artifacts_dir = temporary_root / "artifacts"
    artifacts_dir.mkdir(mode=0o700)
    staged = {}
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    for role, source in paths.items():
        destination = artifacts_dir / source.name
        source_fd = destination_fd = None
        try:
            path_state = source.lstat()
            if not stat.S_ISREG(path_state.st_mode) or path_state.st_size <= 0:
                raise OSError
            source_fd = os.open(source, os.O_RDONLY | nofollow)
            with os.fdopen(source_fd, "rb") as source_stream:
                source_fd = None
                opened_state = os.fstat(source_stream.fileno())
                if (not stat.S_ISREG(opened_state.st_mode)
                        or not _same_file_state(path_state, opened_state)):
                    raise OSError
                destination_fd = os.open(
                    destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(destination_fd, "wb") as destination_stream:
                    destination_fd = None
                    shutil.copyfileobj(source_stream, destination_stream,
                                       length=1024 * 1024)
                    destination_stream.flush()
                    os.fsync(destination_stream.fileno())
                after_copy = os.fstat(source_stream.fileno())
                current_path_state = source.lstat()
                if (not _same_file_state(opened_state, after_copy)
                        or not _same_file_state(opened_state, current_path_state)):
                    raise OSError
                if destination.stat().st_size != opened_state.st_size:
                    raise OSError
                source_stream.seek(0)
                source_digest = _sha256_stream(source_stream)
                with destination.open("rb") as staged_stream:
                    staged_digest = _sha256_stream(staged_stream)
                if source_digest != staged_digest:
                    raise OSError
        except OSError:
            try:
                destination.unlink()
            except OSError:
                pass
            raise RestoreInputError(
                f"restore artifact could not be staged safely: {role}") from None
        finally:
            if source_fd is not None:
                os.close(source_fd)
            if destination_fd is not None:
                os.close(destination_fd)
        staged[role] = destination
    return staged


def _native_restore(site: str, backup_set: str, encryption_key: str,
                    db_root_password: str, admin_password: str) -> None:
    backup_dir = SITES_DIR / site / "private" / "backups"
    paths = {
        role: backup_dir / f"{backup_set}{suffix}"
        for role, suffix in BACKUP_SUFFIXES.items()
    }
    parent_dirs = (SITES_DIR, SITES_DIR / site,
                   SITES_DIR / site / "private", backup_dir)
    if any(path.is_symlink() for path in parent_dirs):
        raise RestoreInputError("restore artifact directory is unsafe")
    try:
        resolved_backup_dir = backup_dir.resolve(strict=True)
    except OSError:
        raise RestoreInputError("required restore artifact directory is missing") from None
    for role, path in paths.items():
        try:
            resolved_path = path.resolve(strict=True)
            valid_path = resolved_path.parent == resolved_backup_dir
            valid_file = path.is_file() and path.stat().st_size > 0
        except OSError:
            valid_path = valid_file = False
        if path.is_symlink() or not valid_path or not valid_file:
            raise RestoreInputError(f"required restore artifact is missing or unsafe: {role}")

    # Match the pinned Frappe CLI's native restore wrapper: initialize the
    # selected site, acquire its restore lock, then call the same internal
    # implementation that `bench restore` invokes. Secrets remain in-process.
    import frappe
    import frappe.utils
    from frappe.commands.site import _restore
    from frappe.utils.synchronization import filelock

    initialized = False
    captured = io.StringIO()
    try:
        # Frappe's native decrypt_backup temporarily replaces its input files
        # with plaintext while restoring. Keep that in-place behavior confined
        # to disposable container storage, not the preserved native backup set.
        # A fixed /tmp parent also keeps paths safe for Frappe's native `file`
        # shell command, which accepts an unquoted path.
        if Path("/tmp").is_symlink():
            raise RestoreInputError("temporary restore storage is unsafe")
        with tempfile.TemporaryDirectory(
                prefix="toefl-house-native-restore-", dir="/tmp") as working_name:
            working_dir = Path(working_name)
            staged_paths = _stage_restore_artifacts(paths, working_dir)
            with safe_mariadb_credential_transport(frappe, working_dir):
                with safe_gpg_transport(frappe, encryption_key):
                    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                        frappe.init(site, sites_path=str(SITES_DIR))
                        initialized = True
                        with filelock("site_restore", timeout=1):
                            _restore(
                                site=site,
                                sql_file_path=str(staged_paths["database"]),
                                encryption_key=encryption_key,
                                db_root_username="root",
                                db_root_password=db_root_password,
                                admin_password=admin_password,
                                force=True,
                                with_public_files=str(staged_paths["public_files"]),
                                with_private_files=str(staged_paths["private_files"]),
                            )
    except RestoreInputError:
        raise
    except SystemExit as error:
        if error.code not in (None, 0):
            raise _native_restore_failure(error, captured.getvalue()) from None
    except Exception as error:
        # Native restore diagnostics can include command context. Preserve only
        # an allowlisted class/category and compact frame names/line numbers.
        raise _native_restore_failure(error, captured.getvalue()) from None
    finally:
        if initialized:
            try:
                with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                    frappe.destroy()
            except Exception:
                pass


def main(stdin=None, stdout=None, stderr=None, argv=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    arguments = sys.argv[1:] if argv is None else argv
    if arguments:
        stderr.write("Restore refused: this adapter accepts no command-line arguments.\n")
        return 2
    try:
        payload = _read_payload(stdin)
        site, backup_set, encryption_key, db_root_password, admin_password = (
            _validate_payload(payload))
        _native_restore(site, backup_set, encryption_key,
                        db_root_password, admin_password)
    except RestoreInputError as exc:
        stderr.write(f"Restore refused: {exc}\n")
        return 2
    except NativeRestoreError as error:
        details = ["Native Frappe restore failed",
                   "exception type: " + error.failure_type]
        if (error.reported_failure_type
                and error.reported_failure_type != error.failure_type):
            details.append("reported exception type: " + error.reported_failure_type)
        if error.failure_errno is not None:
            details.append("OS error code: " + str(error.failure_errno))
        if error.failure_category != "unclassified":
            details.append("GPG diagnostic category: " + error.failure_category)
        if error.failure_frames:
            details.append("frames: " + ",".join(error.failure_frames))
        details.append("Sensitive diagnostics were withheld")
        stderr.write("; ".join(details) + ". Leave the application writers stopped "
                     "and inspect logs through the approved secure procedure.\n")
        return 1
    except Exception:
        stderr.write(
            "Native Frappe restore failed. Sensitive diagnostics were withheld; "
            "leave the application writers stopped and inspect logs through the "
            "approved secure procedure.\n")
        return 1
    stdout.write("Native Frappe restore completed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

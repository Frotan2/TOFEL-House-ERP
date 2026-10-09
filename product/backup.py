#!/usr/bin/env python3
"""Run Frappe's native full-site backup with safe credential transport.

This adapter does not implement a backup format or retention policy. It calls
pinned Frappe ``scheduled_backup``/``BackupGenerator`` with the native full-
site options, suppresses only Frappe's unsafe deletion of older native-source
files, and publishes a newly generated set after confirming Frappe produced
real GPG-encrypted database/public/private artifacts. All pre-existing backup
files remain untouched.
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
import subprocess
import sys
import tempfile

from native_db import safe_mariadb_credential_transport
from native_gpg import safe_gpg_transport

BENCH_DIR = Path(os.environ.get("BENCH_DIR", "/home/frappe/bench"))
SITES_DIR = BENCH_DIR / "sites"
SITE_NAME = os.environ.get("SITE_NAME", "toeflhouse.localhost")
SUPPORTED_SITE = "toeflhouse.localhost"
BACKUP_SUFFIXES = {
    "database": "-database-enc.sql.gz",
    "public_files": "-files-enc.tar",
    "private_files": "-private-files-enc.tar",
}
CONFIG_MARKER = "-site_config_backup"
BACKUP_SET_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}\Z")


class BackupInputError(ValueError):
    """The product backup preconditions or verification are incomplete."""

    def __init__(self, message: str, *, safe_code: str | None = None,
                 safe_category: str | None = None):
        super().__init__(message)
        self.safe_code = safe_code
        self.safe_category = safe_category


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _native_backup_directory(backups, site_name: str) -> Path:
    site_root = SITES_DIR / site_name
    private_root = site_root / "private"
    backup_dir = private_root / "backups"
    for path in (SITES_DIR, site_root, private_root, backup_dir):
        if path.is_symlink():
            raise BackupInputError("native Frappe backup directory is unsafe")
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        expected = backup_dir.resolve(strict=True)
        configured = Path(backups.get_backup_path()).resolve(strict=True)
    except OSError:
        raise BackupInputError("native Frappe backup directory is unavailable") from None
    if configured != expected or not expected.is_dir():
        raise BackupInputError(
            "native Frappe backup path differs from the product site's protected backup folder")
    return expected


def _staged_file(raw_path, staging_dir: Path, role: str) -> Path:
    if not isinstance(raw_path, (str, os.PathLike)) or not str(raw_path):
        raise BackupInputError(f"native Frappe backup did not produce the required {role} artifact")
    path = Path(raw_path)
    try:
        resolved = path.resolve(strict=True)
        stage_resolved = staging_dir.resolve(strict=True)
        if (path.is_symlink() or resolved.parent != stage_resolved
                or not path.is_file() or path.stat().st_size <= 0):
            raise OSError
    except OSError:
        raise BackupInputError(f"native Frappe backup produced an unsafe {role} artifact") from None
    return path


def _gpg_diagnostic_category(output: bytes) -> str:
    """Map known GPG errors to non-sensitive categories; never return raw text."""
    lowered = output.lower()
    categories = (
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
    return next((category for marker, category in categories if marker in lowered), "unclassified")


def _assert_gpg_encrypted(path: Path, role: str) -> None:
    role_code = {
        "database": "database",
        "public files": "public-files",
        "private files": "private-files",
    }.get(role, "artifact")
    try:
        result = subprocess.run(
            ["gpg", "--list-packets", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except Exception:
        raise BackupInputError(
            f"native Frappe {role} artifact could not be checked for GPG encryption",
            safe_code=f"gpg-{role_code}-probe-error",
            safe_category="probe-error",
        ) from None
    output = (result.stdout or b"") + (result.stderr or b"")
    if result.returncode != 0:
        code = (result.returncode
                if type(result.returncode) is int and 0 <= result.returncode <= 255
                else "other")
        raise BackupInputError(
            f"native Frappe {role} artifact could not be checked for GPG encryption",
            safe_code=f"gpg-{role_code}-check-exit-{code}",
            safe_category=_gpg_diagnostic_category(output),
        )
    if b":symkey enc packet:" not in output:
        raise BackupInputError(
            f"native Frappe {role} artifact is not verified as GPG-encrypted",
            safe_code=f"gpg-{role_code}-symmetric-packet-missing",
            safe_category=_gpg_diagnostic_category(output),
        )


def _publish_without_overwrite(source: Path, destination: Path) -> None:
    """Copy a verified artifact beside its final path, then link without replace."""
    descriptor = None
    temporary = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".toefl-house-backup-publish-", dir=destination.parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_stream:
            descriptor = None
            shutil.copyfileobj(input_stream, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        if (temporary.stat().st_size != source.stat().st_size
                or _sha256(temporary) != _sha256(source)):
            raise BackupInputError("native Frappe backup artifact changed during publication")
        # Unlike os.replace, a hard link is atomic and refuses to overwrite an
        # existing file (including a symlink) if a concurrent backup races us.
        os.link(temporary, destination, follow_symlinks=False)
    except FileExistsError:
        raise BackupInputError(
            "refusing to overwrite a pre-existing native Frappe backup artifact") from None
    except BackupInputError:
        raise
    except Exception:
        raise BackupInputError(
            "verified native Frappe backup artifact could not be published safely") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                # This name was created exclusively by this process. Do not
                # risk replacing or removing any native/pre-existing backup.
                pass


def _verify_and_publish(backup_result, staging_dir: Path, destination_dir: Path,
                        encryption_key: str) -> str:
    native_paths = {
        "database": _staged_file(
            getattr(backup_result, "backup_path_db", None), staging_dir, "database"),
        "public_files": _staged_file(
            getattr(backup_result, "backup_path_files", None), staging_dir, "public files"),
        "private_files": _staged_file(
            getattr(backup_result, "backup_path_private_files", None), staging_dir, "private files"),
        "site_config": _staged_file(
            getattr(backup_result, "backup_path_conf", None), staging_dir, "site-config"),
    }

    database_name = native_paths["database"].name
    suffix = BACKUP_SUFFIXES["database"]
    if not database_name.endswith(suffix):
        raise BackupInputError("native Frappe database artifact has an unexpected name")
    backup_set = database_name[:-len(suffix)]
    if not BACKUP_SET_PATTERN.fullmatch(backup_set):
        raise BackupInputError("native Frappe backup-set name is invalid")

    destinations = {}
    for role, artifact_suffix in BACKUP_SUFFIXES.items():
        source = native_paths[role]
        expected_name = f"{backup_set}{artifact_suffix}"
        if source.name != expected_name:
            raise BackupInputError(f"native Frappe {role} artifact does not match the backup set")
        _assert_gpg_encrypted(source, role)
        destinations[role] = destination_dir / expected_name

    config_source = native_paths["site_config"]
    if (not config_source.name.startswith(f"{backup_set}{CONFIG_MARKER}")
            or not config_source.name.endswith(".json")):
        raise BackupInputError("native Frappe site-config artifact has an unexpected name")
    try:
        site_config = json.loads(config_source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise BackupInputError("native Frappe site-config artifact is invalid") from None
    if (not isinstance(site_config, dict)
            or site_config.get("backup_encryption_key") != encryption_key):
        raise BackupInputError(
            "native Frappe site-config artifact does not contain its backup_encryption_key")
    destinations["site_config"] = destination_dir / config_source.name

    # Check every name before creating any final output. Publish the plaintext
    # config sidecar last, only after all three native encrypted artifacts have
    # been checked and copied successfully.
    if any(path.exists() or path.is_symlink() for path in destinations.values()):
        raise BackupInputError(
            "refusing to overwrite a pre-existing native Frappe backup set")
    for role in BACKUP_SUFFIXES:
        _publish_without_overwrite(native_paths[role], destinations[role])
    _publish_without_overwrite(native_paths["site_config"], destinations["site_config"])
    return backup_set


def _native_backup(site_name: str | None = None, *, allow_test_site: bool = False) -> None:
    """Run native Frappe backup; the site override is only for CI fixtures.

    ``main`` never exposes the test override, so desktop callers remain bound
    to the single configured product site.
    """
    site_name = SITE_NAME if site_name is None else site_name
    if (not isinstance(site_name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", site_name)
            or (site_name != SUPPORTED_SITE and not allow_test_site)):
        raise BackupInputError("backup site does not match the configured product site")

    import frappe
    import frappe.utils
    from frappe.utils import backups

    initialized = False
    captured = io.StringIO()
    original_cleanup = backups.delete_temp_backups
    try:
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            frappe.init(site_name, sites_path=str(SITES_DIR))
            initialized = True
            frappe.connect()
            destination_dir = _native_backup_directory(backups, site_name)
            if not frappe.get_system_settings("encrypt_backup"):
                raise BackupInputError(
                    "native Frappe backup encryption is not enabled; refusing plaintext backup")

            # Generate/obtain the key through Frappe before BackupGenerator
            # copies site_config.json. On the pinned framework, key generation
            # otherwise happens after that sidecar snapshot is taken.
            encryption_key = backups.get_or_generate_backup_encryption_key()
            if (not isinstance(encryption_key, str) or not encryption_key
                    or not encryption_key.isascii()
                    or any(char in encryption_key for char in "\x00\r\n")):
                raise BackupInputError("native Frappe backup_encryption_key is invalid")

            # Frappe's scheduled path deletes old files from its native backup
            # directory before creating a new set. Retention is owned by the
            # product's separately verified Owner-configured drive workflow.
            backups.delete_temp_backups = lambda *args, **kwargs: None
            try:
                with tempfile.TemporaryDirectory(
                        prefix="toefl-house-native-backup-") as staging_name:
                    staging_dir = Path(staging_name)
                    with safe_mariadb_credential_transport(frappe, staging_dir):
                        with safe_gpg_transport(frappe, encryption_key):
                            backup_result = backups.scheduled_backup(
                                ignore_files=False,
                                force=True,
                                verbose=False,
                                backup_path=str(staging_dir),
                            )
                    _verify_and_publish(
                        backup_result, staging_dir, destination_dir, encryption_key)
            finally:
                backups.delete_temp_backups = original_cleanup
    finally:
        if initialized:
            try:
                with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                    frappe.destroy()
            except Exception:
                pass


def main(argv=None, stdout=None, stderr=None) -> int:
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    # The product supports only a full native backup including both file
    # archives; no CLI option may silently reduce it to a database-only set.
    arguments = sys.argv[1:] if argv is None else argv
    if arguments:
        stderr.write("Backup refused: this adapter accepts no command-line arguments.\n")
        return 2
    try:
        _native_backup()
    except BackupInputError as exc:
        stderr.write(f"Backup refused: {exc}\n")
        return 2
    except SystemExit:
        stderr.write(
            "Native Frappe backup failed; sensitive diagnostics were withheld. "
            "Existing backup material was preserved; inspect logs through the "
            "approved secure procedure.\n")
        return 1
    except Exception:
        stderr.write(
            "Native Frappe backup failed; sensitive diagnostics were withheld. "
            "Existing backup material was preserved; inspect logs through the "
            "approved secure procedure.\n")
        return 1
    stdout.write(
        "Native Frappe database/files backup completed and GPG encryption verified; "
        "the host recovery-sidecar step remains separate.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

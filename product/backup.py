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
from native_gpg import safe_gpg_diagnostic_category, safe_gpg_transport

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
# Must equal apps/toefl_house/.../owner_configuration.py; tests compare the two.
RETENTION_PRESERVE_ALL = "Preserve all valid backup sets"
RETENTION_DELETE_BEYOND_KEEP = "Delete valid older sets beyond keep count"
MIN_RETAINED_SETS = 2
TIMESTAMPED_SET = re.compile(r"(\d{8}_\d{6})-[^/\\\x00]+\Z")
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


def _assert_gpg_encrypted(path: Path, role: str, encryption_key: str) -> None:
    role_code = {
        "database": "database",
        "public files": "public-files",
        "private files": "private-files",
    }.get(role, "artifact")
    try:
        result = subprocess.run(
            ["gpg", "--batch", "--passphrase-fd", "0", "--pinentry-mode", "loopback",
             "--list-packets", str(path)],
            input=(encryption_key + "\n").encode("ascii"),
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
            safe_category=safe_gpg_diagnostic_category(output),
        )
    if b":symkey enc packet:" not in output:
        raise BackupInputError(
            f"native Frappe {role} artifact is not verified as GPG-encrypted",
            safe_code=f"gpg-{role_code}-symmetric-packet-missing",
            safe_category=safe_gpg_diagnostic_category(output),
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
        _assert_gpg_encrypted(source, role, encryption_key)
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
    published = []
    try:
        for role in BACKUP_SUFFIXES:
            _publish_without_overwrite(native_paths[role], destinations[role])
            published.append(destinations[role].name)
        _publish_without_overwrite(native_paths["site_config"], destinations["site_config"])
    except BackupInputError:
        if not published:
            raise
        # Owner decision F7: leave what was published, never delete it here, and say
        # plainly that the set is incomplete. The sidecar is the completion marker and
        # was not written, so retention never counts or deletes this set automatically.
        raise BackupInputError(
            f"native backup set {backup_set} is incomplete: {len(published)} encrypted "
            "artifact(s) were published without the site-config sidecar and were left in "
            "the native backup folder for owner cleanup; no sets were deleted",
            safe_code="native-publish-incomplete") from None
    return backup_set


def _complete_native_sets(native_dir: Path) -> dict:
    """Classify native sets. Only regular, non-symlink files count as present.

    Returns {set_name: {"complete": bool, "timestamp": str|None, "files": [Path...]}}.
    A set is complete only when all three encrypted artifacts and at least one
    site-config sidecar are present as regular files.
    """
    # Every set has a database artifact. Derive names from that suffix only:
    # "-files-enc.tar" is also a suffix of "-private-files-enc.tar".
    database_suffix = BACKUP_SUFFIXES["database"]
    names = {entry.name[:-len(database_suffix)] for entry in native_dir.iterdir()
             if entry.name.endswith(database_suffix)}
    sets = {}
    for name in sorted(names):
        match = TIMESTAMPED_SET.fullmatch(name)
        artifacts = [native_dir / f"{name}{suffix}" for suffix in BACKUP_SUFFIXES.values()]
        sidecars = [p for p in native_dir.iterdir()
                    if p.name.startswith(f"{name}{CONFIG_MARKER}") and p.name.endswith(".json")]
        every = artifacts + sidecars
        regular = all(p.is_file() and not p.is_symlink() for p in every) and bool(sidecars)
        sets[name] = {
            "complete": regular,
            "timestamp": match.group(1) if match else None,
            "files": every,
        }
    return sets


def rotate_native_sets(native_dir: Path, *, keep_count, protect_set: str) -> dict:
    """Owner D17 for the native folder: keep the newest ``keep_count`` complete sets.

    Fail closed: any problem raises before a single file is removed. Incomplete,
    symlinked, or non-timestamped sets are preserved and never counted. Each set's
    site-config sidecar (which holds the backup key) is removed first, so an
    interrupted deletion leaves an incomplete set that later runs never delete.
    """
    if (not isinstance(keep_count, int) or isinstance(keep_count, bool)
            or keep_count < MIN_RETAINED_SETS):
        raise BackupInputError("native retention keep count is not a configured value; no sets were deleted",
                               safe_code="native-retention-keep-count-invalid")
    if native_dir.is_symlink() or not native_dir.is_dir():
        raise BackupInputError("native backup folder is unsafe; no sets were deleted",
                               safe_code="native-retention-folder-unsafe")
    sets = _complete_native_sets(native_dir)
    valid = [(info["timestamp"], name) for name, info in sets.items()
             if info["complete"] and info["timestamp"]]
    valid.sort(reverse=True)
    keep = [name for _, name in valid[:keep_count]]
    if protect_set not in keep:
        raise BackupInputError(
            "native retention plan would discard the newly verified backup; no sets were deleted",
            safe_code="native-retention-would-drop-current")
    doomed = [name for _, name in valid[keep_count:]]
    removed = []
    for name in doomed:
        info = sets[name]
        sidecars = [p for p in info["files"] if CONFIG_MARKER in p.name]
        artifacts = [p for p in info["files"] if CONFIG_MARKER not in p.name]
        try:
            for path in sidecars + artifacts:
                if path.is_symlink() or not path.is_file():
                    raise OSError
                path.unlink()
        except OSError:
            raise BackupInputError(
                f"native retention was interrupted while removing {name}; the remaining files are "
                "an incomplete set for owner cleanup; earlier sets were already removed",
                safe_code="native-retention-interrupted") from None
        removed.append(name)
    return {"kept": keep, "removed": removed}


def _current_owner_backup_policy() -> dict:
    """Read the validated Owner policy from Frappe. Missing or invalid means not configured."""
    try:
        from toefl_house.operations import owner_configuration
    except Exception:
        return {"configured": False, "status": "NOT CONFIGURED"}
    return owner_configuration.current_backup_policy()


def _apply_native_retention(destination_dir: Path, published_set: str, policy=None) -> str:
    """Apply the Owner-selected retention to the native folder; default is no deletion."""
    if policy is None:
        policy = _current_owner_backup_policy()
    if not isinstance(policy, dict) or policy.get("configured") is not True:
        return "not configured; no native sets were deleted"
    behavior = policy.get("retention_behavior")
    if behavior == RETENTION_PRESERVE_ALL:
        return "preserve all valid native sets"
    if behavior != RETENTION_DELETE_BEYOND_KEEP:
        return "retention behavior not recognised; no native sets were deleted"
    result = rotate_native_sets(
        destination_dir, keep_count=policy.get("retention_versions"), protect_set=published_set)
    return (f"kept {len(result['kept'])} complete set(s); removed {len(result['removed'])} "
            "older complete set(s)")


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

    caller_cwd = Path.cwd()
    initialized = False
    retention_status = None
    captured = io.StringIO()
    try:
        os.chdir(SITES_DIR)
        import frappe
        import frappe.utils
        from frappe.utils import backups

        original_cleanup = backups.delete_temp_backups
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            # Match Bench's native `frappe_cmd` CWD and `frappe.init(site)`;
            # BackupGenerator archives the relative site path consumed by
            # Frappe restore's `tar --strip 2` extraction.
            frappe.init(site_name)
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
                    published_set = _verify_and_publish(
                        backup_result, staging_dir, destination_dir, encryption_key)
                    retention_status = _apply_native_retention(destination_dir, published_set)
            finally:
                backups.delete_temp_backups = original_cleanup
    finally:
        try:
            if initialized:
                try:
                    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                        frappe.destroy()
                except Exception:
                    pass
        finally:
            os.chdir(caller_cwd)
    return retention_status


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
        retention_status = _native_backup()
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
    stdout.write(f"Native retention: {retention_status}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

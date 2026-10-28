#!/usr/bin/env python3
"""Run the pinned native Frappe restore with credentials supplied on stdin.

This is a thin adapter around ``frappe.commands.site._restore`` from the
pinned framework. It accepts only a site and a safe backup-set name plus the
restore credentials in a JSON document read from stdin. The backup key is
sent to native GPG over stdin; native MariaDB client passwords use a temporary
mode-0600 option file instead of child argv. Native Frappe remains the restore
authority.

Emergency-recovery gate (new): a restore is either explicitly ``disposable``
— only for a site whose name contains "restore" and is not the production
site — or ``production`` (the default when ``target`` is omitted). A
production restore is refused before any mutation unless it names a distinct
pre-restore backup set preserving the live site, and carries a
two-approver emergency authorization (one Course Owner + one General Manager
or recovery authority, distinct keys, bound to the exact backup artifact
hashes, single-use request_id) verified against the installation-provisioned
trust store. Every restore, disposable or production, is recorded in a
hash-chained audit log that never contains secrets. A fully privileged
operating-system/container administrator can still bypass this adapter with
a direct Bench/MariaDB restore; that path is outside application control and
is covered by access control and procedure, not by this code.
"""
from __future__ import annotations

import base64
import contextlib
import fcntl
import hashlib
import hmac
import io
import json
import os
from datetime import datetime, timezone
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
# The production site name is installation-controlled, never caller-supplied:
# a restore whose site equals this name is a production restore and is refused
# without a verified two-approver emergency authorization (see below).
PRODUCTION_SITE = os.environ.get(
    "TOEFL_HOUSE_PRODUCTION_SITE", "toeflhouse.localhost")

# A disposable restore must be unmistakably a lab target and never the
# production site. The hosted runtime creates BOTH lab sites: ``restore.localhost``
# for the first restore cycle and ``recovery.localhost`` for the hardened
# encrypted-recovery cycle (see the runtime nginx site map). Recognizing only
# "restore" refused the hardened cycle's payload before any restore ran, which
# is why the Foundation runtime gate failed at ``hardened-restore-with-files``
# with exit 2 (RestoreInputError) while the first cycle passed. An ordinary
# business site name is still refused, and PRODUCTION_SITE is always excluded.
DISPOSABLE_SITE_MARKERS = ("restore", "recovery")
MAX_PAYLOAD_BYTES = 128 * 1024
BACKUP_SUFFIXES = {
    "database": "-database-enc.sql.gz",
    "public_files": "-files-enc.tar",
    "private_files": "-private-files-enc.tar",
}
# Emergency-restore authorization (production restores only). This is a
# restore-specific document, distinct from the update engine's recovery
# authorization: same approver roles and trust-store key format, but a
# separate document_type, a separate key purpose ("emergency-restore"), and
# its own single-use request record, so update authority never implicitly
# grants restore authority.
EMERGENCY_RESTORE_SCHEMA_VERSION = 1
EMERGENCY_RESTORE_DOCUMENT_TYPE = "emergency-restore"
EMERGENCY_RESTORE_TRUST_DOCUMENT_TYPE = "toefl-house-erp-update-trust-store"
EMERGENCY_RESTORE_KEY_PURPOSE = "emergency-restore"
EMERGENCY_APPROVER_ROLES = ("course-owner", "general-manager", "recovery-authority")
EMERGENCY_REQUEST_ID = re.compile(r"[0-9a-f]{32}\Z")
EMERGENCY_APPROVAL_KEYS = ("key_id", "approver_identity", "approver_role")
EMERGENCY_DOCUMENT_KEYS = (
    "schema_version", "document_type", "site", "target", "backup_set",
    "backup_sha256", "request_id", "issued_utc", "expires_utc", "approvals")
KEY_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


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
                 reported_failure_type: str | None,
                 reported_frames: tuple[str, ...] = (),
                 failure_location: str | None = None,
                 reported_cwd: str | None = None,
                 failure_parent_location: str | None = None,
                 failure_parent_state: str | None = None):
        self.failure_type = (failure_type if re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]{0,63}", failure_type) else "Exception")
        self.failure_frames = tuple(failure_frames[:6])
        self.failure_errno = (failure_errno if type(failure_errno) is int
                              and 0 <= failure_errno <= 65535 else None)
        self.failure_category = failure_category
        self.reported_failure_type = reported_failure_type
        self.reported_frames = tuple(reported_frames[:6])
        self.failure_location = failure_location
        self.reported_cwd = (reported_cwd if reported_cwd in {
            "site-data", "bench", "bench-parent", "other", "unknown"} else None)
        self.failure_parent_location = failure_parent_location
        self.failure_parent_state = (failure_parent_state if failure_parent_state in {
            "directory", "missing", "not-directory", "unknown"} else None)
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


def _exception_chain(error: BaseException) -> tuple[BaseException, ...]:
    chain = []
    seen = set()
    current = error
    while isinstance(current, BaseException) and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return tuple(chain)


def _safe_traceback_frames(error: BaseException) -> tuple[str, ...]:
    frames = []
    for frame in traceback.extract_tb(error.__traceback__)[-6:]:
        if (re.fullmatch(r"[A-Za-z0-9_<>.-]{1,128}", frame.name)
                and type(frame.lineno) is int and 1 <= frame.lineno <= 999999):
            frames.append(f"{frame.name}:{frame.lineno}")
    return tuple(frames)


def _runtime_path_roots(temporary_root: Path | None = None):
    roots = []
    if temporary_root is not None:
        roots.append(("restore-temp", Path(os.path.abspath(temporary_root))))
    roots.extend((
        ("site-data", Path(os.path.abspath(SITES_DIR))),
        ("bench", Path(os.path.abspath(BENCH_DIR))),
        ("bench-parent", Path(os.path.abspath(BENCH_DIR.parent))),
        ("system-bin", Path("/usr/bin")),
        ("system-bin", Path("/bin")),
        ("system-bin", Path("/usr/sbin")),
    ))
    return roots


def _safe_runtime_path_location(candidate: Path,
                                temporary_root: Path | None = None) -> str | None:
    safe_component = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,200}\Z")
    candidate = Path(os.path.abspath(candidate))
    for label, root in _runtime_path_roots(temporary_root):
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            continue
        parts = relative.parts
        if not parts:
            return label + ":<root>"
        if (len(parts) > 16
                or any(not safe_component.fullmatch(part) for part in parts)):
            return label + ":<path-withheld>"
        return label + ":" + "/".join(parts)
    return None


def _safe_current_directory() -> str:
    try:
        current = Path(os.path.abspath(os.getcwd()))
    except OSError:
        return "unknown"
    for label, root in _runtime_path_roots():
        if label == "system-bin":
            continue
        try:
            current.relative_to(root)
        except ValueError:
            continue
        return label
    return "other"


def _safe_directory_state(path: Path,
                          temporary_root: Path | None = None) -> str:
    if _safe_runtime_path_location(path, temporary_root) is None:
        return "unknown"
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return "missing"
    except NotADirectoryError:
        return "not-directory"
    except OSError:
        return "unknown"
    return "directory" if stat.S_ISDIR(mode) else "not-directory"


def _safe_restore_context(temporary_root: Path | None = None) -> tuple[str, str]:
    """Describe only the known-root CWD class and relative Frappe log dir."""
    try:
        log_directory = Path(os.path.abspath(Path("..") / "logs"))
    except OSError:
        return _safe_current_directory(), "unknown"
    return (_safe_current_directory(),
            _safe_directory_state(log_directory, temporary_root))


def _safe_failure_location(error: BaseException | None,
                           temporary_root: Path | None) -> str | None:
    """Map an exception filename to a known disposable/runtime root.

    Absolute host paths, arbitrary path components, and exception messages are
    never emitted. This retains useful command/artifact context without
    disclosing user paths or backup contents.
    """
    filename = getattr(error, "filename", None)
    if not isinstance(filename, (str, bytes, os.PathLike)):
        return None
    try:
        raw_path = os.fsdecode(os.fspath(filename))
    except (TypeError, ValueError):
        return None
    if (not raw_path or len(raw_path) > 4096
            or any(ord(char) < 0x20 or ord(char) == 0x7f for char in raw_path)):
        return None

    safe_component = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,200}\Z")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        parts = candidate.parts
        if ".." not in parts:
            if (not parts or len(parts) > 16
                    or any(not safe_component.fullmatch(part) for part in parts)):
                return None
            return "relative:" + "/".join(parts)
    return _safe_runtime_path_location(candidate, temporary_root)


def _safe_failure_parent(error: BaseException | None,
                         temporary_root: Path | None) -> tuple[str | None, str | None]:
    if _safe_failure_location(error, temporary_root) is None:
        return None, None
    filename = getattr(error, "filename", None)
    try:
        candidate = Path(os.fsdecode(os.fspath(filename)))
        if not candidate.is_absolute():
            candidate = Path(os.path.abspath(candidate))
        parent = candidate.parent
        parent_location = _safe_runtime_path_location(parent, temporary_root)
        if parent_location is None:
            return None, None
        if (parent_location.startswith("restore-temp:")
                or not isinstance(error, FileNotFoundError)):
            return parent_location, "unknown"
        return parent_location, _safe_directory_state(parent, temporary_root)
    except (OSError, TypeError, ValueError):
        return None, None


def _native_restore_failure(error: BaseException, captured_output: str,
                            temporary_root: Path | None = None) -> NativeRestoreError:
    """Keep only safe exception types, frames, path classes and numeric OS code."""
    failure_type = type(error).__name__
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", failure_type):
        failure_type = "Exception"
    frames = _safe_traceback_frames(error)
    chain = _exception_chain(error)
    reported_error = next((candidate for candidate in reversed(chain)
                           if candidate is not error
                           and type(candidate).__name__ in _SAFE_CAPTURED_EXCEPTION_TYPES), None)
    reported_type = (type(reported_error).__name__ if reported_error is not None
                     else _captured_failure_type(captured_output))
    reported_frames = (_safe_traceback_frames(reported_error)
                       if reported_error is not None else ())
    error_number = next((getattr(candidate, "errno", None)
                         for candidate in reversed(chain)
                         if type(getattr(candidate, "errno", None)) is int
                         and 0 <= getattr(candidate, "errno") <= 65535), None)
    if error_number is None:
        error_number = _captured_os_error_code(captured_output)
    path_error = next(
        (candidate for candidate in reversed(chain)
         if _safe_failure_location(candidate, temporary_root) is not None), None)
    failure_location = _safe_failure_location(path_error, temporary_root)
    failure_parent_location, failure_parent_state = _safe_failure_parent(
        path_error, temporary_root)
    reported_cwd = _safe_current_directory() if failure_location else None
    gpg_lines = [line for line in captured_output.splitlines()
                 if re.search(r"\bgpg(?:\[[^]]+\])?:", line, re.IGNORECASE)]
    category = safe_gpg_diagnostic_category("\n".join(gpg_lines))
    return NativeRestoreError(
        failure_type, frames, error_number, category, reported_type,
        reported_frames, failure_location, reported_cwd,
        failure_parent_location, failure_parent_state)


def _canonical_document_bytes(document: dict) -> bytes:
    """The exact bytes both approvers sign: sorted, compact JSON."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _rsa_pkcs1v15_sha256_verify(modulus: int, exponent: int,
                                message: bytes, signature: bytes) -> bool:
    """Pure-stdlib RSA PKCS#1 v1.5 / SHA-256 verification (trust store ships
    modulus/exponent, so no DER parsing is needed here)."""
    if not isinstance(modulus, int) or not isinstance(exponent, int):
        return False
    if modulus <= 0 or exponent <= 0 or exponent % 2 == 0 or exponent != 65537:
        return False
    key_bytes = (modulus.bit_length() + 7) // 8
    if key_bytes < 256 or len(signature) != key_bytes:
        return False
    signature_int = int.from_bytes(signature, "big")
    if signature_int >= modulus:
        return False
    encoded = pow(signature_int, exponent, modulus).to_bytes(key_bytes, "big")
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") \
        + hashlib.sha256(message).digest()
    padding = key_bytes - len(digest_info) - 3
    if padding < 8:
        return False
    expected = b"\x00\x01" + (b"\xff" * padding) + b"\x00" + digest_info
    return hmac.compare_digest(encoded, expected)


def _parse_utc(value, label: str) -> datetime:
    if not isinstance(value, str):
        raise RestoreInputError(f"emergency authorization {label} is invalid")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise RestoreInputError(
            f"emergency authorization {label} is invalid") from None
    return parsed.replace(tzinfo=timezone.utc)


def _restore_state_dir(site: str) -> Path:
    """Durable, installation-controlled state for consumed requests, the
    in-progress marker and the audit log. Never caller-supplied through the
    payload: the caller controls only the payload, not this location."""
    configured = os.environ.get("RESTORE_STATE_DIR")
    if configured:
        state_dir = Path(configured)
        if not state_dir.is_absolute():
            raise RestoreInputError("emergency restore state directory is unsafe")
        return state_dir / site
    return SITES_DIR / site / "private" / "restore-requests"


def _ensure_state_dir(site: str) -> Path:
    state_dir = _restore_state_dir(site)
    # Restore state is security-critical. Never follow a symlink at the
    # state directory or any ancestor, including a configured parent.
    for ancestor in (state_dir, *state_dir.parents):
        if ancestor.is_symlink():
            raise RestoreInputError("emergency restore state directory is unsafe")
    try:
        state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        if state_dir.is_symlink() or not state_dir.is_dir():
            raise RestoreInputError("emergency restore state directory is unsafe")
        state_dir.chmod(0o700)
    except OSError:
        raise RestoreInputError("emergency restore state directory is unavailable") from None
    return state_dir


def _append_audit(state_dir: Path, record: dict) -> None:
    """Append one verified hash-chain record under an interprocess file lock.

    Existing log lines are verified before appending. No password, key, or
    detached signature is recorded. A hash chain detects changes to retained
    earlier lines, but cannot prove that the complete log was not replaced
    or its tail removed: independent host-level retention is still needed.
    """
    audit_path = state_dir / "audit.jsonl"
    lock_path = state_dir / "audit.lock"
    if audit_path.is_symlink() or lock_path.is_symlink():
        raise RestoreInputError("emergency restore audit path is unsafe")
    try:
        flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW
        with os.fdopen(os.open(lock_path, flags, 0o600), "rb+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            previous_hash = ""
            if audit_path.exists():
                with os.fdopen(os.open(audit_path, os.O_RDONLY | os.O_NOFOLLOW),
                               "rb") as audit_input:
                    for line in audit_input:
                        if not line.endswith(b"\n"):
                            raise RestoreInputError("emergency restore audit chain is invalid")
                        item = json.loads(line)
                        if not isinstance(item, dict):
                            raise RestoreInputError("emergency restore audit chain is invalid")
                        stamped = dict(item)
                        supplied_hash = stamped.pop("hash", None)
                        if (not isinstance(supplied_hash, str)
                                or item.get("prev_hash") != previous_hash
                                or supplied_hash != hashlib.sha256(
                                    _canonical_document_bytes(stamped)).hexdigest()):
                            raise RestoreInputError("emergency restore audit chain is invalid")
                        previous_hash = hashlib.sha256(line.rstrip(b"\n")).hexdigest()
            entry = {**record, "prev_hash": previous_hash}
            entry["hash"] = hashlib.sha256(
                _canonical_document_bytes(entry)).hexdigest()
            line = _canonical_document_bytes(entry) + b"\n"
            with os.fdopen(os.open(audit_path,
                                   os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW,
                                   0o600), "ab") as audit_output:
                os.fchmod(audit_output.fileno(), 0o600)
                audit_output.write(line)
                audit_output.flush()
                os.fsync(audit_output.fileno())
    except (OSError, ValueError, UnicodeError):
        raise RestoreInputError("emergency restore audit path or chain is unsafe") from None


def _load_restore_trust_store(path: Path) -> dict:
    """Load the installation-provisioned trust store. The path comes from the
    RESTORE_TRUST_STORE environment variable, never from the restore payload,
    so a caller cannot substitute their own trust anchor."""
    try:
        store = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise RestoreInputError(
            "emergency restore trust store is missing or invalid") from None
    if not isinstance(store, dict):
        raise RestoreInputError("emergency restore trust store is invalid")
    if (store.get("schema_version") != 1
            or store.get("document_type") != EMERGENCY_RESTORE_TRUST_DOCUMENT_TYPE
            or store.get("provisioned") is not True):
        raise RestoreInputError(
            "emergency restore trust store is not provisioned")
    keys = store.get("keys")
    if not isinstance(keys, list) or not 1 <= len(keys) <= 8:
        raise RestoreInputError("emergency restore trust store is invalid")
    parsed = {}
    for entry in keys:
        if not isinstance(entry, dict):
            raise RestoreInputError("emergency restore trust store is invalid")
        key_id = entry.get("key_id")
        if (not isinstance(key_id, str) or not KEY_ID_PATTERN.fullmatch(key_id)
                or key_id in parsed):
            raise RestoreInputError("emergency restore trust store is invalid")
        try:
            modulus = int.from_bytes(
                base64.b64decode(entry.get("modulus_b64", ""), validate=True), "big")
            exponent = int.from_bytes(
                base64.b64decode(entry.get("exponent_b64", ""), validate=True), "big")
        except (ValueError, TypeError):
            raise RestoreInputError(
                "emergency restore trust store is invalid") from None
        if modulus.bit_length() < 2048 or exponent != 65537:
            raise RestoreInputError("emergency restore trust store is invalid")
        purposes = entry.get("purposes")
        if not isinstance(purposes, list) or not all(
                isinstance(item, str) for item in purposes):
            raise RestoreInputError("emergency restore trust store is invalid")
        parsed[key_id] = {
            "modulus": modulus, "exponent": exponent, "purposes": purposes,
            "approver_identity": entry.get("approver_identity"),
            "approver_role": entry.get("approver_role"),
            "not_before_utc": entry.get("not_before_utc"),
            "not_after_utc": entry.get("not_after_utc"),
        }
    return parsed


def _verified_backup_paths(site: str, backup_set: str) -> dict[str, Path]:
    """The artifact checks _native_restore already performed, factored out so
    production authorization can bind to the exact files before any mutation.
    Error messages are unchanged from the original inline checks."""
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
        raise RestoreInputError(
            "required restore artifact directory is missing") from None
    for role, path in paths.items():
        try:
            resolved_path = path.resolve(strict=True)
            valid_path = resolved_path.parent == resolved_backup_dir
            valid_file = path.is_file() and path.stat().st_size > 0
        except OSError:
            valid_path = valid_file = False
        if path.is_symlink() or not valid_path or not valid_file:
            raise RestoreInputError(
                f"required restore artifact is missing or unsafe: {role}")
    return paths


def _artifact_hashes(paths: dict[str, Path]) -> dict[str, str]:
    hashes = {}
    for role, path in paths.items():
        with path.open("rb") as stream:
            hashes[role] = _sha256_stream(stream)
    return hashes

def _verify_staged_restore_hashes(staged_paths: dict[str, Path],
                                  expected_hashes: dict[str, str] | None) -> None:
    """Compare staged files with the signed pre-restore artifact digests.

    The source may change after authorization but before the copy starts.
    Rechecking the actual staged bytes before invoking Frappe closes that
    time-of-check/time-of-use window for production recovery.
    """
    if expected_hashes is not None and _artifact_hashes(staged_paths) != expected_hashes:
        raise RestoreInputError(
            "restore artifact content changed after emergency authorization")



def validate_emergency_authorization(document, signature_1_b64, signature_2_b64,
                                     *, site: str, backup_set: str,
                                     artifact_hashes: dict, now: datetime,
                                     trust_store_path: Path,
                                     state_dir: Path) -> tuple[str, list]:
    """Verify a production emergency-restore authorization before any data
    mutation. Returns (request_id, approvals). Raises RestoreInputError on
    every refusal; no secret or signature value is ever in a message."""
    if not isinstance(document, dict) or tuple(sorted(document)) != tuple(
            sorted(EMERGENCY_DOCUMENT_KEYS)):
        raise RestoreInputError("emergency restore authorization is invalid")
    if document["schema_version"] != EMERGENCY_RESTORE_SCHEMA_VERSION:
        raise RestoreInputError("emergency restore authorization is invalid")
    if document["document_type"] != EMERGENCY_RESTORE_DOCUMENT_TYPE:
        raise RestoreInputError("emergency restore authorization is invalid")
    if document["site"] != site or document["target"] != "production":
        raise RestoreInputError(
            "emergency restore authorization does not match this restore")
    if document["backup_set"] != backup_set:
        raise RestoreInputError(
            "emergency restore authorization does not match this backup set")
    if document["backup_sha256"] != artifact_hashes:
        raise RestoreInputError(
            "emergency restore authorization does not match the backup artifacts")
    request_id = document["request_id"]
    if not isinstance(request_id, str) or not EMERGENCY_REQUEST_ID.fullmatch(request_id):
        raise RestoreInputError("emergency restore authorization is invalid")
    issued = _parse_utc(document["issued_utc"], "issued time")
    expires = _parse_utc(document["expires_utc"], "expiry time")
    if expires <= issued or not issued <= now <= expires:
        raise RestoreInputError("emergency restore authorization is expired or not yet valid")
    approvals = document["approvals"]
    if not isinstance(approvals, list) or len(approvals) != 2:
        raise RestoreInputError(
            "emergency restore requires exactly two distinct approvers")
    seen_identities, seen_roles, seen_keys = set(), set(), set()
    for approval in approvals:
        if not isinstance(approval, dict) or tuple(sorted(approval)) != tuple(
                sorted(EMERGENCY_APPROVAL_KEYS)):
            raise RestoreInputError("emergency restore authorization is invalid")
        identity = approval["approver_identity"]
        role = approval["approver_role"]
        key_id = approval["key_id"]
        if not isinstance(identity, str) or not identity \
                or not isinstance(role, str) or not isinstance(key_id, str):
            raise RestoreInputError("emergency restore authorization is invalid")
        if identity.lower() in seen_identities or role in seen_roles \
                or key_id in seen_keys:
            raise RestoreInputError(
                "emergency restore approvers must be distinct people, roles and keys")
        seen_identities.add(identity.lower())
        seen_roles.add(role)
        seen_keys.add(key_id)
    if seen_roles != {"course-owner"} | (seen_roles & {"general-manager", "recovery-authority"}) \
            or "course-owner" not in seen_roles or len(seen_roles) != 2:
        raise RestoreInputError(
            "emergency restore requires one Course Owner and one General Manager "
            "or designated recovery authority")
    trust_store = _load_restore_trust_store(trust_store_path)
    raw_document = _canonical_document_bytes(document)
    for approval, signature_b64 in zip(approvals, (signature_1_b64, signature_2_b64)):
        key = trust_store.get(approval["key_id"])
        if key is None:
            raise RestoreInputError("emergency restore approver key is unknown")
        if EMERGENCY_RESTORE_KEY_PURPOSE not in key["purposes"]:
            raise RestoreInputError(
                "emergency restore approver key is not authorized for restore")
        if key["approver_identity"] != approval["approver_identity"] \
                or key["approver_role"] != approval["approver_role"]:
            raise RestoreInputError(
                "emergency restore approver does not match its trust-store binding")
        not_before = _parse_utc(key["not_before_utc"], "key validity start")
        not_after = _parse_utc(key["not_after_utc"], "key validity end")
        if not not_before <= now <= not_after:
            raise RestoreInputError("emergency restore approver key is expired or not yet valid")
        try:
            signature = base64.b64decode(signature_b64, validate=True)
        except (ValueError, TypeError):
            raise RestoreInputError("emergency restore signature is invalid") from None
        if not _rsa_pkcs1v15_sha256_verify(
                key["modulus"], key["exponent"], raw_document, signature):
            raise RestoreInputError("emergency restore signature is invalid")
    if (state_dir / f"{request_id}.json").exists():
        raise RestoreInputError("emergency restore request was already used")
    if (state_dir / "in-progress.json").exists():
        raise RestoreInputError(
            "a previous emergency restore did not complete; resolve it per the "
            "recovery procedure before starting another production restore")
    return request_id, approvals


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


def _validate_payload(payload: dict):
    """Validate the stdin payload. Target classification is fail-closed:
    omitting ``target`` means production. A disposable target is only a
    declaration here; _native_restore enforces that a disposable site is
    genuinely a restore site and never the production site. Authorization
    fields are passed through untouched (never logged) for production
    validation inside _native_restore, before any mutation."""
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
    target = payload.get("target", "production")
    if target not in ("disposable", "production"):
        raise RestoreInputError("restore target is invalid")
    if target == "disposable" and (
            site == PRODUCTION_SITE
            or not any(marker in site for marker in DISPOSABLE_SITE_MARKERS)):
        raise RestoreInputError(
            "a disposable restore must target a restore or recovery site, "
            "never the production site")
    pre_restore_backup_set = payload.get("pre_restore_backup_set")
    if pre_restore_backup_set is not None and (
            not isinstance(pre_restore_backup_set, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", pre_restore_backup_set)):
        raise RestoreInputError("pre-restore backup-set name is invalid")
    authorization = payload.get("authorization")
    signature_1 = payload.get("authorization_signature_1")
    signature_2 = payload.get("authorization_signature_2")
    if target == "production" and (
            authorization is None or signature_1 is None or signature_2 is None):
        raise RestoreInputError(
            "a production restore requires a two-approver emergency authorization")
    return (site, backup_set, encryption_key, db_root_password, admin_password,
            target, pre_restore_backup_set, authorization, signature_1, signature_2)


def _sha256_stream(stream) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def _same_file_state(left, right) -> bool:
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    # Windows can finalize creation-time metadata after a newly written file
    # is opened. The shipped restore runs in Linux, where ctime is a reliable
    # extra in-place-change signal. Keep that stronger check there; inode,
    # device, size, mtime and the staged-content hash remain checked on both.
    if os.name != "nt":
        identity += ("st_ctime_ns",)
    return all(getattr(left, field) == getattr(right, field) for field in identity)


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
                    db_root_password: str, admin_password: str,
                    target: str = "production",
                    pre_restore_backup_set: str | None = None,
                    authorization=None, signature_1=None, signature_2=None,
                    context_writer=None) -> None:
    """Gate, then run, a restore. All production checks happen here, before
    _run_native_restore mutates anything: pre-restore preservation, the
    two-approver authorization bound to the exact artifact hashes, single-use
    consumption, and the in-progress marker. Disposable restores skip
    authorization/consumption but are still audit-logged, without secrets."""
    paths = _verified_backup_paths(site, backup_set)
    hashes = _artifact_hashes(paths)
    state_dir = _ensure_state_dir(site)
    request_id = None
    approvals: list = []
    audit_base = {
        "site": site, "target": target, "backup_set": backup_set,
        "backup_sha256": hashes,
    }
    if target == "production":
        if pre_restore_backup_set is None or pre_restore_backup_set == backup_set:
            raise RestoreInputError(
                "a production restore requires a distinct pre-restore backup "
                "set preserving the live site's current data")
        pre_paths = _verified_backup_paths(site, pre_restore_backup_set)
        audit_base["pre_restore_backup_set"] = pre_restore_backup_set
        audit_base["pre_restore_backup_sha256"] = _artifact_hashes(pre_paths)
        trust_store_value = os.environ.get("RESTORE_TRUST_STORE")
        if not trust_store_value:
            raise RestoreInputError(
                "a production restore requires a provisioned emergency restore "
                "trust store; no trust store is configured")
        request_id, approvals = validate_emergency_authorization(
            authorization, signature_1, signature_2, site=site,
            backup_set=backup_set, artifact_hashes=hashes,
            now=datetime.now(timezone.utc),
            trust_store_path=Path(trust_store_value), state_dir=state_dir)
        audit_base["request_id"] = request_id
        audit_base["approvals"] = approvals
        consumed_path = state_dir / f"{request_id}.json"
        try:
            with os.fdopen(os.open(consumed_path, os.O_WRONLY | os.O_CREAT
                                   | os.O_EXCL, 0o600), "w") as stream:
                json.dump(audit_base, stream, sort_keys=True)
        except FileExistsError:
            raise RestoreInputError(
                "emergency restore request was already used") from None
        marker_path = state_dir / "in-progress.json"
        # Exclusive creation closes the check-then-create race: a second
        # signed request can never overwrite another active restore marker.
        try:
            with os.fdopen(os.open(marker_path, os.O_WRONLY | os.O_CREAT
                                   | os.O_EXCL, 0o600), "w") as stream:
                json.dump({"request_id": request_id, "site": site,
                           "backup_set": backup_set}, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            raise RestoreInputError(
                "another emergency restore is in progress; resolve it first") from None
        _append_audit(state_dir, {**audit_base, "outcome": "started"})
        try:
            _run_native_restore(site, backup_set, encryption_key,
                                db_root_password, admin_password,
                                context_writer=context_writer,
                                expected_hashes=hashes)
        except Exception:
            # Native Frappe may have partially overwritten the site before
            # failing. Keep the in-progress marker until independently
            # reviewed, even though the request is already spent.
            _append_audit(state_dir, {**audit_base, "outcome": "failed"})
            raise
        _append_audit(state_dir, {**audit_base, "outcome": "completed"})
        # Only a fully successful and durably audited restore may clear the
        # hold; if this fails, recovery remains blocked for support review.
        try:
            marker_path.unlink()
        except OSError:
            raise RestoreInputError(
                "completed restore needs support review of its state marker") from None
        return
    _append_audit(state_dir, {**audit_base, "outcome": "started"})
    try:
        _run_native_restore(site, backup_set, encryption_key,
                            db_root_password, admin_password,
                            context_writer=context_writer)
    except Exception:
        _append_audit(state_dir, {**audit_base, "outcome": "failed"})
        raise
    _append_audit(state_dir, {**audit_base, "outcome": "completed"})


def _run_native_restore(site: str, backup_set: str, encryption_key: str,
                        db_root_password: str, admin_password: str,
                        context_writer=None,
                        expected_hashes: dict[str, str] | None = None) -> None:
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

    # Bench's pinned `frappe_cmd` changes to bench/sites, and Frappe's native
    # restore command then calls frappe.init(site) with its default relative
    # sites_path. Keep both details so logger and file-archive paths match the
    # CLI's native `--strip 2` extraction semantics.
    caller_cwd = Path.cwd()
    initialized = False
    captured = io.StringIO()
    working_dir = None
    try:
        os.chdir(SITES_DIR)
        import frappe
        import frappe.utils
        from frappe.commands.site import _restore
        from frappe.utils.synchronization import filelock

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
            _verify_staged_restore_hashes(staged_paths, expected_hashes)
            with safe_mariadb_credential_transport(frappe, working_dir):
                with safe_gpg_transport(frappe, encryption_key):
                    if context_writer is not None:
                        cwd_class, log_directory_state = _safe_restore_context(working_dir)
                        try:
                            context_writer.write(
                                f"Restore context before frappe.init: cwd={cwd_class}; "
                                f"../logs={log_directory_state}\n")
                            context_writer.flush()
                        except (OSError, ValueError):
                            pass
                    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                        frappe.init(site)
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
            raise _native_restore_failure(
                error, captured.getvalue(), working_dir) from None
    except Exception as error:
        # Native restore diagnostics can include command context. Preserve only
        # allowlisted classes/frames and a path relative to approved roots.
        raise _native_restore_failure(
            error, captured.getvalue(), working_dir) from None
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
        (site, backup_set, encryption_key, db_root_password, admin_password,
         target, pre_restore_backup_set, authorization, signature_1,
         signature_2) = _validate_payload(payload)
        _native_restore(site, backup_set, encryption_key,
                        db_root_password, admin_password, target=target,
                        pre_restore_backup_set=pre_restore_backup_set,
                        authorization=authorization, signature_1=signature_1,
                        signature_2=signature_2, context_writer=stdout)
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
        if error.reported_frames:
            details.append("reported frames: " + ",".join(error.reported_frames))
        if error.reported_cwd:
            details.append("reported CWD: " + error.reported_cwd)
        if error.failure_location:
            details.append("reported path: " + error.failure_location)
        if error.failure_parent_location and error.failure_parent_state:
            details.append(
                "reported parent: " + error.failure_parent_location
                + " (" + error.failure_parent_state + ")")
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

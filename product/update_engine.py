#!/usr/bin/env python3
"""Fail-closed update engine for the TOEFL House ERP desktop product.

This module is the decision layer of the Windows "Check for Updates" workflow.
The Windows launcher owns the GUI, HTTPS transport and Docker orchestration;
this engine owns the security policy that decides whether an already-downloaded
release may modify an installed site, and performs the supported migration.

Design rules enforced here (see docs/engineering/SAFE-UPDATES.md):

* Updates are prebuilt images.  Nothing here builds Frappe, Node assets or an
  application image on the customer's PC.
* A release is only considered when its manifest is signed by a key shipped in
  the package trust store.  A bare SHA-256 sidecar is corruption detection,
  never publisher identity.
* Prebuilt image bytes, exact source revision, exact version, release sequence
  and compatibility are bound together before any Docker import.
* An update is refused unless a current, independently stored, encrypted and
  verified native Frappe backup receipt exists, its artifacts still hash to
  the receipt, the Owner's signed recovery/key-custody authorization is valid,
  disk space is sufficient, the existing site and named database volume are
  intact, and the release is production-authorized.
* Migrations are not assumed to be reversible.  The engine takes a record
  census before ``bench migrate`` and refuses a release that would reduce any
  counted business record.  On failure it reports a recovery-required state;
  it never restores over a live site and never deletes customer data.

The engine is standard-library only so the same file runs inside the pinned
product image (``/product/update_engine.py``), on provider packaging machines,
and in the repository test suite.

Machine protocol (no free-text log parsing):

* request/response are JSON documents read from ``--request`` /
  ``$TH_UPDATE_REQUEST`` and written to ``--response`` / ``$TH_UPDATE_RESPONSE``
  (or stdout).  Secrets are never echoed.
* The Windows launcher only acts on ``decision == "allow"``.
* Every human message is a stable code from :data:`MESSAGE_CODES`; the
  bilingual English/Dari catalog lives in
  ``product/windows/updater-strings.json`` and is verified by tests.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

PRODUCT = "TOEFL House ERP"
DOCUMENT_UPDATE = "toefl-house-erp-update"
DOCUMENT_UPDATE_SIGNATURE = "toefl-house-erp-update-signature"
DOCUMENT_RECOVERY = "toefl-house-erp-recovery-authorization"
DOCUMENT_RECOVERY_SIGNATURE = "toefl-house-erp-recovery-authorization-signature"
DOCUMENT_TRUST = "toefl-house-erp-update-trust-store"
DOCUMENT_CHANNEL = "toefl-house-erp-update-channels"
DOCUMENT_RESPONSE = "toefl-house-erp-update-engine-response"
ENGINE_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
TRUST_SCHEMA_VERSION = 1
CHANNEL_SCHEMA_VERSION = 1
SITE_NAME = "toeflhouse.localhost"
IMAGE_TAG = "toefl-house-erp-app:local"
DB_VOLUME = "toefl-house-erp_db-data"
MAX_JSON_BYTES = 256 * 1024
MAX_ARCHIVE_BYTES = 16 * 1024 ** 3
MIN_ARCHIVE_BYTES = 4096
MAX_METADATA_BYTES = 4 * 1024 * 1024
MIN_FREE_BYTES_FLOOR = 30 * 1024 ** 3
# Release sequence numbers are date-derived build numbers (see
# release_sequence); the ceiling stays inside a signed 32-bit integer.
MAX_SEQUENCE = 2_147_483_647
MAX_BACKUP_MAX_AGE_HOURS = 24
SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
KEY_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
SAFE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,95}$")
SHA256_TAG = re.compile(r"^sha256:[0-9a-f]{64}$")
RELEASE_STATUSES = ("TEST PACKAGE - NO REAL DATA", "PRODUCTION RELEASE")
AUTHORIZATIONS = ("REJECT", "AUTHORIZED")
MIGRATION_MODES = ("supported", "none")
SIGNATURE_ALGORITHMS = ("rsa-pkcs1v15-sha256",)
KEY_PURPOSES = ("update-manifest", "recovery-authorization")
SAFE_HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
SAFE_ASSET = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
# Business records that must never shrink across a supported migration.  These
# are native doctypes, so the same census works on every supported release; an
# application that is not installed is recorded as absent, never as zero.
CENSUS_DOCTYPES = (
    "Student",
    "Student Group",
    "Course",
    "Program",
    "Sales Invoice",
    "Payment Entry",
    "Attendance",
    "Salary Slip",
    "Employee",
    "User",
    "Role",
)
# The eight role desks must survive every supported update.
ROLE_DESK_PAGES = (
    "th-owner-cockpit",
    "th-reception-desk",
    "th-academic-desk",
    "th-finance-desk",
    "th-teacher-desk",
    "th-operations-desk",
    "th-configuration",
    "th-academic-setup",
)
REQUIRED_APPS = (
    "frappe",
    "erpnext",
    "education",
    "payments",
    "hrms",
    "foundation_security",
    "toefl_house",
)
PLAN_PHASES = (
    "quiesce",
    "verify",
    "import",
    "migrate",
    "verify-data",
    "start",
    "health",
)
JOURNAL_TERMINAL_STATES = ("idle", "completed", "rolled-back")

# Every code the engine can emit.  The Windows catalog must define English and
# Dari text for each one; tests/foundation/test_update_engine.py enforces it.
MESSAGE_CODES = frozenset({
    "trust.not_provisioned",
    "trust.invalid",
    "trust.key_expired",
    "trust.key_unknown",
    "channel.invalid",
    "channel.disabled",
    "release.manifest.missing",
    "release.manifest.invalid",
    "release.signature.invalid",
    "release.archive.missing",
    "release.archive.size_mismatch",
    "release.archive.hash_mismatch",
    "release.archive.identity_mismatch",
    "release.image.labels_mismatch",
    "policy.release_not_authorized",
    "policy.release_not_production",
    "compat.host_updater_too_old",
    "compat.engine_schema_unsupported",
    "compat.installed_version_unknown",
    "compat.installed_too_old",
    "compat.installed_too_new",
    "compat.downgrade",
    "compat.sequence_gap",
    "compat.schema_unsupported",
    "preflight.not_installed",
    "preflight.site.credentials_missing",
    "preflight.site.config_missing",
    "preflight.site.config_unreadable",
    "preflight.volume.missing",
    "preflight.volume.unverified",
    "preflight.disk.insufficient",
    "preflight.services.unhealthy",
    "preflight.image.missing",
    "preflight.image.identity_mismatch",
    "preflight.backup.receipt_missing",
    "preflight.backup.receipt_unreadable",
    "preflight.backup.receipt_invalid",
    "preflight.backup.stale",
    "preflight.backup.artifact_invalid",
    "preflight.recovery.authorization_missing",
    "preflight.recovery.authorization_invalid",
    "preflight.recovery.authorization_expired",
    "preflight.recovery.binding_mismatch",
    "preflight.recovery.key_custody_unverified",
    "preflight.recovery.rehearsal_unverified",
    "preflight.update_in_progress",
    "apply.site_invalid",
    "apply.counts_unavailable",
    "apply.migrate_failed",
    "apply.records_lost",
    "apply.apps_missing",
    "apply.role_desk_missing",
    "apply.health_failed",
    "engine.request_invalid",
    "engine.unexpected",
    "warning.backup_age_near_limit",
    "warning.not_rollback_safe",
})


# --------------------------------------------------------------------------
# Errors and strict helpers
# --------------------------------------------------------------------------

class UpdateError(ValueError):
    """A safe, categorized update failure with a stable message code."""

    def __init__(self, code: str, detail: str = ""):
        if code not in MESSAGE_CODES:
            raise AssertionError(f"unknown update message code: {code}")
        super().__init__(code + (": " + detail if detail else ""))
        self.code = code
        self.detail = detail[:400]


def refuse(code: str, detail: str = "") -> UpdateError:
    return UpdateError(code, detail)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise refuse("engine.request_invalid", f"{label} must be a JSON object")
    return value


def _require_exact_keys(value: Mapping[str, object], allowed: Sequence[str], required: Sequence[str],
                        label: str, *, code: str = "engine.request_invalid") -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise refuse(code, f"{label} has unsupported keys: {','.join(unknown)}")
    missing = [key for key in required if key not in value]
    if missing:
        raise refuse(code, f"{label} is missing keys: {','.join(missing)}")


def _text(value: object, label: str, *, pattern: re.Pattern[str] | None = None,
          maximum: int = 512, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise refuse("engine.request_invalid", f"{label} must be a string")
    if not allow_empty and not value:
        raise refuse("engine.request_invalid", f"{label} must not be empty")
    if len(value) > maximum:
        raise refuse("engine.request_invalid", f"{label} is too long")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise refuse("engine.request_invalid", f"{label} contains control characters")
    if pattern is not None and not pattern.fullmatch(value):
        raise refuse("engine.request_invalid", f"{label} has an unsupported format")
    return value


def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if not _is_int(value) or value < minimum or value > maximum:
        raise refuse("engine.request_invalid", f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise refuse("engine.request_invalid", f"{label} must be true or false")
    return value


def parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise refuse("engine.request_invalid", f"{label} has no UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise refuse("engine.request_invalid", f"{label} has an invalid UTC timestamp") from None
    if parsed.tzinfo is None:
        raise refuse("engine.request_invalid", f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_inside(root: Path, relative: object, label: str) -> Path:
    """Resolve a caller-supplied relative path without leaving ``root``."""
    value = _text(relative, label, maximum=512)
    if "\\" in value:
        raise refuse("engine.request_invalid", f"{label} must use forward slashes")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise refuse("engine.request_invalid", f"{label} must stay inside the product folder")
    candidate = (root / Path(*pure.parts)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        raise refuse("engine.request_invalid", f"{label} escapes the product folder") from None
    return candidate


_MISSING_CODES = {
    "release manifest": "release.manifest.missing",
    "release signature": "release.signature.invalid",
    "trust store": "trust.not_provisioned",
    "update channel": "channel.invalid",
    "backup receipt": "preflight.backup.receipt_missing",
    "recovery authorization": "preflight.recovery.authorization_missing",
    "recovery signature": "preflight.recovery.authorization_missing",
}
_INVALID_CODES = {
    "release manifest": "release.manifest.invalid",
    "release signature": "release.signature.invalid",
    "trust store": "trust.invalid",
    "update channel": "channel.invalid",
    "backup receipt": "preflight.backup.receipt_unreadable",
    "recovery authorization": "preflight.recovery.authorization_invalid",
    "recovery signature": "preflight.recovery.authorization_invalid",
}


def load_json_file(path: Path, label: str, *, limit: int = MAX_JSON_BYTES) -> dict:
    if path.is_symlink() or not path.is_file():
        raise UpdateError(_MISSING_CODES.get(label, "release.manifest.missing"), f"{label} is missing")
    try:
        size = path.stat().st_size
    except OSError:
        raise UpdateError(_MISSING_CODES.get(label, "release.manifest.missing"), f"{label} is unreadable") from None
    if size <= 0 or size > limit:
        raise UpdateError(_INVALID_CODES.get(label, "release.manifest.invalid"), f"{label} has an unsupported size")
    try:
        raw = path.read_bytes()
    except OSError:
        raise UpdateError(_MISSING_CODES.get(label, "release.manifest.missing"), f"{label} is unreadable") from None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise UpdateError(_INVALID_CODES.get(label, "release.manifest.invalid"),
                          f"{label} is not valid UTF-8 JSON") from None
    if not isinstance(value, dict):
        raise UpdateError(_INVALID_CODES.get(label, "release.manifest.invalid"),
                          f"{label} must be a JSON object")
    return value


# --------------------------------------------------------------------------
# Minimal DER reader and RSA PKCS#1 v1.5 / SHA-256 verification
# --------------------------------------------------------------------------

def _der_tlv(data: bytes, offset: int, label: str) -> tuple[int, bytes, int]:
    """Read one DER tag/length/value triple with strict bounds checking."""
    if offset + 2 > len(data):
        raise refuse("trust.invalid", f"{label}: truncated DER header")
    tag = data[offset]
    length_byte = data[offset + 1]
    cursor = offset + 2
    if length_byte & 0x80:
        count = length_byte & 0x7F
        if count == 0 or count > 4 or cursor + count > len(data):
            raise refuse("trust.invalid", f"{label}: unsupported DER length")
        length = int.from_bytes(data[cursor:cursor + count], "big")
        cursor += count
    else:
        length = length_byte
    end = cursor + length
    if end > len(data) or length < 0:
        raise refuse("trust.invalid", f"{label}: truncated DER value")
    return tag, data[cursor:end], end


def parse_rsa_public_key(der: bytes) -> tuple[int, int]:
    """Extract (modulus, exponent) from a PKIX SubjectPublicKeyInfo DER blob.

    The trust store ships ``modulus_b64``/``exponent_b64``; the provider tool
    derives them from a PEM key through this function, so both sides agree on
    one encoding and no PEM parser is needed at update time.
    """
    if not isinstance(der, bytes) or not 200 <= len(der) <= 2048:
        raise refuse("trust.invalid", "public key DER has an unsupported size")
    tag, sequence, end = _der_tlv(der, 0, "public key")
    if tag != 0x30 or end != len(der):
        raise refuse("trust.invalid", "public key is not a single DER sequence")
    tag, algorithm, sequence_cursor = _der_tlv(sequence, 0, "algorithm")
    if tag != 0x30:
        raise refuse("trust.invalid", "public key algorithm is malformed")
    tag, oid, algorithm_cursor = _der_tlv(algorithm, 0, "algorithm OID")
    if tag != 0x06 or oid != bytes.fromhex("2a864886f70d010101"):
        raise refuse("trust.invalid", "public key is not RSA")
    if algorithm_cursor < len(algorithm):
        # RSA AlgorithmIdentifier parameters are the DER NULL value.
        tag, parameters, algorithm_cursor = _der_tlv(algorithm, algorithm_cursor, "algorithm parameters")
        if tag != 0x05 or parameters or algorithm_cursor != len(algorithm):
            raise refuse("trust.invalid", "public key algorithm parameters are unexpected")
    tag, bit_string, cursor = _der_tlv(sequence, sequence_cursor, "bit string")
    if tag != 0x03 or not bit_string or bit_string[0] != 0x00:
        raise refuse("trust.invalid", "public key bit string is malformed")
    if cursor != len(sequence):
        raise refuse("trust.invalid", "public key has trailing data")
    tag, rsa_sequence, end = _der_tlv(bit_string[1:], 0, "RSA key")
    if tag != 0x30 or end != len(bit_string) - 1:
        raise refuse("trust.invalid", "RSA public key is malformed")
    tag, modulus, cursor = _der_tlv(rsa_sequence, 0, "modulus")
    if tag != 0x02 or not modulus:
        raise refuse("trust.invalid", "RSA modulus is malformed")
    tag, exponent, cursor = _der_tlv(rsa_sequence, cursor, "exponent")
    if tag != 0x02 or not exponent or cursor != len(rsa_sequence):
        raise refuse("trust.invalid", "RSA exponent is malformed")
    if modulus[0] & 0x80:
        raise refuse("trust.invalid", "RSA modulus is not a positive integer")
    return int.from_bytes(modulus, "big"), int.from_bytes(exponent, "big")


def rsa_pkcs1v15_sha256_verify(modulus: int, exponent: int, message: bytes, signature: bytes) -> bool:
    """Strict RSA PKCS#1 v1.5 / SHA-256 detached-signature verification."""
    if not _is_int(modulus) or not _is_int(exponent):
        return False
    if modulus <= 0 or exponent <= 0 or exponent % 2 == 0:
        return False
    key_bytes = (modulus.bit_length() + 7) // 8
    if key_bytes < 256 or len(signature) != key_bytes:
        return False
    signature_int = int.from_bytes(signature, "big")
    if signature_int >= modulus:
        return False
    encoded = pow(signature_int, exponent, modulus).to_bytes(key_bytes, "big")
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(message).digest()
    padding = key_bytes - len(digest_info) - 3
    if padding < 8:
        return False
    expected = b"\x00\x01" + (b"\xff" * padding) + b"\x00" + digest_info
    return len(encoded) == len(expected) and _constant_time_equal(encoded, expected)


def _constant_time_equal(left: bytes, right: bytes) -> bool:
    if len(left) != len(right):
        return False
    result = 0
    for first, second in zip(left, right):
        result |= first ^ second
    return result == 0


# --------------------------------------------------------------------------
# Trust store and update channel
# --------------------------------------------------------------------------

def load_trust_store(path: Path, *, now: datetime) -> dict:
    try:
        return _load_trust_store(path, now=now)
    except UpdateError as error:
        if error.code == "engine.request_invalid":
            raise UpdateError("trust.invalid", error.detail) from None
        raise


def _load_trust_store(path: Path, *, now: datetime) -> dict:
    store = load_json_file(path, "trust store")
    _require_exact_keys(store, ("schema_version", "document_type", "product", "provisioned", "keys"),
                        ("schema_version", "document_type", "product", "provisioned", "keys"),
                        "trust store", code="trust.invalid")
    if (store["schema_version"] != TRUST_SCHEMA_VERSION
            or store["document_type"] != DOCUMENT_TRUST
            or store["product"] != PRODUCT):
        raise refuse("trust.invalid", "trust store header is not supported")
    provisioned = _boolean(store["provisioned"], "trust.provisioned")
    keys = store["keys"]
    if not isinstance(keys, list):
        raise refuse("trust.invalid", "trust store keys must be a list")
    if not provisioned:
        if keys:
            raise refuse("trust.invalid", "an unprovisioned trust store must not list keys")
        raise refuse("trust.not_provisioned",
                     "no provider release signing key is installed; updates stay disabled")
    if not 1 <= len(keys) <= 8:
        raise refuse("trust.invalid", "trust store must contain between 1 and 8 keys")
    seen: set[str] = set()
    parsed: list[dict] = []
    for entry in keys:
        entry = _require_object(entry, "trust key")
        _require_exact_keys(entry, ("key_id", "algorithm", "purposes", "modulus_b64", "exponent_b64",
                                    "not_before_utc", "not_after_utc"),
                            ("key_id", "algorithm", "purposes", "modulus_b64", "exponent_b64",
                             "not_before_utc", "not_after_utc"), "trust key", code="trust.invalid")
        key_id = _text(entry["key_id"], "trust.key_id", pattern=KEY_ID, maximum=64)
        if key_id in seen:
            raise refuse("trust.invalid", "trust store contains a duplicate key id")
        seen.add(key_id)
        if entry["algorithm"] not in SIGNATURE_ALGORITHMS:
            raise refuse("trust.invalid", "trust store contains an unsupported signature algorithm")
        purposes = entry["purposes"]
        if (not isinstance(purposes, list) or not purposes or len(purposes) > 4
                or not all(isinstance(item, str) and item in KEY_PURPOSES for item in purposes)
                or len(set(purposes)) != len(purposes)):
            raise refuse("trust.invalid", "trust key purposes are invalid")
        try:
            modulus_bytes = base64.b64decode(_text(entry["modulus_b64"], "trust.modulus_b64", maximum=1024),
                                             validate=True)
            exponent_bytes = base64.b64decode(_text(entry["exponent_b64"], "trust.exponent_b64", maximum=16),
                                              validate=True)
        except (ValueError, TypeError):
            raise refuse("trust.invalid", "trust key material is not valid base64") from None
        if len(modulus_bytes) < 256 or len(modulus_bytes) > 512 or modulus_bytes[0] == 0:
            raise refuse("trust.invalid", "trust key modulus has an unsupported size")
        modulus = int.from_bytes(modulus_bytes, "big")
        exponent = int.from_bytes(exponent_bytes, "big")
        if exponent != 65537:
            raise refuse("trust.invalid", "trust key exponent must be 65537")
        not_before = parse_utc(entry["not_before_utc"], "trust.not_before_utc")
        not_after = parse_utc(entry["not_after_utc"], "trust.not_after_utc")
        if not_after <= not_before:
            raise refuse("trust.invalid", "trust key validity window is inverted")
        parsed.append({
            "key_id": key_id,
            "algorithm": entry["algorithm"],
            "purposes": tuple(purposes),
            "modulus": modulus,
            "exponent": exponent,
            "not_before": not_before,
            "not_after": not_after,
        })
    return {"provisioned": True, "keys": parsed, "now": now}


def select_key(store: dict, key_id: str, purpose: str, *, now: datetime) -> dict:
    if purpose not in KEY_PURPOSES:
        raise AssertionError("unsupported key purpose")
    for key in store["keys"]:
        if key["key_id"] != key_id or purpose not in key["purposes"]:
            continue
        if now < key["not_before"] or now > key["not_after"]:
            raise refuse("trust.key_expired", f"signing key {key_id} is outside its validity window")
        return key
    raise refuse("trust.key_unknown", f"signing key {key_id} is not trusted for {purpose}")


def _valid_host(host: object) -> bool:
    if not isinstance(host, str) or not 1 <= len(host) <= 253 or host != host.strip().lower():
        return False
    if not SAFE_HOST.fullmatch(host):
        return False
    return not host.endswith((".local", ".localhost", ".internal", ".invalid", ".test", ".example"))


def parse_https_url(url: object, allowed_hosts: Sequence[str]) -> str:
    from urllib.parse import urlsplit
    value = _text(url, "channel URL", maximum=512, pattern=None)
    try:
        parts = urlsplit(value)
    except ValueError:
        raise refuse("channel.invalid", "update URL is not parseable") from None
    if parts.scheme != "https":
        raise refuse("channel.invalid", "update URLs must use https")
    if parts.username or parts.password:
        raise refuse("channel.invalid", "update URLs must not embed credentials")
    if not parts.hostname or parts.hostname.lower() not in {host.lower() for host in allowed_hosts}:
        raise refuse("channel.invalid", "update URL host is not on the channel allowlist")
    if parts.port not in (None, 443):
        raise refuse("channel.invalid", "update URL uses an unsupported port")
    if parts.fragment:
        raise refuse("channel.invalid", "update URL must not contain a fragment")
    if not parts.path.startswith("/"):
        raise refuse("channel.invalid", "update URL path is invalid")
    return value


def load_channel_config(path: Path, *, channel_id: str | None) -> dict:
    try:
        return _load_channel_config(path, channel_id=channel_id)
    except UpdateError as error:
        if error.code == "engine.request_invalid":
            raise UpdateError("channel.invalid", error.detail) from None
        raise


def _load_channel_config(path: Path, *, channel_id: str | None) -> dict:
    config = load_json_file(path, "update channel")
    _require_exact_keys(config, ("schema_version", "document_type", "product", "default_channel", "channels"),
                        ("schema_version", "document_type", "product", "default_channel", "channels"),
                        "update channel", code="channel.invalid")
    if (config["schema_version"] != CHANNEL_SCHEMA_VERSION
            or config["document_type"] != DOCUMENT_CHANNEL
            or config["product"] != PRODUCT):
        raise refuse("channel.invalid", "update channel header is not supported")
    channels = config["channels"]
    if not isinstance(channels, list) or not 1 <= len(channels) <= 4:
        raise refuse("channel.invalid", "update channel list is invalid")
    default = _text(config["default_channel"], "channel.default_channel", pattern=KEY_ID, maximum=64)
    wanted = channel_id or default
    selected = None
    for entry in channels:
        entry = _require_object(entry, "channel")
        _require_exact_keys(entry, ("id", "provider", "metadata_url", "allowed_hosts", "required_assets", "enabled"),
                            ("id", "provider", "metadata_url", "allowed_hosts", "required_assets", "enabled"),
                            "channel", code="channel.invalid")
        if entry.get("id") == wanted:
            selected = entry
            break
    if selected is None:
        raise refuse("channel.invalid", "the requested update channel is not configured")
    if not _boolean(selected["enabled"], "channel.enabled"):
        raise refuse("channel.disabled", "this update channel is disabled by the provider")
    provider = _text(selected["provider"], "channel.provider", maximum=120)
    allowed = selected["allowed_hosts"]
    if (not isinstance(allowed, list) or not 1 <= len(allowed) <= 8
            or not all(_valid_host(host) for host in allowed)
            or len(set(allowed)) != len(allowed)):
        raise refuse("channel.invalid", "channel allowed_hosts is invalid")
    assets = selected["required_assets"]
    if (not isinstance(assets, list) or not assets or len(assets) > 8
            or not all(isinstance(name, str) and SAFE_ASSET.fullmatch(name) for name in assets)
            or len(set(assets)) != len(assets)):
        raise refuse("channel.invalid", "channel required_assets is invalid")
    metadata_url = parse_https_url(selected["metadata_url"], tuple(allowed))
    return {
        "id": wanted,
        "provider": provider,
        "metadata_url": metadata_url,
        "allowed_hosts": tuple(host.lower() for host in allowed),
        "required_assets": tuple(assets),
        "enabled": True,
    }


# --------------------------------------------------------------------------
# Signed release manifest
# --------------------------------------------------------------------------

def canonical_manifest_bytes(manifest: Mapping[str, object]) -> bytes:
    """Canonical JSON used by the provider tool to author manifest bytes.

    Signatures are always verified against the exact bytes on disk; this helper
    exists so the provider and the tests can create those bytes reproducibly.
    """
    return (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def validate_manifest(manifest: object, *, now: datetime) -> dict:
    try:
        return _validate_manifest(manifest, now=now)
    except UpdateError as error:
        if error.code == "engine.request_invalid":
            raise UpdateError("release.manifest.invalid", error.detail) from None
        raise


def _validate_manifest(manifest: object, *, now: datetime) -> dict:
    manifest = _require_object(manifest, "release manifest")
    _require_exact_keys(manifest, (
        "schema_version", "document_type", "product", "channel", "version", "release_sequence",
        "source_revision", "release_status", "production_authorization", "issued_utc", "notes",
        "requirements", "database", "image", "updater", "signature",
    ), (
        "schema_version", "document_type", "product", "channel", "version", "release_sequence",
        "source_revision", "release_status", "production_authorization", "issued_utc",
        "requirements", "database", "image", "updater", "signature",
    ), "release manifest", code="release.manifest.invalid")
    if (manifest["schema_version"] != MANIFEST_SCHEMA_VERSION
            or manifest["document_type"] != DOCUMENT_UPDATE
            or manifest["product"] != PRODUCT):
        raise refuse("release.manifest.invalid", "release manifest header is not supported")
    version = _text(manifest["version"], "manifest.version", pattern=SAFE_VERSION, maximum=64)
    sequence = _integer(manifest["release_sequence"], "manifest.release_sequence", 1, MAX_SEQUENCE)
    revision = _text(manifest["source_revision"], "manifest.source_revision", pattern=HEX40, maximum=40)
    channel = _text(manifest["channel"], "manifest.channel", pattern=KEY_ID, maximum=64)
    if manifest["release_status"] not in RELEASE_STATUSES:
        raise refuse("release.manifest.invalid", "release status is not supported")
    if manifest["production_authorization"] not in AUTHORIZATIONS:
        raise refuse("release.manifest.invalid", "production authorization is not supported")
    issued = parse_utc(manifest["issued_utc"], "manifest.issued_utc")
    if issued > now + timedelta(minutes=10):
        raise refuse("release.manifest.invalid", "release manifest is dated in the future")
    notes = manifest.get("notes", "")
    if (not isinstance(notes, str) or len(notes) > 2000
            or any(ord(char) < 0x20 and char not in "\n\t" for char in notes)):
        raise refuse("release.manifest.invalid", "release notes are invalid")

    requirements = _require_object(manifest["requirements"], "manifest.requirements")
    _require_exact_keys(requirements, ("minimum_host_updater_version", "engine_schema", "minimum_installed_version",
                                       "minimum_installed_sequence", "maximum_installed_sequence",
                                       "minimum_free_bytes", "backup", "recovery_authorization"),
                        ("minimum_host_updater_version", "engine_schema", "minimum_installed_version",
                         "minimum_free_bytes", "backup", "recovery_authorization"),
                        "manifest.requirements", code="release.manifest.invalid")
    host_version = _text(requirements["minimum_host_updater_version"], "requirements.minimum_host_updater_version",
                         pattern=SAFE_VERSION, maximum=64)
    engine_schema = _integer(requirements["engine_schema"], "requirements.engine_schema", 1, 100)
    installed_version = _text(requirements["minimum_installed_version"], "requirements.minimum_installed_version",
                              pattern=SAFE_VERSION, maximum=64)
    minimum_sequence = requirements.get("minimum_installed_sequence")
    maximum_sequence = requirements.get("maximum_installed_sequence")
    if minimum_sequence is not None:
        minimum_sequence = _integer(minimum_sequence, "requirements.minimum_installed_sequence", 0, MAX_SEQUENCE)
    if maximum_sequence is not None:
        maximum_sequence = _integer(maximum_sequence, "requirements.maximum_installed_sequence", 1, MAX_SEQUENCE)
    if minimum_sequence is not None and maximum_sequence is not None and minimum_sequence > maximum_sequence:
        raise refuse("release.manifest.invalid", "installed sequence window is inverted")
    minimum_free = _integer(requirements["minimum_free_bytes"], "requirements.minimum_free_bytes", 0, 100 * 1024 ** 4)
    backup = _require_object(requirements["backup"], "requirements.backup")
    _require_exact_keys(backup, ("required", "max_age_hours", "require_restore_verification"),
                        ("required", "max_age_hours", "require_restore_verification"),
                        "requirements.backup", code="release.manifest.invalid")
    backup_required = _boolean(backup["required"], "requirements.backup.required")
    backup_age = _integer(backup["max_age_hours"], "requirements.backup.max_age_hours", 1, MAX_BACKUP_MAX_AGE_HOURS)
    restore_required = _boolean(backup["require_restore_verification"],
                                "requirements.backup.require_restore_verification")
    recovery = _require_object(requirements["recovery_authorization"], "requirements.recovery_authorization")
    _require_exact_keys(recovery, ("required", "max_age_hours"), ("required", "max_age_hours"),
                        "requirements.recovery_authorization", code="release.manifest.invalid")
    recovery_required = _boolean(recovery["required"], "requirements.recovery_authorization.required")
    recovery_age = _integer(recovery["max_age_hours"], "requirements.recovery_authorization.max_age_hours", 1, 720)

    database = _require_object(manifest["database"], "manifest.database")
    _require_exact_keys(database, ("migration", "reversible", "requires_verified_backup", "target_schema_version",
                                   "minimum_source_schema_version"),
                        ("migration", "reversible", "requires_verified_backup", "target_schema_version"),
                        "manifest.database", code="release.manifest.invalid")
    if database["migration"] not in MIGRATION_MODES:
        raise refuse("release.manifest.invalid", "database migration mode is not supported")
    reversible = _boolean(database["reversible"], "database.reversible")
    requires_backup = _boolean(database["requires_verified_backup"], "database.requires_verified_backup")
    target_schema = _text(database["target_schema_version"], "database.target_schema_version",
                          pattern=SAFE_TOKEN, maximum=64)
    minimum_source_schema = database.get("minimum_source_schema_version")
    if minimum_source_schema is not None:
        minimum_source_schema = _text(minimum_source_schema, "database.minimum_source_schema_version",
                                      pattern=SAFE_TOKEN, maximum=64)

    image = _require_object(manifest["image"], "manifest.image")
    _require_exact_keys(image, ("tag", "archive", "sha256", "size_bytes", "config_digest", "labels"),
                        ("tag", "archive", "sha256", "size_bytes", "config_digest", "labels"),
                        "manifest.image", code="release.manifest.invalid")
    if image["tag"] != IMAGE_TAG:
        raise refuse("release.manifest.invalid", "the image tag must remain the reviewed local tag")
    archive_name = _text(image["archive"], "image.archive", maximum=128)
    if archive_name != PurePosixPath(archive_name).name or not SAFE_ASSET.fullmatch(archive_name):
        raise refuse("release.manifest.invalid", "image archive name is unsafe")
    image_hash = _text(image["sha256"], "image.sha256", pattern=HEX64, maximum=64)
    image_size = _integer(image["size_bytes"], "image.size_bytes", MIN_ARCHIVE_BYTES, MAX_ARCHIVE_BYTES)
    config_digest = _text(image["config_digest"], "image.config_digest", pattern=SHA256_TAG, maximum=71)
    labels = _require_object(image["labels"], "image.labels")
    _require_exact_keys(labels, ("org.toefl-house.source-eol", "org.toefl-house.source-revision",
                                 "org.toefl-house.release-version"),
                        ("org.toefl-house.source-eol", "org.toefl-house.source-revision",
                         "org.toefl-house.release-version"), "image.labels", code="release.manifest.invalid")
    if (labels["org.toefl-house.source-eol"] != "lf-v1"
            or labels["org.toefl-house.source-revision"] != revision
            or labels["org.toefl-house.release-version"] != version):
        raise refuse("release.image.labels_mismatch", "image labels do not match the signed release identity")

    updater = _require_object(manifest["updater"], "manifest.updater")
    _require_exact_keys(updater, ("engine_schema", "strings_schema"), ("engine_schema", "strings_schema"),
                        "manifest.updater", code="release.manifest.invalid")
    _integer(updater["engine_schema"], "updater.engine_schema", 1, 100)
    _integer(updater["strings_schema"], "updater.strings_schema", 1, 100)

    signature = _require_object(manifest["signature"], "manifest.signature")
    _require_exact_keys(signature, ("key_id", "algorithm"), ("key_id", "algorithm"),
                        "manifest.signature", code="release.manifest.invalid")
    key_id = _text(signature["key_id"], "signature.key_id", pattern=KEY_ID, maximum=64)
    if signature["algorithm"] not in SIGNATURE_ALGORITHMS:
        raise refuse("release.manifest.invalid", "signature algorithm is not supported")

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "version": version,
        "release_sequence": sequence,
        "source_revision": revision,
        "channel": channel,
        "release_status": manifest["release_status"],
        "production_authorization": manifest["production_authorization"],
        "issued_utc": issued,
        "notes": notes,
        "requirements": {
            "minimum_host_updater_version": host_version,
            "engine_schema": engine_schema,
            "minimum_installed_version": installed_version,
            "minimum_installed_sequence": minimum_sequence,
            "maximum_installed_sequence": maximum_sequence,
            "minimum_free_bytes": minimum_free,
            "backup_required": backup_required,
            "backup_max_age_hours": backup_age,
            "restore_verification_required": restore_required,
            "recovery_required": recovery_required,
            "recovery_max_age_hours": recovery_age,
        },
        "database": {
            "migration": database["migration"],
            "reversible": reversible,
            "requires_verified_backup": requires_backup,
            "target_schema_version": target_schema,
            "minimum_source_schema_version": minimum_source_schema,
        },
        "image": {
            "tag": IMAGE_TAG,
            "archive": archive_name,
            "sha256": image_hash,
            "size_bytes": image_size,
            "config_digest": config_digest,
            "labels": {key: labels[key] for key in sorted(labels)},
        },
        "updater": {"engine_schema": updater["engine_schema"], "strings_schema": updater["strings_schema"]},
        "signature": {"key_id": key_id, "algorithm": signature["algorithm"]},
        "raw_sha256": None,
    }


def _load_signature_envelope(path: Path, document_type: str, *, code: str, label: str = "release signature") -> dict:
    envelope = load_json_file(path, label)
    _require_exact_keys(envelope, ("schema_version", "document_type", "algorithm", "key_id", "signature_b64"),
                        ("schema_version", "document_type", "algorithm", "key_id", "signature_b64"),
                        "signature envelope", code=code)
    if envelope["schema_version"] != ENGINE_SCHEMA_VERSION or envelope["document_type"] != document_type:
        raise refuse(code, "signature envelope is not supported")
    if envelope["algorithm"] not in SIGNATURE_ALGORITHMS:
        raise refuse(code, "signature algorithm is not supported")
    key_id = _text(envelope["key_id"], "signature.key_id", pattern=KEY_ID, maximum=64)
    try:
        signature = base64.b64decode(_text(envelope["signature_b64"], "signature.signature_b64", maximum=2048),
                                     validate=True)
    except (ValueError, TypeError):
        raise refuse(code, "signature is not valid base64") from None
    return {"key_id": key_id, "algorithm": envelope["algorithm"], "signature": signature}


def verify_manifest_signature(manifest_path: Path, signature_path: Path, store: dict, *, now: datetime) -> dict:
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise refuse("release.manifest.missing", "the signed release manifest is missing")
    if signature_path.is_symlink() or not signature_path.is_file():
        raise refuse("release.signature.invalid", "the release signature document is missing")
    manifest = load_json_file(manifest_path, "release manifest")
    normalized = validate_manifest(manifest, now=now)
    envelope = _load_signature_envelope(signature_path, DOCUMENT_UPDATE_SIGNATURE,
                                        code="release.signature.invalid")
    if envelope["key_id"] != normalized["signature"]["key_id"]:
        raise refuse("release.signature.invalid", "signature key id does not match the signed manifest")
    if envelope["algorithm"] != normalized["signature"]["algorithm"]:
        raise refuse("release.signature.invalid", "signature algorithm does not match the signed manifest")
    key = select_key(store, normalized["signature"]["key_id"], "update-manifest", now=now)
    raw = manifest_path.read_bytes()
    if not rsa_pkcs1v15_sha256_verify(key["modulus"], key["exponent"], raw, envelope["signature"]):
        raise refuse("release.signature.invalid", "release manifest signature did not verify")
    normalized["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    return normalized


# --------------------------------------------------------------------------
# Docker image archive identity (no Docker daemon required)
# --------------------------------------------------------------------------

def inspect_image_archive(path: Path, *, expected: Mapping[str, object] | None = None,
                          verify_layers: bool = False) -> dict:
    """Bind saved image bytes to their labels/config digest without Docker."""
    if path.is_symlink() or not path.is_file():
        raise refuse("release.archive.missing", "the prebuilt image archive is missing")
    try:
        size = path.stat().st_size
    except OSError:
        raise refuse("release.archive.missing", "the prebuilt image archive is unreadable") from None
    if not MIN_ARCHIVE_BYTES <= size <= MAX_ARCHIVE_BYTES:
        raise refuse("release.archive.size_mismatch", "the image archive size is outside the supported range")
    digest = sha256_file(path)
    try:
        with tarfile.open(path, "r:*") as archive:
            members: dict[str, tarfile.TarInfo] = {}
            for member in archive:
                if member.name in members:
                    raise refuse("release.archive.identity_mismatch", "duplicate image archive member")
                members[member.name] = member

            def regular(name: str, limit: int = MAX_METADATA_BYTES) -> tarfile.TarInfo:
                if (not isinstance(name, str) or not name or "\\" in name
                        or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts):
                    raise refuse("release.archive.identity_mismatch", "unsafe image archive member path")
                member = members.get(name)
                if member is None or not member.isfile() or member.size > limit:
                    raise refuse("release.archive.identity_mismatch",
                                 "missing, linked or oversized image archive member")
                return member

            def read(name: str, limit: int = MAX_METADATA_BYTES) -> bytes:
                member = regular(name, limit)
                handle = archive.extractfile(member)
                if handle is None:
                    raise refuse("release.archive.identity_mismatch", "unreadable image archive member")
                with handle:
                    data = handle.read(limit + 1)
                if len(data) != member.size or len(data) > limit:
                    raise refuse("release.archive.identity_mismatch", "truncated image archive member")
                return data

            entry_manifest = json.loads(read("manifest.json").decode("utf-8"))
            if (not isinstance(entry_manifest, list) or len(entry_manifest) != 1
                    or not isinstance(entry_manifest[0], dict)):
                raise refuse("release.archive.identity_mismatch",
                             "the archive must describe exactly one image")
            entry = entry_manifest[0]
            if entry.get("RepoTags") != [IMAGE_TAG]:
                raise refuse("release.archive.identity_mismatch",
                             "the archive must carry only the reviewed image tag")
            config_name = entry.get("Config")
            if not isinstance(config_name, str):
                raise refuse("release.archive.identity_mismatch", "the archive image config is missing")
            config_bytes = read(config_name)
            config_hash = hashlib.sha256(config_bytes).hexdigest()
            if config_name not in (f"{config_hash}.json", f"blobs/sha256/{config_hash}"):
                raise refuse("release.archive.identity_mismatch",
                             "image config filename does not match its digest")
            config = json.loads(config_bytes.decode("utf-8"))
            if not isinstance(config, dict) or not isinstance(config.get("config"), dict):
                raise refuse("release.archive.identity_mismatch", "image config is malformed")
            labels = config["config"].get("Labels")
            if (not isinstance(labels, dict)
                    or not all(isinstance(key, str) and isinstance(value, str)
                               for key, value in labels.items())):
                raise refuse("release.archive.identity_mismatch", "image labels are malformed")
            layers = entry.get("Layers")
            rootfs = config.get("rootfs")
            if (not isinstance(layers, list) or not isinstance(rootfs, dict)
                    or rootfs.get("type") != "layers"
                    or not isinstance(rootfs.get("diff_ids"), list)
                    or len(rootfs["diff_ids"]) != len(layers)
                    or not all(isinstance(item, str) and SHA256_TAG.fullmatch(item)
                               for item in rootfs["diff_ids"])):
                raise refuse("release.archive.identity_mismatch", "image layer metadata is malformed")
            if verify_layers:
                for layer, expected_id in zip(layers, rootfs["diff_ids"]):
                    member = regular(layer, MAX_ARCHIVE_BYTES)
                    handle = archive.extractfile(member)
                    if handle is None:
                        raise refuse("release.archive.identity_mismatch", "unreadable image layer")
                    hasher = hashlib.sha256()
                    with handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            hasher.update(chunk)
                    if "sha256:" + hasher.hexdigest() != expected_id:
                        raise refuse("release.archive.identity_mismatch", "image layer content changed")
    except UpdateError:
        raise
    except (tarfile.TarError, UnicodeError, json.JSONDecodeError, OSError):
        raise refuse("release.archive.identity_mismatch",
                     "the image archive is not a valid Docker save archive") from None
    identity = {
        "config_digest": "sha256:" + config_hash,
        "labels": {key: labels[key] for key in sorted(labels)},
        "archive_sha256": digest,
        "size_bytes": size,
    }
    if expected is not None:
        if identity["config_digest"] != expected["config_digest"]:
            raise refuse("release.archive.identity_mismatch",
                         "image config digest differs from the signed manifest")
        if identity["labels"] != dict(expected["labels"]):
            raise refuse("release.image.labels_mismatch", "image labels differ from the signed manifest")
        if digest != expected["sha256"]:
            raise refuse("release.archive.hash_mismatch", "the image archive failed its signed SHA-256 check")
        if size != expected["size_bytes"]:
            raise refuse("release.archive.size_mismatch",
                         "the image archive size differs from the signed manifest")
    return identity


# --------------------------------------------------------------------------
# Version and compatibility policy
# --------------------------------------------------------------------------

def release_sequence(version: str) -> int:
    """Return the date-derived build number for a plain numeric release.

    ``2026.11.01`` becomes ``2026110100``: one number that orders releases the
    same way their dates do.  The provider signs the same number in the release
    manifest, and the Windows updater derives the installed number from the
    image version label with this identical rule, so no extra local state is
    trusted.  Pre-release or ad-hoc versions have no sequence and therefore
    cannot take part in an update; they fail closed instead of guessing.
    """
    if not isinstance(version, str):
        raise refuse("compat.installed_version_unknown", "release version is not text")
    match = re.fullmatch(r"(\d{1,4})(?:\.(\d{1,2}))?(?:\.(\d{1,2}))?(?:\.(\d{1,2}))?", version)
    if not match:
        raise refuse("compat.installed_version_unknown",
                     "only a plain numeric release has an update sequence")
    numbers = [int(part) if part is not None else 0 for part in match.groups()]
    if numbers[0] < 1 or numbers[0] > 2147 or any(value > 99 for value in numbers[1:]):
        raise refuse("compat.installed_version_unknown",
                     "release version components are outside the supported range")
    value = numbers[0] * 1_000_000 + numbers[1] * 10_000 + numbers[2] * 100 + numbers[3]
    if not 1 <= value <= MAX_SEQUENCE:
        raise refuse("compat.installed_version_unknown", "release sequence is outside the supported range")
    return value


def version_key(version: str) -> tuple:
    """Order dotted numeric versions with an optional build suffix."""
    if not isinstance(version, str) or not SAFE_VERSION.fullmatch(version):
        raise refuse("compat.installed_version_unknown", "release version format is unsupported")
    match = re.fullmatch(r"[vV]?(\d+(?:\.\d+){0,3})(?:[-+]([A-Za-z0-9][A-Za-z0-9.-]*))?", version)
    if not match:
        raise refuse("compat.installed_version_unknown", "release version format is unsupported")
    numbers = tuple(int(part) for part in match.group(1).split("."))
    while len(numbers) < 4:
        numbers += (0,)
    suffix = match.group(2) or ""
    return numbers, (1, suffix) if suffix else (0, "")


def _block(code: str, detail: str = "") -> dict:
    if code not in MESSAGE_CODES:
        raise AssertionError(f"unknown update message code: {code}")
    return {"code": code, "detail": str(detail)[:400]}


def evaluate_compatibility(manifest: dict, installed: Mapping[str, object] | None,
                           host_updater_version: str) -> list[dict]:
    blockers: list[dict] = []
    requirements = manifest["requirements"]
    try:
        if version_key(host_updater_version) < version_key(requirements["minimum_host_updater_version"]):
            blockers.append(_block("compat.host_updater_too_old",
                                   f"host updater {host_updater_version} is older than this release requires"))
    except UpdateError:
        blockers.append(_block("compat.host_updater_too_old", "this updater cannot verify its own version"))
    if requirements["engine_schema"] != ENGINE_SCHEMA_VERSION:
        blockers.append(_block("compat.engine_schema_unsupported",
                               "this release needs a different update engine"))
    if manifest["database"]["migration"] == "none" and not manifest["database"]["reversible"]:
        blockers.append(_block("compat.schema_unsupported", "release declares no migration path"))

    if installed is None:
        blockers.append(_block("preflight.not_installed", "no installed release identity was supplied"))
        return blockers
    installed = _require_object(installed, "installed")
    _require_exact_keys(installed, ("version", "release_sequence", "source_revision", "image_labels", "image_id"),
                        ("version", "release_sequence", "source_revision", "image_labels", "image_id"),
                        "installed", code="compat.installed_version_unknown")
    try:
        installed_version = _text(installed["version"], "installed.version", pattern=SAFE_VERSION, maximum=64)
        installed_key = version_key(installed_version)
    except UpdateError:
        blockers.append(_block("compat.installed_version_unknown",
                               "the installed release version is not established"))
        return blockers
    sequence = installed["release_sequence"]
    if sequence is not None:
        try:
            sequence = _integer(sequence, "installed.release_sequence", 0, MAX_SEQUENCE)
        except UpdateError:
            blockers.append(_block("compat.installed_version_unknown",
                                   "the installed release sequence is invalid"))
            return blockers
    if sequence is None:
        # An unknown installed sequence cannot prove the candidate is newer, so
        # the update fails closed exactly like a downgrade attempt.
        blockers.append(_block("compat.downgrade",
                               "the installed release sequence is not established"))
    target_key = version_key(manifest["version"])
    target_sequence = manifest["release_sequence"]
    if target_key < installed_key:
        blockers.append(_block("compat.downgrade", "the candidate release is older than the installed release"))
    elif target_key == installed_key and (sequence is None or target_sequence <= sequence):
        blockers.append(_block("compat.downgrade", "the candidate release is already installed"))
    if target_sequence <= (sequence if isinstance(sequence, int) else 0):
        blockers.append(_block("compat.downgrade", "the candidate release sequence is not newer"))
    try:
        if installed_key < version_key(requirements["minimum_installed_version"]):
            blockers.append(_block("compat.installed_too_old",
                                   "the installed release is older than the supported upgrade path"))
    except UpdateError:
        blockers.append(_block("compat.installed_too_old", "the supported upgrade path could not be evaluated"))
    minimum_sequence = requirements["minimum_installed_sequence"]
    maximum_sequence = requirements["maximum_installed_sequence"]
    if isinstance(sequence, int):
        if minimum_sequence is not None and sequence < minimum_sequence:
            blockers.append(_block("compat.sequence_gap",
                                   f"installed sequence {sequence} is below the supported upgrade path"))
        if maximum_sequence is not None and sequence > maximum_sequence:
            blockers.append(_block("compat.installed_too_new",
                                   f"installed sequence {sequence} is newer than this release supports"))
    source_schema = manifest["database"]["minimum_source_schema_version"]
    if source_schema is not None and installed_version != source_schema:
        blockers.append(_block("compat.schema_unsupported",
                               "the installed schema does not match the supported migration source"))
    return blockers


# --------------------------------------------------------------------------
# Evidence: verified encrypted backup and signed recovery authorization
# --------------------------------------------------------------------------

def _load_activate_module():
    """Import the product's existing guarded activation receipt validator.

    ``product/activate.py`` owns the single native-backup receipt contract.
    Reusing it makes update preconditions identical to activation instead of
    introducing a second, drifting receipt schema.
    """
    product_dir = Path(__file__).resolve().parent
    if str(product_dir) not in sys.path:
        sys.path.insert(0, str(product_dir))
    import activate  # deliberate late import; activate.py imports only stdlib
    return activate


def validate_backup_receipt(path: Path, *, site: str, backup_dir: Path, now: datetime,
                            max_age_hours: int) -> dict:
    activate = _load_activate_module()
    try:
        receipt = activate.read_backup_receipt(path)
    except activate.Refused as error:
        raise refuse("preflight.backup.receipt_unreadable", str(error)) from None
    if receipt is None:
        raise refuse("preflight.backup.receipt_missing",
                     "no verified encrypted backup receipt exists for this site")
    try:
        activate.validate_backup_receipt_for_update(site, receipt, now.timestamp(), backup_dir)
    except activate.Refused as error:
        message = str(error)
        if "last 24 hours" in message or "age" in message or "future" in message:
            raise refuse("preflight.backup.stale", message) from None
        if "artifact" in message:
            raise refuse("preflight.backup.artifact_invalid", message) from None
        raise refuse("preflight.backup.receipt_invalid", message) from None
    created = activate._parse_utc(receipt.get("created_utc"))
    age_hours = (now - created).total_seconds() / 3600
    if age_hours > max_age_hours:
        raise refuse("preflight.backup.stale",
                     f"the verified backup is older than the release allows ({max_age_hours}h)")
    return {"receipt": receipt, "sha256": sha256_file(path), "age_hours": age_hours}


def validate_recovery_authorization(path: Path, signature_path: Path, store: dict, *, site: str,
                                    receipt_sha256: str, now: datetime, max_age_hours: int) -> dict:
    document = load_json_file(path, "recovery authorization")
    _require_exact_keys(document, (
        "schema_version", "document_type", "site", "scope", "issued_utc", "expires_utc",
        "owner_key_custody_verified", "rehearsal_restore_verified", "backup_receipt_sha256",
        "authorized_by", "attested_by",
    ), (
        "schema_version", "document_type", "site", "scope", "issued_utc", "expires_utc",
        "owner_key_custody_verified", "rehearsal_restore_verified", "backup_receipt_sha256",
        "authorized_by", "attested_by",
    ), "recovery authorization", code="preflight.recovery.authorization_invalid")
    if (document["schema_version"] != ENGINE_SCHEMA_VERSION
            or document["document_type"] != DOCUMENT_RECOVERY):
        raise refuse("preflight.recovery.authorization_invalid",
                     "recovery authorization header is not supported")
    if document["site"] != site or document["scope"] != "site-update":
        raise refuse("preflight.recovery.binding_mismatch",
                     "recovery authorization is for another site or scope")
    if document["authorized_by"] != "owner" or document["attested_by"] != "toefl-house-support":
        raise refuse("preflight.recovery.authorization_invalid",
                     "recovery authorization signer identity is invalid")
    if not _boolean(document["owner_key_custody_verified"], "recovery.owner_key_custody_verified"):
        raise refuse("preflight.recovery.key_custody_unverified",
                     "Owner encryption-key custody is not verified")
    if not _boolean(document["rehearsal_restore_verified"], "recovery.rehearsal_restore_verified"):
        raise refuse("preflight.recovery.rehearsal_unverified", "a rehearsal restore is not verified")
    if document["backup_receipt_sha256"] != receipt_sha256:
        raise refuse("preflight.recovery.binding_mismatch",
                     "recovery authorization is bound to a different backup")
    issued = parse_utc(document["issued_utc"], "recovery.issued_utc")
    expires = parse_utc(document["expires_utc"], "recovery.expires_utc")
    if issued > now + timedelta(minutes=10):
        raise refuse("preflight.recovery.authorization_invalid",
                     "recovery authorization is dated in the future")
    if expires <= issued:
        raise refuse("preflight.recovery.authorization_invalid",
                     "recovery authorization validity window is inverted")
    if expires <= now:
        raise refuse("preflight.recovery.authorization_expired", "recovery authorization has expired")
    if (now - issued) > timedelta(hours=max_age_hours):
        raise refuse("preflight.recovery.authorization_expired",
                     "recovery authorization is too old for this release")
    envelope = _load_signature_envelope(signature_path, DOCUMENT_RECOVERY_SIGNATURE,
                                        code="preflight.recovery.authorization_invalid",
                                        label="recovery signature")
    key = select_key(store, envelope["key_id"], "recovery-authorization", now=now)
    raw = path.read_bytes()
    if not rsa_pkcs1v15_sha256_verify(key["modulus"], key["exponent"], raw, envelope["signature"]):
        raise refuse("preflight.recovery.authorization_invalid",
                     "recovery authorization signature did not verify")
    return {"sha256": hashlib.sha256(raw).hexdigest(), "expires_utc": expires.isoformat()}


# --------------------------------------------------------------------------
# Preflight decision
# --------------------------------------------------------------------------

def _host_facts(request: Mapping[str, object]) -> dict:
    facts = _require_object(request.get("host"), "host facts")
    _require_exact_keys(facts, ("disk_free_bytes", "volume_present", "volume_verified", "services",
                                "image_present", "image_id", "image_labels", "site_credentials_present",
                                "site_config_present"),
                        ("disk_free_bytes", "volume_present", "volume_verified", "services",
                         "image_present", "image_id", "image_labels", "site_credentials_present",
                         "site_config_present"), "host facts")
    disk = _integer(facts["disk_free_bytes"], "host.disk_free_bytes", 0, 1024 ** 5)
    services = _require_object(facts["services"], "host.services")
    _require_exact_keys(services, ("db", "redis_cache", "redis_queue", "web"),
                        ("db", "redis_cache", "redis_queue", "web"), "host.services")
    for name, value in services.items():
        if value not in (True, False, None):
            raise refuse("engine.request_invalid", f"host.services.{name} must be boolean or null")
    labels = facts["image_labels"]
    if labels is not None:
        labels = _require_object(labels, "host.image_labels")
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in labels.items()):
            raise refuse("engine.request_invalid", "host.image_labels must be a string mapping")
    return {
        "disk_free_bytes": disk,
        "volume_present": _boolean(facts["volume_present"], "host.volume_present"),
        "volume_verified": _boolean(facts["volume_verified"], "host.volume_verified"),
        "services": dict(services),
        "image_present": _boolean(facts["image_present"], "host.image_present"),
        "image_id": _text(facts["image_id"], "host.image_id", maximum=80, allow_empty=True),
        "image_labels": labels,
        "site_credentials_present": _boolean(facts["site_credentials_present"], "host.site_credentials_present"),
        "site_config_present": _boolean(facts["site_config_present"], "host.site_config_present"),
    }


def preflight(request: Mapping[str, object], *, now: datetime) -> dict:
    """Return an allow/refuse decision.  This function never mutates anything."""
    request = _require_object(request, "request")
    _require_exact_keys(request, ("action", "now_utc", "site", "product_root", "host_updater_version",
                                  "trust_store", "channel", "manifest", "signature", "archive",
                                  "backup_receipt", "backup_dir", "recovery_authorization",
                                  "recovery_signature", "installed", "journal_state", "host"),
                        ("action", "site", "product_root", "host_updater_version", "trust_store",
                         "channel", "manifest", "signature", "archive", "installed", "host"), "request")
    if request["action"] != "preflight":
        raise refuse("engine.request_invalid", "request action is not preflight")
    if request["site"] != SITE_NAME:
        raise refuse("preflight.site.config_unreadable", "the site name is not the supported product site")
    product_root = Path(_text(request["product_root"], "request.product_root", maximum=1024))
    if product_root.is_symlink() or not product_root.is_dir():
        raise refuse("preflight.site.config_unreadable", "the product folder is missing or unsafe")
    host_version = _text(request["host_updater_version"], "request.host_updater_version",
                         pattern=SAFE_VERSION, maximum=64)
    blockers: list[dict] = []

    # Defense in depth: the engine re-checks the site files even though the
    # launcher already reported them in the host facts.
    if not (product_root / "data" / "secrets" / "db.env").is_file():
        blockers.append(_block("preflight.site.credentials_missing",
                               "local database credentials are missing"))
    if not (product_root / "data" / "sites" / SITE_NAME / "site_config.json").is_file():
        blockers.append(_block("preflight.site.config_missing",
                               "the Frappe site configuration is missing"))

    try:
        store = load_trust_store(resolve_inside(product_root, request["trust_store"], "request.trust_store"),
                                 now=now)
        channel = load_channel_config(resolve_inside(product_root, request["channel"], "request.channel"),
                                      channel_id=None)
    except UpdateError as error:
        blockers.append(_block(error.code, error.detail))
        return _decision(blockers, [], None, None, request)

    try:
        manifest = verify_manifest_signature(
            resolve_inside(product_root, request["manifest"], "request.manifest"),
            resolve_inside(product_root, request["signature"], "request.signature"),
            store, now=now)
    except UpdateError as error:
        blockers.append(_block(error.code, error.detail))
        return _decision(blockers, [], None, None, request)

    if manifest["channel"] != channel["id"]:
        blockers.append(_block("policy.release_not_authorized",
                               "the release is signed for a different update channel"))
    if manifest["production_authorization"] != "AUTHORIZED":
        blockers.append(_block("policy.release_not_authorized",
                               "this release is not authorized for a real installation"))
    if manifest["release_status"] != "PRODUCTION RELEASE":
        blockers.append(_block("policy.release_not_production",
                               "this release is a non-production test package"))

    identity = None
    try:
        identity = inspect_image_archive(
            resolve_inside(product_root, request["archive"], "request.archive"), expected=manifest["image"])
    except UpdateError as error:
        blockers.append(_block(error.code, error.detail))

    blockers.extend(evaluate_compatibility(manifest, request.get("installed"), host_version))

    journal_state = request.get("journal_state", "idle")
    if journal_state not in JOURNAL_TERMINAL_STATES:
        blockers.append(_block("preflight.update_in_progress", "an update transaction is not finished"))

    facts = _host_facts(request)
    requirements = manifest["requirements"]
    required_free = max(requirements["minimum_free_bytes"], MIN_FREE_BYTES_FLOOR)
    if facts["disk_free_bytes"] < required_free:
        blockers.append(_block("preflight.disk.insufficient",
                               f"{facts['disk_free_bytes']} free bytes < {required_free} required"))
    if not facts["volume_present"]:
        blockers.append(_block("preflight.volume.missing",
                               "the named database volume is missing"))
    elif not facts["volume_verified"]:
        blockers.append(_block("preflight.volume.unverified",
                               "the named database volume could not be verified"))
    if not facts["site_credentials_present"]:
        blockers.append(_block("preflight.site.credentials_missing", "local database credentials are missing"))
    if not facts["site_config_present"]:
        blockers.append(_block("preflight.site.config_missing", "the Frappe site configuration is missing"))
    if not facts["image_present"]:
        blockers.append(_block("preflight.image.missing", "the installed application image was not found"))
    else:
        installed = request.get("installed") if isinstance(request.get("installed"), dict) else {}
        expected_labels = installed.get("image_labels")
        if isinstance(expected_labels, dict) and facts["image_labels"] is not None \
                and facts["image_labels"] != expected_labels:
            blockers.append(_block("preflight.image.identity_mismatch",
                                   "the running image identity differs from the installed release record"))
    unhealthy = [name for name, value in facts["services"].items() if value is not True]
    if unhealthy:
        blockers.append(_block("preflight.services.unhealthy",
                               "services are not healthy before the update: " + ",".join(sorted(unhealthy))))

    warnings: list[dict] = []
    receipt_details = None
    if requirements["backup_required"] or manifest["database"]["requires_verified_backup"]:
        receipt_value = request.get("backup_receipt")
        if not isinstance(receipt_value, str) or not receipt_value:
            blockers.append(_block("preflight.backup.receipt_missing",
                                   "no verified backup receipt was supplied"))
        else:
            if request.get("backup_dir"):
                backup_dir = resolve_inside(product_root, request["backup_dir"], "request.backup_dir")
            else:
                backup_dir = product_root / "data" / "sites" / SITE_NAME / "private" / "backups"
            try:
                receipt_details = validate_backup_receipt(
                    resolve_inside(product_root, receipt_value, "request.backup_receipt"),
                    site=SITE_NAME, backup_dir=backup_dir, now=now,
                    max_age_hours=requirements["backup_max_age_hours"])
                if receipt_details["age_hours"] > requirements["backup_max_age_hours"] * 0.75:
                    warnings.append(_block("warning.backup_age_near_limit",
                                           f"verified backup is {receipt_details['age_hours']:.1f}h old"))
            except UpdateError as error:
                blockers.append(_block(error.code, error.detail))

    if manifest["database"]["migration"] != "none" and not manifest["database"]["reversible"]:
        warnings.append(_block("warning.not_rollback_safe",
                               "database migrations are not reversible; recovery uses the verified backup"))

    if requirements["recovery_required"]:
        if not request.get("recovery_authorization") or not request.get("recovery_signature"):
            blockers.append(_block("preflight.recovery.authorization_missing",
                                   "signed Owner recovery/key-custody authorization is not present"))
        elif receipt_details is None:
            blockers.append(_block("preflight.recovery.binding_mismatch",
                                   "recovery authorization cannot be bound without a verified backup"))
        else:
            try:
                validate_recovery_authorization(
                    resolve_inside(product_root, request["recovery_authorization"],
                                   "request.recovery_authorization"),
                    resolve_inside(product_root, request["recovery_signature"],
                                   "request.recovery_signature"),
                    store, site=SITE_NAME, receipt_sha256=receipt_details["sha256"], now=now,
                    max_age_hours=requirements["recovery_max_age_hours"])
            except UpdateError as error:
                blockers.append(_block(error.code, error.detail))
            except (OSError, ValueError):
                blockers.append(_block("preflight.recovery.authorization_invalid",
                                       "recovery authorization could not be read"))

    return _decision(blockers, warnings, manifest, identity, request, receipt_details)


def _decision(blockers: list[dict], warnings: list[dict], manifest: dict | None,
              identity: dict | None, request: Mapping[str, object],
              receipt_details: dict | None = None) -> dict:
    installed = request.get("installed") if isinstance(request.get("installed"), dict) else None
    required_free = None
    if manifest is not None:
        required_free = max(manifest["requirements"]["minimum_free_bytes"], MIN_FREE_BYTES_FLOOR)
    return {
        "schema_version": ENGINE_SCHEMA_VERSION,
        "document_type": DOCUMENT_RESPONSE,
        "action": "preflight",
        "decision": "allow" if not blockers else "refuse",
        "blockers": blockers,
        "warnings": warnings,
        "current": _public_installed(installed),
        "target": None if manifest is None else {
            "version": manifest["version"],
            "release_sequence": manifest["release_sequence"],
            "source_revision": manifest["source_revision"],
            "release_status": manifest["release_status"],
            "production_authorization": manifest["production_authorization"],
            "notes": manifest["notes"],
            "image": identity,
        },
        "plan": {
            "phases": list(PLAN_PHASES),
            "required_free_bytes": required_free,
            "database_migration": None if manifest is None else manifest["database"]["migration"],
            "reversible": None if manifest is None else manifest["database"]["reversible"],
            "backup_set": None if receipt_details is None else receipt_details["receipt"].get("backup_set"),
            "rollback": ("image-only" if manifest is not None and manifest["database"]["reversible"]
                         else "recovery-required"),
        },
    }


def _public_installed(installed: Mapping[str, object] | None) -> dict:
    if not isinstance(installed, Mapping):
        return {"version": None, "release_sequence": None, "source_revision": None}
    return {
        "version": installed.get("version"),
        "release_sequence": installed.get("release_sequence"),
        "source_revision": installed.get("source_revision"),
        "image_id": installed.get("image_id"),
    }


# --------------------------------------------------------------------------
# Apply: supported migration plus a preservation census
# --------------------------------------------------------------------------

class BenchRunner:
    """Run the pinned bench entrypoint and parse only structured output."""

    def __init__(self, bench: str, sites_dir: Path, *, timeout: int = 1800):
        self.bench = bench
        self.sites_dir = sites_dir
        self.timeout = timeout

    def _run(self, arguments: Sequence[str], *, timeout: int | None = None) -> subprocess.CompletedProcess:
        command = [self.bench, *arguments]
        environment = {key: value for key, value in os.environ.items()
                       if key not in ("MARIADB_ROOT_PASSWORD", "DB_PASSWORD", "ADMIN_PASSWORD")}
        environment.setdefault("HOME", "/home/frappe")
        try:
            return subprocess.run(command, cwd=self.sites_dir, env=environment, text=True,
                                  capture_output=True, timeout=timeout or self.timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise refuse("apply.counts_unavailable", f"bench could not run: {type(error).__name__}") from None

    def list_apps(self, site: str) -> list[str]:
        result = self._run(["--site", site, "list-apps", "--format", "json"], timeout=300)
        if result.returncode != 0:
            raise refuse("apply.counts_unavailable", "the installed application list is unavailable")
        try:
            value = json.loads((result.stdout or "").strip())
        except json.JSONDecodeError:
            raise refuse("apply.counts_unavailable", "the installed application list is unreadable") from None
        if not isinstance(value, list) or not all(
                isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,63}", item)
                for item in value):
            raise refuse("apply.counts_unavailable", "the installed application list is malformed")
        return sorted(value)

    def count(self, site: str, doctype: str) -> int | None:
        result = self._run(["--site", site, "execute", "frappe.db.count",
                            "--kwargs", json.dumps({"doctype": doctype})], timeout=180)
        if result.returncode != 0:
            return None
        lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
        if not lines:
            return None
        try:
            value = int(lines[-1])
        except ValueError:
            return None
        return value if value >= 0 else None

    def census(self, site: str) -> dict[str, int | None]:
        return {doctype: self.count(site, doctype) for doctype in CENSUS_DOCTYPES}

    def migrate(self, site: str) -> None:
        result = self._run(["--site", site, "migrate"], timeout=self.timeout)
        if result.returncode != 0:
            raise refuse("apply.migrate_failed", f"bench migrate exited {result.returncode}")

    def role_desk_pages(self, site: str) -> list[str]:
        result = self._run(["--site", site, "execute", "frappe.client.get_list", "--kwargs", json.dumps({
            "doctype": "Page", "filters": {"name": ["in", list(ROLE_DESK_PAGES)]},
            "fields": ["name"], "limit_page_length": len(ROLE_DESK_PAGES),
        })], timeout=300)
        if result.returncode != 0:
            raise refuse("apply.health_failed", "the role desk endpoints could not be read")
        try:
            value = json.loads((result.stdout or "").strip())
        except json.JSONDecodeError:
            raise refuse("apply.health_failed", "the role desk response is unreadable") from None
        if not isinstance(value, list):
            raise refuse("apply.health_failed", "the role desk response is malformed")
        names = []
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                names.append(item["name"])
        return sorted(set(names))


def apply_update(request: Mapping[str, object], *, now: datetime) -> dict:
    request = _require_object(request, "request")
    _require_exact_keys(request, ("action", "site", "product_root", "manifest", "signature", "trust_store",
                                  "sites_dir", "bench", "host_updater_version", "migrate_replays",
                                  "command_timeout_seconds"),
                        ("action", "site", "product_root", "manifest", "signature", "trust_store",
                         "sites_dir", "bench", "host_updater_version"), "request")
    if request["action"] != "apply":
        raise refuse("engine.request_invalid", "request action is not apply")
    if request["site"] != SITE_NAME:
        raise refuse("apply.site_invalid", "the site name is not the supported product site")
    product_root = Path(_text(request["product_root"], "request.product_root", maximum=1024))
    sites_dir = Path(_text(request["sites_dir"], "request.sites_dir", maximum=1024))
    if sites_dir.is_symlink() or not sites_dir.is_dir():
        raise refuse("apply.site_invalid", "the sites directory is missing or unsafe")
    site_dir = sites_dir / SITE_NAME
    if site_dir.is_symlink() or not site_dir.is_dir():
        raise refuse("apply.site_invalid", "the installed site directory is missing or unsafe")
    if not (site_dir / "site_config.json").is_file():
        raise refuse("apply.site_invalid", "the Frappe site configuration is missing")

    try:
        store = load_trust_store(resolve_inside(product_root, request["trust_store"], "request.trust_store"),
                                 now=now)
        manifest = verify_manifest_signature(
            resolve_inside(product_root, request["manifest"], "request.manifest"),
            resolve_inside(product_root, request["signature"], "request.signature"), store, now=now)
    except UpdateError as error:
        return _apply_report("failed", "pre-migrate", blockers=[_block(error.code, error.detail)])
    blockers: list[dict] = []
    if manifest["production_authorization"] != "AUTHORIZED":
        blockers.append(_block("policy.release_not_authorized", "release is not production-authorized"))
    if manifest["release_status"] != "PRODUCTION RELEASE":
        blockers.append(_block("policy.release_not_production", "release is a test package"))
    if blockers:
        return _apply_report("failed", "pre-migrate", blockers=blockers,
                             target_version=manifest["version"])

    migrate_replays = request.get("migrate_replays", 2)
    if not _is_int(migrate_replays) or not 1 <= migrate_replays <= 3:
        raise refuse("engine.request_invalid", "migrate_replays must be 1, 2 or 3")
    timeout = request.get("command_timeout_seconds", 1800)
    if not _is_int(timeout) or not 60 <= timeout <= 7200:
        raise refuse("engine.request_invalid", "command_timeout_seconds is out of range")
    runner = BenchRunner(_text(request["bench"], "request.bench", maximum=512), sites_dir, timeout=timeout)

    counts_before: dict[str, int | None] = {}
    apps_before: list[str] = []
    try:
        apps_before = runner.list_apps(SITE_NAME)
        counts_before = runner.census(SITE_NAME)
        if counts_before and all(value is None for value in counts_before.values()):
            raise refuse("apply.counts_unavailable",
                         "no business record could be counted before the migration")
    except UpdateError as error:
        return _apply_report("failed", "pre-migrate", blockers=[_block(error.code, error.detail)],
                             counts_before=counts_before, apps_before=apps_before,
                             target_version=manifest["version"])

    if manifest["database"]["migration"] == "supported":
        try:
            for _ in range(migrate_replays):
                runner.migrate(SITE_NAME)
        except UpdateError as error:
            return _apply_report("failed", "migrating", blockers=[_block(error.code, error.detail)],
                                 counts_before=counts_before, apps_before=apps_before,
                                 target_version=manifest["version"])

    try:
        apps_after = runner.list_apps(SITE_NAME)
        counts_after = runner.census(SITE_NAME)
        pages = runner.role_desk_pages(SITE_NAME)
    except UpdateError as error:
        return _apply_report("failed", "verify-data", blockers=[_block(error.code, error.detail)],
                             counts_before=counts_before, apps_before=apps_before,
                             target_version=manifest["version"])

    for doctype, before in counts_before.items():
        after = counts_after.get(doctype)
        if before is not None and (after is None or after < before):
            blockers.append(_block("apply.records_lost",
                                   f"{doctype}: {before} before, {after} after the migration"))
    missing_apps = [app for app in REQUIRED_APPS if app not in apps_after]
    if missing_apps:
        blockers.append(_block("apply.apps_missing", "missing applications: " + ",".join(missing_apps)))
    lost_pages = [page for page in ROLE_DESK_PAGES if page not in pages]
    if lost_pages:
        blockers.append(_block("apply.role_desk_missing", "missing role desks: " + ",".join(lost_pages)))
    status = "succeeded" if not blockers else "failed"
    return _apply_report(status, "verified" if status == "succeeded" else "verify-data",
                         blockers=blockers, counts_before=counts_before, counts_after=counts_after,
                         apps_before=apps_before, apps_after=apps_after, role_pages=pages,
                         target_version=manifest["version"])


def _apply_report(status: str, phase: str, *, blockers: list[dict] | None = None,
                  counts_before: dict | None = None, counts_after: dict | None = None,
                  apps_before: list | None = None, apps_after: list | None = None,
                  role_pages: list | None = None, target_version: str | None = None) -> dict:
    return {
        "schema_version": ENGINE_SCHEMA_VERSION,
        "document_type": DOCUMENT_RESPONSE,
        "action": "apply",
        "status": status,
        "decision": "allow" if status == "succeeded" else "refuse",
        "phase": phase,
        "blockers": blockers or [],
        "warnings": [],
        "counts_before": counts_before or {},
        "counts_after": counts_after or {},
        "apps_before": apps_before or [],
        "apps_after": apps_after or [],
        "role_desk_pages": role_pages or [],
        "target_version": target_version,
        "transaction_outcome": ("completed" if status == "succeeded"
                                else ("recovery-required"
                                      if phase in ("migrating", "verify-data") else "safe-abort")),
    }


# --------------------------------------------------------------------------
# Provider/CI bundle verification (same rules the customer updater applies)
# --------------------------------------------------------------------------

def verify_release(request: Mapping[str, object], *, now: datetime) -> dict:
    request = _require_object(request, "request")
    _require_exact_keys(request, ("action", "product_root", "trust_store", "manifest", "signature",
                                  "archive", "verify_layers"),
                        ("action", "product_root", "trust_store", "manifest", "signature", "archive"),
                        "request")
    if request["action"] != "verify-release":
        raise refuse("engine.request_invalid", "request action is not verify-release")
    product_root = Path(_text(request["product_root"], "request.product_root", maximum=1024))
    store = load_trust_store(resolve_inside(product_root, request["trust_store"], "request.trust_store"),
                             now=now)
    manifest = verify_manifest_signature(
        resolve_inside(product_root, request["manifest"], "request.manifest"),
        resolve_inside(product_root, request["signature"], "request.signature"), store, now=now)
    identity = inspect_image_archive(
        resolve_inside(product_root, request["archive"], "request.archive"),
        expected=manifest["image"], verify_layers=bool(request.get("verify_layers")))
    return {
        "schema_version": ENGINE_SCHEMA_VERSION,
        "document_type": DOCUMENT_RESPONSE,
        "action": "verify-release",
        "status": "verified",
        "decision": "allow",
        "blockers": [],
        "warnings": [],
        "target": {
            "version": manifest["version"],
            "release_sequence": manifest["release_sequence"],
            "source_revision": manifest["source_revision"],
            "release_status": manifest["release_status"],
            "production_authorization": manifest["production_authorization"],
            "signing_key_id": manifest["signature"]["key_id"],
            "image": identity,
        },
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def run(request: Mapping[str, object], *, now: datetime | None = None) -> tuple[dict, int]:
    now = now or datetime.now(timezone.utc)
    action = request.get("action") if isinstance(request, Mapping) else None
    try:
        if action == "preflight":
            response = preflight(request, now=now)
            return response, 0 if response["decision"] == "allow" else 3
        if action == "apply":
            response = apply_update(request, now=now)
            return response, 0 if response["status"] == "succeeded" else 5
        if action == "verify-release":
            return verify_release(request, now=now), 0
        raise refuse("engine.request_invalid", "unsupported action")
    except UpdateError as error:
        if error.code == "engine.request_invalid":
            status = 4
        elif action == "apply":
            status = 5
        else:
            status = 3
        return _error_response(action, error.code, error.detail), status
    except Exception as error:  # never leak internals to the customer UI
        return _error_response(action, "engine.unexpected", type(error).__name__), 5


def _error_response(action: object, code: str, detail: str) -> dict:
    if code not in MESSAGE_CODES:
        code, detail = "engine.unexpected", ""
    return {
        "schema_version": ENGINE_SCHEMA_VERSION,
        "document_type": DOCUMENT_RESPONSE,
        "action": action if isinstance(action, str) else None,
        "status": "failed",
        "decision": "refuse",
        "blockers": [{"code": code, "detail": detail[:400]}],
        "warnings": [],
        "current": {"version": None, "release_sequence": None, "source_revision": None},
        "target": None,
        "plan": None,
    }


def _read_request(arguments: argparse.Namespace) -> dict:
    path_value = arguments.request or os.environ.get("TH_UPDATE_REQUEST", "")
    if not path_value:
        raise refuse("engine.request_invalid", "no request document was supplied")
    path = Path(path_value)
    try:
        size = path.stat().st_size
    except OSError:
        raise refuse("engine.request_invalid", "the request document is missing") from None
    if path.is_symlink() or not path.is_file() or size > MAX_JSON_BYTES:
        raise refuse("engine.request_invalid", "the request document is missing or too large")
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise refuse("engine.request_invalid", "the request document is not valid JSON") from None
    if not isinstance(request, dict):
        raise refuse("engine.request_invalid", "the request document must be an object")
    return request


def _write_response(arguments: argparse.Namespace, response: dict) -> None:
    text = json.dumps(response, indent=2, sort_keys=True) + "\n"
    path_value = arguments.response or os.environ.get("TH_UPDATE_RESPONSE", "")
    if not path_value:
        sys.stdout.write(text)
        return
    target = Path(path_value)
    temporary = target.with_name(target.name + ".partial")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, target)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TOEFL House ERP safe update engine")
    parser.add_argument("--request", default="")
    parser.add_argument("--response", default="")
    parser.add_argument("--self-check", action="store_true",
                        help="validate the engine and its message catalog, then exit")
    arguments = parser.parse_args(argv)
    if arguments.self_check:
        invalid = [code for code in MESSAGE_CODES if not SAFE_TOKEN.fullmatch(code)]
        if invalid:
            sys.stderr.write("invalid message codes\n")
            return 5
        sys.stdout.write(json.dumps({"status": "ok", "engine_schema": ENGINE_SCHEMA_VERSION,
                                     "message_codes": len(MESSAGE_CODES)}, sort_keys=True) + "\n")
        return 0
    try:
        request = _read_request(arguments)
    except UpdateError as error:
        _write_response(arguments, _error_response(None, error.code, error.detail))
        return 4
    response, code = run(request)
    _write_response(arguments, response)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

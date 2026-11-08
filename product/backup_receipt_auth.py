"""Authenticated native-backup receipts.

Receipts are authenticated with a key derived from Frappe's existing
``backup_encryption_key``. That secret is already required to decrypt every
artifact, but is not stored in the receipt. PBKDF2 with a random per-receipt
salt and a fixed work factor prevents the receipt from becoming a cheap
password-verification oracle. This is a symmetric provenance guarantee: it
proves possession of the configured backup secret, not a provider's identity
or non-repudiation.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets

AUTHENTICATION_FIELD = "authentication"
AUTHENTICATION_SCHEMA = 1
AUTHENTICATION_ALGORITHM = "HMAC-SHA256"
KDF_ALGORITHM = "PBKDF2-HMAC-SHA256"
KDF_ITERATIONS = 600_000
SALT_BYTES = 16
DIGEST_BYTES = 32
_HEX_SHA256 = re.compile(r"[a-f0-9]{64}\Z")


class ReceiptAuthenticationError(ValueError):
    """Receipt authentication is absent, malformed, or does not verify."""


def _canonical_receipt_bytes(receipt: dict) -> bytes:
    if not isinstance(receipt, dict):
        raise ReceiptAuthenticationError("backup receipt is invalid")
    unsigned = {key: value for key, value in receipt.items()
                if key != AUTHENTICATION_FIELD}
    try:
        return json.dumps(unsigned, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise ReceiptAuthenticationError("backup receipt is invalid") from None


def _unique_object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_backup_secret_from_site_config(path) -> str:
    """Read only the existing Frappe backup key from a bounded site config."""
    from pathlib import Path

    path = Path(path)
    try:
        if (not path.is_absolute() or path.is_symlink() or not path.is_file()
                or path.stat().st_size > 1024 * 1024):
            raise OSError
        for parent in path.parents:
            if parent.is_symlink():
                raise OSError
        with path.open("r", encoding="utf-8") as stream:
            config = json.load(stream, object_pairs_hook=_unique_object_pairs,
                               parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
    except (OSError, UnicodeError, ValueError, TypeError):
        raise ReceiptAuthenticationError(
            "the site backup encryption key is unavailable") from None
    if not isinstance(config, dict):
        raise ReceiptAuthenticationError(
            "the site backup encryption key is unavailable")
    secret = config.get("backup_encryption_key")
    if (not isinstance(secret, str) or not secret or not secret.isascii()
            or len(secret) > 4096):
        raise ReceiptAuthenticationError(
            "the site backup encryption key is unavailable")
    return secret


def _derive_key(secret: str, salt: bytes) -> bytes:
    if (not isinstance(secret, str) or not secret or not secret.isascii()
            or len(secret) > 4096 or not isinstance(salt, bytes)
            or len(salt) != SALT_BYTES):
        raise ReceiptAuthenticationError("backup receipt authentication is invalid")
    return hashlib.pbkdf2_hmac("sha256", secret.encode("ascii"), salt,
                               KDF_ITERATIONS, dklen=DIGEST_BYTES)


def authenticate_backup_receipt(receipt: dict, backup_secret: str) -> dict:
    """Attach a new keyed authenticator to a receipt in place and return it."""
    receipt.pop(AUTHENTICATION_FIELD, None)
    salt = secrets.token_bytes(SALT_BYTES)
    key = _derive_key(backup_secret, salt)
    signature = hmac.new(key, _canonical_receipt_bytes(receipt),
                         hashlib.sha256).hexdigest()
    receipt[AUTHENTICATION_FIELD] = {
        "schema": AUTHENTICATION_SCHEMA,
        "algorithm": AUTHENTICATION_ALGORITHM,
        "kdf": KDF_ALGORITHM,
        "iterations": KDF_ITERATIONS,
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "payload_b64": base64.b64encode(_canonical_receipt_bytes(receipt)).decode("ascii"),
        "mac_hex": signature,
    }
    return receipt


def verify_backup_receipt_authentication(receipt: dict, backup_secret: str) -> None:
    """Require a well-formed HMAC using the exact supported KDF parameters."""
    if not isinstance(receipt, dict):
        raise ReceiptAuthenticationError("backup receipt authentication is invalid")
    auth = receipt.get(AUTHENTICATION_FIELD)
    expected_keys = {"schema", "algorithm", "kdf", "iterations", "salt_b64",
                     "payload_b64", "mac_hex"}
    if (not isinstance(auth, dict) or set(auth) != expected_keys
            or type(auth.get("schema")) is not int
            or auth.get("schema") != AUTHENTICATION_SCHEMA
            or auth.get("algorithm") != AUTHENTICATION_ALGORITHM
            or auth.get("kdf") != KDF_ALGORITHM
            or type(auth.get("iterations")) is not int
            or auth.get("iterations") != KDF_ITERATIONS
            or not isinstance(auth.get("salt_b64"), str)
            or not isinstance(auth.get("payload_b64"), str)
            or len(auth.get("payload_b64", "")) > 96 * 1024
            or not isinstance(auth.get("mac_hex"), str)
            or not _HEX_SHA256.fullmatch(auth["mac_hex"])):
        raise ReceiptAuthenticationError("backup receipt authentication is missing or unsupported")
    try:
        salt = base64.b64decode(auth["salt_b64"], validate=True)
        signed_payload = base64.b64decode(auth["payload_b64"], validate=True)
        if len(salt) != SALT_BYTES or not signed_payload:
            raise ValueError
        payload_object = json.loads(signed_payload.decode("utf-8"),
                                    object_pairs_hook=_unique_object_pairs,
                                    parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
        unsigned_receipt = {key: value for key, value in receipt.items()
                            if key != AUTHENTICATION_FIELD}
        if payload_object != unsigned_receipt:
            raise ValueError
        key = _derive_key(backup_secret, salt)
        expected = hmac.new(key, signed_payload, hashlib.sha256).hexdigest()
    except (ValueError, TypeError):
        raise ReceiptAuthenticationError("backup receipt authentication is invalid") from None
    if not hmac.compare_digest(expected, auth["mac_hex"]):
        raise ReceiptAuthenticationError("backup receipt authentication did not verify")

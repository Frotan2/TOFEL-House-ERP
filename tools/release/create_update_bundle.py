#!/usr/bin/env python3
"""Provider-side signing tool for the TOEFL House ERP customer update channel.

The customer never invents trust and never builds software. This tool is the
provider half of the protocol:

* ``bundle`` reads an already-built, already-tested customer package (the
  prebuilt image archive plus its ``release-manifest.json``), writes the
  canonical *update* manifest, signs it with the offline provider key, writes
  the channel index, and verifies its own output with the same engine that runs
  on the customer PC.
* ``trust-store`` turns the provider public key into the trust anchor that is
  provisioned separately on a customer PC.
* ``sign`` signs one approval of a site-specific two-person recovery
  authorization.  Each approver (Course Owner, then General Manager or
  designated recovery authority) runs it separately with their own offline
  key, over the identical document bytes, into a separate signature file;
  the customer engine requires both signatures before any migration.

Nothing here can invent authorization: the release status and the production
authorization string are copied from the package manifest. A package that says
``TEST PACKAGE - NO REAL DATA`` / ``REJECT`` therefore produces a signed update
that every customer engine refuses, which is the current release posture.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_DIR = ROOT / "product"
if str(PRODUCT_DIR) not in sys.path:
    sys.path.insert(0, str(PRODUCT_DIR))

import update_engine as engine  # noqa: E402  (path insertion is deliberate)

IMAGE_ARCHIVE = "toefl-house-erp-app.tar"
UPDATE_MANIFEST = "update.json"
UPDATE_SIGNATURE = "update.json.sig"
UPDATE_INDEX = "index.json"
TRUST_STORE = "trust-store.json"
# The first product release that carried this updater/engine protocol. A
# release may raise the floor with --minimum-host-updater-version.
FIRST_UPDATER_VERSION = "2026.10.24"
MAX_TRUST_DAYS = 3660


class ReleaseRefused(ValueError):
    """A provider input is missing, inconsistent or unsafe."""


def fail(message: str) -> "ReleaseRefused":
    return ReleaseRefused(message)


def read_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise fail(f"{label} is unreadable: {error}") from None
    if not isinstance(value, dict):
        raise fail(f"{label} must be a JSON object")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def write_bytes(path: Path, value: bytes) -> None:
    path.write_bytes(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def openssl(arguments: list[str], *, executable: str) -> bytes:
    found = shutil.which(executable)
    if found is None:
        raise fail("openssl is required for signing and was not found on PATH")
    completed = subprocess.run([found, *arguments], capture_output=True, check=False)
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", "replace").strip().splitlines()
        raise fail("openssl failed: " + (message[-1] if message else str(completed.returncode)))
    return completed.stdout


def public_key(private_key: Path, executable: str) -> tuple[int, int]:
    der = openssl(["pkey", "-in", str(private_key), "-pubout", "-outform", "DER"], executable=executable)
    return engine.parse_rsa_public_key(der)


def sign_bytes(private_key: Path, payload: bytes, executable: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="toefl-signature-") as folder:
        source = Path(folder) / "payload.bin"
        signed = Path(folder) / "signature.bin"
        write_bytes(source, payload)
        openssl(["dgst", "-sha256", "-sign", str(private_key), "-out", str(signed), str(source)],
                executable=executable)
        return signed.read_bytes()


def signature_envelope(document_type: str, key_id: str, signature: bytes) -> dict:
    return {
        "schema_version": 1,
        "document_type": document_type,
        "algorithm": engine.SIGNATURE_ALGORITHMS[0],
        "key_id": key_id,
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }


def trust_store_document(private_key: Path, key_id: str, *, days: int, executable: str) -> dict:
    if not 1 <= days <= MAX_TRUST_DAYS:
        raise fail(f"trust key lifetime must be between 1 and {MAX_TRUST_DAYS} days")
    modulus, exponent = public_key(private_key, executable)
    modulus_bytes = modulus.to_bytes((modulus.bit_length() + 7) // 8, "big")
    exponent_bytes = exponent.to_bytes((exponent.bit_length() + 7) // 8, "big")
    if exponent != 65537:
        raise fail("the provider signing key must use the public exponent 65537")
    if not 256 <= len(modulus_bytes) <= 512:
        raise fail("the provider signing key must be RSA 2048-4096 bits")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return {
        "schema_version": engine.TRUST_SCHEMA_VERSION,
        "document_type": engine.DOCUMENT_TRUST,
        "product": engine.PRODUCT,
        "provisioned": True,
        "keys": [{
            "key_id": key_id,
            "algorithm": engine.SIGNATURE_ALGORITHMS[0],
            "purposes": ["update-manifest", "recovery-authorization"],
            "modulus_b64": base64.b64encode(modulus_bytes).decode("ascii"),
            "exponent_b64": base64.b64encode(exponent_bytes).decode("ascii"),
            "not_before_utc": utc(now - timedelta(days=1)),
            "not_after_utc": utc(now + timedelta(days=days)),
        }],
    }


def check_key_id(key_id: object) -> str:
    if not isinstance(key_id, str) or not engine.KEY_ID.fullmatch(key_id):
        raise fail("key id must be lowercase letters, digits, dot, dash or underscore (3-64 characters)")
    return key_id


def release_identity(package_manifest: dict, archive: Path) -> dict:
    version = engine._text(package_manifest.get("version"), "package.version",
                           pattern=engine.SAFE_VERSION, maximum=64)
    revision = engine._text(package_manifest.get("source_revision"), "package.source_revision",
                            pattern=engine.HEX40, maximum=40)
    release_status = package_manifest.get("release_status")
    if release_status not in engine.RELEASE_STATUSES:
        raise fail("package release status is not a supported release status")
    authorization = package_manifest.get("production_authorization")
    if authorization not in engine.AUTHORIZATIONS:
        raise fail("package production authorization is not a supported value")
    image = package_manifest.get("image")
    if not isinstance(image, dict):
        raise fail("package manifest has no image identity block")
    if image.get("tag") != engine.IMAGE_TAG:
        raise fail(f"package image tag must be {engine.IMAGE_TAG!r}")
    if not archive.is_file() or archive.is_symlink():
        raise fail(f"the prebuilt image archive is missing: {archive}")
    digest = sha256_file(archive)
    if image.get("sha256") != digest:
        raise fail("the image archive does not match the package manifest SHA-256")
    if image.get("size_bytes") != archive.stat().st_size:
        raise fail("the image archive does not match the package manifest size")
    labels = image.get("labels")
    if not isinstance(labels, dict):
        raise fail("package manifest image labels are missing")
    expected = {
        "org.toefl-house.source-eol": "lf-v1",
        "org.toefl-house.source-revision": revision,
        "org.toefl-house.release-version": version,
    }
    for name, value in expected.items():
        if labels.get(name) != value:
            raise fail(f"package image label {name} does not match the package identity")
    config_digest = engine._text(image.get("config_digest"), "package.image.config_digest",
                                 pattern=engine.SHA256_TAG, maximum=71)
    return {
        "version": version,
        "revision": revision,
        "release_status": release_status,
        "production_authorization": authorization,
        "archive_sha256": digest,
        "archive_size_bytes": archive.stat().st_size,
        "config_digest": config_digest,
        "labels": {name: expected[name] for name in expected},
    }


def update_manifest(arguments: argparse.Namespace, identity: dict, now: datetime) -> dict:
    try:
        derived = engine.release_sequence(identity["version"])
    except engine.UpdateError:
        derived = None
    sequence = arguments.sequence if arguments.sequence is not None else derived
    if sequence is None:
        raise fail("this version has no date-derived release sequence; pass --sequence explicitly")
    if arguments.sequence is not None and derived is not None and arguments.sequence != derived:
        raise fail("--sequence must equal the date-derived release sequence for a dated version")
    if arguments.minimum_installed_version is None:
        minimum_version = arguments.minimum_host_updater_version
    else:
        minimum_version = arguments.minimum_installed_version
    if arguments.target_schema_version:
        target_schema = arguments.target_schema_version
    else:
        candidate = "frappe-v16-" + identity["version"].lower()
        if not engine.SAFE_TOKEN.fullmatch(candidate):
            raise fail("pass --target-schema-version: it cannot be derived from this version")
        target_schema = candidate
    minimum_sequence = arguments.minimum_installed_sequence
    maximum_sequence = arguments.maximum_installed_sequence
    if (minimum_sequence is not None and maximum_sequence is not None
            and minimum_sequence > maximum_sequence):
        raise fail("the installed sequence window is inverted")
    database = {
        "migration": arguments.migration,
        "reversible": bool(arguments.reversible),
        "requires_verified_backup": True,
        "target_schema_version": target_schema,
    }
    if arguments.minimum_source_schema_version:
        database["minimum_source_schema_version"] = arguments.minimum_source_schema_version
    requirements = {
        "minimum_host_updater_version": arguments.minimum_host_updater_version,
        "engine_schema": arguments.engine_schema,
        "minimum_installed_version": minimum_version,
        "minimum_free_bytes": arguments.minimum_free_bytes,
        "backup": {
            "required": True,
            "max_age_hours": arguments.backup_max_age_hours,
            "require_restore_verification": True,
        },
        "recovery_authorization": {
            "required": True,
            "max_age_hours": arguments.recovery_max_age_hours,
        },
    }
    if minimum_sequence is not None:
        requirements["minimum_installed_sequence"] = minimum_sequence
    if maximum_sequence is not None:
        requirements["maximum_installed_sequence"] = maximum_sequence
    return {
        "schema_version": engine.MANIFEST_SCHEMA_VERSION,
        "document_type": engine.DOCUMENT_UPDATE,
        "product": engine.PRODUCT,
        "channel": arguments.channel,
        "version": identity["version"],
        "release_sequence": sequence,
        "source_revision": identity["revision"],
        "release_status": identity["release_status"],
        "production_authorization": identity["production_authorization"],
        "issued_utc": utc(now),
        "notes": arguments.notes or "",
        "requirements": requirements,
        "database": database,
        "image": {
            "tag": engine.IMAGE_TAG,
            "archive": IMAGE_ARCHIVE,
            "sha256": identity["archive_sha256"],
            "size_bytes": identity["archive_size_bytes"],
            "config_digest": identity["config_digest"],
            "labels": identity["labels"],
        },
        "updater": {"engine_schema": engine.ENGINE_SCHEMA_VERSION, "strings_schema": 1},
        "signature": {"key_id": arguments.key_id, "algorithm": engine.SIGNATURE_ALGORITHMS[0]},
    }


def index_document(arguments: argparse.Namespace, manifest: dict, now: datetime) -> dict:
    return {
        "schema_version": 1,
        "document_type": "toefl-house-erp-update-index",
        "product": engine.PRODUCT,
        "channel": arguments.channel,
        "generated_utc": utc(now),
        "latest": {
            "version": manifest["version"],
            "release_sequence": manifest["release_sequence"],
            "source_revision": manifest["source_revision"],
            "manifest": UPDATE_MANIFEST,
            "signature": UPDATE_SIGNATURE,
            "archive": IMAGE_ARCHIVE,
            "archive_sha256": manifest["image"]["sha256"],
            "archive_size_bytes": manifest["image"]["size_bytes"],
            "issued_utc": manifest["issued_utc"],
        },
    }


def verify_published_bundle(out: Path, trust_store: Path, archive: Path, now: datetime) -> dict:
    """Verify the produced folder exactly the way the customer engine does."""
    staged_store = out / TRUST_STORE
    remove_store = False
    staged_archive = out / IMAGE_ARCHIVE
    remove_archive = False
    if trust_store.resolve() != staged_store.resolve():
        if staged_store.exists():
            raise fail("a different trust store already occupies the output folder")
        if trust_store.resolve().parent == out.resolve():
            raise fail("a trust store with an unexpected name is already in the output folder")
        shutil.copy2(trust_store, staged_store)
        remove_store = True
    if archive.resolve() != staged_archive.resolve() and not staged_archive.exists():
        try:
            staged_archive.hardlink_to(archive.resolve())
        except OSError:
            shutil.copy2(archive, staged_archive)
        remove_archive = True
    try:
        return engine.verify_release({
            "action": "verify-release",
            "product_root": str(out),
            "trust_store": TRUST_STORE,
            "manifest": UPDATE_MANIFEST,
            "signature": UPDATE_SIGNATURE,
            "archive": IMAGE_ARCHIVE,
            "verify_layers": True,
        }, now=now)
    finally:
        if remove_store:
            staged_store.unlink(missing_ok=True)
        if remove_archive:
            staged_archive.unlink(missing_ok=True)


def publish(out: Path, documents: dict[str, object], archive: Path | None) -> list[str]:
    """Write every document, or nothing at all."""
    if out.exists() and not out.is_dir():
        raise fail(f"the output path is not a folder: {out}")
    wrote: list[Path] = []
    try:
        out.mkdir(parents=True, exist_ok=True)
        for name, value in documents.items():
            target = out / name
            if target.exists():
                raise fail(f"refusing to overwrite an existing file: {target}")
            if isinstance(value, bytes):
                write_bytes(target, value)
            else:
                write_json(target, value)
            wrote.append(target)
        if archive is not None:
            target = out / IMAGE_ARCHIVE
            if target.exists():
                raise fail(f"refusing to overwrite an existing file: {target}")
            shutil.copy2(archive, target)
            wrote.append(target)
    except BaseException:
        for path in wrote:
            path.unlink(missing_ok=True)
        raise
    return sorted(path.name for path in wrote)


def command_bundle(arguments: argparse.Namespace) -> int:
    release_dir = arguments.release_dir.resolve()
    manifest_path = release_dir / "release-manifest.json"
    package_manifest = read_json(manifest_path, "package release manifest")
    checksum_path = release_dir / "release-manifest.json.sha256"
    if checksum_path.is_file():
        published = checksum_path.read_text(encoding="utf-8").split()
        if not published or not engine.HEX64.fullmatch(published[0].strip().lower()):
            raise fail("release-manifest.json.sha256 does not contain a SHA-256 digest")
        if published[0].strip().lower() != sha256_file(manifest_path):
            raise fail("release-manifest.json does not match its published checksum")
    archive = (arguments.archive or (release_dir / IMAGE_ARCHIVE)).resolve()
    identity = release_identity(package_manifest, archive)
    key_id = check_key_id(arguments.key_id)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    manifest = update_manifest(arguments, identity, now)
    raw = engine.canonical_manifest_bytes(manifest)
    signature = sign_bytes(arguments.private_key, raw, arguments.openssl)
    modulus, exponent = public_key(arguments.private_key, arguments.openssl)
    if not engine.rsa_pkcs1v15_sha256_verify(modulus, exponent, raw, signature):
        raise fail("the produced signature does not verify with the supplied key")
    envelope = signature_envelope(engine.DOCUMENT_UPDATE_SIGNATURE, key_id, signature)
    documents = {
        UPDATE_MANIFEST: raw,
        UPDATE_SIGNATURE: envelope,
        UPDATE_INDEX: index_document(arguments, manifest, now),
    }
    out = arguments.out.resolve()
    if arguments.trust_store_out:
        store_path = Path(arguments.trust_store_out).resolve()
        if store_path.exists():
            raise fail(f"refusing to overwrite an existing trust store: {store_path}")
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store = trust_store_document(arguments.private_key, key_id,
                                     days=arguments.trust_days, executable=arguments.openssl)
        write_json(store_path, store)
        engine.load_trust_store(store_path, now=now)
    else:
        raise fail("--trust-store-out is required so the customer trust anchor is reproducible")
    files = publish(out, documents, archive if arguments.copy_archive else None)
    verified = verify_published_bundle(out, store_path, archive, now)
    if verified["target"]["version"] != manifest["version"]:
        raise fail("the engine verified a different version than the one signed")
    print(json.dumps({
        "status": "signed",
        "version": manifest["version"],
        "release_sequence": manifest["release_sequence"],
        "release_status": manifest["release_status"],
        "production_authorization": manifest["production_authorization"],
        "channel": manifest["channel"],
        "output": str(out),
        "files": files,
        "trust_store": str(store_path),
        "engine_verification": "verified",
        "customer_policy": ("customers can install this release"
                            if manifest["production_authorization"] == "AUTHORIZED"
                            and manifest["release_status"] == "PRODUCTION RELEASE"
                            else "every customer engine refuses this release until the provider "
                                 "issues a production-authorized package"),
    }, indent=2, sort_keys=True))
    return 0


def command_trust_store(arguments: argparse.Namespace) -> int:
    key_id = check_key_id(arguments.key_id)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    out = Path(arguments.out).resolve()
    if out.exists():
        raise fail(f"refusing to overwrite an existing trust store: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, trust_store_document(arguments.private_key, key_id,
                                         days=arguments.days, executable=arguments.openssl))
    store = engine.load_trust_store(out, now=now)
    print(json.dumps({"status": "provisioned", "trust_store": str(out), "key_id": key_id,
                      "keys": len(store["keys"])}, indent=2, sort_keys=True))
    return 0


def command_sign(arguments: argparse.Namespace) -> int:
    key_id = check_key_id(arguments.key_id)
    document = Path(arguments.document).resolve()
    payload = document.read_bytes()
    parsed = read_json(document, "document to sign")
    expected = {
        "update-manifest": engine.DOCUMENT_UPDATE,
        "recovery-authorization": engine.DOCUMENT_RECOVERY,
    }[arguments.document_type]
    if parsed.get("document_type") != expected:
        raise fail(f"the document must be a {expected!r} document")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if arguments.document_type == "recovery-authorization":
        for name in ("site", "scope", "operation", "request_id", "issued_utc", "expires_utc",
                     "owner_key_custody_verified", "rehearsal_restore_verified",
                     "backup_receipt_sha256", "approvals"):
            if name not in parsed:
                raise fail(f"the recovery authorization is missing {name}")
        if parsed.get("schema_version") != engine.RECOVERY_AUTHORIZATION_SCHEMA_VERSION:
            raise fail("only a schema-2 two-person recovery authorization may be signed")
        if parsed["scope"] != "site-update" or parsed["operation"] != "site-update":
            raise fail("a recovery authorization must be bound to a site-update operation")
        if not isinstance(parsed["request_id"], str) \
                or not engine.RECOVERY_REQUEST_ID.fullmatch(parsed["request_id"]):
            raise fail("recovery request_id must be 32 lowercase hex characters")
        approvals = parsed["approvals"]
        if not isinstance(approvals, list) or len(approvals) != 2:
            raise fail("recovery requires exactly two approvers")
        roles = [entry.get("approver_role") for entry in approvals if isinstance(entry, dict)]
        identities = [entry.get("approver_identity") for entry in approvals if isinstance(entry, dict)]
        key_ids = [entry.get("key_id") for entry in approvals if isinstance(entry, dict)]
        if len(roles) != 2 or len(set(roles)) != 2 or len(set(identities)) != 2 \
                or len(set(key_ids)) != 2 or "course-owner" not in roles \
                or not (set(roles) & {"general-manager", "recovery-authority"}):
            raise fail("recovery requires one Course Owner and one independent "
                       "General Manager or designated recovery authority, with distinct identities")
        if key_id not in key_ids:
            raise fail("the signing key must be one of the named recovery approvers; "
                       "each approver signs the same document with their own key, "
                       "into a separate signature file")
        if parsed["owner_key_custody_verified"] is not True or parsed["rehearsal_restore_verified"] is not True:
            raise fail("recovery authorization requires verified key custody and a verified rehearsal restore")
        if not isinstance(parsed["backup_receipt_sha256"], str) or not engine.HEX64.fullmatch(
                parsed["backup_receipt_sha256"]):
            raise fail("backup_receipt_sha256 must be the SHA-256 of the verified backup receipt")
    else:
        engine.validate_manifest(parsed, now=now)
    signature = sign_bytes(arguments.private_key, payload, arguments.openssl)
    envelope_type = (engine.DOCUMENT_UPDATE_SIGNATURE if arguments.document_type == "update-manifest"
                     else engine.DOCUMENT_RECOVERY_SIGNATURE)
    out = Path(arguments.out).resolve()
    if out.exists():
        raise fail(f"refusing to overwrite an existing signature: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, signature_envelope(envelope_type, key_id, signature))
    with tempfile.TemporaryDirectory(prefix="toefl-trust-") as folder:
        store_path = Path(folder) / TRUST_STORE
        write_json(store_path, trust_store_document(arguments.private_key, key_id, days=1,
                                                    executable=arguments.openssl))
        try:
            store = engine.load_trust_store(store_path, now=now)
        except engine.UpdateError as error:
            raise fail(f"the signing key is not usable: {error}") from None
        try:
            if arguments.document_type == "recovery-authorization":
                # This invocation produces only one of the two required
                # approvals, so full two-person validation cannot pass here
                # yet: the engine validates both signatures, the approver
                # binding and the request id at preflight.  Verify only that
                # this signature itself is valid for the signing key.
                key = engine.select_key(store, key_id, "recovery-authorization", now=now)
                if not engine.rsa_pkcs1v15_sha256_verify(key["modulus"], key["exponent"],
                                                         payload, signature):
                    raise fail("the produced recovery signature does not verify")
            else:
                key = engine.select_key(store, key_id, "update-manifest", now=now)
                if not engine.rsa_pkcs1v15_sha256_verify(key["modulus"], key["exponent"], payload, signature):
                    raise fail("the produced update signature does not verify")
        finally:
            store_path.unlink(missing_ok=True)
    print(json.dumps({"status": "signed", "document": str(document), "signature": str(out),
                      "document_type": arguments.document_type, "key_id": key_id},
                     indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    bundle = subparsers.add_parser("bundle", help="sign a built package for the update channel")
    bundle.add_argument("--release-dir", required=True, type=Path,
                        help="folder with release-manifest.json and the prebuilt image archive")
    bundle.add_argument("--archive", type=Path, default=None,
                        help="image archive path when it is not inside --release-dir")
    bundle.add_argument("--private-key", required=True, type=Path,
                        help="offline PEM RSA private key; never share or commit it")
    bundle.add_argument("--key-id", required=True, help="public name of the signing key")
    bundle.add_argument("--channel", default="stable")
    bundle.add_argument("--out", required=True, type=Path)
    bundle.add_argument("--trust-store-out", required=True, type=Path,
                        help="write the customer trust anchor for this key")
    bundle.add_argument("--trust-days", type=int, default=1825)
    bundle.add_argument("--notes", default="")
    bundle.add_argument("--sequence", type=int, default=None,
                        help="only for versions without a date-derived sequence")
    bundle.add_argument("--minimum-host-updater-version", default=FIRST_UPDATER_VERSION)
    bundle.add_argument("--minimum-installed-version", default=None)
    bundle.add_argument("--minimum-installed-sequence", type=int, default=None)
    bundle.add_argument("--maximum-installed-sequence", type=int, default=None)
    bundle.add_argument("--minimum-free-bytes", type=int, default=engine.MIN_FREE_BYTES_FLOOR)
    bundle.add_argument("--backup-max-age-hours", type=int, default=24)
    bundle.add_argument("--recovery-max-age-hours", type=int, default=72)
    bundle.add_argument("--migration", choices=list(engine.MIGRATION_MODES), default="supported")
    bundle.add_argument("--reversible", action="store_true",
                        help="declare a reversible migration (default: not reversible)")
    bundle.add_argument("--target-schema-version", default="")
    bundle.add_argument("--minimum-source-schema-version", default="")
    bundle.add_argument("--engine-schema", type=int, default=engine.ENGINE_SCHEMA_VERSION)
    bundle.add_argument("--copy-archive", action="store_true",
                        help="also copy the image archive into the channel folder")
    bundle.add_argument("--openssl", default="openssl")
    bundle.set_defaults(handler=command_bundle)

    trust = subparsers.add_parser("trust-store", help="create the customer trust anchor")
    trust.add_argument("--private-key", required=True, type=Path)
    trust.add_argument("--key-id", required=True)
    trust.add_argument("--out", required=True, type=Path)
    trust.add_argument("--days", type=int, default=1825)
    trust.add_argument("--openssl", default="openssl")
    trust.set_defaults(handler=command_trust_store)

    sign = subparsers.add_parser("sign", help="sign an update or recovery document")
    sign.add_argument("--document", required=True, type=Path)
    sign.add_argument("--private-key", required=True, type=Path)
    sign.add_argument("--key-id", required=True)
    sign.add_argument("--document-type", required=True,
                      choices=["update-manifest", "recovery-authorization"])
    sign.add_argument("--out", required=True, type=Path)
    sign.add_argument("--openssl", default="openssl")
    sign.set_defaults(handler=command_sign)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        return arguments.handler(arguments)
    except (ReleaseRefused, engine.UpdateError, OSError) as error:
        sys.stderr.write(f"release bundle refused: {error}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Safety contracts for the Windows safe-update engine.

These tests exercise the real decision code that runs inside the pinned product
image during a customer update: release-signature verification, image identity
binding, version/compatibility policy, backup and recovery evidence, host
preconditions, the supported migration census, and the machine protocol.

They run without Docker, Windows or a live Frappe site.  The Windows launcher,
HTTPS transport and real Docker lifecycle are covered by
tests/foundation/test_windows_safe_update.ps1 in the Windows CI job.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

import update_engine as engine  # noqa: E402

NOW = datetime(2026, 10, 24, 9, 30, tzinfo=timezone.utc)
OPENSSL = shutil.which("openssl")
KDF = "org.toefl-house.source-revision"
VERSION_LABEL = "org.toefl-house.release-version"


def iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RsaKey:
    """Ephemeral RSA test key; the private half never enters the repository."""

    def __init__(self, directory: Path, name: str):
        if OPENSSL is None:  # pragma: no cover - CI images ship openssl
            raise unittest.SkipTest("openssl is required for update signature tests")
        self.directory = directory
        self.name = name
        self.private = directory / f"{name}.pem"
        self.public_der = directory / f"{name}.der"
        subprocess.run([OPENSSL, "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                        "-out", str(self.private)], check=True, capture_output=True)
        subprocess.run([OPENSSL, "pkey", "-in", str(self.private), "-pubout", "-outform", "DER",
                        "-out", str(self.public_der)], check=True, capture_output=True)
        self.modulus, self.exponent = engine.parse_rsa_public_key(self.public_der.read_bytes())

    def sign(self, payload: bytes) -> bytes:
        message = self.directory / f"{self.name}-message.bin"
        signature = self.directory / f"{self.name}-signature.bin"
        message.write_bytes(payload)
        subprocess.run([OPENSSL, "dgst", "-sha256", "-sign", str(self.private), "-out", str(signature),
                        str(message)], check=True, capture_output=True)
        return signature.read_bytes()

    def trust_entry(self, key_id: str, purposes: tuple[str, ...],
                    not_before: datetime = NOW - timedelta(days=1),
                    not_after: datetime = NOW + timedelta(days=365)) -> dict:
        modulus = self.modulus.to_bytes((self.modulus.bit_length() + 7) // 8, "big")
        return {
            "key_id": key_id,
            "algorithm": "rsa-pkcs1v15-sha256",
            "purposes": list(purposes),
            "modulus_b64": base64.b64encode(modulus).decode("ascii"),
            "exponent_b64": base64.b64encode(self.exponent.to_bytes(3, "big")).decode("ascii"),
            "not_before_utc": iso(not_before),
            "not_after_utc": iso(not_after),
        }


def signature_envelope(document_type: str, key_id: str, signature: bytes) -> dict:
    return {
        "schema_version": 1,
        "document_type": document_type,
        "algorithm": "rsa-pkcs1v15-sha256",
        "key_id": key_id,
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }


def image_archive(directory: Path, version: str, revision: str, *, extra_labels: dict | None = None,
                  padding: bool = True) -> tuple[Path, dict]:
    """A real Docker-save layout with a small filesystem layer."""
    layer_buffer = io.BytesIO()
    with tarfile.open(fileobj=layer_buffer, mode="w") as layer:
        content = b"application layer\n"
        member = tarfile.TarInfo("application.txt")
        member.size = len(content)
        layer.addfile(member, io.BytesIO(content))
        if padding:
            # Keep the archive above the engine's sanity floor.
            filler = b"x" * 8192
            fifo = tarfile.TarInfo("padding.bin")
            fifo.size = len(filler)
            layer.addfile(fifo, io.BytesIO(filler))
    layer_bytes = layer_buffer.getvalue()
    labels = {
        "org.toefl-house.source-eol": "lf-v1",
        KDF: revision,
        VERSION_LABEL: version,
    }
    if extra_labels:
        labels.update(extra_labels)
    config = json.dumps({
        "architecture": "amd64",
        "os": "linux",
        "config": {"Labels": labels},
        "rootfs": {"type": "layers", "diff_ids": ["sha256:" + hashlib.sha256(layer_bytes).hexdigest()]},
    }, sort_keys=True).encode()
    config_digest = hashlib.sha256(config).hexdigest()
    manifest = [{"Config": config_digest + ".json", "RepoTags": [engine.IMAGE_TAG],
                 "Layers": ["layer/layer.tar"]}]
    path = directory / f"toefl-house-erp-app-{version}.tar"
    with tarfile.open(path, "w") as archive:
        for name, data in (("manifest.json", json.dumps(manifest).encode()), (config_digest + ".json", config),
                           ("layer/layer.tar", layer_bytes)):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return path, {"config_digest": "sha256:" + config_digest, "labels": labels,
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size}


class UpdateFixture:
    """A complete synthetic product root, release bundle and site evidence."""

    def __init__(self, base: Path, *, version: str = "2026.11.01", sequence: int = 43,
                 previous_version: str = "2026.10.01", previous_sequence: int = 42,
                 release_status: str = "PRODUCTION RELEASE",
                 authorization: str = "AUTHORIZED", migration: str = "supported",
                 reversible: bool = False, recovery_required: bool = True):
        self.base = base
        self.product_root = base / "product"
        self.data = self.product_root / "data"
        self.site = self.data / "sites" / engine.SITE_NAME
        self.backup_dir = self.site / "private" / "backups"
        self.package = self.product_root / "release"
        self.staging = self.data / "update" / "staging" / version
        self.evidence = self.data / "update" / "evidence"
        for directory in (self.data / "secrets", self.site, self.backup_dir, self.package,
                          self.staging, self.evidence):
            directory.mkdir(parents=True, exist_ok=True)
        (self.data / "secrets" / "db.env").write_text("MARIADB_ROOT_PASSWORD=test\n", encoding="utf-8")
        (self.site / "site_config.json").write_text('{"db_name": "test"}\n', encoding="utf-8")
        self.version = version
        self.sequence = sequence
        self.previous_version = previous_version
        self.previous_sequence = previous_sequence
        self.release_status = release_status
        self.authorization = authorization
        self.migration = migration
        self.reversible = reversible
        self.recovery_required = recovery_required
        self.signing = RsaKey(base, "release-key")
        self.support = RsaKey(base, "support-key")
        self.trust_store_rel = "release/trusted-publisher-keys.json"
        self.channel_rel = "release/update-channels.json"
        self.write_trust_store()
        self.write_channel()
        self.archive, self.identity = image_archive(base, version, "a" * 40)
        self.manifest = self.build_manifest()
        self.manifest_rel, self.signature_rel = self.write_signed_manifest(self.manifest, "update")
        self.write_backup_receipt()
        self.write_recovery_authorization()

    # -- configuration ---------------------------------------------------
    def write_trust_store(self, *, include_support: bool = True, key_override: dict | None = None,
                          provisioned: bool = True, keys: list | None = None) -> None:
        entries = keys if keys is not None else [
            self.signing.trust_entry("release-2026a", ("update-manifest",)),
        ]
        if include_support and keys is None:
            entries = list(entries) + [self.support.trust_entry("support-2026a", ("recovery-authorization",))]
        if key_override:
            entries = [{**entry, **key_override} for entry in entries]
        store = {
            "schema_version": 1,
            "document_type": "toefl-house-erp-update-trust-store",
            "product": engine.PRODUCT,
            "provisioned": provisioned,
            "keys": entries,
        }
        (self.product_root / self.trust_store_rel).write_text(json.dumps(store, indent=2), encoding="utf-8")

    def write_channel(self, *, enabled: bool = True) -> None:
        config = {
            "schema_version": 1,
            "document_type": "toefl-house-erp-update-channels",
            "product": engine.PRODUCT,
            "default_channel": "official",
            "channels": [{
                "id": "official",
                "provider": "Frotan2/TOFEL-House-ERP",
                "metadata_url": "https://api.github.com/repos/Frotan2/TOFEL-House-ERP/releases/latest",
                "allowed_hosts": ["api.github.com", "github.com", "objects.githubusercontent.com"],
                "required_assets": ["update-manifest.json", "update-manifest.json.sig",
                                    "toefl-house-erp-app.tar", "toefl-house-erp-app.tar.sha256"],
                "enabled": enabled,
            }],
        }
        (self.product_root / self.channel_rel).write_text(json.dumps(config, indent=2), encoding="utf-8")

    def build_manifest(self, **overrides) -> dict:
        manifest = {
            "schema_version": 1,
            "document_type": engine.DOCUMENT_UPDATE,
            "product": engine.PRODUCT,
            "channel": "official",
            "version": self.version,
            "release_sequence": self.sequence,
            "source_revision": "a" * 40,
            "release_status": self.release_status,
            "production_authorization": self.authorization,
            "issued_utc": iso(NOW - timedelta(hours=2)),
            "notes": "Synthetic test release.",
            "requirements": {
                "minimum_host_updater_version": "2026.10.24",
                "engine_schema": 1,
                "minimum_installed_version": "2026.10.01",
                "minimum_installed_sequence": 42,
                "maximum_installed_sequence": 42,
                "minimum_free_bytes": 0,
                "backup": {"required": True, "max_age_hours": 24, "require_restore_verification": True},
                "recovery_authorization": {"required": self.recovery_required, "max_age_hours": 168},
            },
            "database": {
                "migration": self.migration,
                "reversible": self.reversible,
                "requires_verified_backup": True,
                "target_schema_version": "schema-" + self.version,
                "minimum_source_schema_version": self.previous_version,
            },
            "image": {
                "tag": engine.IMAGE_TAG,
                "archive": "toefl-house-erp-app.tar",
                "sha256": self.identity["sha256"],
                "size_bytes": self.identity["size_bytes"],
                "config_digest": self.identity["config_digest"],
                "labels": self.identity["labels"],
            },
            "updater": {"engine_schema": 1, "strings_schema": 1},
            "signature": {"key_id": "release-2026a", "algorithm": "rsa-pkcs1v15-sha256"},
        }
        manifest.update(overrides)
        return manifest

    def write_signed_manifest(self, manifest: dict, prefix: str, *, key: RsaKey | None = None,
                              key_id: str = "release-2026a") -> tuple[str, str]:
        target = self.staging if prefix == "update" else self.evidence
        manifest_path = target / ("update-manifest.json" if prefix == "update" else "recovery-request.json")
        raw = engine.canonical_manifest_bytes(manifest)
        manifest_path.write_bytes(raw)
        signature = (key or self.signing).sign(raw)
        envelope = signature_envelope(engine.DOCUMENT_UPDATE_SIGNATURE
                                      if prefix == "update" else "unused-not-used", key_id, signature)
        signature_path = manifest_path.with_name(manifest_path.name + ".sig")
        signature_path.write_text(json.dumps(envelope), encoding="utf-8")
        archive = self.staging / "toefl-house-erp-app.tar"
        if not archive.exists():
            shutil.copyfile(self.archive, archive)
        (self.staging / "toefl-house-erp-app.tar.sha256").write_text(
            self.identity["sha256"] + "  toefl-house-erp-app.tar\n", encoding="utf-8")
        return (str(manifest_path.relative_to(self.product_root)),
                str(signature_path.relative_to(self.product_root)))

    # -- evidence --------------------------------------------------------
    def write_backup_receipt(self, *, created: datetime | None = None, backup_set: str = "20261024_083000-set",
                             mutate: dict | None = None) -> None:
        created = created or (NOW - timedelta(hours=3))
        backup_set = backup_set
        artifacts = []
        for role, suffix in (
            ("database", "-database-enc.sql.gz"),
            ("public_files", "-files-enc.tar"),
            ("private_files", "-private-files-enc.tar"),
            ("recovery_config", "-site-config.gpg"),
        ):
            name = backup_set + suffix
            payload = (role + " encrypted synthetic backup\n").encode()
            (self.backup_dir / name).write_bytes(payload)
            artifacts.append({"role": role, "name": name, "bytes": len(payload),
                              "sha256": hashlib.sha256(payload).hexdigest()})
        receipt = {
            "schema_version": 1,
            "source_site": engine.SITE_NAME,
            "encrypted": True,
            "verified": True,
            "automation_ready": True,
            "source_drive": "C:",
            "backup_drive": "E:",
            "created_utc": iso(created),
            "backup_set": backup_set,
            "manifest_sha256": "b" * 64,
            "policy_hash": "c" * 64,
            "recovery_key_sha256": "d" * 64,
            "schedule_time": "02:00",
            "retention_versions": 3,
            "retention_behavior": "Delete valid older sets beyond keep count",
            "task_name": "TOEFL House ERP Backup",
            "artifacts": artifacts,
        }
        if mutate:
            receipt.update(mutate)
        self.receipt_rel = "data/update/evidence/backup-receipt.json"
        payload = json.dumps(receipt, indent=2).encode()
        (self.product_root / self.receipt_rel).write_bytes(payload)
        self.receipt_sha256 = hashlib.sha256(payload).hexdigest()

    def write_recovery_authorization(self, *, issued: datetime | None = None,
                                     expires: datetime | None = None, mutate: dict | None = None,
                                     key: RsaKey | None = None, key_id: str = "support-2026a") -> None:
        issued = issued or (NOW - timedelta(hours=1))
        expires = expires or (NOW + timedelta(days=2))
        document = {
            "schema_version": 1,
            "document_type": engine.DOCUMENT_RECOVERY,
            "site": engine.SITE_NAME,
            "scope": "site-update",
            "issued_utc": iso(issued),
            "expires_utc": iso(expires),
            "owner_key_custody_verified": True,
            "rehearsal_restore_verified": True,
            "backup_receipt_sha256": self.receipt_sha256,
            "authorized_by": "owner",
            "attested_by": "toefl-house-support",
        }
        if mutate:
            document.update(mutate)
        raw = json.dumps(document, indent=2, sort_keys=True).encode()
        self.authorization_rel = "data/update/evidence/recovery-authorization.json"
        (self.product_root / self.authorization_rel).write_bytes(raw)
        signature = (key or self.support).sign(raw)
        envelope = signature_envelope(engine.DOCUMENT_RECOVERY_SIGNATURE, key_id, signature)
        self.authorization_signature_rel = "data/update/evidence/recovery-authorization.json.sig"
        (self.product_root / self.authorization_signature_rel).write_text(
            json.dumps(envelope), encoding="utf-8")

    # -- requests --------------------------------------------------------
    def installed(self, **overrides) -> dict:
        installed = {
            "version": self.previous_version,
            "release_sequence": self.previous_sequence,
            "source_revision": "9" * 40,
            "image_labels": {
                "org.toefl-house.source-eol": "lf-v1",
                KDF: "9" * 40,
                VERSION_LABEL: self.previous_version,
            },
            "image_id": "sha256:" + "9" * 64,
        }
        installed.update(overrides)
        return installed

    def host(self, **overrides) -> dict:
        facts = {
            "disk_free_bytes": 60 * 1024 ** 3,
            "volume_present": True,
            "volume_verified": True,
            "services": {"db": True, "redis_cache": True, "redis_queue": True, "web": True},
            "image_present": True,
            "image_id": "sha256:" + "9" * 64,
            "image_labels": {
                "org.toefl-house.source-eol": "lf-v1",
                KDF: "9" * 40,
                VERSION_LABEL: self.previous_version,
            },
            "site_credentials_present": True,
            "site_config_present": True,
        }
        facts.update(overrides)
        return facts

    def preflight_request(self, **overrides) -> dict:
        request = {
            "action": "preflight",
            "now_utc": iso(NOW),
            "site": engine.SITE_NAME,
            "product_root": str(self.product_root),
            "host_updater_version": "2026.10.24",
            "trust_store": self.trust_store_rel,
            "channel": self.channel_rel,
            "manifest": self.manifest_rel,
            "signature": self.signature_rel,
            "archive": str((self.staging / "toefl-house-erp-app.tar").relative_to(self.product_root)),
            "backup_receipt": getattr(self, "receipt_rel", ""),
            "recovery_authorization": getattr(self, "authorization_rel", ""),
            "recovery_signature": getattr(self, "authorization_signature_rel", ""),
            "installed": self.installed(),
            "journal_state": "idle",
            "host": self.host(),
        }
        request.update(overrides)
        return request

    def preflight(self, **overrides) -> dict:
        return engine.preflight(self.preflight_request(**overrides), now=NOW)


def codes(response: dict) -> set[str]:
    return {item["code"] for item in response.get("blockers", [])}


class UpdateEngineBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="update-engine-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def fixture(self, **overrides) -> UpdateFixture:
        return UpdateFixture(self.tmp / "fixture", **overrides)


class TrustStoreTests(UpdateEngineBase):
    def test_unprovisioned_trust_store_refuses_every_update(self):
        fixture = self.fixture()
        fixture.write_trust_store(provisioned=False, keys=[])
        response = fixture.preflight()
        self.assertEqual(response["decision"], "refuse")
        self.assertIn("trust.not_provisioned", codes(response))

    def test_missing_trust_store_is_reported_as_not_provisioned(self):
        fixture = self.fixture()
        (fixture.product_root / fixture.trust_store_rel).unlink()
        response = fixture.preflight()
        self.assertIn("trust.not_provisioned", codes(response))

    def test_trust_store_rejects_unknown_fields_and_duplicate_keys(self):
        fixture = self.fixture()
        store_path = fixture.product_root / fixture.trust_store_rel
        store = json.loads(store_path.read_text())
        store["extra"] = "smuggled"
        store_path.write_text(json.dumps(store))
        self.assertIn("trust.invalid", codes(fixture.preflight()))

        fixture.write_trust_store()
        store = json.loads(store_path.read_text())
        store["keys"].append(store["keys"][0])
        store_path.write_text(json.dumps(store))
        self.assertIn("trust.invalid", codes(fixture.preflight()))

    def test_weak_or_non_rsa_keys_are_rejected(self):
        fixture = self.fixture()
        entry = fixture.signing.trust_entry("release-2026a", ("update-manifest",))
        entry["modulus_b64"] = base64.b64encode(b"\x01" * 128).decode()
        fixture.write_trust_store(keys=[entry])
        self.assertIn("trust.invalid", codes(fixture.preflight()))


class SignatureTests(UpdateEngineBase):
    def test_signed_release_verifies_and_binds_the_exact_manifest_bytes(self):
        fixture = self.fixture()
        manifest = engine.verify_manifest_signature(
            fixture.product_root / fixture.manifest_rel,
            fixture.product_root / fixture.signature_rel,
            engine.load_trust_store(fixture.product_root / fixture.trust_store_rel, now=NOW),
            now=NOW)
        self.assertEqual(manifest["version"], fixture.version)
        self.assertEqual(manifest["raw_sha256"],
                         hashlib.sha256((fixture.product_root / fixture.manifest_rel).read_bytes()).hexdigest())

    def test_modified_manifest_after_signing_is_rejected(self):
        fixture = self.fixture()
        path = fixture.product_root / fixture.manifest_rel
        path.write_bytes(path.read_bytes().replace(b"2026.11.01", b"2026.11.02"))
        response = fixture.preflight()
        self.assertIn("release.signature.invalid", codes(response))

    def test_signature_from_an_untrusted_key_is_rejected(self):
        fixture = self.fixture()
        rogue = RsaKey(self.tmp, "rogue")
        raw = (fixture.product_root / fixture.manifest_rel).read_bytes()
        envelope = signature_envelope(engine.DOCUMENT_UPDATE_SIGNATURE, "release-2026a", rogue.sign(raw))
        (fixture.product_root / fixture.signature_rel).write_text(json.dumps(envelope))
        self.assertIn("release.signature.invalid", codes(fixture.preflight()))

    def test_expired_signing_key_is_rejected(self):
        fixture = self.fixture()
        fixture.write_trust_store(key_override={
            "not_before_utc": iso(NOW - timedelta(days=30)),
            "not_after_utc": iso(NOW - timedelta(days=1)),
        })
        self.assertIn("trust.key_expired", codes(fixture.preflight()))

    def test_signature_key_id_mismatch_is_rejected(self):
        fixture = self.fixture()
        envelope_path = fixture.product_root / fixture.signature_rel
        envelope = json.loads(envelope_path.read_text())
        envelope["key_id"] = "support-2026a"
        envelope_path.write_text(json.dumps(envelope))
        self.assertIn("release.signature.invalid", codes(fixture.preflight()))

    def test_unknown_manifest_fields_are_refused(self):
        fixture = self.fixture()
        fixture.manifest = fixture.build_manifest(surprise="value")
        fixture.manifest_rel, fixture.signature_rel = fixture.write_signed_manifest(fixture.manifest, "update")
        self.assertIn("release.manifest.invalid", codes(fixture.preflight()))

    def test_manifest_dated_in_the_future_is_refused(self):
        fixture = self.fixture()
        fixture.manifest = fixture.build_manifest(issued_utc=iso(NOW + timedelta(days=1)))
        fixture.manifest_rel, fixture.signature_rel = fixture.write_signed_manifest(fixture.manifest, "update")
        self.assertIn("release.manifest.invalid", codes(fixture.preflight()))


class ImageIdentityTests(UpdateEngineBase):
    def test_archive_hash_mismatch_is_refused(self):
        fixture = self.fixture()
        with open(fixture.staging / "toefl-house-erp-app.tar", "ab") as handle:
            handle.write(b"tampered")
        self.assertIn("release.archive.hash_mismatch", codes(fixture.preflight()))

    def test_archive_config_digest_mismatch_is_refused(self):
        fixture = self.fixture()
        identity = dict(fixture.identity)
        identity["config_digest"] = "sha256:" + "0" * 64
        fixture.manifest = fixture.build_manifest(image={**fixture.manifest["image"], **identity})
        fixture.manifest_rel, fixture.signature_rel = fixture.write_signed_manifest(fixture.manifest, "update")
        self.assertIn("release.archive.identity_mismatch", codes(fixture.preflight()))

    def test_archive_label_mismatch_is_refused(self):
        fixture = self.fixture()
        labels = dict(fixture.identity["labels"])
        labels[VERSION_LABEL] = "2026.12.01"
        fixture.manifest = fixture.build_manifest(image={**fixture.manifest["image"], "labels": labels})
        fixture.manifest_rel, fixture.signature_rel = fixture.write_signed_manifest(fixture.manifest, "update")
        self.assertIn("release.image.labels_mismatch", codes(fixture.preflight()))

    def test_extra_image_tag_is_refused(self):
        fixture = self.fixture()
        archive_path = fixture.staging / "toefl-house-erp-app.tar"
        with tarfile.open(archive_path, "r") as source:
            members = {member.name: source.extractfile(member).read() for member in source.getmembers()}
        entry = json.loads(members["manifest.json"])
        entry[0]["RepoTags"] = [engine.IMAGE_TAG, "unrelated:latest"]
        members["manifest.json"] = json.dumps(entry).encode()
        with tarfile.open(archive_path, "w") as target:
            for name, data in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                target.addfile(info, io.BytesIO(data))
        identity = dict(fixture.identity)
        identity["sha256"] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        identity["size_bytes"] = archive_path.stat().st_size
        fixture.manifest = fixture.build_manifest(image={**fixture.manifest["image"], **identity})
        fixture.manifest_rel, fixture.signature_rel = fixture.write_signed_manifest(fixture.manifest, "update")
        self.assertIn("release.archive.identity_mismatch", codes(fixture.preflight()))

    def test_layer_verification_detects_changed_layer(self):
        fixture = self.fixture()
        archive_path = fixture.staging / "toefl-house-erp-app.tar"
        with tarfile.open(archive_path, "r") as source:
            members = {member.name: source.extractfile(member).read() for member in source.getmembers()}
        members["layer/layer.tar"] = members["layer/layer.tar"] + b"changed"
        with tarfile.open(archive_path, "w") as target:
            for name, data in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                target.addfile(info, io.BytesIO(data))
        with self.assertRaises(engine.UpdateError) as caught:
            engine.inspect_image_archive(archive_path, verify_layers=True)
        self.assertEqual(caught.exception.code, "release.archive.identity_mismatch")


class ChannelTests(UpdateEngineBase):
    def test_insecure_or_unlisted_update_urls_are_refused(self):
        for url in ("http://api.github.com/repos/x/y", "https://user:pw@api.github.com/repos/x/y",
                    "https://example.net/repos/x/y", "https://api.github.com:8443/repos/x/y"):
            with self.subTest(url=url):
                channels = {"schema_version": 1, "document_type": engine.DOCUMENT_CHANNEL,
                            "product": engine.PRODUCT, "default_channel": "official",
                            "channels": [{"id": "official", "provider": "x", "metadata_url": url,
                                          "allowed_hosts": ["api.github.com"],
                                          "required_assets": ["update-manifest.json"], "enabled": True}]}
                path = self.tmp / "channels.json"
                path.write_text(json.dumps(channels))
                with self.assertRaises(engine.UpdateError) as caught:
                    engine.load_channel_config(path, channel_id=None)
                self.assertEqual(caught.exception.code, "channel.invalid")

    def test_disabled_channel_is_refused(self):
        fixture = self.fixture()
        fixture.write_channel(enabled=False)
        self.assertIn("channel.disabled", codes(fixture.preflight()))

    def test_release_signed_for_another_channel_is_refused(self):
        fixture = self.fixture()
        fixture.manifest = fixture.build_manifest(channel="partner")
        fixture.manifest_rel, fixture.signature_rel = fixture.write_signed_manifest(fixture.manifest, "update")
        self.assertIn("policy.release_not_authorized", codes(fixture.preflight()))


class CompatibilityTests(unittest.TestCase):
    def test_version_ordering_is_numeric_and_suffix_aware(self):
        key = engine.version_key
        self.assertLess(key("2026.10.01"), key("2026.10.24"))
        self.assertLess(key("2026.9.30"), key("2026.10.1"))
        self.assertLess(key("2026.10.24"), key("2026.10.24-1"))
        self.assertLess(key("2026.10.24"), key("2026.10.25"))
        for invalid in ("", "..", "2026..1", "2026.10.24-" , "bad version"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(engine.UpdateError):
                    key(invalid)

    def test_release_sequence_is_derived_from_a_numeric_version(self):
        # Same table is asserted by the Windows updater smoke test in CI, so a
        # drift between the Python helper and the PowerShell mirror fails loudly.
        expected = {
            "2026.10.24": 2026102400,
            "2026.11.01": 2026110100,
            "2026.09.30": 2026093000,
            "2027.1.2": 2027010200,
            "2026.11": 2026110000,
            "2026.11.01.2": 2026110102,
            "2026": 2026000000,
        }
        for version, sequence in expected.items():
            with self.subTest(version=version):
                self.assertEqual(engine.release_sequence(version), sequence)
        for version in ("ci-windows-package", "2026.11.01-rc1", "v2026.11.01", "", "..",
                        "9999.1.1", "2026.100.1"):
            with self.subTest(version=version):
                with self.assertRaises(engine.UpdateError):
                    engine.release_sequence(version)

    def test_sequence_numbers_stay_inside_the_signed_integer_ceiling(self):
        self.assertEqual(engine.MAX_SEQUENCE, 2_147_483_647)
        self.assertEqual(engine.release_sequence("2147.0.0"), 2_147_000_000)
        with self.assertRaises(engine.UpdateError):
            engine.release_sequence("2147.99.99.99")


class PreflightTests(UpdateEngineBase):
    def test_complete_installation_is_the_only_allow_path(self):
        fixture = self.fixture()
        response = fixture.preflight()
        self.assertEqual(response["decision"], "allow", response["blockers"])
        self.assertEqual(response["target"]["version"], fixture.version)
        self.assertEqual(response["plan"]["phases"], list(engine.PLAN_PHASES))
        self.assertEqual(response["plan"]["rollback"], "recovery-required")
        self.assertIn("warning.not_rollback_safe", {item["code"] for item in response["warnings"]})
        self.assertEqual(response["current"]["version"], fixture.previous_version)

    def test_unsigned_test_package_is_refused_for_a_real_installation(self):
        fixture = self.fixture(release_status="TEST PACKAGE - NO REAL DATA", authorization="REJECT")
        self.assertIn("policy.release_not_authorized", codes(fixture.preflight()))
        self.assertIn("policy.release_not_production", codes(fixture.preflight()))

    def test_older_or_unlisted_release_is_refused(self):
        fixture = self.fixture(version="2026.09.01", sequence=41)
        response = fixture.preflight()
        self.assertIn("compat.downgrade", codes(response))

    def test_sequence_gap_and_unknown_installed_state_are_refused(self):
        fixture = self.fixture()
        response = fixture.preflight(installed=fixture.installed(release_sequence=41))
        self.assertIn("compat.sequence_gap", codes(response))
        response = fixture.preflight(installed=fixture.installed(release_sequence=None))
        self.assertIn("compat.downgrade", codes(response))
        response = fixture.preflight(installed={**fixture.installed(), "version": "not a version"})
        self.assertIn("compat.installed_version_unknown", codes(response))

    def test_host_updater_too_old_is_refused(self):
        fixture = self.fixture()
        self.assertIn("compat.host_updater_too_old",
                      codes(fixture.preflight(host_updater_version="2026.09.01")))

    def test_missing_database_volume_is_refused(self):
        fixture = self.fixture()
        self.assertIn("preflight.volume.missing",
                      codes(fixture.preflight(host=fixture.host(volume_present=False))))
        self.assertIn("preflight.volume.unverified",
                      codes(fixture.preflight(host=fixture.host(volume_verified=False))))

    def test_insufficient_disk_space_is_refused(self):
        fixture = self.fixture()
        self.assertIn("preflight.disk.insufficient",
                      codes(fixture.preflight(host=fixture.host(disk_free_bytes=1024))))

    def test_unhealthy_services_are_refused(self):
        fixture = self.fixture()
        services = {"db": True, "redis_cache": True, "redis_queue": False, "web": None}
        self.assertIn("preflight.services.unhealthy", codes(fixture.preflight(host=fixture.host(services=services))))

    def test_missing_site_files_are_refused_even_if_host_facts_lie(self):
        fixture = self.fixture()
        (fixture.data / "secrets" / "db.env").unlink()
        self.assertIn("preflight.site.credentials_missing", codes(fixture.preflight()))

    def test_image_identity_drift_is_refused(self):
        fixture = self.fixture()
        labels = dict(fixture.host()["image_labels"])
        labels[VERSION_LABEL] = "2026.09.01"
        self.assertIn("preflight.image.identity_mismatch",
                      codes(fixture.preflight(host=fixture.host(image_labels=labels))))

    def test_unfinished_update_transaction_is_refused(self):
        fixture = self.fixture()
        for state in ("applying", "migrating", "recovery-required"):
            with self.subTest(state=state):
                self.assertIn("preflight.update_in_progress",
                              codes(fixture.preflight(journal_state=state)))

    def test_preflight_never_modifies_site_or_evidence_files(self):
        fixture = self.fixture()
        roots = [fixture.site, fixture.evidence, fixture.data / "secrets"]
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                  for root in roots for path in root.rglob("*") if path.is_file()}
        fixture.preflight()
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                 for root in roots for path in root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)


class BackupEvidenceTests(UpdateEngineBase):
    def test_missing_receipt_refuses_the_update(self):
        fixture = self.fixture()
        self.assertIn("preflight.backup.receipt_missing", codes(fixture.preflight(backup_receipt="")))

    def test_stale_backup_refuses_the_update(self):
        fixture = self.fixture()
        fixture.write_backup_receipt(created=NOW - timedelta(hours=30))
        fixture.write_recovery_authorization()
        self.assertIn("preflight.backup.stale", codes(fixture.preflight()))

    def test_receipt_for_another_site_is_refused(self):
        fixture = self.fixture()
        fixture.write_backup_receipt(mutate={"source_site": "other.localhost"})
        self.assertIn("preflight.backup.receipt_invalid", codes(fixture.preflight()))

    def test_unverified_or_unencrypted_receipt_is_refused(self):
        for field in ("encrypted", "verified", "automation_ready"):
            with self.subTest(field=field):
                base = tempfile.mkdtemp(prefix="receipt-", dir=self.tmp)
                fixture = UpdateFixture(Path(base))
                fixture.write_backup_receipt(mutate={field: False})
                self.assertIn("preflight.backup.receipt_invalid", codes(fixture.preflight()))

    def test_changed_backup_artifact_is_refused(self):
        fixture = self.fixture()
        artifact = next(fixture.backup_dir.glob("*-database-enc.sql.gz"))
        artifact.write_bytes(artifact.read_bytes() + b"changed")
        self.assertIn("preflight.backup.artifact_invalid", codes(fixture.preflight()))

    def test_backup_on_the_same_drive_is_refused(self):
        fixture = self.fixture()
        fixture.write_backup_receipt(mutate={"backup_drive": "C:"})
        self.assertIn("preflight.backup.receipt_invalid", codes(fixture.preflight()))

    def test_backup_age_near_the_limit_is_only_a_warning(self):
        fixture = self.fixture()
        fixture.write_backup_receipt(created=NOW - timedelta(hours=19))
        fixture.write_recovery_authorization()
        response = fixture.preflight()
        self.assertEqual(response["decision"], "allow", response["blockers"])
        self.assertIn("warning.backup_age_near_limit", {item["code"] for item in response["warnings"]})


class RecoveryAuthorizationTests(UpdateEngineBase):
    def test_missing_owner_authorization_refuses_the_update(self):
        fixture = self.fixture()
        self.assertIn("preflight.recovery.authorization_missing",
                      codes(fixture.preflight(recovery_authorization="", recovery_signature="")))

    def test_forged_authorization_signature_is_refused(self):
        fixture = self.fixture()
        rogue = RsaKey(self.tmp, "rogue-support")
        fixture.write_recovery_authorization(key=rogue, key_id="support-2026a")
        self.assertIn("preflight.recovery.authorization_invalid", codes(fixture.preflight()))

    def test_expired_authorization_is_refused(self):
        fixture = self.fixture()
        fixture.write_recovery_authorization(issued=NOW - timedelta(days=9),
                                             expires=NOW - timedelta(days=1))
        self.assertIn("preflight.recovery.authorization_expired", codes(fixture.preflight()))

    def test_authorization_bound_to_another_backup_is_refused(self):
        fixture = self.fixture()
        fixture.write_recovery_authorization(mutate={"backup_receipt_sha256": "f" * 64})
        self.assertIn("preflight.recovery.binding_mismatch", codes(fixture.preflight()))

    def test_unverified_key_custody_or_rehearsal_is_refused(self):
        for field, expected in (("owner_key_custody_verified", "preflight.recovery.key_custody_unverified"),
                                ("rehearsal_restore_verified", "preflight.recovery.rehearsal_unverified")):
            with self.subTest(field=field):
                base = Path(tempfile.mkdtemp(prefix="auth-", dir=self.tmp))
                fixture = UpdateFixture(base)
                fixture.write_recovery_authorization(mutate={field: False})
                self.assertIn(expected, codes(fixture.preflight()))

    def test_authorization_signature_by_wrong_purpose_key_is_refused(self):
        fixture = self.fixture()
        # The release key is trusted for manifests, not for recovery authorization.
        fixture.write_recovery_authorization(key=fixture.signing, key_id="release-2026a")
        self.assertIn("trust.key_unknown", codes(fixture.preflight()))

    def test_authorization_is_optional_only_when_the_release_does_not_require_it(self):
        fixture = self.fixture(recovery_required=False)
        response = fixture.preflight(recovery_authorization="", recovery_signature="")
        self.assertEqual(response["decision"], "allow", response["blockers"])


FAKE_BENCH = r'''#!/usr/bin/env python3
import json, os, sys
state_path = os.environ["TH_TEST_BENCH_STATE"]
log_path = os.environ["TH_TEST_BENCH_LOG"]
state = json.loads(open(state_path, encoding="utf-8").read())
args = sys.argv[1:]
with open(log_path, "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\n")
if state.get("fail_migrate") and "migrate" in args:
    sys.stderr.write("synthetic migration failure\n")
    raise SystemExit(1)
if "migrate" in args:
    state["migrate_calls"] = state.get("migrate_calls", 0) + 1
    for doctype, delta in state.get("mutations", {}).items():
        state["counts"][doctype] = (state["counts"].get(doctype) or 0) + delta
    open(state_path, "w", encoding="utf-8").write(json.dumps(state))
    print("migration complete")
    raise SystemExit(0)
if "list-apps" in args:
    print(json.dumps(state.get("apps", [])))
    raise SystemExit(0)
if "frappe.db.count" in args:
    doctype = json.loads(args[args.index("--kwargs") + 1])["doctype"]
    value = state.get("counts", {}).get(doctype)
    if value is None:
        sys.stderr.write("DoesNotExistError\n")
        raise SystemExit(1)
    print(value)
    raise SystemExit(0)
if "frappe.client.get_list" in args:
    if state.get("fail_pages"):
        raise SystemExit(1)
    print(json.dumps([{"name": name} for name in state.get("pages", [])]))
    raise SystemExit(0)
sys.stderr.write("unexpected synthetic bench arguments\n")
raise SystemExit(1)
'''


class ApplyTests(UpdateEngineBase):
    def setUp(self):
        super().setUp()
        self.fixture = self.fixture()
        self.sites_dir = self.fixture.data / "sites"
        self.fixture.sites_dir = self.sites_dir
        self.bench = self.tmp / "fake-bench.py"
        self.bench.write_text(FAKE_BENCH, encoding="utf-8")
        self.bench.chmod(0o755)
        self.state = {
            "migrate_calls": 0,
            "counts": {"Student": 12, "Student Group": 3, "Course": 4, "Program": 2,
                       "Sales Invoice": 20, "Payment Entry": 18, "Attendance": 200,
                       "Salary Slip": 5, "Employee": 6, "User": 4, "Role": 9},
            "apps": list(engine.REQUIRED_APPS),
            "pages": list(engine.ROLE_DESK_PAGES),
            "mutations": {},
        }
        self.state_path = self.tmp / "bench-state.json"
        self.log_path = self.tmp / "bench-log.jsonl"
        self.write_state()
        self.addCleanup(lambda: os.environ.pop("TH_TEST_BENCH_STATE", None))
        self.addCleanup(lambda: os.environ.pop("TH_TEST_BENCH_LOG", None))
        os.environ["TH_TEST_BENCH_STATE"] = str(self.state_path)
        os.environ["TH_TEST_BENCH_LOG"] = str(self.log_path)

    def write_state(self):
        self.state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def read_state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def calls(self) -> list[list[str]]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text().splitlines() if line.strip()]

    def apply_request(self, **overrides) -> dict:
        request = {
            "action": "apply",
            "site": engine.SITE_NAME,
            "product_root": str(self.fixture.product_root),
            "manifest": self.fixture.manifest_rel,
            "signature": self.fixture.signature_rel,
            "trust_store": self.fixture.trust_store_rel,
            "sites_dir": str(self.sites_dir),
            "bench": str(self.bench),
            "host_updater_version": "2026.10.24",
            "migrate_replays": 2,
            "command_timeout_seconds": 120,
        }
        request.update(overrides)
        return request

    def apply(self, **overrides) -> dict:
        return engine.apply_update(self.apply_request(**overrides), now=NOW)

    def test_supported_migration_runs_twice_and_preserves_all_records(self):
        report = self.apply()
        self.assertEqual(report["status"], "succeeded", report["blockers"])
        self.assertEqual(report["phase"], "verified")
        self.assertEqual(report["transaction_outcome"], "completed")
        self.assertEqual(self.read_state()["migrate_calls"], 2)
        migrate_calls = [call for call in self.calls() if "migrate" in call]
        self.assertEqual(len(migrate_calls), 2)
        self.assertEqual(report["counts_before"]["Student"], 12)
        self.assertEqual(report["counts_after"]["Student"], 12)
        self.assertEqual(report["apps_after"], sorted(engine.REQUIRED_APPS))
        self.assertEqual(report["role_desk_pages"], sorted(engine.ROLE_DESK_PAGES))

    def test_record_loss_stops_the_update_and_requires_recovery(self):
        self.state["mutations"] = {"Student": -1}
        self.write_state()
        report = self.apply()
        self.assertEqual(report["status"], "failed")
        self.assertIn("apply.records_lost", {item["code"] for item in report["blockers"]})
        self.assertEqual(report["transaction_outcome"], "recovery-required")

    def test_failed_migration_is_reported_as_recovery_required(self):
        self.state["fail_migrate"] = True
        self.write_state()
        report = self.apply()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["phase"], "migrating")
        self.assertIn("apply.migrate_failed", {item["code"] for item in report["blockers"]})
        self.assertEqual(report["transaction_outcome"], "recovery-required")

    def test_missing_application_or_role_desk_fails_the_update(self):
        self.state["apps"] = [app for app in engine.REQUIRED_APPS if app != "toefl_house"]
        self.write_state()
        report = self.apply()
        self.assertIn("apply.apps_missing", {item["code"] for item in report["blockers"]})

        self.state["apps"] = list(engine.REQUIRED_APPS)
        self.state["pages"] = list(engine.ROLE_DESK_PAGES[:-1])
        self.write_state()
        report = self.apply()
        self.assertIn("apply.role_desk_missing", {item["code"] for item in report["blockers"]})

    def test_no_migration_mode_still_verifies_data(self):
        fixture = self.fixture
        fixture.manifest = fixture.build_manifest(database={
            **fixture.manifest["database"], "migration": "none", "reversible": True})
        fixture.manifest_rel, fixture.signature_rel = fixture.write_signed_manifest(fixture.manifest, "update")
        report = self.apply()
        self.assertEqual(report["status"], "succeeded", report["blockers"])
        self.assertEqual(self.read_state()["migrate_calls"], 0)

    def test_unauthorized_release_is_never_migrated(self):
        fixture = self.fixture
        fixture.manifest = fixture.build_manifest(release_status="TEST PACKAGE - NO REAL DATA",
                                                  production_authorization="REJECT")
        fixture.manifest_rel, fixture.signature_rel = fixture.write_signed_manifest(fixture.manifest, "update")
        report = self.apply()
        self.assertEqual(report["status"], "failed")
        self.assertIn("policy.release_not_authorized", {item["code"] for item in report["blockers"]})
        self.assertNotIn("migrate", [item for call in self.calls() for item in call])

    def test_tampered_manifest_is_never_migrated(self):
        path = self.fixture.product_root / self.fixture.manifest_rel
        path.write_bytes(path.read_bytes().replace(b"2026.11.01", b"2026.11.02"))
        report = self.apply()
        self.assertEqual(report["status"], "failed")
        self.assertIn("release.signature.invalid", {item["code"] for item in report["blockers"]})
        self.assertEqual(self.state["migrate_calls"], 0)


class ProtocolTests(UpdateEngineBase):
    def test_cli_uses_request_and_response_documents(self):
        fixture = self.fixture()
        request = fixture.preflight_request()
        request_path = self.tmp / "request.json"
        response_path = self.tmp / "response.json"
        request_path.write_text(json.dumps(request))
        completed = subprocess.run(
            [sys.executable, str(PRODUCT / "update_engine.py"),
             "--request", str(request_path), "--response", str(response_path)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(completed.stdout, "")
        response = json.loads(response_path.read_text())
        self.assertEqual(response["decision"], "allow", response["blockers"])
        self.assertEqual(response["document_type"], engine.DOCUMENT_RESPONSE)

    def test_cli_reads_request_path_from_environment(self):
        fixture = self.fixture()
        request_path = self.tmp / "request.json"
        response_path = self.tmp / "response.json"
        request_path.write_text(json.dumps(fixture.preflight_request()))
        completed = subprocess.run(
            [sys.executable, str(PRODUCT / "update_engine.py")],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "TH_UPDATE_REQUEST": str(request_path),
                 "TH_UPDATE_RESPONSE": str(response_path)})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(response_path.read_text())["decision"], "allow")

    def test_missing_request_is_a_safe_failure(self):
        completed = subprocess.run(
            [sys.executable, str(PRODUCT / "update_engine.py")],
            capture_output=True, text=True, timeout=120, env={**os.environ, "TH_UPDATE_REQUEST": ""})
        self.assertEqual(completed.returncode, 4)
        response = json.loads(completed.stdout)
        self.assertEqual(response["blockers"][0]["code"], "engine.request_invalid")

    def test_unknown_action_is_refused(self):
        # An unrecognised action is a malformed request (exit 4), never a
        # successful no-op and never an apply failure.
        response, status = engine.run({"action": "activate-production"})
        self.assertEqual(status, 4)
        self.assertEqual(response["blockers"][0]["code"], "engine.request_invalid")

    def test_engine_self_check_lists_the_catalog(self):
        completed = subprocess.run([sys.executable, str(PRODUCT / "update_engine.py"), "--self-check"],
                                   capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["message_codes"], len(engine.MESSAGE_CODES))

    def test_engine_never_echoes_unexpected_exception_text(self):
        with patch.object(engine, "preflight", side_effect=RuntimeError("secret-token-value")):
            response, status = engine.run({"action": "preflight"})
        self.assertEqual(status, 5)
        self.assertNotIn("secret-token-value", json.dumps(response))
        self.assertEqual(response["blockers"][0]["code"], "engine.unexpected")


class CatalogTests(unittest.TestCase):
    def test_every_engine_message_has_english_and_dari_text(self):
        catalog = json.loads((ROOT / "product/windows/updater-strings.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["schema_version"], 1)
        self.assertEqual(catalog["document_type"], "toefl-house-erp-updater-strings")
        messages = catalog["messages"]
        missing = sorted(engine.MESSAGE_CODES - set(messages))
        self.assertEqual(missing, [], f"missing bilingual updater messages: {missing}")
        for code, entry in messages.items():
            with self.subTest(code=code):
                self.assertEqual(set(entry), {"en", "fa"}, code)
                self.assertTrue(entry["en"].strip(), code)
                self.assertTrue(entry["fa"].strip(), code)
                self.assertNotIn("git ", entry["en"].lower(), code)

    def test_catalog_has_no_duplicate_or_unknown_codes(self):
        catalog = json.loads((ROOT / "product/windows/updater-strings.json").read_text(encoding="utf-8"))
        unknown = sorted(set(catalog["messages"]) - engine.MESSAGE_CODES)
        self.assertEqual(unknown, [], f"catalog defines unused codes: {unknown}")


if __name__ == "__main__":
    unittest.main()

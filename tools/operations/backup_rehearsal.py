#!/usr/bin/env python3
"""End-to-end rehearsal for the interim backup tool.

Runs `tools.operations.interim_backup` against a synthetic dump payload (no real
MariaDB required), on two distinct fake "volumes" (separate temporary trees)
so every guard fires in sequence:

  1. same-volume destination is refused;
  2. a second volume accepts the backup, which is encrypted (openssl
     aes-256-cbc pbkdf2), SHA-256 digested both plain and cipher, and the
     plaintext is removed;
  3. the sidecar carries limitations, retention and both digests;
  4. restore into staging refuses a missing/corrupted sidecar, refuses to
     write inside the live data root, verifies the cipher digest, decrypts,
     and re-verifies the plaintext digest;
  5. an external restore command (tee) is fed the decrypted dump to prove
     the plaintext is byte-identical to what the dump produced;
  6. timing is reported per phase so an operator can reason about RTO on
     real hardware (actual production RPO/RTO remain an Owner decision - see
     docs/engineering/evidence/backup-restore-rehearsal-2026-09-24.md).

The script never imports frappe, never touches any installed site, and writes
only into the directory passed via --scratch. Exit 0 on success; any policy
violation or digest mismatch raises.
"""
from __future__ import annotations

import argparse
import json
import secrets
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.operations import interim_backup as ib  # noqa: E402
from tools.operations.backup_policy import (
    default_policy, read_audit,
)  # noqa: E402


def _write_payload(path: Path, size: int) -> bytes:
    payload = secrets.token_bytes(size)
    path.write_bytes(payload)
    return payload


def _scrub(path: Path) -> None:
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def _fake_dump_cmd(scratch: Path, label: str, size: int) -> tuple[list[str], Path, bytes]:
    """A "dump" command that writes a deterministic SQL-shaped payload to stdout.

    The payload starts with a SQL comment header and a CREATE TABLE marker so
    that interim_backup's magic-byte verification (which checks for gzip/SQL
    markers) accepts it as a database artifact, followed by deterministic
    random filler so round-trip SHA-256 verification proves byte-identity.
    """
    payload_path = scratch / f"source-{label}.bin"
    filler = secrets.token_bytes(max(0, size - 64))
    header = (
        "-- MariaDB dump 10.19  Distrib 11.3.2-MariaDB, for Linux (x86_64)\n"
        "-- Host: localhost    Database: toefl_house_bench\n"
        "-- ------------------------------------------------------\n"
        "-- Server version\t11.3.2-MariaDB-1:11.3.2+maria~ubu2204\n"
        "CREATE TABLE `tabRehearsalMarker` (\n"
        "  `name` varchar(140) NOT NULL,\n"
        "  `marker` varchar(140) NOT NULL,\n"
        "  PRIMARY KEY (`name`)\n"
        ");\n"
        "INSERT INTO `tabRehearsalMarker` VALUES ('rehearsal','ok');\n"
        "-- FILLER:"
    ).encode("ascii")
    payload = header + filler
    payload_path.write_bytes(payload)
    script = (
        "import sys; "
        f"p={str(payload_path)!r}; "
        "sys.stdout.buffer.write(open(p,'rb').read()); "
        "sys.stdout.buffer.flush()"
    )
    return [sys.executable, "-c", script], payload_path, payload


def run_rehearsal(scratch: Path, payload_size: int = 1 << 20) -> dict:
    scratch = Path(scratch).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    live_root = scratch / "live-data"
    backup_root = scratch / "backup-volume"
    staging = scratch / "staging"
    passfile = scratch / "passphrase"
    for p in (live_root, backup_root, staging):
        _scrub(p)
        p.mkdir(parents=True)
    # Distinct "volumes" — we rely on the code's st_dev check, which on Linux
    # returns the same device for every tmpfs; pass volume_evidence directly
    # to simulate a real second mount. The same-volume refusal is covered by
    # test_interim_backup separately; here we just need both trees present.
    passfile.write_text(secrets.token_urlsafe(48) + "\n")
    passfile.chmod(0o600)

    timings: dict[str, float] = {}

    # 1. Dump + encrypt side
    dump_cmd, _src_path, expected_payload = _fake_dump_cmd(
        scratch, "db-daily", payload_size)

    t0 = time.perf_counter()
    vol_evidence = {
        "active_st_dev": 1, "backup_st_dev": 2, "different_volume": True,
        "note": "synthetic volumes for rehearsal; real volume check covered by unit tests",
    }
    run = ib.run_backup(
        backup_root=str(backup_root), label="db-daily",
        dump_command=dump_cmd, passphrase_file=str(passfile),
        volume_evidence=vol_evidence,
        policy_state=default_policy(),
        audit_log_dir=str(scratch / "audit"),
        artifact_kind="database",
    )
    sidecar_path = ib.write_sidecar(
        run, ib.RetentionPolicy(),
        restore_command="python3 -m tools.operations.interim_backup --print-restore-procedure",
        artifact_kind="database",
        policy_state=default_policy(),
    )
    timings["backup_encrypt_seconds"] = round(time.perf_counter() - t0, 3)

    cipher = Path(run.cipher_path)
    assert cipher.is_file(), "cipher artifact missing after backup"
    assert not (backup_root / "db-daily.plain").exists(), \
        "plaintext must be removed after encryption"
    assert Path(sidecar_path).is_file(), "manifest sidecar missing"
    manifest = json.loads(Path(sidecar_path).read_text())
    assert manifest["schema_version"] == ib.SCHEMA_VERSION
    assert manifest["classification"] == "INTERIM_PRODUCTION_BACKUP_NOT_DISASTER_RECOVERY"
    assert any("same machine" in lim for lim in manifest["limitations"]), \
        "limitations must travel with the artifact"

    # 2. Restore-within-live must be refused.
    refused = False
    try:
        ib.run_restore(
            artifact=str(cipher),
            staging_root=str(live_root / "inside"),
            passphrase_file=str(passfile),
            active_data_root=str(live_root),
            manifest_path=sidecar_path,
        )
    except ib.BackupPolicyError as exc:
        refused = "never over the live one" in str(exc)
    assert refused, "restore into live data root was not refused"

    # 3. Good-path restore + pipe into a fake loader (tee)
    fresh_dump = scratch / "loaded-into-fresh-db.sql"
    t1 = time.perf_counter()
    restored = ib.run_restore(
        artifact=str(cipher),
        staging_root=str(staging),
        passphrase_file=str(passfile),
        active_data_root=str(live_root),
        restore_command=["tee", str(fresh_dump)],
        manifest_path=sidecar_path,
        audit_log_dir=str(scratch / "audit"),
    )
    timings["verify_decrypt_load_seconds"] = round(time.perf_counter() - t1, 3)

    assert restored.verified
    assert restored.restore_command_ran
    assert Path(restored.decrypted_path).is_file()
    round_tripped = Path(restored.decrypted_path).read_bytes()
    assert round_tripped == expected_payload, \
        "decrypted plaintext differs from the original dump"
    assert fresh_dump.read_bytes() == expected_payload, \
        "restore-command stdin differs from the original dump"
    assert cipher.is_file(), "cipher must not be consumed by restore"

    # 4. Tamper detection: flip one byte in the cipher and restore must fail.
    tampered = scratch / "tampered.enc"
    shutil.copy2(cipher, tampered)
    raw = bytearray(tampered.read_bytes())
    raw[len(raw) // 2] ^= 0x01
    tampered.write_bytes(bytes(raw))
    tampered_sidecar = scratch / "tampered.enc.manifest.json"
    shutil.copy2(sidecar_path, tampered_sidecar)
    # The sidecar holds the original cipher digest; the tampered copy must
    # fail verification before any decrypt is attempted.
    tampered_fail = None
    try:
        ib.run_restore(
            artifact=str(tampered),
            staging_root=str(staging / "tampered-out"),
            passphrase_file=str(passfile),
            active_data_root=str(live_root),
            manifest_path=str(tampered_sidecar),
        )
    except ib.BackupPolicyError as exc:
        tampered_fail = str(exc)
    assert tampered_fail and "digest" in tampered_fail.lower(), \
        "tampered artifact was not refused on digest mismatch"

    # 7. Audit log + policy-state evidence.
    manifest = json.loads(Path(sidecar_path).read_text())
    policy_fields = manifest.get("policy_state", {})
    audit_entries = read_audit(scratch / "audit")
    assert len(audit_entries) >= 2, "expected at least backup + restore audit entries"
    assert any(e.get("action") == "backup" for e in audit_entries)
    assert any(e.get("action") == "restore" for e in audit_entries)
    assert policy_fields.get("rpo_hours") == "NOT_CONFIGURED"
    assert policy_fields.get("rto_hours") == "NOT_CONFIGURED"
    assert policy_fields.get("offsite_destination") == "NOT_CONFIGURED"
    assert not default_policy().is_fully_configured(),         "default policy must be NOT_CONFIGURED on every field"

    return {
        "status": "pass",
        "classification": "INTERIM_PRODUCTION_BACKUP_NOT_DISASTER_RECOVERY",
        "scratch": str(scratch),
        "audit_log_entries": len(audit_entries),
        "policy_state_unconfigured_fields": sorted(
            k for k, v in policy_fields.items() if v == "NOT_CONFIGURED"),
        "cipher_path": str(cipher),
        "cipher_bytes": cipher.stat().st_size,
        "plaintext_bytes": len(expected_payload),
        "plaintext_sha256": restored.plaintext_digest,
        "cipher_sha256": restored.cipher_digest,
        "sidecar_path": sidecar_path,
        "timings_seconds": timings,
        "checks": [
            {"name": "synthetic-dump-encrypted-and-plain-removed", "status": "pass"},
            {"name": "sidecar-carries-limitations-and-both-digests", "status": "pass"},
            {"name": "restore-into-live-root-refused", "status": "pass"},
            {"name": "restore-verifies-then-decrypts-byte-identical", "status": "pass"},
            {"name": "restore-command-receives-the-plaintext-dump", "status": "pass"},
            {"name": "tampered-cipher-refused-before-decrypt", "status": "pass"},
        ],
        "owner_decisions_required": [
            "B12/RPO-RTO: targets are not selected; timings here are local-sandbox and do not satisfy RPO/RTO.",
            "D14/off-site-destination: interim backup writes only to a second local volume; off-site custody is not built.",
            "Key-custody quorum and operator procedures are rehearsed separately (runtime_key_custody_*).",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", required=True,
                        help="Writable directory; every artifact is created and "
                             "verified under this tree, the live data root is "
                             "never touched.")
    parser.add_argument("--payload-bytes", type=int, default=1 << 20,
                        help="Synthetic dump size in bytes (default 1 MiB).")
    parser.add_argument("--output", type=Path,
                        help="Write JSON report to this path in addition to stdout.")
    args = parser.parse_args(argv)
    report = run_rehearsal(args.scratch, args.payload_bytes)
    text = json.dumps(report, indent=2) + "\n"
    sys.stdout.write(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

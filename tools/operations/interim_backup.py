# -*- coding: utf-8 -*-
"""Interim production backup for the local-server + Tailscale deployment.

Owner directive of 2026-09-19, section 2. This is an **interim production
backup**, not disaster recovery, and the code says so rather than leaving the
distinction to a reader's charity.

What it provides: an automated, encrypted, multi-version backup written to a
volume other than the one holding the live data, with predictable rotation and
per-artifact integrity verification.

What it explicitly does not provide: a second drive inside the same machine does
not protect against theft, fire, flood, total hardware loss, site loss, or
ransomware that reaches both mounted volumes. Those require the off-site
destination recorded as owner decision D14, which has not been built.

The pure decision logic (volume selection, rotation, integrity verdicts) is
separated from I/O so it can be tested without a database, and so the policy
cannot silently drift from the documented procedure.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = "1.0"

# Rotation: keep this many of each generation. Predictable and documented so an
# operator can state the worst-case recovery point without reading the code.
DEFAULT_RETENTION = {"daily": 14, "weekly": 8, "monthly": 12}

# What this backup does NOT protect against. Surfaced by the tool itself so the
# limitation travels with the artifact instead of living only in a document.
LIMITATIONS = (
    "A second drive inside the same machine does not protect against theft, "
    "fire, flood, total hardware loss, site loss, or ransomware that reaches "
    "both mounted volumes.",
    "Off-site custody is owner decision D14 (hardware the Owner controls at a "
    "separate physical location) and is NOT YET BUILT.",
    "Recovery objectives RPO 24 hours / RTO 8 hours (owner decision D13) are "
    "targets. They are not measured or demonstrated by this tool.",
)


class BackupPolicyError(RuntimeError):
    """The backup refuses to run rather than produce a misleading artifact."""


@dataclass(frozen=True)
class RetentionPolicy:
    daily: int = DEFAULT_RETENTION["daily"]
    weekly: int = DEFAULT_RETENTION["weekly"]
    monthly: int = DEFAULT_RETENTION["monthly"]

    def as_dict(self) -> dict[str, int]:
        return {"daily": self.daily, "weekly": self.weekly, "monthly": self.monthly}


def volume_id(path: str | os.PathLike[str]) -> int:
    """Identity of the filesystem holding ``path``.

    Walks up to the nearest existing ancestor so a destination that does not
    yet exist can still be refused before anything is written there.
    """
    target = pathlib.Path(path)
    while not target.exists():
        parent = target.parent
        if parent == target:
            raise BackupPolicyError(f"cannot determine volume for {path}")
        target = parent
    return os.stat(target).st_dev


def assert_different_volume(active_data_root: str, backup_root: str) -> dict[str, Any]:
    """Refuse to back up onto the volume that holds the live data.

    The whole point of section 2 is that the copy survives loss of the working
    volume. A backup on the same filesystem satisfies the letter of "a backup
    exists" while providing none of that protection, so it is rejected rather
    than warned about.
    """
    active = volume_id(active_data_root)
    backup = volume_id(backup_root)
    if active == backup:
        raise BackupPolicyError(
            "backup destination is on the same volume as the active data; "
            f"st_dev {active} matches {backup}. Mount a different volume.")
    return {"active_st_dev": active, "backup_st_dev": backup, "different_volume": True}


def classify_generation(name: str) -> str:
    """Bucket a backup name into the generation it counts against."""
    lowered = name.lower()
    if "monthly" in lowered:
        return "monthly"
    if "weekly" in lowered:
        return "weekly"
    return "daily"


def retention_plan(artifacts: list[str], policy: RetentionPolicy | None = None,
                   ) -> dict[str, Any]:
    """Decide what to keep and what to expire.

    Newest-first by name within each generation, which is deterministic and needs
    no clock, so the same directory always yields the same plan. Expiry is
    reported, never executed here: deletion stays an explicit operator action so
    a bad plan cannot destroy backups as a side effect.
    """
    policy = policy or RetentionPolicy()
    buckets: dict[str, list[str]] = {"daily": [], "weekly": [], "monthly": []}
    for artifact in artifacts:
        buckets[classify_generation(artifact)].append(artifact)

    keep: list[str] = []
    expire: list[str] = []
    for generation, names in buckets.items():
        limit = getattr(policy, generation)
        ordered = sorted(names, reverse=True)
        keep.extend(ordered[:limit])
        expire.extend(ordered[limit:])
    return {"retention": policy.as_dict(),
            "keep": sorted(keep),
            "expire": sorted(expire),
            "counts": {g: len(v) for g, v in buckets.items()}}


def digest_file(path: str | os.PathLike[str], chunk: int = 1 << 20) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            hasher.update(block)
    return hasher.hexdigest()


def verify_artifact(path: str | os.PathLike[str], expected_sha256: str) -> dict[str, Any]:
    """Integrity verdict for one stored backup."""
    target = pathlib.Path(path)
    if not target.is_file():
        return {"path": str(target), "verified": False, "reason": "missing"}
    observed = digest_file(target)
    return {"path": str(target), "verified": observed == expected_sha256,
            "expected_sha256": expected_sha256, "observed_sha256": observed}


def backup_manifest(*, artifacts: list[dict[str, Any]], retention: RetentionPolicy,
                    volume_evidence: dict[str, Any], restore_command: str,
                    ) -> dict[str, Any]:
    """The record that travels with a backup run."""
    return {"schema_version": SCHEMA_VERSION,
            "artifacts": artifacts,
            "retention": retention.as_dict(),
            "volume_evidence": volume_evidence,
            "restore_command": restore_command,
            "limitations": list(LIMITATIONS),
            "classification": "INTERIM_PRODUCTION_BACKUP_NOT_DISASTER_RECOVERY"}


def restore_procedure() -> list[str]:
    """Documented restore steps, kept in code so docs cannot drift from them."""
    return [
        "Stop the application so nothing writes during the restore.",
        "Verify the artifact first: compare its sha256 against the manifest. "
        "Do not restore an artifact that fails verification.",
        "Restore the database dump into a fresh database, never over the live one.",
        "Restore the files archive into a staging directory and inspect it.",
        "Point the site at the restored database and files, then start the app.",
        "Log in as a real role and confirm a known record is present and correct.",
        "Record the rehearsal: date, artifact digest, elapsed time, and outcome.",
    ]


DEFAULT_ENCRYPT = ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
                   "-salt", "-in", "{plain}", "-out", "{cipher}",
                   "-pass", "file:{passphrase_file}"]

DEFAULT_DECRYPT = ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
                   "-in", "{cipher}", "-out", "{plain}",
                   "-pass", "file:{passphrase_file}"]


@dataclass(frozen=True)
class BackupRun:
    """One executed backup. Carries its own digest and its own limitations."""
    generation: str
    plaintext_digest: str
    cipher_digest: str
    cipher_path: str
    encrypted: bool
    command: list[str]
    volume_evidence: dict[str, Any]


def run_backup(*, backup_root: str, label: str, dump_command: list[str],
               encrypt_command: list[str] | None = None,
               passphrase_file: str | None = None,
               volume_evidence: dict[str, Any] | None = None,
               active_data_root: str | None = None,
               ) -> BackupRun:
    """Execute one backup: dump, encrypt, digest.

    ``volume_evidence`` is injectable so the policy can be tested without two
    real mounts; when omitted it is computed from ``active_data_root`` versus
    ``backup_root``, and a same-volume destination raises before anything is
    written. Encryption is applied when a passphrase file is supplied. The
    plaintext is removed once the cipher is verified, so an unencrypted copy
    of the database is not left sitting on disk. A failed dump or encrypt
    attempt removes its own leftovers rather than leaving a partial artifact.
    """
    import shutil
    import subprocess

    if volume_evidence is None:
        if not active_data_root:
            raise BackupPolicyError(
                "active_data_root is required when volume_evidence is not injected")
        volume_evidence = assert_different_volume(active_data_root, backup_root)
    destination = pathlib.Path(backup_root)
    destination.mkdir(parents=True, exist_ok=True)

    plain = destination / f"{label}.plain"
    cipher = destination / f"{label}.enc"
    try:
        with open(plain, "wb") as sink:
            subprocess.run(dump_command, stdout=sink, stderr=subprocess.PIPE, check=True)
        plain_digest = digest_file(plain)

        if passphrase_file:
            template = encrypt_command or DEFAULT_ENCRYPT
            argv = [part.format(plain=str(plain), cipher=str(cipher),
                                passphrase_file=passphrase_file) for part in template]
            subprocess.run(argv, check=True, capture_output=True)
            cipher_digest = digest_file(cipher)
            plain.unlink()
            return BackupRun(label, plain_digest, cipher_digest, str(cipher), True,
                             argv, dict(volume_evidence))

        kept = destination / f"{label}.plain.keep"
        shutil.move(str(plain), str(kept))
        return BackupRun(label, plain_digest, digest_file(kept), str(kept), False,
                         list(dump_command), dict(volume_evidence))
    except Exception:
        for leftover in (plain, cipher):
            if leftover.exists():
                leftover.unlink()
        raise


def write_sidecar(run: BackupRun, retention: RetentionPolicy,
                  restore_command: str,
                  volume_evidence: dict[str, Any] | None = None) -> str:
    """Write the manifest next to the artifact and return its path."""
    import json as _json
    evidence = volume_evidence if volume_evidence is not None else run.volume_evidence
    manifest = backup_manifest(
        artifacts=[{"generation": run.generation, "path": run.cipher_path,
                    "sha256": run.cipher_digest, "encrypted": run.encrypted,
                    "plaintext_sha256": run.plaintext_digest}],
        retention=retention, volume_evidence=evidence,
        restore_command=restore_command)
    sidecar = pathlib.Path(run.cipher_path + ".manifest.json")
    sidecar.write_text(_json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return str(sidecar)


@dataclass(frozen=True)
class RestoreRun:
    """One executed restore into staging. Never a live-site rehearsal record."""

    artifact: str
    decrypted_path: str
    cipher_digest: str
    plaintext_digest: str
    verified: bool
    restore_command_ran: bool
    classification: str
    rehearsal_on_real_server: bool


def _is_within(path: str, root: str) -> bool:
    """True when ``path`` is ``root`` or a file/directory inside it."""
    target = pathlib.Path(path).resolve()
    base = pathlib.Path(root).resolve()
    if target == base:
        return True
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def expected_digest_from_sidecar(artifact: str, manifest_path: str | None = None,
                                 ) -> tuple[str, str | None, bool]:
    """Cipher digest, plaintext digest if recorded, and whether the artifact is encrypted.

    A missing sidecar is a refusal, not a skip: decrypting an unverified
    artifact is how a corrupted backup becomes a corrupted database.
    """
    import json as _json
    sidecar = pathlib.Path(manifest_path) if manifest_path else pathlib.Path(
        str(artifact) + ".manifest.json")
    if not sidecar.is_file():
        raise BackupPolicyError(
            "restore refused: sidecar manifest is missing; "
            "will not decrypt an unverified artifact")
    try:
        payload = _json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BackupPolicyError(
            "restore refused: sidecar manifest is unreadable") from exc
    artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
    if not isinstance(artifacts, list) or not artifacts or not isinstance(artifacts[0], dict):
        raise BackupPolicyError("restore refused: sidecar lists no artifacts")
    sha = artifacts[0].get("sha256")
    if not isinstance(sha, str) or not sha:
        raise BackupPolicyError("restore refused: sidecar has no cipher digest")
    plain = artifacts[0].get("plaintext_sha256")
    encrypted = bool(artifacts[0].get("encrypted"))
    return sha, (plain if isinstance(plain, str) and plain else None), encrypted


def run_restore(*, artifact: str, staging_root: str,
                passphrase_file: str | None = None,
                active_data_root: str | None = None,
                restore_command: list[str] | None = None,
                decrypt_command: list[str] | None = None,
                manifest_path: str | None = None,
                ) -> RestoreRun:
    """Verify, then decrypt into staging. Never onto the live data root.

    The backup-restore gate stays BLOCKED until a rehearsal is recorded on
    the real server. This function is the mechanism for that rehearsal: it
    will not decrypt a digest mismatch, will not write into the live data
    directory, and always reports ``rehearsal_on_real_server=False``.
    """
    import subprocess

    cipher = pathlib.Path(artifact)
    if not cipher.is_file():
        raise BackupPolicyError(f"restore refused: artifact missing: {artifact}")
    expected, expected_plain, encrypted = expected_digest_from_sidecar(
        str(cipher), manifest_path)
    verdict = verify_artifact(cipher, expected)
    if not verdict["verified"]:
        raise BackupPolicyError(
            "restore refused: artifact digest does not match the sidecar; "
            "will not decrypt a corrupted or substituted backup")
    if encrypted and not passphrase_file:
        raise BackupPolicyError(
            "restore refused: artifact is encrypted and no passphrase file was given")

    if active_data_root and _is_within(staging_root, active_data_root):
        raise BackupPolicyError(
            "restore refused: staging directory is the live data root or inside it; "
            "restore into a fresh location, never over the live one")

    staging = pathlib.Path(staging_root)
    staging.mkdir(parents=True, exist_ok=True)
    decrypted = staging / (cipher.name + ".restored")
    if decrypted.resolve() == cipher.resolve():
        raise BackupPolicyError("restore refused: decrypted path would overwrite the cipher")

    try:
        if passphrase_file:
            template = decrypt_command or DEFAULT_DECRYPT
            argv = [part.format(plain=str(decrypted), cipher=str(cipher),
                                passphrase_file=passphrase_file) for part in template]
            subprocess.run(argv, check=True, capture_output=True)
        else:
            import shutil
            shutil.copy2(cipher, decrypted)
        plain_digest = digest_file(decrypted)
        if expected_plain and plain_digest != expected_plain:
            decrypted.unlink()
            raise BackupPolicyError(
                "restore refused: decrypted dump does not match the sidecar plaintext digest")
    except BackupPolicyError:
        raise
    except Exception:
        if decrypted.exists():
            decrypted.unlink()
        raise

    ran = False
    if restore_command:
        with open(decrypted, "rb") as source:
            subprocess.run(restore_command, stdin=source, check=True, capture_output=True)
        ran = True
    return RestoreRun(
        artifact=str(cipher), decrypted_path=str(decrypted),
        cipher_digest=expected, plaintext_digest=plain_digest,
        verified=True, restore_command_ran=ran,
        classification="INTERIM_PRODUCTION_BACKUP_NOT_DISASTER_RECOVERY",
        rehearsal_on_real_server=False,
    )


def main(argv: list[str] | None = None) -> int:
    """Operator entry: run one backup, or verify-and-decrypt a restore into staging.

    Example (on the real server, with a second volume mounted):

        python3 -m tools.operations.interim_backup \\
            --active-data-root /var/lib/mysql \\
            --backup-root /mnt/toefl-house-backup \\
            --label db-$(date +%Y-%m-%d)-daily \\
            --passphrase-file /etc/toefl-house/backup-passphrase \\
            --dump-command mysqldump --single-transaction --routines --triggers SITE_DB

    Staging restore (still not a real-server rehearsal):

        python3 -m tools.operations.interim_backup \\
            --restore --artifact PATH.enc --staging-root /var/tmp/toefl-restore \\
            --active-data-root /var/lib/mysql --passphrase-file /etc/toefl-house/backup-passphrase

    The operator checklist is printed by ``--print-restore-procedure``. The
    backup-restore gate stays BLOCKED until a rehearsal is recorded on the
    real server.
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-restore-procedure", action="store_true")
    parser.add_argument("--print-limitations", action="store_true")
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--artifact")
    parser.add_argument("--staging-root")
    parser.add_argument("--active-data-root")
    parser.add_argument("--backup-root")
    parser.add_argument("--label")
    parser.add_argument("--passphrase-file")
    parser.add_argument("--dump-command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    if args.print_restore_procedure:
        for i, step in enumerate(restore_procedure(), 1):
            print(f"{i}. {step}")
        return 0
    if args.print_limitations:
        for line in LIMITATIONS:
            print(line)
        return 0
    if args.restore:
        missing = [name for name in ("artifact", "staging_root", "active_data_root")
                   if not getattr(args, name)]
        if missing:
            parser.error("a restore requires --artifact, --staging-root and "
                         "--active-data-root")
        run = run_restore(artifact=args.artifact, staging_root=args.staging_root,
                          passphrase_file=args.passphrase_file,
                          active_data_root=args.active_data_root)
        print(run.decrypted_path)
        print("verified")
        print(run.classification)
        print("NOT A REAL-SERVER REHEARSAL")
        return 0
    missing = [name for name in ("active_data_root", "backup_root", "label")
               if not getattr(args, name)]
    if missing or not args.dump_command:
        parser.error("a run requires --active-data-root, --backup-root, "
                     "--label and --dump-command")
    dump = list(args.dump_command)
    if dump and dump[0] == "--":
        dump = dump[1:]
    run = run_backup(backup_root=args.backup_root, label=args.label,
                     dump_command=dump, passphrase_file=args.passphrase_file,
                     active_data_root=args.active_data_root)
    sidecar = write_sidecar(run, RetentionPolicy(),
                            restore_command="python3 -m tools.operations.interim_backup "
                            "--print-restore-procedure")
    print(run.cipher_path)
    print(sidecar)
    print("INTERIM_PRODUCTION_BACKUP_NOT_DISASTER_RECOVERY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

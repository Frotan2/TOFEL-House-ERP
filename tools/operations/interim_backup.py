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
    """Identity of the filesystem holding ``path``."""
    return os.stat(path).st_dev


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

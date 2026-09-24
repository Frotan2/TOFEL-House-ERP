#!/usr/bin/env python3
"""Structured configuration and audit logging for the interim backup tool.

The interim backup refuses to invent policy (RPO/RTO, off-site destination,
custodian identities, schedule). This module:

* exposes a `PolicyState` dataclass where every operational parameter defaults
  to NOT_CONFIGURED, with a `configured` flag the operator can set only by
  passing an explicit file or env value — never from ambient defaults;
* records a structured, append-only JSON-lines audit log for every
  backup/restore invocation (timestamp, action, artifact digests, operator
  euid, hostname, policy-state hash, and outcome);
* provides idempotency checks (re-running the same label refuses to
  overwrite an existing cipher unless `--force` is given; the check is
  based on the sidecar digest, not just file existence).

Nothing here touches vendor code or selects business policy.
"""
from __future__ import annotations

import datetime as dt
import getpass
import json
import os
import pathlib
import socket
from dataclasses import asdict, dataclass, field
from typing import Any

NOT_CONFIGURED = "NOT_CONFIGURED"


@dataclass(frozen=True)
class PolicyState:
    """Operational parameters the Owner must supply. Every field defaults to
    NOT_CONFIGURED; the backup tool surfaces these explicitly so an operator
    reading a manifest can see exactly what has and has not been decided."""

    rpo_hours: int | None | str = NOT_CONFIGURED
    rto_hours: int | None | str = NOT_CONFIGURED
    offsite_destination: str | None = NOT_CONFIGURED
    custodian_identities: list[str] | str = field(default_factory=lambda: NOT_CONFIGURED)
    schedule: dict[str, str] | str = field(default_factory=lambda: NOT_CONFIGURED)
    retention_overrides: dict[str, int] | str = field(default_factory=lambda: NOT_CONFIGURED)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_fully_configured(self) -> bool:
        return all(v != NOT_CONFIGURED for v in asdict(self).values())


def default_policy() -> PolicyState:
    """Policy shipped with the tool: every field NOT_CONFIGURED.

    The operator must supply a policy file or CLI overrides to flip any
    field; silent defaults are treated as unconfigured rather than assumed.
    """
    return PolicyState()


def load_policy(path: str | os.PathLike[str] | None = None) -> PolicyState:
    """Load a policy JSON file; missing/unknown keys remain NOT_CONFIGURED.

    If `path` is None, returns the default NOT_CONFIGURED policy.
    """
    if path is None:
        return default_policy()
    p = pathlib.Path(path)
    if not p.is_file():
        raise ValueError(f"policy file not found: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("policy file must be a JSON object")
    fields = {f: data.get(f, getattr(default_policy(), f)) for f in PolicyState.__annotations__}
    return PolicyState(**fields)


def append_audit(log_dir: str | os.PathLike[str], entry: dict[str, Any]) -> str:
    """Append one JSON-line audit entry and return the written line count.

    The audit log is append-only; it does not rotate or truncate. Lines
    include a UTC timestamp so replay is possible without reading file
    mtimes. Returns the path written.
    """
    log_dir = pathlib.Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "interim-backup.audit.jsonl"
    record = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "user": getpass.getuser(),
        "euid": os.geteuid(),
        **entry,
    }
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return str(log_path)


def read_audit(log_dir: str | os.PathLike[str]) -> list[dict[str, Any]]:
    log_path = pathlib.Path(log_dir) / "interim-backup.audit.jsonl"
    if not log_path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def existing_sidecar_matches(cipher_path: str | os.PathLike[str],
                             expected_cipher_digest: str) -> bool:
    """Return True when an existing sidecar for `cipher_path` carries the
    expected cipher digest — i.e., the artifact has already been produced
    with the same contents, so the run is idempotent.
    """
    sidecar = pathlib.Path(str(cipher_path) + ".manifest.json")
    if not sidecar.is_file():
        return False
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    artifacts = data.get("artifacts") if isinstance(data, dict) else None
    if not isinstance(artifacts, list) or not artifacts:
        return False
    return any(isinstance(a, dict) and a.get("sha256") == expected_cipher_digest
               for a in artifacts)


def verify_artifact_header(plain_path: str | os.PathLike[str],
                           kind: str) -> dict[str, Any]:
    """Cheap sanity verification on a decrypted dump before it is fed to
    an external loader.

    * For "database" (gzip SQL produced by mariadb-dump/mysqldump with
      default flags): check the gzip magic bytes (1f 8b) or plain-text
      `--` or `CREATE` / `INSERT` markers if uncompressed.
    * For "files" (tar archive): check the `ustar` magic at offset 257.
    * For anything else: return {verified_by_magic: False, reason: "kind
      not recognised"}.

    This is not a substitute for a real restore; it exists so obvious
    truncation (e.g. half-written backup) is caught before the artifact
    reaches the loader.
    """
    import gzip
    p = pathlib.Path(plain_path)
    if not p.is_file():
        return {"verified_by_magic": False, "reason": "file missing", "kind": kind}
    head = p.read_bytes()[:512]
    if kind == "database":
        # gzip magic
        if head.startswith(b"\x1f\x8b"):
            try:
                with gzip.open(p, "rb") as gh:
                    gz_head = gh.read(512)
                looks_sql = (b"--" in gz_head[:64] or b"MySQL" in gz_head[:64]
                             or b"CREATE" in gz_head or b"INSERT" in gz_head
                             or b"mariadb" in gz_head.lower()
                             or b"dump" in gz_head.lower())
                return {"verified_by_magic": looks_sql, "kind": kind,
                        "format": "gzip", "reason": None if looks_sql else "does not look like a SQL dump"}
            except (OSError, EOFError, gzip.BadGzipFile) as exc:
                return {"verified_by_magic": False, "kind": kind,
                        "format": "gzip", "reason": f"gzip decode failed: {exc}"}
        # uncompressed sql
        looks_sql = head.startswith(b"--") or b"CREATE" in head or b"INSERT" in head \
            or b"MySQL" in head[:64]
        return {"verified_by_magic": looks_sql, "kind": kind,
                "format": "plain", "reason": None if looks_sql else "does not look like a SQL dump"}
    if kind == "files":
        # GNU/tar archives are 512-byte blocked and the first header's
        # checksum is easy to verify. Accept either classic ustar magic or
        # GNU long-name (which still uses the POSIX header layout at 0..512
        # with a valid checksum); reject anything whose first block fails
        # the checksum check.
        if len(head) < 512:
            return {"verified_by_magic": False, "kind": kind, "format": "unknown",
                    "reason": "file shorter than one tar block"}
        # Compute POSIX tar header checksum: sum bytes treating chksum
        # field (offset 148..155) as spaces.
        chksum_field = head[148:156]
        buf = bytearray(head)
        buf[148:156] = b"        "  # eight spaces
        computed = sum(buf) & 0o777777
        try:
            # POSIX octal field: six digits plus trailing NUL or space, e.g. b"012360\0 ".
            stored = int(bytes(chksum_field).rstrip(b"\0 ").lstrip(b"0") or b"0", 8)
        except ValueError:
            stored = -1
        # ustar magic is at 257..262 in POSIX; GNU archives may have
        # "ustar \0" or "GNUtar\0" there, and PAX may have other markers.
        if computed == stored:
            return {"verified_by_magic": True, "kind": kind,
                    "format": "tar", "checksum": oct(computed)}
        return {"verified_by_magic": False, "kind": kind, "format": "unknown",
                "reason": f"first tar header checksum invalid (computed {oct(computed)} != stored {oct(stored)})"}
    return {"verified_by_magic": False, "kind": kind, "format": "unknown",
            "reason": "unrecognised artifact kind"}

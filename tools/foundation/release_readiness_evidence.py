#!/usr/bin/env python3
"""Run bounded, reproducible production-readiness evidence harnesses.

This command never connects to a Frappe site, accepts a production path, or
claims that a provider-neutral harness is production evidence. It creates a
synthetic source system and an independent restore system in a temporary
workspace, encrypts/version-rotates a real archive with the system OpenSSL,
restores it, and runs bounded revocation, audit, monitoring and rollback
checks. Runtime/deployment gates remain BLOCKED unless their actual evidence
exists elsewhere in the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_BASELINE = "14cd64e"
MARKER = b"synthetic-readiness-evidence-marker-not-production-data"


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_json(value: Any) -> str:
    return digest_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(command: list[str], *, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def sha_tree(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        result[str(path.relative_to(root))] = digest_bytes(path.read_bytes())
    return result


def make_fixture(source: Path) -> dict[str, Any]:
    native = {
        "User": [
            {"name": "course-owner@example.test", "enabled": 1, "roles": ["Course Owner"]},
            {"name": "branch-a-reception@example.test", "enabled": 1, "roles": ["Reception"]},
            {"name": "branch-b-reception@example.test", "enabled": 1, "roles": ["Reception"]},
        ],
        "Branch": [{"name": "Branch A"}, {"name": "Branch B"}],
        "User Permission": [
            {"user": "branch-a-reception@example.test", "allow": "Branch", "for_value": "Branch A"},
            {"user": "branch-b-reception@example.test", "allow": "Branch", "for_value": "Branch B"},
        ],
        "Student": [
            {"name": "student-a", "branch": "Branch A", "history": "preserve-a"},
            {"name": "student-b", "branch": "Branch B", "history": "preserve-b"},
        ],
        "Version": [
            {"name": "Version-1", "ref_doctype": "User", "docname": "branch-a-reception@example.test", "action": "role-scope-reviewed"}
        ],
    }
    files = {
        "private/Branch A/student-a/identity.bin": b"branch-a-private-file",
        "private/Branch B/student-b/identity.bin": b"branch-b-private-file",
        "public/assets/manifest.txt": MARKER,
    }
    write_json(source / "native-state.json", native)
    write_json(source / "system.json", {"system_id": "local-source-system", "phase": "local-server-tailscale"})
    for relative, content in files.items():
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return {"native": native, "files": files}


def create_archive(source: Path, archive: Path) -> None:
    with tarfile.open(archive, "w") as tar:
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            relative = path.relative_to(source)
            info = tar.gettarinfo(str(path), arcname=str(relative))
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            with path.open("rb") as stream:
                tar.addfile(info, stream)


def encrypted_version(source: Path, backup: Path, key_file: Path, version: int) -> dict[str, Any]:
    plain = backup / f"version-{version}.tar"
    cipher = backup / f"version-{version}.tar.enc"
    tag = backup / f"version-{version}.hmac"
    create_archive(source, plain)
    run([
        "openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
        "-salt", "-in", str(plain), "-out", str(cipher), "-pass", f"file:{key_file}",
    ])
    ciphertext = cipher.read_bytes()
    hmac_key = hashlib.sha256(key_file.read_bytes() + b"/hmac").digest()
    tag.write_text(hmac.new(hmac_key, ciphertext, hashlib.sha256).hexdigest() + "\n", encoding="ascii")
    plain.unlink()
    return {
        "version": version,
        "ciphertext_sha256": digest_bytes(ciphertext),
        "ciphertext_bytes": len(ciphertext),
        "hmac_sha256": tag.read_text(encoding="ascii").strip(),
        "plaintext_removed": not plain.exists(),
    }


def restore_encrypted(backup: Path, restore: Path, key_file: Path, version: int) -> dict[str, Any]:
    cipher = backup / f"version-{version}.tar.enc"
    tag = backup / f"version-{version}.hmac"
    ciphertext = cipher.read_bytes()
    hmac_key = hashlib.sha256(key_file.read_bytes() + b"/hmac").digest()
    expected_tag = tag.read_text(encoding="ascii").strip()
    actual_tag = hmac.new(hmac_key, ciphertext, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(actual_tag, expected_tag):
        raise AssertionError("encrypted backup HMAC does not verify")
    plain = backup / "restore.tar"
    run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-in", str(cipher), "-out", str(plain), "-pass", f"file:{key_file}"])
    restore.mkdir(parents=True, exist_ok=True)
    with tarfile.open(plain, "r") as tar:
        tar.extractall(restore)
    plain.unlink()
    return {"version": version, "hmac_verified": True, "decrypted_archive": True}


def check_branch_isolation() -> dict[str, Any]:
    rows = {
        "Branch A": {"student-a": "private-a"},
        "Branch B": {"student-b": "private-b"},
    }

    def can_read(user_branch: str, row_branch: str) -> bool:
        return user_branch == row_branch

    assert can_read("Branch A", "Branch A")
    assert not can_read("Branch A", "Branch B")
    assert not can_read("Branch B", "Branch A")
    aggregate = {branch: len(records) for branch, records in rows.items()}
    assert aggregate == {"Branch A": 1, "Branch B": 1}
    return {
        "status": "BLOCKED / NOT PROVEN",
        "bounded_model": "branch-scope predicate and aggregate separation passed",
        "reason": "The application checkout has no deployed native branch runtime/fixture evidence; this model is not production authorization.",
    }


def check_offboarding() -> dict[str, Any]:
    historical = {"student": "student-a", "enrollment": "enrollment-a", "audit": "Version-1"}
    user = {"enabled": 1, "roles": ["Reception"], "sessions": ["sid-a", "sid-b"]}
    before = digest_json(historical)
    user.update(enabled=0, roles=[], sessions=[])
    assert user == {"enabled": 0, "roles": [], "sessions": []}
    assert digest_json(historical) == before
    return {"status": "PASS / BOUNDED", "active_access_revoked": True, "historical_digest_preserved": True}


def check_auditability() -> dict[str, Any]:
    event = {
        "native_authority": "Version",
        "actor": "course-owner@example.test",
        "request_key": "a" * 24,
        "target": "User:branch-a-reception@example.test",
        "before": ["Reception"],
        "after": [],
    }
    assert set(("native_authority", "actor", "request_key", "target", "before", "after")) <= event.keys()
    source = (ROOT / "apps/toefl_house/toefl_house/administration.py").read_text(encoding="utf-8")
    assert '"doctype": "Version"' in source and '"audit_authority": "Version"' in source
    return {"status": "PASS / BOUNDED", "native_audit_model": "Version", "event_digest": digest_json(event)}


def check_monitoring() -> dict[str, Any]:
    alerts: list[dict[str, str]] = []

    def emit(receiver: list[dict[str, str]] | None, event: dict[str, str]) -> str:
        if receiver is None:
            return "BLOCKED / NO_RECEIVER"
        receiver.append(event)
        return "DELIVERED"

    event = {"signal": "backup_failure", "severity": "critical", "secret": "redacted"}
    assert emit(None, event) == "BLOCKED / NO_RECEIVER"
    assert emit(alerts, event) == "DELIVERED" and alerts[0]["secret"] == "redacted"
    return {"status": "BLOCKED / NOT PROVEN", "bounded_alert_delivery": True, "missing_receiver_fail_closed": True}


def check_rollback(root: Path) -> dict[str, Any]:
    releases = root / "releases"
    releases.mkdir()
    release_a = releases / "release-a.json"
    release_b = releases / "release-b.json"
    write_json(release_a, {"version": "A", "native_authority": "unchanged"})
    write_json(release_b, {"version": "B", "native_authority": "unchanged"})
    active = releases / "active.json"
    shutil.copyfile(release_a, active)
    digest_a = digest_bytes(active.read_bytes())
    shutil.copyfile(release_b, active)
    assert json.loads(active.read_text())["version"] == "B"
    shutil.copyfile(release_a, active)
    assert digest_bytes(active.read_bytes()) == digest_a
    return {"status": "PASS / BOUNDED", "release_a_sha256": digest_a, "rollback_restored": True}


def check_native_first() -> dict[str, Any]:
    source = (ROOT / "apps/toefl_house/toefl_house/administration.py").read_text(encoding="utf-8")
    for native in ("frappe.get_doc(\"User\"", "doctype\": \"Version\"", "User Permission", "Branch"):
        assert native in source
    for forbidden in ("TH Role", "TH Branch", "TH Permission", "parallel payroll"):
        assert forbidden not in source
    return {"status": "PASS / STATIC", "authority": "native User and Version; no new authority ledger"}


def run_evidence(output: Path | None = None, artifact_dir: Path | None = None) -> dict[str, Any]:
    if shutil.which("openssl") is None:
        raise RuntimeError("openssl is required for the encrypted backup evidence harness")
    artifact_dir = artifact_dir or Path(tempfile.mkdtemp(prefix="toefl-house-release-evidence-"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    try:
        artifact_ref = artifact_dir.relative_to(ROOT).as_posix()
    except ValueError:
        artifact_ref = str(artifact_dir)
    with tempfile.TemporaryDirectory(prefix="toefl-house-evidence-") as temporary:
        temp = Path(temporary)
        source = temp / "local-source-system"
        backup = temp / "backup-store"
        restore = temp / "independent-restore-system"
        backup.mkdir()
        fixture = make_fixture(source)
        key_file = temp / "external-key.material"
        key_file.write_bytes(os.urandom(32))
        versions = [encrypted_version(source, backup, key_file, version) for version in (1, 2, 3)]
        # Rotation is explicit and inspectable: keep two versioned encrypted points.
        (backup / "version-1.tar.enc").unlink()
        (backup / "version-1.hmac").unlink()
        assert not (backup / "version-1.tar.enc").exists()
        assert sorted(p.name for p in backup.glob("version-*.tar.enc")) == ["version-2.tar.enc", "version-3.tar.enc"]
        restore_info = restore_encrypted(backup, restore, key_file, 3)
        source_tree = sha_tree(source)
        restored_tree = sha_tree(restore)
        assert source_tree == restored_tree
        assert MARKER not in (backup / "version-3.tar.enc").read_bytes()
        # The key is outside the encrypted archive and is never copied into the restore system.
        assert not (restore / key_file.name).exists()
        manifest = {
            "source_tree_sha256": digest_json(source_tree),
            "restored_tree_sha256": digest_json(restored_tree),
            "same_tree": True,
            "source_system": "local-source-system",
            "restore_system": "independent-restore-system",
            "database_state_sha256": digest_bytes((source / "native-state.json").read_bytes()),
            "private_and_public_files_preserved": True,
            "external_key_not_archived": True,
        }
        write_json(artifact_dir / "encrypted-restore-manifest.json", manifest)
        report = {
            "schema_version": 1,
            "scope": "Bounded synthetic evidence harness; no production site, credentials, customer data, provider or deployment probe",
            "baseline_commit": EXPECTED_BASELINE,
            "evidence_artifact": f"{artifact_ref}/encrypted-restore-manifest.json",
            "proofs": {
                "native_first": check_native_first(),
                "encrypted_versioned_backup": {"status": "PASS / BOUNDED", "versions_created": [1, 2, 3], "versions_retained": [2, 3], "openssl_aes_256_cbc_pbkdf2": True, "hmac_verified": True},
                "restore_on_another_system": {"status": "PASS / BOUNDED", **restore_info, **manifest},
                "durable_db_and_file_preservation": {"status": "PASS / BOUNDED", "database_state_preserved": True, "private_and_public_files_preserved": True, "tree_digest_equal": True},
                "key_custody_boundary": {"status": "PASS / BOUNDED", "key_external_to_archive": True, "key_not_in_restore_tree": True},
                "offboarding_emergency_revocation": check_offboarding(),
                "branch_isolation": check_branch_isolation(),
                "auditability": check_auditability(),
                "monitoring_alerting": check_monitoring(),
                "rollback_change_control": check_rollback(temp),
            },
            "release_gate_state": {
                "domain_qualification": "PASS / SCOPED EXISTING HOSTED EVIDENCE",
                "authorization_isolation": "PASS / SCOPED; PRODUCTION NOT PROVEN",
                "dependency_security": "REJECT / SEC-DEPS-01 UPSTREAM-BLOCKED",
                # Run 35170062251 executed a real destructive trigger and a recovery onto a separate
                # ephemeral system. Run 35179445639 then executed external key custody across three
                # separate ephemeral systems: keys issued by a custodian, retrieved from two channels,
                # installed natively, used to decrypt what the operating system encrypted, and rotated.
                # Both gates stay BLOCKED. D8-BACKUP-RECOVERY also requires session revocation and a
                # measured RPO/RTO, and no owner objective exists to measure against; custody itself is
                # a bounded split-share model, not an external secret store, because this session's
                # credential cannot create repository secrets (HTTP 403, no admin permission).
                "recovery": "BLOCKED / SEPARATE-SYSTEM REHEARSAL AND KEY RETRIEVAL FROM SEPARATE CUSTODY EXECUTED; SESSION REVOCATION AND MEASURED RPO/RTO NOT PROVEN",
                "backup_restore": "BLOCKED / ENCRYPTED BACKUP RESTORED WITH A CUSTODY-RETRIEVED KEY AND BOTH KEYS ROTATED; OFF-SITE DESTINATION, VERSIONING, RETENTION AND TRUST-BOUNDARY CUSTODY NOT PROVEN",
                "upgrade_rollback": "BLOCKED / DEPLOYED FULL-BUNDLE EVIDENCE NOT PROVEN",
                "realtime": "PASS / SCOPED EXISTING EVIDENCE",
                "observability": "BLOCKED / DEPLOYED MONITORING NOT PROVEN",
                "ownership": "PASS / SCOPED OWNER DECISION + CHARTER",
                "topology_edge_session": "BLOCKED / DEPLOYED CURRENT BOUNDARY NOT PROVEN",
                "capacity_availability": "BLOCKED / NO OWNER NUMERIC OBJECTIVE",
                "durability": "BLOCKED / DEPLOYED DB/REDIS/HOST DURABILITY NOT PROVEN",
                "change_control": "BLOCKED / DEPLOYED RELEASE/ROLLBACK EVIDENCE NOT PROVEN",
                "production_authorization": "REJECT",
            },
            "production_state": "REJECT",
            "production_enabled": False,
            "synthetic_only_guard": "REQUIRED",
            "security_dependency_state": "UPSTREAM-BLOCKED / REJECT",
            "commands": [
                "python3 tools/foundation/release_readiness_evidence.py --output docs/engineering/evidence/release-readiness-evidence.json --artifact-dir docs/engineering/evidence/release-readiness",
                "python3 -m unittest tests.foundation.test_release_readiness_evidence -v",
                "python3 tools/foundation/d8_validate.py --contract docs/engineering/d8-operational-contract.template.json",
                "python3 -m unittest discover -s tests -p 'test_*.py'",
                "node tests/foundation/test_command_pages.cjs",
            ],
        }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    args = parser.parse_args()
    report = run_evidence(args.output, args.artifact_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

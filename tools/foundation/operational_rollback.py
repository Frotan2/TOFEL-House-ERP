"""Pure helpers for rolling a site back to a real versioned artifact.

A rollback that reports success proves nothing. Three things have to be observed
for it to count, and each is a separate verdict here:

* the version identity after the rollback equals the version identity recorded
  before the upgrade - from the checked-out revision, which is authoritative, and
  from ``bench version`` as the human-readable corroboration;
* the artifact the rollback deployed is byte-identical to the artifact whose digest
  was recorded when it was first built, so a rollback cannot quietly substitute
  something else;
* application state created before the upgrade is still readable afterwards, with
  content and creation timestamps unchanged - an unchanged timestamp matters,
  because a row that was deleted and re-created would have new content-equal fields
  but a different ``creation``.

Frappe has no rollback command and migrations are forward-only, so a rollback is
composed from native primitives: restore the versioned backup and put the source
back at the revision it was built from. That composition is recorded as composed
rather than presented as a native capability.
"""
import hashlib
import json
from pathlib import Path


def rollback_verdict(before, after_rollback, artifact_sha256, artifact_sha256_before):
    """Verdict on whether a rollback really restored a prior versioned artifact.

    A rollback that merely reports success is worthless. Three things must hold:
    the version observed after the rollback equals the version observed before the
    upgrade, the artifact digest deployed by the rollback equals the digest
    recorded when that artifact was first built, and the application state created
    before the upgrade is still readable afterwards.
    """
    version_restored = bool(before) and before == after_rollback
    artifact_matches = bool(artifact_sha256) and artifact_sha256 == artifact_sha256_before
    return {
        "version_before_upgrade": before,
        "version_after_rollback": after_rollback,
        "version_restored": version_restored,
        "artifact_sha256_at_rollback": artifact_sha256,
        "artifact_sha256_when_built": artifact_sha256_before,
        "artifact_is_the_same_bytes": artifact_matches,
        "verdict": ("ROLLBACK RESTORED THE PRIOR VERSIONED ARTIFACT"
                    if version_restored and artifact_matches else "NOT PROVEN"),
        "reason": ("the version string matches the pre-upgrade observation and the deployed "
                   "artifact is byte-identical to the one recorded when it was built"
                   if version_restored and artifact_matches else
                   ("version mismatch" if not version_restored else "artifact digest mismatch")),
    }


def version_identity(revision, bench_version=None, apps=None):
    """The identity a rollback has to reproduce.

    The checked-out revision is authoritative because it is what the code actually
    is; ``bench version`` is recorded as corroboration, not as the discriminator,
    since a development checkout reports a version string plus ``HEAD`` that does
    not change between adjacent commits.
    """
    return {
        "revision": revision or None,
        "bench_version": bench_version,
        "installed_apps": sorted(apps) if apps else [],
        "recorded": bool(revision),
    }


def artifact_entry(label, sha256, size_bytes, kind, created_from=None):
    """One entry in the registry of versioned artifacts a rollback may deploy."""
    return {"label": label, "sha256": sha256, "bytes": size_bytes, "kind": kind,
            "created_from": created_from, "registered": bool(sha256)}


def artifacts_match(built, deployed):
    """Compare what was registered when built against what the rollback deployed.

    A missing digest on either side is a mismatch, not a pass: an artifact that was
    never registered cannot be shown to be the one deployed.
    """
    compared = {}
    for label in sorted(set(built) | set(deployed)):
        before = built.get(label) or {}
        after = deployed.get(label) or {}
        same = bool(before.get("sha256")) and before.get("sha256") == after.get("sha256")
        compared[label] = {
            "registered_when_built": before.get("sha256"),
            "deployed_by_rollback": after.get("sha256"),
            "byte_identical": same,
            "size_before": before.get("bytes"), "size_after": after.get("bytes"),
            "missing": label not in built or label not in deployed,
        }
    mismatched = sorted(name for name, entry in compared.items()
                        if entry["missing"] or not entry["byte_identical"])
    return {"per_artifact": compared, "mismatched": mismatched,
            "all_byte_identical": not mismatched and bool(compared),
            "verdict": ("ARTIFACTS ARE THE SAME BYTES" if not mismatched and compared
                        else "NOT PROVEN")}


def data_preservation_verdict(before, after, *, require_identical_creation=True):
    """Confirm state created before the upgrade survived the rollback.

    ``creation`` is compared because it is the field a delete-and-recreate would
    change while leaving content equal. A record set that matches on content alone
    is weaker evidence than one that matches on identity too.
    """
    observations = {}
    missing = []
    changed = []
    recreated = []
    for key, expected in (before or {}).items():
        actual = (after or {}).get(key)
        if actual is None:
            missing.append(key)
            continue
        if str(actual.get("description")) != str(expected.get("description")):
            changed.append(key)
        if require_identical_creation and str(actual.get("creation")) != str(
                expected.get("creation")):
            recreated.append(key)
        observations[key] = {
            "description_matches": str(actual.get("description")) == str(
                expected.get("description")),
            "creation_matches": str(actual.get("creation")) == str(expected.get("creation")),
            "creation_before": expected.get("creation"), "creation_after": actual.get("creation"),
        }
    preserved = bool(before) and not missing and not changed and not recreated
    return {
        "records_compared": len(before or {}),
        "observations": observations,
        "missing_after_rollback": missing,
        "content_changed": changed,
        "creation_timestamp_changed": recreated,
        "preserved": preserved,
        "verdict": ("STATE PRESERVED" if preserved else "NOT PROVEN"),
        "reason": ("every record created before the upgrade is readable afterwards with "
                   "unchanged content and an unchanged creation timestamp" if preserved else
                   ("no records were compared" if not before else
                    ("missing: " + ", ".join(sorted(missing)) if missing else
                     ("content changed: " + ", ".join(sorted(changed)) if changed else
                      "creation timestamps changed, so the rows were recreated rather than "
                      "preserved: " + ", ".join(sorted(recreated)))))),
    }


def rollback_steps(*, site, backup_database, backup_public_files=None,
                   backup_private_files=None, from_revision, to_revision, app_dir,
                   remote):
    """The ordered native primitives a rollback is composed from.

    Returned as data so the plan can be inspected, recorded in the evidence and
    tested before anything executes it. Frappe offers no rollback command, and its
    migrations are forward-only, so the code has to go back to the revision the
    artifact was built from and the data has to come from the versioned backup -
    neither half alone leaves a consistent site.
    """
    steps = [
        {"order": 1, "purpose": "put the application source back at the revision the "
                                "artifact was built from",
         "command": ["git", "-C", str(app_dir), "fetch", remote, to_revision]},
        {"order": 2, "purpose": "check out that revision, detached, so the tree is exactly "
                                "the recorded one",
         "command": ["git", "-C", str(app_dir), "checkout", "--detach", to_revision]},
        {"order": 3, "purpose": "confirm the revision rather than assuming the checkout worked",
         "command": ["git", "-C", str(app_dir), "rev-parse", "HEAD"]},
        {"order": 4, "purpose": "reinstall the dependency set that revision declares, undoing "
                                "the upgrade's package changes",
         "command": ["bench", "setup", "requirements"]},
        {"order": 5, "purpose": "restore the versioned database and file artifacts",
         "command": ["bench", "--site", site, "restore", str(backup_database),
                     *(["--with-public-files", str(backup_public_files)]
                       if backup_public_files else []),
                     *(["--with-private-files", str(backup_private_files)]
                       if backup_private_files else [])]},
        {"order": 6, "purpose": "migrate the restored schema under the restored code",
         "command": ["bench", "--site", site, "migrate"]},
    ]
    return {"from_revision": from_revision, "to_revision": to_revision,
            "native_rollback_command_available": False,
            "composed_from": ["git fetch", "git checkout", "bench setup requirements",
                              "bench restore", "bench migrate"],
            "steps": steps}


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def registry_digest(entries):
    """One digest over the whole artifact registry, for cross-system comparison."""
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def find_backup_artifacts(directory, site=None):
    """Locate a Frappe backup's artifacts by role, not by an assumed exact name.

    Frappe appends ``-enc`` to every artifact name when System Settings encrypts
    backups, and the database dump is ``-database.sql.gz``, so globs have to allow
    both. Guessing the name is how a probe ends up restoring nothing.
    """
    directory = Path(directory)
    found = {}
    patterns = {
        "database": ["*-database*.sql.gz", "*-database*.sql"],
        "public_files": ["*-files.tar", "*-files*.tar"],
        "private_files": ["*-private-files.tar", "*-private-files*.tar"],
        "site_config": ["*site_config*.json"],
    }
    for role, candidates in patterns.items():
        matches = []
        for pattern in candidates:
            matches.extend(sorted(directory.glob(pattern)))
        # ``-files.tar`` also matches ``-private-files.tar``; keep them distinct.
        if role == "public_files":
            matches = [path for path in matches if "private" not in path.name]
        if matches:
            newest = max(matches, key=lambda path: path.stat().st_mtime)
            found[role] = {"path": str(newest), "name": newest.name,
                           "sha256": sha256_file(newest), "bytes": newest.stat().st_size,
                           "candidates": [path.name for path in matches]}
    return found

"""Source half of independent-system recovery: build, back up, then destroy.

Runs on one ephemeral hosted runner. It builds a real pinned Bench with
digest-pinned MariaDB and Redis, creates synthetic records plus one private and
one public file through the native API, takes a real ``bench backup --with-files``,
stages exactly the files the independent system needs, and then destroys its own
site with the native ``bench drop-site`` so the recovery on the other system is
genuine rather than a copy taken while the source was still intact.

What is staged for the other job is an explicit allowlist. ``bench backup`` also
writes a ``*-site_config.json`` alongside the dumps, and that file contains the
database password and the site encryption key; it is never staged, and the probe
verifies before finishing that no staged file is a site config and that no
generated secret appears in any staged text file. Plaintext key material must not
travel through an artifact.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from bench_bootstrap import (  # noqa: E402
    MARIADB_CONTAINER, REDIS_CACHE_CONTAINER, REDIS_QUEUE_CONTAINER,
    Probe, build_bench, cleanup, clone_pinned_sources, install_apps,
    load_components, machine_identity, new_site, require_hosted_runner,
    start_services, wait_mariadb_healthy,
)

SITE = "source.localhost"
STAGED_NAMES = ("database.sql.gz", "private-files.tar", "public-files.tar",
                "manifest.json", "source-identity.json")


def main() -> int:
    require_hosted_runner()
    components = load_components()
    lab = Path(os.environ["RUNNER_TEMP"]) / "foundation-independent-source"
    lab.mkdir(mode=0o700)
    payload = ROOT / ".foundation/independent-recovery/payload"
    if payload.exists():
        shutil.rmtree(payload)
    payload.mkdir(parents=True)
    evidence = ROOT / ".foundation/independent-source-evidence"

    passwords = [secrets.token_urlsafe(32) for _ in range(4)]
    root_password, db_password, admin_password, test_password = passwords

    report = {
        "artifact_name": "source-result.json",
        "scope": ("Source system for independent-environment recovery: real backup of synthetic "
                  "state followed by native destruction of the source site"),
        "role": "source",
        "site": SITE,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "commit": os.environ.get("GITHUB_SHA"),
        "ref": os.environ.get("GITHUB_REF"),
        "status": "running",
        "checks": [],
        "mocks_or_simulations_used": False,
        "machine_identity": machine_identity(),
        "source_revisions": {},
    }
    probe = Probe(report, evidence, lab)
    for value in passwords:
        probe.mask(value)
    # Built once, up front, as the durability probe does. `docker exec --env
    # MYSQL_PWD` forwards it from the child environment, so the value never
    # appears in a recorded command and never mutates this process' environ.
    db_env = {"MYSQL_PWD": root_password}

    secret_file = lab / "db-password"
    secret_file.write_text(root_password)
    secret_file.chmod(0o600)
    bench_dir = lab / "bench"
    source_dir = lab / "sources"
    source_dir.mkdir()
    python_bin = Path(os.environ["RUNNER_TEMP"]) / "foundation-runner-probe/python/bin/python3"
    if not python_bin.exists():
        python_bin = Path(sys.executable)

    try:
        start_services(probe, components, secret_file)
        report["mariadb_health"] = wait_mariadb_healthy(probe)
        report["source_revisions"] = clone_pinned_sources(
            probe, components, source_dir, ("frappe", "erpnext"))
        bench = build_bench(probe, components, lab, source_dir, bench_dir, python_bin)
        new_site(probe, bench, bench_dir, SITE, root_password, db_password, admin_password)
        report["installed_apps"] = install_apps(probe, bench, bench_dir, SITE, ["erpnext"])
        probe.run("migrate", [str(bench), "--site", SITE, "migrate"], cwd=bench_dir, timeout=1800)

        env_backup = dict(os.environ)
        env_backup["FOUNDATION_TEST_PASSWORD"] = test_password
        env_backup["FOUNDATION_INDEPENDENT_MANIFEST"] = str(lab / "recovery-manifest.json")
        env_backup["FOUNDATION_INDEPENDENT_REPORT"] = str(evidence / "create-result.json")
        os.environ.update({k: env_backup[k] for k in (
            "FOUNDATION_TEST_PASSWORD", "FOUNDATION_INDEPENDENT_MANIFEST",
            "FOUNDATION_INDEPENDENT_REPORT")})
        probe.run("create-synthetic-state",
                  [str(bench_dir / "env/bin/python"),
                   str(ROOT / "tools/foundation/runtime_independent_data.py"),
                   "create", SITE], cwd=bench_dir / "sites")
        created = json.loads((evidence / "create-result.json").read_text())
        if created["status"] != "pass":
            raise RuntimeError("Synthetic state was not created on the source system")
        manifest = json.loads((lab / "recovery-manifest.json").read_text())
        report["created_state"] = created["checks"][0]["observation"]
        # The exact manifest the independent system must reproduce. Recorded as a
        # digest of the canonical form so any later discrepancy is detectable.
        report["manifest_sha256"] = hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        report["manifest_run_tag"] = manifest["run_tag"]

        probe.run("backup-with-files",
                  [str(bench), "--site", SITE, "backup", "--with-files"],
                  cwd=bench_dir, timeout=1200)
        backup_dir = bench_dir / "sites" / SITE / "private" / "backups"
        database = max(backup_dir.glob("*-database.sql.gz"), key=lambda p: p.stat().st_mtime_ns)
        private_files = max(backup_dir.glob("*-private-files.tar"), key=lambda p: p.stat().st_mtime_ns)
        public_candidates = [p for p in backup_dir.glob("*-files.tar")
                             if "-private-files" not in p.name]
        if not public_candidates:
            raise RuntimeError("No public-files archive was produced by the backup")
        public_files = max(public_candidates, key=lambda p: p.stat().st_mtime_ns)

        # Explicit allowlist. Everything else in the backup directory - notably
        # bench's own *-site_config.json, which holds the database password and
        # the site encryption key - is deliberately left behind.
        staged = {
            "database.sql.gz": database,
            "private-files.tar": private_files,
            "public-files.tar": public_files,
        }
        for name, source in staged.items():
            shutil.copyfile(source, payload / name)
        shutil.copyfile(lab / "recovery-manifest.json", payload / "manifest.json")
        (payload / "source-identity.json").write_text(json.dumps({
            "role": "source", "site": SITE,
            "run_id": report["run_id"], "commit": report["commit"],
            "machine_identity": report["machine_identity"],
            "source_revisions": report["source_revisions"],
            "installed_apps": report["installed_apps"],
            "backup_sha256": {
                label: hashlib.sha256(path.read_bytes()).hexdigest()
                for label, path in staged.items()},
            "backup_bytes": {label: path.stat().st_size
                             for label, path in staged.items()},
        }, indent=2) + "\n")

        report["staged_payload"] = {
            name: {"bytes": (payload / name).stat().st_size,
                   "sha256": hashlib.sha256((payload / name).read_bytes()).hexdigest()}
            for name in STAGED_NAMES}
        report["backup_site_config_excluded"] = sorted(
            p.name for p in backup_dir.glob("*site_config*.json"))

        # Verify the exclusion rather than trusting the allowlist alone.
        staged_files = sorted(p.name for p in payload.iterdir())
        if staged_files != sorted(STAGED_NAMES):
            raise RuntimeError("Staged payload does not match the allowlist: " + str(staged_files))
        if any("site_config" in name for name in staged_files):
            raise RuntimeError("A site config was staged; it holds the key and db password")
        for name in ("manifest.json", "source-identity.json"):
            text = (payload / name).read_text()
            for value in passwords:
                if value in text:
                    raise RuntimeError("A generated secret appears in staged " + name)
            key = json.loads((bench_dir / "sites" / SITE / "site_config.json").read_text()).get(
                "encryption_key")
            if key and key in text:
                raise RuntimeError("The site encryption key appears in staged " + name)
        report["staged_payload_contains_no_secrets"] = True

        # Destructive trigger: the native, supported way to remove a site, which
        # drops its database and deletes its directory including private and
        # public files. Recovery on the other system is therefore real.
        site_dir = bench_dir / "sites" / SITE
        db_name = json.loads((site_dir / "site_config.json").read_text())["db_name"]
        report["pre_destruction"] = {
            "site_directory_exists": site_dir.exists(),
            "database_name": db_name,
            "private_file_present": (site_dir / "private/files" /
                                     "independent-recovery-private.txt").exists(),
            "public_file_present": (site_dir / "public/files" /
                                    "independent-recovery-public.txt").exists(),
            "database_present": probe.run(
                "database-present-before-destruction",
                ["docker", "exec", "--interactive", "--env", "MYSQL_PWD", MARIADB_CONTAINER,
                 "mariadb", "--user=root", "--batch", "--skip-column-names", "-e",
                 f"SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='{db_name}';"],
                quiet=True, env=db_env),
        }
        # --no-backup so destruction does not leave a second recoverable dump
        # behind on this machine. bench still moves the site directory into
        # sites/archived_sites; that is recorded rather than hidden, and it is on
        # the source VM only, so the independent system cannot reach it.
        probe.run("destructive-drop-site",
                  [str(bench), "drop-site", SITE, "--db-root-password", root_password,
                   "--no-backup"], cwd=bench_dir, timeout=600)
        # frappe moves the site directory to <bench>/archived/sites, not to
        # sites/archived_sites; recording the wrong path would silently report an
        # empty archive and misrepresent what destruction left behind.
        archived = bench_dir / "archived" / "sites"
        report["archived_site_directories_on_source_only"] = (
            sorted(p.name for p in archived.glob("*")) if archived.exists() else [])
        report["post_destruction"] = {
            "site_directory_exists": site_dir.exists(),
            "private_file_present": (site_dir / "private/files" /
                                     "independent-recovery-private.txt").exists(),
            "public_file_present": (site_dir / "public/files" /
                                    "independent-recovery-public.txt").exists(),
            "database_present": probe.run(
                "database-present-after-destruction",
                ["docker", "exec", "--interactive", "--env", "MYSQL_PWD", MARIADB_CONTAINER,
                 "mariadb", "--user=root", "--batch", "--skip-column-names", "-e",
                 f"SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='{db_name}';"],
                quiet=True, env=db_env),
        }
        post = report["post_destruction"]
        pre = report["pre_destruction"]
        if not (pre["site_directory_exists"] and pre["database_present"] == "1"
                and pre["private_file_present"] and pre["public_file_present"]):
            raise RuntimeError("Source state was not fully present before destruction")
        if post["site_directory_exists"] or post["database_present"] != "0":
            raise RuntimeError("Destructive trigger did not actually remove the source site")
        report["source_destroyed"] = True
        report["recovery_depends_on_the_staged_backup"] = True

        report["status"] = "pass"
        print("Source system backed up and destroyed; payload staged for an independent system")
    except Exception as exc:
        report["status"] = "fail"
        report["failure"] = probe.redact(str(exc))[-4000:]
        print(report["failure"], file=sys.stderr)
    finally:
        secret_file.unlink(missing_ok=True)
        (evidence / "source-result.json").write_text(
            probe.redact(json.dumps(report, indent=2)) + "\n")
        cleanup((MARIADB_CONTAINER, REDIS_QUEUE_CONTAINER, REDIS_CACHE_CONTAINER))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

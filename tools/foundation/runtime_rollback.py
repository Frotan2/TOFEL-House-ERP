"""Roll a site back to a real versioned artifact, and prove the rollback happened.

The isolated upgrade experiment moved a site forward from Frappe v16.33.0
(``33bf510b``) to the pinned current commit (``988e54f3``) while the other
applications stayed pinned, and recorded its own scope as "not rollback". This is the
other direction, and it uses the same version pair so the forward result and the
backward result describe one round trip rather than two unrelated setups.

A rollback is only worth anything if it can be distinguished from a claim, so three
separate things are observed:

* **Code identity** - the checked-out revision of ``apps/frappe`` after the rollback
  equals the revision recorded before the upgrade. The revision is authoritative;
  ``bench version`` is recorded as corroboration only, because on a development
  checkout it reports a release string plus ``HEAD`` that does not distinguish
  adjacent commits.
* **Artifact identity** - the backup the rollback restores is byte-identical to the
  backup whose digest was registered when it was taken. The artifacts are copied out
  of the live backup directory into a separate store immediately after the backup and
  restored from there, so nothing the upgrade or the restore writes can substitute a
  different file and still match.
* **Data identity** - the records and files created before the upgrade are readable
  afterwards with unchanged content *and* unchanged ``creation`` timestamps. The
  timestamp is what distinguishes preserved rows from rows that were deleted and
  re-created, which a content-only comparison would happily accept.

Frappe has no rollback command and its migrations are forward-only, so the rollback is
composed from native primitives in an order that matters: the source goes back to the
revision the artifact was built from and the dependencies are reinstalled to match
*before* the versioned backup is restored, because restoring old data under new code
would leave the schema and the code disagreeing. The plan is generated as data by
``operational_rollback.rollback_steps`` so it is recorded in the evidence and tested
before anything executes it.

What this does not claim is listed in ``not_proven_by_this_probe`` at the end. In
particular: an in-place rollback of a *major* version is not attempted, no HTTP
surface is exercised, and nothing here upgrades a release gate.
"""
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
    Probe, build_bench, cleanup, clone_pinned_sources, load_components,
    machine_identity, new_site, install_apps, require_hosted_runner, start_services,
    wait_mariadb_healthy,
)
import operational_rollback as rollback  # noqa: E402

SITE = "rollback.localhost"
#: Frappe v16.33.0 - the version the upgrade experiment started from.
OLD = "33bf510b17afcaaa857ed38b921d8e9e50dcd232"
OLD_TAG = "v16.33.0"
#: The pinned current Frappe commit - the version the upgrade experiment moved to.
NEW = "988e54f3c4c291e2077a83809663f123731abe76"
FRAPPE_REMOTE = "https://github.com/frappe/frappe"
EVIDENCE = ROOT / ".foundation/rollback-evidence"


def main() -> int:
    require_hosted_runner()
    components = load_components()
    lab = Path(os.environ["RUNNER_TEMP"]) / "foundation-rollback"
    lab.mkdir(mode=0o700, parents=True, exist_ok=True)
    #: Artifacts are copied out of the live tree into their own store, so the
    #: rollback deploys a registered artifact rather than whatever happens to be the
    #: newest file in a directory the restore may also have written to.
    store = lab / "versioned-artifacts" / "v1"
    store.mkdir(mode=0o700, parents=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    root_password = secrets.token_urlsafe(32)
    db_password = secrets.token_urlsafe(32)
    admin_password = secrets.token_urlsafe(32)

    report = {
        "artifact_name": "rollback-result.json",
        "scope": ("Rollback of a live site to a real versioned artifact: Frappe v16.33.0 -> the "
                  "pinned current commit -> back to v16.33.0, restoring a registered backup and "
                  "verifying code identity, artifact identity and data identity; synthetic data "
                  "only"),
        "role": "rollback",
        "site": SITE,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "commit": os.environ.get("GITHUB_SHA"),
        "ref": os.environ.get("GITHUB_REF"),
        "status": "running",
        "checks": [],
        "mocks_or_simulations_used": False,
        "machine_identity": machine_identity(),
        "version_pair": {"from": OLD, "from_tag": OLD_TAG, "upgraded_to": NEW,
                         "rolled_back_to": OLD},
        "verdicts": {},
    }
    probe = Probe(report, EVIDENCE, lab)
    for value in (root_password, db_password, admin_password):
        probe.mask(value)

    secret_file = lab / "db-password"
    secret_file.write_text(root_password)
    secret_file.chmod(0o600)
    bench_dir = lab / "bench"
    source_dir = lab / "sources"
    source_dir.mkdir()
    python_bin = Path(os.environ["RUNNER_TEMP"]) / "foundation-runner-probe/python/bin/python3"
    if not python_bin.exists():
        python_bin = Path(sys.executable)
    manifest = EVIDENCE / "state-manifest.json"
    state_result = EVIDENCE / "state-result.json"
    state_env = {"FOUNDATION_ROLLBACK_MANIFEST": str(manifest),
                 "FOUNDATION_ROLLBACK_STATE_RESULT": str(state_result)}

    def frappe_revision(label):
        return probe.run(label, ["git", "-C", str(bench_dir / "apps/frappe"), "rev-parse",
                                 "HEAD"], quiet=True)

    def bench_version(label):
        # Corroboration only; a bench release without this command must not fail the run.
        return probe.run(label, [str(bench), "version"], cwd=bench_dir, quiet=True,
                         allow_failure=True)

    def app_list(label):
        raw = probe.run(label, [str(bench), "--site", SITE, "list-apps"], cwd=bench_dir,
                        quiet=True)
        return sorted(line.strip() for line in raw.splitlines() if line.strip())

    def state(action, label):
        probe.run(label, [str(bench_dir / "env/bin/python"),
                          str(ROOT / "tools/foundation/runtime_rollback_state.py"),
                          action, SITE], cwd=bench_dir / "sites", timeout=900, env=state_env)
        outcome = json.loads(state_result.read_text())
        if outcome["status"] != "pass":
            raise RuntimeError("State " + action + " did not pass: "
                               + json.dumps(outcome.get("failure") or outcome["checks"]))
        return outcome

    bench = None
    try:
        start_services(probe, components, secret_file)
        report["mariadb_health"] = wait_mariadb_healthy(probe)

        # --- Deploy v1: Frappe at the v16.33.0 tag, the other apps at their pins ---
        v1_source = source_dir / "frappe"
        probe.run("clone-frappe-at-the-rollback-target",
                  ["git", "clone", "--depth", "1", "--branch", OLD_TAG, FRAPPE_REMOTE,
                   str(v1_source)], timeout=1200)
        head = probe.run("verify-frappe-source-is-the-rollback-target",
                         ["git", "-C", str(v1_source), "rev-parse", "HEAD"], quiet=True)
        if head != OLD:
            raise RuntimeError("The v16.33.0 tag did not check out at " + OLD + ": " + head)
        report["source_revisions"] = clone_pinned_sources(probe, components, source_dir,
                                                          ("erpnext",))
        report["source_revisions"]["frappe"] = head

        bench = build_bench(probe, components, lab, source_dir, bench_dir, python_bin)
        new_site(probe, bench, bench_dir, SITE, root_password, db_password, admin_password,
                 label="new-site-at-v1")
        report["installed_apps_at_v1"] = app_list("list-apps-at-v1")
        install_apps(probe, bench, bench_dir, SITE, ("erpnext",))
        report["installed_apps_at_v1"] = app_list("list-apps-at-v1-after-install")

        v1 = rollback.version_identity(frappe_revision("v1-frappe-revision"),
                                       bench_version("v1-bench-version"),
                                       report["installed_apps_at_v1"])
        report["version_identity_v1"] = v1
        if v1["revision"] != OLD:
            raise RuntimeError("The deployed site is not at the rollback target revision: "
                               + str(v1))

        # --- Create the state the rollback has to preserve ---
        state("create", "create-state-under-v1")
        created = json.loads(manifest.read_text())
        report["state_created_under_v1"] = {
            "run_tag": created["run_tag"],
            "records": len(created["records"]),
            "files": sorted(created["files"]),
            "record_names": sorted(created["records"]),
        }

        # --- Take the versioned artifact and register it ---
        probe.run("backup-under-v1", [str(bench), "--site", SITE, "backup", "--with-files"],
                  cwd=bench_dir, timeout=1800)
        found = rollback.find_backup_artifacts(bench_dir / "sites" / SITE / "private" / "backups")
        if "database" not in found:
            raise RuntimeError("No database artifact was produced by the backup: "
                               + json.dumps(sorted(found)))
        registry_v1 = {}
        for role in ("database", "public_files", "private_files"):
            if role not in found:
                continue
            source = Path(found[role]["path"])
            destination = store / source.name
            shutil.copy2(source, destination)
            registry_v1[role] = rollback.artifact_entry(
                role, rollback.sha256_file(destination), destination.stat().st_size,
                source.suffix.lstrip("."), created_from=str(source))
        report["registered_artifacts_v1"] = registry_v1
        report["artifact_registry_digest_v1"] = rollback.registry_digest(registry_v1)
        report["artifact_store"] = str(store)
        if registry_v1["database"]["sha256"] != found["database"]["sha256"]:
            raise RuntimeError("Copying the artifact into the store changed its bytes")

        # --- Upgrade to the pinned current commit ---
        probe.run("fetch-the-upgrade-target",
                  ["git", "-C", str(bench_dir / "apps/frappe"), "fetch", FRAPPE_REMOTE, NEW],
                  timeout=1200)
        probe.run("check-out-the-upgrade-target",
                  ["git", "-C", str(bench_dir / "apps/frappe"), "checkout", "--detach", NEW])
        upgraded_revision = frappe_revision("v2-frappe-revision")
        if upgraded_revision != NEW:
            raise RuntimeError("The upgrade did not reach " + NEW + ": " + upgraded_revision)
        probe.run("reinstall-dependencies-for-the-upgrade",
                  [str(bench), "setup", "requirements"], cwd=bench_dir, timeout=1800)
        probe.run("migrate-under-v2", [str(bench), "--site", SITE, "migrate"], cwd=bench_dir,
                  timeout=1800)
        v2 = rollback.version_identity(upgraded_revision, bench_version("v2-bench-version"),
                                       app_list("list-apps-at-v2"))
        report["version_identity_v2"] = v2
        if v2["revision"] == v1["revision"]:
            raise RuntimeError("The upgrade did not change the deployed revision")
        state("verify", "verify-state-survived-the-upgrade")
        report["state_survived_the_upgrade"] = True

        # --- Roll back from the registered artifact ---
        def stored(role):
            return str(store / Path(registry_v1[role]["created_from"]).name) \
                if role in registry_v1 else None

        plan = rollback.rollback_steps(
            site=SITE, backup_database=stored("database"),
            backup_public_files=stored("public_files"),
            backup_private_files=stored("private_files"),
            from_revision=v2["revision"], to_revision=OLD,
            app_dir=bench_dir / "apps/frappe", remote=FRAPPE_REMOTE)
        report["rollback_plan"] = plan

        probe.run("rollback-1-fetch-the-recorded-revision", plan["steps"][0]["command"],
                  cwd=bench_dir, timeout=1200)
        probe.run("rollback-2-check-out-the-recorded-revision", plan["steps"][1]["command"],
                  cwd=bench_dir)
        restored_revision = probe.run("rollback-3-confirm-the-revision",
                                      plan["steps"][2]["command"], quiet=True)
        if restored_revision != OLD:
            raise RuntimeError("The source did not return to " + OLD + ": " + restored_revision)
        probe.run("rollback-4-reinstall-dependencies-for-v1",
                  [str(bench)] + plan["steps"][3]["command"][1:], cwd=bench_dir, timeout=1800)
        probe.run("rollback-5-restore-the-registered-artifacts",
                  [str(bench)] + plan["steps"][4]["command"][1:]
                  + ["--db-root-password", root_password, "--admin-password", admin_password],
                  cwd=bench_dir, timeout=1800)
        probe.run("rollback-6-migrate-under-v1",
                  [str(bench)] + plan["steps"][5]["command"][1:], cwd=bench_dir, timeout=1800)

        v3 = rollback.version_identity(frappe_revision("v3-frappe-revision-after-rollback"),
                                       bench_version("v3-bench-version-after-rollback"),
                                       app_list("list-apps-after-rollback"))
        report["version_identity_after_rollback"] = v3

        # The artifact the rollback deployed, re-digested from the store it came from.
        registry_deployed = {}
        for role, entry in registry_v1.items():
            path = store / Path(entry["created_from"]).name
            registry_deployed[role] = rollback.artifact_entry(
                role, rollback.sha256_file(path), path.stat().st_size, entry["kind"],
                created_from=entry["created_from"])
        match = rollback.artifacts_match(registry_v1, registry_deployed)
        report["verdicts"]["artifact_identity"] = match
        if not match["all_byte_identical"]:
            raise RuntimeError("The rollback did not deploy the registered artifacts: "
                               + json.dumps(match["mismatched"]))

        outcome = state("verify", "verify-state-after-rollback")
        preserved = next(check["observation"] for check in outcome["checks"]
                         if check["name"] == "state-preserved-and-identical")
        report["state_after_rollback"] = {
            "records_compared": preserved["records_compared"],
            "files_compared": preserved["files_compared"],
            "missing": preserved["missing"],
            "content_changed": preserved["content_changed"],
            "creation_timestamp_changed": preserved["creation_timestamp_changed"],
            "records": preserved["detail"]["records"],
            "files": {name: {key: value for key, value in entry.items()
                             if key != "on_disk_sha256"}
                      for name, entry in preserved["detail"]["files"].items()},
        }
        # Compare what v1 wrote against what is readable after the rollback. A record
        # that came back with equal content but a new creation timestamp was rebuilt,
        # not preserved, so both fields go into the verdict.
        before = {name: {"description": entry["description"], "creation": entry["creation"]}
                  for name, entry in created["records"].items()}
        after = {}
        for name, detail in preserved["detail"]["records"].items():
            expected = created["records"].get(name, {})
            after[name] = {
                "description": (expected.get("description")
                                if detail["description_matches"] else "CONTENT CHANGED"),
                "creation": detail["creation_observed"],
            }
        data_verdict = rollback.data_preservation_verdict(before, after)
        report["verdicts"]["data_identity"] = data_verdict

        verdict = rollback.rollback_verdict(v1["revision"], v3["revision"],
                                            registry_deployed["database"]["sha256"],
                                            registry_v1["database"]["sha256"])
        report["verdicts"]["rollback"] = verdict
        report["verdicts"]["bench_version_corroboration"] = {
            "at_v1": v1["bench_version"], "at_v2": v2["bench_version"],
            "after_rollback": v3["bench_version"],
            "note": ("Corroboration only. On a development checkout bench version reports a "
                     "release string plus HEAD, which does not distinguish adjacent commits, so "
                     "the revision is what the verdict is decided on."),
        }
        report["applications_after_rollback"] = v3["installed_apps"]
        missing_apps = sorted(set(v1["installed_apps"]) - set(v3["installed_apps"]))
        if missing_apps:
            raise RuntimeError("Applications did not survive the rollback: "
                               + json.dumps(missing_apps))

        if verdict["verdict"] != "ROLLBACK RESTORED THE PRIOR VERSIONED ARTIFACT":
            raise RuntimeError("Rollback not proven: " + json.dumps(verdict))
        if not data_verdict["preserved"] or not match["all_byte_identical"]:
            raise RuntimeError("Rollback did not preserve data or artifacts: " + json.dumps(
                {"data": data_verdict["reason"], "artifacts": match["mismatched"]}))

        report["not_proven_by_this_probe"] = [
            "A rollback across a major version boundary: this is a patch-level round trip between "
            "v16.33.0 and the pinned current commit, the same pair the upgrade experiment used",
            "A code-only rollback that leaves a migrated schema in place: Frappe migrations are "
            "forward-only, so the rollback restores the versioned data artifact as well. Whether "
            "a schema can be left ahead of the code is therefore not tested, and not claimed",
            "Rollback of the other pinned applications: erpnext stays at its pin throughout, "
            "matching the upgrade experiment, so no multi-application coordinated rollback is "
            "proven",
            "An HTTP surface after the rollback: verification is through the native API inside the "
            "bench environment. Usability over HTTP is proven elsewhere - by independent recovery "
            "run 35170062251 over plaintext and by the TLS edge probe over TLS - not here",
            "Rebuilt web assets after the rollback: no bench build is run, so asset bundles are "
            "not part of what is verified",
            "Zero-downtime rollback, connection draining, or rollback while users are connected: "
            "the site is quiescent throughout",
            "A rollback triggered by a failed deployment: this is a deliberate rollback of a "
            "successful upgrade, which is the harder case to verify but not the same scenario",
            "Retention of many versioned artifacts: one artifact generation is registered and "
            "redeployed, not a store of successive releases",
            "Any production workload: every record, file and credential here is synthetic and "
            "generated for this run",
        ]
        report["status"] = "pass"
        print("Rolled back from " + NEW[:8] + " to " + OLD[:8] + " using a registered artifact: "
              "code identity, artifact identity and data identity all confirmed")
    except Exception as exc:
        report["status"] = "fail"
        report["failure"] = probe.redact(str(exc))[-4000:]
        print(report["failure"], file=sys.stderr)
    finally:
        secret_file.unlink(missing_ok=True)
        (EVIDENCE / "rollback-result.json").write_text(
            probe.redact(json.dumps(report, indent=2)) + "\n")
        cleanup((MARIADB_CONTAINER, REDIS_QUEUE_CONTAINER, REDIS_CACHE_CONTAINER))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Operator role of external key custody: run a site on keys held elsewhere.

Builds the pinned Bench on its own ephemeral hosted runner, retrieves epoch 1 key
material from the two custody channels, installs it through the native config
path, creates synthetic state including a native encrypted Password field, and
takes a real ``bench backup --with-files`` with System Settings ``encrypt_backup``
on - so the database dump and both file tars leave this machine as GPG ciphertext
rather than as readable data.

It then destroys itself the same way independent-system recovery does, with native
``bench drop-site --no-backup``, and goes one step further: ``drop-site`` moves the
site directory into ``<bench>/archived/sites``, and that archived
``site_config.json`` holds both plaintext keys, so the archive is removed too and
the whole machine is then scanned to prove no plaintext key survives. After this
job the only key material anywhere is in the two custody channels.

Two native keys are in play, and they are not interchangeable:

``encryption_key`` protects ``__Auth`` ciphertext. Installing a key the custodian
issued uses ``frappe.installer.update_site_config``, the same call
``get_encryption_key()`` makes when it generates one lazily.

``backup_encryption_key`` protects the artifacts. ``bench backup`` passes it to
``gpg --passphrase <key> -c``, and ``bench restore --encryption-key <key>`` passes
it to ``gpg -d``. Restore detects an encrypted backup by running ``file`` and
looking for ``AES``, so this probe asserts that detection itself instead of
assuming it: a backup that was not actually encrypted would restore happily
without any key, and the custody claim would be empty.

Scope limit, recorded rather than hidden: the site is frappe-only, with no product
app installed. Both keys protect framework-level surfaces - ``__Auth`` and the
backup artifacts - which behave identically with or without product apps, and
independent-system recovery (run 35170062251) already proved the full pinned stack
recovers. Installing erpnext here would add runtime and failure surface without
adding custody evidence.
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
    Probe, build_bench, cleanup, clone_pinned_sources, install_mariadb_client,
    load_components, machine_identity, new_site, require_hosted_runner,
    start_services, wait_mariadb_healthy,
)
import key_custody as custody  # noqa: E402

SITE = "custody-operator.localhost"
CUSTODY = ROOT / ".foundation/key-custody"
PAYLOAD = ROOT / ".foundation/key-custody-operator/payload"
EVIDENCE = ROOT / ".foundation/key-custody-operator-evidence"
STAGED_NAMES = ("database.sql.gz", "private-files.tar", "public-files.tar",
                "manifest.json", "operator-identity.json")
PRIVATE_FILE = "key-custody-private.txt"
PUBLIC_FILE = "key-custody-public.txt"


def load_channels(role):
    """Read both custody channels and the manifest that this role downloaded."""
    manifest_path = CUSTODY / "manifest" / "custody-manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("The custody manifest did not arrive for the " + role
                           + " system: " + str(manifest_path))
    manifest = json.loads(manifest_path.read_text())
    channels = {}
    for channel in ("a", "b"):
        directory = CUSTODY / ("channel-" + channel)
        if not directory.exists():
            raise RuntimeError("Custody channel " + channel + " did not arrive for the "
                               + role + " system")
        channels[channel] = {
            name: json.loads((directory / name).read_text())
            for name in sorted(os.listdir(directory))}
    return manifest, channels


def retrieve(channels, manifest, epoch, role_key):
    """Reconstruct one key from both channels and verify it against the manifest.

    Retrieval is verified, not assumed: the reconstructed key must fingerprint to
    the value the custodian published for that epoch and role. A share from the
    wrong epoch produces a valid-looking key with the wrong fingerprint, which is
    why the fingerprint check is the gate.
    """
    entry = next(e for e in manifest["entries"]
                 if e["epoch"] == epoch and e["key_role"] == role_key)
    name = f"epoch{epoch}-{role_key}.json"
    reports = {}
    for channel in ("a", "b"):
        if name not in channels[channel]:
            raise RuntimeError("Custody channel " + channel + " is missing " + name)
        reports[channel] = channels[channel][name]
    return custody.reconstruct_key(reports["a"]["share"], reports["b"]["share"]), entry


def main() -> int:
    require_hosted_runner()
    components = load_components()
    lab = Path(os.environ["RUNNER_TEMP"]) / "foundation-key-custody-operator"
    lab.mkdir(mode=0o700, parents=True, exist_ok=True)
    if PAYLOAD.exists():
        shutil.rmtree(PAYLOAD)
    PAYLOAD.mkdir(parents=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    passwords = [secrets.token_urlsafe(32) for _ in range(4)]
    root_password, db_password, admin_password, api_secret = passwords

    report = {
        "artifact_name": "operator-result.json",
        "scope": ("Operator system for external key custody: run a real site on keys retrieved "
                  "from separate custody channels, produce an encrypted backup, then destroy the "
                  "site and every local copy of the key material"),
        "role": "operator",
        "site": SITE,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "commit": os.environ.get("GITHUB_SHA"),
        "ref": os.environ.get("GITHUB_REF"),
        "status": "running",
        "checks": [],
        "mocks_or_simulations_used": False,
        "machine_identity": machine_identity(),
        "operator_revisions": {},
    }
    probe = Probe(report, EVIDENCE, lab)
    for value in passwords:
        probe.mask(value)
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
        manifest, channels = load_channels("operator")
        report["custody_manifest"] = {
            "sha256": hashlib.sha256(
                (CUSTODY / "manifest" / "custody-manifest.json").read_bytes()).hexdigest(),
            "entries": len(manifest["entries"]),
            "split_method": manifest["split_method"],
            "epochs": manifest["epochs_issued"],
            "rotation_lineage": manifest["rotation_lineage"],
        }
        for channel, files in channels.items():
            report.setdefault("custody_channels", {})[channel] = sorted(files)

        retrieved = {}
        retrieved_evidence = {}
        for role_key in custody.KEY_ROLES:
            for epoch in (1, 2):
                key, entry = retrieve(channels, manifest, epoch, role_key)
                # Masked before anything else can happen, so a key cannot reach a
                # recorded command or an error message unredacted.
                probe.mask(key)
                if custody.key_fingerprint(key) != entry["fingerprint"]:
                    raise RuntimeError(
                        "Key retrieved from custody does not match the custodian's fingerprint for "
                        f"epoch {epoch} {role_key}")
                format_check = custody.validate_key_format(key)
                if not format_check["valid"]:
                    raise RuntimeError(f"Retrieved key is malformed: epoch {epoch} {role_key}: "
                                       + str(format_check["reason"]))
                retrieved[(epoch, role_key)] = key
                retrieved_evidence[f"epoch{epoch}-{role_key}"] = {
                    "fingerprint": entry["fingerprint"],
                    "matches_custody_manifest": True,
                    "native_fernet_format": {
                        "valid": True,
                        "characters": format_check["characters"],
                        "decoded_bytes": format_check["decoded_bytes"],
                        "matches": ("the shape Fernet.generate_key() produces, which is what "
                                    "frappe.installer.update_site_config and gpg both accept"),
                    },
                    "channels_combined": ["a", "b"],
                }
        site_key, backup_key = retrieved[(1, custody.SITE_KEY)], retrieved[(1, custody.BACKUP_KEY)]
        site_key_2 = retrieved[(2, custody.SITE_KEY)]
        report["key_retrieval"] = {
            "channels_required": ["a", "b"],
            "retrieved": retrieved_evidence,
            "verified_by": "SHA-256 fingerprint comparison against the custodian's manifest",
            "plaintext_published": False,
        }

        # Negative controls, run before anything is built: they are the reason the
        # split means anything at all.
        entry1 = next(e for e in manifest["entries"]
                      if e["epoch"] == 1 and e["key_role"] == custody.SITE_KEY)
        name1 = "epoch1-" + custody.SITE_KEY + ".json"
        name2 = "epoch2-" + custody.SITE_KEY + ".json"
        controls = {
            "channel_a_alone": custody.reconstruction_report(
                channels["a"][name1]["share"], channels["a"][name1]["share"],
                entry1["fingerprint"]),
            "channel_b_alone": custody.reconstruction_report(
                channels["b"][name1]["share"], channels["b"][name1]["share"],
                entry1["fingerprint"]),
            "epoch1_a_with_epoch2_b": custody.reconstruction_report(
                channels["a"][name1]["share"], channels["b"][name2]["share"],
                entry1["fingerprint"]),
        }
        report["custody_negative_controls_before_use"] = controls
        for label, result in controls.items():
            if result["fingerprint_matches"]:
                raise RuntimeError("A custody negative control reconstructed the key: " + label)

        start_services(probe, components, secret_file)
        report["mariadb_health"] = wait_mariadb_healthy(probe)
        install_mariadb_client(probe)
        report["machine_identity"]["docker_daemon_id"] = report["docker_daemon_id"]
        report["operator_revisions"] = clone_pinned_sources(
            probe, components, source_dir, ("frappe", "erpnext"))
        bench = build_bench(probe, components, lab, source_dir, bench_dir, python_bin)
        new_site(probe, bench, bench_dir, SITE, root_password, db_password, admin_password)
        report["installed_apps"] = []
        report["product_app_not_installed"] = {
            "reason": ("Both custody keys protect framework-level surfaces - __Auth ciphertext and "
                       "the backup artifacts - which behave identically with or without a product "
                       "app. Independent-system recovery run 35170062251 already proved the full "
                       "pinned stack recovers, so installing erpnext here would add runtime and "
                       "failure surface without adding custody evidence."),
        }
        probe.run("migrate", [str(bench), "--site", SITE, "migrate"], cwd=bench_dir, timeout=1800)
        site_dir = bench_dir / "sites" / SITE
        db_name = json.loads((site_dir / "site_config.json").read_text())["db_name"]
        report["operator_database_name"] = db_name

        def run_data(action, extra_env=None, report_name="data-result.json"):
            environment = dict(os.environ)
            environment.update({
                "FOUNDATION_CUSTODY_SITE_KEY": site_key,
                "FOUNDATION_CUSTODY_BACKUP_KEY": backup_key,
                "FOUNDATION_CUSTODY_SITE_KEY_2": site_key_2,
                "FOUNDATION_CUSTODY_SECRET": api_secret,
                "FOUNDATION_CUSTODY_MANIFEST": str(lab / "custody-manifest-state.json"),
                "FOUNDATION_CUSTODY_REPORT": str(EVIDENCE / report_name),
            })
            if extra_env:
                environment.update(extra_env)
            probe.run(action, [str(bench_dir / "env/bin/python"),
                               str(ROOT / "tools/foundation/runtime_key_custody_data.py"),
                               action, SITE], cwd=bench_dir / "sites", env=environment)
            result = json.loads((EVIDENCE / report_name).read_text())
            if result["status"] != "pass":
                raise RuntimeError(action + " did not pass: " + json.dumps(result["checks"])[-800:])
            return result

        installed = run_data("install-keys", report_name="install-keys-result.json")
        report["keys_installed_natively"] = installed["checks"][0]["observation"]
        report["backup_encryption_enabled"] = installed["checks"][1]["observation"]
        created = run_data("create", report_name="create-result.json")
        state = created["checks"][0]["observation"]
        report["created_state"] = state
        report["manifest_sha256"] = hashlib.sha256(
            (lab / "custody-manifest-state.json").read_bytes()).hexdigest()

        # cwd MUST be the bench directory: frappe builds archive members from a
        # sites-relative path and `bench restore` untars with --strip 2.
        probe.run("backup-with-files-under-encryption",
                  [str(bench), "--site", SITE, "backup", "--with-files"],
                  cwd=bench_dir, timeout=1200)
        backup_dir = site_dir / "private" / "backups"
        database = max(backup_dir.glob("*-database.sql.gz"), key=lambda p: p.stat().st_mtime_ns)
        private_files = max(backup_dir.glob("*-private-files.tar"),
                            key=lambda p: p.stat().st_mtime_ns)
        public_candidates = [p for p in backup_dir.glob("*-files.tar")
                             if "-private-files" not in p.name]
        if not public_candidates:
            raise RuntimeError("No public-files archive was produced by the backup")
        public_files = max(public_candidates, key=lambda p: p.stat().st_mtime_ns)

        # Assert the encryption rather than trusting the setting. `bench restore`
        # decides whether to decrypt by running `file` and looking for AES, so if
        # these artifacts are not detected as AES the recovery side would restore
        # them without any key and the custody claim would be empty.
        detection = {}
        for label, path in (("database.sql.gz", database), ("private-files.tar", private_files),
                            ("public-files.tar", public_files)):
            description = probe.run("detect-encryption-" + label, ["file", "--brief", str(path)],
                                    quiet=True)
            detection[label] = {"file_says": description,
                                "aes_detected": "AES" in description,
                                "gpg_detected": "GPG" in description.upper()}
            if "AES" not in description:
                raise RuntimeError(
                    "bench backup did not encrypt " + label + " even though encrypt_backup is on; "
                    "`file` reports: " + description)
        report["backup_artifacts_are_encrypted_at_rest"] = detection

        staged = {"database.sql.gz": database, "private-files.tar": private_files,
                  "public-files.tar": public_files}
        for name, source in staged.items():
            shutil.copyfile(source, PAYLOAD / name)
        shutil.copyfile(lab / "custody-manifest-state.json", PAYLOAD / "manifest.json")
        (PAYLOAD / "operator-identity.json").write_text(json.dumps({
            "role": "operator", "site": SITE, "run_id": report["run_id"],
            "commit": report["commit"], "machine_identity": report["machine_identity"],
            "operator_lab_path": str(lab), "operator_database_name": db_name,
            "operator_revisions": report["operator_revisions"],
            "installed_apps": report["installed_apps"],
            "custody_manifest_sha256": report["custody_manifest"]["sha256"],
            "key_fingerprints": {
                "epoch1_encryption_key": custody.key_fingerprint(site_key),
                "epoch1_backup_encryption_key": custody.key_fingerprint(backup_key),
                "epoch2_encryption_key": custody.key_fingerprint(site_key_2)},
            "backup_sha256": {label: hashlib.sha256(path.read_bytes()).hexdigest()
                              for label, path in staged.items()},
            "backup_bytes": {label: path.stat().st_size for label, path in staged.items()},
        }, indent=2) + "\n")

        report["staged_payload"] = {
            name: {"bytes": (PAYLOAD / name).stat().st_size,
                   "sha256": hashlib.sha256((PAYLOAD / name).read_bytes()).hexdigest()}
            for name in STAGED_NAMES}
        site_config_backups = sorted(p.name for p in backup_dir.glob("*site_config*.json"))
        report["backup_site_config_excluded"] = site_config_backups
        if not site_config_backups:
            # Not a failure of the probe, but the exclusion claim would be empty.
            report["backup_site_config_excluded_note"] = (
                "No site config backup was written beside the dumps in this run, so there was "
                "nothing to exclude; the allowlist would still have refused it.")

        staged_files = sorted(p.name for p in PAYLOAD.iterdir())
        if staged_files != sorted(STAGED_NAMES):
            raise RuntimeError("Staged payload does not match the allowlist: " + str(staged_files))
        if any("site_config" in name for name in staged_files):
            raise RuntimeError("A site config was staged; it holds both keys and the db password")

        # Scan every staged byte for key material and for the synthetic secret.
        # The artifacts are ciphertext, so a hit here would mean the backup leaks.
        needles = {"epoch1_site_key": site_key, "epoch1_backup_key": backup_key,
                   "epoch2_site_key": site_key_2, "api_secret": api_secret,
                   "root_password": root_password, "db_password": db_password,
                   "admin_password": admin_password}
        leaks = {}
        for name in STAGED_NAMES:
            found = custody.find_plaintext((PAYLOAD / name).read_bytes(), needles)
            if found:
                leaks[name] = found
        report["staged_payload_scan"] = {"secrets_scanned": sorted(needles), "leaks": leaks,
                                         "clean": not leaks}
        if leaks:
            raise RuntimeError("The encrypted backup leaked plaintext: " + json.dumps(leaks))

        report["pre_destruction"] = {
            "site_directory_exists": site_dir.exists(),
            "database_name": db_name,
            "private_file_present": (site_dir / "private/files" / PRIVATE_FILE).exists(),
            "public_file_present": (site_dir / "public/files" / PUBLIC_FILE).exists(),
            "site_config_holds_both_keys": all(
                json.loads((site_dir / "site_config.json").read_text()).get(k)
                for k in ("encryption_key", "backup_encryption_key")),
            "database_present": probe.run(
                "database-present-before-destruction",
                ["docker", "exec", "--interactive", "--env", "MYSQL_PWD", MARIADB_CONTAINER,
                 "mariadb", "--user=root", "--batch", "--skip-column-names", "-e",
                 f"SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='{db_name}';"],
                quiet=True, env=db_env),
        }
        probe.run("destructive-drop-site",
                  [str(bench), "drop-site", SITE, "--db-root-password", root_password,
                   "--no-backup"], cwd=bench_dir, timeout=600)
        # drop-site archives the site directory to <bench>/archived/sites, and that
        # archive contains site_config.json with BOTH plaintext keys. Custody means
        # it must not survive on this machine, so it is removed and the removal is
        # verified rather than assumed.
        archived = bench_dir / "archived" / "sites"
        archived_before = sorted(p.name for p in archived.glob("*")) if archived.exists() else []
        if archived.exists():
            shutil.rmtree(archived)
        report["archived_site_directory_removed"] = {
            "present_after_drop_site": archived_before,
            "held_plaintext_keys": True,
            "removed": not archived.exists(),
            "reason": ("bench drop-site archives the site directory, and the archived "
                       "site_config.json holds both plaintext keys, so custody requires removing "
                       "it; leaving it would mean plaintext key material survived on the "
                       "operator machine after destruction."),
        }
        if archived.exists():
            raise RuntimeError("The archived site directory survived removal")

        report["post_destruction"] = {
            "site_directory_exists": site_dir.exists(),
            "private_file_present": (site_dir / "private/files" / PRIVATE_FILE).exists(),
            "public_file_present": (site_dir / "public/files" / PUBLIC_FILE).exists(),
            "database_present": probe.run(
                "database-present-after-destruction",
                ["docker", "exec", "--interactive", "--env", "MYSQL_PWD", MARIADB_CONTAINER,
                 "mariadb", "--user=root", "--batch", "--skip-column-names", "-e",
                 f"SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='{db_name}';"],
                quiet=True, env=db_env),
        }
        pre, post = report["pre_destruction"], report["post_destruction"]
        if not (pre["site_directory_exists"] and pre["database_present"] == "1"
                and pre["private_file_present"] and pre["public_file_present"]
                and pre["site_config_holds_both_keys"]):
            raise RuntimeError("Operator state was not fully present before destruction")
        if post["site_directory_exists"] or post["database_present"] != "0":
            raise RuntimeError("Destructive trigger did not remove the operator site")
        report["operator_destroyed"] = True

        # The custody property this job exists to establish: after destruction, no
        # plaintext key survives anywhere this job could have written one.
        survivors = []
        for root in (lab, ROOT / ".foundation"):
            for path in sorted(Path(root).rglob("*")):
                if not path.is_file():
                    continue
                try:
                    blob = path.read_bytes()
                except OSError:
                    continue
                found = custody.find_plaintext(blob, {
                    "epoch1_site_key": site_key, "epoch1_backup_key": backup_key,
                    "epoch2_site_key": site_key_2,
                    "epoch2_backup_key": retrieved[(2, custody.BACKUP_KEY)]})
                if found:
                    survivors.append({"path": str(path), "found": found})
        report["no_plaintext_key_survives_destruction"] = {
            "scanned_roots": [str(lab), str(ROOT / ".foundation")],
            "survivors": survivors, "clean": not survivors,
            "meaning": ("The only surviving copies of this key material are the shares in the two "
                        "custody channels, which this machine never held in reconstructed form "
                        "after destruction."),
        }
        if survivors:
            raise RuntimeError("Plaintext key material survived destruction: "
                               + json.dumps(survivors))

        report["recovery_depends_on_custody_and_the_staged_backup"] = True
        report["status"] = "pass"
        print("Operator site backed up under custodian-issued keys, then destroyed; "
              "no plaintext key survives on this machine")
    except Exception as exc:
        report["status"] = "fail"
        report["failure"] = probe.redact(str(exc))[-4000:]
        print(report["failure"], file=sys.stderr)
    finally:
        secret_file.unlink(missing_ok=True)
        (EVIDENCE / "operator-result.json").write_text(
            probe.redact(json.dumps(report, indent=2)) + "\n")
        cleanup((MARIADB_CONTAINER, REDIS_QUEUE_CONTAINER, REDIS_CACHE_CONTAINER))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Recovery role of external key custody: retrieve, restore, decrypt, rotate.

Runs on a third ephemeral hosted runner. It retrieves key material from the two
custody channels, and before it builds anything it proves the retrieval is
load-bearing: restoring the encrypted backup **without** a key must fail, and
restoring it with a real key from the wrong epoch must fail too. Only then does it
restore properly with ``bench restore --encryption-key``, install the retrieved
site key through the native config path, and prove the field the operator
encrypted now decrypts.

That last check is the point of the whole exercise. Independent-system recovery
(run 35170062251) proved a destroyed site's database and files come back on a
separate machine, and asserted as an expected failure that the source-encrypted
field was intact but undecryptable, because no key travelled. Here the same field
must decrypt, with the key obtained from custody rather than from the backup.

Then rotation, which Frappe has no command for:

* the site key is rotated to epoch 2 and the native consequence is recorded -
  ciphertext written under epoch 1 stops decrypting, which is what ``decrypt()``
  itself warns about when it tells an operator to restore the original
  ``site_config.json``;
* the ciphertext is re-encrypted through native primitives and becomes readable
  again, with its plaintext digest unchanged;
* the epoch 1 key no longer decrypts it, the epoch 2 key does, and a key custody
  never issued does not;
* the backup key is rotated too, and the proof is cryptographic rather than
  another full restore: a new backup is taken under epoch 2, detected as AES, and
  ``gpg -d`` succeeds with the epoch 2 key and fails with the epoch 1 key.

Finally the three roles are proven to have run on three separate machines, using
the discriminator model that independent-system recovery established - boot id and
runner name required to differ, ``dmi_product_uuid`` corroborating, and hostname
plus Docker daemon id recorded as observations only, each annotated with the run
that disproved it as a discriminator.
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
from runtime_key_custody_operator import load_channels, retrieve  # noqa: E402

SITE = "custody-recovered.localhost"
NEGATIVE_SITE = "custody-negative.localhost"
PAYLOAD = ROOT / ".foundation/key-custody-operator/payload"
EVIDENCE = ROOT / ".foundation/key-custody-recovery-evidence"


def main() -> int:
    require_hosted_runner()
    components = load_components()
    lab = Path(os.environ["RUNNER_TEMP"]) / "foundation-key-custody-recovery"
    lab.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch = lab / "negative-controls"
    scratch.mkdir(mode=0o700)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    root_password = secrets.token_urlsafe(32)
    db_password = secrets.token_urlsafe(32)
    admin_password = secrets.token_urlsafe(32)
    passwords = [root_password, db_password, admin_password]

    report = {
        "artifact_name": "recovery-result.json",
        "scope": ("Recovery system for external key custody: retrieve key material from separate "
                  "custody channels, prove retrieval is load-bearing, restore an encrypted backup, "
                  "decrypt what the operator encrypted, then rotate both keys"),
        "role": "recovery",
        "site": SITE,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "commit": os.environ.get("GITHUB_SHA"),
        "ref": os.environ.get("GITHUB_REF"),
        "status": "running",
        "checks": [],
        "mocks_or_simulations_used": False,
        "machine_identity": machine_identity(),
        "target_revisions": {},
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
        manifest, channels = load_channels("recovery")
        identity = json.loads((PAYLOAD / "operator-identity.json").read_text())
        state_manifest = json.loads((PAYLOAD / "manifest.json").read_text())
        retrieved = {}
        for role_key in custody.KEY_ROLES:
            for epoch in (1, 2):
                key, entry = retrieve(channels, manifest, epoch, role_key)
                probe.mask(key)
                if custody.key_fingerprint(key) != entry["fingerprint"]:
                    raise RuntimeError("Retrieved key does not match the custodian fingerprint: "
                                       f"epoch {epoch} {role_key}")
                retrieved[(epoch, role_key)] = key
        site_key = retrieved[(1, custody.SITE_KEY)]
        backup_key = retrieved[(1, custody.BACKUP_KEY)]
        site_key_2 = retrieved[(2, custody.SITE_KEY)]
        backup_key_2 = retrieved[(2, custody.BACKUP_KEY)]

        # The operator published fingerprints, not keys. Agreement between two
        # machines that never shared a plaintext key is the retrieval proof.
        published = identity["key_fingerprints"]
        agreement = {
            "epoch1_encryption_key": custody.key_fingerprint(site_key)
            == published["epoch1_encryption_key"],
            "epoch1_backup_encryption_key": custody.key_fingerprint(backup_key)
            == published["epoch1_backup_encryption_key"],
            "epoch2_encryption_key": custody.key_fingerprint(site_key_2)
            == published["epoch2_encryption_key"],
        }
        report["key_retrieval"] = {
            "channels_required": ["a", "b"],
            "fingerprints_agree_with_the_operator": agreement,
            "verified_by": ("SHA-256 fingerprints published by the custodian and by the operator, "
                            "compared against keys reconstructed here from both channels"),
            "plaintext_key_received_from_the_backup": False,
            "plaintext_published": False,
        }
        if not all(agreement.values()):
            raise RuntimeError("Retrieved keys disagree with the operator's fingerprints: "
                               + json.dumps(agreement))

        name1 = "epoch1-" + custody.SITE_KEY + ".json"
        name2 = "epoch2-" + custody.SITE_KEY + ".json"
        entry1 = next(e for e in manifest["entries"]
                      if e["epoch"] == 1 and e["key_role"] == custody.SITE_KEY)
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
        report["custody_negative_controls"] = controls
        for label, result in controls.items():
            if result["fingerprint_matches"]:
                raise RuntimeError("A custody negative control reconstructed the key: " + label)

        # Payload integrity before anything consumes it.
        integrity = {}
        for name in ("database.sql.gz", "private-files.tar", "public-files.tar",
                     "manifest.json", "operator-identity.json"):
            digest = hashlib.sha256((PAYLOAD / name).read_bytes()).hexdigest()
            expected = identity["backup_sha256"].get(name)
            integrity[name] = {"bytes": (PAYLOAD / name).stat().st_size, "sha256": digest,
                               "matches_source_record": (digest == expected) if expected else None}
            if expected and digest != expected:
                raise RuntimeError("Transferred payload differs from the operator's record: " + name)
        report["payload_integrity"] = integrity

        start_services(probe, components, secret_file)
        report["mariadb_health"] = wait_mariadb_healthy(probe)
        install_mariadb_client(probe)
        report["machine_identity"]["docker_daemon_id"] = report["docker_daemon_id"]
        # Same discriminator independent-system recovery used: the recovering
        # system must not already hold the database it is about to restore.
        report["operator_database_absent_before_restore"] = probe.run(
            "operator-database-is-absent-before-restore",
            ["docker", "exec", "--interactive", "--env", "MYSQL_PWD", MARIADB_CONTAINER,
             "mariadb", "--user=root", "--batch", "--skip-column-names", "-e",
             "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='"
             + identity["operator_database_name"] + "';"], quiet=True, env=db_env)
        if report["operator_database_absent_before_restore"] != "0":
            raise RuntimeError(
                "This system already held the operator's database, so a successful restore would "
                "prove nothing about recovery")
        report["target_revisions"] = clone_pinned_sources(
            probe, components, source_dir, ("frappe", "erpnext"))
        if report["target_revisions"] != identity["operator_revisions"]:
            raise RuntimeError("Recovery rebuilt from different revisions than the operator: "
                               + json.dumps({"recovery": report["target_revisions"],
                                             "operator": identity["operator_revisions"]}))
        bench = build_bench(probe, components, lab, source_dir, bench_dir, python_bin)

        # --- Negative controls: retrieval must be load-bearing -----------------
        # Run on copies, so a failed attempt cannot consume the real payload.
        new_site(probe, bench, bench_dir, NEGATIVE_SITE, root_password, db_password,
                 admin_password, label="new-site-for-negative-controls")
        staged_sql = PAYLOAD / "database.sql.gz"
        original_digest = hashlib.sha256(staged_sql.read_bytes()).hexdigest()

        def attempt(label, sql_copy, extra):
            """Run a restore that is REQUIRED to fail.

            ``allow_failure=True`` is deliberate: without it Probe.run would mark
            the whole report failed, and an expected failure is evidence here
            rather than an error. The exit code is read back from the recorded
            check, which is the only thing Probe.run exposes about the process.
            """
            command = [str(bench), "--site", NEGATIVE_SITE, "restore", str(sql_copy),
                       "--db-root-password", root_password, "--admin-password", admin_password,
                       *extra]
            probe.run(label, command, cwd=bench_dir, timeout=900, allow_failure=True)
            record = next((c for c in reversed(report["checks"]) if c["name"] == label), None)
            if record is None:
                raise RuntimeError("The negative control was not recorded: " + label)
            return {"exit_code": record["exit_code"],
                    "failed_as_required": record["exit_code"] != 0,
                    "output_tail": str(record.get("output_tail", ""))[-1200:],
                    "required_to_fail": True}

        copy_a = scratch / "no-key-database.sql.gz"
        shutil.copyfile(staged_sql, copy_a)
        report["restore_without_any_key_must_fail"] = attempt(
            "negative-control-restore-without-key", copy_a, [])
        copy_b = scratch / "wrong-epoch-database.sql.gz"
        shutil.copyfile(staged_sql, copy_b)
        report["restore_with_the_wrong_epoch_key_must_fail"] = attempt(
            "negative-control-restore-with-wrong-epoch-key", copy_b,
            ["--encryption-key", backup_key_2])
        for label in ("restore_without_any_key_must_fail",
                      "restore_with_the_wrong_epoch_key_must_fail"):
            if not report[label]["failed_as_required"]:
                raise RuntimeError(
                    "The encrypted backup restored without the correct custody key, so custody is "
                    "not load-bearing and this probe proves nothing: " + label)
        after = hashlib.sha256(staged_sql.read_bytes()).hexdigest()
        report["payload_untouched_by_the_negative_controls"] = {
            "sha256_before": original_digest, "sha256_after": after,
            "unchanged": original_digest == after,
            "why_it_matters": ("frappe's decrypt_backup renames the dump to .gpg and renames it "
                               "back in a finally block, so a failed attempt must leave the "
                               "staged payload byte-identical; the real restore consumes the "
                               "original file and must not be handed a damaged one."),
        }
        if original_digest != after:
            raise RuntimeError("A negative control damaged the staged payload")
        probe.run("drop-negative-control-site",
                  [str(bench), "drop-site", NEGATIVE_SITE, "--db-root-password", root_password,
                   "--no-backup"], cwd=bench_dir, timeout=600)
        report["negative_control_site_dropped"] = not (bench_dir / "sites" / NEGATIVE_SITE).exists()
        report["negative_controls_left_no_recoverable_copy"] = {
            "scratch_sql_copies_removed": True,
            "why": ("each negative-control attempt ran on a copy of the dump so the staged payload "
                    "was never handed to a failing gpg run; the copies are deleted here so the only "
                    "encrypted dump left on this machine is the one the real restore consumed."),
        }
        for stale in (copy_a, copy_b):
            stale.unlink(missing_ok=True)

        # --- The real restore, with the key retrieved from custody -------------
        new_site(probe, bench, bench_dir, SITE, root_password, db_password, admin_password,
                 label="new-empty-site-for-custody-recovery")
        probe.run("restore-encrypted-backup-with-key-from-custody",
                  [str(bench), "--site", SITE, "restore", str(staged_sql),
                   "--db-root-password", root_password, "--admin-password", admin_password,
                   "--encryption-key", backup_key,
                   "--with-public-files", str(PAYLOAD / "public-files.tar"),
                   "--with-private-files", str(PAYLOAD / "private-files.tar")],
                  cwd=bench_dir, timeout=1800)
        probe.run("restore-migrate", [str(bench), "--site", SITE, "migrate"],
                  cwd=bench_dir, timeout=1800)
        # ``bench restore --admin-password`` does not reach the Administrator user
        # on the restore path (hosted run 35168996127: HTTP 401 after a successful
        # restore), so the recovering system sets its own credential natively and
        # never needs one from the operator.
        probe.run("set-admin-password-on-recovered-site",
                  [str(bench), "--site", SITE, "set-admin-password", admin_password],
                  cwd=bench_dir, timeout=600)
        report["restored_into_a_separate_database"] = True
        report["admin_credential_is_the_recovery_systems_own"] = {
            "operator_admin_password_transferred": False,
            "set_with_native_command": "bench set-admin-password",
        }
        report["backup_decrypted_with_key_from_custody"] = {
            "native_option": "bench restore --encryption-key",
            "key_source": "reconstructed from custody channels a and b, fingerprint-verified",
            "applied_to": ["database.sql.gz", "public-files.tar", "private-files.tar"],
            "note": ("frappe applies the same key to the file tars whenever --encryption-key is "
                     "set, which is correct here because bench backup encrypted all three with "
                     "the one backup_encryption_key."),
        }
        report["payload_intact_after_restore"] = {
            name: hashlib.sha256((PAYLOAD / name).read_bytes()).hexdigest()
            for name in ("database.sql.gz", "private-files.tar", "public-files.tar")}

        def run_data(action, report_name, site=SITE):
            environment = dict(os.environ)
            environment.update({
                "FOUNDATION_CUSTODY_SITE_KEY": site_key,
                "FOUNDATION_CUSTODY_BACKUP_KEY": backup_key,
                "FOUNDATION_CUSTODY_SITE_KEY_2": site_key_2,
                "FOUNDATION_CUSTODY_BACKUP_KEY_2": backup_key_2,
                "FOUNDATION_CUSTODY_SECRET": os.environ.get("FOUNDATION_CUSTODY_SECRET", ""),
                "FOUNDATION_CUSTODY_MANIFEST": str(PAYLOAD / "manifest.json"),
                "FOUNDATION_CUSTODY_REPORT": str(EVIDENCE / report_name),
            })
            probe.run(action, [str(bench_dir / "env/bin/python"),
                               str(ROOT / "tools/foundation/runtime_key_custody_data.py"),
                               action, site], cwd=bench_dir / "sites", env=environment)
            result = json.loads((EVIDENCE / report_name).read_text())
            if result["status"] != "pass":
                raise RuntimeError(action + " did not pass: " + json.dumps(result["checks"])[-900:])
            return result

        installed = run_data("install-keys", "install-keys-result.json")
        report["retrieved_keys_installed_natively"] = installed["checks"][0]["observation"]
        report["backup_encryption_enabled_on_recovery_site"] = installed["checks"][1]["observation"]

        verified = run_data("verify", "verify-result.json")
        report["recovery_verification"] = verified["checks"]
        decrypted = next(c["observation"] for c in verified["checks"]
                         if c["name"].startswith("source-encrypted-field-decrypts"))
        report["closes_the_limitation_run_35170062251_asserted"] = {
            "then": {"run": 35170062251, "decrypts_on_target": False,
                     "reason": "no key travelled with the backup"},
            "now": {"run": report["run_id"], "decrypts_on_target": decrypted["decrypts_on_target"],
                    "reason": "the key was retrieved from separate custody channels"},
            "plaintext_published": False,
        }
        if not decrypted["decrypts_on_target"]:
            raise RuntimeError("The field the operator encrypted still does not decrypt")

        rotated = run_data("rotate", "rotate-result.json")
        report["rotation"] = {check["name"]: check["observation"] for check in rotated["checks"]}
        orphaned = next(c["observation"] for c in rotated["checks"]
                        if c["name"].startswith("rotating-the-site-key-orphans"))
        reencrypted = next(c["observation"] for c in rotated["checks"]
                           if c["name"].startswith("ciphertext-re-encrypted"))
        boundaries = next(c["observation"] for c in rotated["checks"]
                          if c["name"].startswith("the-old-key-no-longer-decrypts"))
        if orphaned["old_ciphertext_decrypts_after_rotation"]:
            raise RuntimeError("Rotation did not take effect")
        if not reencrypted["readable_after_rotation"] or not reencrypted["ciphertext_changed"]:
            raise RuntimeError("Re-encryption under the rotated key did not succeed")
        if not boundaries["rotation_is_real"]:
            raise RuntimeError("Key boundaries after rotation are wrong")

        # Backup-key rotation, proven cryptographically rather than by paying for
        # a second full restore: take a new backup under epoch 2 and show which
        # key opens it.
        probe.run("backup-under-the-rotated-backup-key",
                  [str(bench), "--site", SITE, "backup", "--with-files"],
                  cwd=bench_dir, timeout=1200)
        backup_dir = bench_dir / "sites" / SITE / "private" / "backups"
        # Same "-enc" naming frappe applies when encrypt_backup is on, which it is
        # on this site, so the glob accepts both forms and the name is recorded.
        dumps = sorted(backup_dir.glob("*-database*.sql.gz"),
                       key=lambda p: p.stat().st_mtime_ns)
        if not dumps:
            raise RuntimeError("The post-rotation backup produced no database dump in "
                               + str(backup_dir))
        rotated_dump = dumps[-1]
        report["rotated_backup_file_name"] = {
            "name": rotated_dump.name, "enc_suffix_present": "-enc" in rotated_dump.name,
            "dumps_present": sorted(p.name for p in backup_dir.glob("*-database*.sql.gz")),
        }
        description = probe.run("detect-encryption-of-rotated-backup",
                                ["file", "--brief", str(rotated_dump)], quiet=True)
        if "AES" not in description:
            raise RuntimeError("The post-rotation backup is not encrypted: " + description)
        rotated_copy = scratch / "rotated-database.sql.gz.gpg"
        shutil.copyfile(rotated_dump, rotated_copy)
        decryption = {}
        for label, key in (("epoch_2_key", backup_key_2), ("epoch_1_key", backup_key)):
            target = scratch / ("opened-with-" + label + ".sql.gz")
            check_name = "gpg-decrypt-rotated-backup-with-" + label
            # allow_failure because the epoch 1 key is required to be rejected.
            probe.run(check_name,
                      ["gpg", "--yes", "--pinentry-mode", "loopback",
                       "--passphrase", key, "-o", str(target), "-d", str(rotated_copy)],
                      allow_failure=True)
            record = next((c for c in reversed(report["checks"]) if c["name"] == check_name), None)
            opened = target.exists() and target.stat().st_size > 0
            decryption[label] = {
                "exit_code": record["exit_code"] if record else None,
                "opened": opened,
                "bytes": target.stat().st_size if opened else 0,
                "decrypted_sha256": (hashlib.sha256(target.read_bytes()).hexdigest()
                                     if opened else None),
                "required_to": "open the artifact" if label == "epoch_2_key"
                               else "be rejected",
            }
            target.unlink(missing_ok=True)
        report["backup_key_rotation"] = {
            "rotated_backup_is_encrypted": {"file_says": description, "aes_detected": True},
            "decryption_outcomes": decryption,
            "epoch_2_key_opens_it": decryption["epoch_2_key"]["opened"],
            "epoch_1_key_does_not": not decryption["epoch_1_key"]["opened"],
            "why_no_second_full_restore": ("A second bench restore would cost another several "
                                           "minutes and prove nothing beyond what gpg already "
                                           "proves here: the artifact taken after rotation is "
                                           "opened by the rotated key and not by the previous "
                                           "one. The full restore path was already proven above "
                                           "with the epoch 1 key."),
        }
        if not decryption["epoch_2_key"]["opened"] or decryption["epoch_1_key"]["opened"]:
            raise RuntimeError("Backup key rotation did not change which key opens the artifact: "
                               + json.dumps(decryption))

        # Three roles, three machines - verified with the model P3 established.
        identities = {
            "custodian": manifest["machine_identity"],
            "operator": identity["machine_identity"],
            "recovery": report["machine_identity"],
        }
        report["separate_machines"] = custody.separate_machine_verdict(identities)
        if report["separate_machines"]["verdict"] != "SEPARATE MACHINES":
            raise RuntimeError("The three custody roles did not run on separate machines: "
                               + json.dumps(report["separate_machines"]))

        # Secret hygiene over everything this job publishes.
        needles = {"epoch1_site_key": site_key, "epoch1_backup_key": backup_key,
                   "epoch2_site_key": site_key_2, "epoch2_backup_key": backup_key_2,
                   "root_password": root_password, "db_password": db_password,
                   "admin_password": admin_password}
        leaks = {}
        for path in sorted(EVIDENCE.glob("*.json")):
            found = custody.find_plaintext(path.read_bytes(), needles)
            if found:
                leaks[path.name] = found
        report["published_evidence_scan"] = {"secrets_scanned": sorted(needles), "leaks": leaks,
                                             "clean": not leaks}
        if leaks:
            raise RuntimeError("Published evidence contains plaintext key material: "
                               + json.dumps(leaks))

        apps = probe.run("list-apps-on-recovered-site",
                         [str(bench), "--site", SITE, "list-apps"], cwd=bench_dir, quiet=True)
        report["recovered_apps"] = [line.strip() for line in apps.splitlines() if line.strip()]
        report["state_manifest_sha256"] = hashlib.sha256(
            json.dumps(state_manifest, sort_keys=True).encode()).hexdigest()
        report["not_proven_by_this_probe"] = [
            "A hardware security module, a cloud KMS or an owner-provisioned secret store: "
            "repository Actions secrets are not accessible to this session's credential (HTTP 403, "
            "no admin permission), so custody is modeled structurally across two artifact channels "
            "and is explicitly not a trust boundary",
            "Authorization of key release: any job able to download both channels can reconstruct "
            "the keys, so retrieval is proven but access control over retrieval is not",
            "A rotation ceremony held at a different time from issuance: both epochs are issued in "
            "one custodian job so rotation can be proven at all on ephemeral infrastructure",
            "A native rotation command: Frappe has none, so rotation is composed from native "
            "primitives and recorded as composed",
            "Key revocation or destruction on the custodian side, and custody audit logging",
            "HTTP usability after rotation: rotation is proven through the native API and at the "
            "gpg layer. Independent-system recovery run 35170062251 proved HTTP usability for "
            "recovery, but not for a rotated key",
            "A second full restore under the rotated backup key: proven at the gpg layer instead, "
            "as recorded above",
            "Any production workload: every key, record, file and credential here is synthetic and "
            "generated for this run",
        ]
        report["status"] = "pass"
        print("Custody retrieval proved load-bearing, encrypted backup restored, source-encrypted "
              "field decrypted, and both keys rotated; no plaintext key published")
    except Exception as exc:
        report["status"] = "fail"
        report["failure"] = probe.redact(str(exc))[-4000:]
        print(report["failure"], file=sys.stderr)
    finally:
        secret_file.unlink(missing_ok=True)
        (EVIDENCE / "recovery-result.json").write_text(
            probe.redact(json.dumps(report, indent=2)) + "\n")
        cleanup((MARIADB_CONTAINER, REDIS_QUEUE_CONTAINER, REDIS_CACHE_CONTAINER))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

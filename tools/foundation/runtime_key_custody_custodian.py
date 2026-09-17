"""Custodian role of external key custody: issue, split and publish key material.

Runs on its own ephemeral hosted runner and deliberately does **not** build the
product stack. A key custodian that has to install Bench, MariaDB and the
application before it can hold a key is not a separate control, so this role is
standard library only: it generates the two native keys Frappe uses, splits each
into two shares, publishes the shares as two separate artifacts plus a non-secret
manifest of fingerprints, and destroys its plaintext copies.

The two keys are issued for two epochs each. Epoch 1 is what the operator runs
its site with; epoch 2 is the rotation target the recovery system must retrieve
and apply later. Issuing both in one ceremony is a scope limit and is recorded as
one: a real rotation is a separate ceremony at a separate time, and this rehearsal
compresses the two so that rotation can be proven at all on ephemeral
infrastructure.

Nothing published here is a key. The manifest holds SHA-256 fingerprints, and each
channel holds one share of a one-time-pad split, which is indistinguishable from
random on its own. Every published file is scanned for plaintext key material
before the job ends, and the scan fails the job rather than warning.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from bench_bootstrap import Probe, machine_identity, require_hosted_runner  # noqa: E402
import key_custody as custody  # noqa: E402

OUTPUT = ROOT / ".foundation/key-custody"
EVIDENCE = ROOT / ".foundation/key-custody-evidence"
CHANNELS = ("a", "b")
EPOCHS = (1, 2)
PURPOSE = {
    custody.SITE_KEY: ("Protects secrets stored in __Auth (Fernet). Read natively through "
                       "frappe.utils.password.get_encryption_key()."),
    custody.BACKUP_KEY: ("Protects the backup artifacts at rest. Used natively by bench backup "
                         "when System Settings encrypt_backup is on, and by bench restore "
                         "--encryption-key."),
}
ROTATION_PURPOSE = {
    custody.SITE_KEY: ("Rotation target for the site key: after rotation, ciphertext written "
                       "under epoch 1 must be re-encrypted natively before it can be read."),
    custody.BACKUP_KEY: ("Rotation target for the backup key: a backup taken under epoch 2 must "
                         "not decrypt with the epoch 1 key."),
}


def main() -> int:
    require_hosted_runner()
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    for channel in CHANNELS:
        (OUTPUT / ("channel-" + channel)).mkdir(parents=True)
    (OUTPUT / "manifest").mkdir(parents=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    lab = Path(os.environ["RUNNER_TEMP"]) / "foundation-key-custody-custodian"
    lab.mkdir(mode=0o700, parents=True, exist_ok=True)

    report = {
        "artifact_name": "custodian-result.json",
        "scope": ("External key custody: issuance and splitting of the two native Frappe keys for "
                  "two epochs, on a machine that never builds the product stack and never sees a "
                  "site or a backup"),
        "role": "custodian",
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "commit": os.environ.get("GITHUB_SHA"),
        "ref": os.environ.get("GITHUB_REF"),
        "status": "running",
        "checks": [],
        "mocks_or_simulations_used": False,
    }
    probe = Probe(report, EVIDENCE, lab)
    report["machine_identity"] = machine_identity()

    def check(name, fn):
        try:
            observation = fn()
            report["checks"].append({"name": name, "status": "pass", "observation": observation})
            (EVIDENCE / "custodian-result.json").write_text(json.dumps(report, indent=2) + "\n")
            return observation
        except Exception as exc:
            report["checks"].append({"name": name, "status": "fail",
                                     "exception": type(exc).__name__,
                                     "message": probe.redact(str(exc))[:600]})
            report["status"] = "fail"
            report["failure"] = name + ": " + type(exc).__name__
            (EVIDENCE / "custodian-result.json").write_text(json.dumps(report, indent=2) + "\n")
            raise

    # Generated keys are masked in the Actions log the moment they exist, so a
    # stray echo cannot leak one. They are never written to any file.
    issued = {}
    for epoch in EPOCHS:
        for role_key in custody.KEY_ROLES:
            key = custody.generate_native_key()
            probe.mask(key)
            issued[(epoch, role_key)] = key
    plaintext_labels = {f"key-epoch{epoch}-{role_key}": key
                        for (epoch, role_key), key in issued.items()}

    def _custodian_is_separate_from_the_product_stack():
        # A custody control must not depend on the thing it holds keys for.
        return {
            "frappe_imported": "frappe" in sys.modules,
            "bench_present_on_this_machine": shutil.which("bench") is not None,
            "docker_invoked": False,
            "database_started": False,
            "site_created": False,
            "stdlib_only": "frappe" not in sys.modules and shutil.which("bench") is None,
        }

    observed = check("custodian-runs-without-the-product-stack",
                     _custodian_is_separate_from_the_product_stack)
    if not observed["stdlib_only"]:
        raise RuntimeError("The custodian role must not have the product stack available")

    def _keys_are_native_format():
        return {f"epoch{epoch}-{role_key}": custody.validate_key_format(key)
                for (epoch, role_key), key in sorted(issued.items())}

    formats = check("keys-issued-in-native-fernet-format", _keys_are_native_format)
    for label, validation in formats.items():
        if not validation["valid"]:
            raise RuntimeError("Issued key is not usable by Frappe: " + label + " "
                               + str(validation["reason"]))

    def _keys_are_safe_to_hand_to_gpg_unquoted():
        """Frappe passes the backup key to gpg on a command line, unquoted.

        A key beginning with '-' would be parsed as an option, gpg would fail, and
        frappe catches that failure, prints 'Files are stored without encryption'
        and carries on - leaving a plaintext backup under an '-enc' filename. The
        generator refuses such keys; this records that every issued key is safe,
        so the control is proved rather than assumed.
        """
        observed = {}
        for (epoch, role_key), key in sorted(issued.items()):
            safety = custody.command_line_safety(key)
            observed[f"epoch{epoch}-{role_key}"] = safety
            if not safety["safe_to_pass_unquoted"]:
                raise AssertionError(
                    "An issued key cannot be passed to gpg unquoted: "
                    + f"epoch{epoch}-{role_key} " + json.dumps(safety))
        return observed

    check("keys-issued-are-safe-to-pass-to-gpg-unquoted",
          _keys_are_safe_to_hand_to_gpg_unquoted)

    shares = {}
    for (epoch, role_key), key in issued.items():
        shares[(epoch, role_key)] = custody.split_key(key)

    def _neither_share_reveals_its_key():
        return {f"epoch{epoch}-{role_key}": custody.share_reveals_nothing(
                    issued[(epoch, role_key)], shares[(epoch, role_key)])
                for (epoch, role_key) in sorted(shares)}

    reveals = check("neither-share-reveals-the-key-it-hides", _neither_share_reveals_its_key)
    for label, observation in reveals.items():
        if not observation["neither_share_reveals_the_key"]:
            raise RuntimeError("A share reveals its key: " + label)

    def _both_shares_reconstruct():
        return {f"epoch{epoch}-{role_key}": custody.reconstruction_report(
                    shares[(epoch, role_key)]["share_a"], shares[(epoch, role_key)]["share_b"],
                    shares[(epoch, role_key)]["fingerprint"])
                for (epoch, role_key) in sorted(shares)}

    rebuilt = check("both-shares-together-reconstruct-the-issued-key", _both_shares_reconstruct)
    for label, result in rebuilt.items():
        if not result["fingerprint_matches"]:
            raise RuntimeError("Reconstruction from both shares failed: " + label)

    def _one_share_is_not_enough():
        observation = {}
        for (epoch, role_key), split in sorted(shares.items()):
            label = f"epoch{epoch}-{role_key}"
            observation[label] = {
                "share_a_alone": custody.reconstruction_report(
                    split["share_a"], split["share_a"], split["fingerprint"]),
                "share_b_alone": custody.reconstruction_report(
                    split["share_b"], split["share_b"], split["fingerprint"]),
            }
        return observation

    alone = check("a-single-share-does-not-reconstruct-the-key", _one_share_is_not_enough)
    for label, result in alone.items():
        for which in ("share_a_alone", "share_b_alone"):
            if result[which]["fingerprint_matches"]:
                raise RuntimeError("One share alone reconstructed the key: " + label + " " + which)

    def _epochs_are_bound_to_their_shares():
        observation = {}
        for role_key in custody.KEY_ROLES:
            first, second = shares[(1, role_key)], shares[(2, role_key)]
            observation[role_key] = {
                "epoch1_share_a_with_epoch2_share_b": custody.reconstruction_report(
                    first["share_a"], second["share_b"], first["fingerprint"]),
                "epoch2_share_a_with_epoch1_share_b": custody.reconstruction_report(
                    second["share_a"], first["share_b"], second["fingerprint"]),
            }
        return observation

    crossed = check("shares-from-different-epochs-do-not-reconstruct",
                    _epochs_are_bound_to_their_shares)
    for role_key, result in crossed.items():
        for which, report_line in result.items():
            if report_line["fingerprint_matches"]:
                raise RuntimeError("Cross-epoch shares reconstructed a key: " + role_key + " "
                                   + which)

    # Publish: one file per channel per epoch/role, plus a manifest that carries
    # fingerprints only. Two channels means two separately named artifacts, so a
    # consumer that receives one of them cannot reconstruct anything.
    published = {}
    entries = []
    for epoch in EPOCHS:
        for role_key in custody.KEY_ROLES:
            split = shares[(epoch, role_key)]
            entries.append(custody.epoch_entry(
                epoch, role_key, split,
                purpose=PURPOSE[role_key] if epoch == 1 else ROTATION_PURPOSE[role_key],
                rotated_from=(shares[(epoch - 1, role_key)]["fingerprint"] if epoch > 1 else None)))
            for channel in CHANNELS:
                name = f"epoch{epoch}-{role_key}.json"
                path = OUTPUT / ("channel-" + channel) / name
                path.write_text(custody.as_json({
                    "schema": "foundation-key-custody-share/1",
                    "channel": channel,
                    "epoch": epoch,
                    "key_role": role_key,
                    "share": split["share_" + channel],
                    "fingerprint": split["fingerprint"],
                    "split_method": custody.SPLIT_METHOD,
                }))
                published[(channel, epoch, role_key)] = path
    manifest = custody.custody_manifest(
        entries, run_id=report["run_id"], commit=report["commit"], role="custodian")
    manifest["machine_identity"] = report["machine_identity"]
    manifest["epochs_issued"] = list(EPOCHS)
    manifest["rotation_lineage"] = {
        role_key: {"epoch1": shares[(1, role_key)]["fingerprint"],
                   "epoch2": shares[(2, role_key)]["fingerprint"],
                   "keys_differ": shares[(1, role_key)]["fingerprint"]
                   != shares[(2, role_key)]["fingerprint"]}
        for role_key in custody.KEY_ROLES}
    manifest_path = OUTPUT / "manifest" / "custody-manifest.json"
    manifest_path.write_text(custody.as_json(manifest))

    def _manifest_carries_no_key_material():
        text = manifest_path.read_text()
        leaked = custody.find_plaintext(text, dict(
            plaintext_labels,
            **{f"share-{channel}-epoch{epoch}-{role_key}": shares[(epoch, role_key)]["share_" + channel]
               for channel in CHANNELS for (epoch, role_key) in sorted(shares)}))
        return {"manifest_bytes": len(text.encode()), "plaintext_found": leaked,
                "entries": len(manifest["entries"]),
                "fingerprints_only": not leaked}

    observed = check("published-manifest-carries-fingerprints-and-no-key-material",
                     _manifest_carries_no_key_material)
    if observed["plaintext_found"]:
        raise RuntimeError("The manifest leaked key material: "
                           + json.dumps(observed["plaintext_found"]))

    def _each_channel_holds_only_its_own_shares():
        observation = {}
        for channel in CHANNELS:
            other = "b" if channel == "a" else "a"
            blob = "".join((OUTPUT / ("channel-" + channel) / name).read_text()
                           for name in sorted(os.listdir(OUTPUT / ("channel-" + channel))))
            foreign = {f"other-channel-share-epoch{epoch}-{role_key}":
                       shares[(epoch, role_key)]["share_" + other]
                       for (epoch, role_key) in sorted(shares)}
            observation["channel-" + channel] = {
                "files": sorted(os.listdir(OUTPUT / ("channel-" + channel))),
                "plaintext_keys_found": custody.find_plaintext(blob, plaintext_labels),
                "other_channel_shares_found": custody.find_plaintext(blob, foreign),
                "own_shares_present": all(
                    shares[(epoch, role_key)]["share_" + channel] in blob
                    for (epoch, role_key) in sorted(shares)),
            }
        return observation

    observed = check("each-channel-holds-only-its-own-shares", _each_channel_holds_only_its_own_shares)
    for channel, result in observed.items():
        if result["plaintext_keys_found"] or result["other_channel_shares_found"]:
            raise RuntimeError("Channel " + channel + " holds material it must not: "
                               + json.dumps(result))
        if not result["own_shares_present"]:
            raise RuntimeError("Channel " + channel + " is missing one of its own shares")

    def _no_plaintext_key_anywhere_on_this_machine():
        # Walk everything this job wrote, plus its scratch directory, and look for
        # any issued key in plaintext. Shares are expected; keys are not.
        hits = []
        for root in (ROOT / ".foundation", lab):
            for path in sorted(Path(root).rglob("*")):
                if not path.is_file():
                    continue
                try:
                    blob = path.read_bytes()
                except OSError:
                    continue
                found = custody.find_plaintext(blob, plaintext_labels)
                if found:
                    hits.append({"path": str(path.relative_to(ROOT)) if ROOT in path.parents
                                 else str(path), "found": found})
        return {"files_scanned_root": str(ROOT / ".foundation"), "hits": hits,
                "clean": not hits}

    observed = check("no-plaintext-key-was-written-to-disk", _no_plaintext_key_anywhere_on_this_machine)
    if not observed["clean"]:
        raise RuntimeError("Plaintext key material reached disk: " + json.dumps(observed["hits"]))

    # Drop the plaintext bindings. This cannot be proven to have erased memory -
    # CPython gives no such guarantee - so the claim is limited to what is true
    # and checkable: no plaintext key was ever written to a file, and the machine
    # is destroyed when the job ends.
    for key in list(issued):
        del issued[key]
    report["plaintext_key_destruction"] = {
        "in_memory_bindings_dropped": True,
        "erasure_provable": False,
        "reason": ("CPython gives no memory-erasure guarantee, so this is recorded as a limit "
                   "rather than claimed as a property. What is proven is that no plaintext key was "
                   "written to any file, that only shares persist, and that this virtual machine "
                   "is destroyed when the job ends."),
        "vm_destroyed_at_job_end": True,
    }

    report["issued_keys"] = {
        f"epoch{epoch}-{role_key}": {
            "fingerprint": shares[(epoch, role_key)]["fingerprint"],
            "format": custody.validate_key_format(
                custody.reconstruct_key(shares[(epoch, role_key)]["share_a"],
                                        shares[(epoch, role_key)]["share_b"])),
            "channel_a_file": str(published[("a", epoch, role_key)].relative_to(ROOT)),
            "channel_b_file": str(published[("b", epoch, role_key)].relative_to(ROOT)),
        } for epoch in EPOCHS for role_key in custody.KEY_ROLES}
    report["manifest"] = {
        "path": str(manifest_path.relative_to(ROOT)),
        "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "bytes": manifest_path.stat().st_size,
        "epochs": list(EPOCHS),
        "rotation_lineage": manifest["rotation_lineage"],
    }
    report["channels"] = {
        "channel-" + channel: {
            "files": sorted(os.listdir(OUTPUT / ("channel-" + channel))),
            "sha256": {name: hashlib.sha256(
                (OUTPUT / ("channel-" + channel) / name).read_bytes()).hexdigest()
                for name in sorted(os.listdir(OUTPUT / ("channel-" + channel)))},
        } for channel in CHANNELS}
    report["custody_model"] = {
        "split_method": custody.SPLIT_METHOD,
        "channels": list(CHANNELS),
        "reconstruction_requires": "both channels",
        "separation_is_structural_not_a_trust_boundary": True,
        "reason": ("Both channels live in the same artifact system, so an adversary who can read "
                   "both can reconstruct the key. What is proven is that the backup alone yields "
                   "no key, that neither channel alone yields a key, and that retrieval from "
                   "custody is what makes restoration possible. A production custodian must be a "
                   "KMS, an HSM or an owner-provisioned secret store."),
        "external_secret_store_available": False,
        "external_secret_store_status": ("ENVIRONMENT-BLOCKED: repository Actions secrets are not "
                                         "accessible to this session's credential (HTTP 403 "
                                         "Resource not accessible by integration; no admin "
                                         "permission), so a real external store could not be "
                                         "provisioned. Recorded rather than worked around by "
                                         "weakening the model."),
    }
    report["not_proven_by_this_probe"] = [
        "A hardware security module, a cloud KMS or an owner-provisioned secret store: none is "
        "accessible to this session, so custody is modeled structurally across two artifact "
        "channels and is explicitly not a trust boundary",
        "Key retrieval under authentication or authorization control: any job that can download "
        "both artifacts can reconstruct the keys, which is the limit above",
        "A rotation ceremony held at a different time from issuance: both epochs are issued in one "
        "job here so that rotation can be proven at all on ephemeral infrastructure",
        "Custody of a key that protects real customer data: every key here is generated for this "
        "run and every value it protects is synthetic",
        "Durability of the custody channels beyond the artifact retention window",
        "Anything about the site or the backup: this role never sees either",
    ]
    report["status"] = "pass"
    (EVIDENCE / "custodian-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Key custody issued " + str(len(entries)) + " keys across " + str(len(CHANNELS))
          + " channels; no plaintext key material published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

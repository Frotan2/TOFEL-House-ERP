"""Separately controlled key custody for the production-like harness.

Pure, dependency-free helpers shared by the three custody roles - the custodian
that issues key material, the operator that runs a site with it, and the recovery
system that must retrieve it before it can restore anything. Everything here is
stdlib only, so the custodian role needs no Bench, no database and no application
checkout: it is a key system, and a key system that has to build the product
before it can hold a key is not a separate control.

Why this exists. Independent-system recovery (run 35170062251) proved that a
destroyed site's database and files come back on a separate machine, and it
asserted one limitation as an expected failure: the field the source encrypted
was recovered intact but was undecryptable on the target, because no key
travelled. That was correct behaviour, not a defect - plaintext key material must
never ride along inside a backup - but it means recovery without key custody is
incomplete. This module is the custody half.

Two distinct native keys are held, because Frappe uses two:

``encryption_key``
    Protects secrets stored in ``__Auth`` (Fernet). ``frappe.utils.password``
    reads it through ``get_encryption_key()``, which generates it lazily and
    writes it with ``frappe.installer.update_site_config``. Losing it orphans
    every stored ciphertext; ``decrypt()`` says so in its own error text.

``backup_encryption_key``
    Protects the backup artifacts themselves. ``get_or_generate_backup_encryption_key()``
    generates it the same lazy way, and when System Settings ``encrypt_backup``
    is on, ``bench backup`` runs ``gpg --passphrase <key> -c`` over the database
    dump and both file tars. ``bench restore --encryption-key <key>`` decrypts
    them again. Note that ``restore`` detects encryption by running ``file`` and
    looking for ``AES``, and that the same key is then applied to the file tars -
    so passing ``--encryption-key`` against a backup that was never encrypted
    would try to gpg-decrypt plain tars. The probes therefore assert the AES
    detection before relying on it.

Custody model, and its honest limits. Key material is split into two shares with
a random mask (a one-time pad over the key bytes), and the two shares travel as
two separate artifacts. Reconstruction requires both, and a share from one epoch
combined with a share from another produces a key whose fingerprint does not
match - which the probes assert rather than assume. This is a *structural*
separation, executable on ephemeral CI infrastructure with no owner action: it
proves that the backup alone yields no key, that neither channel alone yields a
key, that retrieval from custody is what makes restoration possible, and that
rotation is real. It is NOT a trust boundary - both channels live in the same
artifact system, so anyone who can read both artifacts can reconstruct the key.
A production deployment needs a real custodian: a KMS or HSM, or an
owner-provisioned secret store. Repository secrets were checked and are not
accessible to this session's credential (HTTP 403, no admin permission), which is
recorded as ENVIRONMENT-BLOCKED rather than worked around by weakening the model.
"""
import base64
import binascii
import hashlib
import json
import os

# Frappe keys come from Fernet.generate_key(), which is exactly
# base64.urlsafe_b64encode(os.urandom(32)). Reproducing that with the standard
# library keeps the custodian role free of any application dependency, and the
# probes verify the result by handing it to Frappe's own Fernet construction.
KEY_BYTES = 32
KEY_CHARACTERS = 44
SPLIT_METHOD = "xor-one-time-pad-over-key-bytes"

SITE_KEY = "encryption_key"
BACKUP_KEY = "backup_encryption_key"
KEY_ROLES = (SITE_KEY, BACKUP_KEY)

# Recorded with every observation-only identifier, citing the runs that disproved
# them as discriminators. Never re-promote these to requirements.
OBSERVATION_ONLY = {
    "hostname": ("GitHub-hosted runners reuse generated hostnames across separate "
                 "ephemeral VMs; disproved as a discriminator by run 35143620884"),
    "docker_daemon_id": ("The runner image ships a pre-generated /etc/docker/key.json, so "
                         "separate VMs report one daemon id; disproved by run 35168111875"),
}


def generate_native_key():
    """A key in exactly the format ``Fernet.generate_key()`` produces.

    cryptography's ``Fernet.generate_key()`` is ``urlsafe_b64encode(urandom(32))``,
    and the url-safe alphabet includes ``-``, so a generated key can begin with
    one. That matters for the backup key: at the pinned revision frappe passes it
    to gpg unquoted - ``utils/backups.py backup_encryption()`` builds
    ``gpg --yes --passphrase {passphrase} --pinentry-mode loopback -c {path}`` -
    so a leading dash is parsed as an option, gpg fails, and frappe catches the
    error, prints "Files are stored without encryption" and continues. The result
    is a plaintext backup sitting under an ``-enc`` filename, which is the worst
    possible outcome for a control that exists to keep backups confidential.

    Rejecting a leading dash costs about 0.02 bits of entropy and removes a
    failure mode the framework itself does not guard against. The operator probe
    still asserts the artifacts are detected as AES by ``file``, so the guard here
    is defence in depth rather than the only thing standing between the run and a
    silently unencrypted backup.
    """
    while True:
        key = base64.urlsafe_b64encode(os.urandom(KEY_BYTES)).decode()
        if not key.startswith("-"):
            return key


SHELL_METACHARACTERS = " \t\n\"'`$\\|&;<>()*?[]{}!#~"


def command_line_safety(key):
    """Report whether a key can be handed to gpg on a command line unquoted.

    Frappe does exactly that with ``backup_encryption_key``, so this is a native
    interoperability requirement rather than a stylistic preference. Only a
    leading dash changes how the argument is parsed; ``-`` and ``_`` elsewhere and
    the trailing ``=`` padding are inert inside a single shell word.
    """
    text = str(key)
    metacharacters = sorted({character for character in text
                             if character in SHELL_METACHARACTERS})
    return {
        "leading_dash": text.startswith("-"),
        "shell_metacharacters": metacharacters,
        "safe_to_pass_unquoted": not text.startswith("-") and not metacharacters,
        "checked_because": (
            "frappe.utils.backups.backup_encryption() passes backup_encryption_key to gpg "
            "unquoted, and on failure prints 'Files are stored without encryption' and "
            "continues, so an unsafe key yields a plaintext backup under an -enc filename"),
    }


def validate_key_format(key):
    """Describe whether a string is a usable Frappe encryption key.

    Returns a report rather than raising, because "the custodian issued a
    malformed key" is evidence worth recording precisely, not an exception to be
    swallowed by a caller.
    """
    report = {"valid": False, "characters": None, "decoded_bytes": None, "reason": None}
    if not isinstance(key, str):
        report["reason"] = "key is not a string"
        return report
    report["characters"] = len(key)
    try:
        decoded = base64.urlsafe_b64decode(key.encode())
    except (binascii.Error, ValueError):
        report["reason"] = "key is not url-safe base64"
        return report
    report["decoded_bytes"] = len(decoded)
    if len(key) != KEY_CHARACTERS:
        report["reason"] = f"key is {len(key)} characters, Frappe keys are {KEY_CHARACTERS}"
        return report
    if len(decoded) != KEY_BYTES:
        report["reason"] = f"key decodes to {len(decoded)} bytes, Frappe keys are {KEY_BYTES}"
        return report
    if base64.urlsafe_b64encode(decoded).decode() != key:
        report["reason"] = "key is not the canonical encoding of its own bytes"
        return report
    report["valid"] = True
    return report


def key_fingerprint(key):
    """SHA-256 of the key string.

    Fingerprints are the only form of key material that may be published: they
    let two separate systems agree that they hold the same key without either of
    them revealing it.
    """
    return hashlib.sha256(key.encode()).hexdigest()


def _xor(left, right):
    if len(left) != len(right):
        raise ValueError("share lengths differ, so they cannot be combined")
    # strict=True is redundant with the check above and deliberately so: if that
    # check were ever removed, a silent truncation here would corrupt key shares
    # rather than fail. Key material must never be combined partially.
    return bytes(a ^ b for a, b in zip(left, right, strict=True))


def split_key(key):
    """Split a key into two shares, neither of which reveals it.

    The mask is fresh random bytes of the same length as the key, so share B is a
    one-time-pad ciphertext of the key and share A is the pad. Each is
    indistinguishable from random on its own, and the key itself appears in
    neither.
    """
    validation = validate_key_format(key)
    if not validation["valid"]:
        raise ValueError("refusing to split a malformed key: " + str(validation["reason"]))
    raw = base64.urlsafe_b64decode(key.encode())
    mask = os.urandom(len(raw))
    share_a = base64.urlsafe_b64encode(mask).decode()
    share_b = base64.urlsafe_b64encode(_xor(raw, mask)).decode()
    return {
        "method": SPLIT_METHOD,
        "share_a": share_a,
        "share_b": share_b,
        "fingerprint": key_fingerprint(key),
    }


def reconstruct_key(share_a, share_b):
    """Rebuild a key from both shares, or raise if either is unusable."""
    try:
        left = base64.urlsafe_b64decode(share_a.encode())
        right = base64.urlsafe_b64decode(share_b.encode())
    except (binascii.Error, ValueError, AttributeError) as exc:
        raise ValueError("a share is not url-safe base64: " + str(exc))
    return base64.urlsafe_b64encode(_xor(left, right)).decode()


def reconstruction_report(share_a, share_b, expected_fingerprint):
    """Reconstruct and verify against an expected fingerprint.

    Never raises on a fingerprint mismatch: a mismatch is the *expected* result
    of the negative controls (a single share, or shares from different epochs),
    and the caller must be able to record it.
    """
    try:
        key = reconstruct_key(share_a, share_b)
    except ValueError as exc:
        return {"reconstructed": False, "error": str(exc), "fingerprint": None,
                "fingerprint_matches": False}
    fingerprint = key_fingerprint(key)
    return {"reconstructed": True, "error": None, "fingerprint": fingerprint,
            "fingerprint_matches": fingerprint == expected_fingerprint}


def share_reveals_nothing(key, shares):
    """Assert, per share, that the key is not recoverable from it alone.

    Checks the properties that actually matter: neither share is the key, neither
    share has the same fingerprint as the key, neither contains the key as a
    substring, and the two shares differ from each other.
    """
    fingerprint = key_fingerprint(key)
    observation = {"fingerprint": fingerprint, "shares": {}}
    for name in ("share_a", "share_b"):
        share = shares[name]
        observation["shares"][name] = {
            "equals_key": share == key,
            "fingerprint_equals_key_fingerprint": key_fingerprint(share) == fingerprint,
            "contains_key": key in share,
            "characters": len(share),
        }
    observation["shares_differ_from_each_other"] = shares["share_a"] != shares["share_b"]
    observation["neither_share_reveals_the_key"] = all(
        not (value["equals_key"] or value["fingerprint_equals_key_fingerprint"]
             or value["contains_key"])
        for value in observation["shares"].values())
    return observation


def find_plaintext(haystack, secrets):
    """Report which of ``secrets`` appear in ``haystack``.

    ``haystack`` may be bytes or text; ``secrets`` maps a label to a value, so
    the report names what leaked instead of printing it. Values shorter than 8
    characters are refused, because a short needle produces meaningless matches.
    """
    if isinstance(haystack, bytes):
        try:
            haystack = haystack.decode("utf-8", "strict")
        except UnicodeDecodeError:
            haystack = haystack.decode("utf-8", "replace")
    found = []
    for label, value in secrets.items():
        if not value:
            continue
        if len(str(value)) < 8:
            raise ValueError("refusing to scan for a needle shorter than 8 characters: " + label)
        if str(value) in haystack:
            found.append(label)
    return found


def separate_machine_verdict(identities):
    """Verify that N roles ran on N separate machines.

    Applies the discriminator model that independent-system recovery proved out,
    including its two corrections: ``hostname`` and the Docker daemon id are
    recorded as observations only, each annotated with the run that disproved it
    as a discriminator, and a missing required identifier fails closed instead of
    silently weakening the verdict.
    """
    roles = sorted(identities)
    if len(roles) < 2:
        raise ValueError("at least two machine identities are required to compare")
    pairs = []
    for index, left in enumerate(roles):
        for right in roles[index + 1:]:
            a, b = identities[left], identities[right]
            pair = {"left": left, "right": right}
            for field, key in (("kernel_boot_id", "kernel_boot_id"),
                               ("runner_name", "runner_name")):
                first, second = a.get(key), b.get(key)
                pair[field] = {"left": first, "right": second,
                               "both_present": bool(first) and bool(second),
                               "differs": bool(first) and bool(second) and first != second}
            uuids = (a.get("dmi_product_uuid"), b.get("dmi_product_uuid"))
            pair["dmi_product_uuid"] = {
                "left": uuids[0], "right": uuids[1],
                "available": all(uuids), "differs": all(uuids) and uuids[0] != uuids[1]}
            pair["hostname"] = {"left": a.get("hostname"), "right": b.get("hostname"),
                                "matches": a.get("hostname") == b.get("hostname"),
                                "used_as_a_discriminator": False,
                                "role": "OBSERVATION ONLY", "note": OBSERVATION_ONLY["hostname"]}
            pair["docker_daemon_id"] = {
                "left": a.get("docker_daemon_id"), "right": b.get("docker_daemon_id"),
                "matches": (a.get("docker_daemon_id") is not None
                            and a.get("docker_daemon_id") == b.get("docker_daemon_id")),
                "used_as_a_discriminator": False,
                "role": "OBSERVATION ONLY", "note": OBSERVATION_ONLY["docker_daemon_id"]}
            pair["separate"] = all(pair[f]["differs"] for f in ("kernel_boot_id", "runner_name"))
            pairs.append(pair)
    missing = [f"{p['left']}/{p['right']}:{field}"
               for p in pairs for field in ("kernel_boot_id", "runner_name")
               if not p[field]["both_present"]]
    # ``dmi_product_uuid`` is only readable as root, so on a runner where no step
    # could read it there is nothing to corroborate. ``all([])`` is vacuously true,
    # which would report corroboration that never happened, so an empty comparison
    # set is reported as None alongside the number of pairs actually compared.
    comparisons = [p["dmi_product_uuid"]["differs"] for p in pairs
                   if p["dmi_product_uuid"]["available"]]
    return {
        "roles": roles,
        "pairs": pairs,
        "every_pair_separate": all(p["separate"] for p in pairs),
        "missing_required_identifiers": missing,
        "dmi_product_uuid_pairs_compared": len(comparisons),
        "corroborated_by_dmi_product_uuid": (all(comparisons) if comparisons else None),
        "verdict": ("SEPARATE MACHINES" if all(p["separate"] for p in pairs) and not missing
                    else "NOT PROVEN SEPARATE"),
    }


def custody_manifest(entries, *, run_id=None, commit=None, role="custodian"):
    """Build the non-secret manifest that accompanies the shares.

    Holds fingerprints, epochs and formats - never a key, never a share. Both
    consuming roles verify what they reconstruct against this manifest, so a
    manifest that accidentally carried key material would defeat the split; the
    probe scans it before publishing.
    """
    return {
        "schema": "foundation-key-custody-manifest/1",
        "role": role,
        "run_id": run_id,
        "commit": commit,
        "split_method": SPLIT_METHOD,
        "key_format": {"characters": KEY_CHARACTERS, "decoded_bytes": KEY_BYTES,
                       "compatible_with": "cryptography.fernet.Fernet.generate_key()"},
        "entries": entries,
        "contains_no_key_material": True,
    }


def epoch_entry(epoch, role_key, shares, *, purpose, rotated_from=None):
    """One issued key, described without revealing it."""
    return {
        "epoch": epoch,
        "key_role": role_key,
        "purpose": purpose,
        "fingerprint": shares["fingerprint"],
        "share_a_fingerprint": key_fingerprint(shares["share_a"]),
        "share_b_fingerprint": key_fingerprint(shares["share_b"]),
        "share_a_characters": len(shares["share_a"]),
        "share_b_characters": len(shares["share_b"]),
        "rotated_from": rotated_from,
    }


def as_json(value):
    """Canonical serialization used for every published custody file."""
    return json.dumps(value, indent=2, sort_keys=True) + "\n"

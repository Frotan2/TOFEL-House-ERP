"""Prove the native site encryption key survives backup -> restore.

Root cause this probe closes: Frappe writes ``encryption_key`` into
``sites/<site>/site_config.json`` *lazily*, on the first call to
``frappe.utils.password.get_encryption_key()``. ``bench new-site`` does not
create it. A site that has never encrypted anything therefore has no key, so a
backup taken before that point carries no key material and the restore silently
produces a site that cannot decrypt encrypted content.

The probe uses only native, application-supported mechanisms:
``get_encryption_key()`` to initialize, ``set_encrypted_password()`` to write a
native encrypted Password field, and ``get_decrypted_password()`` to read it
back. It records a SHA-256 *fingerprint* of the key so a restored site can be
compared against its source without ever moving key material into evidence.

The key and the plaintext secret are never printed, never written to the
evidence directory and never leave the private runner-temporary fingerprint
file. Only fingerprints, byte lengths and pass/fail results are reported.

``fingerprint_key`` and ``restore_key_into_config`` are pure module-level
functions so the hosted harness and the local regression tests exercise exactly
the same logic rather than a copy of it.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

# Sites this probe may touch on a disposable hosted runner. The source site is
# initialized before its first backup; restore/recovery sites are verified after
# a restore into a separate database.
ALLOWED = {
    ("initialize", "foundation.localhost"),
    ("prepare", "foundation.localhost"),
    ("verify", "restore.localhost"),
    ("verify", "recovery.localhost"),
}

SOURCE_SITE = "foundation.localhost"
FINGERPRINT_FILE = "site-encryption-key-fingerprint.json"


def fingerprint_key(key):
    """Return a SHA-256 fingerprint of a site encryption key.

    The key itself is never returned, printed or persisted. Raises rather than
    returning a sentinel, so a missing key cannot be mistaken for a valid one.
    """
    if not key or not isinstance(key, str):
        raise ValueError("site encryption key is missing or is not a string")
    return {"sha256": hashlib.sha256(key.encode()).hexdigest(), "key_length": len(key)}


def read_config_fingerprint(config_path):
    """Fingerprint the encryption key held in a site_config.json file."""
    config = json.loads(Path(config_path).read_text())
    return fingerprint_key(config.get("encryption_key"))


def restore_key_into_config(source_config, restore_config):
    """Fail-closed carry of the site encryption key into a restored site config.

    ``site_config.json`` is not SQL, so ``bench restore`` never carries the key
    across on its own. The previous harness code copied it only
    ``if "encryption_key" in original_config``, which silently no-oped whenever
    the source site had not yet generated a key and reported the omission as a
    passive observation instead of a failure. This function raises instead, so a
    missing key stops the run.

    Returns a new dict; it never mutates its inputs and never silently no-ops.
    """
    key = source_config.get("encryption_key")
    if not key or not isinstance(key, str):
        raise ValueError("source site had no encryption key at restore time")
    if not source_config.get("db_name") or not restore_config.get("db_name"):
        raise ValueError("both sites must declare a database name")
    if source_config["db_name"] == restore_config["db_name"]:
        raise ValueError("restore must target a different database")
    source_password = source_config.get("db_password")
    if source_password and source_password == restore_config.get("db_password"):
        raise ValueError("restore must not reuse the source database credentials")
    updated = dict(restore_config)
    updated["encryption_key"] = key
    return updated


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    site = sys.argv[2] if len(sys.argv) > 2 else ""
    # Guard first, before any application import: the probe must refuse on any
    # machine that is not a disposable hosted runner with an authorized site.
    if os.environ.get("GITHUB_ACTIONS") != "true" or (action, site) not in ALLOWED:
        raise SystemExit("Disposable hosted source/restore/recovery sites only")

    import frappe
    from frappe.utils.password import (
        get_decrypted_password,
        get_encryption_key,
        set_encrypted_password,
    )

    # Private, never published. Lives beside the captured-session file.
    private_dir = Path(os.environ["FOUNDATION_LAB"])
    fingerprint_file = private_dir / FINGERPRINT_FILE
    report_path = Path(os.environ["FOUNDATION_ENCRYPTION_KEY_REPORT"])
    result = {
        "scope": "Native site encryption key initialization and backup/restore survival; synthetic secret only",
        "action": action,
        "site": site,
        "status": "running",
        "checks": [],
    }

    def check(name, fn):
        try:
            observation = fn()
            result["checks"].append({"name": name, "status": "pass", "observation": observation})
            report_path.write_text(json.dumps(result, indent=2) + "\n")
            return observation
        except Exception as exc:  # fail closed; never report a partial pass
            result["checks"].append({
                "name": name, "status": "fail",
                "exception": type(exc).__name__, "message": str(exc)[:250],
            })
            result["status"] = "fail"
            report_path.write_text(json.dumps(result, indent=2) + "\n")
            raise

    def config_path():
        return Path.cwd() / site / "site_config.json"

    frappe.init(site=site, sites_path=str(Path.cwd()))
    try:
        frappe.connect()
        frappe.set_user("Administrator")

        if action == "initialize":
            def _initialize():
                # Native mechanism: the same call the application's own
                # after_install hook uses. Idempotent in Frappe - it returns the
                # existing key if one is already present.
                native_key = get_encryption_key()
                if not native_key:
                    raise AssertionError("native get_encryption_key() returned no key")
                digest = read_config_fingerprint(config_path())
                fingerprint_file.write_text(json.dumps({
                    "source_site": site, **digest,
                }) + "\n")
                fingerprint_file.chmod(0o600)
                return {**digest, "persisted_to_site_config": True,
                        "mechanism": "frappe.utils.password.get_encryption_key"}

            check("native-site-key-initialized-before-first-backup", _initialize)

        elif action == "prepare":
            def _prepare():
                digest = read_config_fingerprint(config_path())
                recorded = json.loads(fingerprint_file.read_text())
                if recorded["sha256"] != digest["sha256"]:
                    raise AssertionError("site key changed between initialize and prepare")
                # No API key is generated or enabled. This is an encrypted
                # Password-field fixture using an already masked synthetic
                # secret, not a real credential.
                secret = os.environ["FOUNDATION_TEST_PASSWORD"]
                assert not frappe.db.get_value("User", "Administrator", "api_key")
                set_encrypted_password("User", "Administrator", secret, "api_secret")
                frappe.db.commit()
                stored = frappe.db.get_value("User", "Administrator", "api_secret")
                if not stored or stored == secret:
                    raise AssertionError("Password field was not stored as ciphertext")
                if get_decrypted_password("User", "Administrator", "api_secret") != secret:
                    raise AssertionError("source site cannot decrypt its own encrypted field")
                ciphertext = hashlib.sha256(str(stored).encode()).hexdigest()
                # Record the ciphertext digest privately so `verify` can prove the
                # exact encrypted bytes survived the round trip - not merely that
                # some ciphertext happens to decrypt. Fernet output is randomized
                # per encryption, so a re-encrypted value would not match.
                fingerprint_file.write_text(json.dumps({
                    "source_site": site, **digest, "ciphertext_sha256": ciphertext,
                }) + "\n")
                fingerprint_file.chmod(0o600)
                return {
                    "encryption_key_sha256": digest["sha256"], "key_length": digest["key_length"],
                    "encrypted_field": "User.Administrator.api_secret",
                    "stored_as_ciphertext": True,
                    "ciphertext_sha256": ciphertext,
                    "source_decrypts_before_backup": True,
                }

            check("native-encrypted-fixture-written-before-backup", _prepare)

        else:  # verify
            def _verify():
                recorded = json.loads(fingerprint_file.read_text())
                digest = read_config_fingerprint(config_path())
                if digest["sha256"] != recorded["sha256"]:
                    raise AssertionError(
                        "restored site encryption key does not match the source fingerprint")
                secret = os.environ["FOUNDATION_TEST_PASSWORD"]
                if get_decrypted_password("User", "Administrator", "api_secret") != secret:
                    raise AssertionError(
                        "restored site cannot decrypt content encrypted before the backup")
                stored = frappe.db.get_value("User", "Administrator", "api_secret")
                ciphertext = hashlib.sha256(str(stored).encode()).hexdigest()
                if ciphertext != recorded.get("ciphertext_sha256"):
                    raise AssertionError(
                        "restored ciphertext is not the ciphertext written before the backup")
                if site == recorded["source_site"]:
                    raise AssertionError("verify must run on a restored site, not the source")
                return {
                    "restored_encryption_key_sha256": digest["sha256"],
                    "key_length": digest["key_length"],
                    "source_encryption_key_sha256": recorded["sha256"],
                    "fingerprint_matches_source": True,
                    "restored_site_is_not_source": True,
                    "encrypted_content_decrypts_after_restore": True,
                    "ciphertext_sha256": ciphertext,
                    "ciphertext_matches_source": True,
                }

            check("encryption-key-and-ciphertext-survived-restore", _verify)

        result["status"] = "pass"
        report_path.write_text(json.dumps(result, indent=2) + "\n")
        print("Native site encryption key " + action + " verified on " + site + "; key and secret omitted")
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()

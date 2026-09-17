"""Native key-custody operations, executed inside the Bench environment.

Four actions, each run as its own process so that no action can read a stale
``frappe.local.conf``:

``install-keys``
    Install keys retrieved from custody with ``frappe.installer.update_site_config``
    - the same native call ``get_encryption_key()`` uses when it generates a key
    lazily - and turn on System Settings ``encrypt_backup`` so ``bench backup``
    protects its own artifacts.

``create``
    Create synthetic state, including a native encrypted Password field, and write
    a manifest of digests. The manifest never holds a plaintext secret or a key.

``verify``
    Prove that the ciphertext survived backup and restore intact, and that it now
    decrypts because the key was retrieved from custody. This is the exact check
    that independent-system recovery (run 35170062251) asserted as an expected
    failure; here it must succeed.

``rotate``
    Rotate the site key to epoch 2 and prove the consequences natively: ciphertext
    written under epoch 1 stops decrypting, re-encrypting it through native
    primitives restores readability, and the new ciphertext does not decrypt under
    the old key. Frappe has no rotation command, so rotation is composed from
    native functions - ``decrypt(..., encryption_key=...)``, ``set_encrypted_password``
    and ``update_site_config`` - and that composition is recorded as composed, not
    as a native single command.

Two helpers are imported from the independent-recovery data probe rather than
duplicated, so both harnesses read ``__Auth`` ciphertext the same way.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

import key_custody as custody  # noqa: E402
from runtime_independent_data import AUTH_FIELD, stored_ciphertext  # noqa: E402

OPERATOR_SITE = "custody-operator.localhost"
RECOVERY_SITE = "custody-recovered.localhost"
NEGATIVE_SITE = "custody-negative.localhost"
ALLOWED = {
    ("install-keys", OPERATOR_SITE),
    ("create", OPERATOR_SITE),
    ("install-keys", RECOVERY_SITE),
    ("verify", RECOVERY_SITE),
    ("rotate", RECOVERY_SITE),
    ("install-keys", NEGATIVE_SITE),
}
RECORDS_PER_DOCTYPE = 6
PRIVATE_FILE = "key-custody-private.txt"
PUBLIC_FILE = "key-custody-public.txt"
DIGEST = lambda value: hashlib.sha256(str(value).encode()).hexdigest()


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    site = sys.argv[2] if len(sys.argv) > 2 else ""
    # Guard before importing the application, so this cannot run anywhere else.
    if os.environ.get("GITHUB_ACTIONS") != "true" or (action, site) not in ALLOWED:
        raise SystemExit("Disposable hosted key-custody sites only")

    import frappe
    from frappe.installer import update_site_config
    from frappe.utils.password import (decrypt, get_decrypted_password,
                                       get_encryption_key, set_encrypted_password)

    manifest_path = Path(os.environ["FOUNDATION_CUSTODY_MANIFEST"])
    report_path = Path(os.environ["FOUNDATION_CUSTODY_REPORT"])
    site_key = os.environ.get("FOUNDATION_CUSTODY_SITE_KEY")
    backup_key = os.environ.get("FOUNDATION_CUSTODY_BACKUP_KEY")
    site_key_2 = os.environ.get("FOUNDATION_CUSTODY_SITE_KEY_2")
    backup_key_2 = os.environ.get("FOUNDATION_CUSTODY_BACKUP_KEY_2")
    secret = os.environ.get("FOUNDATION_CUSTODY_SECRET")
    result = {
        "scope": ("Native key-custody operations on synthetic state; no real credentials or "
                  "business data"),
        "action": action, "site": site, "status": "running", "checks": [],
    }

    def write_result():
        # Redaction belt and braces: a report must never carry a key or a secret,
        # even if a check accidentally returns one.
        text = json.dumps(result, indent=2) + "\n"
        for value in (site_key, backup_key, site_key_2, backup_key_2, secret):
            if value:
                text = text.replace(value, "[REDACTED]")
        report_path.write_text(text)

    def check(name, fn):
        try:
            observation = fn()
            result["checks"].append({"name": name, "status": "pass", "observation": observation})
            write_result()
            return observation
        except Exception as exc:
            result["checks"].append({"name": name, "status": "fail",
                                     "exception": type(exc).__name__,
                                     "message": str(exc)[:400]})
            result["status"] = "fail"
            write_result()
            raise

    def config_on_disk():
        return json.loads((Path.cwd() / site / "site_config.json").read_text())

    frappe.init(site=site, sites_path=str(Path.cwd()))
    try:
        frappe.connect()
        frappe.set_user("Administrator")

        if action == "install-keys":
            if not site_key or not backup_key:
                raise AssertionError("Keys retrieved from custody were not supplied")

            def _install():
                # Nothing may be orphaned by this install. Two roles reach it with
                # different expectations, so the invariant is stated once and holds
                # for both: every Fernet-encrypted row that already exists must
                # decrypt under the key being installed.
                #
                # A freshly built site satisfies it vacuously: installer.py at the
                # pinned revision never writes encryption_key (zero mentions),
                # get_encryption_key() only generates one lazily on first use, and
                # user passwords - Administrator's included - are stored by
                # update_password() as bcrypt hashes with encrypted=0, so they are
                # not affected by the site key at all.
                #
                # A restored site satisfies it substantively: it holds the
                # ciphertext the operating system wrote under this same epoch 1
                # key, and if it did not decrypt, installing the key would
                # silently strand data this probe could not re-encrypt.
                rows = frappe.db.sql(
                    "SELECT `doctype`, `name`, `fieldname`, `password` FROM `__Auth`"
                    " WHERE `encrypted`=1")
                existing = len(rows)
                orphaned = []
                for row in rows:
                    try:
                        decrypt(str(row[3]), encryption_key=site_key)
                    except Exception as exc:
                        orphaned.append({"row": ".".join(str(part) for part in row[:3]),
                                         "error": type(exc).__name__})
                if orphaned:
                    raise AssertionError(
                        "Installing the key retrieved from custody would orphan existing "
                        "ciphertext: " + json.dumps(orphaned))
                # The native mechanism: get_encryption_key() writes a lazily
                # generated key through exactly this call, so installing a key
                # retrieved from custody uses the supported path rather than
                # editing site_config.json behind the application's back.
                update_site_config("encryption_key", site_key)
                update_site_config("backup_encryption_key", backup_key)
                on_disk = config_on_disk()
                if on_disk.get("encryption_key") != site_key:
                    raise AssertionError("Site key was not installed by update_site_config")
                if on_disk.get("backup_encryption_key") != backup_key:
                    raise AssertionError("Backup key was not installed by update_site_config")
                return {
                    "installed_with": "frappe.installer.update_site_config",
                    "site_key_fingerprint": hashlib.sha256(site_key.encode()).hexdigest(),
                    "backup_key_fingerprint": hashlib.sha256(backup_key.encode()).hexdigest(),
                    "frappe_generates_the_same_key_lazily": (
                        "frappe.utils.password.get_encryption_key() calls update_site_config with "
                        "a Fernet.generate_key() value, so a custodian-issued key is installed "
                        "through the same native path"),
                    "encrypted_auth_rows_before_install": existing,
                    "ciphertext_orphaned_by_the_install": 0,
                    "invariant": ("every pre-existing Fernet-encrypted __Auth row decrypts under "
                                  "the key being installed, so nothing is stranded; user "
                                  "passwords are bcrypt with encrypted=0 and are unaffected by "
                                  "the site key"),
                }

            check("custody-keys-installed-through-the-native-config-path", _install)

            def _enable_encrypted_backups():
                frappe.db.set_single_value("System Settings", "encrypt_backup", 1)
                frappe.db.commit()
                frappe.clear_cache()
                value = frappe.get_system_settings("encrypt_backup")
                if not int(value):
                    raise AssertionError("encrypt_backup did not take effect: " + str(value))
                return {"system_setting": "encrypt_backup", "value": int(value),
                        "effect": ("bench backup now runs gpg --passphrase <backup_encryption_key> "
                                   "-c over the database dump and both file tars"),
                        "field_is_native": "Check field on System Settings, default 0"}

            check("backup-encryption-enabled-through-native-system-settings",
                  _enable_encrypted_backups)

        elif action == "create":
            if not secret:
                raise AssertionError("No synthetic secret was supplied")

            def _create():
                created = {"doctypes": {}, "files": {}, "encrypted_field": {},
                           "key_fingerprints": {
                               "site_key": hashlib.sha256(site_key.encode()).hexdigest(),
                               "backup_key": hashlib.sha256(backup_key.encode()).hexdigest()}}
                first_todo = None
                for doctype in ("ToDo", "Note"):
                    names = []
                    for index in range(RECORDS_PER_DOCTYPE):
                        if doctype == "ToDo":
                            doc = frappe.get_doc({
                                "doctype": "ToDo",
                                "description": f"synthetic-key-custody-{index:03d}",
                                "status": "Open", "priority": "Medium", "reference_type": "",
                            })
                        else:
                            doc = frappe.get_doc({
                                "doctype": "Note",
                                "title": f"synthetic-key-custody-{index:03d}",
                                "public": 1,
                                "content": f"<p>synthetic custody body {index:03d}</p>",
                            })
                        doc.insert(ignore_permissions=True)
                        names.append(doc.name)
                    frappe.db.commit()
                    if doctype == "ToDo":
                        first_todo = names[0]
                    created["doctypes"][doctype] = {
                        "count": len(names),
                        "names_sha256": hashlib.sha256(
                            "\n".join(sorted(names)).encode()).hexdigest(),
                    }
                # The field that independent recovery could not decrypt without
                # custody. Plaintext is never recorded - only its digest, so the
                # recovery side can prove decryption without either side
                # publishing the value.
                get_encryption_key()
                set_encrypted_password("User", "Administrator", secret, "api_secret")
                frappe.db.commit()
                if get_decrypted_password("User", "Administrator", "api_secret") != secret:
                    raise AssertionError("The operator cannot read back what it encrypted")
                stored = str(stored_ciphertext(frappe.db, *AUTH_FIELD))
                created["encrypted_field"] = {
                    "field": "User.Administrator.api_secret",
                    "plaintext_sha256": hashlib.sha256(secret.encode()).hexdigest(),
                    "ciphertext_sha256": hashlib.sha256(stored.encode()).hexdigest(),
                    "encrypted_under_site_key_fingerprint":
                        hashlib.sha256(site_key.encode()).hexdigest(),
                    "decrypts_on_operator": True,
                }
                private_payload = "synthetic custody private content\n" + ("x" * 512) + "\n"
                public_payload = "synthetic custody public content\n" + ("y" * 512) + "\n"
                for file_name, payload, is_private in (
                        (PRIVATE_FILE, private_payload, 1), (PUBLIC_FILE, public_payload, 0)):
                    doc = frappe.get_doc({
                        "doctype": "File", "file_name": file_name, "content": payload,
                        "is_private": is_private,
                        "attached_to_doctype": "ToDo" if is_private else "",
                        "attached_to_name": first_todo if is_private else "",
                    }).insert(ignore_permissions=True)
                    frappe.db.commit()
                    absolute = Path.cwd() / site / (
                        "private/files" if is_private else "public/files") / file_name
                    if not absolute.exists():
                        raise AssertionError("File was not written to disk at " + str(absolute))
                    created["files"][file_name] = {
                        "file_url": doc.file_url, "is_private": is_private,
                        "on_disk_sha256": hashlib.sha256(absolute.read_bytes()).hexdigest(),
                        "bytes": absolute.stat().st_size,
                        "attached_to": doc.attached_to_name or None,
                    }
                manifest_path.write_text(json.dumps(created, indent=2) + "\n")
                return created

            check("synthetic-state-created-under-a-custodian-issued-key", _create)

        elif action == "verify":
            manifest = json.loads(manifest_path.read_text())

            def _ciphertext_intact():
                stored = str(stored_ciphertext(frappe.db, *AUTH_FIELD))
                digest = hashlib.sha256(stored.encode()).hexdigest()
                if digest != manifest["encrypted_field"]["ciphertext_sha256"]:
                    raise AssertionError("Ciphertext changed between the operator and recovery")
                return {"ciphertext_sha256": digest,
                        "matches_the_operators_record": True,
                        "survived_backup_restore": True}

            check("source-ciphertext-recovered-intact", _ciphertext_intact)

            def _key_retrieved_from_custody_is_installed():
                # Read through the native accessor first: Frappe creates the key
                # lazily, so reading site_config.json before any key access could
                # find nothing and mask the comparison.
                get_encryption_key()
                on_disk = config_on_disk()
                installed = hashlib.sha256(
                    str(on_disk.get("encryption_key", "")).encode()).hexdigest()
                expected = manifest["encrypted_field"]["encrypted_under_site_key_fingerprint"]
                if installed != expected:
                    raise AssertionError(
                        "The installed site key is not the one custody issued: "
                        + installed + " != " + expected)
                return {"installed_site_key_fingerprint": installed,
                        "matches_custody_fingerprint": True,
                        "backup_key_fingerprint": hashlib.sha256(
                            str(on_disk.get("backup_encryption_key", "")).encode()).hexdigest()}

            check("retrieved-key-material-is-installed-on-the-recovered-site",
                  _key_retrieved_from_custody_is_installed)

            def _decrypts_now():
                """The check independent recovery had to assert as a failure.

                Run 35170062251 proved the database and files come back on a
                separate machine while the source-encrypted field stays intact but
                undecryptable, because no key travelled. With the key retrieved
                from custody this must now succeed, and it is compared by digest so
                neither side publishes the plaintext.
                """
                plaintext = get_decrypted_password("User", "Administrator", "api_secret")
                digest = hashlib.sha256(str(plaintext).encode()).hexdigest()
                if digest != manifest["encrypted_field"]["plaintext_sha256"]:
                    raise AssertionError(
                        "Decrypted value does not match what the operator encrypted")
                return {"decrypts_on_target": True,
                        "plaintext_sha256_matches_the_operators_record": True,
                        "plaintext_published": False,
                        "closes": ("the limitation asserted by run 35170062251, where "
                                   "decrypts_on_target was false")}

            check("source-encrypted-field-decrypts-with-the-key-retrieved-from-custody",
                  _decrypts_now)

            def _records_and_files():
                observed = {}
                patterns = {"ToDo": ("description", "synthetic-key-custody-%"),
                            "Note": ("title", "synthetic-key-custody-%")}
                for doctype, expected in manifest["doctypes"].items():
                    field, pattern = patterns[doctype]
                    names = frappe.get_all(doctype, filters={field: ["like", pattern]},
                                           pluck="name", order_by=None)
                    if len(names) != expected["count"]:
                        raise AssertionError(
                            f"{doctype}: recovered {len(names)} of {expected['count']} records")
                    digest = hashlib.sha256("\n".join(sorted(names)).encode()).hexdigest()
                    if digest != expected["names_sha256"]:
                        raise AssertionError(doctype + ": recovered record names differ")
                    observed[doctype] = {"recovered": len(names), "names_sha256_matches": True}
                for file_name, expected in manifest["files"].items():
                    relative = (("private/files" if expected["is_private"] else "public/files")
                                + "/" + file_name)
                    absolute = Path.cwd() / site / relative
                    if not absolute.exists():
                        raise AssertionError("Recovered file is missing on disk: " + relative)
                    if hashlib.sha256(absolute.read_bytes()).hexdigest() != expected["on_disk_sha256"]:
                        raise AssertionError("Recovered file content differs: " + relative)
                    record = frappe.db.get_value("File", {"file_url": expected["file_url"]},
                                                 ["name", "is_private", "file_size"], as_dict=True)
                    if not record:
                        raise AssertionError("File document was not recovered: " + file_name)
                    observed[file_name] = {"bytes": absolute.stat().st_size,
                                           "on_disk_sha256_matches": True,
                                           "file_document_recovered": True,
                                           "is_private": int(record["is_private"])}
                return observed

            check("records-and-both-file-trees-recovered", _records_and_files)

        elif action == "rotate":
            manifest = json.loads(manifest_path.read_text())
            if not site_key_2:
                raise AssertionError("No epoch 2 key was supplied for rotation")

            def _rotation_orphans_the_old_ciphertext():
                """Step 1: rotate the key and show the native consequence.

                Frappe has no rotation command, and ``decrypt()`` says so in its
                own error text - it tells an operator who changed the key to
                restore the original ``site_config.json``. So the first honest
                observation after rotating is that existing ciphertext stops
                being readable.
                """
                update_site_config("encryption_key", site_key_2)
                # Refresh through the native accessor rather than rebuilding the
                # config by hand, so the rotated key is what Frappe itself sees.
                frappe.local.conf = frappe.get_conf()
                try:
                    get_decrypted_password("User", "Administrator", "api_secret")
                    still_decrypts = True
                    error = None
                except Exception as exc:
                    still_decrypts = False
                    error = type(exc).__name__ + ": " + str(exc)[:200]
                if still_decrypts:
                    raise AssertionError(
                        "Ciphertext still decrypted after the site key was rotated, which would "
                        "mean the rotation did not take effect")
                return {"rotated_to_fingerprint": hashlib.sha256(
                            site_key_2.encode()).hexdigest(),
                        "old_ciphertext_decrypts_after_rotation": False,
                        "native_error": error,
                        "why": ("Frappe has no key-rotation command; decrypt() itself tells an "
                                "operator who changed the key to restore the original "
                                "site_config.json, so orphaned ciphertext is the expected native "
                                "consequence of rotation without re-encryption")}

            check("rotating-the-site-key-orphans-ciphertext-written-under-the-old-key",
                  _rotation_orphans_the_old_ciphertext)

            def _reencrypt_natively():
                """Step 2: re-encrypt through native primitives.

                Composed, not a single native command: read the stored ciphertext,
                decrypt it with the explicitly supplied old key, and write it back
                so it is encrypted under the key now in site config.
                """
                old_ciphertext = str(stored_ciphertext(frappe.db, *AUTH_FIELD))
                plaintext = decrypt(old_ciphertext, encryption_key=site_key)
                if hashlib.sha256(str(plaintext).encode()).hexdigest() != \
                        manifest["encrypted_field"]["plaintext_sha256"]:
                    raise AssertionError(
                        "Re-encryption source plaintext does not match the operator's record")
                set_encrypted_password("User", "Administrator", plaintext, "api_secret")
                frappe.db.commit()
                new_ciphertext = str(stored_ciphertext(frappe.db, *AUTH_FIELD))
                readable = get_decrypted_password("User", "Administrator", "api_secret")
                if hashlib.sha256(str(readable).encode()).hexdigest() != \
                        manifest["encrypted_field"]["plaintext_sha256"]:
                    raise AssertionError("Value changed during re-encryption")
                result["rotated_ciphertext_sha256"] = hashlib.sha256(
                    new_ciphertext.encode()).hexdigest()
                return {"composed_from": ["frappe.utils.password.decrypt(encryption_key=old)",
                                          "frappe.utils.password.set_encrypted_password",
                                          "frappe.installer.update_site_config"],
                        "native_single_command_exists": False,
                        "old_ciphertext_sha256": manifest["encrypted_field"]["ciphertext_sha256"],
                        "new_ciphertext_sha256": hashlib.sha256(new_ciphertext.encode()).hexdigest(),
                        "ciphertext_changed": new_ciphertext != old_ciphertext,
                        "readable_after_rotation": True,
                        "plaintext_sha256_unchanged": True}

            observed = check("ciphertext-re-encrypted-under-the-new-key-through-native-primitives",
                             _reencrypt_natively)
            new_ciphertext_sha = observed["new_ciphertext_sha256"]

            def _old_key_no_longer_works():
                stored = str(stored_ciphertext(frappe.db, *AUTH_FIELD))
                outcomes = {}
                for label, key in (("epoch_1_key", site_key), ("epoch_2_key", site_key_2)):
                    try:
                        value = decrypt(stored, encryption_key=key)
                        outcomes[label] = {"decrypts": True,
                                           "plaintext_sha256_matches":
                                               hashlib.sha256(str(value).encode()).hexdigest()
                                               == manifest["encrypted_field"]["plaintext_sha256"]}
                    except Exception as exc:
                        outcomes[label] = {"decrypts": False, "error": type(exc).__name__}
                # A key nobody issued must not work either.
                stranger = custody.generate_native_key()
                try:
                    decrypt(stored, encryption_key=stranger)
                    outcomes["a_key_custody_never_issued"] = {"decrypts": True}
                except Exception as exc:
                    outcomes["a_key_custody_never_issued"] = {"decrypts": False,
                                                             "error": type(exc).__name__}
                if outcomes["epoch_1_key"]["decrypts"]:
                    raise AssertionError(
                        "The epoch 1 key still decrypts post-rotation ciphertext, so rotation "
                        "did not take effect")
                if not outcomes["epoch_2_key"]["decrypts"]:
                    raise AssertionError("The epoch 2 key cannot decrypt its own ciphertext")
                if outcomes["a_key_custody_never_issued"]["decrypts"]:
                    raise AssertionError("A key custody never issued decrypted the ciphertext")
                return {"post_rotation_ciphertext_sha256": new_ciphertext_sha,
                        "outcomes": outcomes,
                        "rotation_is_real": True}

            check("the-old-key-no-longer-decrypts-and-the-new-key-does", _old_key_no_longer_works)

            def _config_holds_the_new_key():
                on_disk = config_on_disk()
                return {"site_key_fingerprint": hashlib.sha256(
                            str(on_disk["encryption_key"]).encode()).hexdigest(),
                        "matches_epoch_2": hashlib.sha256(
                            str(on_disk["encryption_key"]).encode()).hexdigest()
                        == hashlib.sha256(site_key_2.encode()).hexdigest(),
                        "epoch_1_key_absent_from_config":
                            on_disk.get("encryption_key") != site_key}

            observed = check("site-config-holds-the-rotated-key", _config_holds_the_new_key)
            if not observed["matches_epoch_2"]:
                raise AssertionError("site_config does not hold the epoch 2 key")

            def _rotate_the_backup_key_too():
                """Step 3: rotate the backup key through the same native path.

                The proof that this took effect is cryptographic and happens in the
                probe: a backup taken after this step must open with the epoch 2
                key and not with the epoch 1 key.
                """
                if not backup_key_2:
                    raise AssertionError("No epoch 2 backup key was supplied for rotation")
                update_site_config("backup_encryption_key", backup_key_2)
                frappe.local.conf = frappe.get_conf()
                on_disk = config_on_disk()
                if on_disk.get("backup_encryption_key") != backup_key_2:
                    raise AssertionError("The backup key was not rotated in site_config")
                return {"installed_with": "frappe.installer.update_site_config",
                        "backup_key_fingerprint": hashlib.sha256(
                            backup_key_2.encode()).hexdigest(),
                        "epoch_1_backup_key_absent_from_config":
                            on_disk.get("backup_encryption_key") != backup_key,
                        "effect": ("the next bench backup passes this key to gpg, so the artifact "
                                   "it produces can only be opened with it"),
                        "proof_is_in_the_probe": ("the recovery probe takes a backup after this "
                                                  "step and shows gpg -d succeeds with epoch 2 and "
                                                  "fails with epoch 1")}

            check("backup-key-rotated-through-the-native-config-path",
                  _rotate_the_backup_key_too)

        result["status"] = "pass"
        write_result()
        print("Key-custody " + action + " completed on " + site + "; no key or secret emitted")
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()

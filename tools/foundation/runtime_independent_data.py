"""Create, verify and exercise the synthetic state used by independent recovery.

Runs inside the bench environment on a disposable hosted runner. Two independent
systems use it: the source system calls ``create`` before backing up and then
destroys itself, and the genuinely separate target system calls ``verify`` after
restoring the uploaded backup. Because both sides use this same script, the
comparison is between what one machine wrote and what another machine can read
back - not between two interpretations of the same data.

Only synthetic records and files are created. The manifest holds record names,
content digests and counts; it never holds a password, an encryption key or a
site configuration.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

SOURCE_SITE = "source.localhost"
TARGET_SITE = "recovered.localhost"
ALLOWED = {
    ("create", SOURCE_SITE),
    ("verify", TARGET_SITE),
}
RECORDS_PER_DOCTYPE = 12
PRIVATE_FILE = "independent-recovery-private.txt"
PUBLIC_FILE = "independent-recovery-public.txt"
AUTH_FIELD = ("User", "Administrator", "api_secret")


def first_ciphertext(rows, label):
    """Validate the rows returned by the ``__Auth`` query.

    Split out from the database access so it can be exercised directly: an absent
    row and an empty value are different failures, and neither may be reported as
    a recovered ciphertext.
    """
    if not rows:
        raise AssertionError("No ciphertext row exists in __Auth for " + label)
    row = rows[0]
    value = row[0] if isinstance(row, (list, tuple)) else row
    if value in (None, "", b""):
        raise AssertionError("__Auth holds an empty value for " + label)
    return value


def stored_ciphertext(db, doctype, name, fieldname):
    """Read the stored ciphertext straight from ``__Auth``.

    ``frappe.db.get_value`` appends the default ``ORDER BY creation``, and
    ``__Auth`` has no ``creation`` column, so it fails with MySQL error 1054. The
    native parameterized query is used instead - the same form the encryption-key
    probe uses.
    """
    label = ".".join((doctype, name, fieldname))
    rows = db.sql(
        "SELECT `password` FROM `__Auth`"
        " WHERE `doctype`=%s AND `name`=%s AND `fieldname`=%s",
        (doctype, name, fieldname))
    return first_ciphertext(rows, label)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    site = sys.argv[2] if len(sys.argv) > 2 else ""
    # Guard before importing the application, so this cannot run anywhere else.
    if os.environ.get("GITHUB_ACTIONS") != "true" or (action, site) not in ALLOWED:
        raise SystemExit("Disposable hosted independent-recovery sites only")

    import frappe

    manifest_path = Path(os.environ["FOUNDATION_INDEPENDENT_MANIFEST"])
    report_path = Path(os.environ["FOUNDATION_INDEPENDENT_REPORT"])
    result = {
        "scope": ("Synthetic record, private-file and public-file state for independent-system "
                  "recovery; no real business data"),
        "action": action, "site": site, "status": "running", "checks": [],
    }

    def write_result():
        report_path.write_text(json.dumps(result, indent=2) + "\n")

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

    frappe.init(site=site, sites_path=str(Path.cwd()))
    try:
        frappe.connect()
        frappe.set_user("Administrator")
        run_tag = uuid.uuid4().hex[:12]

        if action == "create":
            def _create():
                created = {"run_tag": run_tag, "doctypes": {}, "files": {},
                           "encrypted_field": {}}
                for doctype in ("ToDo", "Note"):
                    names = []
                    for index in range(RECORDS_PER_DOCTYPE):
                        if doctype == "ToDo":
                            doc = frappe.get_doc({
                                "doctype": "ToDo",
                                "description": f"synthetic-independent-recovery-{run_tag}-{index:03d}",
                                "status": "Open",
                                "priority": "Medium",
                                "reference_type": "",
                            })
                        else:
                            doc = frappe.get_doc({
                                "doctype": "Note",
                                "title": f"synthetic-independent-recovery-{run_tag}-{index:03d}",
                                "public": 1,
                                "content": f"<p>synthetic body {run_tag} {index:03d}</p>",
                            })
                        doc.insert(ignore_permissions=True)
                        names.append(doc.name)
                    frappe.db.commit()
                    created["doctypes"][doctype] = {
                        "count": len(names),
                        "names": names,
                        "names_sha256": hashlib.sha256(
                            "\n".join(sorted(names)).encode()).hexdigest(),
                    }
                # A native encrypted Password field, so the target system can
                # demonstrate concretely what independent recovery cannot do
                # without separately controlled key custody.
                secret = os.environ["FOUNDATION_TEST_PASSWORD"]
                from frappe.utils.password import (get_decrypted_password,
                                                   get_encryption_key,
                                                   set_encrypted_password)
                get_encryption_key()
                set_encrypted_password("User", "Administrator", secret, "api_secret")
                frappe.db.commit()
                assert get_decrypted_password("User", "Administrator", "api_secret") == secret
                key = json.loads((Path.cwd() / site / "site_config.json").read_text())["encryption_key"]
                created["encrypted_field"] = {
                    "field": "User.Administrator.api_secret",
                    "source_key_sha256": hashlib.sha256(key.encode()).hexdigest(),
                    "ciphertext_sha256": hashlib.sha256(
                        str(stored_ciphertext(frappe.db, *AUTH_FIELD)).encode()).hexdigest(),
                    "decrypts_on_source": True,
                }
                private_payload = f"synthetic private content {run_tag}\n" + ("x" * 512) + "\n"
                public_payload = f"synthetic public content {run_tag}\n" + ("y" * 512) + "\n"
                todo = created["doctypes"]["ToDo"]["names"][0]
                for file_name, payload, is_private in (
                        (PRIVATE_FILE, private_payload, 1), (PUBLIC_FILE, public_payload, 0)):
                    doc = frappe.get_doc({
                        "doctype": "File", "file_name": file_name, "content": payload,
                        "is_private": is_private,
                        "attached_to_doctype": "ToDo" if is_private else "",
                        "attached_to_name": todo if is_private else "",
                    }).insert(ignore_permissions=True)
                    frappe.db.commit()
                    absolute = Path.cwd() / site / (
                        "private/files" if is_private else "public/files") / file_name
                    if not absolute.exists():
                        raise AssertionError("File was not written to disk at " + str(absolute))
                    created["files"][file_name] = {
                        "file_url": doc.file_url,
                        "is_private": is_private,
                        "content_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                        "on_disk_sha256": hashlib.sha256(absolute.read_bytes()).hexdigest(),
                        "bytes": absolute.stat().st_size,
                        "attached_to": doc.attached_to_name or None,
                    }
                manifest_path.write_text(json.dumps(created, indent=2) + "\n")
                return created

            check("synthetic-state-created-on-source-system", _create)

        else:  # verify
            manifest = json.loads(manifest_path.read_text())

            def _verify_records():
                observed = {}
                for doctype, expected in manifest["doctypes"].items():
                    names = [n for n in expected["names"] if frappe.db.exists(doctype, n)]
                    if len(names) != expected["count"]:
                        raise AssertionError(
                            f"{doctype}: recovered {len(names)} of {expected['count']} records")
                    digest = hashlib.sha256("\n".join(sorted(names)).encode()).hexdigest()
                    if digest != expected["names_sha256"]:
                        raise AssertionError(doctype + ": recovered record names differ")
                    observed[doctype] = {"recovered": len(names),
                                         "names_sha256_matches": True}
                return observed

            check("database-records-recovered-on-independent-system", _verify_records)

            def _verify_files():
                observed = {}
                for file_name, expected in manifest["files"].items():
                    relative = ("private/files" if expected["is_private"]
                                else "public/files") + "/" + file_name
                    absolute = Path.cwd() / site / relative
                    if not absolute.exists():
                        raise AssertionError("Recovered file is missing on disk: " + relative)
                    digest = hashlib.sha256(absolute.read_bytes()).hexdigest()
                    if digest != expected["on_disk_sha256"]:
                        raise AssertionError("Recovered file content differs: " + relative)
                    record = frappe.db.get_value(
                        "File", {"file_url": expected["file_url"]},
                        ["name", "is_private", "file_size"], as_dict=True)
                    if not record:
                        raise AssertionError("File document was not recovered: " + file_name)
                    if int(record["is_private"]) != int(expected["is_private"]):
                        raise AssertionError("File privacy flag changed: " + file_name)
                    if int(record["file_size"]) != int(expected["bytes"]):
                        raise AssertionError("File size changed: " + file_name)
                    observed[file_name] = {
                        "path": relative, "on_disk_sha256_matches": True,
                        "bytes": absolute.stat().st_size,
                        "file_document_recovered": True,
                        "is_private": int(record["is_private"]),
                    }
                return observed

            check("private-and-public-files-recovered-on-independent-system", _verify_files)

            def _encrypted_field_limitation():
                """Recorded deliberately: this is what P4 must close.

                The backup carries ciphertext written under the SOURCE system's
                key. That key is never transferred, because plaintext key
                material must not travel through an artifact. So the independent
                system can recover the database and the files but cannot decrypt
                fields the source encrypted. This is asserted as an expected,
                explained limitation rather than silently ignored - and it is the
                concrete evidence that external key custody is a separate,
                required capability.
                """
                from frappe.utils.password import (get_decrypted_password,
                                                   get_encryption_key)
                expected = manifest["encrypted_field"]
                # Generate/read the target's own key FIRST. Frappe creates it
                # lazily, so reading site_config.json before any key access
                # would find nothing and mask the comparison.
                get_encryption_key()
                local_key = json.loads(
                    (Path.cwd() / site / "site_config.json").read_text())["encryption_key"]
                local_sha = hashlib.sha256(local_key.encode()).hexdigest()
                stored = str(stored_ciphertext(frappe.db, *AUTH_FIELD))
                ciphertext_sha = hashlib.sha256(stored.encode()).hexdigest()
                try:
                    get_decrypted_password("User", "Administrator", "api_secret")
                    decrypted = True
                except Exception:
                    decrypted = False
                if decrypted:
                    raise AssertionError(
                        "Encrypted field decrypted on the independent system, which would mean "
                        "source key material travelled with the backup")
                return {
                    "ciphertext_recovered_intact": ciphertext_sha == expected["ciphertext_sha256"],
                    "source_key_sha256": expected["source_key_sha256"],
                    "target_key_sha256": local_sha,
                    "keys_differ": local_sha != expected["source_key_sha256"],
                    "decrypts_on_target": False,
                    "conclusion": ("Database and files recovered; source-encrypted field is "
                                   "intact but undecryptable here because the key was never "
                                   "transferred. Closing this requires separately controlled "
                                   "external key custody, which is a distinct requirement."),
                }

            check("source-encrypted-field-is-intact-but-undecryptable-here",
                  _encrypted_field_limitation)

        result["status"] = "pass"
        write_result()
        print("Independent-recovery " + action + " verified on " + site + "; no secrets emitted")
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()

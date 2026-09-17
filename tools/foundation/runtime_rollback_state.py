"""Create and verify the state a rollback has to preserve.

Runs inside the bench environment on a disposable hosted runner. ``create`` writes
the state before an upgrade and registers it in a manifest; ``verify`` reads it back
afterwards and compares. Both sides use this same script, so the comparison is
between what one version of the application wrote and what another can read back -
not between two interpretations of the same data.

Two kinds of state are created, because a rollback can fail in two different ways:

* records, compared on content *and* on ``creation``. The timestamp matters: a row
  that was deleted and re-created during a restore matches on content while
  differing on identity, and a rollback that silently rebuilt the data is not the
  rollback that was claimed;
* files, compared on SHA-256 of both the served content and what is on disk, with
  one private and one public so the privacy split is part of what has to survive.

Only synthetic records and files are created. The manifest holds names, timestamps
and digests; it never holds a password, an encryption key or a site configuration.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

SITE = "rollback.localhost"
PRIVATE_FILE = "rollback-private.txt"
PUBLIC_FILE = "rollback-public.txt"
RECORD_COUNT = 3


def main() -> int:
    argv = sys.argv[1:]
    if os.environ.get("GITHUB_ACTIONS") != "true" or SITE not in argv:
        raise SystemExit("Disposable hosted rollback site only")
    action = "create" if "create" in argv else "verify" if "verify" in argv else None
    if action is None:
        raise SystemExit("An action of create or verify is required")

    manifest_path = Path(os.environ["FOUNDATION_ROLLBACK_MANIFEST"])
    result_path = Path(os.environ["FOUNDATION_ROLLBACK_STATE_RESULT"])
    result = {"status": "running", "action": action, "site": SITE, "checks": []}

    def write_result():
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, indent=2) + "\n")

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

    import frappe

    frappe.init(site=SITE, sites_path=str(Path.cwd()))
    frappe.connect()
    frappe.set_user("Administrator")

    try:
        if action == "create":
            def _create():
                run_tag = uuid.uuid4().hex[:12]
                created = {"run_tag": run_tag, "records": {}, "files": {}}
                for index in range(RECORD_COUNT):
                    description = f"synthetic-rollback-{run_tag}-{index:03d}"
                    doc = frappe.get_doc({"doctype": "ToDo", "description": description}).insert(
                        ignore_permissions=True)
                    frappe.db.commit()
                    created["records"][doc.name] = {
                        "doctype": "ToDo", "description": description,
                        "creation": str(doc.creation),
                    }
                anchor = sorted(created["records"])[0]
                private_payload = f"synthetic private content {run_tag}\n" + ("x" * 512) + "\n"
                public_payload = f"synthetic public content {run_tag}\n" + ("y" * 512) + "\n"
                for file_name, payload, is_private in (
                        (PRIVATE_FILE, private_payload, 1), (PUBLIC_FILE, public_payload, 0)):
                    doc = frappe.get_doc({
                        "doctype": "File", "file_name": file_name, "content": payload,
                        "is_private": is_private,
                        "attached_to_doctype": "ToDo" if is_private else "",
                        "attached_to_name": anchor if is_private else "",
                    }).insert(ignore_permissions=True)
                    frappe.db.commit()
                    absolute = Path.cwd() / SITE / (
                        "private/files" if is_private else "public/files") / file_name
                    if not absolute.exists():
                        raise AssertionError("File was not written to disk at " + str(absolute))
                    created["files"][file_name] = {
                        "file_url": doc.file_url, "is_private": is_private,
                        "name": doc.name, "creation": str(doc.creation),
                        "content_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                        "on_disk_sha256": hashlib.sha256(absolute.read_bytes()).hexdigest(),
                        "bytes": absolute.stat().st_size,
                    }
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text(json.dumps(created, indent=2) + "\n")
                return {"run_tag": run_tag, "records": len(created["records"]),
                        "files": sorted(created["files"]),
                        "manifest_sha256": hashlib.sha256(
                            json.dumps(created, sort_keys=True).encode()).hexdigest()}

            check("synthetic-state-created-before-upgrade", _create)
        else:
            manifest = json.loads(manifest_path.read_text())

            def _verify():
                compared = {"records": {}, "files": {}}
                missing = []
                content_changed = []
                recreated = []
                for name, expected in manifest["records"].items():
                    rows = frappe.db.get_value("ToDo", name, ["description", "creation"],
                                               as_dict=True)
                    if not rows:
                        missing.append(name)
                        continue
                    description_matches = str(rows["description"]) == expected["description"]
                    creation_matches = str(rows["creation"]) == expected["creation"]
                    if not description_matches:
                        content_changed.append(name)
                    if not creation_matches:
                        recreated.append(name)
                    compared["records"][name] = {
                        "description_matches": description_matches,
                        "creation_matches": creation_matches,
                        "creation_expected": expected["creation"],
                        "creation_observed": str(rows["creation"]),
                    }
                for file_name, expected in manifest["files"].items():
                    row = frappe.db.get_value("File", {"file_url": expected["file_url"]},
                                              ["name", "is_private", "file_size", "creation"],
                                              as_dict=True)
                    if not row:
                        missing.append(file_name)
                        continue
                    absolute = Path.cwd() / SITE / (
                        "private/files" if expected["is_private"] else "public/files"
                    ) / file_name
                    on_disk = hashlib.sha256(absolute.read_bytes()).hexdigest() \
                        if absolute.exists() else None
                    if on_disk != expected["on_disk_sha256"]:
                        content_changed.append(file_name)
                    if str(row["creation"]) != expected["creation"]:
                        recreated.append(file_name)
                    compared["files"][file_name] = {
                        "document_present": True,
                        "is_private": int(row["is_private"]),
                        "privacy_flag_unchanged": int(row["is_private"]) == int(
                            expected["is_private"]),
                        "on_disk_sha256": on_disk,
                        "on_disk_matches": on_disk == expected["on_disk_sha256"],
                        "creation_matches": str(row["creation"]) == expected["creation"],
                        "file_size": int(row["file_size"] or 0),
                    }
                preserved = (not missing and not content_changed and not recreated
                             and bool(compared["records"]))
                observation = {
                    "records_compared": len(compared["records"]),
                    "files_compared": len(compared["files"]),
                    "missing": missing, "content_changed": content_changed,
                    "creation_timestamp_changed": recreated,
                    "preserved": preserved, "detail": compared,
                }
                if not preserved:
                    raise AssertionError("State did not survive: " + json.dumps(
                        {key: observation[key] for key in
                         ("missing", "content_changed", "creation_timestamp_changed")}))
                return observation

            check("state-preserved-and-identical", _verify)

        result["status"] = "pass"
        write_result()
        print("Rollback state " + action + " completed on " + SITE)
    except Exception as exc:
        result["status"] = "fail"
        result["failure"] = str(exc)[:400]
        print(result["failure"], file=sys.stderr)
    finally:
        write_result()
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

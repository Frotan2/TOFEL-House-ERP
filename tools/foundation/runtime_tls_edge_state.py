"""Create the synthetic file pair that the TLS boundary probe serves.

Runs inside the bench environment on a disposable hosted runner, using the same
``File`` idiom the independent-recovery source harness already proved at this pin
(``frappe.get_doc({...}).insert(ignore_permissions=True)`` followed by a commit and
an on-disk existence assertion).

Files are created server-side rather than through an HTTP POST on purpose. The TLS
claim being tested is about *serving* - that a private file crosses the edge only
for an authenticated session, and only through ``X-Accel-Redirect`` - and GET
requests are safe methods, so no CSRF token is involved. Creating them over HTTP
would add a second variable to a check that is meant to isolate one.

The manifest holds file URLs, privacy flags and content digests. It never holds a
password, a key or a site configuration, and no private key is written anywhere
near it.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

SITE = "edge.foundation.internal"
PRIVATE_FILE = "tls-edge-private.txt"
PUBLIC_FILE = "tls-edge-public.txt"


def main() -> int:
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or "create" not in sys.argv[1:] or SITE not in sys.argv[1:]):
        raise SystemExit("Disposable hosted TLS-edge site only")

    manifest_path = Path(os.environ["FOUNDATION_TLS_EDGE_MANIFEST"])
    result = {"status": "running", "checks": [], "site": SITE}

    def write_result():
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        (manifest_path.parent / "state-result.json").write_text(
            json.dumps(result, indent=2) + "\n")

    def check(name, fn):
        try:
            observation = fn()
            result["checks"].append({"name": name, "status": "pass",
                                     "observation": observation})
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
    run_tag = uuid.uuid4().hex[:12]

    def _create():
        created = {"run_tag": run_tag, "files": {}, "todo": None}
        todo = frappe.get_doc({
            "doctype": "ToDo",
            "description": f"synthetic-tls-edge-{run_tag}",
        }).insert(ignore_permissions=True).name
        frappe.db.commit()
        created["todo"] = todo

        private_payload = f"synthetic private content {run_tag}\n" + ("x" * 512) + "\n"
        public_payload = f"synthetic public content {run_tag}\n" + ("y" * 512) + "\n"
        for file_name, payload, is_private in (
                (PRIVATE_FILE, private_payload, 1), (PUBLIC_FILE, public_payload, 0)):
            doc = frappe.get_doc({
                "doctype": "File", "file_name": file_name, "content": payload,
                "is_private": is_private,
                "attached_to_doctype": "ToDo" if is_private else "",
                "attached_to_name": todo if is_private else "",
            }).insert(ignore_permissions=True)
            frappe.db.commit()
            absolute = Path.cwd() / SITE / (
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
        return {"run_tag": run_tag, "todo": todo,
                "files": sorted(created["files"]),
                "private_file_url": created["files"][PRIVATE_FILE]["file_url"],
                "public_file_url": created["files"][PUBLIC_FILE]["file_url"]}

    try:
        check("synthetic-file-pair-created-on-edge-site", _create)
        result["status"] = "pass"
        print("Synthetic private and public files created on the edge site")
    except Exception as exc:
        result["status"] = "fail"
        result["failure"] = str(exc)[:400]
        print(result["failure"], file=sys.stderr)
    finally:
        write_result()
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

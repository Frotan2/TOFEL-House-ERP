#!/usr/bin/env python3
"""Capture and verify a synthetic TOEFL House backup/restore boundary.

This helper is deliberately restricted to the disposable GitHub runner and the
source/restore sites created by ``run_native.py``. It never accepts a production
site, prints no credentials or document contents, and records only counts and
SHA-256 digests of synthetic record names and full row values. It does not
establish an offsite backup policy, recovery objective, or production restore
guarantee.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

SOURCE_SITE = "placement-test.localhost"
RESTORE_SITE = "placement-restore.localhost"

# One representative row from each implemented domain plus the native records
# written by guarded commands. The test keeps the persistence claim factual: it
# does not pretend that a synthetic backup proves an institution-wide dataset.
REPRESENTATIVE_DOCTYPES = (
    "TH Placement Item Revision",
    "TH Placement Attempt",
    "TH Placement Decision",
    "TH Admission Decision",
    "Program Enrollment",
    "Student Group",
    "Course Schedule",
    "Student Attendance",
    "TH Instructor Contract",
    "TH Teaching Assignment",
    "TH Correction Policy",
    "TH Correction Request",
    "Fees",
    "Sales Invoice",
)


def _digest(names: list[str]) -> str:
    return hashlib.sha256("\0".join(sorted(names)).encode()).hexdigest()


def _row_digest(rows) -> str:
    payload=json.dumps(rows,sort_keys=True,separators=(",",":"),default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _connect(site: str):
    import frappe

    frappe.init(site=site)
    frappe.connect()
    frappe.set_user("Administrator")
    return frappe


def _file_storage_path(frappe, file_doc) -> Path:
    """Resolve only Frappe's canonical public/private file URL layouts."""
    file_name = str(file_doc.file_name or "")
    if not file_name or Path(file_name).name != file_name or file_name in {".", ".."}:
        raise AssertionError("Synthetic File has an unsafe file name")
    is_private = int(file_doc.is_private or 0) == 1
    expected_url = ("/private/files/" if is_private else "/files/") + file_name
    if file_doc.file_url != expected_url:
        raise AssertionError("Synthetic File URL does not match its privacy flag")
    return Path(frappe.get_site_path(
        "private" if is_private else "public", "files", file_name))


def _file_snapshot(frappe, file_doc, marker: bytes) -> dict:
    path = _file_storage_path(frappe, file_doc)
    stat = path.stat()
    content = file_doc.get_content()
    if isinstance(content, str):
        content = content.encode()
    if content != marker:
        raise AssertionError("Synthetic File content differs immediately after creation")
    return {
        "name": file_doc.name,
        "file_name": file_doc.file_name,
        "file_url": file_doc.file_url,
        "is_private": int(file_doc.is_private or 0),
        "attached_to_doctype": file_doc.attached_to_doctype,
        "attached_to_name_digest": hashlib.sha256(
            str(file_doc.attached_to_name).encode()).hexdigest(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "storage": {
            "size": stat.st_size,
            "mode": stat.st_mode & 0o777,
            "uid": stat.st_uid,
            "gid": stat.st_gid,
        },
    }


def _snapshot(frappe) -> dict:
    doctypes = {}
    for doctype in REPRESENTATIVE_DOCTYPES:
        names = frappe.get_all(doctype, pluck="name", order_by="name asc")
        if not names:
            raise AssertionError(f"Expected synthetic {doctype} record before backup")
        rows=frappe.get_all(doctype,fields=["*"],order_by="name asc")
        doctypes[doctype] = {
            "count": len(names),
            "name_digest": _digest(names),
            "row_digest": _row_digest(rows),
        }

    # Both markers are generated only in the disposable CI site. Their
    # content, File metadata, storage location, permissions and ownership are
    # recorded before the native backup; the restore target must reproduce
    # them exactly without touching the source site.
    decision = frappe.get_all("TH Placement Decision", pluck="name", order_by="name asc", limit=1)[0]
    attached_digest = hashlib.sha256(decision.encode()).hexdigest()
    run_id = os.environ["GITHUB_RUN_ID"]
    markers = {
        "private_file": (b"Synthetic private restore marker; not production data.", 1),
        "public_file": (b"Synthetic public restore marker; not production data.", 0),
    }
    files = {}
    for role, (marker, is_private) in markers.items():
        filename = f"synthetic-product-restore-{role}-{run_id}.txt"
        file_doc = frappe.get_doc({
            "doctype": "File", "file_name": filename, "is_private": is_private,
            "attached_to_doctype": "TH Placement Decision", "attached_to_name": decision,
            "content": marker,
        }).insert()
        files[role] = _file_snapshot(frappe, file_doc, marker)
        if files[role]["attached_to_name_digest"] != attached_digest:
            raise AssertionError("Synthetic File attachment metadata was not stored")
    frappe.db.commit()
    return {
        "scope": "Disposable synthetic TOEFL House records plus public/private file integrity, metadata and filesystem attributes; not production DR",
        "status": "captured",
        "doctypes": doctypes,
        "files": files,
    }


def _verify(frappe, expected: dict) -> dict:
    if expected.get("status") != "captured":
        raise AssertionError("Restore expectation was not created by this capture helper")
    expected_doctypes=expected.get("doctypes")
    expected_files=expected.get("files")
    if not isinstance(expected_doctypes,dict) or set(expected_doctypes)!=set(REPRESENTATIVE_DOCTYPES):
        raise AssertionError("Restore expectation has incomplete representative DocType coverage")
    if not isinstance(expected_files,dict) or set(expected_files)!={"public_file","private_file"}:
        raise AssertionError("Restore expectation must contain both public and private file roles")
    verified = {}
    for doctype, source in expected["doctypes"].items():
        names = frappe.get_all(doctype, pluck="name", order_by="name asc")
        rows=frappe.get_all(doctype,fields=["*"],order_by="name asc")
        actual = {
            "count": len(names),
            "name_digest": _digest(names),
            "row_digest": _row_digest(rows),
        }
        if actual != source:
            raise AssertionError(f"Restored {doctype} does not match source snapshot")
        verified[doctype] = actual["count"]

    verified_files = {}
    for role, file_expected in expected["files"].items():
        file_doc = frappe.get_doc("File", file_expected["name"])
        if (file_doc.file_name != file_expected["file_name"]
                or file_doc.file_url != file_expected["file_url"]
                or int(file_doc.is_private or 0) != file_expected["is_private"]
                or file_doc.attached_to_doctype != file_expected["attached_to_doctype"]):
            raise AssertionError(f"Restored {role} File metadata differs from the captured file")
        attached_digest = hashlib.sha256(
            str(file_doc.attached_to_name).encode()).hexdigest()
        if attached_digest != file_expected["attached_to_name_digest"]:
            raise AssertionError(f"Restored {role} File points at a different record")
        content = file_doc.get_content()
        if isinstance(content, str):
            content = content.encode()
        if hashlib.sha256(content).hexdigest() != file_expected["sha256"]:
            raise AssertionError(f"Restored {role} file content digest differs")
        path = _file_storage_path(frappe, file_doc)
        stat = path.stat()
        actual_storage = {
            "size": stat.st_size,
            "mode": stat.st_mode & 0o777,
            "uid": stat.st_uid,
            "gid": stat.st_gid,
        }
        if actual_storage != file_expected["storage"]:
            raise AssertionError(
                f"Restored {role} filesystem size/mode/uid/gid differs from source")
        verified_files[role] = {
            "content_sha256_verified": True,
            "metadata_verified": True,
            "storage_size": stat.st_size,
            "storage_mode_octal": format(stat.st_mode & 0o777, "04o"),
            "storage_uid": stat.st_uid,
            "storage_gid": stat.st_gid,
        }
    return {
        "scope": expected["scope"], "status": "pass",
        "doctypes_verified": verified,
        "files_verified": verified_files,
        "source_snapshot_is_synthetic": True,
    }


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Hosted disposable runner only")
    if len(sys.argv) != 3 or sys.argv[1] not in {"capture", "verify"}:
        raise SystemExit("Usage: runtime_restore.py capture|verify <approved synthetic site>")
    action, site = sys.argv[1:]
    if (action, site) not in (("capture", SOURCE_SITE), ("verify", RESTORE_SITE)):
        raise SystemExit("Only the runner-created source and restore sites are permitted")
    output = Path(os.environ["PLACEMENT_RESTORE_REPORT"])
    frappe = _connect(site)
    try:
        if action == "capture":
            result = _snapshot(frappe)
        else:
            source = Path(os.environ["PLACEMENT_RESTORE_EXPECTATION"])
            result = _verify(frappe, json.loads(source.read_text()))
        output.write_text(json.dumps(result, indent=2) + "\n")
        return 0
    finally:
        frappe.destroy()


if __name__ == "__main__":
    raise SystemExit(main())

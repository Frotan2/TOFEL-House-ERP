#!/usr/bin/env python3
"""Capture and verify a synthetic TOEFL House backup/restore boundary.

This helper is deliberately restricted to the disposable GitHub runner and the
source/restore sites created by ``run_native.py``. It never accepts a production
site, prints no credentials or document contents, and records only counts and
SHA-256 digests of synthetic record names. It does not establish an offsite
backup policy, recovery objective, or production restore guarantee.
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


def _connect(site: str):
    import frappe

    frappe.init(site=site, sites_path=str(Path.cwd()))
    frappe.connect()
    frappe.set_user("Administrator")
    return frappe


def _snapshot(frappe) -> dict:
    doctypes = {}
    for doctype in REPRESENTATIVE_DOCTYPES:
        names = frappe.get_all(doctype, pluck="name", order_by="name asc")
        if not names:
            raise AssertionError(f"Expected synthetic {doctype} record before backup")
        doctypes[doctype] = {"count": len(names), "name_digest": _digest(names)}

    # File bytes are deliberately generated only in this disposable site. The
    # marker is attached to a real guarded decision, goes through Frappe file
    # storage, and lets the restore verifier prove the private bytes survived.
    decision = frappe.get_all("TH Placement Decision", pluck="name", order_by="name asc", limit=1)[0]
    marker = b"Synthetic TOEFL House product backup restore marker; not production data."
    filename = "synthetic-product-restore-marker-" + os.environ["GITHUB_RUN_ID"] + ".txt"
    file_doc = frappe.get_doc({
        "doctype": "File", "file_name": filename, "is_private": 1,
        "attached_to_doctype": "TH Placement Decision", "attached_to_name": decision,
        "content": marker,
    }).insert()
    frappe.db.commit()
    return {
        "scope": "Disposable synthetic TOEFL House record and private-file restore only; not production DR",
        "status": "captured",
        "doctypes": doctypes,
        "private_file": {
            "name": file_doc.name,
            "attached_to_doctype": "TH Placement Decision",
            "attached_to_name_digest": hashlib.sha256(decision.encode()).hexdigest(),
            "sha256": hashlib.sha256(marker).hexdigest(),
        },
    }


def _verify(frappe, expected: dict) -> dict:
    if expected.get("status") != "captured":
        raise AssertionError("Restore expectation was not created by this capture helper")
    verified = {}
    for doctype, source in expected["doctypes"].items():
        names = frappe.get_all(doctype, pluck="name", order_by="name asc")
        actual = {"count": len(names), "name_digest": _digest(names)}
        if actual != source:
            raise AssertionError(f"Restored {doctype} does not match source snapshot")
        verified[doctype] = actual["count"]

    file_expected = expected["private_file"]
    file_doc = frappe.get_doc("File", file_expected["name"])
    if not file_doc.is_private or file_doc.attached_to_doctype != file_expected["attached_to_doctype"]:
        raise AssertionError("Restored private file metadata differs from the captured file")
    attached_digest = hashlib.sha256(file_doc.attached_to_name.encode()).hexdigest()
    if attached_digest != file_expected["attached_to_name_digest"]:
        raise AssertionError("Restored private file points at a different decision")
    content = file_doc.get_content()
    if isinstance(content, str):
        content = content.encode()
    content_digest = hashlib.sha256(content).hexdigest()
    if content_digest != file_expected["sha256"]:
        raise AssertionError("Restored private file content digest differs")
    return {
        "scope": expected["scope"], "status": "pass",
        "doctypes_verified": verified,
        "private_file_sha256_verified": True,
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

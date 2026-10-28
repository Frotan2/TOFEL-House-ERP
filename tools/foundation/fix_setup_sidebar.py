"""Keep the pinned Frappe sidebar absent during the initial setup wizard.

Frappe 988e54f3 skips Sidebar.make_dom before setup, but Container.change_to
still calls Sidebar.toggle. Apply the constructor's lifecycle condition to
toggle as well. Unexpected source and output bytes are refused before writing.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

TARGET = Path("frappe/public/js/frappe/ui/sidebar/sidebar.js")
UPSTREAM_SHA256 = "3074e4da84338a5e8a94ca1ec7f0f0ac0cda8ce0f8c64f9ecd37b2c3c5562aba"
REVIEWED_SHA256 = "4bc6ae7043a21ef20c26ed7ec50a2fd1dedaa4ac106d61e7d9772eaaab300646"
BEFORE = b"\ttoggle(hide) {\n"
AFTER = BEFORE + (
    b"\t\t// The setup wizard has no sidebar DOM until setup completes.\n"
    b"\t\tif (!frappe.boot.setup_complete) return;\n"
)


def apply(frappe: Path, *, verify_only: bool = False) -> str:
    target = frappe / TARGET
    if target.is_symlink() or not target.is_file():
        raise ValueError("Sidebar target must be a regular file")
    current = target.read_bytes()
    digest = hashlib.sha256(current).hexdigest()
    if digest == REVIEWED_SHA256:
        return "verified" if verify_only else "already-applied"
    if verify_only:
        raise ValueError("Sidebar lifecycle fix is not applied")
    if digest != UPSTREAM_SHA256 or current.count(BEFORE) != 1:
        raise ValueError("Unreviewed sidebar source; refusing modification")
    result = current.replace(BEFORE, AFTER)
    if hashlib.sha256(result).hexdigest() != REVIEWED_SHA256:
        raise ValueError("Unreviewed sidebar output; refusing modification")
    target.write_bytes(result)
    apply(frappe, verify_only=True)
    return "applied"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frappe", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    print("Setup sidebar lifecycle: " + apply(args.frappe, verify_only=args.verify))

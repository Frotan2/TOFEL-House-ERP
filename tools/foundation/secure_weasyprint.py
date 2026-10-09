#!/usr/bin/env python3
"""Hash-bound guard on Frappe's single WeasyPrint rendering constructor.

Apply only to a disposable pinned installation after source integrity checks.
Fail closed on upstream drift; do not modify the operator's checkout or site.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

PINNED_SHA256 = "0ddfabf43b5678abeb31730cc660c581fd4f305bcfd406852c2ad50688f5159d"
ANCHOR = "\t\tself.base_url = frappe.utils.get_url()\n"
GUARD = ("\t\t# TOEFL House: validate every entry to the WeasyPrint renderer.\n"
         "\t\tfrom toefl_house.printing import authorize_weasyprint\n"
         "\t\tauthorize_weasyprint(print_format, doc)\n")


def apply_guard(path: Path) -> None:
    original = path.read_bytes()
    if hashlib.sha256(original).hexdigest() != PINNED_SHA256:
        raise ValueError("Pinned WeasyPrint source changed; refuse unreviewed renderer")
    text = original.decode("utf-8")
    if text.count(ANCHOR) != 1 or text.count("class PrintFormatGenerator:") != 1:
        raise ValueError("WeasyPrint constructor anchor changed")
    updated = text.replace(ANCHOR, GUARD + ANCHOR, 1)
    path.write_bytes(updated.encode("utf-8"))
    if GUARD not in path.read_text():
        raise ValueError("WeasyPrint guard did not persist")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("frappe_app", type=Path)
    args = parser.parse_args()
    apply_guard(args.frappe_app / "frappe/utils/weasyprint.py")


if __name__ == "__main__":
    main()

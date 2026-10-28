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
PATCHED_SHA256 = "182673493b481f5bb173b763392ede94db1ce4fe15a4f04b6f637e140f63a2ca"
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
    replacements = {
        ANCHOR: ANCHOR + (
            "\t\tfrom toefl_house.pdf_resources import resource_policy\n"
            "\t\tself.resource_policy = resource_policy(doc, self.base_url)\n"),
        "html = HTML(string=main_html, base_url=self.base_url)":
            "html = HTML(string=main_html, base_url=self.base_url, url_fetcher=self.resource_policy)",
        "\t\t\tbase_url=self.base_url,\n":
            "\t\t\tbase_url=self.base_url,\n\t\t\turl_fetcher=self.resource_policy,\n",
        "\t\tmain_doc = html.render()\n":
            "\t\tmain_doc = html.render()\n\t\tself.resource_policy.check()\n",
        '\t\telement_doc = html.render(stylesheets=[CSS(string="@page {size: A4 portrait; margin: 0;}")])\n':
            ('\t\telement_doc = html.render(stylesheets=[CSS(string="@page {size: A4 portrait; margin: 0;}")])\n'
             "\t\tself.resource_policy.check()\n"),
        "\t\treturn main_doc.write_pdf()": (
            "\t\tpdf = main_doc.write_pdf()\n"
            "\t\tself.resource_policy.check()\n"
            "\t\treturn pdf"),
    }
    for before, after in replacements.items():
        if updated.count(before) != 1:
            raise ValueError("WeasyPrint resource-policy anchor changed")
        updated = updated.replace(before, after, 1)
    if hashlib.sha256(updated.encode("utf-8")).hexdigest() != PATCHED_SHA256:
        raise ValueError("Unexpected WeasyPrint patch output; original left unchanged")
    path.write_bytes(updated.encode("utf-8"))
    verify_guard(path)


def verify_guard(path: Path) -> None:
    if hashlib.sha256(path.read_bytes()).hexdigest() != PATCHED_SHA256:
        raise ValueError("Installed WeasyPrint guard bytes changed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("frappe_app", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    path = args.frappe_app / "frappe/utils/weasyprint.py"
    if args.verify:
        verify_guard(path)
    else:
        apply_guard(path)


if __name__ == "__main__":
    main()

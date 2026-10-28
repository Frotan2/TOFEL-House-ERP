#!/usr/bin/env python3
"""Cap showdown input in the Desk markdown renderer (SEC-DEPS-01, GHSA-rmmh-p597-ppvv).

showdown <= 2.1.0 has a nested regular expression in its `anchors` subparser (ReDoS, medium).
No patched showdown exists. Frappe core uses showdown in exactly one place: `frappe.markdown` in
`frappe/public/js/frappe/utils/tools.js` (code search at 988e54f3). This tool inserts a guard that
shows input longer than MAX_CHARS as escaped plain text, so the parser never sees it.

Measured on showdown 2.1.0 (see docs/engineering/evidence/sec-deps-01/markdown-cap-2026-10-19):
an attacker-shaped `[]( ` x 2000 (2000 chars) parses in about 0.2 s; x 12000 (12000 chars) took 35.8 s.
The cap bounds the input the parser sees. It is a bound on cost, not a proof for every payload.

Input digests must match either the pinned upstream file (apply) or the reviewed output (verify).
Any other content is refused. Nothing is resolved or downloaded here.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

TARGET = Path("frappe/public/js/frappe/utils/tools.js")
UPSTREAM_SHA256 = "99a91f55dbdb537e3fa457fb41a83909f9f116b9a3cc8dd06b9109e14eb090e3"
REVIEWED_SHA256 = "8f122bc9561836888790a5755afa10933434efae3e28ab2521ee5bbcc7f05cf7"
MAX_CHARS = 2000

BEFORE = "\treturn sanitize_markdown_html(frappe.md2html.makeHtml(txt));\n"
GUARD = (
    "\t// SEC-DEPS-01 (showdown GHSA-rmmh-p597-ppvv, ReDoS): input above the cap is shown as plain text, not parsed.\n"
    f"\tif (txt.length > {MAX_CHARS}) {{\n"
    "\t\tvar plain = document.createElement(\"div\");\n"
    "\t\tplain.textContent = txt;\n"
    "\t\treturn plain.innerHTML;\n"
    "\t}\n"
)
AFTER = GUARD + BEFORE


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def secure_markdown(frappe: Path, *, verify_only: bool = False) -> str:
    """Apply (or verify) the markdown cap in the disposable Frappe checkout.

    Returns "applied", "already-applied" or "verified". Raises ValueError on any other content.
    """
    target = frappe / TARGET
    if target.is_symlink() or not target.is_file():
        raise ValueError("markdown cap target is missing or not a regular file: " + str(TARGET))
    current = target.read_bytes()
    digest = _sha256(current)
    if digest == REVIEWED_SHA256:
        return "verified" if verify_only else "already-applied"
    if verify_only:
        raise ValueError("markdown cap is not applied (digest %s)" % digest)
    if digest != UPSTREAM_SHA256:
        raise ValueError("markdown cap refused: unreviewed tools.js content (digest %s)" % digest)
    text = current.decode("utf-8")
    if text.count(BEFORE) != 1:
        raise ValueError("markdown cap anchor must occur exactly once")
    patched = text.replace(BEFORE, AFTER).encode("utf-8")
    if _sha256(patched) != REVIEWED_SHA256:
        raise ValueError("markdown cap output does not match the reviewed digest")
    target.write_bytes(patched)
    if _sha256(target.read_bytes()) != REVIEWED_SHA256:
        raise ValueError("markdown cap write verification failed")
    return "applied"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("frappe", type=Path, help="Frappe app directory (apps/frappe)")
    parser.add_argument("--verify", action="store_true", help="verify only; never write")
    args = parser.parse_args()
    print("markdown cap: " + secure_markdown(args.frappe, verify_only=args.verify))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the product's native backup adapter for a disposable CI site only.

The adapter delegates backup creation and encryption to pinned Frappe. Its
explicit test-site override is not exposed by product/backup.py's CLI.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))
import backup  # noqa: E402


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", argv[0]):
        sys.stderr.write("Synthetic backup site is invalid.\n")
        return 2
    try:
        backup._native_backup(site_name=argv[0], allow_test_site=True)
    except (Exception, SystemExit):
        sys.stderr.write(
            "Native Frappe backup failed; sensitive diagnostics were withheld.\n")
        return 1
    sys.stdout.write("Native Frappe backup adapter completed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

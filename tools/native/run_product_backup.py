"""Run the product's native backup adapter for a disposable CI site only.

The adapter delegates backup creation and encryption to pinned Frappe. Its
explicit test-site override is not exposed by product/backup.py's CLI.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
_SAFE_EXCEPTION_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")


def safe_failure_summary(error: BaseException) -> str:
    """Expose only a validated class, numeric OS code, and compact frames."""
    name = type(error).__name__
    if not _SAFE_EXCEPTION_NAME.fullmatch(name):
        name = "Exception"
    details = ["exception type: " + name]
    code = getattr(error, "errno", None)
    if type(code) is int and 0 <= code <= 65535:
        details.append("OS error code: " + str(code))
    if name == "CommandFailedError":
        client_error = getattr(error, "err", None)
        if isinstance(client_error, str):
            match = re.search(
                r"\b(?:got error|error(?:\s+code)?)\s*(?::|=|#)?\s*(\d{1,5})\b",
                client_error, re.IGNORECASE)
            if match:
                details.append("client diagnostic code: " + str(int(match.group(1))))
    frames = []
    try:
        for frame in traceback.extract_tb(error.__traceback__)[-6:]:
            if re.fullmatch(r"[A-Za-z0-9_<>.-]{1,128}", frame.name):
                frames.append(f"{frame.name}:{frame.lineno}")
    except Exception:
        frames = []
    if frames:
        details.append("frames: " + ",".join(frames))
    return "; ".join(details)


sys.path.insert(0, str(ROOT / "product"))
import backup  # noqa: E402


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", argv[0]):
        sys.stderr.write("Synthetic backup site is invalid.\n")
        return 2
    try:
        backup._native_backup(site_name=argv[0], allow_test_site=True)
    except (Exception, SystemExit) as error:
        sys.stderr.write(
            "Native Frappe backup failed; " + safe_failure_summary(error)
            + "; sensitive diagnostics were withheld.\n")
        return 1
    sys.stdout.write("Native Frappe backup adapter completed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Apply Frappe's reviewed Pillow 13 security dependency uplift.

The pinned Frappe commit requires Pillow~=12.3.0. Pillow 13.0.0 fixes the
October 2026 image-decoder/encoder security batch, and upstream Frappe PR
#44814 makes the same one-line dependency change. This helper changes only
that dependency declaration in the disposable installed Frappe checkout.

The committed pyproject bytes and commit SHA must match the reviewed pin.
Verification reconstructs the expected patched bytes from git HEAD, so an
unreviewed source change cannot be hidden behind the overlay.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
from pathlib import Path
import subprocess

PINNED_FRAPPE_COMMIT = "988e54f3c4c291e2077a83809663f123731abe76"
PINNED_PYPROJECT_SHA256 = "75a442bcc2fdf946920bd4352c9719370869c5d943ad11e46e4f552bf301d8a6"
PATCHED_PILLOW_VERSION = "13.0.0"
OLD_REQUIREMENT = b'    "Pillow~=12.3.0",\n'
NEW_REQUIREMENT = b'    "Pillow~=13.0.0",\n'


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reviewed_pyproject(committed: bytes) -> bytes:
    if _sha256(committed) != PINNED_PYPROJECT_SHA256:
        raise ValueError("Pinned Frappe pyproject changed; refuse Pillow overlay")
    if committed.count(OLD_REQUIREMENT) != 1:
        raise ValueError("Pinned Pillow requirement anchor must occur exactly once")
    return committed.replace(OLD_REQUIREMENT, NEW_REQUIREMENT, 1)


def secure_pillow(frappe: Path, *, verify_only: bool = False) -> str:
    target = frappe / "pyproject.toml"
    if target.is_symlink() or not target.is_file():
        raise ValueError("Frappe pyproject is missing or not a regular file")

    head = subprocess.check_output(
        ["git", "-C", str(frappe), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != PINNED_FRAPPE_COMMIT:
        raise ValueError("Frappe revision changed; refuse Pillow overlay")

    committed = subprocess.check_output(
        ["git", "-C", str(frappe), "show", "HEAD:pyproject.toml"]
    )
    expected = _reviewed_pyproject(committed)
    current = target.read_bytes()
    if current == expected:
        return "verified" if verify_only else "already-applied"
    if verify_only:
        raise ValueError("Pillow 13 dependency overlay is not applied")
    if current != committed:
        raise ValueError("Frappe pyproject has unreviewed changes; refuse Pillow overlay")

    target.write_bytes(expected)
    if target.read_bytes() != expected:
        raise ValueError("Pillow dependency overlay write verification failed")
    return "applied"


def verify_runtime() -> None:
    installed = version("Pillow")
    if installed != PATCHED_PILLOW_VERSION:
        raise ValueError(
            f"Expected Pillow {PATCHED_PILLOW_VERSION}, found {installed}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("frappe_app", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    state = secure_pillow(args.frappe_app, verify_only=args.verify)
    if args.verify:
        verify_runtime()
    print(f"Pillow security overlay: {state}; required={PATCHED_PILLOW_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Apply the reviewed Python dependency security uplift to pinned Frappe.

The product remains commit-pinned to Frappe
988e54f3c4c291e2077a83809663f123731abe76. This helper changes only five
dependency declarations in that exact checkout, then the installers replace the
resolved packages with reviewed patched releases and reinstall Frappe metadata.

Reviewed uplifts:
- GitPython 3.2.1: fixes GHSA-83vg-56qc-22m7 (validate submodule destination
  before mutation).
- Pillow 13.0.0: fixes the October 2026 image codec security batch; upstream
  Frappe PR #44814 makes the same dependency-family uplift.
- PyJWT 2.15.1: includes the 2.14.0 fix for GHSA-pxh4-856f-4h89 and aligns
  with the newer upstream Frappe line.
- pypdf 6.21.2: includes the October 2026 parser/resource fixes through
  6.21.2, including the 6.21.1 DCT/JPEG validation fix.
- filelock 4.2.4: includes the 4.2.1 fix for GHSA-69hj-f68j-2879 and
  GHSA-8mx5-7m5m-r77g; pinned Frappe 3.x dependency metadata must be
  overlaid together with the installed package (never bypass pip check).

The committed pyproject bytes and Frappe commit must match the reviewed pin.
Verification reconstructs the exact expected patched bytes from git HEAD, so an
unreviewed source edit cannot hide behind this overlay.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
from pathlib import Path
import subprocess

PINNED_FRAPPE_COMMIT = "988e54f3c4c291e2077a83809663f123731abe76"
PINNED_PYPROJECT_SHA256 = "75a442bcc2fdf946920bd4352c9719370869c5d943ad11e46e4f552bf301d8a6"

REQUIREMENT_UPGRADES = (
    (b'    "GitPython~=3.1.45",\n', b'    "GitPython~=3.2.1",\n'),
    (b'    "Pillow~=12.3.0",\n', b'    "Pillow~=13.0.0",\n'),
    (b'    "PyJWT~=2.13.0",\n', b'    "PyJWT~=2.15.1",\n'),
    (b'    "pypdf==6.15.0",\n', b'    "pypdf==6.21.2",\n'),
    (b'    "filelock~=3.20.1",\n', b'    "filelock~=4.2.4",\n'),
)

REQUIRED_RUNTIME_VERSIONS = {
    "GitPython": "3.2.1",
    "Pillow": "13.0.0",
    "PyJWT": "2.15.1",
    "pypdf": "6.21.2",
    "filelock": "4.2.4",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reviewed_pyproject(committed: bytes) -> bytes:
    if _sha256(committed) != PINNED_PYPROJECT_SHA256:
        raise ValueError("Pinned Frappe pyproject changed; refuse Python security overlay")
    updated = committed
    for old, new in REQUIREMENT_UPGRADES:
        if committed.count(old) != 1:
            raise ValueError(
                "Pinned Python security requirement anchor must occur exactly once"
            )
        if committed.count(new):
            raise ValueError("Pinned pyproject unexpectedly already contains a security uplift")
        updated = updated.replace(old, new, 1)
    return updated


def secure_frappe_python(frappe: Path, *, verify_only: bool = False) -> str:
    target = frappe / "pyproject.toml"
    if target.is_symlink() or not target.is_file():
        raise ValueError("Frappe pyproject is missing or not a regular file")

    head = subprocess.check_output(
        ["git", "-C", str(frappe), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != PINNED_FRAPPE_COMMIT:
        raise ValueError("Frappe revision changed; refuse Python security overlay")

    committed = subprocess.check_output(
        ["git", "-C", str(frappe), "show", "HEAD:pyproject.toml"]
    )
    expected = _reviewed_pyproject(committed)
    current = target.read_bytes()
    if current == expected:
        return "verified" if verify_only else "already-applied"
    if verify_only:
        raise ValueError("Frappe Python security dependency overlay is not applied")
    if current != committed:
        raise ValueError(
            "Frappe pyproject has unreviewed changes; refuse Python security overlay"
        )

    target.write_bytes(expected)
    if target.read_bytes() != expected:
        raise ValueError("Frappe Python security overlay write verification failed")
    return "applied"


def verify_runtime() -> None:
    mismatches = []
    for package, expected in REQUIRED_RUNTIME_VERSIONS.items():
        installed = version(package)
        if installed != expected:
            mismatches.append(f"{package}={installed} (expected {expected})")
    if mismatches:
        raise ValueError("Patched Python runtime versions differ: " + "; ".join(mismatches))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("frappe_app", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    state = secure_frappe_python(args.frappe_app, verify_only=args.verify)
    if args.verify:
        verify_runtime()
    versions = ", ".join(
        f"{name}={required}" for name, required in REQUIRED_RUNTIME_VERSIONS.items()
    )
    print(f"Frappe Python security overlay: {state}; required: {versions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

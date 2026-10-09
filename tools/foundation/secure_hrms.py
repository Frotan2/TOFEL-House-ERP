#!/usr/bin/env python3
"""Integrity-pinned remediation of the installed HRMS editor dependency.

The upstream HRMS source commit/lock remain verifiable and unchanged. Apply to
*disposable* installed node_modules before asset build; verify again after build.
Yarn may nest copies, so a top-level-only replacement is not sufficient.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
from urllib.request import urlopen

PATCHES = {
    "prosemirror-view": ("1.42.3", "oTN7EtH+CpwxU9NrwEYWd0UZ4JUx7l048l5A2Xppm4p/60isZYLnth9QVQmC3VRIvdrIWCxwZSd+Uz791G31/w=="),
    "prosemirror-model": ("1.25.8", "BswA4BLSFEiORV6Vjj/yZBXDbos1zTEnhyeSSgT8psGFhstQS7UJ8/WOLiDos9Byaee27+tml0/DuMNxYR84zg=="),
}


def installed_copies(hrms: Path, name: str) -> list[Path]:
    """Find each copy without following symlinks outside the disposable tree."""
    found = []
    for tree in (hrms / "frontend", hrms / "roster"):
        root = tree / "node_modules"
        if not root.is_dir():
            raise ValueError(f"Missing HRMS dependency root: {tree.name}")
        for manifest in root.rglob(f"{name}/package.json"):
            if manifest.is_symlink() or manifest.parent.is_symlink():
                raise ValueError("Symlinked editor dependency is not an auditable install")
            if json.loads(manifest.read_text()).get("name") == name:
                found.append(manifest.parent)
    return found


def verify(hrms: Path) -> dict[str, int]:
    counts = {}
    for name, (version, _) in PATCHES.items():
        copies = installed_copies(hrms, name)
        if not copies:
            raise ValueError(f"No installed {name} in HRMS frontend/roster")
        for folder in copies:
            manifest = json.loads((folder / "package.json").read_text())
            if manifest.get("version") != version:
                raise ValueError(f"Vulnerable {name} remains in HRMS")
        counts[name] = len(copies)
    return counts


def patch(hrms: Path) -> dict[str, int]:
    # Download public code only from fixed npm URLs, not from site configuration.
    for name, (version, digest) in PATCHES.items():
        copies = installed_copies(hrms, name)
        if not copies:
            raise ValueError(f"No installed {name}; refusing vacuous remediation")
        url = f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz"
        data = urlopen(url, timeout=60).read()
        if hashlib.sha512(data).digest() != base64.b64decode(digest):
            raise ValueError(f"Integrity mismatch for {name}")
        with tempfile.TemporaryDirectory() as tmp:
            extracted = Path(tmp) / "package"
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                for member in archive:
                    path = Path(member.name)
                    if (not path.parts or path.parts[0] != "package"
                            or ".." in path.parts or member.issym() or member.islnk()
                            or not (member.isfile() or member.isdir())):
                        raise ValueError(f"Unsafe npm tarball for {name}")
                archive.extractall(tmp)
            manifest = json.loads((extracted / "package.json").read_text())
            if manifest.get("name") != name or manifest.get("version") != version:
                raise ValueError(f"Unexpected npm package for {name}")
            for folder in copies:
                shutil.rmtree(folder)
                shutil.copytree(extracted, folder)
    return verify(hrms)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("hrms_app", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(args.hrms_app) if args.verify else patch(args.hrms_app), sort_keys=True))


if __name__ == "__main__":
    main()

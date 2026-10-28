#!/usr/bin/env python3
"""Apply the reviewed Education frontend overlay (GHSA-vhrc-hgrq-x75r).

The Education frontend pins frappe-ui 0.1.31, which resolves @tiptap/* 2.2.3.
Its @tiptap/extension-link is inside the advisory's vulnerable range (< 2.10.4).
This overlay pins every @tiptap/* package to 2.27.3 through `resolutions`, with a
frozen lockfile. It is applied to the disposable Education checkout only, before the
bench asset build, and verified again after the build.

Nothing is resolved here. Source hashes must match the pinned upstream or the exact
overlay output, and the installed link extension must be patched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().with_name("education-locks")
PATCHED_LINK_MINIMUM = (2, 10, 4)


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("-", 1)[0].split("."))


def security_lock_files(education: Path, *, verify_only: bool = False) -> None:
    """Write the reviewed frontend overlay, then install it frozen."""
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    if subprocess.check_output(["yarn", "--version"], text=True).strip() != manifest["yarn_version"]:
        raise ValueError("Education overlay requires the pinned Yarn version")
    # Validate every overlay source before touching the disposable checkout.
    sources = {}
    for relative, hashes in manifest["files"].items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 2:
            raise ValueError("Invalid Education overlay path")
        content = (ROOT / path).read_bytes()
        if hashlib.sha256(content).hexdigest() != hashes["security_sha256"]:
            raise ValueError("Education overlay integrity failure")
        sources[relative] = content
    pending = []
    for relative, hashes in manifest["files"].items():
        target = education / relative
        if target.is_symlink() or target.parent.is_symlink() or not target.is_file():
            raise ValueError("Education overlay target is missing or not a regular file")
        current = hashlib.sha256(target.read_bytes()).hexdigest()
        allowed = {hashes["security_sha256"]} if verify_only else set(hashes.values())
        if current not in allowed:
            raise ValueError("Education manifests drifted; refusing unreviewed dependency graph")
        pending.append((target, sources[relative]))
    if not verify_only:
        for target, content in pending:
            target.write_bytes(content)
        subprocess.run(["yarn", "install", "--frozen-lockfile", "--non-interactive"],
                       cwd=education / "frontend", check=True)
        security_lock_files(education, verify_only=True)


def verify_installed_link(education: Path) -> dict:
    """Every installed @tiptap/extension-link copy must be patched, and at least one must exist."""
    frontend = education / "frontend" / "node_modules"
    found = sorted(frontend.rglob("@tiptap/extension-link/package.json"))
    if not found:
        raise ValueError("No installed @tiptap/extension-link in the Education frontend")
    versions = {}
    for manifest_path in found:
        version = json.loads(manifest_path.read_text(encoding="utf-8"))["version"]
        versions[str(manifest_path.relative_to(education))] = version
        if _version_tuple(version) < PATCHED_LINK_MINIMUM:
            raise ValueError("Vulnerable @tiptap/extension-link remains in the Education frontend: " + version)
    return {"extension_link_copies": versions}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("education_app", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    security_lock_files(args.education_app, verify_only=args.verify)
    print(json.dumps(verify_installed_link(args.education_app), sort_keys=True))


if __name__ == "__main__":
    main()

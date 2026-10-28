#!/usr/bin/env python3
"""Apply the reviewed Frappe realtime (Socket.IO) dependency overlay.

The pinned Frappe root lockfile resolves the production Socket.IO server to
engine.io 6.5.4, ws 8.11.0 and socket.io-parser 4.2.4. Each of those versions is
inside the affected range of at least one advisory (see manifest.json). This
overlay replaces the root package.json and yarn.lock of the disposable Frappe
checkout with reviewed versions, installs them with a frozen lockfile, and then
verifies that every installed copy of the three packages is at or above the
fixed minimum.

Nothing is resolved here. Input digests must match either the pinned upstream
file (before apply) or the reviewed overlay (verify only). Any other content is
refused. The script never falls back to the upstream lock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().with_name("realtime-locks")
FILES = ("package.json", "yarn.lock")


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("-", 1)[0].split("+", 1)[0].split("."))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest() -> dict:
    return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def security_lock_files(frappe: Path, *, verify_only: bool = False) -> None:
    """Write the reviewed root overlay, then install it frozen (unless verify_only)."""
    manifest = _load_manifest()
    if subprocess.check_output(["yarn", "--version"], text=True).strip() != manifest["yarn_version"]:
        raise ValueError("Realtime overlay requires the pinned Yarn version")
    if set(manifest["files"]) != set(FILES):
        raise ValueError("Realtime overlay manifest must list exactly package.json and yarn.lock")

    # Validate every overlay source before touching the disposable checkout.
    sources: dict[str, bytes] = {}
    for relative, hashes in manifest["files"].items():
        content = (ROOT / relative).read_bytes()
        if hashlib.sha256(content).hexdigest() != hashes["security_sha256"]:
            raise ValueError("Realtime overlay integrity failure: " + relative)
        sources[relative] = content

    pending = []
    for relative, hashes in manifest["files"].items():
        target = frappe / relative
        if target.is_symlink() or not target.is_file():
            raise ValueError("Realtime overlay target is missing or not a regular file: " + relative)
        current = _sha256(target)
        allowed = {hashes["security_sha256"]} if verify_only else {hashes["upstream_sha256"], hashes["security_sha256"]}
        if current not in allowed:
            raise ValueError("Frappe realtime manifests drifted; refusing unreviewed dependency graph")
        pending.append((target, sources[relative]))

    if not verify_only:
        for target, content in pending:
            target.write_bytes(content)
        subprocess.run(["yarn", "install", "--frozen-lockfile", "--non-interactive"],
                       cwd=frappe, check=True)
        security_lock_files(frappe, verify_only=True)


def verify_installed_realtime(frappe: Path) -> dict:
    """Every installed copy of a patched package must be at or above its fixed minimum."""
    manifest = _load_manifest()
    modules = frappe / "node_modules"
    report: dict[str, dict[str, str]] = {}
    for name, minimum in manifest["fixed_minimums"].items():
        # Only real installed package roots (directly under a node_modules folder),
        # so vendored fixtures inside other packages cannot satisfy the check.
        found = sorted(p for p in modules.rglob(f"{name}/package.json")
                       if p.parent.parent.name == "node_modules")
        if not found:
            raise ValueError(f"No installed {name} in the Frappe root; the overlay did not materialize")
        versions: dict[str, str] = {}
        for manifest_path in found:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if data.get("name") != name:
                continue
            version = data["version"]
            # Reports are consumed by CI annotations and release evidence,
            # which use the container's canonical POSIX path spelling even
            # when a Windows host runs the contract tests.
            versions[manifest_path.relative_to(frappe).as_posix()] = version
            if _version_tuple(version) < _version_tuple(minimum):
                raise ValueError(f"Vulnerable {name} {version} remains in the Frappe root (minimum {minimum})")
        if not versions:
            raise ValueError(f"No verifiable installed {name} package.json in the Frappe root")
        report[name] = versions
    return {"installed": report, "fixed_minimums": manifest["fixed_minimums"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("frappe_app", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    security_lock_files(args.frappe_app, verify_only=args.verify)
    print(json.dumps(verify_installed_realtime(args.frappe_app), sort_keys=True))


if __name__ == "__main__":
    main()

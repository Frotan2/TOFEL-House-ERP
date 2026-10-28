#!/usr/bin/env python3
"""Integrity-pinned remediation of installed HRMS client dependencies.

Apply reviewed Yarn security locks to disposable HRMS/ERPNext checkouts, then
verify publisher code for the HRMS editor/parser before and after asset build.
Original source hashes and explicit overlay hashes remain independently auditable.
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
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen

PATCHES = {
    "prosemirror-view": ("1.42.3", "oTN7EtH+CpwxU9NrwEYWd0UZ4JUx7l048l5A2Xppm4p/60isZYLnth9QVQmC3VRIvdrIWCxwZSd+Uz791G31/w=="),
    "prosemirror-model": ("1.25.8", "BswA4BLSFEiORV6Vjj/yZBXDbos1zTEnhyeSSgT8psGFhstQS7UJ8/WOLiDos9Byaee27+tml0/DuMNxYR84zg=="),
    # GHSA-cqmj-92xf-r6r9, GHSA-677m-j7p3-52f9, GHSA-2m8v-j782-fhvr.
    # 4.2.7 stays within the upstream ~4.2.x dependency range.
    "socket.io-parser": ("4.2.7", "IH/iSeO9T6gz1KkFleGDWkG9N3dl4jXVYUtMhIqH10Md0ttMer8nUNWiP1DKuNrybD2xBrixLJdCC9J6ECoYkg=="),
}
# Hash of sorted relative file name + NUL + SHA256(file bytes), from the
# integrity-verified npm tarballs. Verify the *code*, not just package.json.
FILE_TREE_SHA256 = {
    # Recomputed from the SHA-512-integrity-verified npm archives on
    # 2026-10-23. The previous values described older archive contents and
    # rejected the current immutable publisher tarballs before patching.
    "prosemirror-view": "dcf389324798cd44ba0dfb99484c867d8926af48245c185f27893816ed601b49",
    "prosemirror-model": "769a68d022eb80af04f98ecfea0767ec573eb24952290658b5699ee07c8a844f",
    "socket.io-parser": "053e6f8dcc424388a8ac27d8d7262c87d29bc80d3f5898805a03e67dc57a079c",
}
# Parser 4.2.7 requires debug ~4.4.1 and debug requires ms ^2.1.3. The frozen
# upstream install has debug 4.3.4 and ms 2.1.2. Nest only these two verified
# transitive dependencies under the parser; do not change other consumers.
PARSER_DEPENDENCIES = {
    "debug": ("4.4.1", "KcKCqiftBJcZr++7ykoDIEwSa3XWowTfNPo92BYxjXiyYEVrUQh2aLyhxBCwww+heortUFxEJYcRzosstTEBYQ==",
              "f967bf4602f684cc8b2841996f94c580c63bea59cf4be7d04176b2d73ff659ec"),
    "ms": ("2.1.3", "6FlzubTLZG3J2a/NVCAleEhjzq5oxgHyaCU9yYXvcLsvoVaHJq/s5xXI6/XXP6tz7R9xAOtHnSO/tXtF3WRTlA==",
           "43ec4600f61993ecf77328010aedcc47a095217e91539695c3d90f72d13de2df"),
}


def tree_digest(folder: Path, *, exclude_nested_modules: bool = False) -> str:
    digest = hashlib.sha256()
    files = sorted(
        (p for p in folder.rglob("*") if p.is_file() or p.is_symlink()),
        key=lambda p: p.relative_to(folder).as_posix(),
    )
    if not files or any(p.is_symlink() for p in files):
        raise ValueError("Missing or symlinked dependency package files")
    for path in files:
        relative = path.relative_to(folder)
        if exclude_nested_modules and relative.parts[0] == "node_modules":
            continue  # The parser's separately verified debug/ms packages.
        digest.update(relative.as_posix().encode() + b"\0"
                      + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def installed_copies(hrms: Path, name: str) -> list[Path]:
    """Find each copy without following symlinks outside the disposable tree."""
    found = []
    for tree in (hrms / "frontend", hrms / "roster"):
        root = tree / "node_modules"
        if not root.is_dir():
            raise ValueError(f"Missing HRMS dependency root: {tree.name}")
        for manifest in root.rglob(f"{name}/package.json"):
            if manifest.is_symlink() or manifest.parent.is_symlink():
                raise ValueError("Symlinked dependency is not an auditable install")
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
            if tree_digest(folder, exclude_nested_modules=name == "socket.io-parser") != FILE_TREE_SHA256[name]:
                raise ValueError(f"Installed {name} code differs from the pinned publisher tarball")
            if name == "socket.io-parser":
                modules = folder / "node_modules"
                if (not modules.is_dir() or modules.is_symlink()
                        or {p.name for p in modules.iterdir()} != set(PARSER_DEPENDENCIES)):
                    raise ValueError("Missing or unexpected socket.io-parser dependencies")
                for dep, (required, _, expected) in PARSER_DEPENDENCIES.items():
                    target = modules / dep
                    if (not target.is_dir() or target.is_symlink()
                            or json.loads((target / "package.json").read_text()).get("version") != required
                            or json.loads((target / "package.json").read_text()).get("name") != dep
                            or tree_digest(target) != expected):
                        raise ValueError(f"Unverified socket.io-parser dependency: {dep}")
        counts[name] = len(copies)
    return counts


def publisher_tree(name: str, version: str, integrity: str,
                   expected_tree: str, root: Path) -> Path:
    """Unpack an exact, safe npm publisher tarball into a disposable directory."""
    url = f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz"
    data = urlopen(url, timeout=60).read()
    if hashlib.sha512(data).digest() != base64.b64decode(integrity):
        raise ValueError(f"Integrity mismatch for {name}")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive:
            path = Path(member.name)
            if (not path.parts or path.parts[0] != "package"
                    or ".." in path.parts or member.issym() or member.islnk()
                    or not (member.isfile() or member.isdir())):
                raise ValueError(f"Unsafe npm tarball for {name}")
        archive.extractall(root)
    extracted = root / "package"
    manifest = json.loads((extracted / "package.json").read_text())
    if manifest.get("name") != name or manifest.get("version") != version:
        raise ValueError(f"Unexpected npm package for {name}")
    if tree_digest(extracted) != expected_tree:
        raise ValueError(f"Unexpected file tree for {name}")
    return extracted


def patch(hrms: Path) -> dict[str, int]:
    # Preflight every copy and every publisher archive before touching the
    # installed tree. No real site data or secrets are read by this helper.
    copies = {name: installed_copies(hrms, name) for name in PATCHES}
    for name, folders in copies.items():
        if not folders:
            raise ValueError(f"No installed {name}; refusing vacuous remediation")
    with tempfile.TemporaryDirectory() as tmp:
        source = {}
        for name, (version, integrity) in PATCHES.items():
            source[name] = publisher_tree(
                name, version, integrity, FILE_TREE_SHA256[name], Path(tmp) / name)
        nested = {}
        for name, (version, integrity, digest) in PARSER_DEPENDENCIES.items():
            nested[name] = publisher_tree(name, version, integrity, digest, Path(tmp) / name)
        for name, folders in copies.items():
            for folder in folders:
                shutil.rmtree(folder)
                shutil.copytree(source[name], folder)
                if name == "socket.io-parser":
                    for dep, extracted in nested.items():
                        shutil.copytree(extracted, folder / "node_modules" / dep)
    return verify(hrms)



def security_lock_files(hrms: Path, *, verify_only: bool = False, banking: bool = False) -> None:
    """Apply reviewed Yarn-generated manifests/locks to the disposable app only.

    Source hashes must match the pinned upstream or our exact security output.
    No resolution is performed in CI or on the owner's PC: installs are frozen.
    """
    root = Path(__file__).resolve().with_name("banking-locks" if banking else "hrms-locks")
    manifest = json.loads((root / "manifest.json").read_text())
    if subprocess.check_output(["yarn", "--version"], text=True).strip() != manifest["yarn_version"]:
        raise ValueError("Security lockfiles require the pinned Yarn version")
    pending = []
    for relative, hashes in manifest["files"].items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 2:
            raise ValueError("Invalid security lockfile path")
        target = hrms / path
        content = (root / path).read_bytes()
        if hashlib.sha256(content).hexdigest() != hashes["security_sha256"]:
            raise ValueError("Security lockfile integrity failure")
        current = hashlib.sha256(target.read_bytes()).hexdigest()
        allowed = {hashes["security_sha256"]} if verify_only else set(hashes.values())
        if current not in allowed or target.is_symlink() or target.parent.is_symlink():
            raise ValueError("HRMS manifests drifted; refusing unreviewed dependency graph")
        pending.append((target, content))
    if not verify_only:
        for target, content in pending:
            target.write_bytes(content)
        for tree in (("banking",) if banking else ("frontend", "roster")):
            subprocess.run(["yarn", "install", "--frozen-lockfile", "--non-interactive"],
                           cwd=hrms / tree, check=True)
        security_lock_files(hrms, verify_only=True, banking=banking)



EDITOR_PATH = "src/components/TextEditor/TextEditor.vue"
EDITOR_ORIGINAL_SHA256 = "59eb76d3a3d067ddbe2954eb0c576ba7aa013530db3e7335231ddd2b27316ca4"
EDITOR_PATCHED_SHA256 = "462f87ebf5791eefc7029ae82622e0b26e8f1a6525859a9b3780b5c2083d8a74"
EDITOR_BEFORE = "          let dom = document.createElement('div')\n          dom.innerHTML = markdownToHTML(text)"
EDITOR_AFTER = "          // Parse in an inert document: image handlers can execute even on a\n          // disconnected element created in the live document, before the\n          // ProseMirror schema has a chance to discard hostile attributes.\n          let dom = new window.DOMParser().parseFromString(\n            markdownToHTML(text), 'text/html',\n          ).body"


def secure_markdown_paste(hrms: Path, *, verify_only: bool = False) -> None:
    """Close pre-schema execution in the pinned Frappe UI Markdown paste path."""
    copies = installed_copies(hrms, "frappe-ui")
    if len(copies) < 2:
        raise ValueError("Missing shipped HRMS Frappe UI editors")
    pending = []
    for folder in copies:
        if json.loads((folder / "package.json").read_text()).get("version") != "0.1.105":
            raise ValueError("Unreviewed Frappe UI editor version")
        target = folder / EDITOR_PATH
        if target.is_symlink():
            raise ValueError("Symlinked editor source")
        source = target.read_bytes()
        digest = hashlib.sha256(source).hexdigest()
        if digest == EDITOR_PATCHED_SHA256:
            continue
        if verify_only or digest != EDITOR_ORIGINAL_SHA256:
            raise ValueError("Unverified Frappe UI Markdown paste source")
        text = source.decode()
        if text.count(EDITOR_BEFORE) != 1:
            raise ValueError("Markdown parser anchor changed")
        updated = text.replace(EDITOR_BEFORE, EDITOR_AFTER).encode()
        if hashlib.sha256(updated).hexdigest() != EDITOR_PATCHED_SHA256:
            raise ValueError("Unexpected Markdown parser patch output")
        pending.append((target, updated))
    for target, content in pending:
        target.write_bytes(content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("hrms_app", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--banking", action="store_true", help="Apply ERPNext banking locks instead of HRMS")
    args = parser.parse_args()
    security_lock_files(args.hrms_app, verify_only=args.verify, banking=args.banking)
    if args.banking:
        print("ERPNext banking security locks verified")
        return
    secure_markdown_paste(args.hrms_app, verify_only=args.verify)
    print(json.dumps(verify(args.hrms_app) if args.verify else patch(args.hrms_app), sort_keys=True))


if __name__ == "__main__":
    main()

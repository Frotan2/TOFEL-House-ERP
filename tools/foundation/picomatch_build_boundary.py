"""Keep the reviewed Picomatch build dependency out of the customer runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil


# npm publisher tarballs, lib/parse.js, reviewed for CVE-2026-112366.
PARSER_HASHES = {
    "2.3.1": "def9662f49cd241d7f0f22c295aa5d7ac6541fc983a9394eb45d57b486de2f39",
    "2.3.2": "3a91656f440069aa8f8e15c9d695b9f6b2209df1eab2be8127c72cbcca45ff5f",
    "4.0.7": "4e1e05447668aa1e94366c5516a2bcd8f5fff800cc92b1d0cd7d77703b8618c4",
}
PARSER_LITERALS = (b"Input length:", b"exceeds maximum allowed length:")


def _fail_on_walk_error(error):
    raise error


def _audited_packages(root: Path) -> list[Path]:
    packages = []
    for parent, dirs, files in os.walk(root, onerror=_fail_on_walk_error):
        parent = Path(parent)
        if parent.name == "node_modules" and {"picomatch", "picomatch.js"}.intersection(files):
            raise ValueError(f"Unreviewed Picomatch module layout: {parent}")
        dirs[:] = [name for name in dirs if name not in (".git", ".bin", "__pycache__")]
        for name in tuple(dirs):
            folder = parent / name
            if folder.is_symlink():
                # Frappe's public/node_modules aliases point back to these same
                # audited roots. Other dependency directory links can hide copies.
                target = folder.parent.parent.parent / "node_modules"
                public_alias = (name == "node_modules" and parent.name == "public"
                                and target.is_dir() and not target.is_symlink()
                                and folder.resolve(strict=True) == target.resolve(strict=True))
                if "node_modules" in folder.parts and not public_alias:
                    raise ValueError(f"Linked dependency directory: {folder}")
                dirs.remove(name)
                continue
            if name != "picomatch" or parent.name != "node_modules":
                continue
            manifest = folder / "package.json"
            parser = folder / "lib/parse.js"
            if any(path.is_symlink() for path in (manifest, parser, parser.parent)):
                raise ValueError(f"Linked Picomatch package files: {folder}")
            release = json.loads(manifest.read_text(encoding="utf-8"))
            content = parser.read_bytes()
            if (release.get("name") != "picomatch"
                    or hashlib.sha256(content).hexdigest() != PARSER_HASHES.get(release.get("version"))
                    or not all(literal in content for literal in PARSER_LITERALS)):
                raise ValueError(f"Unreviewed Picomatch package: {folder}")
            packages.append(folder)
            dirs.remove(name)
    return packages


def _verify_emitted_scripts(root: Path) -> int:
    count = 0
    for parent, dirs, files in os.walk(root, onerror=_fail_on_walk_error):
        dirs[:] = [name for name in dirs if name != "node_modules"]
        for name in files:
            path = Path(parent) / name
            if path.suffix not in {".js", ".mjs", ".cjs", ".map"}:
                continue
            if path.is_symlink():
                raise ValueError(f"Linked emitted script: {path}")
            content = path.read_bytes()
            if (all(literal in content for literal in PARSER_LITERALS)
                    or b"node_modules/picomatch/" in content):
                raise ValueError(f"Picomatch was emitted into a browser asset: {path}")
            count += 1
    return count


def enforce(apps: Path, global_assets: Path) -> tuple[int, int]:
    """Verify provider assets before removing the reviewed build-only copies."""
    if any(not path.is_dir() or path.is_symlink() for path in (apps, global_assets)):
        raise ValueError("Expected real provider app and global asset directories")
    packages = _audited_packages(apps) + _audited_packages(global_assets)
    if not packages:
        raise ValueError("Expected reviewed Picomatch copies in the provider build")
    public_roots = [app / app.name / "public" for app in apps.iterdir()]
    public_roots = [path for path in public_roots if path.is_dir()]
    scripts = sum(_verify_emitted_scripts(path) for path in (*public_roots, global_assets))
    if not scripts:
        raise ValueError("Expected emitted browser scripts in the provider build")
    for package in packages:
        shutil.rmtree(package)
    return len(packages), scripts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apps", type=Path)
    parser.add_argument("global_assets", type=Path)
    args = parser.parse_args()
    packages, scripts = enforce(args.apps, args.global_assets)
    print(f"Removed {packages} build-only Picomatch copies after inspecting {scripts} browser assets")

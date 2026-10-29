"""Hash-pinned deepmerge 4.3.1 prototype-setter mitigation (GHSA-gcqx-w48m-w2h4).

Run on disposable installed app trees before compiling assets, and verify after.
All three publisher entry points are checked before any writes occur.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

HASHES = json.loads(Path(__file__).with_name("deepmerge-hashes.json").read_text())
REQUIRED_CONSUMERS = ("education/frontend", "hrms/frontend")
# The reviewed Tiptap overlay removes Education's trailing-node dependency.
# Absence is allowed only for this exact reviewed dependency graph.
EDUCATION_WITHOUT_DEEPMERGE = "0b43016c9285f967f6602fbaba989fb864c7f3712bd0ad7ae02d80497d97b998"


def _linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _copies(root: Path):
    def fail(error):
        raise error

    for base, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        folder = Path(base)
        for name in list(dirs):
            child = folder / name
            if name in (".git", ".bin", "__pycache__"):
                dirs.remove(name)
            elif _linked(child):
                # bench build creates this public alias to the same root
                # dependency tree that the walk audits separately. Accept
                # only the exact native alias and exact regular target.
                native_alias = root / "frappe/frappe/public/node_modules"
                native_target = root / "frappe/node_modules"
                if (child == native_alias and native_target.is_dir()
                        and not any(_linked(p) for p in (native_target, *native_target.parents))
                        and child.resolve(strict=True) == native_target.resolve(strict=True)):
                    dirs.remove(name)
                    continue
                # Yarn's .bin links are launchers, never dependency roots.
                # Reject links that could hide copies from a non-following walk.
                if "node_modules" in child.relative_to(root).parts:
                    raise ValueError("Linked dependency directory: " + str(child))
                dirs.remove(name)
        if folder.name == "deepmerge" and folder.parent.name == "node_modules":
            if "package.json" not in files:
                raise ValueError("Missing deepmerge package manifest")
            yield folder / "package.json"


def secure(root: Path, *, verify_only: bool = False, apps: bool = False) -> int:
    if not root.is_dir() or any(_linked(p) for p in (root, *root.parents)):
        raise ValueError("Missing or linked dependency scan root")
    pending = []
    copies = 0
    consumers = set()
    if apps:
        for relative in REQUIRED_CONSUMERS:
            required = root / relative / "node_modules"
            if not required.is_dir() or any(_linked(p) for p in (required, *required.parents)):
                raise ValueError("Missing or linked required consumer: " + relative)
    for manifest in _copies(root):
        folder = manifest.parent
        if folder.parent.name != "node_modules":
            continue
        if any(p.is_symlink() for p in (manifest, folder, *folder.parents)):
            raise ValueError("Symlinked deepmerge path")
        package = json.loads(manifest.read_text())
        if package.get("name") != "deepmerge" or package.get("version") != "4.3.1":
            raise ValueError("Unreviewed deepmerge package")
        copies += 1
        for relative in REQUIRED_CONSUMERS:
            if (root / relative / "node_modules") in folder.parents:
                consumers.add(relative)
        for name, hashes in HASHES.items():
            target = folder / name
            if target.is_symlink() or target.parent.is_symlink():
                raise ValueError("Symlinked deepmerge entry point")
            data = target.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest == hashes["patched"]:
                continue
            if verify_only or digest != hashes["upstream"]:
                raise ValueError("Unverified deepmerge code: " + str(target))
            text, count = re.subn(
                r"destination\[key\] = ([^;\n]+)",
                r"Object.defineProperty(destination, key, { value: \1, enumerable: true, configurable: true, writable: true })",
                data.decode(),
            )
            output = text.encode()
            if count != 3 or hashlib.sha256(output).hexdigest() != hashes["patched"]:
                raise ValueError("Unexpected deepmerge patch output")
            pending.append((target, output))
    if not copies:
        raise ValueError("No installed deepmerge copies; refusing empty verification")
    if apps:
        if "hrms/frontend" not in consumers:
            raise ValueError("Missing deepmerge in required HRMS consumer")
        if "education/frontend" not in consumers:
            lock = root / "education/frontend/yarn.lock"
            if not lock.is_file() or _linked(lock) or hashlib.sha256(lock.read_bytes()).hexdigest() != EDUCATION_WITHOUT_DEEPMERGE:
                raise ValueError("Missing deepmerge in unreviewed Education graph")
    for target, output in pending:
        target.write_bytes(output)
    return copies


def receipt(root: Path, *, assets: bool = False) -> dict:
    """Probe the shipped CJS/UMD entry points, record exact code/asset identities."""
    records = []
    probe = r'''
const assert = require('node:assert/strict');
const path = require('node:path');
const folder = process.argv[1];
assert.equal(require.resolve(folder), path.join(folder, 'dist', 'cjs.js'));
for (const file of ['dist/cjs.js', 'dist/umd.js']) {
  const merge = require(path.join(folder, file));
  const poison = JSON.parse('{"__proto__":{"admin":true},"constructor":{"prototype":{"admin":true}}}');
  for (const result of [merge(poison, {}), merge(Object.create(null), poison),
    merge({}, {nested: poison}).nested, merge([], [poison])[0]]) {
    assert.equal(Object.getPrototypeOf(result), Object.prototype);
    assert.equal(result.admin, undefined);
    assert.equal({}.admin, undefined);
  }
  assert.deepEqual(merge({a:{b:1},list:[1]}, {a:{c:2},list:[2]}), {a:{b:1,c:2},list:[1,2]});
}
'''
    for manifest in _copies(root):
        folder = manifest.parent
        subprocess.run(["node", "-e", probe, str(folder.resolve())], check=True, capture_output=True, text=True)
        records.append({"package": folder.relative_to(root).as_posix(), "resolved_main": "dist/cjs.js",
                        "sha256": {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in HASHES}})
    emitted = {}
    if assets:
        for relative in REQUIRED_CONSUMERS:
            app, tree = relative.split("/")
            public = root / app / app / "public" / tree
            files = sorted(public.rglob("*.js"))
            if not files:
                raise ValueError("Missing emitted JavaScript assets: " + relative)
            emitted[relative] = {}
            for path in files:
                if any(_linked(p) for p in (path, *path.parents)):
                    raise ValueError("Linked emitted asset")
                emitted[relative][path.relative_to(public).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"status": "pass", "copies": sorted(records, key=lambda r: r["package"]), "emitted_asset_sha256": emitted,
            "scope": "Resolved shipped distribution probes and compiled asset identities; module inclusion is separate Vite graph evidence"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--apps", action="store_true", help="Require both pinned Education/HRMS consumers")
    parser.add_argument("--report", type=Path, help="Write code and resolved-distribution probe evidence")
    parser.add_argument("--assets", action="store_true", help="Require and hash emitted frontend JavaScript")
    args = parser.parse_args()
    count = secure(args.root, verify_only=args.verify, apps=args.apps)
    if args.report:
        args.report.write_text(json.dumps(receipt(args.root, assets=args.assets), indent=2) + "\n")
    print("Verified deepmerge copies:", count)

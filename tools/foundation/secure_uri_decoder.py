"""Hash-verified upstream decoder backport for GHSA-qr28-fpjm-wq7f.

Keep the pinned CommonJS manifest/lock and plus conversion, replacing only the
decoder with upstream 0.5.1. Reject every unknown input before changing a copy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

DATA = Path(__file__).with_name("decoder")
HASHES = json.loads((DATA / "hashes.json").read_text())
APPS = ("frappe", "erpnext", "education", "payments", "hrms", "foundation_security", "toefl_house")


def linked(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def copies(root):
    aliases = {root / app / app / "public/node_modules": root / app / "node_modules" for app in APPS}

    def fail(error):
        raise error

    for base, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        folder = Path(base)
        for name in list(dirs):
            child = folder / name
            if name in (".git", ".bin", "__pycache__"):
                dirs.remove(name)
            elif linked(child):
                target = aliases.get(child)
                if (target is not None and target.is_dir()
                        and not any(linked(p) for p in (target, *target.parents))
                        and child.resolve(strict=True) == target.resolve(strict=True)):
                    dirs.remove(name)
                    continue
                if "node_modules" in child.relative_to(root).parts:
                    raise ValueError("Linked dependency directory")
                dirs.remove(name)
        if folder.name == "decode-uri-component" and folder.parent.name == "node_modules":
            if "package.json" not in files:
                raise ValueError("Missing decoder manifest")
            yield folder


def secure(root, *, verify=False):
    if not root.is_dir() or any(linked(p) for p in (root, *root.parents)):
        raise ValueError("Missing or linked scan root")
    patched = (DATA / "decode-uri-component-0.5.1.cjs").read_bytes()
    if hashlib.sha256(patched).hexdigest() != HASHES["cjs_0_5_1_sha256"]:
        raise ValueError("Unverified upstream backport payload")
    pending, found = [], []
    for folder in copies(root):
        manifest, target = folder / "package.json", folder / "index.js"
        if any(linked(p) for p in (manifest, target, folder, *folder.parents)):
            raise ValueError("Linked decoder entry point")
        if hashlib.sha256(manifest.read_bytes()).hexdigest() != HASHES["original_package_json_sha256"]:
            raise ValueError("Unreviewed decoder manifest")
        current = hashlib.sha256(target.read_bytes()).hexdigest()
        if current != HASHES["cjs_0_5_1_sha256"]:
            if verify or current != HASHES["original_0_2_2_sha256"]:
                raise ValueError("Unreviewed decoder source")
            pending.append(target)
        found.append(folder)
    if not found:
        raise ValueError("No installed decoder copies; refusing empty verification")
    for target in pending:
        target.write_bytes(patched)
    return found


PROBE = r"""
const assert = require('node:assert/strict');
const path = require('node:path');
const folder = process.argv[1];
assert.equal(require.resolve(folder), path.join(folder, 'index.js'));
const decode = require(folder);
assert.equal(decode('a+b%2Bc'), 'a b+c');
assert.equal(decode('%D8%B3%D9%84%D8%A7%D9%85'), 'سلام');
assert.equal(decode('%25C3%25A5%zz'), '%C3%A5%zz');
assert.throws(() => decode(null), TypeError);
// Both upstream denial-of-service patterns must finish within the child timeout.
decode('%C2'.repeat(32000));
let payload = '';
for (let i=0; i<32000; i++) payload += '%' + Math.floor(i/256).toString(16).padStart(2,'0') + '%' + (i%256).toString(16).padStart(2,'0') + 'x';
decode(payload + '%zz');
"""


def receipt(root, found):
    rows = []
    for folder in found:
        subprocess.run(["node", "-e", PROBE, str(folder.resolve())], check=True, capture_output=True, timeout=10)
        rows.append({"package": folder.relative_to(root).as_posix(),
                     "index_sha256": hashlib.sha256((folder / "index.js").read_bytes()).hexdigest()})
    return {"status": "pass", "upstream_commit": HASHES["upstream_commit"], "copies": sorted(rows, key=lambda row: row["package"]),
            "scope": "All installed decoder copies, unchanged publisher manifests, resolved CJS API and bounded hostile inputs"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    found = secure(args.root, verify=args.verify)
    result = receipt(args.root, found)
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + "\n")
    print("Verified decoder copies:", len(found))

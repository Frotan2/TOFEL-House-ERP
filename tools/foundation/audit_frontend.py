#!/usr/bin/env python3
"""Query npm advisories for an installed, public-package frontend dependency tree.

Sends package names/versions to npm, not source code or credentials. Do not use on
private dependencies without approval. Findings are advisory matches, not proof
of reachable exploits. Exits 1 if advisories are returned; transport errors fail.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import datetime as dt
import json
from pathlib import Path
from urllib.request import Request, urlopen

ENDPOINT = "https://registry.npmjs.org/-/npm/v1/security/advisories/bulk"


def inventory(root: Path) -> dict:
    versions: dict[str, set[str]] = defaultdict(set)
    seen = set()

    def visit(modules: Path) -> None:
        if not modules.is_dir() or modules.resolve() in seen:
            return
        seen.add(modules.resolve())
        for folder in modules.iterdir():
            packages = folder.iterdir() if folder.is_dir() and folder.name.startswith("@") else [folder]
            for package in packages:
                manifest = package / "package.json"
                if not manifest.is_file():
                    continue
                data = json.loads(manifest.read_text())
                if data.get("name") and data.get("version"):
                    versions[data["name"]].add(data["version"])
                visit(package / "node_modules")

    visit(root)
    if not versions:
        raise ValueError("No installed package manifests found; refusing an empty audit")
    return {name: sorted(values) for name, values in sorted(versions.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("node_modules", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    versions = inventory(args.node_modules)
    request = Request(ENDPOINT, data=json.dumps(versions).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=30) as response:
        advisories = json.load(response)
    report = {
        "scope": "Installed frontend dependencies only; not exploit validation or full-stack SBOM",
        "source": ENDPOINT,
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "versions_submitted": versions,
        "package_names_submitted": len(versions),
        "packages_with_advisories": len(advisories),
        "advisories": advisories,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Queried {len(versions)} package names; {len(advisories)} returned advisory entries")
    return 1 if advisories else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Query npm advisories for an installed, public-package frontend dependency tree.

Sends package names/versions to npm, not source code or credentials. Do not use on
private dependencies without approval. Raw advisories are triaged against the
SEC-DEPS-01 per-finding disposition table: pre-existing matches resolve to their
recorded disposition (MITIGATED / NOT_REACHABLE / BUILD_ONLY / DEV_ONLY /
INSTALL_ONLY / BROWSER_SELF_DENIAL) and do not fail the build; genuinely new,
untriaged advisories exit non-zero so CI surfaces regressions.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import datetime as dt
import json
from pathlib import Path
from urllib.request import Request, urlopen

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from advisory_triage import triage_npm, overall_status  # noqa: E402

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
        "scope": ("Installed frontend dependencies; advisory-version matches are "
                  "triaged against the SEC-DEPS-01 dispositions; untriaged "
                  "advisories fail closed."),
        "source": ENDPOINT,
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "versions_submitted": versions,
        "package_names_submitted": len(versions),
        "packages_with_advisories": len(advisories),
        "advisories": advisories,
    }
    triage_result = triage_npm(advisories)
    report["triage"] = triage_result
    report["status"] = overall_status(npm_result=triage_result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    untriaged = len(triage_result["untriaged"])
    open_count = triage_result["open"]
    print(f"Queried {len(versions)} package names; {len(advisories)} packages returned "
          f"advisory entries ({triage_result['closed']} closed by triage, "
          f"{open_count} open, {untriaged} untriaged)")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Inventory resolved hosted Foundation dependencies and query public advisories.

The tool runs with the already-created Bench interpreter. It inventories every
installed Python distribution in that interpreter, every supplied installed
Node dependency root, and the exact container references supplied by the
caller. Only public package names and versions are sent to OSV/npm; it never
sends source, site configuration, credentials, backup contents, or files.

A finding is an advisory-version match, not proof of reachability, exploit,
severity in the selected deployment, or production approval. Container and OS
package CVEs are deliberately out of scope unless a separate approved scanner
and image/host boundary are supplied.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import datetime as dt
from importlib import metadata
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.request import Request, urlopen

from audit_frontend import inventory as installed_node_inventory

NPM_ADVISORY_ENDPOINT = "https://registry.npmjs.org/-/npm/v1/security/advisories/bulk"
OSV_BATCH_ENDPOINT = "https://api.osv.dev/v1/querybatch"
OSV_BATCH_SIZE = 500


def canonical_pypi_name(name: str) -> str:
    """Use the conventional PyPI spelling without depending on packaging."""
    return re.sub(r"[-_.]+", "-", name).lower()


def installed_python_inventory() -> dict[str, list[str]]:
    """Return every distribution visible to the interpreter executing this tool."""
    packages: dict[str, set[str]] = defaultdict(set)
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if name and distribution.version:
            packages[canonical_pypi_name(name)].add(distribution.version)
    if not packages:
        raise RuntimeError("No installed Python distributions found; refusing empty audit")
    return {name: sorted(versions) for name, versions in sorted(packages.items())}


def combined_node_inventory(roots: list[Path]) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """Merge installed Node manifests, retaining missing roots as coverage evidence."""
    packages: dict[str, set[str]] = defaultdict(set)
    root_results: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            root_results.append({"path": str(root), "status": "missing"})
            continue
        try:
            discovered = installed_node_inventory(root)
        except ValueError as exc:
            # A built app may legitimately have an empty node_modules directory.
            # Preserve that coverage fact, but do not prevent later supplied roots
            # from being inventoried. Other malformed-manifest errors remain fatal.
            if str(exc) != "No installed package manifests found; refusing an empty audit":
                raise
            root_results.append({"path": str(root), "status": "empty"})
            continue
        root_results.append({"path": str(root), "status": "collected", "package_names": len(discovered)})
        for name, versions in discovered.items():
            packages[name].update(versions)
    if not packages:
        raise RuntimeError("No installed Node package manifests found in supplied roots")
    return {name: sorted(versions) for name, versions in sorted(packages.items())}, root_results


def post_json(endpoint: str, payload: dict[str, Any], *, timeout: int = 60) -> Any:
    request = Request(endpoint, data=json.dumps(payload, sort_keys=True).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def npm_advisories(packages: dict[str, list[str]]) -> dict[str, Any]:
    findings = post_json(NPM_ADVISORY_ENDPOINT, packages)
    if not isinstance(findings, dict):
        raise RuntimeError("npm advisory endpoint returned a non-object response")
    return findings


def _osv_finding(package: str, version: str, vulnerability: dict[str, Any]) -> dict[str, Any]:
    """Retain stable identifying information, avoiding needlessly large raw reports."""
    database = vulnerability.get("database_specific") or {}
    return {
        "package": package,
        "version": version,
        "id": vulnerability.get("id"),
        "aliases": sorted(str(alias) for alias in vulnerability.get("aliases", []) if alias),
        "summary": vulnerability.get("summary"),
        "modified": vulnerability.get("modified"),
        "severity": database.get("severity"),
    }


def osv_pypi_advisories(packages: dict[str, list[str]]) -> dict[str, Any]:
    queries = [
        {"package": {"ecosystem": "PyPI", "name": name}, "version": version}
        for name, versions in packages.items() for version in versions
    ]
    findings: list[dict[str, Any]] = []
    for start in range(0, len(queries), OSV_BATCH_SIZE):
        batch = queries[start:start + OSV_BATCH_SIZE]
        response = post_json(OSV_BATCH_ENDPOINT, {"queries": batch})
        results = response.get("results") if isinstance(response, dict) else None
        if not isinstance(results, list) or len(results) != len(batch):
            raise RuntimeError("OSV response does not match submitted Python dependency queries")
        for query, result in zip(batch, results):
            vulnerabilities = result.get("vulns", []) if isinstance(result, dict) else []
            if not isinstance(vulnerabilities, list):
                raise RuntimeError("OSV vulnerability response is malformed")
            package = query["package"]["name"]
            version = query["version"]
            for vulnerability in vulnerabilities:
                if not isinstance(vulnerability, dict) or not vulnerability.get("id"):
                    raise RuntimeError("OSV returned a vulnerability without an identifier")
                findings.append(_osv_finding(package, version, vulnerability))
    return {"endpoint": OSV_BATCH_ENDPOINT, "queries": len(queries), "findings": findings}


def parse_images(values: list[str]) -> dict[str, str]:
    images: dict[str, str] = {}
    for value in values:
        name, separator, reference = value.partition("=")
        if not separator or not name or "@sha256:" not in reference:
            raise ValueError("Container image must be component=reference@sha256:<digest>")
        if name in images:
            raise ValueError("Duplicate container image component: " + name)
        images[name] = reference
    return dict(sorted(images.items()))


def report_for(args: argparse.Namespace) -> dict[str, Any]:
    python_packages = installed_python_inventory()
    node_packages, node_roots = combined_node_inventory(args.node_modules)
    npm = npm_advisories(node_packages)
    osv = osv_pypi_advisories(python_packages)
    npm_entries = sum(len(value) for value in npm.values())
    report = {
        "scope": "Resolved Bench Python and supplied installed Node dependency trees plus pinned container references; advisory matches only, not exploit/reachability, full SBOM, OS packages, container CVE scan, or production approval",
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "python": {
            "interpreter": sys.executable,
            "package_names": len(python_packages),
            "packages": python_packages,
            "osv": osv,
        },
        "node": {
            "roots": node_roots,
            "package_names": len(node_packages),
            "packages": node_packages,
            "npm_advisory_endpoint": NPM_ADVISORY_ENDPOINT,
            "packages_with_advisories": len(npm),
            "advisory_entries": npm_entries,
            "advisories": npm,
        },
        "containers": {
            "pinned_references": parse_images(args.image),
            "status": "inventory_only",
            "limit": "No container-image or host-package vulnerability scanner is configured by this tool.",
        },
    }
    report["status"] = "fail" if npm_entries or osv["findings"] else "pass"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-modules", type=Path, action="append", required=True,
                        help="Installed node_modules root; repeat for every built app root")
    parser.add_argument("--image", action="append", default=[], metavar="COMPONENT=REFERENCE",
                        help="Pinned container reference (must include @sha256); repeat as needed")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = report_for(args)
    except Exception as exc:
        report = {
            "scope": "Resolved dependency audit attempted; transport/inventory failure is not a pass",
            "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if report["status"] == "error":
        print("Dependency audit ERROR: " + report["error"], file=sys.stderr)
        return 2
    print("Dependency audit: Python OSV findings=" + str(len(report["python"]["osv"]["findings"])) +
          ", Node npm advisory entries=" + str(report["node"]["advisory_entries"]))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

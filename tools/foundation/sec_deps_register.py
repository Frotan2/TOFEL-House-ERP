#!/usr/bin/env python3
"""Assemble the readable SEC-DEPS-01 finding register from retained evidence.

The finding SET is authoritative from the retained resolved-stack evidence
(`docs/engineering/evidence/phase-2/resolved-stack-advisory-2026-09-16.json`,
SHA-256 verified transport of hosted run 35084695840): 14 PyPI/OSV records and
97 npm advisory records. This tool adds NOTHING to that set and removes
NOTHING from it — `tests/foundation/test_sec_deps_register.py` enforces exact
set equality, so a finding can neither be invented nor silently dropped.

What this tool adds is READABILITY for the 14 PyPI/OSV records, whose retained
summaries and severities are null: each record below was resolved against the
public OSV API on 2026-09-19 and the returned summary, severity, CWE, aliases
and fixed-version range events were transcribed verbatim. The npm records were
already readable in the retained evidence (title, severity, CWE, vulnerable
range) and are rolled up per package unchanged.

This register is NOT a fresh audit of the current pins, NOT exploitability or
reachability proof, NOT a full SBOM, and NOT a gate change. SEC-DEPS-01 stays
UPSTREAM-BLOCKED / REJECT until the owner re-decides on the basis of readable
findings. Reachability in the selected local-server + Tailscale deployment is
explicitly NOT established for any finding recorded here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RETAINED_PATH = ROOT / "docs/engineering/evidence/phase-2/resolved-stack-advisory-2026-09-16.json"
REGISTER_PATH = ROOT / "docs/engineering/evidence/sec-deps-01/readable-register-2026-09-19.json"

ENRICHED_AT_UTC = "2026-09-19"
ENRICHMENT_SOURCE = "https://api.osv.dev/v1/vulns/<id> (public OSV API, fetched 2026-09-19)"

# Seven unique vulnerabilities behind the fourteen retained PyPI/OSV records.
# Each entry transcribes the OSV record verbatim; `records` names the retained
# record ids that describe this vulnerability (GHSA + PYSEC pairs).
PYPI_VULNS = [
    {
        "vuln_key": "pdfkit-path-traversal-from-string",
        "package": "pdfkit",
        "installed_version": "1.0.0",
        "records": ["GHSA-9g3x-6x24-vf9f", "PYSEC-2026-2860"],
        "summary": "pdfkit: Path traversal in from_string",
        "severity": "HIGH",
        "cvss": "CVSS:3.1/AV:L/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "cwe": ["CWE-120", "CWE-22"],
        "cve": "CVE-2025-26240",
        "fixed_version": None,
        "fix_status": "NO FIX LISTED (last_affected 1.0.0, which is the installed version)",
        "detail": ("In JazzCore python-pdfkit 1.0.0, the from_string method enables the "
                   "execution of JavaScript code within the context of the server application "
                   "and the exfiltration of local files."),
        "deployment_note": ("Consumer class: server-side PDF/print rendering (upstream). The R3 "
                            "print-path containment checks cover download_pdf denial, but whether "
                            "untrusted input reaches pdfkit from_string in the selected deployment "
                            "is NOT established by this register."),
    },
    {
        "vuln_key": "pypdf-outline-resource-exhaustion",
        "package": "pypdf",
        "installed_version": "6.15.0",
        "records": ["GHSA-23w6-3w8w-8484", "PYSEC-2026-3910"],
        "summary": "pypdf: Possible long runtimes/large memory usage when retrieving outlines",
        "severity": "MODERATE",
        "cvss": "CVSS:4.0/AV:L/AC:L/AT:N/PR:N/UI:P/VC:N/VI:N/VA:L/SC:N/SI:N/SA:N",
        "cwe": ["CWE-405", "CWE-834"],
        "cve": "CVE-2026-84310",
        "fixed_version": "6.16.1",
        "fix_status": "FIXED in 6.16.1 (installed 6.15.0 is affected)",
        "detail": ("A crafted PDF leads to long runtimes and large memory consumption when "
                   "accessing outlines with many entries or nested outlines with long "
                   "re-used nesting paths."),
        "deployment_note": ("Crafted-PDF denial of service. Whether attacker-influenced PDFs reach "
                            "pypdf outline handling in the selected deployment is NOT established."),
    },
    {
        "vuln_key": "pypdf-xform-resource-exhaustion",
        "package": "pypdf",
        "installed_version": "6.15.0",
        "records": ["GHSA-763m-79hh-57f2", "PYSEC-2026-3911"],
        "summary": "pypdf: Possible long runtimes/large memory usage when extracting XForm objects",
        "severity": "MODERATE",
        "cvss": "CVSS:4.0/AV:L/AC:L/AT:N/PR:N/UI:P/VC:N/VI:N/VA:L/SC:N/SI:N/SA:N",
        "cwe": ["CWE-834"],
        "cve": "CVE-2026-84311",
        "fixed_version": "6.16.1",
        "fix_status": "FIXED in 6.16.1 (installed 6.15.0 is affected)",
        "detail": ("A crafted PDF leads to long runtimes and large memory consumption when "
                   "extracting text of a page with many XForm objects, some re-used."),
        "deployment_note": ("Crafted-PDF denial of service. Whether attacker-influenced PDFs reach "
                            "pypdf XForm handling in the selected deployment is NOT established."),
    },
    {
        "vuln_key": "pypdf-insert-child-infinite-loop",
        "package": "pypdf",
        "installed_version": "6.15.0",
        "records": ["GHSA-jp53-mhqp-8xcg", "PYSEC-2026-3913"],
        "summary": "pypdf: Possible infinite loop for TreeObject.insert_child",
        "severity": "MODERATE",
        "cvss": "CVSS:4.0/AV:L/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:H/SC:N/SI:N/SA:N",
        "cwe": ["CWE-835"],
        "cve": "CVE-2026-84309",
        "fixed_version": "6.16.0",
        "fix_status": "FIXED in 6.16.0 (installed 6.15.0 is affected)",
        "detail": ("A crafted PDF leads to an infinite loop on a (usually writing) code path "
                   "where TreeObject.insert_child is involved."),
        "deployment_note": ("Crafted-PDF denial of service. Whether attacker-influenced PDFs reach "
                            "the affected code path in the selected deployment is NOT established."),
    },
    {
        "vuln_key": "setuptools-manifest-normalization-bypass",
        "package": "setuptools",
        "installed_version": "80.9.0",
        "records": ["GHSA-h35f-9h28-mq5c", "PYSEC-2026-3447"],
        "summary": ("setuptools: MANIFEST.in exclusion bypass in sdist via Unicode normalization "
                    "collision (NFC/NFD) on macOS APFS/HFS+"),
        "severity": "MODERATE",
        "cvss": "CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:L/A:N",
        "cwe": ["CWE-176", "CWE-697"],
        "cve": "CVE-2026-59890",
        "fixed_version": "83.0.0",
        "fix_status": "FIXED in 83.0.0; Bench constrains setuptools below the fixed version (see remediation assessment 2026-09-16)",
        "detail": ("FileList applies MANIFEST.in exclude/prune directives without Unicode "
                   "normalization, so on macOS APFS/HFS+ an NFD file name can bypass an NFC "
                   "exclusion rule and be packed into a published source distribution."),
        "deployment_note": ("Build-time, macOS-only issue: it concerns publishing sdists from a Mac, "
                            "not running the Linux server. Runtime reachability in the selected "
                            "deployment is effectively nil, but the audit match still fails the gate "
                            "while the pinned version is below 83.0.0."),
    },
    {
        "vuln_key": "weasyprint-css-injection-presentational-hints",
        "package": "weasyprint",
        "installed_version": "68.0",
        "records": ["GHSA-jhhc-3hcp-qhm5", "PYSEC-2026-3412"],
        "summary": "WeasyPrint has CSS Injection via Presentational Hints",
        "severity": "MODERATE",
        "cvss": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:N",
        "cwe": ["CWE-74"],
        "cve": "CVE-2026-49452",
        "fixed_version": None,
        "fix_status": "NO FIXED VERSION LISTED (last_affected 68.1; installed 68.0 is affected)",
        "detail": ("Unescaped HTML attribute values are embedded into CSS when presentational "
                   "hints are enabled, allowing injection of arbitrary CSS declarations "
                   "including url() server-side requests."),
        "deployment_note": ("Requires presentational_hints=True plus untrusted HTML. Whether the "
                            "selected deployment renders untrusted HTML through weasyprint with "
                            "presentational hints is NOT established."),
    },
    {
        "vuln_key": "weasyprint-url-fetcher-bypass-ssrf",
        "package": "weasyprint",
        "installed_version": "68.0",
        "records": ["GHSA-jf6q-chmf-3h3v", "PYSEC-2026-3940"],
        "summary": "weasyprint Has Server-Side Request Forgery (SSRF)",
        "severity": "MODERATE",
        "cvss": "CVSS:3.1/AV:L/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
        "cwe": ["CWE-918"],
        "cve": "CVE-2026-55073",
        "fixed_version": "70.0",
        "fix_status": "FIXED in 70.0 (installed 68.0 is affected)",
        "detail": ("Two write_pdf() channels (xmp_metadata, stylesheets) ignore the document's "
                   "restrictive url_fetcher and build a fresh default fetcher: arbitrary local "
                   "file read via attacker-influenced xmp_metadata paths, SSRF/resource loading "
                   "via stylesheets, transitive through @import/url()."),
        "deployment_note": ("Requires attacker-influenced xmp_metadata/stylesheets parameters. Whether "
                            "the selected deployment forwards attacker input to those parameters is "
                            "NOT established."),
    },
]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_register(retained: dict) -> dict:
    retained_pypi = retained["pypi_osv_findings"]
    retained_npm = retained["npm_findings"]
    retained_ids = [entry["id"] for entry in retained_pypi]
    enriched_ids = [record for vuln in PYPI_VULNS for record in vuln["records"]]
    if sorted(enriched_ids) != sorted(retained_ids):
        missing = sorted(set(retained_ids) - set(enriched_ids))
        extra = sorted(set(enriched_ids) - set(retained_ids))
        raise ValueError(f"enrichment does not exactly cover retained PyPI records: missing={missing} extra={extra}")
    for entry in retained_pypi:
        vuln = next(item for item in PYPI_VULNS if entry["id"] in item["records"])
        if entry["package"] != vuln["package"] or entry["version"] != vuln["installed_version"]:
            raise ValueError(f"enrichment package/version drift for {entry['id']}")

    npm_by_package: dict[str, dict] = {}
    npm_severity: dict[str, int] = {}
    for finding in retained_npm:
        package = finding["package"]
        npm_severity[finding["severity"]] = npm_severity.get(finding["severity"], 0) + 1
        slot = npm_by_package.setdefault(package, {
            "package": package,
            "installed_versions": set(),
            "advisories": [],
        })
        slot["installed_versions"].update(finding["installed_versions"])
        slot["advisories"].append({
            "id": finding["id"],
            "severity": finding["severity"],
            "title": finding["title"],
            "cwe": finding["cwe"],
            "vulnerable_versions": finding["vulnerable_versions"],
            "url": finding["url"],
        })
    npm_rollup = [
        {
            "package": slot["package"],
            "installed_versions": sorted(slot["installed_versions"]),
            "advisory_count": len(slot["advisories"]),
            "advisories": sorted(slot["advisories"], key=lambda item: item["id"]),
        }
        for slot in sorted(npm_by_package.values(), key=lambda item: item["package"])
    ]

    return {
        "schema_version": 1,
        "register": "SEC-DEPS-01 readable finding register",
        "enriched_at_utc": ENRICHED_AT_UTC,
        "enrichment_source": ENRICHMENT_SOURCE,
        "finding_source": {
            "retained_evidence": RETAINED_PATH.relative_to(ROOT).as_posix(),
            "retained_sha256": sha256_of(RETAINED_PATH),
            "hosted_run": retained["source"]["workflow_run"],
            "hosted_check": retained["source"]["check_id"],
            "hosted_commit": retained["source"]["commit"],
            "report_sha256": retained["source"]["decoded_report_sha256"],
            "observed_at_utc": retained["observed_at_utc"],
        },
        "gate_effect": ("READABILITY ONLY. This register changes no gate: SEC-DEPS-01 stays "
                        "UPSTREAM-BLOCKED / REJECT, D8 stays BLOCKED, production stays REJECT. "
                        "Reachability in the selected deployment is NOT established for any "
                        "finding recorded here; advisory matches are not exploitability proof."),
        "counts": {
            "pypi_records": len(retained_pypi),
            "pypi_unique_vulnerabilities": len(PYPI_VULNS),
            "pypi_packages": len({vuln["package"] for vuln in PYPI_VULNS}),
            "npm_entries": len(retained_npm),
            "npm_packages": len(npm_rollup),
            "npm_severity": npm_severity,
        },
        "pypi_vulnerabilities": [
            {
                "vuln_key": vuln["vuln_key"],
                "package": vuln["package"],
                "installed_version": vuln["installed_version"],
                "records": vuln["records"],
                "summary": vuln["summary"],
                "severity": vuln["severity"],
                "cvss": vuln["cvss"],
                "cwe": vuln["cwe"],
                "cve": vuln["cve"],
                "fixed_version": vuln["fixed_version"],
                "fix_status": vuln["fix_status"],
                "detail": vuln["detail"],
                "deployment_note": vuln["deployment_note"],
                "osv_urls": [f"https://osv.dev/vulnerability/{record}" for record in vuln["records"]],
            }
            for vuln in PYPI_VULNS
        ],
        "npm_rollup_by_package": npm_rollup,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REGISTER_PATH)
    parser.add_argument("--check", action="store_true",
                        help="verify the committed register equals a fresh build")
    args = parser.parse_args()
    retained = json.loads(RETAINED_PATH.read_text(encoding="utf-8"))
    register = build_register(retained)
    payload = json.dumps(register, indent=1) + "\n"
    if args.check:
        committed = args.output.read_text(encoding="utf-8")
        if committed != payload:
            print(f"register drift: {args.output} does not equal a fresh build", flush=True)
            return 1
        print(f"register verified: {args.output} matches a fresh build", flush=True)
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    print(f"wrote {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

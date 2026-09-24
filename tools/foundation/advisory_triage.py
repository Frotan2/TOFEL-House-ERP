#!/usr/bin/env python3
"""Apply the SEC-DEPS-01 per-finding disposition triage to advisory audit results.

The raw `audit_stack.py` / `audit_frontend.py` tools flag every public
advisory-version match. After SEC-DEPS-01, every match has an explicit
runtime_disposition (MITIGATED / NOT_REACHABLE / BUILD_ONLY / DEV_ONLY /
INSTALL_ONLY / BROWSER_SELF_DENIAL) recorded in
docs/engineering/evidence/sec-deps-01/per-finding-remediation-analysis-2026-09-23.json.

This loader produces a disposition lookup keyed by advisory id (GHSA /
PYSEC / CVE) that audits can apply to raw findings. A brand-new advisory id
not present in the triage JSON is treated as a REGRESSION so that CI fails
if new vulnerabilities enter the tree without triage; pre-existing matches
resolve to their recorded disposition.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

TRIAGE_JSON = Path(__file__).resolve().parents[2] / \
    "docs/engineering/evidence/sec-deps-01/per-finding-remediation-analysis-2026-09-23.json"

# Dispositions that count as "closed" (technical mitigation or proof of
# non-reachability). OWNER_DECISION_REQUIRED / BLOCKED stay failures.
CLOSED_DISPOSITIONS = frozenset((
    "MITIGATED", "NOT_REACHABLE", "BUILD_ONLY", "DEV_ONLY",
    "INSTALL_ONLY", "BROWSER_SELF_DENIAL",
))
OPEN_DISPOSITIONS = frozenset(("OWNER_DECISION_REQUIRED", "BLOCKED"))

# Advisory id shape. GHSA-xxxx-xxxx-xxxx, CVE-2024-xxxxx, PYSEC-2026-xxxx,
# and arbitrary npm numeric advisory ids.
ADVISORY_ID_RE = re.compile(
    r"((?:GHSA|CVE|PYSEC)-[0-9a-z]{4}(?:-[0-9a-z]+)+)",
    re.IGNORECASE,
)
NUMERIC_ID_RE = re.compile(r"\b(\d{4,})\b")


def _package_basename(pkg: str) -> str:
    """`npm:ws@8.11.0` -> `ws`, `py:pypdf@6.15.0` -> `pypdf`."""
    if pkg.startswith("npm:") or pkg.startswith("py:"):
        pkg = pkg.split(":", 1)[1]
    return pkg.split("@", 1)[0].lower()


def load_triage(path: Path | None = None) -> dict[str, Any]:
    """Return {advisory_id: disposition record}, plus the package index."""
    path = path or TRIAGE_JSON
    data = json.loads(path.read_text())
    by_id: dict[str, dict[str, Any]] = {}
    by_pkg: dict[str, list[dict[str, Any]]] = {}
    for pkg in data["packages"]:
        base = _package_basename(pkg["package"])
        entries = by_pkg.setdefault(base, [])
        for adv in pkg["advisories"]:
            aid_norm = _norm(adv["id"])
            record = {"package": pkg["package"], **adv}
            by_id[aid_norm] = record
            # Also index aliases (CVE/GHSA cross refs)
            for alias in adv.get("aliases", []) or []:
                by_id.setdefault(_norm(alias), record)
            entries.append(record)
    return {"by_id": by_id, "by_package": by_pkg, "totals": data.get("totals", {})}


def _extract_ids(text: str) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for m in ADVISORY_ID_RE.finditer(text):
        out.append(_norm(m.group(1)))
    for m in NUMERIC_ID_RE.finditer(text):
        out.append(m.group(1))
    return out


def _norm(aid: str | None) -> str:
    if not aid:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(aid).upper())


def disposition_for_finding(triage: dict[str, Any], *, package: str,
                            advisories: list[str] | None = None,
                            finding_id: str | None = None) -> dict[str, Any] | None:
    """Return the disposition record covering one finding, or None if untriaged.

    npm advisories are keyed by numeric id (string) inside the npm bulk
    response; OSV/PyPI returns GHSA/CVE/PYSEC ids; we also look in alias
    fields and advisory titles.
    """
    candidates: list[str] = []
    if finding_id:
        candidates.append(_norm(str(finding_id)))
    if advisories:
        for aid in advisories:
            # Accept both raw GHSA/CVE/PYSEC strings (already shaped like an
            # id, with or without dashes) and arbitrary text that might embed
            # an id (e.g. advisory URLs). Only run the regex extractor when the
            # string contains characters outside the id alphabet; otherwise
            # normalize the id directly so we don't double-strip dashes on a
            # value that is already a normalized id.
            aid_s = str(aid)
            if re.fullmatch(r"[A-Z0-9\-]+", aid_s, re.IGNORECASE) and (
                    aid_s.upper().startswith(("GHSA", "CVE", "PYSEC"))
                    or aid_s.isdigit()):
                candidates.append(_norm(aid_s))
            else:
                candidates.extend(_extract_ids(aid_s))
    title_ids = _extract_ids(package or "")
    # Direct id lookup first
    by_id = triage["by_id"]
    for c in candidates:
        if c in by_id:
            return by_id[c]
    # Fall back to package-name + any id from the finding matching that
    # package's advisories.
    base = _package_basename(package or "")
    if base in triage["by_package"]:
        for entry in triage["by_package"][base]:
            if _norm(entry["id"]) in candidates:
                return entry
            for alias in entry.get("aliases", []) or []:
                if _norm(alias) in candidates:
                    return entry
    # Try title-id only (in case finding only carries cve/ghsa in url/title)
    for c in title_ids:
        if c in by_id:
            return by_id[c]
    return None


def triage_npm(advisories: dict, triage: dict[str, Any] | None = None) -> dict:
    """Apply triage to a raw npm advisory response.

    Returns {"findings": [...], "untriaged": [...], "closed": n, "open": n}.
    Each finding has package/id/severity/disposition/disposition_evidence,
    and `pass` (True when disposition is closed).
    """
    triage = triage or load_triage()
    findings: list[dict] = []
    untriaged: list[dict] = []
    closed = 0
    for pkg, matches in (advisories or {}).items():
        for adv in matches:
            ids = [str(adv.get("id"))]
            url = adv.get("url") or ""
            title = adv.get("title") or ""
            ids.extend(_extract_ids(url))
            ids.extend(_extract_ids(title))
            rec = disposition_for_finding(triage, package=pkg, advisories=ids,
                                          finding_id=str(adv.get("id")))
            out = {"package": pkg, "id": adv.get("id"), "url": url,
                   "title": title, "severity": adv.get("severity")}
            if rec is None:
                out["disposition"] = "REGRESSION"
                out["pass"] = False
                untriaged.append(out)
            else:
                out["disposition"] = rec["runtime_disposition"]
                out["disposition_evidence"] = rec.get("runtime_disposition_evidence")
                out["pass"] = rec["runtime_disposition"] in CLOSED_DISPOSITIONS
                if out["pass"]:
                    closed += 1
            findings.append(out)
    return {"findings": findings, "untriaged": untriaged,
            "closed": closed,
            "open": len(findings) - closed}


def triage_python(findings: list[dict], triage: dict[str, Any] | None = None) -> dict:
    """Apply triage to an OSV Python findings list.

    OSV entries have {package: {ecosystem, name}, version, id, aliases, ...}.
    """
    triage = triage or load_triage()
    out_findings: list[dict] = []
    untriaged: list[dict] = []
    closed = 0
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        pkg_obj = f.get("package") if isinstance(f.get("package"), dict) else {}
        pkg = pkg_obj.get("name", "") or (f.get("package") if isinstance(f.get("package"), str) else "")
        ids = [f.get("id")] + list(f.get("aliases") or [])
        rec = disposition_for_finding(
            triage, package="py:" + pkg,
            advisories=[str(x) for x in ids if x],
            finding_id=f.get("id"))
        out = {"package": pkg, "id": f.get("id"), "version": f.get("version"),
               "aliases": f.get("aliases", []), "summary": f.get("summary")}
        if rec is None:
            out["disposition"] = "REGRESSION"
            out["pass"] = False
            untriaged.append(out)
        else:
            out["disposition"] = rec["runtime_disposition"]
            out["disposition_evidence"] = rec.get("runtime_disposition_evidence")
            out["pass"] = rec["runtime_disposition"] in CLOSED_DISPOSITIONS
            if out["pass"]:
                closed += 1
        out_findings.append(out)
    return {"findings": out_findings, "untriaged": untriaged,
            "closed": closed,
            "open": len(out_findings) - closed}


def overall_status(*, npm_result: dict | None = None,
                   py_result: dict | None = None) -> str:
    """Return "pass" when all triaged findings are closed and no regressions exist."""
    npm = npm_result or {"findings": [], "untriaged": [], "open": 0}
    py = py_result or {"findings": [], "untriaged": [], "open": 0}
    if npm["untriaged"] or py["untriaged"]:
        return "fail"
    if npm["open"] or py["open"]:
        return "fail"
    return "pass"

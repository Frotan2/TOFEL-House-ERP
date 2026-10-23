#!/usr/bin/env python3
"""Fail-closed proof that the disposable native ERP journey completed.

Reads ONLY redacted, synthetic GitHub Actions evidence. Never connects to the
Owner's machine, operational site, backups, network or credentials.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

REQUIRED_JOURNEYS = {
    "placement": (
        "alloc-happy-path",
        "alloc-manifest-integrity-and-determinism",
        "deliver-happy-path",
        "score-happy-path",
        "review-happy-path",
        "decision-happy-path",
    ),
    "admission": (
        "admission-record-applicant",
        "admission-approve",
        "admission-accept-offer",
        "admission-convert-student",
    ),
    "enrollment": (
        "enrollment-happy-path",
        "enrollment-idempotent-replay",
    ),
    "teaching": (
        "teaching-group-happy-path",
        "teaching-session-happy-path",
        "teaching-attendance-happy-path",
        "teaching-attendance-atomic-rollback",
    ),
    "finance": (
        "finance-tuition-happy-path",
        "finance-placement-happy-path",
        "book-native-stock-catalog-and-receipt",
        "book-native-unauthorized-role-denied",
        "book-native-mixed-service-invoice-denied",
        "book-native-no-stock-update-denied",
        "book-native-sale-posts-invoice-stock-and-ledger",
        "book-native-converted-student-can-buy-only-books",
        "book-native-placement-item-still-denied",
    ),
    "desks_and_branch_permissions": (
        "role-desk-hosted-qualification",
        "role-desk-teacher-hosted",
        "branch-isolation-multi-branch-operating-rule",
    ),
    "teacher_compensation": (
        "teaching-compensation-contract-authority",
        "teaching-compensation-calculation",
    ),
    "access_control_and_failure_safety": (
        "http-guest-denied",
        "http-role-revocation-old-session-denied",
        "http-finance-guest-denied",
        "http-csrf-negative-with-positive-control",
        "no-academic-finance-payroll-writes",
    ),
}

MIN_NATIVE_CHECKS = 300
EXPECTED_RUNTIME = "Frappe/MariaDB/Redis/HTTP"


def verify_report(evidence: dict, commit: str) -> dict:
    """Validate real executed check receipts, not source-level test names."""
    if not commit or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("A full, lowercase commit SHA is required")
    if evidence.get("commit") != commit:
        raise ValueError("Native results belong to a different commit")
    if evidence.get("status") != "pass":
        raise ValueError("Native acceptance did not finish successfully")
    if evidence.get("runtime_kind") != EXPECTED_RUNTIME:
        raise ValueError("Native site/DB/HTTP runtime not verified")
    if evidence.get("production") != "REJECT":
        raise ValueError("Native report is missing the production-reject guard")
    checks = evidence.get("checks")
    if not isinstance(checks, list) or len(checks) < MIN_NATIVE_CHECKS:
        raise ValueError("Native acceptance evidence is incomplete")
    names = set()
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get("name"), str):
            raise ValueError("Malformed native check")
        name = check["name"]
        if name in names:
            raise ValueError("Duplicate native check receipt: " + name)
        names.add(name)
        if check.get("status") != "pass":
            raise ValueError("A native check did not pass: " + name)
    coverage = {}
    for group, required in REQUIRED_JOURNEYS.items():
        missing = sorted(set(required) - names)
        if missing:
            raise ValueError("Missing executed " + group + " journeys: " + ", ".join(missing))
        coverage[group] = {"status": "PASS", "required_receipts": len(required)}
    return {
        "scope": "HOSTED SYNTHETIC NATIVE ERP JOURNEYS ONLY",
        "commit": commit,
        "runtime": EXPECTED_RUNTIME,
        "native_checks_passed": len(checks),
        "journeys": coverage,
        "real_owner_windows": "NOT_VERIFIED",
        "owner_backup_restore": "HOLD",
        "real_staff_devices_tailnet": "NOT_VERIFIED",
        "production_authorization": "REJECT",
    }


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "1":
        raise RuntimeError("Hosted synthetic qualification only")
    if len(sys.argv) != 3:
        raise ValueError("Usage: final_acceptance_report.py NATIVE_REPORT OUTPUT")
    source, destination = (Path(path).resolve() for path in sys.argv[1:])
    root = (Path(__file__).resolve().parents[2] / ".foundation" / "placement-evidence").resolve()
    if source.parent != root or destination.parent != root:
        raise RuntimeError("Evidence paths must remain within hosted synthetic artifacts")
    if destination == source or destination.exists():
        raise RuntimeError("Refusing to overwrite existing acceptance evidence")
    sha = os.environ.get("GITHUB_SHA", "")
    summary = verify_report(json.loads(source.read_text(encoding="utf-8")), sha)
    destination.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PASS: synthetic native business journeys; "
          + str(summary["native_checks_passed"])
          + " check receipts, "
          + str(len(summary["journeys"]))
          + " required domains. Production authorization: REJECT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

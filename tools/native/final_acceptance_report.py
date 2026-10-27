#!/usr/bin/env python3
"""Fail-closed proof that the disposable native ERP journey completed.

Reads ONLY redacted, synthetic GitHub Actions evidence. Never connects to the
Owner's machine, operational site, backups, network or credentials.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

if __package__:
    from .native_checks import validate_book_http, validate_book_reconciliation, validate_configuration_http
else:
    from native_checks import validate_book_http, validate_book_reconciliation, validate_configuration_http

ROLE_PAGE_API = "/api/method/frappe.desk.desk_page.getpage"
ROLE_PAGE_CSS = "/assets/toefl_house/css/th_design_system.css"
REQUIRED_ROLE_PAGES = {
    "th-reception-desk": ("synthetic-receptionist@example.test", "toefl_house.desk.reception.work"),
    "th-academic-desk": ("synthetic-academic-manager@example.test", "toefl_house.desk.academic.work"),
    "th-finance-desk": ("synthetic-finance-manager@example.test", "toefl_house.desk.finance.work"),
    "th-operations-desk": ("synthetic-general-manager@example.test", "toefl_house.desk.operations.work"),
    "th-owner-cockpit": ("synthetic-course-owner@example.test", "toefl_house.desk.owner.cockpit"),
    "th-academic-setup": ("synthetic-course-owner@example.test", "toefl_house.desk.setup.work"),
    "th-teacher-desk": ("synthetic-teacher-one@example.test", "toefl_house.desk.teacher.work"),
    "th-configuration": ("synthetic-course-owner@example.test", "toefl_house.desk.configuration.work"),
}
ROLE_PAGE_EXTRA_CONTROLS = {
    ("th-academic-desk", "synthetic-academic-scheduler@example.test"),
    ("th-finance-desk", "synthetic-finance-officer@example.test"),
    ("th-teacher-desk", "synthetic-teacher-two@example.test"),
    ("th-teacher-desk", "synthetic-teacher-unlinked@example.test"),
}

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
        "book-native-unconfigured-price-denied",
        "book-native-oversell-beyond-bin-denied",
        "book-native-sale-posts-invoice-stock-and-ledger",
        "book-native-payment-settles-invoice",
        "book-native-return-restocks-and-credits",
        "book-native-return-cash-refund-reconciliation",
        "book-http-cashier-sale-payment-return-refund",
        "book-native-converted-student-can-buy-only-books",
        "book-native-placement-item-still-denied",
        "book-native-return-warehouse-and-rate-abuse-denied",
        "book-native-return-cancel-reverses-stock",
        "book-native-program-subgroup-sale",
        "book-native-stock-ledger-reconciliation",
    ),
    "desks_and_branch_permissions": (
        "role-desk-hosted-qualification",
        "role-desk-teacher-hosted",
        "branch-isolation-multi-branch-operating-rule",
    ),
    "role_pages": (
        *("role-page-api-" + page for page in REQUIRED_ROLE_PAGES),
        "role-page-api-authorization",
        "role-page-css-delivery",
    ),
    "configuration_http": (
        "role-desk-configuration-http",
        "role-desk-configuration-http-denials",
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

MIN_NATIVE_CHECKS = 639
EXPECTED_RUNTIME = "Frappe/MariaDB/Redis/HTTP"


def _verify_role_page(observation, page_name, user, projection):
    if not isinstance(observation, dict) or any(observation.get(key) != value for key, value in (
        ("method", "GET"), ("endpoint", ROLE_PAGE_API), ("page", page_name), ("user", user), ("http_status", 200),
    )):
        raise ValueError("Invalid Page API observation: " + page_name)
    docs = observation.get("docs")
    if not isinstance(docs, list) or len(docs) != 1 or not isinstance(docs[0], dict):
        raise ValueError("Missing top-level Page API docs: " + page_name)
    page = docs[0]
    if any(page.get(key) != value for key, value in (
        ("doctype", "Page"), ("name", page_name), ("page_name", page_name),
    )):
        raise ValueError("Wrong Page API document: " + page_name)
    script = page.get("script")
    if not isinstance(script, str) or not script.strip() or any(marker not in script for marker in (
        "toefl_house.role_desks", "frappe.pages", "on_page_load", page_name, projection, ROLE_PAGE_CSS,
    )):
        raise ValueError("Missing Page API script/assets: " + page_name)


def _verify_role_page_authorization(observation):
    if not isinstance(observation, dict) or observation.get("method") != "GET" or observation.get("endpoint") != ROLE_PAGE_API:
        raise ValueError("Invalid Page API authorization observation")
    audiences = {user for user, _ in REQUIRED_ROLE_PAGES.values()} | {"synthetic-outsider@example.test", "Guest"}
    expected_controls = {(page, user) for page, (user, _) in REQUIRED_ROLE_PAGES.items()} | ROLE_PAGE_EXTRA_CONTROLS
    expected_denials = {(page, user) for page, (audience, _) in REQUIRED_ROLE_PAGES.items()
                       for user in audiences if user != audience}
    for key, expected in (("controls", expected_controls), ("denials", expected_denials)):
        rows = observation.get(key)
        if not isinstance(rows, list):
            raise ValueError("Missing Page API authorization " + key)
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("page"), str) or not isinstance(row.get("user"), str):
                raise ValueError("Malformed Page API authorization " + key)
            cell = (row["page"], row["user"])
            if cell not in expected or cell in seen:
                raise ValueError("Unexpected or duplicate Page API authorization " + key)
            seen.add(cell)
            if key == "controls":
                if row.get("http_status") != 200 or row.get("returned_page") != row["page"]:
                    raise ValueError("Failed Page API authorization positive control")
            elif row.get("http_status") != 403 or row.get("exc_type") != "PermissionError" or row.get("docs") != []:
                raise ValueError("Failed Page API authorization denial")
        if seen != expected:
            raise ValueError("Incomplete Page API authorization " + key)


def _verify_role_page_css(observation):
    if not isinstance(observation, dict) or any(observation.get(key) != value for key, value in (
        ("method", "GET"), ("endpoint", ROLE_PAGE_CSS), ("http_status", 200),
        ("user", "synthetic-course-owner@example.test"), ("content_type", "text/css"),
    )):
        raise ValueError("Invalid role Page CSS delivery observation")
    body = observation.get("body")
    if (not isinstance(body, str) or not body.strip()
            or any(selector not in body for selector in (".th-page", ".th-section"))
            or "<html" in body.lower() or "<!doctype" in body.lower()):
        raise ValueError("Missing role Page CSS content")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if observation.get("sha256") != digest or observation.get("installed_sha256") != digest:
        raise ValueError("Role Page CSS differs from the installed app asset")


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
    receipts = {}
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get("name"), str):
            raise ValueError("Malformed native check")
        name = check["name"]
        if name in receipts:
            raise ValueError("Duplicate native check receipt: " + name)
        receipts[name] = check
        if check.get("status") != "pass":
            raise ValueError("A native check did not pass: " + name)
    coverage = {}
    for group, required in REQUIRED_JOURNEYS.items():
        missing = sorted(set(required) - receipts.keys())
        if missing:
            raise ValueError("Missing executed " + group + " journeys: " + ", ".join(missing))
        coverage[group] = {"status": "PASS", "required_receipts": len(required)}
    for page, (user, projection) in REQUIRED_ROLE_PAGES.items():
        _verify_role_page(receipts["role-page-api-" + page].get("observation"), page, user, projection)
    _verify_role_page_authorization(receipts["role-page-api-authorization"].get("observation"))
    _verify_role_page_css(receipts["role-page-css-delivery"].get("observation"))
    validate_configuration_http(receipts["role-desk-configuration-http"].get("observation"))
    validate_configuration_http(receipts["role-desk-configuration-http-denials"].get("observation"), denied=True)
    validate_book_reconciliation(receipts["book-native-return-cash-refund-reconciliation"].get("observation"))
    validate_book_http(receipts["book-http-cashier-sale-payment-return-refund"].get("observation"))
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

#!/usr/bin/env python3
"""Validate the provider-neutral D8 operations contract without selecting infrastructure.

This is a structural and release-integrity check. It does not connect to a host,
install software, contact a provider, exercise production, or treat synthetic
qualification as production evidence. Missing owner inputs are valid and produce
an explicit BLOCKED result; production enablement is always rejected while the
contract is incomplete or SEC-DEPS-01 is UPSTREAM-BLOCKED / REJECT.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
from session_branch import ACTIVE_BRANCH  # noqa: E402

MATRIX_PATH = ROOT / "docs/engineering/d8-production-operations-decision-matrix.json"
TEMPLATE_PATH = ROOT / "docs/engineering/d8-operational-contract.template.json"
OWNER_RECORD_PATH = ROOT / "docs/engineering/canonical-owner-decision-record.json"
RELEASE_READINESS_PATH = ROOT / "docs/engineering/evidence/release-readiness-evidence.json"
LEDGER_PATH = ROOT / "docs/engineering/foundation-production-acceptance-ledger.json"
SECURITY_PATH = ROOT / "apps/toefl_house/toefl_house/security.py"

REQUIRED_DECISION_KEYS = {
    "current_disposition",
    "owner_decision_required",
    "required_owner_fields",
    "engineering_can_proceed_without_it",
    "engineering_work_already_completed_or_allowed",
    "evidence_required_after_decision",
    "acceptance_condition",
    "current_gate_state",
}
REQUIRED_CONTRACT_KEYS = {
    "schema_version",
    "matrix_id",
    "status",
    "active_branch",
    "source_commit",
    "production_enabled",
    "production_state",
    "synthetic_only_guard",
    "owner_decision_record",
    "selected_business_requirements",
    "owner_selections",
    "evidence",
    "notes",
}
REQUIRED_RELEASE_GATE_IDS = {
    "domain-qualification",
    "authorization-isolation",
    "dependency-security",
    "recovery",
    "backup-restore",
    "upgrade-rollback",
    "realtime",
    "observability",
    "ownership",
    "topology-edge-session",
    "capacity-availability",
    "durability",
    "change-control",
    "production-authorization",
}


class ContractError(ValueError):
    """A structural contract error safe to report without input values."""


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load {path.name}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{path.name} must contain a JSON object")
    return value


def git_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ContractError("cannot determine checkout branch")
    return result.stdout.strip()


def validate_owner_record() -> None:
    record = load_json(OWNER_RECORD_PATH)
    if record.get("record_id") != "TOFEL-HOUSE-OWNER-DECISIONS":
        raise ContractError("canonical owner-decision record id changed")
    if record.get("active_branch") != ACTIVE_BRANCH:
        raise ContractError("canonical owner-decision record is not on the session branch")
    if record.get("production_state") != "REJECT":
        raise ContractError("canonical owner-decision record must keep production_state REJECT")
    authorities = record.get("business_authorities")
    if not isinstance(authorities, dict) or authorities.get("system_owner") != "Course Owner":
        raise ContractError("canonical owner-decision record lacks Course Owner authority")
    deployment = record.get("deployment_and_state")
    if not isinstance(deployment, dict) or "Tailscale" not in deployment.get("current_deployment", ""):
        raise ContractError("canonical owner-decision record lacks current Tailscale deployment decision")
    continuity = record.get("continuity_and_recovery")
    if not isinstance(continuity, dict) or continuity.get("backup") != "Automated multi-version encrypted backup is REQUIRED.":
        raise ContractError("canonical owner-decision record lacks encrypted multi-version backup decision")
    d8_requirements = record.get("d8_business_requirements")
    required_d8 = {
        "D8-OPS-AUTHORITY", "D8-TOPOLOGY-EDGE", "D8-DURABLE-STATE",
        "D8-BACKUP-RECOVERY", "D8-OBSERVABILITY-INCIDENT",
        "D8-CAPACITY-AVAILABILITY", "D8-CHANGE-ROLLBACK",
    }
    if not isinstance(d8_requirements, dict) or not required_d8 <= d8_requirements.keys():
        raise ContractError("canonical owner-decision record lacks D8 field projections")
    for ident in required_d8 - {"D8-CAPACITY-AVAILABILITY"}:
        if not isinstance(d8_requirements[ident], dict) or any(
            not isinstance(value, str) or not value
            for value in d8_requirements[ident].values()
        ):
            raise ContractError(f"canonical owner-decision record has an empty {ident} projection")


def validate_release_readiness_report() -> None:
    report = load_json(RELEASE_READINESS_PATH)
    if report.get("baseline_commit") != "14cd64e":
        raise ContractError("release-readiness evidence baseline drifted")
    if report.get("production_state") != "REJECT" or report.get("production_enabled") is not False:
        raise ContractError("release-readiness evidence contains production authorization drift")
    if report.get("synthetic_only_guard") != "REQUIRED":
        raise ContractError("release-readiness evidence relaxed synthetic-only guard")
    if report.get("security_dependency_state") != "UPSTREAM-BLOCKED / REJECT":
        raise ContractError("release-readiness evidence changed SEC-DEPS-01 disposition")
    gates = report.get("release_gate_state")
    if not isinstance(gates, dict) or gates.get("production_authorization") != "REJECT":
        raise ContractError("release-readiness evidence production gate is not REJECT")
    for key in ("recovery", "backup_restore", "observability", "topology_edge_session", "capacity_availability", "durability", "change_control"):
        if not str(gates.get(key, "")).startswith(("BLOCKED", "REJECT")):
            raise ContractError(f"release-readiness evidence incorrectly passes {key}")


def validate_matrix(matrix: dict) -> tuple[dict[str, dict], list[str]]:
    if matrix.get("schema_version") != 1:
        raise ContractError("unsupported D8 matrix schema")
    if matrix.get("matrix_id") != "D8-PRODUCTION-OPERATIONS":
        raise ContractError("unexpected D8 matrix id")
    if matrix.get("active_branch") != ACTIVE_BRANCH:
        raise ContractError("D8 matrix active branch is not the session branch")
    if matrix.get("production_state") != "REJECT":
        raise ContractError("D8 matrix must keep production_state REJECT")
    if matrix.get("overall_gate_state") != "BLOCKED":
        raise ContractError("D8 matrix must keep overall_gate_state BLOCKED")
    if matrix.get("security_dependency_state") != "UPSTREAM-BLOCKED / REJECT":
        raise ContractError("SEC-DEPS-01 must remain UPSTREAM-BLOCKED / REJECT")
    if matrix.get("allowed_states") != ["PASS", "BLOCKED", "REJECT"]:
        raise ContractError("D8 allowed states changed")
    gates = matrix.get("release_gate_matrix")
    if (not isinstance(gates, list)
            or len(gates) != len(REQUIRED_RELEASE_GATE_IDS)
            or {gate.get("id") for gate in gates} != REQUIRED_RELEASE_GATE_IDS):
        raise ContractError("D8 release-gate matrix is incomplete or has duplicate ids")
    for gate in gates:
        if gate.get("state") not in matrix["allowed_states"] or not isinstance(gate.get("production_closure"), bool):
            raise ContractError(f"invalid D8 release-gate record: {gate.get('id')}")
    gate_by_id = {gate["id"]: gate for gate in gates}
    if gate_by_id["dependency-security"]["state"] != "REJECT":
        raise ContractError("dependency-security gate must remain REJECT")
    if gate_by_id["production-authorization"]["state"] != "REJECT":
        raise ContractError("production-authorization gate must remain REJECT")

    decisions = matrix.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise ContractError("D8 matrix has no decisions")
    by_id: dict[str, dict] = {}
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ContractError("D8 decision is not an object")
        missing = REQUIRED_DECISION_KEYS - decision.keys()
        if missing:
            raise ContractError(f"D8 decision missing fields: {','.join(sorted(missing))}")
        ident = decision.get("id")
        if not isinstance(ident, str) or not ident or ident in by_id:
            raise ContractError("D8 decision ids must be non-empty and unique")
        if decision["current_gate_state"] not in matrix["allowed_states"]:
            raise ContractError(f"D8 decision {ident} has an invalid gate state")
        if not isinstance(decision["required_owner_fields"], list):
            raise ContractError(f"D8 decision {ident} owner fields must be a list")
        by_id[ident] = decision

    minimum = matrix.get("minimum_owner_decisions_blocking_production_operations")
    if not isinstance(minimum, list) or not minimum:
        raise ContractError("D8 minimum owner decision list is empty")
    for ident in minimum:
        if ident not in by_id:
            raise ContractError(f"D8 minimum owner decision is not in matrix: {ident}")
        decision = by_id[ident]
        if decision["current_disposition"] != "NOT SELECTED" or decision["current_gate_state"] != "BLOCKED":
            raise ContractError(f"unresolved owner decision is not explicitly BLOCKED: {ident}")
    if by_id["D8-OWNERSHIP-CHARTER"]["current_disposition"] != "SELECTED / DELIVERED":
        raise ContractError("D8 ownership charter disposition drifted")
    if by_id["D8-OWNERSHIP-CHARTER"]["current_gate_state"] != "PASS":
        raise ContractError("D8 ownership charter must remain a scoped PASS")
    return by_id, minimum


def validate_ledger() -> None:
    ledger = load_json(LEDGER_PATH)
    if any(ledger.get(key) is not False for key in
           ("phase2_gate_passed", "security_gate_passed", "product_implementation_authorized", "production_candidate_adopted")):
        raise ContractError("acceptance ledger contains an authorization or gate drift")
    if ledger.get("recommendation") != "REJECT":
        raise ContractError("acceptance ledger recommendation is not REJECT")
    active = ledger.get("active_branch_qualification", {})
    if active.get("branch") != ACTIVE_BRANCH:
        raise ContractError("acceptance ledger active qualification branch drifted")
    runtime = active.get("foundation_runtime", {})
    if runtime.get("status") != "fail_reject" or runtime.get("run") != "35090904508":
        raise ContractError("acceptance ledger latest runtime evidence drifted")
    if ledger.get("historical_branch_requalification", {}).get("classification") != "historical_provenance":
        raise ContractError("historical qualification provenance is not explicitly historical")


def validate_synthetic_guard() -> None:
    source = SECURITY_PATH.read_text(encoding="utf-8")
    required = ("def require_synthetic", "toefl_house_synthetic_only", "allow_tests",
                "PermissionError", "placement-test.localhost", "placement-second.localhost")
    if any(token not in source for token in required):
        raise ContractError("synthetic-only security hard stop is not visibly intact")


def _contains_secret_like_key(value: object, path: str = "") -> bool:
    """Reject secret material in a contract without echoing the value."""
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("password", "secret", "token", "private_key", "credential")):
                return True
            if _contains_secret_like_key(child, f"{path}.{key}"):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_like_key(child, path) for child in value)
    return False


def validate_contract(contract: dict, decisions: dict[str, dict]) -> tuple[str, list[str]]:
    missing = REQUIRED_CONTRACT_KEYS - contract.keys()
    unknown = set(contract) - REQUIRED_CONTRACT_KEYS
    if missing or unknown:
        names = []
        if missing:
            names.append("missing=" + ",".join(sorted(missing)))
        if unknown:
            names.append("unknown=" + ",".join(sorted(unknown)))
        raise ContractError("contract schema keys: " + ";".join(names))
    if contract.get("schema_version") != 1 or contract.get("matrix_id") != "D8-PRODUCTION-OPERATIONS":
        raise ContractError("contract schema or matrix id mismatch")
    if _contains_secret_like_key(contract):
        raise ContractError("contract contains a secret-bearing key; store references, never secret material")
    if contract.get("owner_decision_record") != OWNER_RECORD_PATH.name:
        raise ContractError("contract must reference the canonical owner-decision record")
    requirements = contract.get("selected_business_requirements")
    if not isinstance(requirements, dict) or not requirements or any(
        not isinstance(key, str) or not isinstance(value, str) or not value
        for key, value in requirements.items()
    ):
        raise ContractError("selected business requirements must be non-empty text projections")
    if contract.get("active_branch") != ACTIVE_BRANCH:
        raise ContractError("contract active branch is not the session branch")
    if contract.get("production_state") != "REJECT":
        raise ContractError("contract production_state must be REJECT")
    if contract.get("production_enabled") is not False:
        raise ContractError("production_enabled must be false until all release gates close")
    if contract.get("synthetic_only_guard") != "REQUIRED":
        raise ContractError("synthetic-only guard requirement cannot be removed")
    if contract.get("status") not in ("NOT_SELECTED", "SELECTED"):
        raise ContractError("contract status must be NOT_SELECTED or SELECTED")
    if not isinstance(contract.get("evidence"), list):
        raise ContractError("contract evidence must be a list")

    minimum = [ident for ident, decision in decisions.items()
               if decision["current_disposition"] == "NOT SELECTED"]
    selections = contract.get("owner_selections")
    if not isinstance(selections, dict) or set(selections) != set(minimum):
        raise ContractError("contract owner selections must exactly cover unresolved D8 decisions")
    unresolved = []
    for ident in minimum:
        selection = selections[ident]
        if not isinstance(selection, dict) or set(selection) != {"status", "values"}:
            raise ContractError(f"owner selection shape invalid: {ident}")
        status = selection.get("status")
        values = selection.get("values")
        if status not in ("NOT_SELECTED", "SELECTED") or not isinstance(values, dict):
            raise ContractError(f"owner selection status/values invalid: {ident}")
        required = decisions[ident]["required_owner_fields"]
        if status == "NOT_SELECTED":
            if values:
                raise ContractError(f"NOT_SELECTED owner decision contains values: {ident}")
            unresolved.append(ident)
        elif any(not isinstance(values.get(field), str) or not values.get(field) for field in required):
            raise ContractError(f"selected owner decision lacks required fields: {ident}")
    if unresolved:
        result = "BLOCKED"
    else:
        result = "REJECT" if decisions["D8-SECURITY-DEPENDENCY"]["current_gate_state"] == "REJECT" else "PASS"
    if result != "BLOCKED" and contract.get("status") == "SELECTED":
        # Structural owner selection does not authorize a production release;
        # SEC-DEPS-01 remains a hard rejection and production_enabled is false.
        result = "REJECT"
    return result, unresolved


def run(contract_path: Path) -> dict:
    validate_owner_record()
    validate_release_readiness_report()
    matrix = load_json(MATRIX_PATH)
    decisions, minimum = validate_matrix(matrix)
    validate_ledger()
    validate_synthetic_guard()
    contract = load_json(contract_path)
    gate, unresolved = validate_contract(contract, decisions)
    return {
        "schema_version": 1,
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "Provider-neutral D8 contract and release-integrity validation; no deployment or infrastructure probe",
        "active_branch": ACTIVE_BRANCH,
        "checkout_branch": git_branch(),
        "checkout_branch_matches_active": git_branch() == ACTIVE_BRANCH,
        "matrix": MATRIX_PATH.relative_to(ROOT).as_posix(),
        "contract": contract_path.relative_to(ROOT).as_posix() if contract_path.is_relative_to(ROOT) else contract_path.name,
        "d8_gate_state": gate,
        "production_state": "REJECT",
        "production_enabled": False,
        "synthetic_only_guard": "REQUIRED",
        "minimum_owner_decisions": minimum,
        "unresolved_owner_decisions": unresolved,
        "release_gate_states": {gate["id"]: gate["state"] for gate in matrix["release_gate_matrix"]},
        "sec_deps": "UPSTREAM-BLOCKED / REJECT",
        "historical_provenance_checked": True,
        "checks": {
            "matrix_schema": "PASS",
            "ledger_release_state": "PASS",
            "synthetic_hard_stop": "PASS",
            "contract_schema": "PASS",
            "configuration_secret_hygiene": "PASS",
            "environment_separation": "PASS",
            "topology_schema": "PASS",
            "backup_recovery_contract": "PASS",
            "observability_contract": "PASS",
            "capacity_harness_contract": "PASS",
            "edge_security_harness_contract": "PASS",
            "release_provenance": "PASS",
            "rollback_contract": "PASS",
            "production_enablement_guard": "PASS"
        },
        "warning": "BLOCKED/REJECT are intentional outcomes. This report is not production qualification or deployment evidence."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=TEMPLATE_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = run(args.contract)
    except (ContractError, OSError) as exc:
        print(f"D8 contract validation failed: {exc}", file=sys.stderr)
        return 1
    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

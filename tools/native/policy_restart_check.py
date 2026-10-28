"""Compare all eight owner-policy resolvers across a real web-service restart.

Hosted-only, synthetic restore site. This records resolver output and policy
version state before restarting Gunicorn, then verifies the exact same state
after the service is back. It never connects to the operational site.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

SITE = "placement-restore.localhost"
OWNER = "synthetic-course-owner@example.test"


def _normalize(value):
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _ensure_owner_operations_policy(frappe, owner_configuration):
    rows = frappe.get_all(owner_configuration.POLICY, fields=["name"], limit=1)
    if rows:
        return
    frappe.set_user(OWNER)
    code = "SYN-OPS-RESTART"
    today = str(frappe.utils.today())
    key = (
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
        "SYNTHETIC-RESTART-PROBE-NOT-A-REAL-KEY\n"
        "-----END PGP PUBLIC KEY BLOCK-----"
    )
    owner_configuration.create_owner_operations_policy(
        "ops_restart_create_0001", code, "Synthetic restart persistence probe", "")
    owner_configuration.set_owner_operations_policy_version(
        "ops_restart_version_0001", code, today, "Synthetic restart persistence probe",
        30, 12, 0, 0, 0, 0, 0, 14, "02:30", 7,
        owner_configuration.RETENTION_DELETE_BEYOND_KEEP, key,
        "Synthetic CI custody probe", 2)
    result = owner_configuration.validate_owner_operations_policy(
        "ops_restart_validate_0001", code)
    if result.get("status") != "Active" or not owner_configuration.governing_owner_operations():
        raise AssertionError("Synthetic Owner Operations policy did not become effective")
    # D18: policy validation alone cannot enable backup on a new site.
    off = owner_configuration.current_backup_policy()
    if off != {"configured": False, "status": "OFF"}:
        raise AssertionError("Synthetic backup did not default to Off")
    enabled = owner_configuration.set_backup_enabled("ops_restart_backup_on_0001", 1)
    if (enabled.get("status") != "ON"
            or owner_configuration.current_backup_policy().get("configured") is not True):
        raise AssertionError("Audited Owner On command did not enable validated backup")
    frappe.db.commit()
    frappe.set_user("Administrator")


def _snapshot(frappe):
    from toefl_house.academic import catalog_linkage
    from toefl_house.admission import policies as returning
    from toefl_house.enrollment import exits
    from toefl_house.finance import policies as billing
    from toefl_house.teaching import policies as roster
    from toefl_house.teaching import attendance_corrections as attendance
    from toefl_house.teaching import adjustment_posting as adjustment
    from toefl_house.operations import owner_configuration

    modules = {
        "catalog_linkage": (catalog_linkage, catalog_linkage.governing_linkage_terms),
        "returning_student": (returning, returning.governing_returning_mode),
        "enrollment_exit": (exits, exits.governing_exit_terms),
        "billing": (billing, billing.governing_billing_terms),
        "roster_change": (roster, roster.governing_cutoff_date),
        "attendance_correction": (attendance, attendance.governing_correction_terms),
        "adjustment_posting": (adjustment, adjustment.governing_posting_terms),
        "owner_operations": (owner_configuration, owner_configuration.governing_owner_operations),
    }
    result = {}
    for key, (module, resolver) in modules.items():
        rows = frappe.get_all(module.POLICY, fields=["name", "code", "status"], order_by="name asc")
        if not rows:
            raise AssertionError(f"Missing policy row after native acceptance: {key}")
        policies = []
        for row in rows:
            doc = frappe.get_doc(module.POLICY, row["name"])
            versions = []
            for version in (doc.get("versions") or []):
                data = version.as_dict()
                for field in ("creation", "modified", "owner", "modified_by", "docstatus", "idx"):
                    data.pop(field, None)
                versions.append(_normalize(data))
            policies.append({
                "name": doc.name,
                "code": doc.get("code") or "",
                "status": doc.get("status") or "",
                "versions": versions,
            })
        result[key] = {
            "policies": policies,
            "effective_terms": _normalize(resolver()),
        }
    backup = owner_configuration.current_backup_policy()
    switch = owner_configuration.backup_switch_state()
    if switch.get("enabled") is not True or backup.get("configured") is not True:
        raise AssertionError("Owner-chosen On state or backup policy did not persist")
    result["owner_operations"]["backup_consumer"] = _normalize({
        key: backup.get(key) for key in
        ("configured", "status", "schedule_time", "retention_versions", "retention_behavior")
    })
    return result


def _exercise_off_switches(frappe):
    """Exercise each policy's live resolver and fail-closed switch after restart.

    Every mutation runs in a savepoint and is rolled back; this uses only the
    disposable restore site and leaves no policy/audit changes behind.
    """
    from toefl_house.academic import catalog_linkage
    from toefl_house.admission import policies as returning
    from toefl_house.enrollment import exits
    from toefl_house.finance import policies as billing
    from toefl_house.teaching import policies as roster
    from toefl_house.teaching import attendance_corrections as attendance
    from toefl_house.teaching import adjustment_posting as adjustment
    from toefl_house.operations import owner_configuration

    controls = {
        "catalog_linkage": (catalog_linkage, catalog_linkage.set_catalog_linkage_status,
                            catalog_linkage.governing_linkage_terms),
        "returning_student": (returning, returning.set_returning_student_policy_status,
                              returning.governing_returning_mode),
        "enrollment_exit": (exits, exits.set_enrollment_exit_policy_status,
                            exits.governing_exit_terms),
        "billing": (billing, billing.set_billing_policy_status,
                    billing.governing_billing_terms),
        "roster_change": (roster, roster.set_roster_change_policy_status,
                          roster.governing_cutoff_date),
        "attendance_correction": (attendance, attendance.set_attendance_correction_policy_status,
                                  attendance.governing_correction_terms),
        "adjustment_posting": (adjustment, adjustment.set_adjustment_posting_status,
                               adjustment.governing_posting_terms),
        "owner_operations": (owner_configuration, owner_configuration.set_owner_operations_policy_status,
                             owner_configuration.governing_owner_operations),
    }
    verified = []
    for index, (key, (module, set_status, resolver)) in enumerate(controls.items()):
        rows = frappe.get_all(module.POLICY, fields=["name", "code", "status"], order_by="name asc")
        if len(rows) != 1:
            raise AssertionError(f"Expected one singleton policy row for off-switch probe: {key}")
        row = rows[0]
        before_terms = _normalize(resolver())
        savepoint = f"policy_restart_off_{index}"
        frappe.db.savepoint(savepoint)
        off_switch_result = "retirement fail-closed verified"
        try:
            frappe.set_user(OWNER)
            if row["status"] != "Active":
                set_status(f"restart_{key}_activate_0001", row["code"], 1)
            live_terms = resolver()
            # D5 intentionally keeps enrollment exits closed in the canonical
            # Owner decision ledger. Do not claim its policy off-switch was
            # exercised when no effective terms can resolve even while Active.
            d5_closed = key == "enrollment_exit" and not live_terms
            if not live_terms and not d5_closed:
                raise AssertionError(f"Could not resolve effective terms for {key} before off-switch")
            if d5_closed:
                off_switch_result = "D5 remains fail-closed; no live terms to switch off"
            set_status(f"restart_{key}_retire_0001", row["code"], 0)
            if resolver():
                raise AssertionError(f"{key} resolver remained live after retirement")
            if key == "owner_operations" and owner_configuration.current_backup_policy().get("configured"):
                raise AssertionError("Owner Operations backup consumer stayed configured after retirement")
        finally:
            frappe.db.rollback(save_point=savepoint)
            frappe.set_user("Administrator")
        if _normalize(resolver()) != before_terms:
            raise AssertionError(f"{key} state did not roll back after off-switch probe")
        if key == "owner_operations":
            backup = owner_configuration.current_backup_policy()
            if backup.get("configured") is not True:
                raise AssertionError("Owner Operations backup consumer did not return after rollback")
        verified.append({"policy": key, "result": off_switch_result})
    return verified


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Hosted disposable runner only")
    if len(sys.argv) != 3 or sys.argv[1] not in {"capture", "verify"} or sys.argv[2] != SITE:
        raise SystemExit("Usage: policy_restart_check.py capture|verify placement-restore.localhost")
    expected_path = Path(os.environ["PLACEMENT_POLICY_RESTART_EXPECTATION"])
    action = sys.argv[1]
    import frappe

    frappe.init(site=SITE)
    frappe.connect()
    try:
        frappe.set_user("Administrator")
        from toefl_house.operations import owner_configuration
        if action == "capture":
            _ensure_owner_operations_policy(frappe, owner_configuration)
            actual = _snapshot(frappe)
            expected_path.write_text(json.dumps(actual, indent=2, sort_keys=True, default=str) + "\n")
            print(json.dumps({
                "status": "captured",
                "policy_resolvers": sorted(actual),
                "policy_rows": sum(len(value["policies"]) for value in actual.values()),
            }, sort_keys=True))
            return 0
        expected = json.loads(expected_path.read_text())
        actual = _snapshot(frappe)
        if actual != expected:
            changed = [key for key in sorted(set(actual) | set(expected))
                       if actual.get(key) != expected.get(key)]
            raise AssertionError("Policy state/resolvers changed across service restart: " + ", ".join(changed))
        off_switches = _exercise_off_switches(frappe)
        print(json.dumps({
            "status": "pass",
            "policy_resolvers_verified": sorted(actual),
            "policy_rows": sum(len(value["policies"]) for value in actual.values()),
            "owner_operations_backup_consumer_verified": True,
            "post_restart_off_switches_verified": off_switches,
            "off_switch_changes_rolled_back": True,
        }, sort_keys=True))
        return 0
    finally:
        frappe.destroy()


if __name__ == "__main__":
    raise SystemExit(main())

"""Genuine initial assessment configuration, rolled back after qualification."""
from datetime import date, timedelta
import hashlib
import json
import secrets

import frappe


def run(owner_user, forbidden_user):
    from toefl_house import academic
    from toefl_house.administration import set_managed_role
    from toefl_house.academic import rules
    from toefl_house.policy import digest, request_digest
    from toefl_house.security import SYNTHETIC, site_mode
    from toefl_house.setup_presets.native_grading_scale import create_owner_grading_scale

    assert site_mode() == SYNTHETIC and not frappe.conf.get("toefl_house_production_active")
    original_user = frappe.session.user
    tables = ("User", "Has Role", "Version", "TH Academic Program", "TH Program Level", "Program", "Program Course", "Course", "Room", "Grading Scale",
              "Grading Scale Interval", "TH Assessment Policy", "TH Assessment Policy Version",
              "TH Configuration Operation", "TH Configuration Audit Event", "Fees", "GL Entry")

    def snapshot():
        return {dt: hashlib.sha256(json.dumps(frappe.get_all(
            dt, fields=["*"], order_by="name asc", limit_page_length=0),
            sort_keys=True, default=str).encode()).hexdigest() for dt in tables}

    before = snapshot()
    token = secrets.token_hex(6).upper()
    family, foreign_family = "INIT-" + token, "OTHER-" + token
    level, foreign_level = "LEVEL-" + token, "FOREIGN-" + token
    policy, bad_policy = "POLICY-" + token, "BAD-" + token
    legacy_policy = "LEGACY-" + token
    scale = "Synthetic initial grading " + token
    day = frappe.utils.today()
    key = "initial-assessment-" + token.lower()
    reason = "Synthetic native initial snapshot qualification, rolled back"
    frappe.db.savepoint("initial_assessment_root")
    try:
        frappe.set_user(owner_user)
        staff = frappe.get_doc({"doctype": "User", "email": "initial-role-" + token.lower() + "@example.test",
                               "first_name": "Synthetic staged staff", "enabled": 0,
                               "send_welcome_email": 0, "user_type": "System User",
                               "roles": [{"role": "Reception"}]})
        staff.insert(ignore_permissions=True)
        granted = set_managed_role(key + "grant-role", staff.name, "Enrollment Officer", True)
        assert granted["changed"] is True
        assert "Enrollment Officer" in {row.role for row in frappe.get_doc("User", staff.name).roles}
        assert not frappe.db.get_value("User", staff.name, "enabled")
        replay = set_managed_role(key + "grant-role", staff.name, "Enrollment Officer", True)
        assert replay["replayed"] and replay["changed"]
        set_managed_role(key + "revoke-role", staff.name, "Enrollment Officer", False)
        assert "Enrollment Officer" not in {row.role for row in frappe.get_doc("User", staff.name).roles}
        for code in (family, foreign_family):
            academic.create_program(key + code.lower(), code, code, reason)
        for code, parent in ((level, family), (foreign_level, foreign_family)):
            academic.create_level(key + code.lower(), parent, code, code, 1,
                                  2, "Solar Hijri Month", day)
            native_program = frappe.db.get_value("TH Program Level", code, "native_program")
            native = frappe.get_doc("Program", native_program)
            assert len(native.courses) == 1 and native.courses[0].required
            assert frappe.db.exists("Course", native.courses[0].course)
        room_name = "Synthetic initial room " + token
        room = academic.create_room(key + "room", room_name, 15, reason)
        assert room == academic.create_room(key + "room", room_name, 15, reason)
        assert int(frappe.db.get_value("Room", room["name"], "seating_capacity")) == 15
        create_owner_grading_scale(key + "scale", scale,
                                   [{"grade_code": "P", "threshold": 60},
                                    {"grade_code": "F", "threshold": 0}], reason)
        for code in (policy, bad_policy, legacy_policy):
            academic.create_assessment_policy(key + code.lower(), family, code, code, reason)
        facets = {
            "components": [{"code": "SPK", "title": "Speaking", "maximum_score": 100}],
            "weights": [{"component": "SPK", "weight": 100}],
            "pass_rules": {"overall": {"kind": "percent", "value": 60}},
            "rubrics": [],
            "progression": {"target": "next", "requires": [
                {"kind": "assessment_pass", "policy": policy},
                {"kind": "approval", "role": "Academic Manager"}]},
            "retakes": {"max_attempts": 2, "wait_days": 7, "scope": "full", "governing": "best"},
            "level_mapping": {"levels": [level]},
        }
        result = academic.set_assessment_policy_version(key + "version", policy, day,
                                                        reason, scale, facets)
        doc = frappe.get_doc("TH Assessment Policy", policy)
        assert len(doc.versions) == 1 and doc.versions[0].grading_scale == scale
        parsed = rules.validate_policy_facets(doc.versions[0].as_dict())
        assert set(parsed) == set(rules.ASSESSMENT_FACETS) - {"rubrics"}
        assert parsed["pass_rules"]["overall"]["value"] == 60
        assert result == academic.set_assessment_policy_version(
            key + "version", policy, day, reason, scale, facets)
        academic.validate_assessment_policy(key + "validate", policy)

        def refused(callback, exception=frappe.ValidationError):
            frappe.db.savepoint("initial_assessment_negative")
            try:
                try:
                    callback()
                except exception:
                    return
                raise AssertionError("Unsafe initial assessment input was accepted")
            finally:
                frappe.db.rollback(save_point="initial_assessment_negative")

        next_day = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        refused(lambda: academic.create_room(key + "room-duplicate", room_name, 30, reason))
        assert int(frappe.db.get_value("Room", room["name"], "seating_capacity")) == 15
        refused(lambda: academic.create_room(key + "room-zero", room_name + " zero", 0, reason))
        refused(lambda: academic.set_assessment_policy_version(
            key + "rewrite", policy, next_day, reason, scale, facets))
        assert len(frappe.get_doc("TH Assessment Policy", policy).versions) == 1
        bad_mapping = dict(facets, level_mapping={"levels": [foreign_level]})
        refused(lambda: academic.set_assessment_policy_version(
            key + "foreign", bad_policy, day, reason, scale, bad_mapping))
        bad_grade = dict(facets, pass_rules={"overall": {"kind": "grade", "value": "Z"}})
        refused(lambda: academic.set_assessment_policy_version(
            key + "grade", bad_policy, day, reason, scale, bad_grade))
        assert not frappe.get_doc("TH Assessment Policy", bad_policy).versions
        frappe.set_user(forbidden_user)
        refused(lambda: set_managed_role(key + "unauthorized-role", staff.name,
                                        "Enrollment Officer", True), frappe.PermissionError)
        assert "Enrollment Officer" not in {row.role for row in frappe.get_doc("User", staff.name).roles}
        refused(lambda: academic.create_room(key + "room-unauthorized", room_name + " denied", 15, reason),
                frappe.PermissionError)
        refused(lambda: academic.set_assessment_policy_version(
            key + "unauthorized", bad_policy, day, reason, scale, facets), frappe.PermissionError)
        frappe.set_user(owner_user)
        academic.set_assessment_policy_version(key + "legacy", legacy_policy, day, reason, scale)
        original_payload = {"policy": legacy_policy, "effective_from": day,
                            "reason": reason, "grading_scale": scale}
        operation = digest(["set_assessment_policy_version", key + "legacy"])
        assert frappe.db.get_value("TH Configuration Operation", operation, "input_hash") == request_digest(
            original_payload, frappe.conf.get("encryption_key"))
        return {"native_database": True, "one_complete_initial_version": True,
                "native_user_role_grant_replay_revoke_while_disabled": True,
                "non_owner_role_grant_refused": True,
                "new_levels_have_required_native_courses": True,
                "native_room_creation_replay_and_duplicate_preservation": True,
                "invalid_capacity_and_non_owner_room_creation_refused": True,
                "same_key_replay": True, "historical_rewrite_refused": True,
                "foreign_family_refused": True, "unknown_grade_refused": True,
                "non_owner_refused": True, "old_receipt_payload_compatible": True,
                "all_test_records_rolled_back": True}
    finally:
        frappe.db.rollback(save_point="initial_assessment_root")
        frappe.set_user(original_user)
        assert snapshot() == before, "Initial assessment qualification changed pre-existing records"

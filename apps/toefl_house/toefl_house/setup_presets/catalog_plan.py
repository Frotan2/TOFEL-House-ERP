"""Pure, safe first-run command planner for native academic catalog records.

This module does not import Frappe, create documents, issue receivables or
enable operational controls. A future audited Owner installer must explicitly
authorize and execute these commands within the native transaction boundary.
"""
from __future__ import annotations

from toefl_house.setup_presets.preset import load_preset, preview_catalog, validate_preset


def prepare_catalog_plan(snapshot: dict, preset: dict | None = None) -> dict:
    preset = validate_preset(preset or load_preset())
    preview = preview_catalog(snapshot, preset)
    if preview["counts"]["review"]:
        raise ValueError("Existing configuration conflicts require explicit Owner mapping before setup")
    statuses = {
        (item["kind"], item["code"]): item["status"]
        for item in preview["actions"]
    }
    actions = []

    for year in preset["academic_years"]:
        if statuses[("academic_year", year["name"])] == "create":
            actions.append({"operation": "create_academic_year",
                            "name": year["name"],
                            "start_date": year["start"],
                            "end_date": year["end"]})
    for program in preset["programs"]:
        if statuses[("program", program["code"])] == "create":
            actions.append({"operation": "create_program",
                            "code": program["code"],
                            "title": program["title"],
                            "description": ""})
    for program in preset["programs"]:
        for level in program["levels"]:
            if statuses[("level", level["code"])] == "create":
                actions.append({"operation": "create_level",
                                "family": program["code"],
                                "code": level["code"],
                                "title": level["title"],
                                "sequence": level["sequence"],
                                "duration_value": level["duration_months"],
                                "duration_unit": "Month",
                                "next_level": ""})
    # Native next_level accepts successors in the same family only.
    # Linking happens after all levels have been created; this prevents
    # dangling references and never links an independent/concurrent track.
    for program in preset["programs"]:
        if program["progression_kind"] != "sequential":
            continue
        levels = program["levels"]
        for previous, following in zip(levels, levels[1:]):
            if statuses[("level", previous["code"])] == "create":
                actions.append({"operation": "set_next_level",
                                "level": previous["code"],
                                "next_level": following["code"]})
    category = preset["fee_policy"]["category"]
    if statuses[("fee_category", category)] == "create":
        actions.append({"operation": "create_fee_type", "name": category,
                        "description": "Approved semester tuition (native Education)"})
    for program in preset["programs"]:
        for level in program["levels"]:
            for year in preset["academic_years"]:
                key = level["code"] + "@" + year["name"]
                if statuses[("tuition", key)] == "create":
                    actions.append({
                        "operation": "set_level_fee_component",
                        "level": level["code"],
                        "academic_year": year["name"],
                        "fee_category": category,
                        "amount": level["semester_tuition_afn"],
                    })
    allowed = {"create_academic_year", "create_program", "create_level",
               "set_next_level", "create_fee_type", "set_level_fee_component"}
    if any(action["operation"] not in allowed for action in actions):
        raise ValueError("Unsupported or potentially destructive setup command")
    return {"mode": "REQUIRES_EXPLICIT_OWNER_AUTHORIZATION",
            "preset_id": preset["preset_id"],
            "actions": actions,
            "count": len(actions),
            "preview": preview,
            "permitted_to_execute": False,
            "excluded": ["Student", "Program Enrollment", "Fees", "Payment Entry",
                         "Salary Slip", "Discount Rule", "Owner Operations Policy",
                         "Backup & Recovery", "Tax", "Academic Result"]}


def action_request_key(preset_id: str, action: dict) -> str:
    """Stable action-level idempotency identity for an authorized integrator."""
    import hashlib
    import json

    if not isinstance(preset_id, str) or not preset_id:
        raise ValueError("Preset identity is required")
    payload = json.dumps([preset_id, action], sort_keys=True,
                         separators=(",", ":"), ensure_ascii=True)
    return "OWNERSETUP-" + hashlib.sha256(payload.encode("ascii")).hexdigest()[:48]

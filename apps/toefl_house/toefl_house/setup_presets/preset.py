"""Pure, non-mutating TOEFL House setup preset validation and preview.

This module deliberately does not import Frappe or write records. The installer
must not convert owner proposals into live business policy without a separate
authorized and audited confirmation workflow.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path


PRESET_FILENAME = "toefl_house_afghanistan_1405.json"


def validate_preset(data: dict) -> dict:
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported setup preset version")
    if data.get("status") != "PROPOSED_FOR_SYNTHETIC_TEST_ONLY":
        raise ValueError("Unreviewed preset cannot be declared production ready")

    families = data.get("programs") or []
    if len(families) < 4:
        raise ValueError("The four in-person TOEFL House programs are required")
    codes, levels, policy_codes, aliases = set(), set(), set(), set()
    for family in families:
        code = family["code"]
        if code in codes:
            raise ValueError(f"Duplicate program code: {code}")
        codes.add(code)
        if not isinstance(family.get("initial_tuition_approved", False), bool):
            raise ValueError(f"Initial tuition approval must be an explicit boolean in {code}")
        policy_code = family.get("assessment_policy_code")
        if not isinstance(policy_code, str) or not policy_code.strip():
            raise ValueError(f"Missing assessment policy identity in {code}")
        if policy_code in policy_codes:
            raise ValueError(f"Duplicate assessment policy code: {policy_code}")
        policy_codes.add(policy_code)
        skill_weights = family.get("assessment_skill_weights_percent") or {}
        allowed_skills = {
            "speaking", "listening", "writing", "reading",
            "grammar", "vocabulary",
        }
        if (not skill_weights or any(skill not in allowed_skills
                                     for skill in skill_weights)
                or any(isinstance(weight, bool)
                       or not isinstance(weight, (int, float))
                       or weight < 0 for weight in skill_weights.values())
                or sum(skill_weights.values()) != 100):
            raise ValueError(f"Assessment skills must total 100 in {code}")
        positions = set()
        for level in family.get("levels") or []:
            level_code = level["code"]
            if level_code in levels:
                raise ValueError(f"Duplicate level code: {level_code}")
            levels.add(level_code)
            for alias in level.get("existing_site_aliases") or []:
                if (not isinstance(alias, str) or not alias.strip()
                        or alias == level_code or alias in levels or alias in aliases):
                    raise ValueError(f"Invalid or duplicate existing-site level alias: {alias!r}")
                aliases.add(alias)
            position = level["sequence"]
            if position in positions:
                raise ValueError(f"Duplicate position in {code}: {position}")
            positions.add(position)
            if (not isinstance(level["duration_months"], int)
                    or level["duration_months"] < 1):
                raise ValueError(f"Invalid duration for {level_code}")
            if (not isinstance(level["semester_tuition_afn"], int)
                    or level["semester_tuition_afn"] < 1):
                raise ValueError(f"Invalid fee for {level_code}")
    if levels & aliases:
        raise ValueError("An existing-site alias conflicts with a configured level")
    for family in families:
        count = len(family["levels"])
        if sorted(x["sequence"] for x in family["levels"]) != list(range(1, count + 1)):
            raise ValueError(f"Positions must be sequential in {family['code']}")

    assessment = data["assessment"]
    skills = assessment["skills_weight_percent"]
    continuous = assessment["continuous_subweights_percent"]
    continuous_pct = assessment["continuous_percent"]
    final_pct = assessment["final_exam_percent"]
    if (sum(skills.values()) != 100
            or sum(continuous.values()) != continuous_pct
            or continuous_pct + final_pct != 100
            or continuous_pct <= 0 or final_pct <= 0):
        raise ValueError("Assessment component weights must equal their declared percentages")
    scale = assessment["grading_scale"]["grade_thresholds"]
    thresholds = [x["min_percent"] for x in scale]
    if (thresholds != sorted(set(thresholds), reverse=True)
            or len([x for x in scale if x["min_percent"] == 0]) != 1):
        raise ValueError("The grading scale needs unique descending thresholds and one zero")
    if not any(x["min_percent"] == assessment["overall_pass_percent"]
               for x in scale):
        raise ValueError("An explicit pass-grade threshold must match the minimum pass percentage")
    retake = assessment["retake"]
    if (retake["max_total_attempts"] != 2 or retake["wait_days"] < 7
            or retake["governing"] not in ("latest", "best", "first")):
        raise ValueError("Proposed retake count and wait require policy review")
    if (not data["fee_policy"]["late_join_full_original_course_fee"]
            or not data["fee_policy"]["installment_amounts_must_sum_to_net_tuition"]
            or not data["discounts"]["preapprovals_stored_before_any_active_rule"]):
        raise ValueError("The approved full-fee and discount-authorization safeguards are mandatory")
    if (assessment["placement"]["fee_afn_per_attempt"] <= 0
            or not assessment["placement"]["paper_exam_component"]
            or not assessment["placement"]["face_to_face_speaking_component"]):
        raise ValueError("The paid two-component placement policy must be complete")

    if data["cross_program_transition"]["from"] not in levels:
        raise ValueError("Unknown cross-program source")
    if data["cross_program_transition"]["to"] not in levels:
        raise ValueError("Unknown cross-program target")
    if data["cross_program_transition"].get("automated"):
        raise ValueError("Cross-program admission must not be silent progression")
    if not data["discounts"]["templates_are_inactive_by_default"]:
        raise ValueError("A general discount must not silently apply to all students")
    if not data["discounts"]["hundred_percent_only_student_specific"]:
        raise ValueError("100% waivers must identify the student")
    online = data["online_one_to_one"]
    if online.get("teacher_student_ratio") != "1:1":
        raise ValueError("Online One-to-One must remain one instructor per student")
    tuition = online["tuition"]
    if (tuition.get("period") != "one_calendar_month"
            or tuition.get("pricing_type") != "negotiated_per_student_contract"
            or tuition.get("currency") != "AFN"
            or not tuition.get("needs_owner_approved_student_contract")
            or not tuition.get("separate_from_on_site_semester_fee_structure")
            or not tuition.get("amounts_are_guidance_not_automatically_charged")):
        raise ValueError("Online fees must be separately negotiated monthly student tuition")
    examples = tuition.get("suggested_monthly_afn") or {}
    if (examples.get("general_english") != 5000
            or examples.get("eap_min") != 6000
            or examples.get("eap_max") != 7000
            or examples.get("toefl_preparation") != 9000):
        raise ValueError("Owner-supplied online student tuition guidance changed")
    pay = online["instructor_pay"]
    if (pay.get("source_of_truth")
            != "Native HRMS/Payroll and authorized instructor agreement"
            or not pay.get("never_derive_payroll_automatically_from_student_tuition")
            or not pay.get("no_payroll_posting_during_setup")):
        raise ValueError("Instructor compensation must remain under authorized payroll")
    controls = online["financial_controls"]
    if (not controls.get("online_tuition_and_payroll_are_independent_ledgers")
            or not controls.get("no_auto_invoice_without_contract_and_authorization")
            or not controls.get("no_auto_salary_posting_without_payroll_approval")
            or not controls.get("gross_receipts_minus_teacher_cost_is_not_automatically_net_profit")
            or not online.get("no_default_billing_or_salary_posting")
            or not online.get("requires_named_student_instructor_contract_and_schedule")):
        raise ValueError("One-to-one student tuition and payroll controls are mandatory")
    if data["backup"]["enabled"] or data["tax"]["enabled_for_student_fee_billing"]:
        raise ValueError("Unverified tax and backup cannot be automatically enabled")
    if not data["safety"]["never_overwrite_existing_records"]:
        raise ValueError("Setup must not overwrite user records")
    return data


def load_preset() -> dict:
    path = Path(__file__).with_name(PRESET_FILENAME)
    data = json.loads(path.read_text(encoding="utf-8"))
    return copy.deepcopy(validate_preset(data))


def _action(kind: str, code: str, status: str, details: str) -> dict:
    return {"kind": kind, "code": code, "status": status, "details": details}


def preview_catalog(snapshot: dict, preset: dict | None = None) -> dict:
    """Compare live catalog *facts* with the fixture without changing either.

    snapshot is an already-authorized read-only view:
      programs: {code: {"title": ...}}
      levels: {code: {"family": ..., "title": ..., "duration_months": ...}}
      years: {name: {"start": ..., "end": ...}}
      fee_categories: iterable of exact native Fee Category names
      tuition: {"LEVEL-CODE": {"1405": integer_price_afn}}
    The planner flags disagreement for manual review, never overwrites it.
    """
    preset = validate_preset(copy.deepcopy(preset or load_preset()))
    existing_programs = snapshot.get("programs") or {}
    existing_levels = snapshot.get("levels") or {}
    existing_years = snapshot.get("years") or {}
    categories = set(snapshot.get("fee_categories") or [])
    category_items = snapshot.get("fee_category_items")
    tuition = snapshot.get("tuition") or {}
    steps = []
    for year in preset["academic_years"]:
        known = existing_years.get(year["name"])
        status = ("create" if known is None else
                  "match" if known.get("start") == year["start"]
                  and known.get("end") == year["end"] else "review")
        steps.append(_action("academic_year", year["name"], status,
                             "Annual dates must match; no automatic amendment"))
    for family in preset["programs"]:
        code = family["code"]
        existing = existing_programs.get(code)
        status = ("create" if existing is None else
                  "match" if (existing.get("title") == family["title"]
                              and existing.get("status", "Active") == "Active")
                  else "review")
        steps.append(_action("program", code, status,
                             "Retain existing catalog rows; never duplicate"))
        for position, level in enumerate(family["levels"]):
            level_code = level["code"]
            expected_next = (family["levels"][position + 1]["code"]
                             if family["progression_kind"] == "sequential"
                             and position + 1 < len(family["levels"]) else "")
            existing = existing_levels.get(level_code)
            aliases_found = [alias for alias in level.get("existing_site_aliases", [])
                             if alias in existing_levels]
            if aliases_found:
                # Never silently introduce a second native Program for a level.
                status = "review"
                details = ("Existing site uses alternative code(s) " +
                           ", ".join(aliases_found) +
                           "; map the current native Program explicitly")
            else:
                status = ("create" if existing is None else
                          "match" if (existing.get("family") == code
                                      and existing.get("duration_months") == level["duration_months"]
                                      and existing.get("title") == level["title"]
                                      and existing.get("status", "Active") == "Active"
                                      and ("native_program" not in existing
                                           or bool(existing["native_program"]))
                                      and ("next_level" not in existing
                                           or (existing["next_level"] or "") == expected_next))
                          else "review")
                details = "Check family, name and effective-dated duration"
            steps.append(_action("level", level_code, status, details))
            for year in preset["academic_years"]:
                actual = (tuition.get(level_code) or {}).get(year["name"])
                # Approval is preset configuration, never inferred from a
                # program name or code. Missing approval defers fee creation.
                # Historical examples must not become draft prices by default.
                approved_initial_tuition = family.get("initial_tuition_approved", False)
                if aliases_found or (not approved_initial_tuition and actual is not None):
                    status = "review"
                elif not approved_initial_tuition:
                    status = "deferred"
                else:
                    status = ("create" if actual is None else
                              "match" if actual == level["semester_tuition_afn"]
                              else "review")
                details = ("Owner confirmation of specialist tuition required; "
                           "do not create or reuse an unapproved price"
                           if not approved_initial_tuition else
                           "Approved on-site semester price; never modify posted Fees")
                steps.append(_action("tuition", level_code + "@" + year["name"],
                                     status, details))
    category = preset["fee_policy"]["category"]
    category_status = ("match" if category in categories else "create")
    if (category_status == "match" and category_items is not None
            and not category_items.get(category)):
        category_status = "review"
    steps.append(_action("fee_category", category, category_status,
                         "Native Education Fee Category and linked Item required"))
    counts = {state: sum(x["status"] == state for x in steps)
              for state in ("create", "match", "review", "deferred")}
    return {
        "mode": "READ_ONLY_PREVIEW",
        "preset_id": preset["preset_id"],
        "actions": steps,
        "counts": counts,
        "ready_to_apply": False,
        "pending_decisions": [
            "Owner verification and auditable confirmation",
            *(["Specialist tuition requires separate Owner price verification before live billing"]
              if any(not family.get("initial_tuition_approved", False)
                     for family in preset["programs"]) else []),
            "Legal tax classification; do not infer exemption",
            "Approve negotiated one-to-one monthly student tuition and named contract",
            "Approve instructor remuneration independently through HRMS/Payroll",
            "Native grading scale / policy version qualification",
            "Solar-Hijri month-based installment due-date implementation",
            "Windows backup and isolated restore acceptance",
        ],
    }

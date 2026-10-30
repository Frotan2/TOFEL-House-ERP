"""Human-friendly initial academic policy form; no JSON entered by the Owner.

Only brand-new GE/EAP policies are supported. The underlying academic command
remains the authority for permissions, native links, dates, audit, replay and
transaction rollback. No policy is activated automatically at installation.
"""
from __future__ import annotations

import frappe

from toefl_house import academic
from toefl_house.setup_presets.assessment_facets import build_assessment_facets
from toefl_house.setup_presets.api import _owner
from toefl_house.setup_presets.preset import load_preset


def initial_assessment_values(family, policy, passing_score, retake_wait_days):
    """Resolve the approved family template using only scalar Owner inputs."""
    preset = load_preset()
    programs = {row["code"]: row for row in preset["programs"]}
    if family not in ("GEN-ENG", "EAP") or family not in programs:
        raise ValueError(
            "This graded assessment form supports General English and EAP only; "
            "Special Speaking and TOEFL Preparation use separate progress reports")
    if not isinstance(policy, str) or not policy.strip():
        raise ValueError("Choose an existing academic assessment policy first")
    def whole(value, label, minimum, maximum):
        if isinstance(value, bool) or not str(value).strip().isdigit():
            raise ValueError(f"{label} must be a whole number")
        number = int(str(value).strip())
        if not minimum <= number <= maximum:
            raise ValueError(f"{label} must be from {minimum} to {maximum}")
        return number
    pass_score = whole(passing_score, "Pass mark", 1, 100)
    waiting = whole(retake_wait_days, "Retake wait", 7, 365)

    facets = build_assessment_facets(family, preset)
    if set(facets) != {
        "components", "weights", "pass_rules", "rubrics",
        "progression", "retakes", "level_mapping",
    }:
        raise ValueError("The academic template is incomplete; no policy was saved")
    facets["pass_rules"]["overall"] = {"kind": "percent", "value": pass_score}
    facets["retakes"]["wait_days"] = waiting
    # No additional retake: one initial attempt and one retake, retaining best.
    facets["retakes"]["max_attempts"] = 2
    facets["retakes"]["governing"] = "best"
    for evidence in facets["progression"]["requires"]:
        if evidence.get("kind") == "assessment_pass":
            evidence["policy"] = policy.strip()
    return facets


@frappe.whitelist(methods=["POST"])
def configure_initial_assessment(
        request_key, policy, effective_from, reason, grading_scale,
        passing_score=60, retake_wait_days=7):
    """Create one audited initial version from normal numeric form controls.

    The User interface never asks for a code, JSON object, schema or command.
    A previously versioned policy is refused by the existing native command.
    """
    _owner()
    if not isinstance(policy, str) or not policy.strip():
        raise frappe.ValidationError("Select an existing assessment policy")
    row = frappe.db.get_value(
        "TH Assessment Policy", {"code": policy.strip()},
        ["family", "status"], as_dict=True)
    if not row or row.status != "Active":
        raise frappe.ValidationError("Choose an active, unconfigured assessment policy")
    family = frappe.db.get_value("TH Academic Program", row.family, "code")
    if not family:
        raise frappe.ValidationError("The assessment policy has no valid program family")
    if not grading_scale or not frappe.db.exists(
            "Grading Scale", {"name": grading_scale, "docstatus": 1}):
        raise frappe.ValidationError(
            "Choose a submitted native grading scale; create it with the numeric "
            "A/B/C/D grade form before configuring this policy")
    try:
        facets = initial_assessment_values(
            family, policy, passing_score, retake_wait_days)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    return academic.set_assessment_policy_version(
        request_key=request_key,
        policy=policy.strip(),
        effective_from=effective_from,
        reason=reason,
        grading_scale=grading_scale,
        initial_facets=facets,
    )

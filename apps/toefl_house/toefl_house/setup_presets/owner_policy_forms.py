"""Human-friendly initial academic policy form; no JSON entered by the Owner.

Only graded program templates are supported for initialization. The underlying academic command
remains the authority for permissions, native links, dates, audit, replay and
transaction rollback. No policy is activated automatically at installation.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

import frappe

from toefl_house import academic
from toefl_house.setup_presets.assessment_facets import build_assessment_facets
from toefl_house.setup_presets.api import _owner
from toefl_house.setup_presets.preset import load_preset


def whole_number(value, label, minimum, maximum):
    """Accept Frappe's 60/60.0 percent fields, never round a fraction."""
    if (isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal))
            or len(str(value)) > 32):
        raise ValueError(f"{label} must be a whole number")
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a whole number") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError(f"{label} must be a whole number")
    if not minimum <= number <= maximum:
        raise ValueError(f"{label} must be from {minimum} to {maximum}")
    return int(number)


def graded_template_family_codes():
    return tuple(row["code"] for row in load_preset()["programs"]
                 if row.get("progression_kind") == "sequential")


def active_family_level_mapping(family):
    """Use native level identities, including preserved Owner catalog names."""
    levels = frappe.get_all(
        "TH Program Level", filters={"family": family, "status": "Active"},
        fields=["code"], order_by="sequence asc, code asc", limit_page_length=101)
    if not levels or len(levels) > 100:
        raise frappe.ValidationError(
            "The program needs between 1 and 100 active levels before its "
            "initial assessment policy can be configured")
    return {"levels": [level["code"] for level in levels]}


def initial_assessment_values(family, policy, passing_score, retake_wait_days):
    """Resolve the approved family template using only scalar Owner inputs."""
    preset = load_preset()
    programs = {row["code"]: row for row in preset["programs"]}
    if family not in graded_template_family_codes() or family not in programs:
        raise ValueError(
            "This form supports graded program templates only; "
            "Special Speaking and TOEFL Preparation use separate progress reports")
    if not isinstance(policy, str) or not policy.strip():
        raise ValueError("Choose an existing academic assessment policy first")
    facets = build_assessment_facets(family, preset)
    if passing_score is None:
        passing_score = facets["pass_rules"]["overall"]["value"]
    minimum_wait = facets["retakes"]["wait_days"]
    if retake_wait_days is None:
        retake_wait_days = minimum_wait
    pass_score = whole_number(passing_score, "Pass mark", 1, 100)
    waiting = whole_number(retake_wait_days, "Retake wait", minimum_wait, 365)
    if set(facets) != {
        "components", "weights", "pass_rules", "rubrics",
        "progression", "retakes", "level_mapping",
    }:
        raise ValueError("The academic template is incomplete; no policy was saved")
    facets["pass_rules"]["overall"] = {"kind": "percent", "value": pass_score}
    facets["retakes"]["wait_days"] = waiting
    # No additional retake: one initial attempt and one retake, retaining best.
    for evidence in facets["progression"]["requires"]:
        if evidence.get("kind") == "assessment_pass":
            evidence["policy"] = policy.strip()
    return facets


@frappe.whitelist(methods=["POST"])
def configure_initial_assessment(
        request_key, policy, effective_from, reason, grading_scale,
        passing_score=None, retake_wait_days=None,
        speaking=None, listening=None, writing=None, reading=None,
        grammar=None, vocabulary=None, continuous_percent=None):
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
        # The clean-install template supplies policy values, not replacement
        # identities for an existing Owner's native academic catalog.
        facets["level_mapping"] = active_family_level_mapping(row.family)
        defaults = load_preset()["assessment"]
        values = dict(speaking=speaking, listening=listening, writing=writing,
                      reading=reading, grammar=grammar, vocabulary=vocabulary)
        values = {name: defaults["skills_weight_percent"][name] if value is None else value
                  for name, value in values.items()}
        continuous = defaults["continuous_percent"] if continuous_percent is None else continuous_percent
        facets["weights"] = numeric_skill_distribution(**values, continuous_percent=continuous)
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


SKILL_PREFIX = {
    "speaking": "SPK", "listening": "LST", "writing": "WRT",
    "reading": "RDG", "grammar": "GRM", "vocabulary": "VOC",
}


def numeric_skill_distribution(
        speaking, listening, writing, reading, grammar, vocabulary,
        continuous_percent):
    """Convert seven visible numbers to the native 12-component 100% weights.

    One 100% distribution covers all six skills. Each subject's part is
    split into Continuous and Final in the Owner-chosen proportions.
    """
    values = (speaking, listening, writing, reading, grammar, vocabulary)
    shares = [whole_number(value, label, 0, 100)
              for value, label in zip(values, SKILL_PREFIX)]
    if sum(shares) != 100:
        raise ValueError("The six skill percentages must total exactly 100")
    ca = whole_number(continuous_percent, "Continuous assessment percentage", 1, 99)
    result = []
    for (_, prefix), share in zip(SKILL_PREFIX.items(), shares):
        result.append({"component": prefix + "-CA",
                       "weight": share * ca / 100})
        result.append({"component": prefix + "-FINAL",
                       "weight": share * (100 - ca) / 100})
    return result


@frappe.whitelist(methods=["POST"])
def revise_grading_weights(
        request_key, policy, effective_from, reason,
        speaking, listening, writing, reading, grammar, vocabulary,
        continuous_percent):
    """Owner reviews seven numbers; all weighting changes become one version."""
    _owner()
    if not isinstance(policy, str) or not policy.strip():
        raise frappe.ValidationError("Choose an existing academic policy")
    record = frappe.db.get_value(
        "TH Assessment Policy", {"code": policy.strip()},
        ["family", "status"], as_dict=True)
    if not record or record.status != "Active":
        raise frappe.ValidationError("Choose an active graded assessment policy")
    family = frappe.db.get_value("TH Academic Program", record.family, "code")
    if family not in graded_template_family_codes():
        raise frappe.ValidationError(
            "Skill-weight form applies to graded templates only; specialist courses "
            "have their own progress-report rules")
    try:
        weights = numeric_skill_distribution(
            speaking, listening, writing, reading, grammar,
            vocabulary, continuous_percent)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    return academic.set_assessment_policy_version(
        request_key=request_key, policy=policy.strip(),
        effective_from=effective_from, reason=reason,
        skill_weights=weights)


@frappe.whitelist(methods=["GET"])
def owner_form_options():
    """Only safe academic/finance master names needed in nontechnical forms.

    A Course Owner may configure these through guarded commands without being
    granted broad native Education, Accounts or HRMS read/write permissions.
    Values are bounded, read-only and restricted to explicit allowlisted types.
    No student, staff private data, invoices or payment records are returned.
    """
    _owner()
    choices = (
        ("grading_scale", "Grading Scale", {"docstatus": 1}),
        ("program", "TH Academic Program", {"status": "Active"}),
        ("level", "TH Program Level", {"status": "Active"}),
        ("academic_year", "Academic Year", {}),
        ("fee_category", "Fee Category", {}),
        ("company", "Company", {}),
    )
    result = {}
    for key, doctype, filters in choices:
        rows = frappe.db.get_all(
            doctype, filters=filters, fields=["name"],
            order_by="name asc", limit_page_length=101)
        if len(rows) > 100:
            raise frappe.ValidationError(
                "Too many configuration choices to show safely; contact the "
                "authorized Course Owner to review the master catalog")
        names = []
        for row in rows:
            name = row.get("name") if isinstance(row, dict) else row.name
            if (not isinstance(name, str) or not name
                    or len(name) > 140 or "\n" in name or "\r" in name):
                raise frappe.ValidationError(
                    "An academic/finance option has an invalid name; "
                    "resolve the master record before editing settings")
            names.append(name)
        result[key] = names
    return result

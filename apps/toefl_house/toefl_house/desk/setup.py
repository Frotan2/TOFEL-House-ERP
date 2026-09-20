"""Academic Setup desk: the Owner's configuration control plane, as a surface.

Audience: Course Owner only (the same boundary as the guarded configuration
commands in toefl_house.academic). The projection is read-only; every mutation
it offers is a guided action into the guarded, idempotent configuration
commands — the desk adds context, never authority.

The hierarchy is presented the way the Owner thinks (§22 of the control-plane
mission): programs, then their ordered levels with the currently governing
duration version, then the actions that change them. Nothing here invents a
value: counts are counts, durations resolve from the version history, and an
integrity fault (a level without its native anchor) is surfaced, not hidden.
"""
import frappe

from toefl_house.academic import rules
from toefl_house.configuration import rules as configuration_rules
from toefl_house.desk import (
    DESKS,
    LIMIT_QUEUES,
    guided_action,
    issuable_plans,
    plan_with_components,
    project_count,
    project_rows,
    require_desk_audience,
    section,
)

SLUG = "th-academic-setup"

PROGRAM = "TH Academic Program"
LEVEL = "TH Program Level"
NATIVE_PROGRAM = "Program"
DURATION = "TH Level Duration"
ENROLLMENT = "Program Enrollment"
YEAR = "Academic Year"
FEE_CATEGORY = "Fee Category"
FEE_STRUCTURE = "Fee Structure"
FEE_ROW = "Fee Component"
DISCOUNT_RULE = "TH Discount Rule"
ASSESSMENT_POLICY = "TH Assessment Policy"
ASSESSMENT_VERSION = "TH Assessment Policy Version"
CONFIG_AUDIT = "TH Configuration Audit Event"

PROGRAM_FIELDS = ["name", "code", "title", "status", "modified"]
LEVEL_FIELDS = ["name", "family", "code", "title", "sequence", "status",
                "native_program", "next_level", "modified"]
DURATION_FIELDS = ["name", "parent", "parenttype", "duration_value", "duration_unit",
                   "effective_from", "superseded_on", "reason", "set_by"]
YEAR_FIELDS = ["name", "year_start_date", "year_end_date"]
FEE_TYPE_FIELDS = ["name", "category_name", "description", "item"]
FEE_PLAN_FIELDS = ["name", "program", "academic_year", "company",
                   "receivable_account", "docstatus", "total_amount"]
FEE_ROW_FIELDS = ["name", "parent", "parenttype", "fees_category", "amount", "idx"]
DISCOUNT_RULE_FIELDS = ["name", "code", "title", "discount_percentage", "precedence",
                        "status", "fee_category", "program", "description", "modified",
                        "modified_by"]
ASSESSMENT_POLICY_FIELDS = ["name", "family", "code", "title", "status",
                            "description", "modified"]
ASSESSMENT_FACET_FIELDS = ["components", "weights", "pass_rules", "rubrics",
                           "progression", "retakes", "level_mapping"]
ASSESSMENT_VERSION_FIELDS = ["name", "parent", "parenttype", "effective_from",
                             "grading_scale"] + ASSESSMENT_FACET_FIELDS + [
                                 "reason", "set_by", "set_on",
                                 "superseded_on"]


@frappe.whitelist(methods=["GET", "POST"])
def work():
    """Academic Setup payload: health, programs, levels, fees, setup actions."""
    require_desk_audience(SLUG)
    today = frappe.utils.today()

    programs = project_rows("setup", PROGRAM, PROGRAM_FIELDS,
                            order_by="title asc", limit=LIMIT_QUEUES)
    levels = project_rows("setup", LEVEL, LEVEL_FIELDS,
                          order_by="family asc, sequence asc", limit=LIMIT_QUEUES)
    versions = project_rows("setup", DURATION, DURATION_FIELDS,
                            filters={"parenttype": LEVEL},
                            order_by="effective_from asc", limit=LIMIT_QUEUES * 4)
    active_enrollments = project_rows("setup", ENROLLMENT,
                                      ["name", "program", "docstatus"],
                                      filters={"docstatus": 1}, limit=LIMIT_QUEUES * 4)
    years = project_rows("setup", YEAR, YEAR_FIELDS,
                         order_by="year_start_date asc", limit=LIMIT_QUEUES)
    fee_types = project_rows("setup", FEE_CATEGORY, FEE_TYPE_FIELDS,
                             order_by="category_name asc", limit=LIMIT_QUEUES)
    fee_plans = project_rows("setup", FEE_STRUCTURE, FEE_PLAN_FIELDS,
                             order_by="academic_year asc, name asc", limit=LIMIT_QUEUES)
    fee_rows = project_rows("setup", FEE_ROW, FEE_ROW_FIELDS,
                            filters={"parenttype": FEE_STRUCTURE},
                            order_by="idx asc", limit=LIMIT_QUEUES * 4)
    native_programs = project_rows("setup", NATIVE_PROGRAM,
                                   ["name", "program_name"],
                                   order_by="program_name asc", limit=LIMIT_QUEUES)
    discount_rules = project_rows("setup", DISCOUNT_RULE, DISCOUNT_RULE_FIELDS,
                                  order_by="precedence desc, code asc", limit=LIMIT_QUEUES)
    assessment_policies = project_rows("setup", ASSESSMENT_POLICY,
                                       ASSESSMENT_POLICY_FIELDS,
                                       order_by="code asc", limit=LIMIT_QUEUES)
    assessment_versions = project_rows("setup", ASSESSMENT_VERSION,
                                       ASSESSMENT_VERSION_FIELDS,
                                       filters={"parenttype": ASSESSMENT_POLICY},
                                       order_by="effective_from asc",
                                       limit=LIMIT_QUEUES * 4)

    versions_by_level = {}
    for row in versions:
        versions_by_level.setdefault(row.get("parent"), []).append(row)
    enrollments_by_program = {}
    for row in active_enrollments:
        if row.get("program"):
            enrollments_by_program.setdefault(row["program"], []).append(row)
    usage = {}
    for row in active_enrollments:
        if row.get("program"):
            usage[row["program"]] = usage.get(row["program"], 0) + 1
    levels_by_code = {row["code"]: row for row in levels}
    levels_by_native = {row["native_program"]: row
                        for row in levels if row.get("native_program")}
    family_titles = {row["name"]: row["title"] for row in programs}
    programs_by_name = {row["name"]: row for row in programs}

    # --- fee readiness ------------------------------------------------------
    rows_by_plan = {}
    for row in fee_rows:
        rows_by_plan.setdefault(row.get("parent"), []).append(row)
    plans_by_program = {}
    for plan in fee_plans:
        plans_by_program.setdefault((plan.get("program"),
                                     plan.get("academic_year") or ""),
                                    []).append(plan)
    current_year = _current_year(years, today)
    anchored_native = {row["native_program"] for row in levels
                       if row.get("native_program")}
    levels_without_plan = []
    for level in levels:
        if level["status"] != "Active" or not level.get("native_program"):
            continue
        if current_year and not plan_with_components(
                issuable_plans(plans_by_program, level["native_program"], current_year),
                rows_by_plan):
            levels_without_plan.append(level["code"])

    fee_plan_items = []
    for plan in fee_plans:
        level = levels_by_native.get(plan.get("program"))
        rows = rows_by_plan.get(plan["name"], [])
        total = sum(float(row.get("amount") or 0) for row in rows)
        detail = " · ".join(str(part) for part in (
            plan.get("academic_year"), plan.get("company") or "",
            f"{len(rows)} component(s)")) if rows else (
            plan.get("academic_year") or "")
        fee_plan_items.append({
            "id": plan["name"],
            "person": level["title"] if level else (plan.get("program") or ""),
            "detail": detail,
            "status": ("Editable plan" if int(plan.get("docstatus") or 0) == 0
                       else "Submitted (locked)"),
            "stage": "Fee plan",
            "stage_definition": "Fee Structure for the level's program and "
                                "academic year; issued Fees copy its components, so "
                                "posted documents never change with this policy.",
            "next": ("Components: " + ", ".join(
                f"{row.get('fees_category')} {float(row.get('amount') or 0):g}"
                for row in rows) + f". Sum {total:g}."
                + ("" if int(plan.get("docstatus") or 0) == 0
                   else " Submitted: the plan is locked against edits; "
                        "issuance still runs from it.")) if rows
            else "No components yet; the Finance command would refuse an empty plan.",
            "next_role": "Course Owner" if not rows else None,
            "waiting_since": None,
        })
        if level and level["status"] == "Active" and int(plan.get("docstatus") or 0) == 0:
            # Edit actions appear only on Draft plans: the Owner's edit
            # command manages the editable structure, so a button on a
            # submitted plan would silently open a second draft (refusal-
            # free by construction, per the setup desk's own rule).
            fee_plan_items[-1]["action"] = guided_action(
                "Course Owner", "toefl_house.academic.set_level_fee_component",
                "Set fee component",
                {"level": level["code"], "academic_year": plan.get("academic_year") or ""})
            if rows:
                fee_plan_items[-1]["actions"] = [row for row in [
                    guided_action(
                        "Course Owner", "toefl_house.academic.remove_level_fee_component",
                        "Remove component",
                        {"level": level["code"],
                         "academic_year": plan.get("academic_year") or ""})
                ] if row]

    fee_type_items = [{
        "id": row["name"],
        "person": row["category_name"],
        "detail": (row.get("description") or "") + (
            f" · item: {row['item']}" if row.get("item") else " · item pending"),
        "status": "Ready" if row.get("item") else "Item pending",
        "stage": "Fee type",
        "stage_definition": "Fee Category record; Education creates and "
                            "maintains its accounting Item automatically.",
        "next": "No action." if row.get("item") else \
            "The accounting Item has not been created yet; open the Fee "
            "Category in Education to fix it.",
        "next_role": None,
        "waiting_since": None,
    } for row in fee_types]

    program_rows_view = []
    for program in programs:
        family_levels = [row for row in levels if row.get("family") == program["name"]]
        item = {
            "id": program["code"],
            "person": program["title"],
            "detail": f"{len(family_levels)} level(s)",
            "status": program["status"],
            "stage": "Program",
            "stage_definition": "Owner-defined program family; its levels are "
                               "Program records consumed by enrollment, fees and classes.",
            "next": "Define the first level." if not family_levels else "No action.",
            "next_role": "Course Owner" if not family_levels else None,
            "waiting_since": program.get("modified"),
        }
        row_actions = []
        active_family_levels = sum(
            1 for row in family_levels if row["status"] == "Active")
        if program["status"] == "Active":
            item["action"] = guided_action(
                "Course Owner", "toefl_house.academic.create_level",
                "Define level", {"family": program["code"]})
            if active_family_levels == 0:
                # The server rule allows retiring only with no active levels;
                # the button appears exactly when it can succeed.
                row_actions.append(guided_action(
                    "Course Owner", "toefl_house.academic.set_program_status",
                    "Retire program", {"program": program["code"], "active": "0"}))
        else:
            row_actions.append(guided_action(
                "Course Owner", "toefl_house.academic.set_program_status",
                "Reactivate program", {"program": program["code"], "active": "1"}))
        extras = [row for row in row_actions if row]
        if extras:
            item["actions"] = extras
        program_rows_view.append(item)

    level_rows_view = []
    missing_native = 0
    missing_duration = 0
    in_use_levels = 0
    progression_links = 0
    for level in levels:
        versions_for = versions_by_level.get(level["name"], [])
        governing = rules.resolve_duration(versions_for, today)
        label = rules.duration_label(governing)
        if not level.get("native_program"):
            missing_native += 1
        if not governing:
            missing_duration += 1
        if usage.get(level.get("native_program")):
            in_use_levels += 1
        if level.get("next_level"):
            progression_links += 1
        next_bits = []
        if label:
            next_bits.append(f"Duration {label} from {governing.get('effective_from')}.")
            actor = governing.get("set_by") or ""
            reason = governing.get("reason") or ""
            if actor or reason:
                next_bits.append("Set " + " ".join(part for part in (
                    f"by {actor}." if actor else "",
                    f"Reason: {reason}." if reason else "") if part))
        else:
            next_bits.append("No duration version is effective yet.")
        if level.get("next_level"):
            target = levels_by_code.get(level["next_level"]) or {}
            next_bits.append(f"Progression: {target.get('title') or level['next_level']}.")
        else:
            next_bits.append("No next level configured.")
        if level["status"] == "Active":
            if not current_year:
                next_bits.append("Billing readiness unknown: no academic year is defined yet.")
            else:
                complete = plan_with_components(
                    issuable_plans(plans_by_program, level.get("native_program"),
                                   current_year),
                    rows_by_plan)
                if complete and all(int(plan.get("docstatus") or 0) == 0
                                    for plan in complete):
                    next_bits.append(f"Fee plan ready for {current_year}.")
                elif complete:
                    next_bits.append(f"Fee plan ready for {current_year} "
                                     "(submitted and locked; issuance works).")
                else:
                    next_bits.append(f"No complete fee plan for {current_year} yet.")
        # §17 made visible: which duration version governed each live
        # enrollment. History stays whole; only the answer is computed.
        history = ""
        if level.get("native_program"):
            dates = [enrollment.get("enrollment_date") for enrollment
                     in enrollments_by_program.get(level["native_program"], [])
                     if enrollment.get("enrollment_date")]
            counts = rules.duration_history_counts(versions_for, dates)
            if counts:
                history = " History: " + ", ".join(
                    f"{count} enrolled under {label}" for label, count in counts.items()) + "."
        item = {
            "id": level["code"],
            "person": level["title"],
            "detail": " · ".join(part for part in (
                family_titles.get(level.get("family")) or "",
                f"Level {level.get('sequence')}",
                f"native: {level.get('native_program')}" if level.get("native_program") else "",
            ) if part),
            "status": level["status"],
            "stage": f"Level {level.get('sequence')}",
            "stage_definition": "Ordered level of its program family; the duration is "
                                "the governing effective-dated version, not a hard-coded value.",
            "next": " ".join(next_bits) + history,
            "next_role": "Course Owner",
            "waiting_since": level.get("modified"),
        }
        row_actions = []
        if level["status"] == "Active":
            prefill = {"level": level["code"], "effective_from": ""}
            if governing:
                prefill["duration_value"] = governing.get("duration_value")
                prefill["duration_unit"] = governing.get("duration_unit")
            item["action"] = guided_action(
                "Course Owner", "toefl_house.academic.set_level_duration",
                "Set duration", prefill)
            row_actions.append(guided_action(
                "Course Owner", "toefl_house.academic.set_next_level",
                "Set progression", {"level": level["code"], "next_level": ""}))
            if not usage.get(level.get("native_program")):
                # Refusal-free by construction: retire appears only when no
                # submitted enrollment runs on the level.
                row_actions.append(guided_action(
                    "Course Owner", "toefl_house.academic.set_level_status",
                    "Retire level", {"level": level["code"], "active": "0"}))
        else:
            family_status = (programs_by_name.get(level.get("family")) or {}).get("status")
            if family_status == "Active":
                row_actions.append(guided_action(
                    "Course Owner", "toefl_house.academic.set_level_status",
                    "Reactivate level", {"level": level["code"], "active": "1"}))
        extras = [row for row in row_actions if row]
        if extras:
            item["actions"] = extras
        level_rows_view.append(item)

    progression_facts = []
    for program in programs:
        family_levels = sorted(
            (row for row in levels if row.get("family") == program["name"]),
            key=lambda row: int(row.get("sequence") or 0))
        if not family_levels:
            continue
        titles = [row["title"] for row in family_levels]
        issues = []
        for index, row in enumerate(family_levels):
            successor = (family_levels[index + 1]["code"]
                         if index + 1 < len(family_levels) else None)
            points_to = row.get("next_level")
            if successor and points_to != successor:
                if points_to:
                    issues.append(
                        f"{row['title']} progresses to "
                        f"{levels_by_code.get(points_to, {}).get('title', points_to)}, "
                        f"not to the next position ({family_levels[index + 1]['title']})")
                else:
                    issues.append(f"{row['title']} has no progression configured")
            elif not successor and points_to:
                issues.append(
                    f"{row['title']} (last position) also points onward to "
                    f"{levels_by_code.get(points_to, {}).get('title', points_to)}")
        chain = " → ".join(titles)
        if issues:
            chain += " — " + "; ".join(issues)
        progression_facts.append({
            "label": program["title"],
            "definition": "Configured progression in level order; mismatches "
                          "between the order and the configured next level are named.",
            "value": chain, "owner": "Course Owner",
        })

    health = [
        {"label": "Active programs",
         "definition": "TH Academic Program rows in Active status.",
         "value": sum(1 for row in programs if row["status"] == "Active"),
         "owner": "Course Owner"},
        {"label": "Active levels",
         "definition": "TH Program Level rows in Active status.",
         "value": sum(1 for row in levels if row["status"] == "Active"),
         "owner": "Course Owner"},
        {"label": "Levels without an effective duration",
         "definition": "Active levels whose duration versions contain no version "
                       "effective today; new enrollments cannot state their duration.",
         "value": missing_duration, "owner": "Course Owner"},
        {"label": "Levels missing their Program link",
         "definition": "Levels whose Program link is absent — a "
                       "configuration integrity fault, since enrollment, fees "
                       "and classes reach a level through it.",
         "value": missing_native, "owner": "Course Owner"},
        {"label": "Levels in active use",
         "definition": "Levels whose Program carries at least one "
                       "submitted enrollment; deactivation is refused for these.",
         "value": in_use_levels, "owner": "Course Owner"},
        {"label": "Progression links configured",
         "definition": "Levels whose next level is configured.",
         "value": progression_links, "owner": "Course Owner"},
        {"label": "Fee types defined",
         "definition": "Fee Category records (each carries its own "
                       "accounting Item).",
         "value": len(fee_types), "owner": "Course Owner"},
        {"label": "Active levels without a usable fee plan",
         "definition": f"Active levels whose {current_year or 'any defined academic year'} "
                       "has no non-cancelled fee plan carrying components; issuance "
                       "refuses an empty plan, submitted or draft.",
         "value": len(levels_without_plan), "owner": "Course Owner"},
        {"label": "Programs not claimed by any configured level",
         "definition": "Education Program records no configured level "
                       "uses. Enrollment against them bypasses the Owner's "
                       "structure; adopt them as levels or retire them "
                       "deliberately.",
         "value": sum(1 for row in native_programs
                      if row["name"] not in anchored_native),
         "owner": "Course Owner"},
        {"label": "Active discount rules",
         "definition": "Discount rules (TH Discount Rule) in Active status, per Policy A.",
         "value": sum(1 for row in discount_rules if row.get("status") == "Active"),
         "owner": "Course Owner"},
    ]

    year_items = []
    for year in years:
        start = str(year.get("year_start_date") or "")
        end = str(year.get("year_end_date") or "")
        if current_year and year["name"] == current_year:
            marker = "Current"
        elif end and end < str(today):
            marker = "Past"
        elif start and start > str(today):
            marker = "Upcoming"
        else:
            marker = "Defined"
        covered = []
        missing = []
        for level in levels:
            if level["status"] != "Active" or not level.get("native_program"):
                continue
            if plan_with_components(
                    issuable_plans(plans_by_program, level["native_program"],
                                   year["name"]),
                    rows_by_plan):
                covered.append(level["code"])
            else:
                missing.append(level["code"])
        year_items.append({
            "id": year["name"],
            "person": year["name"],
            "detail": f"{start or '?'} to {end or '?'}",
            "status": marker,
            "stage": "Academic year",
            "stage_definition": ("An academic year enrollments, classes and fee "
                               "plans key on. Coverage counts complete fee plans "
                               "for this year across active levels."),
            "next": (f"{len(covered)} complete fee plan(s). "
                     + (f"Missing a plan: {', '.join(missing)}." if missing
                        else "Every active level has a plan."))
            if covered or missing else "No active levels to cover yet.",
            "next_role": "Course Owner" if missing else None,
            "waiting_since": None,
        })

    discount_rule_items = []
    for rule in discount_rules:
        active = rule.get("status") == "Active"
        scope_bits = []
        if rule.get("fee_category"):
            scope_bits.append(f"Fee: {rule['fee_category']}")
        if rule.get("program"):
            scope_bits.append(f"Program: {rule['program']}")
        scope_label = " · ".join(scope_bits) if scope_bits else "Institution-wide"
        changed_by = rule.get("modified_by") or ""
        item = {
            "id": rule["code"],
            "person": rule.get("title") or rule["code"],
            "detail": f"{rule.get('discount_percentage')}% discount · Precedence: {rule.get('precedence')} · Scope: {scope_label}"
                      + (f" · Last changed by {changed_by}" if changed_by else ""),
            "status": rule.get("status", "Active"),
            "stage": "Policy A (Single Discount)",
            "stage_definition": "Central discount rule catalog. Zero or one discount per charge; higher precedence resolves competing rules; never stacks.",
            "next": "Retire this rule when it should no longer apply to new charges." if active
                    else "Reactivate this rule to make it eligible for new charges.",
            "next_role": "Course Owner",
            "waiting_since": rule.get("modified"),
        }
        if active:
            item["action"] = guided_action(
                "Course Owner", "toefl_house.academic.set_discount_rule_status",
                "Retire discount rule", {"code": rule["code"], "active": 0})
        else:
            item["action"] = guided_action(
                "Course Owner", "toefl_house.academic.set_discount_rule_status",
                "Reactivate discount rule", {"code": rule["code"], "active": 1})
        discount_rule_items.append(item)

    setup_actions = [{
        "id": "new-program",
        "person": "Define a new program family",
        "detail": "The family orders and governs its levels; it is not "
                  "itself an enrollment Program.",
        "status": "Ready",
        "stage": "Setup",
        "stage_definition": "Configuration actions open the same guarded, "
                            "idempotent commands the rest of the product uses.",
        "next": "Create the program family, then define its levels in order.",
        "next_role": "Course Owner",
        "waiting_since": None,
        "action": guided_action("Course Owner", "toefl_house.academic.create_program",
                                "Define program", {}),
    }, {
        "id": "new-academic-year",
        "person": "Define an academic year",
        "detail": "An Academic Year record; fees, enrollments and classes key on it.",
        "status": "Ready",
        "stage": "Setup",
        "stage_definition": "Education needs Academic Year records; "
                            "nothing else in the product creates them.",
        "next": "Create the year with its start and end dates before fee plans.",
        "next_role": "Course Owner",
        "waiting_since": None,
        "action": guided_action("Course Owner", "toefl_house.academic.create_academic_year",
                                "Define academic year", {}),
    }, {
        "id": "new-fee-type",
        "person": "Define a fee type",
        "detail": "A Fee Category record; Education creates its accounting Item.",
        "status": "Ready",
        "stage": "Setup",
        "stage_definition": "Fee types are Owner configuration, never hard-coded: "
                            "the Owner can add a new charge without a developer.",
        "next": "Name the charge; use it later inside a level's fee plan.",
        "next_role": "Course Owner",
        "waiting_since": None,
        "action": guided_action("Course Owner", "toefl_house.academic.create_fee_type",
                                "Define fee type", {}),
    }, {
        "id": "new-discount-rule",
        "person": "Define a discount rule (Policy A)",
        "detail": "Centralized discount with explicit precedence. Zero or one discount per charge line; never stacks.",
        "status": "Ready",
        "stage": "Setup",
        "stage_definition": "OD-CP-1 Policy A: central discount rule catalog consumed across all modules.",
        "next": "Configure rule code, title, discount percentage, and precedence.",
        "next_role": "Course Owner",
        "waiting_since": None,
        "action": guided_action("Course Owner", "toefl_house.academic.create_discount_rule",
                                "Define discount rule", {}),
    }]

    return {
        "desk": SLUG,
        "title": DESKS[SLUG]["title"],
        "sections": [
            section("health", "Configuration health", "facts", facts=health,
                    empty_title="No configuration yet",
                    empty_body="Define the first program family below; the desks, "
                               "admission and enrollment consume it from there."),
            section("setup", "Setup actions", "queue", items=setup_actions,
                    empty_title="No setup actions",
                    empty_body="Program creation appears here."),
            section("programs", "Programs", "queue", items=program_rows_view,
                    empty_title="No programs yet",
                    empty_body="Use Setup actions to define the first program family."),
            section("levels", "Levels", "queue", items=level_rows_view,
                    empty_title="No levels yet",
                    empty_body="Define levels inside a program; each becomes a native "
                               "Program that enrollment and fees consume."),
            section("progression", "Progression chains", "facts", facts=progression_facts,
                    empty_title="No levels to chain yet",
                    empty_body="Define levels in order; the chain and any "
                               "progression mismatches appear here."),
            section("fees", "Fee plans (per level and academic year)", "queue",
                    items=fee_plan_items,
                    empty_title="No fee plans yet",
                    empty_body="Define an academic year and fee types, then set the "
                               "components per level; the Finance issuance command "
                               "consumes exactly this configuration."),
            section("fee-types", "Fee types", "queue", items=fee_type_items,
                    empty_title="No fee types yet",
                    empty_body="Tuition, identity card, diploma, retake examination — "
                               "any charge the institution invents later is defined "
                               "here, never in code."),
            section("discounts", "Discount rules (Policy A)", "queue", items=discount_rule_items,
                    empty_title="No discount rules yet",
                    empty_body="Define scholarship or discount rules under Policy A; "
                               "charges receive at most one discount according to configured precedence."),
            section("years", "Academic years", "queue", items=year_items,
                    empty_title="No academic years yet",
                    empty_body="Define the first academic year from Setup actions; "
                               "fee plans, enrollments and classes key on it."),
            section("grading", "Grading (owner decision D1)", "queue",
                    items=_grading_items(assessment_policies,
                                         assessment_versions, today),
                    empty_title="Grading is undecided",
                    empty_body="Owner decision D1 has not been made."),
        ],
    }


def _current_year(years, today):
    """The academic year whose date range contains today, else the latest by
    start date. A fact used for the readiness label — no policy inference."""
    if not years:
        return None
    for row in years:
        start = str(row.get("year_start_date") or "")
        end = str(row.get("year_end_date") or "")
        if start and end and start <= str(today) <= end:
            return row["name"]
    return years[-1]["name"]


def _current_validation(policy_name, snapshot):
    """Whether a validation event commits to this exact version snapshot.

    Matched by count, never projected: the hash stays in the filter, so no
    hash field ever enters a desk projection (read-boundary discipline).
    One bounded count per policy; policies are few by nature.
    """
    return project_count("setup", CONFIG_AUDIT, filters={
        "target": policy_name, "action": "validate_assessment_policy",
        "after_hash": snapshot,
    }) > 0


def _grading_items(policies, versions, today):
    """Assessment policies with computed readiness (D1 reference structure).

    With no policies this is the explicit owner placeholder: D1 undecided,
    nothing computes grades — plus the one action that can succeed (define
    the first policy shell). With policies, each item states its computed
    readiness and offers exactly the actions the server rule allows.
    """
    if not policies:
        return [{
            "id": "grading-policy",
            "person": "Grading policy",
            "detail": "No grading rules are configured.",
            "status": "Not decided",
            "stage": "Grading",
            "stage_definition": ("Grade scales, cutoffs and result "
                               "computation are owner decision D1, which "
                               "has not been made. Nothing in the product "
                               "computes or interprets grades."),
            "next": ("The Course Owner decides the grading policy; until "
                     "then desks show recorded scores only."),
            "next_role": "Course Owner",
            "waiting_since": None,
            "action": guided_action(
                "Course Owner",
                "toefl_house.academic.create_assessment_policy",
                "Define assessment policy", {}),
        }]
    versions_by_policy = {}
    for row in versions:
        versions_by_policy.setdefault(row.get("parent"), []).append(row)
    items = []
    for policy in policies:
        rows = versions_by_policy.get(policy["name"], [])
        snapshot = configuration_rules.snapshot_digest(rows)
        evidence = ([{"after_hash": snapshot}]
                    if rows and _current_validation(policy["name"], snapshot)
                    else [])
        try:
            readiness = configuration_rules.compute_readiness(
                status=policy.get("status"), versions=rows,
                validations=evidence, today=today,
                what="assessment policy")
        except ValueError as exc:
            items.append({
                "id": policy["code"],
                "person": policy["title"],
                "detail": str(exc),
                "status": "Integrity fault",
                "stage": "Assessment policy",
                "stage_definition": ("The version history contradicts "
                                     "itself, so no readiness state can be "
                                     "computed and nothing resolves "
                                     "against it."),
                "next": ("Ask the administrator to repair the version "
                         "history; no action is offered until then."),
                "next_role": "Course Owner",
                "waiting_since": None,
            })
            continue
        governing = configuration_rules.resolve_governing(rows, today)
        if governing:
            detail = (f"{len(rows)} version(s); governing since "
                      f"{governing.get('effective_from')}")
            defined = [facet.replace("_", " ") for facet in
                       ASSESSMENT_FACET_FIELDS if governing.get(facet)]
            detail += ("; facets defined: " + ", ".join(defined)
                       if defined else "; no facets defined yet")
        elif rows:
            detail = f"{len(rows)} version(s); nothing effective yet"
        else:
            detail = "No versions yet"
        item = {
            "id": policy["code"],
            "person": policy["title"],
            "detail": detail,
            "status": readiness.capitalize(),
            "stage": "Assessment policy",
            "stage_definition": ("Computed configuration readiness. "
                                 "Versions carry the grading-scale link and "
                                 "the owned facet structures; each facet "
                                 "stays empty until the Course Owner "
                                 "defines it."),
            "next": _assessment_next(policy, readiness, governing),
            "next_role": "Course Owner",
            "waiting_since": None,
        }
        actions = _assessment_actions(policy, readiness)
        if actions:
            item["action"] = actions[0]
            if len(actions) > 1:
                item["actions"] = actions[1:]
        items.append(item)
    return items


def _assessment_next(policy, readiness, governing):
    code = policy["code"]
    if readiness == "incomplete":
        return (f"Add the first version of {code}; the policy governs "
                "nothing until then.")
    if readiness == "configured":
        return (f"Validate {code}; versions exist but no validation covers "
                "the current set.")
    if readiness == "validated":
        return f"{code} is validated and takes effect on its first version date."
    if readiness == "effective":
        since = governing.get("effective_from") if governing else ""
        return f"{code} governs since {since}."
    return f"{code} is retired; it governs nothing."


FACET_ACTIONS = (
    ("toefl_house.academic.set_assessment_components", "Set components"),
    ("toefl_house.academic.set_assessment_weights", "Set weights"),
    ("toefl_house.academic.set_assessment_pass_rules", "Set pass rules"),
    ("toefl_house.academic.set_assessment_rubrics", "Set rubrics"),
    ("toefl_house.academic.set_assessment_progression", "Set progression"),
    ("toefl_house.academic.set_assessment_retakes", "Set retakes"),
    ("toefl_house.academic.set_assessment_mapping", "Set level mapping"),
)


def _assessment_actions(policy, readiness):
    """Exactly the version/facet/status/validate actions the server allows.

    Facet commands append versions under the same server rules as the
    carrier version command (active policy and family, monotone dates),
    so they are offered everywhere the version action is.
    """
    code = policy["code"]
    retired = readiness == "retired"
    if retired:
        primary = guided_action(
            "Course Owner", "toefl_house.academic.set_assessment_policy_status",
            "Reactivate policy", {"policy": code, "active": "1"})
        return [primary] if primary else []
    version_action = guided_action(
        "Course Owner", "toefl_house.academic.set_assessment_policy_version",
        "Add version", {"policy": code})
    facet_actions = [guided_action("Course Owner", endpoint, label,
                                   {"policy": code})
                     for endpoint, label in FACET_ACTIONS]
    retire_action = guided_action(
        "Course Owner", "toefl_house.academic.set_assessment_policy_status",
        "Retire policy", {"policy": code, "active": "0"})
    if readiness == "incomplete":
        ordered = [version_action] + facet_actions + [retire_action]
    elif readiness == "configured":
        validate_action = guided_action(
            "Course Owner", "toefl_house.academic.validate_assessment_policy",
            "Validate policy", {"policy": code})
        ordered = ([validate_action, version_action] + facet_actions
                   + [retire_action])
    else:
        ordered = [version_action] + facet_actions + [retire_action]
    return [action for action in ordered if action]

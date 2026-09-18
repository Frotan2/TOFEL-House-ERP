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
from toefl_house.desk import (
    DESKS,
    LIMIT_QUEUES,
    guided_action,
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
                        "status", "fee_category", "program", "description", "modified"]


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
        plans_by_program.setdefault((plan.get("program"), plan.get("academic_year")),
                                    []).append(plan)
    current_year = _current_year(years, today)
    anchored_native = {row["native_program"] for row in levels
                       if row.get("native_program")}
    levels_without_plan = []
    for level in levels:
        if level["status"] != "Active" or not level.get("native_program"):
            continue
        if current_year and not plans_by_program.get(
                (level["native_program"], current_year)):
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
            "status": "Editable plan" if int(plan.get("docstatus") or 0) == 0 else "Submitted",
            "stage": "Fee plan",
            "stage_definition": "Native Fee Structure for the level's anchored program "
                                "and academic year; issued Fees copy their components, "
                                "so posted documents never change with this policy.",
            "next": ("Components: " + ", ".join(
                f"{row.get('fees_category')} {float(row.get('amount') or 0):g}"
                for row in rows) + f". Sum {total:g}.") if rows
            else "No components yet; the Finance command would refuse an empty plan.",
            "next_role": "Course Owner" if not rows else None,
            "waiting_since": None,
        })
        if level and level["status"] == "Active":
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
        "stage_definition": "Native Fee Category; Education creates and maintains "
                            "its accounting Item automatically.",
        "next": "No action." if row.get("item") else \
            "The accounting Item has not been created yet; open the category natively.",
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
            "stage_definition": "Owner-defined program family; its levels are native "
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
                plan_rows_for = [
                    plan for plan in plans_by_program.get(
                        (level.get("native_program"), current_year), [])
                    if int(plan.get("docstatus") or 0) == 0]
                ready = any(rows_by_plan.get(plan["name"]) for plan in plan_rows_for)
                next_bits.append(
                    f"Fee plan ready for {current_year}." if ready else
                    f"No complete fee plan for {current_year} yet.")
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
        {"label": "Levels missing their native anchor",
         "definition": "Levels whose native Program link is absent. This is a "
                       "configuration integrity fault: enrollment, fees and classes "
                       "consume levels through that native link.",
         "value": missing_native, "owner": "Course Owner"},
        {"label": "Levels in active use",
         "definition": "Levels whose native program carries at least one submitted "
                       "Program Enrollment; deactivation is refused for these.",
         "value": in_use_levels, "owner": "Course Owner"},
        {"label": "Progression links configured",
         "definition": "Levels whose next level is configured.",
         "value": progression_links, "owner": "Course Owner"},
        {"label": "Fee types defined",
         "definition": "Native Fee Category records (each carries its own "
                       "accounting Item).",
         "value": len(fee_types), "owner": "Course Owner"},
        {"label": "Active levels without a fee plan",
         "definition": f"Active levels with no editable native Fee Structure for "
                       f"{current_year or 'any defined academic year'}; enrollment "
                       "of such a level cannot be billed yet.",
         "value": len(levels_without_plan), "owner": "Course Owner"},
        {"label": "Native programs outside the control plane",
         "definition": "Native Education Program records no configured level "
                       "anchors. Enrollment against them bypasses the Owner's "
                       "structure; adopt them as levels or retire them deliberately.",
         "value": sum(1 for row in native_programs
                      if row["name"] not in anchored_native),
         "owner": "Course Owner"},
        {"label": "Active discount rules",
         "definition": "TH Discount Rule rows in Active status under Policy A.",
         "value": sum(1 for row in discount_rules if row.get("status") == "Active"),
         "owner": "Course Owner"},
    ]

    discount_rule_items = []
    for rule in discount_rules:
        active = rule.get("status") == "Active"
        scope_bits = []
        if rule.get("fee_category"):
            scope_bits.append(f"Fee: {rule['fee_category']}")
        if rule.get("program"):
            scope_bits.append(f"Program: {rule['program']}")
        scope_label = " · ".join(scope_bits) if scope_bits else "Institution-wide"
        item = {
            "id": rule["code"],
            "person": rule.get("title") or rule["code"],
            "detail": f"{rule.get('discount_percentage')}% discount · Precedence: {rule.get('precedence')} · Scope: {scope_label}",
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
        "detail": "The family orders and governs its levels; it is not a native "
                  "Program itself.",
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
        "detail": "Native Academic Year; fees, enrollments and classes key on it.",
        "status": "Ready",
        "stage": "Setup",
        "stage_definition": "Native Education requires Academic Year records; "
                            "nothing else in the product creates them.",
        "next": "Create the year with its start and end dates before fee plans.",
        "next_role": "Course Owner",
        "waiting_since": None,
        "action": guided_action("Course Owner", "toefl_house.academic.create_academic_year",
                                "Define academic year", {}),
    }, {
        "id": "new-fee-type",
        "person": "Define a fee type",
        "detail": "Native Fee Category; Education creates its accounting Item.",
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

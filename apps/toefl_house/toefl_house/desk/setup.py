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
DURATION = "TH Level Duration"
ENROLLMENT = "Program Enrollment"

PROGRAM_FIELDS = ["name", "code", "title", "status", "modified"]
LEVEL_FIELDS = ["name", "family", "code", "title", "sequence", "status",
                "native_program", "next_level", "modified"]
DURATION_FIELDS = ["name", "parent", "parenttype", "duration_value", "duration_unit",
                   "effective_from", "superseded_on", "reason", "set_by"]


def work():
    """Academic Setup payload: health, programs, levels, setup actions."""
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

    versions_by_level = {}
    for row in versions:
        versions_by_level.setdefault(row.get("parent"), []).append(row)
    usage = {}
    for row in active_enrollments:
        if row.get("program"):
            usage[row["program"]] = usage.get(row["program"], 0) + 1
    levels_by_name = {row["name"]: row for row in levels}
    family_titles = {row["name"]: row["title"] for row in programs}

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
        if program["status"] == "Active":
            item["action"] = guided_action(
                "Course Owner", "toefl_house.academic.create_level",
                "Define level", {"family": program["code"]})
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
            target = levels_by_name.get(level["next_level"]) or {}
            next_bits.append(f"Progression: {target.get('title') or level['next_level']}.")
        else:
            next_bits.append("No next level configured.")
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
            "next": " ".join(next_bits),
            "next_role": "Course Owner",
            "waiting_since": level.get("modified"),
        }
        if level["status"] == "Active":
            prefill = {"level": level["code"], "effective_from": ""}
            if governing:
                prefill["duration_value"] = governing.get("duration_value")
                prefill["duration_unit"] = governing.get("duration_unit")
            item["action"] = guided_action(
                "Course Owner", "toefl_house.academic.set_level_duration",
                "Set duration", prefill)
        level_rows_view.append(item)

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
    ]

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
        ],
    }

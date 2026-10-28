"""Build native-compatible *proposed* assessment policy facets from the preset.

No policy versions, grades, students or native Grading Scale are written here.
The Course Owner must confirm these values in a versioned, audited UI flow.
"""
from __future__ import annotations

from toefl_house.setup_presets.preset import load_preset


CODES = {
    "speaking": "SPK", "listening": "LST", "writing": "WRT",
    "reading": "RDG", "grammar": "GRM", "vocabulary": "VOC",
}


def _rubrics(components: list) -> list:
    allowed = {component["code"] for component in components}
    result = []
    evidence = {
        "SPK": [
            "Task completion and relevance",
            "Fluency and coherence",
            "Pronunciation and intelligibility",
            "Vocabulary and grammatical accuracy",
        ],
        "WRT": [
            "Task achievement",
            "Organization and coherence",
            "Vocabulary and grammatical accuracy",
            "Appropriate revision and clarity",
        ],
    }
    for prefix in ("SPK", "WRT"):
        for suffix, title in (("CA", "Continuous"), ("FINAL", "Final")):
            code = f"{prefix}-{suffix}"
            if code not in allowed:
                continue
            result.append({
                "code": f"{code}-RUBRIC",
                "title": ("Speaking" if prefix == "SPK" else "Writing") + " - " + title,
                "component": code,
                "evidence": evidence[prefix],
                "levels": [
                    {"code": "EXCELLENT", "title": "Excellent",
                     "description": "Completes level-appropriate tasks consistently and independently."},
                    {"code": "GOOD", "title": "Good",
                     "description": "Completes most tasks with minor difficulties."},
                    {"code": "DEVELOPING", "title": "Developing",
                     "description": "Completes some tasks with noticeable support."},
                    {"code": "NEEDS-SUPPORT", "title": "Needs Support",
                     "description": "Cannot consistently complete required tasks without substantial support."},
                ],
            })
    return result


def build_assessment_facets(family: str, preset: dict | None = None) -> dict:
    """Return seven valid facet objects; never post or auto-approve them.

    CA/Final sums of 40/60 and full skill proportions are exact. Continuous
    attendance/participation/assignment/quiz evidence is *not* automatically
    aggregated by existing assessment commands; that remains a release gate.
    """
    preset = preset or load_preset()
    program = next((p for p in preset["programs"] if p["code"] == family), None)
    if not program:
        raise ValueError(f"Unknown program family {family}")
    skills = dict(program["assessment_skill_weights_percent"])
    components, weights = [], []
    for skill, share in skills.items():
        label = skill.title()
        prefix = CODES[skill]
        for suffix, phase, percentage in (
                ("CA", "Continuous", 40), ("FINAL", "Final", 60)):
            code = f"{prefix}-{suffix}"
            components.append({
                "code": code, "title": f"{label} - {phase}",
                "maximum_score": 100,
            })
            weights.append({
                "component": code, "weight": share * percentage / 100,
            })
    return {
        "components": components,
        "weights": weights,
        "pass_rules": {
            "components": [],
            "overall": {"kind": "percent",
                        "value": preset["assessment"]["overall_pass_percent"]},
        },
        "rubrics": _rubrics(components),
        "progression": {
            "target": "next",
            "requires": [
                {"kind": "assessment_pass", "policy": program["assessment_policy_code"]},
                {"kind": "approval", "role": "Academic Manager"},
            ],
        },
        "retakes": {
            "max_attempts": preset["assessment"]["retake"]["max_total_attempts"],
            "wait_days": preset["assessment"]["retake"]["wait_days"],
            "scope": preset["assessment"]["retake"]["scope"],
            "governing": preset["assessment"]["retake"]["governing"],
        },
        "level_mapping": {"levels": [level["code"] for level in program["levels"]]},
    }

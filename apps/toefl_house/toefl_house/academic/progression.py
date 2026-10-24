"""Controlled progression: eligibility, decisions and next-level enrollment.

Progression is the academic step after a published result. Three rules make
it governed rather than automatic:

1. **A valid, configured policy is required.** The pinned policy version's
   ``progression`` facet names the evidence required (assessment pass,
   attendance, human approval) and the target level. No facet, or a facet
   that names no approval, fails closed — this module invents no threshold.
2. **Authorized academic approval is required.** The deciding actor must
   hold the structural progression role *and* the approval role the policy
   itself configures, and one result carries exactly one approved decision.
3. **An override is a separate, senior, reasoned act.** It never rewrites
   eligibility: it records ``override_used`` together with the unmet
   requirements that were overridden.

A progression decision never enrolls by itself. The native ``Program
Enrollment`` is still created by the enrollment command; what changes is
that it now asks this module first (``enrollment_gate``) whenever the
student is moving from a predecessor level into a successor level whose
catalog link and policy are configured.
"""
import frappe

from toefl_house.academic import assessment, grading
from toefl_house.api import _execute
from toefl_house.policy import canonical, digest
from toefl_house.security import record_synthetic_flag, require_operational

DECISION = "TH Progression Decision"
RESULT = "TH Academic Result"
LEVEL = "TH Program Level"
POLICY = "TH Assessment Policy"
PROGRAM_ENROLLMENT = "Program Enrollment"
DECISIONS = ("Promote", "Repeat", "Retake", "Complete")


def _text(value, what, maximum=140):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise frappe.ValidationError(f"{what} is required (at most {maximum} characters)")
    return value.strip()


def _reason(value, what, maximum=300):
    if not isinstance(value, str) or not value.strip():
        raise frappe.ValidationError(f"{what} is required")
    text = value.strip()
    if len(text) > maximum:
        raise frappe.ValidationError(f"{what} must be at most {maximum} characters")
    return text


def _published_result(name):
    if not frappe.db.exists(RESULT, name):
        raise frappe.ValidationError("Unknown academic result")
    row = frappe.db.get_value(
        RESULT, name,
        ["name", "student", "student_group", "level", "book", "attempt",
         "status", "outcome", "policy", "policy_effective_from",
         "attendance_percent", "overall_percent", "grade_code"],
        as_dict=True)
    if row.status != "Published":
        raise frappe.ValidationError(
            f"Result {name} is {row.status}; progression is decided on the "
            "current published result only")
    return row


def _pinned_facets(result_row):
    policy_code = frappe.db.get_value(POLICY, result_row.policy, "code")
    _doc, version = assessment.pinned_version(policy_code,
                                              result_row.policy_effective_from)
    return assessment.version_facets(version)


def _level_of(row):
    """The program level a result or class belongs to (never guessed)."""
    if row.level:
        level = frappe.db.get_value(LEVEL, row.level,
                                    ["name", "code", "next_level", "native_program"],
                                    as_dict=True)
        if level:
            return level
    program = frappe.db.get_value("Student Group", row.student_group, "program")
    level = frappe.db.get_value(LEVEL, {"native_program": program},
                                ["name", "code", "next_level", "native_program"],
                                as_dict=True)
    if not level:
        raise frappe.ValidationError(
            "This class is not mapped to a program level; progression cannot "
            "be decided without one (Academic Setup)")
    return level


def _target_level(level, progression):
    """The level a promote/complete decision points at, from the catalog."""
    target = (progression or {}).get("target")
    if not target:
        raise frappe.ValidationError(
            "The pinned policy version names no progression target")
    if target == rules_next():
        if not level.next_level:
            return None
        next_row = frappe.db.get_value(LEVEL, {"code": level.next_level},
                                       ["name", "code", "next_level", "native_program"],
                                       as_dict=True)
        if not next_row:
            raise frappe.ValidationError(
                f"The catalog's next level {level.next_level} does not exist; "
                "history cannot be resolved until Academic Setup is repaired")
        return next_row
    explicit = frappe.db.get_value(LEVEL, {"code": target},
                                   ["name", "code", "next_level", "native_program"],
                                   as_dict=True)
    if not explicit:
        raise frappe.ValidationError(
            f"The policy's progression target {target} is not a configured level")
    return explicit


def rules_next():
    """The structural token meaning 'the catalog's next level'."""
    return "next"


def _attempts_made(row):
    """Distinct attempts recorded for this student and level (retake counting)."""
    attempts = frappe.get_all(RESULT,
                              filters={"student": row.student, "level": row.level},
                              fields=["attempt"])
    return len({int(attempt["attempt"] or 1) for attempt in attempts}) or 1


def _last_attempt_on(row):
    published = frappe.get_all(RESULT,
                               filters={"student": row.student, "level": row.level},
                               fields=["published_on"], order_by="published_on desc",
                               limit=1)
    if not published or not published[0].get("published_on"):
        return ""
    return str(published[0]["published_on"])[:10]


def _eligibility(row, facets, roles):
    progression = facets.get("progression")
    if not progression:
        raise frappe.ValidationError(
            "The pinned assessment policy version configures no progression "
            "rules; progression fails closed until the Course Owner defines them")
    return grading.evaluate_progression(
        progression, outcome=row.outcome,
        attendance_percent=row.attendance_percent, approval_roles=roles)


def _existing_decision(academic_result):
    return frappe.db.get_value(DECISION, {"academic_result": academic_result},
                               ["name", "decision", "decided_by"], as_dict=True)


@frappe.whitelist(methods=["POST"])
def decide_progression(request_key, academic_result, decision, reason):
    """Record the authorized academic progression decision for one result.

    ``Promote`` and ``Complete`` require the configured evidence to be met in
    full; ``Repeat`` and ``Retake`` are the governed negative outcomes and do
    not. ``Retake`` additionally requires the policy's retake rules to allow
    another attempt. Any decision requires the policy-configured approval
    role, and a result carries exactly one decision — a second one is a
    duplicate progression and is refused (a correction is a new decision on a
    new result revision).
    """
    def work(actor):
        name = _text(academic_result, "Academic result")
        if decision not in DECISIONS:
            raise frappe.ValidationError(
                "Decision must be one of " + ", ".join(DECISIONS))
        clean_reason = _reason(reason, "Decision reason")
        row = _published_result(name)
        existing = _existing_decision(name)
        if existing:
            raise frappe.ValidationError(
                f"A progression decision ({existing.decision}) is already recorded "
                "for this result; duplicate progression is refused")
        facets = _pinned_facets(row)
        roles = set(frappe.get_roles(actor))
        eligibility = _eligibility(row, facets, roles)
        level = _level_of(row)
        target = None
        if decision in ("Promote", "Complete"):
            if not eligibility["eligible"]:
                raise frappe.ValidationError(
                    "Progression is not eligible: " + " | ".join(eligibility["reasons"])
                    + ". Record Repeat/Retake, or request an authorized override")
            target = _target_level(level, facets.get("progression"))
            if decision == "Promote" and target is None:
                raise frappe.ValidationError(
                    "The catalog configures no next level for this level; record "
                    "Complete instead")
            if decision == "Complete" and target is not None:
                raise frappe.ValidationError(
                    f"The catalog configures the next level {target.code}; record "
                    "Promote instead of Complete")
        else:
            approval = [entry for entry in eligibility["requirements"]
                        if entry["kind"] == "approval"]
            if not approval or not all(entry["met"] for entry in approval):
                raise frappe.ValidationError(
                    "Progression requires authorized academic approval: "
                    + " | ".join(eligibility["reasons"]))
            if decision == "Retake":
                retakes = facets.get("retakes")
                if not retakes:
                    raise frappe.ValidationError(
                        "The pinned policy version configures no retake rules; "
                        "retakes fail closed until the Course Owner defines them")
                on_date = frappe.utils.today()
                try:
                    state = grading.retake_state(
                        retakes, attempts_made=_attempts_made(row),
                        last_attempt_on=_last_attempt_on(row), on_date=on_date)
                except ValueError as exc:
                    raise frappe.ValidationError(str(exc)) from exc
                if not state["allowed"]:
                    raise frappe.ValidationError(
                        "A retake is not permitted: " + state["reason"])
            target = level
        snapshot = {
            "algorithm": "th-progression-v1",
            "result": name,
            "student": row.student,
            "outcome": row.outcome,
            "overall_percent": row.overall_percent,
            "grade_code": row.grade_code,
            "attendance_percent": row.attendance_percent,
            "policy": {
                "policy": frappe.db.get_value(POLICY, row.policy, "code"),
                "effective_from": str(row.policy_effective_from),
            },
            "progression_rules": facets.get("progression"),
            "progression_target": (target.code if target else ""),
            "decision": decision,
            "eligibility": eligibility,
            "override_used": False,
            "decided_by": actor,
            "decided_on": frappe.utils.now_datetime(),
        }
        document = frappe.get_doc({
            "doctype": DECISION,
            "student": row.student,
            "student_group": row.student_group,
            "academic_result": name,
            "decision": decision,
            "status": "Approved",
            "from_level": level.name,
            "to_level": target.name if target else "",
            "policy": row.policy,
            "policy_effective_from": str(row.policy_effective_from),
            "eligible": 1 if eligibility["eligible"] else 0,
            "override_used": 0,
            "eligibility_json": canonical(snapshot),
            "eligibility_digest": digest(snapshot),
            "reason": clean_reason,
            "decided_by": actor,
            "decided_on": frappe.utils.now_datetime(),
            "synthetic": record_synthetic_flag(),
        })
        document.insert(ignore_permissions=True)
        return _decision_result(document, eligibility), {
            "target": document.name,
            "before_hash": "",
            "after_hash": digest([document.name, name, decision, digest(snapshot)]),
        }

    return _execute("decide_progression", request_key,
                    {"academic_result": academic_result, "decision": decision,
                     "reason": reason}, work)


@frappe.whitelist(methods=["POST"])
def override_progression(request_key, academic_result, decision, reason):
    """Record a senior, reasoned academic override of unmet eligibility.

    The override never edits the eligibility evidence: the snapshot still
    shows the requirements that were not met, the decision is marked
    ``override_used``, and only the General Manager may record one. It is
    available for ``Promote`` and ``Complete`` — the negative outcomes need no
    override.
    """
    def work(actor):
        name = _text(academic_result, "Academic result")
        if decision not in ("Promote", "Complete"):
            raise frappe.ValidationError(
                "An override applies to Promote or Complete; Repeat/Retake "
                "require no override")
        clean_reason = _reason(reason, "Override reason")
        row = _published_result(name)
        existing = _existing_decision(name)
        if existing:
            raise frappe.ValidationError(
                "A progression decision is already recorded for this result; "
                "duplicate progression is refused")
        facets = _pinned_facets(row)
        roles = set(frappe.get_roles(actor))
        eligibility = _eligibility(row, facets, roles)
        level = _level_of(row)
        target = _target_level(level, facets.get("progression"))
        if decision == "Promote" and target is None:
            raise frappe.ValidationError(
                "The catalog configures no next level for this level")
        if decision == "Complete" and target is not None:
            raise frappe.ValidationError(
                f"The catalog configures the next level {target.code}")
        unmet = [entry for entry in eligibility["requirements"] if not entry["met"]]
        if not unmet:
            raise frappe.ValidationError(
                "The configured progression requirements are already met; record "
                "the decision without an override")
        snapshot = {
            "algorithm": "th-progression-v1",
            "result": name,
            "student": row.student,
            "outcome": row.outcome,
            "overall_percent": row.overall_percent,
            "grade_code": row.grade_code,
            "attendance_percent": row.attendance_percent,
            "policy": {
                "policy": frappe.db.get_value(POLICY, row.policy, "code"),
                "effective_from": str(row.policy_effective_from),
            },
            "progression_rules": facets.get("progression"),
            "progression_target": (target.code if target else ""),
            "decision": decision,
            "eligibility": eligibility,
            "override_used": True,
            "overridden_requirements": unmet,
            "override_reason": clean_reason,
            "decided_by": actor,
            "decided_on": frappe.utils.now_datetime(),
        }
        document = frappe.get_doc({
            "doctype": DECISION,
            "student": row.student,
            "student_group": row.student_group,
            "academic_result": name,
            "decision": decision,
            "status": "Approved",
            "from_level": level.name,
            "to_level": target.name if target else "",
            "policy": row.policy,
            "policy_effective_from": str(row.policy_effective_from),
            "eligible": 1 if eligibility["eligible"] else 0,
            "override_used": 1,
            "override_reason": clean_reason,
            "eligibility_json": canonical(snapshot),
            "eligibility_digest": digest(snapshot),
            "reason": clean_reason,
            "decided_by": actor,
            "decided_on": frappe.utils.now_datetime(),
            "synthetic": record_synthetic_flag(),
        })
        document.insert(ignore_permissions=True)
        return _decision_result(document, eligibility), {
            "target": document.name,
            "before_hash": digest([name, "Published"]),
            "after_hash": digest([document.name, name, decision, "override"]),
        }

    return _execute("override_progression", request_key,
                    {"academic_result": academic_result, "decision": decision,
                     "reason": reason}, work)


def _decision_result(document, eligibility):
    return {
        "name": document.name,
        "student": document.student,
        "academic_result": document.academic_result,
        "decision": document.decision,
        "status": document.status,
        "from_level": document.get("from_level") or "",
        "to_level": document.get("to_level") or "",
        "eligible": bool(document.eligible),
        "override_used": bool(document.get("override_used")),
        "requirements": eligibility["requirements"],
        "reasons": eligibility["reasons"],
    }


# --- Next-level enrollment eligibility ------------------------------------
def next_level_eligibility(student, program):
    """Can this student enroll in ``program`` on progression grounds?

    Returns an explicit, explainable answer. ``required`` is False when the
    target program is not a successor level in the configured catalog, or
    when the student has no prior enrollment in the predecessor level — in
    both cases no progression decision is expected (a first enrollment is
    not a promotion).
    """
    student_name = _text(student, "Student")
    program_name = _text(program, "Program")
    level = frappe.db.get_value(LEVEL, {"native_program": program_name},
                                ["name", "code", "next_level", "native_program"],
                                as_dict=True)
    if not level:
        return {"required": False, "eligible": True, "level": "",
                "reasons": ["This program is not mapped to a program level"]}
    predecessor = frappe.db.get_value(LEVEL, {"next_level": level.code},
                                      ["name", "code", "native_program"],
                                      as_dict=True)
    if not predecessor:
        return {"required": False, "eligible": True, "level": level.name,
                "reasons": [f"Level {level.code} is an entry level in the catalog"]}
    prior = frappe.get_all(PROGRAM_ENROLLMENT,
                           filters={"student": student_name,
                                    "program": predecessor.native_program,
                                    "docstatus": ["<", 2]},
                           fields=["name", "academic_year"], limit=1)
    if not prior:
        return {"required": False, "eligible": True, "level": level.name,
                "from_level": predecessor.name,
                "reasons": [f"This student has no enrollment at level {predecessor.code}"]}
    decisions = frappe.get_all(DECISION,
                               filters={"student": student_name, "status": "Approved",
                                        "from_level": predecessor.name},
                               fields=["name", "decision", "to_level", "override_used",
                                       "academic_result"],
                               order_by="decided_on desc", limit=1)
    if not decisions:
        return {"required": True, "eligible": False, "level": level.name,
                "from_level": predecessor.name, "decision": "",
                "reasons": [f"No approved progression decision is recorded for level "
                            f"{predecessor.code}; enrollment into {level.code} is refused"]}
    decision = decisions[0]
    # A corrected result supersedes its prior decision evidence. No earlier
    # approved Promote can admit a student when its linked result is no
    # longer the current Published result (including post-correction).
    evidence_status = frappe.db.get_value(
        RESULT, decision.academic_result, "status") if decision.academic_result else None
    if evidence_status != "Published":
        return {"required": True, "eligible": False, "level": level.name,
                "from_level": predecessor.name, "decision": decision.name,
                "reasons": ["The prior progression evidence was superseded or "
                            "is no longer a published academic result; a new "
                            "approved decision is required"]}
    if decision.decision in ("Promote", "Complete") and decision.to_level == level.name:
        return {"required": True, "eligible": True, "level": level.name,
                "from_level": predecessor.name, "decision": decision.name,
                "override_used": bool(decision.override_used),
                "reasons": [f"An approved {decision.decision} decision "
                            f"({decision.name}) admits this level"]}
    return {"required": True, "eligible": False, "level": level.name,
            "from_level": predecessor.name, "decision": decision.name,
            "reasons": [f"The approved decision records {decision.decision} at level "
                        f"{predecessor.code}; it does not admit level {level.code}"]}


def enrollment_gate(student, program):
    """Refuse a native Program Enrollment that progression does not admit.

    Called by the enrollment command before it writes. Only configured
    successor levels with a prior predecessor enrollment are gated, so an
    unconfigured catalog behaves exactly as before.
    """
    state = next_level_eligibility(student, program)
    if state["required"] and not state["eligible"]:
        raise frappe.ValidationError(" ".join(state["reasons"]))
    return state


@frappe.whitelist(methods=["GET", "POST"])
def progression_state(student, program=""):
    """Read-only progression position for one student (desk projection)."""
    require_operational()
    student_name = _text(student, "Student")
    if not frappe.has_permission("Student", "read", student_name):
        raise frappe.PermissionError("Students are not available to your role")
    results = frappe.get_all(RESULT,
                             filters={"student": student_name, "status": "Published"},
                             fields=["name", "level", "outcome", "overall_percent",
                                     "grade_code", "attempt", "published_on"],
                             order_by="published_on desc", limit=20)
    decisions = frappe.get_all(DECISION, filters={"student": student_name},
                               fields=["name", "academic_result", "decision",
                                       "from_level", "to_level", "override_used",
                                       "decided_on"],
                               order_by="decided_on desc", limit=20)
    state = next_level_eligibility(student_name, program) if program else {}
    return {"student": student_name, "results": results, "decisions": decisions,
            "next_level": state}

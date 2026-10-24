"""Owner configuration for everyday class operations (fail-closed by default).

Everything an institute can choose about classes lives in ONE effective-dated
policy master — teaching days, session duration bounds, the daily session
limit, timetable generation horizon, postponement/cancellation/replacement
windows, suspension limits, waiting-list behaviour, capacity overrides,
transfer approval and the direct-move switch. No value is coded in: with no
policy row, a retired policy, no effective version, or a term set that fails
validation, every policy-gated class command refuses in business language.

The commands follow the house configuration pattern exactly
(docs/CONFIGURATION-PLANE.md): the Course Owner is the only writer, every
version carries a mandatory reason, versions are append-only and monotone by
effective date, the superseded row is closed (never rewritten), and every
write lands in the hash-chained configuration audit ledger.

Reads are pure/decision-only: :func:`governing_operations` resolves the
version governing a date and returns its validated terms, or ``{}`` when
nothing governs. That empty result is the off-switch — never a default.
"""
import frappe

from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest

POLICY = "TH Class Operations Policy"

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
WEEKDAY_INDEX = {code: index for index, code in enumerate(WEEKDAYS)}

# Engineering typo guards, not institutional policy: the owner may choose any
# value inside these bounds. They only stop a mistyped number from silently
# becoming an operating rule.
MINUTES_FLOOR, MINUTES_CEILING = 5, 600
MAX_SESSIONS_PER_DAY_CEILING = 24
HORIZON_CEILING = 366
WINDOW_CEILING = 365
SUSPENSION_CEILING = 180
OFFER_VALIDITY_CEILING = 90
OVERRIDE_SEATS_CEILING = 50
OVERRIDE_EXPIRY_CEILING = 90
TRANSFER_WINDOW_CEILING = 180
ROLE_LIMIT = 140

# The complete set of configurable terms. A version must carry every one of
# them explicitly: nothing is defaulted, so an operator can always read the
# governing rules off a single row and a missing field is a refusal, never a
# silent assumption.
TERM_KEYS = (
    "teaching_days",
    "default_session_minutes",
    "min_session_minutes",
    "max_session_minutes",
    "max_sessions_per_day",
    "timetable_horizon_days",
    "allow_postponement",
    "postpone_max_days",
    "allow_session_cancellation",
    "allow_replacement_sessions",
    "replacement_approver_role",
    "replacement_window_days",
    "allow_class_suspension",
    "class_suspension_max_days",
    "allow_student_suspension",
    "student_suspension_max_days",
    "waiting_list_enabled",
    "waiting_offer_valid_days",
    "remove_member_allowed",
    "capacity_override_role",
    "capacity_override_max_seats",
    "capacity_override_expiry_days",
    "allow_transfers",
    "allow_program_transfers",
    "allow_branch_transfers",
    "transfer_approver_role",
    "transfer_window_days",
    "direct_moves_allowed",
)
BOOLEAN_TERMS = (
    "allow_postponement",
    "allow_session_cancellation",
    "allow_replacement_sessions",
    "allow_class_suspension",
    "allow_student_suspension",
    "waiting_list_enabled",
    "remove_member_allowed",
    "allow_transfers",
    "allow_program_transfers",
    "allow_branch_transfers",
    "direct_moves_allowed",
)
ROLE_TERMS = ("replacement_approver_role", "capacity_override_role",
              "transfer_approver_role")
# Terms that only make sense when their feature is switched on. They are
# still shape-validated when the feature is off so a typo cannot hide.
FEATURE_WINDOWS = {
    "allow_postponement": ("postpone_max_days", 1, WINDOW_CEILING),
    "allow_replacement_sessions": ("replacement_window_days", 1, WINDOW_CEILING),
    "allow_class_suspension": ("class_suspension_max_days", 1, SUSPENSION_CEILING),
    "allow_student_suspension": ("student_suspension_max_days", 1, SUSPENSION_CEILING),
    "waiting_list_enabled": ("waiting_offer_valid_days", 1, OFFER_VALIDITY_CEILING),
}


def _as_bool(value, what):
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "yes"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("false", "no"):
        return False
    raise ValueError(f"{what} must be true or false")


def _int(value, what, low, high):
    if isinstance(value, bool):
        raise ValueError(f"{what} must be a whole number")
    if isinstance(value, str) and value.strip():
        try:
            value = int(value.strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{what} must be a whole number") from exc
    if not isinstance(value, int):
        raise ValueError(f"{what} must be a whole number")
    if not low <= value <= high:
        raise ValueError(f"{what} must be between {low} and {high}")
    return value


def _role(value, what):
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > ROLE_LIMIT:
        raise ValueError(f"{what} must name a Role")
    return value.strip()


def parse_teaching_days(value):
    """Normalize a configured teaching-days value to a weekday-code tuple.

    Accepts the stored comma form ("Mon,Tue,Wed") or a list of codes. Order
    and duplicates are canonicalized; an empty list is invalid — an institute
    that teaches no day cannot schedule a session, so the policy says so
    explicitly instead of defaulting to every day.
    """
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, (list, tuple)):
        parts = [str(part).strip() for part in value if str(part).strip()]
    else:
        raise ValueError("Teaching days must be a comma-separated list of weekday codes")
    if not parts:
        raise ValueError("Teaching days must name at least one weekday")
    unknown = [part for part in parts if part not in WEEKDAYS]
    if unknown:
        raise ValueError(
            "Unknown teaching day(s) " + ", ".join(unknown) +
            "; use " + ", ".join(WEEKDAYS))
    ordered = [code for code in WEEKDAYS if code in set(parts)]
    return tuple(ordered)


def teaching_days_value(terms):
    """The stored comma form of a validated terms mapping."""
    return ",".join(terms.get("teaching_days") or ())


def validate_terms(value):
    """Validate one policy version's complete term set; return a clean copy.

    Raises ``ValueError`` naming the offending term. No default is applied:
    missing keys are refused, unknown keys are refused (so a typo cannot
    silently become an inert field), and a term that only applies to an
    enabled feature must still be within its engineering bound.
    """
    if not isinstance(value, dict):
        raise ValueError("Class-operations policy terms must be an object")
    unknown = sorted(set(value) - set(TERM_KEYS))
    if unknown:
        raise ValueError("Unknown class-operations term(s): " + ", ".join(unknown))
    missing = sorted(set(TERM_KEYS) - set(value))
    if missing:
        raise ValueError(
            "Every class-operations term must be set explicitly; missing: " +
            ", ".join(missing))
    terms = {"teaching_days": parse_teaching_days(value["teaching_days"])}
    for key in BOOLEAN_TERMS:
        terms[key] = _as_bool(value[key], key)
    for key in ROLE_TERMS:
        terms[key] = _role(value[key], key)

    terms["default_session_minutes"] = _int(
        value["default_session_minutes"], "Default session minutes",
        MINUTES_FLOOR, MINUTES_CEILING)
    terms["min_session_minutes"] = _int(
        value["min_session_minutes"], "Minimum session minutes",
        MINUTES_FLOOR, MINUTES_CEILING)
    terms["max_session_minutes"] = _int(
        value["max_session_minutes"], "Maximum session minutes",
        MINUTES_FLOOR, MINUTES_CEILING)
    if not terms["min_session_minutes"] <= terms["default_session_minutes"] <= terms["max_session_minutes"]:
        raise ValueError(
            "Session minutes must satisfy minimum <= default <= maximum")
    terms["max_sessions_per_day"] = _int(
        value["max_sessions_per_day"], "Maximum sessions per class per day",
        1, MAX_SESSIONS_PER_DAY_CEILING)
    terms["timetable_horizon_days"] = _int(
        value["timetable_horizon_days"], "Timetable generation horizon",
        1, HORIZON_CEILING)
    terms["postpone_max_days"] = _int(
        value["postpone_max_days"], "Postponement horizon", 0, WINDOW_CEILING)
    terms["replacement_window_days"] = _int(
        value["replacement_window_days"], "Replacement window", 0, WINDOW_CEILING)
    terms["class_suspension_max_days"] = _int(
        value["class_suspension_max_days"], "Class suspension limit", 0, SUSPENSION_CEILING)
    terms["student_suspension_max_days"] = _int(
        value["student_suspension_max_days"], "Student suspension limit", 0, SUSPENSION_CEILING)
    terms["waiting_offer_valid_days"] = _int(
        value["waiting_offer_valid_days"], "Waiting-list offer validity", 0, OFFER_VALIDITY_CEILING)
    terms["capacity_override_max_seats"] = _int(
        value["capacity_override_max_seats"], "Maximum override seats", 0, OVERRIDE_SEATS_CEILING)
    terms["capacity_override_expiry_days"] = _int(
        value["capacity_override_expiry_days"], "Override expiry", 0, OVERRIDE_EXPIRY_CEILING)
    terms["transfer_window_days"] = _int(
        value["transfer_window_days"], "Transfer window", 0, TRANSFER_WINDOW_CEILING)

    for flag, (window_key, low, high) in FEATURE_WINDOWS.items():
        if terms[flag] and not low <= terms[window_key] <= high:
            raise ValueError(
                f"{window_key} must be between {low} and {high} when {flag} is enabled")
    if terms["allow_replacement_sessions"] and not terms["replacement_approver_role"]:
        raise ValueError(
            "A replacement approver role is required when replacement sessions are allowed")
    if terms["allow_transfers"]:
        if not terms["transfer_approver_role"]:
            raise ValueError(
                "A transfer approver role is required when transfers are allowed")
    else:
        if terms["allow_program_transfers"] or terms["allow_branch_transfers"]:
            raise ValueError(
                "Program and branch transfers require transfers to be allowed")
    if terms["capacity_override_role"]:
        if not 1 <= terms["capacity_override_max_seats"] <= OVERRIDE_SEATS_CEILING:
            raise ValueError(
                "capacity_override_max_seats must be between 1 and "
                f"{OVERRIDE_SEATS_CEILING} once an override role is set")
        if not 1 <= terms["capacity_override_expiry_days"] <= OVERRIDE_EXPIRY_CEILING:
            raise ValueError(
                "capacity_override_expiry_days must be between 1 and "
                f"{OVERRIDE_EXPIRY_CEILING} once an override role is set")
    return terms


def terms_from_row(row):
    """Validate one stored version row (child Document or dict)."""
    values = row.as_dict() if hasattr(row, "as_dict") else dict(row or {})
    return validate_terms({key: values.get(key) for key in TERM_KEYS})


def require_feature(terms, flag, message):
    """Refuse a policy-gated action whose feature is switched off."""
    if not terms or not terms.get(flag):
        raise frappe.ValidationError(message)
    return terms


def _policy_doc(code, for_update=False):
    name = frappe.db.get_value(POLICY, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown class-operations policy: {code}")
    return frappe.get_doc(POLICY, name, for_update=for_update)


def _policy_result(doc, extra=None):
    versions = [row.as_dict() for row in (doc.get("versions") or [])]
    governing = configuration_rules.resolve_governing(
        versions, frappe.utils.today())
    result = {
        "name": doc.name, "code": doc.code, "title": doc.title,
        "status": doc.status, "version_count": len(versions),
        "governing_effective_from": (
            str(governing.get("effective_from")) if governing else ""),
        "governing_teaching_days": (
            str(governing.get("teaching_days") or "") if governing else ""),
    }
    if extra:
        result.update(extra)
    return result


def governing_operations(on_date=None):
    """Read-only resolver: validated governing terms, or ``{}``.

    Fail-closed in four ways — no policy row, retired policy, no effective
    version, or a stored term set that no longer validates. A pure read used
    inside command ``work()`` closures, exactly like the roster-change
    resolver; it writes nothing and carries no receipt.
    """
    rows = frappe.db.get_all(POLICY, fields=["name"], limit=1)
    if not rows:
        return {}
    doc = frappe.get_doc(POLICY, rows[0]["name"])
    if doc.status != "Active":
        return {}
    versions = [row.as_dict() for row in (doc.get("versions") or [])]
    governing = configuration_rules.resolve_governing(
        versions, on_date or frappe.utils.today())
    if not governing:
        return {}
    try:
        terms = terms_from_row(governing)
    except ValueError:
        return {}
    terms["effective_from"] = str(governing.get("effective_from") or "")
    return terms


def require_operations(on_date=None, feature=None, message=None):
    """The governing terms, or a business-language refusal."""
    terms = governing_operations(on_date)
    if not terms:
        raise frappe.ValidationError(
            "No active class-operations policy version is in effect; class "
            "operations stay disabled until the Course Owner configures one")
    if feature:
        require_feature(
            terms, feature,
            message or f"This operation is not permitted by the governing "
                        f"class-operations policy ({feature} is off)")
    return terms


@frappe.whitelist(methods=["POST"])
def create_class_operations_policy(request_key, code, title, description=""):
    """Define the class-operations policy shell (versions carry the terms).

    Creates the single policy row with NO versions: every policy-gated
    operation stays denied until the Course Owner appends the first
    effective-dated version. The shell carries no defaults.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Class-operations policy title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.get_all(POLICY, fields=["name"], limit=1):
            raise frappe.ValidationError(
                "A class-operations policy already exists; version it instead")
        if frappe.db.exists(POLICY, clean_code):
            raise frappe.ValidationError(
                f"Class-operations policy {clean_code} already exists")
        doc = frappe.get_doc({
            "doctype": POLICY,
            "code": clean_code, "title": clean_title, "status": "Active",
            "description": clean_description,
        })
        doc.insert(ignore_permissions=True)
        return _policy_result(doc), {
            "target": doc.name, "before_hash": "",
            "after_hash": configuration_rules.snapshot_digest([]),
        }

    payload = {"code": code, "title": title, "description": description}
    return configuration_audit.execute(
        "create_class_operations_policy", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_class_operations_policy_version(request_key, policy, effective_from,
                                        reason, terms):
    """Append an effective-dated version carrying the complete term set.

    Backdated or same-day versions are refused; the superseded version is
    closed, never rewritten. A mandatory reason records WHY the rules change.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            clean_terms = validate_terms(terms)
            for key in ROLE_TERMS:
                role = clean_terms[key]
                if role and not frappe.db.exists("Role", role):
                    raise ValueError(f"{key} names an unknown Role: {role}")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Class-operations policy {clean_code} is retired; reactivate "
                "it before adding a version")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="class-operations policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        before = configuration_audit.latest_after_hash(doc.name)
        row = {"effective_from": clean_from, "reason": clean_reason,
               "set_by": actor, "set_on": frappe.utils.now_datetime(),
               "teaching_days": teaching_days_value(clean_terms)}
        for key in TERM_KEYS:
            if key == "teaching_days":
                continue
            row[key] = clean_terms[key]
        doc.append("versions", row)
        if current:
            for existing in doc.get("versions") or []:
                if (str(existing.get("effective_from")) == str(current.get("effective_from"))
                        and not existing.get("superseded_on")):
                    existing.superseded_on = clean_from
                    break
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("versions") or [])])
        return _policy_result(doc, {"terms": {
            key: (list(value) if isinstance(value, tuple) else value)
            for key, value in clean_terms.items()}}), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "effective_from": effective_from,
               "reason": reason, "terms": terms}
    return configuration_audit.execute(
        "set_class_operations_policy_version", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_class_operations_policy_status(request_key, policy, active):
    """Retire or reactivate the policy; retiring disables every gated action."""
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            flag = _as_bool(active, "active")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _policy_doc(clean_code, for_update=True)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.status = "Active" if flag else "Retired"
        doc.save(ignore_permissions=True)
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        after = digest(["status", doc.status,
                        configuration_rules.snapshot_digest(versions)])
        return _policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "active": active}
    return configuration_audit.execute(
        "set_class_operations_policy_status", request_key, payload, work)

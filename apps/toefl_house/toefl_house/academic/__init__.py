"""Owner configuration commands: the Academic Control Plane's guarded gate.

This is a governance surface in the administration precedent
(``toefl_house.administration``): NOT synthetic-gated — the Course Owner
configures the real institution, exactly like role governance — and fail-closed
on every input. The Course Owner role is checked at the command gate; native
records are then written inside the gate, so no additional native write
authority is granted to anybody.

What this deliberately is NOT:
- not a second Program/Enrollment/Fee authority: levels ARE native ``Program``
  records; enrollments, fee structures, classes and assessments consume them
  through native links (docs/product/CONFIGURATION-PLANE.md);
- not a rule engine: structured configuration + validation + effective dating;
- not deletable: configuration is deactivated/retired, never removed, and the
  doctype permissions carry no delete for any role.

Audit: native ``Version`` (track_changes on both configuration doctypes)
records who/what/before/after/when; duration versions additionally carry
set_by/set_on/reason/effective_from as first-class data because the effective
date IS business meaning, not just audit metadata.
"""
import frappe

from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest, validate_request_key

PROGRAM = "TH Academic Program"
LEVEL = "TH Program Level"
ASSESSMENT_POLICY = "TH Assessment Policy"
GRADING_SCALE = "Grading Scale"
GRADING_INTERVAL = "Grading Scale Interval"
ASSESSMENT_CRITERIA = "Assessment Criteria"
DURATION = "TH Level Duration"
NATIVE_PROGRAM = "Program"
ENROLLMENT = "Program Enrollment"
YEAR = "Academic Year"
FEE_CATEGORY = "Fee Category"
FEE_STRUCTURE = "Fee Structure"
DISCOUNT_RULE = "TH Discount Rule"


def _require_course_owner():
    user = frappe.session.user
    if user in (None, "Guest", "Administrator") or "Course Owner" not in set(frappe.get_roles(user)):
        raise frappe.PermissionError(
            "The Course Owner configures the academic control plane; "
            "ask the Course Owner for this change")
    # S3: a disabled login holds no authority even with the role still
    # attached (same rule the desk audience gate enforces).
    if not frappe.db.get_value("User", user, "enabled"):
        raise frappe.PermissionError("This account has been disabled.")
    return user


def _context():
    return (frappe.utils.now_datetime().isoformat(timespec="seconds"),
            frappe.utils.today())


def _family_doc(code, for_update=False):
    name = frappe.db.get_value(PROGRAM, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown program: {code}")
    return frappe.get_doc(PROGRAM, name, for_update=for_update)


def _level_doc(code, for_update=False):
    name = frappe.db.get_value(LEVEL, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown level: {code}")
    return frappe.get_doc(LEVEL, name, for_update=for_update)


@frappe.whitelist(methods=["POST"])
def create_program(request_key, code, title, description=""):
    """Define a program family (e.g. a language track the institution sells).

    Receipted (S5): a replayed (kind, key) with the identical payload
    returns the recorded result instead of double-applying; a conflicting
    payload under the same key is refused. A different key for an existing
    code still fails as a duplicate. The family owns no money and no
    enrollment — it orders and governs its levels.
    """
    def work(actor):
        try:
            validate_request_key(request_key)
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Program title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.exists(PROGRAM, clean_code):
            raise frappe.ValidationError(f"Program {clean_code} already exists")
        doc = frappe.get_doc({
            "doctype": PROGRAM, "code": clean_code, "title": clean_title,
            "status": "Active", "description": clean_description,
        })
        doc.insert(ignore_permissions=True)
        result = _program_result(doc)
        return result, {
            "target": doc.name,
            "before_hash": configuration_audit.latest_after_hash(doc.name),
            "after_hash": digest(result),
        }

    return configuration_audit.execute(
        "create_program", request_key,
        {"code": code, "title": title, "description": description}, work)


@frappe.whitelist(methods=["POST"])
def create_level(request_key, family, code, title, sequence,
                 duration_value, duration_unit, effective_from, next_level=""):
    """Define one level of a program family and anchor it to a native Program.

    The native Education ``Program`` is created here so that native Program
    Enrollment, Fee Structure (which is keyed per Program), Student Group,
    Assessment Plan and every dashboard consume the level without any
    TOEFL-specific master. The anchor is written once and never changed.
    """
    def work(actor):
        try:
            validate_request_key(request_key)
            clean_family = rules.validate_code(family)
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Level title")
            clean_sequence = rules.validate_sequence(sequence)
            clean_value = rules.validate_duration_value(duration_value, duration_unit)
            clean_from = rules.parse_date(effective_from)
            clean_next = rules.validate_reason(next_level or "")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc

        family_doc = _family_doc(clean_family, for_update=True)
        if family_doc.status != "Active":
            raise frappe.ValidationError(
                f"Program {clean_family} is retired; reactivate it before adding levels")
        if frappe.db.exists(LEVEL, clean_code):
            raise frappe.ValidationError(f"Level {clean_code} already exists")
        siblings = frappe.db.get_all(LEVEL, filters={"family": family_doc.name},
                                     fields=["code", "sequence"])
        if any(int(row["sequence"]) == clean_sequence for row in siblings):
            raise frappe.ValidationError(
                f"Level position {clean_sequence} is already taken in {clean_family}; "
                "two levels cannot share one position")
        if clean_next:
            rules.validate_next_level(
                clean_code, clean_next,
                family_of=lambda c: _family_of(c),
                next_of=lambda c: _next_of(c))

        native = frappe.get_doc({
            "doctype": NATIVE_PROGRAM,
            "program_name": f"{family_doc.title} — {clean_title}",
            "program_abbreviation": clean_code,
        })
        native.insert(ignore_permissions=True)
        doc = frappe.get_doc({
            "doctype": LEVEL, "family": family_doc.name, "code": clean_code,
            "title": clean_title, "sequence": clean_sequence, "status": "Active",
            "native_program": native.name, "next_level": clean_next or None,
            "durations": [{
                "duration_value": clean_value, "duration_unit": duration_unit,
                "effective_from": clean_from, "reason": "Initial configuration",
                "set_by": actor, "set_on": frappe.utils.now_datetime(),
            }],
        })
        doc.insert(ignore_permissions=True)
        result = _level_result(doc)
        return result, {
            "target": doc.name,
            "before_hash": configuration_audit.latest_after_hash(doc.name),
            "after_hash": digest(result),
        }

    return configuration_audit.execute(
        "create_level", request_key,
        {"family": family, "code": code, "title": title, "sequence": sequence,
         "duration_value": duration_value, "duration_unit": duration_unit,
         "effective_from": effective_from, "next_level": next_level}, work)


@frappe.whitelist(methods=["POST"])
def set_level_duration(request_key, level, duration_value, duration_unit,
                       effective_from, reason=""):
    """Append a new effective-dated duration version for a level.

    Older versions are closed (superseded_on), never rewritten: enrollments
    and fees created under the previous version keep their historical truth,
    and every date still resolves to exactly one governing version.
    """
    def work(actor):
        try:
            validate_request_key(request_key)
            clean_value = rules.validate_duration_value(duration_value, duration_unit)
            clean_from = rules.parse_date(effective_from)
            clean_reason = rules.validate_reason(reason)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _level_doc(level, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Level {level} is retired; reactivate it before changing its duration")
        try:
            versions = [row.as_dict() for row in (doc.get("durations") or [])]
            rules.check_version_appends(versions, clean_from)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = rules.latest_version(versions)
        doc.append("durations", {
            "duration_value": clean_value, "duration_unit": duration_unit,
            "effective_from": clean_from, "reason": clean_reason,
            "set_by": actor, "set_on": frappe.utils.now_datetime(),
        })
        if current:
            # Close the superseded version; never rewrite its meaning, only record
            # the date it stopped governing new activity.
            for row in doc.get("durations") or []:
                if (str(row.get("effective_from")) == str(current.get("effective_from"))
                        and not row.get("superseded_on")):
                    row.superseded_on = clean_from
                    break
        doc.save(ignore_permissions=True)
        result = _level_result(doc, extra={
            "previous_version": (rules.duration_label(current) if current else ""),
            "previous_effective_from": (str(current.get("effective_from")) if current else ""),
        })
        return result, {
            "target": doc.name,
            "before_hash": configuration_audit.latest_after_hash(doc.name),
            "after_hash": digest(result),
        }

    return configuration_audit.execute(
        "set_level_duration", request_key,
        {"level": level, "duration_value": duration_value,
         "duration_unit": duration_unit, "effective_from": effective_from,
         "reason": reason}, work)


@frappe.whitelist(methods=["POST"])
def set_next_level(request_key, level, next_level):
    """Configure where students normally progress after this level."""
    def work(actor):
        try:
            validate_request_key(request_key)
            clean_code = rules.validate_code(level)
            clean_next = rules.validate_reason(next_level or "")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _level_doc(clean_code, for_update=True)
        if clean_next:
            rules.validate_next_level(
                clean_code, clean_next,
                family_of=lambda c: _family_of(c),
                next_of=lambda c: _next_of(c))
            if _level_doc(clean_next).status != "Active":
                raise frappe.ValidationError(
                    f"The next level {clean_next} is retired; progression must point "
                    "at an active level")
        doc.next_level = clean_next or None
        doc.save(ignore_permissions=True)
        result = _level_result(doc)
        return result, {
            "target": doc.name,
            "before_hash": configuration_audit.latest_after_hash(doc.name),
            "after_hash": digest(result),
        }

    return configuration_audit.execute(
        "set_next_level", request_key,
        {"level": level, "next_level": next_level}, work)


@frappe.whitelist(methods=["POST"])
def set_program_status(request_key, program, active):
    """Deactivate (retire) or reactivate a program family."""
    def work(actor):
        try:
            validate_request_key(request_key)
            clean_code = rules.validate_code(program)
            flag = _as_bool(active, "active")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _family_doc(clean_code, for_update=True)
        if not flag:
            active_levels = frappe.db.count(
                LEVEL, {"family": doc.name, "status": "Active"})
            if active_levels:
                raise frappe.ValidationError(rules.program_has_levels_message(clean_code, active_levels))
        doc.status = "Active" if flag else "Retired"
        doc.save(ignore_permissions=True)
        result = _program_result(doc)
        return result, {
            "target": doc.name,
            "before_hash": configuration_audit.latest_after_hash(doc.name),
            "after_hash": digest(result),
        }

    return configuration_audit.execute(
        "set_program_status", request_key,
        {"program": program, "active": active}, work)


@frappe.whitelist(methods=["POST"])
def set_level_status(request_key, level, active):
    """Deactivate (retire) or reactivate a level.

    Deactivation is refused in business language while submitted native
    enrollments still run on the level (no raw exception, no silent damage).
    """
    def work(actor):
        try:
            validate_request_key(request_key)
            clean_code = rules.validate_code(level)
            flag = _as_bool(active, "active")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _level_doc(clean_code, for_update=True)
        if not flag:
            if not doc.native_program:
                raise frappe.ValidationError(rules.level_missing_native_message(clean_code))
            in_use = frappe.db.count(
                ENROLLMENT, {"program": doc.native_program, "docstatus": 1})
            if in_use:
                raise frappe.ValidationError(rules.level_in_use_message(clean_code, in_use))
        else:
            family_status = frappe.db.get_value(PROGRAM, doc.family, "status")
            if family_status != "Active":
                raise frappe.ValidationError(
                    f"The program family {doc.family} is retired; reactivate it first")
        doc.status = "Active" if flag else "Retired"
        doc.save(ignore_permissions=True)
        result = _level_result(doc)
        return result, {
            "target": doc.name,
            "before_hash": configuration_audit.latest_after_hash(doc.name),
            "after_hash": digest(result),
        }

    return configuration_audit.execute(
        "set_level_status", request_key,
        {"level": level, "active": active}, work)


def _as_bool(value, what):
    if isinstance(value, str):
        if value in ("0", "1"):
            return value == "1"
        raise ValueError(f"{what} must be 0 or 1")
    if isinstance(value, (int, bool)) and not isinstance(value, float):
        return bool(value)
    raise ValueError(f"{what} must be boolean-like")


@frappe.whitelist(methods=["POST"])
def create_academic_year(request_key, name, start_date, end_date):
    """Define a native Academic Year (required by fees, enrollment, classes).

    Native Education requires Academic Year records for Fee Structure and
    Program Enrollment, yet nothing in the owned product created them — this
    command closes that setup gap through the same governed gate as the rest
    of the control plane.
    """
    def work(actor):
        try:
            validate_request_key(request_key)
            clean_name = rules.validate_title(name, "Academic year name")
            start, end = rules.validate_year_bounds(start_date, end_date)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.exists(YEAR, clean_name):
            raise frappe.ValidationError(f"Academic year {clean_name} already exists")
        doc = frappe.get_doc({
            "doctype": YEAR, "academic_year_name": clean_name,
            "year_start_date": start, "year_end_date": end,
        })
        doc.insert(ignore_permissions=True)
        result = {"name": doc.name, "start_date": start, "end_date": end}
        return result, {
            "target": doc.name,
            "before_hash": configuration_audit.latest_after_hash(doc.name),
            "after_hash": digest(result),
        }

    return configuration_audit.execute(
        "create_academic_year", request_key,
        {"name": name, "start_date": start_date, "end_date": end_date}, work)


@frappe.whitelist(methods=["POST"])
def create_fee_type(request_key, name, description=""):
    """Define a fee type as a native Fee Category (the native Item follows).

    Native Education's Fee Category controller creates and maintains the
    accounting Item itself (verified at the pinned commit), so the Owner
    defines the *type* and native authority owns the accounting object.
    """
    def work(actor):
        try:
            validate_request_key(request_key)
            clean_name = rules.validate_title(name, "Fee type name")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.exists(FEE_CATEGORY, clean_name):
            raise frappe.ValidationError(f"Fee type {clean_name} already exists")
        if not frappe.db.exists("Item Group", "Fee Component"):
            raise frappe.ValidationError(
                "The native 'Fee Component' item group is missing, so fee types "
                "cannot receive their accounting Item. Ask the administrator to "
                "complete the Education app setup, then retry.")
        doc = frappe.get_doc({
            "doctype": FEE_CATEGORY, "category_name": clean_name,
            "description": clean_description,
        })
        doc.insert(ignore_permissions=True)
        result = {"name": doc.name,
                  "item": frappe.db.get_value(FEE_CATEGORY, doc.name, "item")}
        return result, {
            "target": doc.name,
            "before_hash": configuration_audit.latest_after_hash(doc.name),
            "after_hash": digest(result),
        }

    return configuration_audit.execute(
        "create_fee_type", request_key,
        {"name": name, "description": description}, work)


@frappe.whitelist(methods=["POST"])
def set_level_fee_component(request_key, level, academic_year, fee_category, amount,
                            company=""):
    """Configure one fee component of a level's native fee plan (upsert).

    The plan is the native Fee Structure keyed on the level's anchored native
    Program and the academic year — exactly what the qualified Finance
    issuance command consumes. It is kept in Draft so the Owner's policy
    stays editable; issued Fees copy their components at issuance, so
    changing this configuration never touches a posted document.
    """
    def work(actor):
        try:
            validate_request_key(request_key)
            clean_level = rules.validate_code(level)
            clean_amount = rules.validate_fee_amount(amount)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        level_doc = _level_doc(clean_level, for_update=True)
        if level_doc.status != "Active":
            raise frappe.ValidationError(
                f"Level {clean_level} is retired; reactivate it before configuring fees")
        if not level_doc.native_program:
            raise frappe.ValidationError(rules.level_missing_native_message(clean_level))
        if not frappe.db.exists(YEAR, academic_year):
            raise frappe.ValidationError(
                f"Academic year {academic_year} does not exist yet; define it first")
        if not frappe.db.exists(FEE_CATEGORY, fee_category):
            raise frappe.ValidationError(
                f"Fee type {fee_category} does not exist yet; define it first")
        structure = _managed_fee_structure(level_doc.native_program, academic_year, company)
        rows = structure.get("components") or []
        for row in rows:
            if row.get("fees_category") == fee_category:
                if float(row.get("amount") or 0) == float(clean_amount):
                    result = _fee_plan_result(structure, clean_level, academic_year,
                                              replayed=True)
                    return result, {
                        "target": structure.name,
                        "before_hash": configuration_audit.latest_after_hash(structure.name),
                        "after_hash": digest(result),
                    }
                row.amount = clean_amount
                structure.save(ignore_permissions=True)
                result = _fee_plan_result(structure, clean_level, academic_year)
                return result, {
                    "target": structure.name,
                    "before_hash": configuration_audit.latest_after_hash(structure.name),
                    "after_hash": digest(result),
                }
        structure.append("components", {"fees_category": fee_category, "amount": clean_amount})
        structure.save(ignore_permissions=True)
        result = _fee_plan_result(structure, clean_level, academic_year)
        return result, {
            "target": structure.name,
            "before_hash": configuration_audit.latest_after_hash(structure.name),
            "after_hash": digest(result),
        }

    return configuration_audit.execute(
        "set_level_fee_component", request_key,
        {"level": level, "academic_year": academic_year,
         "fee_category": fee_category, "amount": amount,
         "company": company}, work)


@frappe.whitelist(methods=["POST"])
def remove_level_fee_component(request_key, level, academic_year, fee_category):
    """Remove one fee component from a level's plan.

    Issued Fees keep their copied components; only future issuance is
    affected. The plan must keep at least one component.
    """
    def work(actor):
        try:
            validate_request_key(request_key)
            clean_level = rules.validate_code(level)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        level_doc = _level_doc(clean_level, for_update=True)
        if not level_doc.native_program:
            raise frappe.ValidationError(rules.level_missing_native_message(clean_level))
        if not frappe.db.exists(YEAR, academic_year):
            raise frappe.ValidationError(f"Academic year {academic_year} does not exist")
        structure = _managed_fee_structure(level_doc.native_program, academic_year)
        rows = structure.get("components") or []
        remaining = [row for row in rows if row.get("fees_category") != fee_category]
        if len(remaining) == len(rows):
            raise frappe.ValidationError(
                f"Fee type {fee_category} is not part of the "
                f"{clean_level} plan for {academic_year}")
        if not remaining:
            raise frappe.ValidationError(
                "A fee plan must keep at least one component; remove the whole "
                "plan with Finance if the level should bill nothing")
        structure.set("components", remaining)
        structure.save(ignore_permissions=True)
        result = _fee_plan_result(structure, clean_level, academic_year)
        return result, {
            "target": structure.name,
            "before_hash": configuration_audit.latest_after_hash(structure.name),
            "after_hash": digest(result),
        }

    return configuration_audit.execute(
        "remove_level_fee_component", request_key,
        {"level": level, "academic_year": academic_year,
         "fee_category": fee_category}, work)


FEE_STRUCTURE_NAMING = "EDU-FST-.YYYY.-"  # native default from the pinned doctype


def _managed_fee_structure(native_program, academic_year, company=""):
    """The one editable (Draft) Fee Structure for (program, academic year).

    The control plane manages Draft structures — the qualified issuance
    command reads them regardless of docstatus, and submission would lock
    the Owner's policy behind cancel/amend churn. More than one editable
    structure for the same key is a configuration conflict this refuses.
    """
    found = frappe.db.get_all(
        FEE_STRUCTURE,
        filters={"program": native_program, "academic_year": academic_year,
                 "docstatus": 0},
        fields=["name"], order_by="name asc", limit=2)
    if len(found) > 1:
        raise frappe.ValidationError(
            f"More than one editable fee structure exists for {native_program} "
            f"in {academic_year}; keep exactly one so billing is unambiguous")
    if found:
        return frappe.get_doc(FEE_STRUCTURE, found[0]["name"], for_update=True)
    company_name = _resolve_company(company)
    receivable = frappe.db.get_value(
        "Company", company_name, "default_receivable_account")
    if not receivable:
        raise frappe.ValidationError(
            f"Company {company_name} has no default receivable account; "
            "Finance must set it before fee plans can be configured")
    doc = frappe.get_doc({
        "doctype": FEE_STRUCTURE,
        "naming_series": FEE_STRUCTURE_NAMING,
        "program": native_program, "academic_year": academic_year,
        "company": company_name, "receivable_account": receivable,
        "components": [],
    })
    doc.insert(ignore_permissions=True)
    return doc


def _resolve_company(company=""):
    """Explicit company, or the only existing one; refuse ambiguity."""
    if isinstance(company, str) and company.strip():
        name = company.strip()
        if not frappe.db.exists("Company", name):
            raise frappe.ValidationError(f"Unknown company: {name}")
        return name
    companies = frappe.db.get_all("Company", fields=["name"], order_by="name asc",
                                  limit=2)
    if not companies:
        raise frappe.ValidationError(
            "No company exists yet; create the company before configuring fees")
    if len(companies) > 1:
        raise frappe.ValidationError(
            "More than one company exists; state which company this fee plan "
            "belongs to")
    return companies[0]["name"]


def _fee_plan_result(structure, level, academic_year, replayed=False):
    rows = structure.get("components") or []
    return {
        "fee_structure": structure.name,
        "level": level,
        "academic_year": academic_year,
        "components": [{"category": row.get("fees_category"),
                        "amount": float(row.get("amount") or 0)} for row in rows],
        "total": sum(float(row.get("amount") or 0) for row in rows),
        "company": structure.get("company"),
        "replayed": replayed,
    }


def _family_of(code):
    return frappe.db.get_value(LEVEL, {"code": code}, "family")


def _next_of(code):
    return frappe.db.get_value(LEVEL, {"code": code}, "next_level")


def _program_result(doc, extra=None):
    result = {
        "name": doc.name, "code": doc.code, "title": doc.title,
        "status": doc.status,
    }
    if extra:
        result.update(extra)
    return result


def _level_result(doc, extra=None):
    current = rules.resolve_duration(
        [row.as_dict() for row in (doc.get("durations") or [])], frappe.utils.today())
    result = {
        "name": doc.name, "code": doc.code, "title": doc.title,
        "status": doc.status, "family": doc.family,
        "native_program": doc.native_program,
        "duration": rules.duration_label(current),
        "duration_effective_from": (str(current.get("effective_from")) if current else ""),
    }
    if extra:
        result.update(extra)
    return result


def _discount_rule_doc(code, for_update=False):
    name = frappe.db.get_value(DISCOUNT_RULE, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown discount rule: {code}")
    return frappe.get_doc(DISCOUNT_RULE, name, for_update=for_update)


@frappe.whitelist(methods=["POST"])
def create_discount_rule(request_key, code, title, discount_percentage,
                         precedence=1, fee_category="", program="", description=""):
    """Define a centralized discount rule under OD-CP-1 Policy A.

    Single discount per charge line; explicit configured precedence resolves
    competing rules. Zero or one discount only; never stacks.
    """
    def work(actor):
        try:
            validate_request_key(request_key)
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Discount rule title")
            clean_percent = rules.validate_discount_percentage(discount_percentage)
            clean_precedence = rules.validate_precedence(precedence)
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc

        if frappe.db.exists(DISCOUNT_RULE, clean_code):
            raise frappe.ValidationError(f"Discount rule {clean_code} already exists")

        clean_category = ""
        if fee_category:
            clean_category = rules.validate_title(fee_category, "Fee category")
            if not frappe.db.exists(FEE_CATEGORY, clean_category):
                raise frappe.ValidationError(
                    f"Fee type {clean_category} does not exist yet; define it first")

        clean_program = ""
        if program:
            clean_program = rules.validate_code(program)
            if not frappe.db.exists(PROGRAM, clean_program):
                raise frappe.ValidationError(
                    f"Program {clean_program} does not exist yet; define it first")

        doc = frappe.get_doc({
            "doctype": DISCOUNT_RULE, "code": clean_code, "title": clean_title,
            "discount_percentage": clean_percent, "precedence": clean_precedence,
            "status": "Active", "fee_category": clean_category or None,
            "program": clean_program or None, "description": clean_description,
        })
        doc.insert(ignore_permissions=True)
        result = {
            "name": doc.name, "code": doc.code, "title": doc.title,
            "discount_percentage": float(doc.discount_percentage),
            "precedence": int(doc.precedence), "status": doc.status,
            "fee_category": doc.fee_category or "",
            "program": doc.program or "",
        }
        return result, {
            "target": doc.name,
            "before_hash": configuration_audit.latest_after_hash(doc.name),
            "after_hash": digest(result),
        }

    return configuration_audit.execute(
        "create_discount_rule", request_key,
        {"code": code, "title": title,
         "discount_percentage": discount_percentage, "precedence": precedence,
         "fee_category": fee_category, "program": program,
         "description": description}, work)


@frappe.whitelist(methods=["POST"])
def set_discount_rule_status(request_key, code, active):
    """Deactivate (retire) or reactivate a discount rule."""
    def work(actor):
        try:
            validate_request_key(request_key)
            clean_code = rules.validate_code(code)
            flag = _as_bool(active, "active")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc

        doc = _discount_rule_doc(clean_code, for_update=True)
        doc.status = "Active" if flag else "Retired"
        doc.save(ignore_permissions=True)
        result = {
            "name": doc.name, "code": doc.code, "title": doc.title,
            "status": doc.status,
        }
        return result, {
            "target": doc.name,
            "before_hash": configuration_audit.latest_after_hash(doc.name),
            "after_hash": digest(result),
        }

    return configuration_audit.execute(
        "set_discount_rule_status", request_key,
        {"code": code, "active": active}, work)


def _assessment_policy_doc(code, for_update=False):
    name = frappe.db.get_value(ASSESSMENT_POLICY, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown assessment policy: {code}")
    return frappe.get_doc(ASSESSMENT_POLICY, name, for_update=for_update)


def _carried_facets(versions):
    """The facet payload the next version row inherits unchanged.

    Every version row is full policy state: a command that sets one facet
    (or the grading-scale link) copies the other facets forward from the
    latest version, so history keeps resolving against complete rows and
    no facet is ever lost by appending an unrelated change.
    """
    latest = configuration_rules.latest_version(versions or [])
    carried = {}
    for facet in rules.ASSESSMENT_FACETS:
        carried[facet] = (latest.get(facet) or "") if latest else ""
    return carried


def _assessment_policy_result(doc, extra=None):
    versions = [row.as_dict() for row in (doc.get("versions") or [])]
    governing = configuration_rules.resolve_governing(
        versions, frappe.utils.today())
    result = {
        "name": doc.name, "code": doc.code, "title": doc.title,
        "status": doc.status, "family": doc.family,
        "version_count": len(versions),
        "governing_effective_from": (
            str(governing.get("effective_from")) if governing else ""),
    }
    if extra:
        result.update(extra)
    return result


@frappe.whitelist(methods=["POST"])
def create_assessment_policy(request_key, family, code, title,
                             description=""):
    """Define an assessment policy shell (D1 reference structure).

    Creates the policy with NO versions: readiness stays ``incomplete``
    until the Course Owner appends the first effective-dated version. The
    shell carries no grading values — thresholds arrive only through
    versions, and only after owner decision D1 is made.
    """
    def work(actor):
        try:
            clean_family = rules.validate_code(family)
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Assessment policy title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        family_doc = _family_doc(clean_family, for_update=True)
        if family_doc.status != "Active":
            raise frappe.ValidationError(
                f"Program {clean_family} is retired; reactivate it before "
                "adding an assessment policy")
        if frappe.db.exists(ASSESSMENT_POLICY, clean_code):
            raise frappe.ValidationError(
                f"Assessment policy {clean_code} already exists")
        doc = frappe.get_doc({
            "doctype": ASSESSMENT_POLICY, "family": family_doc.name,
            "code": clean_code, "title": clean_title, "status": "Active",
            "description": clean_description,
        })
        doc.insert(ignore_permissions=True)
        return _assessment_policy_result(doc), {
            "target": doc.name, "before_hash": "",
            "after_hash": configuration_rules.snapshot_digest([]),
        }

    payload = {"family": family, "code": code, "title": title,
               "description": description}
    return configuration_audit.execute(
        "create_assessment_policy", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_assessment_policy_version(request_key, policy, effective_from,
                                  reason, grading_scale=""):
    """Append an effective-dated assessment policy version (D1 configuration).

    The version carries the reusable native Grading Scale LINK plus the
    owned facet structures (components, weights, pass rules, rubrics,
    progression, retakes, level mapping), each defined later by the Course
    Owner through the facet commands. Native per-group Assessment Plans
    are scheduled instances, not reusable policy, and are never referenced
    here (A-D1-1). Facets carry forward unchanged; a change reason is
    mandatory; backdated or same-day versions are refused.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            clean_scale = (rules.validate_title(grading_scale, "Grading scale")
                           if grading_scale else "")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _assessment_policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Assessment policy {clean_code} is retired; reactivate it "
                "before adding a version")
        family_status = frappe.db.get_value(PROGRAM, doc.family, "status")
        if family_status != "Active":
            raise frappe.ValidationError(
                f"The program family {doc.family} is retired; reactivate it "
                "before adding a version")
        if clean_scale and not frappe.db.exists(GRADING_SCALE, clean_scale):
            raise frappe.ValidationError(
                f"Grading scale {clean_scale} does not exist; define it "
                "natively first")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="assessment policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        carried = _carried_facets(versions)
        before = configuration_audit.latest_after_hash(doc.name)
        row = {"effective_from": clean_from,
               "grading_scale": clean_scale or None,
               "reason": clean_reason, "set_by": actor,
               "set_on": frappe.utils.now_datetime()}
        row.update(carried)
        doc.append("versions", row)
        if current:
            # Close the superseded version; never rewrite its meaning, only
            # record the date it stopped governing new activity.
            for row in doc.get("versions") or []:
                if (str(row.get("effective_from")) == str(current.get("effective_from"))
                        and not row.get("superseded_on")):
                    row.superseded_on = clean_from
                    break
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("versions") or [])])
        return _assessment_policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "effective_from": effective_from,
               "reason": reason, "grading_scale": grading_scale}
    return configuration_audit.execute(
        "set_assessment_policy_version", request_key, payload, work)


def _append_facet_version(doc, actor, clean_from, clean_reason, scale,
                          carried):
    """Append one facet-carrying version row and close the superseded one.

    Every row is full state: the caller passes the carried facets with its
    own facet already replaced, plus the (carried) grading-scale link.
    """
    row = {"effective_from": clean_from, "grading_scale": scale,
           "reason": clean_reason, "set_by": actor,
           "set_on": frappe.utils.now_datetime()}
    row.update(carried)
    doc.append("versions", row)


def _close_superseded_facet(doc, current, clean_from):
    if current:
        # Close the superseded version; never rewrite its meaning, only
        # record the date it stopped governing new activity.
        for row in doc.get("versions") or []:
            if (str(row.get("effective_from")) == str(current.get("effective_from"))
                    and not row.get("superseded_on")):
                row.superseded_on = clean_from
                break


def _grade_codes_of_scale(scale):
    """Grade codes on a native scale, or None when no scale is linked."""
    if not scale:
        return None
    return [str(row.get("grade_code") or "")
            for row in frappe.db.get_all(
                GRADING_INTERVAL, filters={"parent": scale},
                fields=["grade_code"])]


def _refuse_unknown_grade_codes(pass_rules, codes, scale):
    found = []
    for entry in (pass_rules.get("components") or []):
        minimum = entry.get("minimum") or {}
        if minimum.get("kind") == "grade":
            found.append(minimum.get("value"))
    overall = pass_rules.get("overall") or {}
    if overall.get("kind") == "grade":
        found.append(overall.get("value"))
    for code in found:
        if code not in codes:
            raise frappe.ValidationError(
                f"Grade code {code!r} is not on grading scale {scale}; "
                "define it on the scale first")


@frappe.whitelist(methods=["POST"])
def set_assessment_components(request_key, policy, effective_from, reason,
                              components):
    """Define the owned assessment components (D1 configuration plane).

    Components are the assessed parts (code, title, maximum score, and an
    optional native Assessment Criteria link each), supplied as JSON. A new
    version carries every other facet forward unchanged; an explicit empty
    list withdraws the facet. Weights, pass rules and rubrics reference
    these codes and therefore need components defined first.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            canonical = rules.canonical_facet("components", components)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _assessment_policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Assessment policy {clean_code} is retired; reactivate it "
                "before changing its facets")
        family_status = frappe.db.get_value(PROGRAM, doc.family, "status")
        if family_status != "Active":
            raise frappe.ValidationError(
                f"The program family {doc.family} is retired; reactivate it "
                "before changing its facets")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="assessment policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        for entry in rules.parse_facet("components", canonical) or []:
            criteria = entry.get("criteria") or ""
            if criteria and not frappe.db.exists(ASSESSMENT_CRITERIA,
                                                 criteria):
                raise frappe.ValidationError(
                    f"Assessment criteria {criteria} does not exist; define "
                    "it natively first")
        carried = _carried_facets(versions)
        carried["components"] = canonical
        before = configuration_audit.latest_after_hash(doc.name)
        _append_facet_version(
            doc, actor, clean_from, clean_reason,
            (current.get("grading_scale") if current else None), carried)
        _close_superseded_facet(doc, current, clean_from)
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("versions") or [])])
        return _assessment_policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "effective_from": effective_from,
               "reason": reason, "components": components}
    return configuration_audit.execute(
        "set_assessment_components", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_assessment_weights(request_key, policy, effective_from, reason,
                           weights):
    """Define the owned component weights (D1 configuration plane).

    Each entry pairs a defined component code with a non-negative number,
    supplied as JSON. These owned numbers are the only weighting the
    configuration plane recognizes: native Course weight columns are never
    read (A-D1-2), and combination semantics arrive with a future owner
    rule. An explicit empty list withdraws the facet.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _assessment_policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Assessment policy {clean_code} is retired; reactivate it "
                "before changing its facets")
        family_status = frappe.db.get_value(PROGRAM, doc.family, "status")
        if family_status != "Active":
            raise frappe.ValidationError(
                f"The program family {doc.family} is retired; reactivate it "
                "before changing its facets")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="assessment policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        carried = _carried_facets(versions)
        try:
            canonical = rules.canonical_facet(
                "weights", weights,
                rules.parse_facet("components",
                                  carried.get("components")))
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        carried["weights"] = canonical
        before = configuration_audit.latest_after_hash(doc.name)
        _append_facet_version(
            doc, actor, clean_from, clean_reason,
            (current.get("grading_scale") if current else None), carried)
        _close_superseded_facet(doc, current, clean_from)
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("versions") or [])])
        return _assessment_policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "effective_from": effective_from,
               "reason": reason, "weights": weights}
    return configuration_audit.execute(
        "set_assessment_weights", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_assessment_pass_rules(request_key, policy, effective_from, reason,
                              pass_rules):
    """Define the owned pass and cutoff rules (D1 configuration plane).

    Per-component and overall minima, each either a percentage or a grade
    code, supplied as JSON. Grade codes resolve against the version's
    linked grading scale when one is linked. No native pass or fail
    concept exists; every cutoff here is owner-entered, and at least one
    minimum must be defined. An explicit empty object withdraws the facet.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _assessment_policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Assessment policy {clean_code} is retired; reactivate it "
                "before changing its facets")
        family_status = frappe.db.get_value(PROGRAM, doc.family, "status")
        if family_status != "Active":
            raise frappe.ValidationError(
                f"The program family {doc.family} is retired; reactivate it "
                "before changing its facets")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="assessment policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        carried = _carried_facets(versions)
        try:
            canonical = rules.canonical_facet(
                "pass_rules", pass_rules,
                rules.parse_facet("components",
                                  carried.get("components")))
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        scale = current.get("grading_scale") if current else ""
        codes = _grade_codes_of_scale(scale)
        if codes is not None:
            _refuse_unknown_grade_codes(
                rules.parse_facet("pass_rules", canonical) or {}, codes,
                scale)
        carried["pass_rules"] = canonical
        before = configuration_audit.latest_after_hash(doc.name)
        _append_facet_version(doc, actor, clean_from, clean_reason,
                              scale or None, carried)
        _close_superseded_facet(doc, current, clean_from)
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("versions") or [])])
        return _assessment_policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "effective_from": effective_from,
               "reason": reason, "pass_rules": pass_rules}
    return configuration_audit.execute(
        "set_assessment_pass_rules", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_assessment_rubrics(request_key, policy, effective_from, reason,
                           rubrics):
    """Define the owned rubric requirements (D1 configuration plane).

    Each rubric names its required evidence and optional rating levels,
    and may attach to a defined component, supplied as JSON. This is the
    requirements structure only: score conversion is a future owner rule
    and is deliberately not represented here. An explicit empty list
    withdraws the facet.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _assessment_policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Assessment policy {clean_code} is retired; reactivate it "
                "before changing its facets")
        family_status = frappe.db.get_value(PROGRAM, doc.family, "status")
        if family_status != "Active":
            raise frappe.ValidationError(
                f"The program family {doc.family} is retired; reactivate it "
                "before changing its facets")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="assessment policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        carried = _carried_facets(versions)
        try:
            canonical = rules.canonical_facet(
                "rubrics", rubrics,
                rules.parse_facet("components",
                                  carried.get("components")))
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        carried["rubrics"] = canonical
        before = configuration_audit.latest_after_hash(doc.name)
        _append_facet_version(
            doc, actor, clean_from, clean_reason,
            (current.get("grading_scale") if current else None), carried)
        _close_superseded_facet(doc, current, clean_from)
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("versions") or [])])
        return _assessment_policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "effective_from": effective_from,
               "reason": reason, "rubrics": rubrics}
    return configuration_audit.execute(
        "set_assessment_rubrics", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_assessment_progression(request_key, policy, effective_from, reason,
                               progression):
    """Define the owned progression rules (D1 configuration plane).

    Required evidence (assessment passes under named policies, an
    attendance minimum, human approvals) and the target level — either
    the chain's next level or an explicit same-family level code —
    supplied as JSON. A progression decision recommends; it never enrolls
    by itself. An explicit empty object withdraws the facet.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            canonical = rules.canonical_facet("progression", progression)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _assessment_policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Assessment policy {clean_code} is retired; reactivate it "
                "before changing its facets")
        family_status = frappe.db.get_value(PROGRAM, doc.family, "status")
        if family_status != "Active":
            raise frappe.ValidationError(
                f"The program family {doc.family} is retired; reactivate it "
                "before changing its facets")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="assessment policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        parsed = rules.parse_facet("progression", canonical) or {}
        target = (parsed.get("target") or "")
        if target and target != rules.PROGRESSION_NEXT:
            level = _level_doc(target)
            if level.family != doc.family:
                raise frappe.ValidationError(
                    f"Progression target {target} is outside the {doc.family} "
                    "program family")
        for entry in parsed.get("requires") or []:
            if entry.get("kind") == "assessment_pass":
                name = frappe.db.get_value(
                    ASSESSMENT_POLICY, {"code": entry.get("policy")}, "name")
                if not name:
                    raise frappe.ValidationError(
                        f"Unknown assessment policy: {entry.get('policy')}")
            elif entry.get("kind") == "approval":
                if not frappe.db.exists("Role", entry.get("role")):
                    raise frappe.ValidationError(
                        f"Unknown role: {entry.get('role')}")
        carried = _carried_facets(versions)
        carried["progression"] = canonical
        before = configuration_audit.latest_after_hash(doc.name)
        _append_facet_version(
            doc, actor, clean_from, clean_reason,
            (current.get("grading_scale") if current else None), carried)
        _close_superseded_facet(doc, current, clean_from)
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("versions") or [])])
        return _assessment_policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "effective_from": effective_from,
               "reason": reason, "progression": progression}
    return configuration_audit.execute(
        "set_assessment_progression", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_assessment_retakes(request_key, policy, effective_from, reason,
                           retakes):
    """Define the owned retake rules (D1 configuration plane).

    Attempt limit, wait, scope (full or partial reassessment) and which
    attempt governs, supplied as JSON with every key explicit — an empty
    attempt limit means unlimited only when written as an explicit null.
    Prior attempts are always preserved. An explicit empty object
    withdraws the facet.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            canonical = rules.canonical_facet("retakes", retakes)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _assessment_policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Assessment policy {clean_code} is retired; reactivate it "
                "before changing its facets")
        family_status = frappe.db.get_value(PROGRAM, doc.family, "status")
        if family_status != "Active":
            raise frappe.ValidationError(
                f"The program family {doc.family} is retired; reactivate it "
                "before changing its facets")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="assessment policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        carried = _carried_facets(versions)
        carried["retakes"] = canonical
        before = configuration_audit.latest_after_hash(doc.name)
        _append_facet_version(
            doc, actor, clean_from, clean_reason,
            (current.get("grading_scale") if current else None), carried)
        _close_superseded_facet(doc, current, clean_from)
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("versions") or [])])
        return _assessment_policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "effective_from": effective_from,
               "reason": reason, "retakes": retakes}
    return configuration_audit.execute(
        "set_assessment_retakes", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_assessment_mapping(request_key, policy, effective_from, reason,
                           mapping):
    """Define which levels the policy governs (D1 configuration plane).

    The policy is configured per program family but assessments run per
    level, so the mapping names the governed level codes explicitly as
    JSON. Every level must exist in the policy's own family; an empty
    list governs nothing. An explicit empty object withdraws the facet.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            canonical = rules.canonical_facet("level_mapping", mapping)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _assessment_policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Assessment policy {clean_code} is retired; reactivate it "
                "before changing its facets")
        family_status = frappe.db.get_value(PROGRAM, doc.family, "status")
        if family_status != "Active":
            raise frappe.ValidationError(
                f"The program family {doc.family} is retired; reactivate it "
                "before changing its facets")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="assessment policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        parsed = rules.parse_facet("level_mapping", canonical) or {}
        for code in parsed.get("levels") or []:
            level = _level_doc(code)
            if level.family != doc.family:
                raise frappe.ValidationError(
                    f"Level {code} is outside the {doc.family} program family")
        carried = _carried_facets(versions)
        carried["level_mapping"] = canonical
        before = configuration_audit.latest_after_hash(doc.name)
        _append_facet_version(
            doc, actor, clean_from, clean_reason,
            (current.get("grading_scale") if current else None), carried)
        _close_superseded_facet(doc, current, clean_from)
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("versions") or [])])
        return _assessment_policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "effective_from": effective_from,
               "reason": reason, "mapping": mapping}
    return configuration_audit.execute(
        "set_assessment_mapping", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_assessment_policy_status(request_key, policy, active):
    """Deactivate (retire) or reactivate an assessment policy.

    No live-use refusal exists yet: no consumer slice reads these policies
    until A06 lands, and inventing a fake dependency check would be worse
    than the honest gap. A06 extends this command with the real
    in-use refusal (recorded in the Phase 1 boundary).
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            flag = _as_bool(active, "active")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _assessment_policy_doc(clean_code, for_update=True)
        if flag:
            family_status = frappe.db.get_value(PROGRAM, doc.family, "status")
            if family_status != "Active":
                raise frappe.ValidationError(
                    f"The program family {doc.family} is retired; reactivate "
                    "it first")
        before = configuration_audit.latest_after_hash(doc.name)
        doc.status = "Active" if flag else "Retired"
        doc.save(ignore_permissions=True)
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        after = digest(["status", doc.status,
                        configuration_rules.snapshot_digest(versions)])
        return _assessment_policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "active": active}
    return configuration_audit.execute(
        "set_assessment_policy_status", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def validate_assessment_policy(request_key, policy):
    """Validate an assessment policy's structure and record the evidence.

    Structural checks only: active policy and family, versions present
    and unambiguous, every row's facets well-formed and coherent, and
    every referenced master (grading scale, criteria, levels, policies,
    roles) still resolving. Facet presence is reported as desk facts, not
    judged here — no completeness gate is invented. Success writes a
    validation audit event over the exact version snapshot; any later
    version change stales it automatically, returning readiness to
    ``configured``.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _assessment_policy_doc(clean_code)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Assessment policy {clean_code} is retired; only active "
                "policies validate")
        family_status = frappe.db.get_value(PROGRAM, doc.family, "status")
        if family_status != "Active":
            raise frappe.ValidationError(
                f"The program family {doc.family} is retired; reactivate it "
                "before validating")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        if not versions:
            raise frappe.ValidationError(
                f"Assessment policy {clean_code} has no versions yet; add "
                "the first version before validating")
        try:
            configuration_rules.assert_no_ambiguous_versions(
                versions, what="assessment policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        for row in versions:
            scale = row.get("grading_scale") or ""
            if scale and not frappe.db.exists(GRADING_SCALE, scale):
                raise frappe.ValidationError(
                    f"Grading scale {scale} no longer exists; repair the "
                    "policy version before validating")
            try:
                facets = rules.validate_policy_facets({
                    facet: row.get(facet)
                    for facet in rules.ASSESSMENT_FACETS})
            except ValueError as exc:
                raise frappe.ValidationError(str(exc)) from exc
            for entry in (facets.get("components") or []):
                criteria = entry.get("criteria") or ""
                if criteria and not frappe.db.exists(ASSESSMENT_CRITERIA,
                                                     criteria):
                    raise frappe.ValidationError(
                        f"Assessment criteria {criteria} no longer exists; "
                        "repair the policy version before validating")
            codes = _grade_codes_of_scale(scale)
            if codes is not None and "pass_rules" in facets:
                _refuse_unknown_grade_codes(facets["pass_rules"], codes,
                                            scale)
            for code in (facets.get("level_mapping") or {}).get("levels",
                                                                []):
                level = _level_doc(code)
                if level.family != doc.family:
                    raise frappe.ValidationError(
                        f"Level {code} is outside the {doc.family} program "
                        "family; repair the policy version before validating")
            progression = facets.get("progression") or {}
            target = progression.get("target") or ""
            if target and target != rules.PROGRESSION_NEXT:
                level = _level_doc(target)
                if level.family != doc.family:
                    raise frappe.ValidationError(
                        f"Progression target {target} is outside the "
                        f"{doc.family} program family; repair the policy "
                        "version before validating")
            for entry in progression.get("requires") or []:
                if entry.get("kind") == "assessment_pass":
                    name = frappe.db.get_value(
                        ASSESSMENT_POLICY, {"code": entry.get("policy")},
                        "name")
                    if not name:
                        raise frappe.ValidationError(
                            f"Assessment policy {entry.get('policy')} no "
                            "longer exists; repair the policy version "
                            "before validating")
                elif entry.get("kind") == "approval":
                    if not frappe.db.exists("Role", entry.get("role")):
                        raise frappe.ValidationError(
                            f"Role {entry.get('role')} no longer exists; "
                            "repair the policy version before validating")
        before = configuration_audit.latest_after_hash(doc.name)
        after = configuration_rules.snapshot_digest(versions)
        readiness = configuration_rules.compute_readiness(
            status=doc.status, versions=versions,
            validations=[{"after_hash": after}],
            today=frappe.utils.today(), what="assessment policy")
        return _assessment_policy_result(doc, extra={"readiness": readiness}), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy}
    return configuration_audit.execute(
        "validate_assessment_policy", request_key, payload, work)


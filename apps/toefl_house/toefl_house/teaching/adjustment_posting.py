"""S13 orphan adjustments (OD-NEW-08): effective-dated owner control over
whether contract adjustments post in periods with no assignments
(S7/S8/S9/S10/S11/S12 singleton mechanics).

Payroll resolves instructors from overlapping assignments, so a
contract adjustment due in a period its instructor teaches nothing in
is an orphan: historically it silently never posted. When the owner
sets orphan posting to ``post``, the calculation also visits
adjustment-only instructors and their due adjustments post through
the covering contract exactly once; ``skip`` keeps the historical
behavior but REPORTS the skipped orphans instead of dropping them
silently. Fixed-salary contracts never post adjustments under either
choice — their payroll runs through the native salary structure path.

Two deliberate boundaries. First, orphan posting follows the covering
contract: the exactly-one-cover rule and the contract-row locks that
keep payroll correct (BUG-PAY-01) apply to orphan instructors
unchanged, so an adjustment due outside its own contract's window is
misfiled input and stays unposted. Second, the policy gates posting
only: skipped orphans are reported, never paid later, because a later
period's due window cannot reach back into this one's effective dates.

Fail-closed by construction: with no policy row, a retired policy, or
no effective version, the calculation refuses — the owner opts in by
appending a version, never by default.
"""

import frappe

from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest

POLICY = "TH Adjustment Posting Policy"
CONTRACT = "TH Instructor Contract"
ADJUSTMENT = "TH Contract Adjustment"

POST = "post"
SKIP = "skip"
ORPHAN_CHOICES = (POST, SKIP)


def validate_orphan_posting(value):
    """Shape-check the orphan-posting vocabulary (command + controller).

    ``post`` pays orphan adjustments through the covering contract;
    ``skip`` reports them and pays nothing. The owner picks one per
    version; fixed-salary contracts never post adjustments under either.
    """
    if value not in ORPHAN_CHOICES:
        raise ValueError(
            "Orphan adjustment posting must be one of: "
            + ", ".join(ORPHAN_CHOICES))
    return value


def collect_orphan_contracts(start, end, assigned_instructors):
    """Map due-adjustment parents with no overlapping assignment.

    Returns ``{contract: {"instructor": ..., "adjustments": [names]}}``
    for non-fixed contracts carrying adjustments due inside the window
    whose instructor holds no overlapping assignment. A pure read used
    inside the calculation work() closure; the caller posts or reports
    per the governing terms.
    """
    due = frappe.db.get_all(
        ADJUSTMENT, filters={"effective_date": ["between", [start, end]]},
        fields=["name", "parent"])
    orphans = {}
    for parent in sorted({row["parent"] for row in due}):
        info = frappe.db.get_value(
            CONTRACT, parent, ["instructor", "compensation_model"],
            as_dict=True)
        if not info or info.compensation_model == "Fixed Salary":
            continue
        if info.instructor in (assigned_instructors or ()):
            continue
        orphans[parent] = {
            "instructor": info.instructor,
            "adjustments": sorted(row["name"] for row in due
                                  if row["parent"] == parent),
        }
    return orphans


def _policy_doc(code, for_update=False):
    name = frappe.db.get_value(POLICY, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown adjustment posting policy: {code}")
    return frappe.get_doc(POLICY, name, for_update=for_update)


def _as_bool(value, what):
    if isinstance(value, str) and value.strip().lower() in ("1", "true", "yes"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("0", "false", "no"):
        return False
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise ValueError(f"{what} must be true or false")


def _policy_result(doc, extra=None):
    versions = [row.as_dict() for row in (doc.get("versions") or [])]
    governing = configuration_rules.resolve_governing(
        versions, frappe.utils.today())
    result = {
        "name": doc.name, "code": doc.code, "title": doc.title,
        "status": doc.status, "version_count": len(versions),
        "governing_effective_from": (
            str(governing.get("effective_from")) if governing else ""),
        "governing_orphan_posting": (
            (governing.get("orphan_posting") or "") if governing else ""),
    }
    if extra:
        result.update(extra)
    return result


def governing_posting_terms(on_date=None):
    """Read-only resolver: governing terms, or {} when unconfigured.

    No receipt: a pure read used inside the calculation work() closure.
    Fail-closed in three ways — no policy row, retired policy, no
    effective version — and every one means payroll refuses.
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
    return {
        "effective_from": str(governing.get("effective_from") or ""),
        "orphan_posting": governing.get("orphan_posting") or "",
    }


@frappe.whitelist(methods=["POST"])
def create_adjustment_posting_policy(request_key, code, title, description=""):
    """Define the adjustment posting policy shell (OD-NEW-08 mechanism).

    Creates the single policy row with NO versions: payroll calculation
    stays denied until the Course Owner appends the first
    effective-dated version. The shell carries no terms — the owner's
    choice of post vs skip arrives only through versions.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Adjustment posting policy title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.get_all(POLICY, fields=["name"], limit=1):
            raise frappe.ValidationError(
                "An adjustment posting policy already exists; version it instead")
        if frappe.db.exists(POLICY, clean_code):
            raise frappe.ValidationError(
                f"Adjustment posting policy {clean_code} already exists")
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
        "create_adjustment_posting_policy", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_adjustment_posting_version(request_key, policy, effective_from, reason,
                                   orphan_posting):
    """Append an effective-dated adjustment posting policy version.

    The version enacts one orphan-posting choice from
    ``effective_from``; a change reason is mandatory; backdated or
    same-day versions are refused. The superseded version is closed,
    never rewritten.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            clean_orphans = validate_orphan_posting(orphan_posting)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Adjustment posting policy {clean_code} is retired; "
                "reactivate it before adding a version")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="adjustment posting version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.append("versions", {
            "effective_from": clean_from, "orphan_posting": clean_orphans,
            "reason": clean_reason, "set_by": actor,
            "set_on": frappe.utils.now_datetime()})
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
        return _policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "effective_from": effective_from,
               "reason": reason, "orphan_posting": orphan_posting}
    return configuration_audit.execute(
        "set_adjustment_posting_version", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_adjustment_posting_status(request_key, policy, active):
    """Deactivate (retire) or reactivate the adjustment posting policy.

    Retiring is the off-switch: with no active policy payroll
    calculation refuses again. Earlier postings keep their recorded
    receipts — the policy gates calculation only, and history is never
    rewritten by a later switch.
    """
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
        "set_adjustment_posting_status", request_key, payload, work)

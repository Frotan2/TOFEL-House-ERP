"""Pure foundation rules for versioned TOEFL House configuration.

Frappe-free: the generic version/readiness/audit primitives every
configuration domain shares, testable offline (tests/configuration).
Domain rule modules (``toefl_house.academic.rules``) delegate their
version primitives here; domain VALUE validation stays in the domain
modules, and native authorities are never duplicated.

Foundation invariants (the approved configuration architecture):

1. Versions are append-only and monotone by effective date, so every date
   resolves to exactly one governing version and history keeps the
   version it was created under.
2. Ambiguous governing versions fail closed: strict resolution raises
   instead of guessing.
3. Readiness is COMPUTED from records, never toggled: incomplete ->
   configured -> validated -> effective, with retired as the terminal
   state. ``superseded`` is a version-row state, never a policy state.
4. Validation evidence is a hash-chained audit event over the exact
   version snapshot; any later version change stales it automatically.
5. Authorities are declared here. Only bound authorities may act, and the
   custody authority is never bound to a Frappe role: ceremonies happen
   outside Frappe by the separate-control principle.
"""
import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar

# --- Configuration Readiness (computed, never toggled) --------------------
READINESS_INCOMPLETE = "incomplete"
READINESS_CONFIGURED = "configured"
READINESS_VALIDATED = "validated"
READINESS_EFFECTIVE = "effective"
READINESS_RETIRED = "retired"
READINESS_STATES = (
    READINESS_INCOMPLETE,
    READINESS_CONFIGURED,
    READINESS_VALIDATED,
    READINESS_EFFECTIVE,
    READINESS_RETIRED,
)

# --- Authorities -----------------------------------------------------------
# business_policy: the Course Owner's business values (the only authority
# Phase 1 binds — the only one Phase 1 exercises).
# operations: technical operational configuration (unbound until a later
# phase binds it explicitly; any use refuses fail-closed).
# custody: real custody ceremonies. NEVER bound to a Frappe role: the
# custodian/operator/recovery roles live outside Frappe (tools/foundation/
# key_custody.py is stdlib-only by design), and ceremony results enter the
# system exclusively as signed evidence reports, never as settings.
AUTHORITIES = {
    "business_policy": ("Course Owner",),
    "operations": (),
    "custody": (),
}
NEVER_BOUND = ("custody",)


def authority_roles(authority):
    """The Frappe roles bound to an authority (empty tuple when unbound)."""
    if authority not in AUTHORITIES:
        raise ValueError(f"Unknown configuration authority: {authority}")
    return AUTHORITIES[authority]


def require_bound_authority(authority):
    """The bound roles for an authority, or a refusal.

    Unbound authorities (and the custody authority, which must never bind)
    raise: no command may act without an explicitly bound authority.
    """
    roles = authority_roles(authority)
    if authority in NEVER_BOUND:
        raise ValueError(
            "The custody authority never acts through Frappe: ceremonies "
            "happen outside the application and enter only as evidence")
    if not roles:
        raise ValueError(
            f"The {authority} authority is not bound to any role; "
            "no command may act under it")
    return roles


# --- Mandatory change reason -----------------------------------------------
# Every policy-version write carries a human reason: who/what/when comes
# from native Version + the version row's set_by/set_on, and the reason
# explains WHY. Empty reasons are refused, never defaulted.
CHANGE_REASON_MAX = 500


def validate_change_reason(value, what="Change reason"):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} is required: say why this change is made")
    reason = value.strip()
    if len(reason) > CHANGE_REASON_MAX:
        raise ValueError(
            f"{what} must be at most {CHANGE_REASON_MAX} characters")
    return reason


# --- Generic effective-dated versions --------------------------------------
def normalize_versions(rows, date_field="effective_from"):
    """Order version rows by effective date (input order breaks ties)."""
    return sorted(list(rows or []),
                  key=lambda row: str(row.get(date_field) or ""))


def latest_version(rows, date_field="effective_from"):
    """The most recently effective version row, or None."""
    existing = normalize_versions(rows, date_field)
    return existing[-1] if existing else None


def check_appends(rows, new_effective_from, what="version",
                  date_field="effective_from"):
    """The monotone-version rule: a new version must start strictly after
    the latest existing one, so every date resolves to exactly one version.
    Backdated and same-day versions are refused (fail closed)."""
    existing = normalize_versions(rows, date_field)
    if existing:
        latest = existing[-1]
        if str(new_effective_from) <= str(latest.get(date_field) or ""):
            raise ValueError(
                f"A new {what} must start after the latest version "
                f"({latest.get(date_field)}); backdated or same-day versions "
                "would make history ambiguous")


def assert_no_ambiguous_versions(rows, what="version",
                                 date_field="effective_from"):
    """Two versions sharing one effective date would make 'which version
    governs this date' unanswerable. Controllers prevent this; resolution
    and validation re-assert it defensively and fail closed."""
    effective = [str(row.get(date_field) or "") for row in (rows or [])]
    if len(effective) != len(set(effective)):
        raise ValueError(
            f"Two {what}s share one effective date; history is ambiguous "
            "until the configuration is repaired")


def resolve_governing(rows, on_date, date_field="effective_from"):
    """The version governing ``on_date``: the latest version whose effective
    date is on or before that date. None when no version is effective yet —
    callers must surface that, never guess."""
    governing = None
    for row in rows or []:
        effective = str(row.get(date_field) or "")
        if not effective or str(on_date) < effective:
            continue
        if governing is None or effective >= str(governing.get(date_field) or ""):
            governing = row
    return governing


def resolve_governing_strict(rows, on_date, what="version",
                             date_field="effective_from"):
    """Strict governing-version resolution: ambiguity fails closed.

    Returns None only when genuinely nothing is effective yet. Raises when
    two versions claim the same governing date.
    """
    applicable = [row for row in (rows or [])
                  if str(row.get(date_field) or "")
                  and str(row.get(date_field) or "") <= str(on_date)]
    if not applicable:
        return None
    best = max(str(row.get(date_field) or "") for row in applicable)
    winners = [row for row in applicable
               if str(row.get(date_field) or "") == best]
    if len(winners) > 1:
        raise ValueError(
            f"Two {what}s claim {best}; history is ambiguous until the "
            "configuration is repaired")
    return winners[0]


def version_state(row, on_date, date_field="effective_from"):
    """One version row's state on a date: superseded, scheduled, effective."""
    if (row or {}).get("superseded_on"):
        return "superseded"
    effective = str((row or {}).get(date_field) or "")
    if not effective or str(on_date) < effective:
        return "scheduled"
    return "effective"


# --- Version snapshots (validation evidence) --------------------------------
# Identity/bookkeeping columns are excluded so a rename or idx shift can
# never stale a validation; every meaning column (including the audit
# columns set_by/set_on/superseded_on) is included, so tampering with any
# of them stales the validation in the fail-closed direction. Unset reads
# as unset regardless of None-vs-empty-string representation.
SNAPSHOT_EXCLUDE = ("name", "idx", "parent", "parenttype", "parentfield",
                    "owner", "creation", "modified", "modified_by",
                    "docstatus")


def snapshot_digest(rows, exclude=SNAPSHOT_EXCLUDE):
    """Stable digest of a version set: the fingerprint validation evidence
    commits to. Row order, key order and None/empty representation do not
    affect it; any meaning change does."""
    normalized = []
    for row in rows or []:
        normalized.append({
            key: str(value)
            for key, value in sorted((row or {}).items())
            if key not in exclude and value is not None and str(value) != ""
        })
    canonical = json.dumps(sorted(normalized, key=lambda item: json.dumps(
        item, sort_keys=True, separators=(",", ":"), ensure_ascii=True)),
        separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


# --- Computed readiness ------------------------------------------------------
def compute_readiness(*, status, versions, validations, today,
                      what="policy", date_field="effective_from"):
    """The computed Configuration Readiness state of one policy.

    ``validations`` are the validation audit events for this policy (each
    carrying the ``after_hash`` snapshot it validated). Nothing here is
    stored: the state falls out of (status, versions, validations, today),
    so appending a version automatically returns a validated policy to
    ``configured`` until it is validated again.
    """
    if status == "Retired":
        return READINESS_RETIRED
    if status != "Active":
        raise ValueError(f"Unknown {what} status: {status}")
    existing = list(versions or [])
    if not existing:
        return READINESS_INCOMPLETE
    # Ambiguity fails closed before any state is reported.
    assert_no_ambiguous_versions(existing, what, date_field)
    current = snapshot_digest(existing)
    validated = any(str(item.get("after_hash") or "") == current
                    for item in (validations or []))
    if not validated:
        return READINESS_CONFIGURED
    # Readiness tracks the LATEST version, not current governance: a
    # scheduled (future) latest reads validated even while a predecessor
    # still governs today; it reads effective only once the latest itself
    # is in effect. (Ambiguity already fails closed above, so the strict
    # resolver's duplicate-date raise is unreachable here.)
    latest_effective = str(
        (latest_version(existing, date_field) or {}).get(date_field) or "")
    if not latest_effective or str(today) < latest_effective:
        return READINESS_VALIDATED
    return READINESS_EFFECTIVE


# --- Command-only mutation boundary --------------------------------------------
# Policy records mutate ONLY through the guarded configuration commands.
# The mechanism mirrors toefl_house.security's command ContextVar minus the
# site gate (governance boundary): configuration_audit.execute() runs every
# command inside command_context(), and the controllers refuse any save
# made outside it — native form, REST API, data import, or stray
# ignore_permissions write — with a business-language refusal. Token reset
# keeps an outer context intact if commands ever nest.
_COMMAND_CONTEXT = ContextVar("toefl_house_configuration_command", default=None)


def active_command():
    """The configuration command kind currently mutating, or None."""
    return _COMMAND_CONTEXT.get()


@contextmanager
def command_context(kind):
    token = _COMMAND_CONTEXT.set(kind)
    try:
        yield kind
    finally:
        _COMMAND_CONTEXT.reset(token)


def assert_command_context(message):
    """Refuse any mutation attempted outside a configuration command.

    Controllers call this FIRST in validate() — before any data check — so
    an unauthorized path always meets the authorization refusal, never a
    data error. Raises ValueError carrying the caller's business-language
    message; controllers convert it to frappe.PermissionError.
    """
    if _COMMAND_CONTEXT.get() is None:
        raise ValueError(message)


# --- Hash-chain verification --------------------------------------------------
def verify_chain(events):
    """Verify per-target hash continuity of ordered audit events.

    Every event's ``before_hash`` must equal the previous event's
    ``after_hash`` for the same target (slice-tolerant: the first event
    shown for a target may start mid-chain), and every ``after_hash`` must
    be present. Returns the number of events verified; raises naming the
    target and the break otherwise.
    """
    count = 0
    last_after = {}
    for event in events or []:
        target = (event or {}).get("target") or ""
        before = (event or {}).get("before_hash") or ""
        after = (event or {}).get("after_hash") or ""
        if not target:
            raise ValueError("An audit event without a target breaks the chain")
        if not after:
            raise ValueError(
                f"The audit chain for {target} is missing an after-hash")
        if target in last_after and before != last_after[target]:
            raise ValueError(
                f"The audit chain for {target} is broken: an event's "
                "before-hash does not match the previous after-hash")
        last_after[target] = after
        count += 1
    return count

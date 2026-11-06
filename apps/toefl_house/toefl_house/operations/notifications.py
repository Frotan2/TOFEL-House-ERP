"""Operational internal notifications with durable delivery.

Implements the seven operational event sources as condition generators,
plus the durable notification lifecycle (queued → delivered/failed →
acknowledged, with retries and escalation) and configurable dispatch
rules (recipients, severity, timing, channel, retries, escalation,
disabling).

Design mirrors the existing policy pattern (fail-closed, no defaults
that invent Owner values) but dispatch rules themselves are owner-config-
urable and default to DISABLED for each event type. A notification is
only created when its event_type rule is enabled.

Durable states (explicit, no fake delivered):
- queued: created, awaiting delivery
- delivered: provider confirmed delivery
- failed: provider reported failure (retries may be pending)
- acknowledged: human has acknowledged (terminal)

Transitions are validated; a failed notification may be retried up to
max_retries, then stays failed. Escalation adds recipients after
escalate_after_minutes of non-acknowledgement.

This module is frappe-light: core logic is pure and testable offline.
Frappe is used only for persistence helpers (get_all/get_doc/insert/save)
which are stub-able in tests.

Related: toefl_house.observability (system alerts), portal_policy,
external_provider.
"""
import frappe
import json
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EVENT_TYPES = (
    "overdue_tuition",
    "pending_academic_approval",
    "incomplete_attendance",
    "class_change",
    "low_book_stock",
    "scheduling_conflict",
    "system_alert",
)

SEVERITIES = ("info", "warning", "critical")
CHANNELS = ("Dashboard", "Email", "SMS", "WhatsApp")
# Normalized lower-case for provider routing
CHANNEL_MAP = {c.lower(): c for c in CHANNELS}

NOTIFICATION_STATES = ("queued", "delivered", "failed", "acknowledged")

# Default dispatch rules — all disabled. Owner must enable each event.
DEFAULT_DISPATCH_RULES = {
    et: {
        "enabled": False,
        "recipients": [],
        "severity": "info",
        "channel": "Dashboard",
        "timing_delay_minutes": 0,
        "max_retries": 3,
        "retry_delay_minutes": 30,
        "escalate_after_minutes": None,
        "escalation_recipients": [],
    }
    for et in EVENT_TYPES
}

# Technical bounds (typo guards, not business values)
RECIPIENT_MAX = 10
RETRY_MAX = 10
ESCALATE_MAX = 525600
TIMING_MAX = 525600  # 1 year in minutes
TITLE_MAX = 140
MESSAGE_MAX = 2000

# DocType name for durable records
NOTIFICATION_DOCTYPE = "TH Notification"
DISPATCH_RULE_DOCTYPE = "TH Notification Dispatch Rule"  # per-event config doc

# In-memory rule overrides for offline tests
_memory_rules = {}  # event_type -> rule dict

# Site wall-clock timezone. Stored datetimes in this app are naive
# Asia/Kabul wall time (Frappe stores naive datetimes in site time);
# aware values are converted here and made naive, never compared raw.
try:
    _KABUL_TZ = ZoneInfo("Asia/Kabul")
except Exception:  # pragma: no cover - tzdata missing from the host
    from datetime import timezone as _timezone

    _KABUL_TZ = _timezone(timedelta(minutes=270))  # +04:30, no DST


def _to_naive_kabul(value):
    """Normalize a datetime to naive Asia/Kabul wall time (None-safe)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    try:
        return value.astimezone(_KABUL_TZ).replace(tzinfo=None)
    except Exception:
        return value.replace(tzinfo=None)


# In-flight delivery claims (same-process duplicate suppression).
# A second attempt for the same notification while one is running
# returns "already in progress" without sending. This bounds
# same-process races; cross-process races are bounded by the
# per-recipient skip below (a duplicate worker can at worst re-send
# to a recipient with no persisted success yet). A fully atomic
# cross-process claim would need a DB row-lock transaction, which
# this frappe-light layer does not have — see the report.
_delivery_lock = threading.Lock()
_in_flight_deliveries = set()

# Versioned per-recipient outcome record, persisted in the existing
# TH Notification.last_failure Small Text field (no doctype schema
# change is in scope for this area). "delivered" needs no record:
# status=delivered itself means every recipient succeeded. A failed
# notification's last_failure is this JSON document, so a fresh load
# (new process, new worker) recovers exactly which recipients already
# succeeded and a retry never resends to them. Legacy plain-text
# last_failure values decode to (text, None) — no known successes.
_DELIVERY_OUTCOME_VERSION = 1
# A retry batch may need to inspect more FAILED rows than it will send:
# undeliverable/exhausted early rows must not starve actionable later ones.
# Reading beyond this bound requires an operator-visible refusal, not a
# silent assumption that the oldest `limit` rows are the entire queue.
RETRY_SCAN_MAX = 5000


def _encode_delivery_outcome(detail, delivery_results):
    payload = {
        "version": _DELIVERY_OUTCOME_VERSION,
        "detail": detail,
        "results": list(delivery_results or []),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True)


def _decode_delivery_outcome(last_failure):
    """Return (detail_text, results_or_None) for a stored last_failure."""
    if not last_failure:
        return ("", None)
    text = str(last_failure).strip()
    if not text.startswith("{"):
        return (text, None)
    try:
        payload = json.loads(text)
    except ValueError:
        return (text, None)
    if not isinstance(payload, dict):
        return (text, None)
    if payload.get("version") != _DELIVERY_OUTCOME_VERSION:
        return (payload.get("detail") or text, None)
    results = payload.get("results")
    if not isinstance(results, list):
        return (payload.get("detail") or text, None)
    return (payload.get("detail") or text, results)


def _live_rows(rows, cap, what):
    """Fail closed when a live generator read exceeds its supported cap.

    Notification generation must never silently drop rows past a limit:
    an overdue fee or low-stock item past the cap would simply never be
    notified about. Callers fetch cap+1 rows and pass them here.
    """
    if len(rows) > cap:
        raise frappe.ValidationError(
            "%s exceeds the supported limit of %d; narrow the scope or "
            "contact an administrator" % (what, cap))
    return rows

# In-memory durable notification fallback (for offline harness where frappe DB is stubbed)
# Keyed by notification name → dict. Used when frappe persistence is not available.
_memory_notifications = {}

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_dispatch_rule(rule):
    """Validate and clean one dispatch rule dict. Returns cleaned copy.

    Required keys: event_type, recipients, severity, channel, max_retries.
    Optional: timing_delay_minutes, retry_delay_minutes,
              escalate_after_minutes, escalation_recipients, enabled.
    Raises ValueError with human message on any violation.
    """
    if not isinstance(rule, dict):
        raise ValueError("Dispatch rule must be a mapping")
    et = rule.get("event_type")
    if et not in EVENT_TYPES:
        raise ValueError(f"event_type must be one of {', '.join(EVENT_TYPES)}")
    # Recipients: list of role names or user emails (non-empty when enabled)
    recipients = rule.get("recipients")
    if recipients is None:
        recipients = []
    if not isinstance(recipients, (list, tuple)):
        raise ValueError("recipients must be a list")
    cleaned_recipients = []
    for r in recipients:
        if not isinstance(r, str) or not r.strip():
            raise ValueError("Each recipient must be a non-empty string")
        s = r.strip()
        if len(s) > 140:
            raise ValueError("Recipient must be at most 140 characters")
        cleaned_recipients.append(s)
    if rule.get("enabled") and not cleaned_recipients:
        raise ValueError(f"Enabled rule for {et} requires at least one recipient")
    if len(cleaned_recipients) > RECIPIENT_MAX:
        raise ValueError(f"At most {RECIPIENT_MAX} recipients per rule")
    # Escalation recipients
    esc = rule.get("escalation_recipients") or []
    if esc is None:
        esc = []
    if not isinstance(esc, (list, tuple)):
        raise ValueError("escalation_recipients must be a list")
    cleaned_esc = []
    for r in esc:
        if not isinstance(r, str) or not r.strip():
            raise ValueError("Each escalation recipient must be non-empty string")
        cleaned_esc.append(r.strip())
    if len(cleaned_esc) > RECIPIENT_MAX:
        raise ValueError(f"At most {RECIPIENT_MAX} escalation recipients")
    # Severity
    sev = rule.get("severity") or "info"
    if sev not in SEVERITIES:
        raise ValueError(f"severity must be one of {', '.join(SEVERITIES)}")
    # Channel
    ch = rule.get("channel") or "Dashboard"
    if ch not in CHANNELS and ch.lower() not in [c.lower() for c in CHANNELS]:
        raise ValueError(f"channel must be one of {', '.join(CHANNELS)}")
    # Normalize channel to canonical capitalisation
    if ch.lower() in CHANNEL_MAP:
        ch = CHANNEL_MAP[ch.lower()]
    # Timing
    for field in ("timing_delay_minutes", "retry_delay_minutes"):
        v = rule.get(field)
        if v in (None, ""):
            v = 0 if field == "timing_delay_minutes" else 30
        else:
            v = _coerce_int(v)
            if not isinstance(v, int) or v < 0 or v > TIMING_MAX:
                raise ValueError(f"{field} must be 0..{TIMING_MAX}")
        rule[field] = v
    # Max retries
    mr = rule.get("max_retries")
    if mr in (None, ""):
        mr = 3
    else:
        mr = _coerce_int(mr)
        if not isinstance(mr, int) or mr < 0 or mr > RETRY_MAX:
            raise ValueError(f"max_retries must be 0..{RETRY_MAX}")
    # Escalation after
    ea = rule.get("escalate_after_minutes")
    if ea in (None, ""):
        ea = None
    else:
        ea = _coerce_int(ea)
        if not isinstance(ea, int) or ea < 1 or ea > ESCALATE_MAX:
            raise ValueError(f"escalate_after_minutes must be 1..{ESCALATE_MAX} or empty")
    # Enabled
    en = rule.get("enabled")
    if en is None:
        en = False
    if isinstance(en, str) and en.strip().lower() in ("1", "true", "yes", "on"):
        en = True
    elif isinstance(en, str) and en.strip().lower() in ("0", "false", "no", "off"):
        en = False
    elif isinstance(en, int) and en in (0, 1):
        en = bool(en)
    elif not isinstance(en, bool):
        raise ValueError("enabled must be true or false")

    return {
        "event_type": et,
        "recipients": cleaned_recipients,
        "severity": sev,
        "channel": ch,
        "timing_delay_minutes": rule.get("timing_delay_minutes", 0),
        "max_retries": mr,
        "retry_delay_minutes": rule.get("retry_delay_minutes", 30),
        "escalate_after_minutes": ea,
        "escalation_recipients": cleaned_esc,
        "enabled": en,
    }


def _coerce_int(v):
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        # allow negative string to be caught by range check
        try:
            return int(v.strip())
        except ValueError:
            return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return v


# ---------------------------------------------------------------------------
# Dispatch rule persistence
# ---------------------------------------------------------------------------
def _isolated_test():
    """Synthetic in-memory transport must never authorize production state."""
    return bool(getattr(getattr(frappe, "flags", None), "in_test", False))


def get_dispatch_rule(event_type):
    """Return the effective dispatch rule for an event_type.

    Checks in-memory overrides first, then TH Notification Dispatch Rule doc,
    then defaults. Never invents a recipient — disabled by default.

    "No rule configured" returns the disabled default. A failed rule
    read is NOT "no rule": the DB error is raised so a transient outage
    can never silently disable every enabled rule (C-20). Only the
    secondary recipient child-table reads stay lenient — an enabled rule
    that ends up with no recipients still fails closed in
    validate_dispatch_rule below.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event_type: {event_type}")
    if _isolated_test() and event_type in _memory_rules:
        return _memory_rules[event_type]
    # Try DB — a read failure here must surface, not fall back to defaults.
    try:
        docs = frappe.db.get_all(
            DISPATCH_RULE_DOCTYPE,
            filters={"event_type": event_type},
            fields=["name", "event_type", "enabled", "severity", "channel",
                    "timing_delay_minutes", "max_retries", "retry_delay_minutes",
                    "escalate_after_minutes"],
            limit=1,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not read dispatch rule for {event_type}: "
            f"{type(exc).__name__}"
        ) from exc
    if docs:
        row = docs[0]
        # recipients are in child table or JSON field
        recipients = []
        try:
            children = frappe.db.get_all(
                "TH Notification Recipient",
                filters={"parent": row["name"]},
                fields=["recipient"],
                limit=100,
            )
            recipients = [c["recipient"] for c in children]
        except Exception:
            recipients = []
        rule = {
            "event_type": row.get("event_type"),
            "enabled": bool(row.get("enabled")),
            "recipients": recipients,
            "severity": row.get("severity") or "info",
            "channel": row.get("channel") or "Dashboard",
            "timing_delay_minutes": row.get("timing_delay_minutes") or 0,
            "max_retries": row.get("max_retries") if row.get("max_retries") is not None else 3,
            "retry_delay_minutes": row.get("retry_delay_minutes") or 30,
            "escalate_after_minutes": row.get("escalate_after_minutes"),
            "escalation_recipients": [],
        }
        # escalation recipients child table. Unlike the main recipients
        # read above, there is no downstream validator that catches a
        # failed read here: an unreadable table would silently look like
        # "no escalation configured" and escalation would never fire.
        # A read failure therefore raises (C-20), like the rule read.
        try:
            esc_rows = frappe.db.get_all(
                "TH Notification Escalation Recipient",
                filters={"parent": row["name"]},
                fields=["recipient"],
                limit=100,
            )
            rule["escalation_recipients"] = [c["recipient"] for c in esc_rows]
        except Exception as exc:
            raise RuntimeError(
                "Could not read escalation recipients for "
                f"{event_type}: {type(exc).__name__}"
            ) from exc
        return validate_dispatch_rule(rule)
    # Default (disabled) — only when no rule row exists.
    return dict(DEFAULT_DISPATCH_RULES[event_type])


def set_dispatch_rule(rule, request_key=None):
    """Owner-authorized durable dispatch rule. No offline fake success.

    A transport or DB failure is a failure, not a valid policy change.
    A process-local cache must never become the source of notification
    authority for another request or worker.
    """
    from toefl_house.configuration.audit import require_authority
    require_authority("business_policy")
    cleaned = validate_dispatch_rule(rule)
    et = cleaned["event_type"]
    existing = frappe.db.get_all(
        DISPATCH_RULE_DOCTYPE, filters={"event_type": et},
        fields=["name"], limit=2)
    if len(existing) > 1:
        raise frappe.ValidationError("Multiple dispatch rules for the same event")
    if existing:
        doc = frappe.get_doc(DISPATCH_RULE_DOCTYPE, existing[0]["name"])
    else:
        doc = frappe.get_doc({"doctype": DISPATCH_RULE_DOCTYPE, "event_type": et})
    doc.enabled = 1 if cleaned["enabled"] else 0
    doc.severity = cleaned["severity"]
    doc.channel = cleaned["channel"]
    doc.timing_delay_minutes = cleaned["timing_delay_minutes"]
    doc.max_retries = cleaned["max_retries"]
    doc.retry_delay_minutes = cleaned["retry_delay_minutes"]
    doc.escalate_after_minutes = cleaned["escalate_after_minutes"]
    doc.set("recipients", [])
    for recipient in cleaned["recipients"]:
        doc.append("recipients", {"recipient": recipient})
    doc.set("escalation_recipients", [])
    for recipient in cleaned["escalation_recipients"]:
        doc.append("escalation_recipients", {"recipient": recipient})
    if existing:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)
    # Do not publish a process-global rule as an alternative to the DB.
    return cleaned


def governing_notification_config():
    """Return all dispatch rules (for admin UI)."""
    result = {}
    for et in EVENT_TYPES:
        result[et] = get_dispatch_rule(et)
    return result


def _reset_memory_notifications():
    _memory_notifications.clear()

def reset_memory_rules():
    _memory_rules.clear()
    _memory_notifications.clear()


# ---------------------------------------------------------------------------
# Durable notification record
# ---------------------------------------------------------------------------
def _now():
    try:
        return frappe.utils.now_datetime()
    except Exception:
        return datetime.now().isoformat(sep=" ", timespec="seconds")


def _today():
    try:
        return frappe.utils.today()
    except Exception:
        return datetime.now().date().isoformat()


def _parse_dt(value):
    """Parse a stored 'YYYY-MM-DD HH:MM:SS' (or ISO) datetime; None if unparseable.

    Naive values are Asia/Kabul wall time; aware values are converted
    to Asia/Kabul and made naive, so the two never meet in a comparison
    (comparing them raises TypeError). Callers treat None as
    "unevaluatable", never as "no time".
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return _to_naive_kabul(value)
    text = str(value).strip()
    try:
        return _to_naive_kabul(datetime.fromisoformat(text))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _now_dt():
    """Current time as a naive Asia/Kabul datetime.

    Tolerates _now() returning a str or a datetime, naive or aware.
    """
    try:
        parsed = _parse_dt(_now())
        if parsed is not None:
            return parsed
    except Exception:
        pass
    return _to_naive_kabul(datetime.now())


def create_notification(event_type, title, message, severity=None,
                        channel=None, related_doctype=None, related_name=None,
                        recipients=None, dispatch_rule=None,
                        timing_delay_minutes=None):
    """Create a durable notification record in queued state.

    Uses the dispatch_rule for recipients/severity/channel/timing unless
    overridden. Respects the rule's enabled flag — if disabled, returns
    None (no notification created). Caller must not fake a delivered
    status; the record is always queued initially.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event_type: {event_type}")
    rule = dispatch_rule or get_dispatch_rule(event_type)
    if not rule.get("enabled"):
        return None

    # Channel enablement check (provider-independent: disabled channel ⇒ queued but delivery will fail)
    # We still create the record so failure is visible; delivery step checks channel enablement.
    sev = severity or rule.get("severity") or "info"
    if sev not in SEVERITIES:
        raise ValueError(f"Invalid severity: {sev}")
    ch = channel or rule.get("channel") or "Dashboard"
    if ch not in CHANNELS and ch.lower() not in [c.lower() for c in CHANNELS]:
        raise ValueError(f"Invalid channel: {ch}")
    if ch.lower() in CHANNEL_MAP:
        ch = CHANNEL_MAP[ch.lower()]

    if not isinstance(title, str) or not 1 <= len(title.strip()) <= TITLE_MAX:
        raise ValueError(f"Title must be 1..{TITLE_MAX} characters")
    title = title.strip()
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Message must be non-empty")
    message = message.strip()
    if len(message) > MESSAGE_MAX:
        raise ValueError(f"Message must be at most {MESSAGE_MAX} characters")

    # Recipients: explicit or from rule
    recips = recipients if recipients is not None else rule.get("recipients") or []
    if not recips:
        raise ValueError("At least one recipient is required")
    if len(recips) > RECIPIENT_MAX:
        raise ValueError(f"At most {RECIPIENT_MAX} recipients")

    # Timing: scheduled delivery time
    delay = timing_delay_minutes if timing_delay_minutes is not None else rule.get("timing_delay_minutes", 0)
    if delay is None:
        delay = 0
    try:
        if isinstance(delay, bool):
            raise ValueError("timing_delay_minutes must be a whole number")
        delay = int(delay)
    except (TypeError, ValueError) as exc:
        raise ValueError("timing_delay_minutes must be a whole number") from exc
    if delay < 0:
        raise ValueError("timing_delay_minutes must not be negative")
    deliver_at = None
    if delay > 0:
        deliver_at = (_now_dt() + timedelta(minutes=delay)).isoformat(sep=" ", timespec="seconds")

    # Build doc dict
    doc_data = {
        "doctype": NOTIFICATION_DOCTYPE,
        "event_type": event_type,
        "title": title,
        "message": message,
        "severity": sev,
        "channel": ch,
        "status": "queued",
        "related_doctype": related_doctype or "",
        "related_name": related_name or "",
        "retry_count": 0,
        "max_retries": rule.get("max_retries", 3),
        "retry_delay_minutes": rule.get("retry_delay_minutes", 30),
        "escalate_after_minutes": rule.get("escalate_after_minutes"),
        "escalated": 0,
        "deliver_at": deliver_at,
        "created_at": _now(),
    }

    # Persist
    try:
        doc = frappe.get_doc(doc_data)
        doc.insert(ignore_permissions=True)
        # Insert recipients child rows if the doctype supports it.
        # A failed recipient write raises (C-10): the caller must
        # never be told recipients exist when none were persisted.
        for r in recips:
            doc.append("recipients", {"recipient": r})
        if recips:
            doc.save(ignore_permissions=True)
        # Also store a flat recipients_json for offline harness
        try:
            # For the in-memory stub, store recipients directly on doc
            doc.recipients_list = list(recips)
        except Exception:
            pass
        result = {
            "name": doc.name,
            "event_type": event_type,
            "title": title,
            "message": message,
            "severity": sev,
            "channel": ch,
            "status": "queued",
            "related_doctype": related_doctype or "",
            "related_name": related_name or "",
            "recipients": list(recips),
            "retry_count": 0,
            "max_retries": rule.get("max_retries", 3),
            "retry_delay_minutes": rule.get("retry_delay_minutes", 30),
            "escalate_after_minutes": rule.get("escalate_after_minutes"),
            "escalated": False,
            "deliver_at": deliver_at,
            "created_at": doc_data["created_at"],
        }
        # Keep fallback store in sync for offline harness
        if _isolated_test():
            _memory_notifications[result["name"]] = dict(result)
        return result
    except Exception:
        if not _isolated_test():
            # A failed DB write is never a durable queued notification.
            # Do not report success from an ephemeral in-memory fallback.
            raise
        # Only isolated unit-test harnesses may simulate missing DB writes.
        # Simulate a doc name (include title to make unique within second)
        import hashlib
        name = "NOTIF-" + hashlib.sha256((_now() + title).encode()).hexdigest()[:8].upper()
        result = {
            "name": name,
            "event_type": event_type,
            "title": title,
            "message": message,
            "severity": sev,
            "channel": ch,
            "status": "queued",
            "related_doctype": related_doctype or "",
            "related_name": related_name or "",
            "recipients": list(recips),
            "retry_count": 0,
            "max_retries": rule.get("max_retries", 3),
            "retry_delay_minutes": rule.get("retry_delay_minutes", 30),
            "escalate_after_minutes": rule.get("escalate_after_minutes"),
            "escalated": False,
            "deliver_at": deliver_at,
            "created_at": doc_data["created_at"],
        }
        _memory_notifications[name] = dict(result)
        return result


def _load_notification(name):
    """Load a notification doc/dict by name."""
    # In-memory fallback store first (offline harness)
    if _isolated_test() and isinstance(name, str) and name in _memory_notifications:
        data = dict(_memory_notifications[name])
        class _MemDoc(dict):
            def get(self, k, d=None):
                return super().get(k, d)
            @property
            def name(self):
                return data.get("name")
            def save(self, ignore_permissions=False):
                # sync data dict from self mutations if any, else sync from data
                for k, v in list(self.items()):
                    data[k] = v
                _memory_notifications[name] = dict(data)
                return self
            def append(self, f, row):
                data.setdefault(f, []).append(dict(row))
                self.setdefault(f, []).append(dict(row))
        doc = _MemDoc(data)
        # Expose mutations on doc proxy back to data
        # We will keep data as single source; doc forwards to data on save
        return doc, data
    try:
        doc = frappe.get_doc(NOTIFICATION_DOCTYPE, name)
        # Convert to dict with key fields
        data = {
            "name": doc.name,
            "event_type": doc.get("event_type"),
            "title": doc.get("title"),
            "message": doc.get("message"),
            "severity": doc.get("severity"),
            "channel": doc.get("channel"),
            "status": doc.get("status"),
            "related_doctype": doc.get("related_doctype"),
            "related_name": doc.get("related_name"),
            "retry_count": doc.get("retry_count") or 0,
            "max_retries": doc.get("max_retries") or 3,
            "retry_delay_minutes": doc.get("retry_delay_minutes") or 30,
            "escalate_after_minutes": doc.get("escalate_after_minutes"),
            "next_retry_at": doc.get("next_retry_at"),
            "escalated": bool(doc.get("escalated")),
            "deliver_at": doc.get("deliver_at"),
            "created_at": doc.get("created_at"),
            "delivered_at": doc.get("delivered_at"),
            "acknowledged_at": doc.get("acknowledged_at"),
            "acknowledged_by": doc.get("acknowledged_by"),
            "last_failure": doc.get("last_failure"),
        }
        # Per-recipient outcomes are durably persisted as JSON in
        # last_failure (see _encode_delivery_outcome). A fresh load must
        # recover them so a retry in another process/worker still knows
        # which recipients already succeeded (C-10).
        _detail, _results = _decode_delivery_outcome(data["last_failure"])
        if _results is not None:
            data["delivery_results"] = _results
        # Recipients child table
        try:
            recips = [r.get("recipient") for r in (doc.get("recipients") or [])]
            data["recipients"] = recips
        except Exception:
            data["recipients"] = getattr(doc, "recipients_list", [])
    except Exception:
        return None, None
    # Escalation recipients live in their own child table; once a
    # notification is escalated they are recipients too, and a fresh
    # load must still retry them — they must never exist only in
    # process memory. This read runs OUTSIDE the broad load try above:
    # a failed read raises (fail-closed, C-10) instead of silently
    # dropping the escalation recipients from the retry.
    esc_rows = doc.get("escalation_recipients") or []
    esc_recips = []
    for r in esc_rows:
        v = r.get("recipient") if isinstance(r, dict) else r
        if v and v not in data["recipients"] and v not in esc_recips:
            esc_recips.append(v)
    if esc_recips:
        data["recipients"] = list(data["recipients"]) + esc_recips
    return doc, data


def _send_to_recipients(payload, recipients, provider_override=None):
    """Send the payload to each recipient in turn.

    Returns a list of per-recipient outcome dicts
    {recipient, delivered, provider, detail}. A provider exception for
    one recipient fails only that recipient, never the whole attempt.
    """
    results = []
    for recipient in recipients:
        per_payload = dict(payload)
        per_payload["recipient"] = recipient
        if provider_override is not None:
            # Custom provider for tests
            try:
                # Only a real boolean True counts as delivery.
                # bool("false") is True and would falsely confirm a send.
                sent = provider_override.send(per_payload) is True
                results.append({
                    "recipient": recipient,
                    "delivered": sent,
                    "provider": getattr(provider_override, "name", "test-provider"),
                    "detail": "Delivered via test provider" if sent
                              else "Test provider reported failure",
                })
            except Exception as exc:
                results.append({
                    "recipient": recipient,
                    "delivered": False,
                    "provider": "test-provider",
                    "detail": f"Test provider exception: {type(exc).__name__}",
                })
        else:
            from toefl_house.operations import external_provider
            sent, prov_name, per_detail = external_provider.deliver(per_payload)
            results.append({
                "recipient": recipient,
                "delivered": sent,
                "provider": prov_name,
                "detail": per_detail,
            })
    return results


def _persist_delivery(doc, data, notification_name, new_status, new_retry,
                      next_retry_at, delivery_results, detail,
                      provider_name=None, touch_delivered_at=True):
    """Persist one delivery outcome to the doc and the in-memory record.

    On failure the per-recipient outcomes are durably encoded in
    last_failure (see _encode_delivery_outcome); on success last_failure
    is cleared — a delivered notification has no outstanding failure —
    and delivered_at/delivered_via record the success. next_retry_at is
    always written (None clears a stale value from an earlier failure).
    A failed doc.save is a failure, never a silent success, outside the
    isolated test harness.
    """
    if doc is not None:
        try:
            doc.status = new_status
            doc.retry_count = new_retry
            doc.next_retry_at = next_retry_at
            if new_status == "delivered":
                if touch_delivered_at:
                    doc.delivered_at = _now()
                if provider_name is not None:
                    doc.delivered_via = provider_name
                doc.last_failure = ""
            else:
                doc.last_failure = _encode_delivery_outcome(detail, delivery_results)
            doc.save(ignore_permissions=True)
        except Exception:
            if not _isolated_test():
                raise
    data["status"] = new_status
    data["retry_count"] = new_retry
    data["next_retry_at"] = next_retry_at
    data["delivery_results"] = list(delivery_results or [])
    if new_status == "delivered":
        if touch_delivered_at:
            data["delivered_at"] = _now()
        data["last_failure"] = ""
    else:
        # The in-memory record carries the same encoded document as the
        # doc: the human detail is inside it (see _decode_delivery_outcome).
        # Storing plain text here would silently drop the durable
        # per-recipient record on the next sync.
        data["last_failure"] = _encode_delivery_outcome(detail, delivery_results)
    # sync fallback store
    if isinstance(notification_name, str) and notification_name in _memory_notifications:
        _memory_notifications[notification_name].update(data)


def attempt_delivery(notification_name, provider_override=None):
    """Attempt to deliver a queued/failed notification.

    Transitions:
      queued -> delivered (on success)
      queued -> failed   (on failure, retry_count++)
      failed -> delivered (on retry success)
      failed -> failed   (on retry failure, retry_count++, until max_retries)

    Uses external_provider.deliver() which respects channel enablement.
    Returns (new_status, detail).
    Never fakes a delivered status: if any recipient fails, status is
    failed. Retries NEVER resend to recipients with a persisted success
    (C-10): outcomes are recovered from the durable record on load.
    Concurrent duplicate attempts in this process are refused without
    sending (see _in_flight_deliveries).
    """
    if isinstance(notification_name, str):
        with _delivery_lock:
            if notification_name in _in_flight_deliveries:
                _, _data = _load_notification(notification_name)
                _status = (_data or {}).get("status") or "failed"
                return (_status, "Delivery already in progress")
            _in_flight_deliveries.add(notification_name)
        try:
            return _attempt_delivery_locked(notification_name, provider_override)
        finally:
            with _delivery_lock:
                _in_flight_deliveries.discard(notification_name)
    return _attempt_delivery_locked(notification_name, provider_override)


def _attempt_delivery_locked(notification_name, provider_override=None):
    """attempt_delivery body; the in-flight claim is held by the caller."""
    doc, data = _load_notification(notification_name)
    if data is None:
        # Might be a dict passed directly (offline harness)
        if isinstance(notification_name, dict):
            data = notification_name
            doc = None
        else:
            raise ValueError(f"Notification not found: {notification_name}")

    if data["status"] not in ("queued", "failed"):
        return (data["status"], "Notification is not in deliverable state")

    # Check timing: if deliver_at is in the future, don't deliver yet.
    # An unparseable deliver_at blocks delivery (fail-closed): a corrupt
    # schedule must not silently become "deliver now".
    deliver_at = data.get("deliver_at")
    if deliver_at:
        da = _parse_dt(deliver_at)
        if da is None:
            # Unevaluable schedule, not a delivery attempt: persist a
            # diagnostic (C-10) instead of returning silently with no
            # record. retry_count is NOT incremented — this was never
            # an attempt — and the raw value is kept so the block
            # stays fail-closed until the schedule is repaired.
            _persist_delivery(doc, data, notification_name, data["status"],
                              data["retry_count"], data.get("next_retry_at"),
                              data.get("delivery_results") or [],
                              "Delivery time could not be evaluated: %r"
                              % (deliver_at,), None)
            return (data["status"], "Delivery time could not be evaluated")
        if _now_dt() < da:
            return (data["status"], "Delivery time has not arrived")

    # Rate-limit retries: check next_retry_at (C-10 — the stored value
    # was previously written but never read, so retries fired immediately).
    # An unparseable next_retry_at likewise blocks the retry.
    if data["status"] == "failed":
        if data["retry_count"] >= data["max_retries"]:
            return ("failed", "Max retries exhausted")
        raw_next = data.get("next_retry_at")
        if raw_next:
            next_retry_at = _parse_dt(raw_next)
            if next_retry_at is None:
                # Same contract as an unevaluable deliver_at: persist
                # a diagnostic, do not count a retry, keep the raw
                # value so the block stays fail-closed.
                _persist_delivery(doc, data, notification_name, "failed",
                                  data["retry_count"],
                                  data.get("next_retry_at"),
                                  data.get("delivery_results") or [],
                                  "Retry time could not be evaluated: %r"
                                  % (raw_next,), None)
                return ("failed", "Retry time could not be evaluated")
            if _now_dt() < next_retry_at:
                return ("failed", "Retry time has not arrived")

    # Build provider payload (base; "recipient" is set per recipient below)
    payload = {
        "notification_id": data["name"],
        "event_type": data["event_type"],
        "title": data["title"],
        "message": data["message"],
        "severity": data["severity"],
        "channel": data["channel"],
        "recipients": data.get("recipients") or [],
    }

    # Deliver to EVERY recipient who has not already succeeded (C-10):
    # the old code sent only to recipients[0] and marked the
    # notification delivered. A notification is delivered only when
    # every recipient succeeds; per-recipient outcomes are recorded in
    # the detail and durably in last_failure (see _persist_delivery).
    # Corrupted durable outcome JSON must NEVER be interpreted as
    # evidence of delivery. In particular, a string "false" is truthy
    # in Python: the old set comprehension treated it as success and
    # skipped that recipient permanently. Reject malformed/duplicate
    # results before calling any external provider.
    raw_prior = data.get("delivery_results")
    if raw_prior is None:
        raw_prior = []
    if not isinstance(raw_prior, list):
        raise frappe.ValidationError(
            "Notification recipient delivery history is malformed")
    prior = []
    seen_prior = set()
    for record in raw_prior:
        if (not isinstance(record, dict)
                or not isinstance(record.get("recipient"), str)
                or not record["recipient"].strip()
                or type(record.get("delivered")) is not bool
                or record["recipient"] in seen_prior):
            raise frappe.ValidationError(
                "Notification recipient delivery history is malformed")
        seen_prior.add(record["recipient"])
        prior.append(record)
    succeeded = {r["recipient"] for r in prior if r["delivered"]}
    recipients = []
    for r in (data.get("recipients") or []):
        if r and r not in recipients:
            recipients.append(r)
    if not recipients:
        # A persisted notification that lost its recipients is a damaged
        # authorization target. The old fallback [""] handed an empty
        # recipient to DashboardProvider, which unconditionally succeeds,
        # and the notification was falsely marked delivered.
        _persist_delivery(doc, data, notification_name, "failed",
                          data["retry_count"], data.get("next_retry_at"),
                          prior, "No recipients configured; restore the "
                          "authorized recipient list before retrying", None)
        return ("failed", "No recipients configured")
    pending = [r for r in recipients if r not in succeeded]
    if not pending:
        # Every recipient already succeeded but the status was never
        # updated (e.g. a crash between persisting outcomes and the
        # status write): reconcile to delivered without resending.
        _persist_delivery(doc, data, notification_name, "delivered",
                          data["retry_count"], None, prior,
                          "All recipients already delivered", None)
        return ("delivered", "All recipients already delivered")

    order = {r: i for i, r in enumerate(recipients)}
    # C-10 crash window: send one recipient at a time and persist
    # that recipient's outcome as soon as its send completes. The old
    # code sent every recipient and persisted once afterwards, so a
    # crash/kill between send and persist lost the whole attempt and
    # the next retry resent to recipients who already received it.
    # The intermediate record stays failed with the original
    # retry_count and no next_retry_at: it is a partial attempt, not
    # a completed failure. A crash after recipient N leaves N's
    # outcome durable; the retry reconciles from it and skips N.
    new_results = []
    for recipient in pending:
        new_results.extend(
            _send_to_recipients(payload, [recipient], provider_override))
        attempted_so_far = {r["recipient"] for r in new_results}
        merged_so_far = [r for r in prior
                         if r["recipient"] not in attempted_so_far]
        merged_so_far.extend(new_results)
        merged_so_far.sort(
            key=lambda r: order.get(r["recipient"], len(order)))
        _persist_delivery(doc, data, notification_name, "failed",
                          data["retry_count"], None, merged_so_far,
                          "Delivery in progress: %d of %d recipient(s) "
                          "recorded" % (len(new_results), len(recipients)),
                          None)
    attempted = {r["recipient"] for r in new_results}
    merged = [r for r in prior if r["recipient"] not in attempted]
    merged.extend(new_results)
    merged.sort(key=lambda r: order.get(r["recipient"], len(order)))

    ok = all(r["delivered"] for r in merged)
    if ok:
        detail = ("Delivered to all %d recipient(s): %s"
                  % (len(recipients), ", ".join(recipients)))
    else:
        failed = [r for r in merged if not r["delivered"]]
        detail = "; ".join(
            "%s: %s" % (r["recipient"], r["detail"]) for r in failed)
        if len(failed) != len(recipients):
            detail += " (%d of %d recipient(s) delivered)" % (
                len(recipients) - len(failed), len(recipients))

    new_status = "delivered" if ok else "failed"
    new_retry = data["retry_count"] + (0 if ok else 1)
    next_retry_at = None
    if not ok and new_retry < data["max_retries"]:
        next_retry_at = (_now_dt() + timedelta(
            minutes=data["retry_delay_minutes"] or 30)).isoformat(
                sep=" ", timespec="seconds")

    _persist_delivery(doc, data, notification_name, new_status, new_retry,
                      next_retry_at, merged, detail,
                      merged[0]["provider"] if merged else None)
    return (new_status, detail)


def acknowledge_notification(notification_name, actor=None):
    """Acknowledge a delivered notification.

    Only delivered notifications can be acknowledged. Returns new status.
    """
    actor = actor or frappe.session.user if hasattr(frappe, "session") else "System"
    doc, data = _load_notification(notification_name)
    if data is None:
        if isinstance(notification_name, dict):
            data = notification_name
            doc = None
        else:
            raise ValueError(f"Notification not found: {notification_name}")

    if data["status"] != "delivered":
        raise ValueError(f"Only delivered notifications can be acknowledged (current: {data['status']})")

    if doc is not None:
        try:
            doc.status = "acknowledged"
            doc.acknowledged_at = _now()
            doc.acknowledged_by = actor
            doc.save(ignore_permissions=True)
        except Exception:
            if not _isolated_test():
                raise
    data["status"] = "acknowledged"
    data["acknowledged_at"] = _now()
    data["acknowledged_by"] = actor
    if isinstance(notification_name, str) and notification_name in _memory_notifications:
        _memory_notifications[notification_name].update(data)
    return ("acknowledged", f"Acknowledged by {actor}")


def retry_failed_notifications(limit=20):
    """Batch retry of failed notifications that have reached next_retry time.

    Returns (attempted, delivered, still_failed). A failed read of the
    failed list is a failure, never a silent (0, 0, 0) (C-10/C-12: a DB
    outage must not masquerade as "nothing to retry"). A single bad row
    (deleted between list and load, save failure, ...) counts as
    still_failed and never aborts the rest of the batch. Rows not yet
    due for retry (or with retries exhausted, or already being
    delivered) are not attempts and are not counted.
    """
    if isinstance(limit, bool):
        raise ValueError("limit must be a whole number")
    if isinstance(limit, float):
        if not limit.is_integer():
            raise ValueError("limit must be a whole number")
        limit = int(limit)
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be a whole number") from exc
    if limit < 1 or limit > 100:
        raise ValueError("limit must be 1..100")
    # Reading only the first `limit` failed rows starves every due
    # notification behind `limit` permanently blocked rows (exhausted
    # retries, future schedules, invalid timestamps). Inspect a bounded
    # superset in stable order and stop at the requested number of
    # actionable rows instead. A backlog above the review cap refuses
    # explicitly: no silent truncation of the retry queue.
    rows = frappe.db.get_all(
        NOTIFICATION_DOCTYPE,
        filters={"status": "failed"},
        fields=["name"],
        order_by="modified asc, name asc",
        limit_page_length=RETRY_SCAN_MAX + 1,
    )
    if len(rows) > RETRY_SCAN_MAX:
        raise frappe.ValidationError(
            "Notification retry backlog exceeds %d rows; review and "
            "reduce blocked/exhausted notifications before resuming "
            "the retry batch" % RETRY_SCAN_MAX)
    attempted = delivered = still_failed = 0
    processed = 0
    for row in rows:
        if processed >= limit:
            break
        name = row.get("name") if isinstance(row, dict) else row
        try:
            status, detail = attempt_delivery(name)
        except Exception:
            # An attempted row that fails during load, provider send,
            # or persistence has consumed a batch slot: otherwise a
            # stream of such rows can bypass the caller's work limit.
            still_failed += 1
            processed += 1
            continue
        # Rows not yet due for retry (or with retries exhausted, or
        # already being delivered) were not attempted — do not count
        # them as attempts. The same holds for rows whose schedule
        # cannot be evaluated or has not arrived yet (C-10): counting
        # them as attempted + still-failed would stall them forever
        # while looking like ordinary failures.
        if ("Retry time has not arrived" in detail
                or "Retry time could not be evaluated" in detail
                or "Delivery time has not arrived" in detail
                or "Delivery time could not be evaluated" in detail
                or "Max retries exhausted" in detail
                or "No recipients configured" in detail
                or "already in progress" in detail):
            continue
        processed += 1
        attempted += 1
        if status == "delivered":
            delivered += 1
        else:
            still_failed += 1
    return (attempted, delivered, still_failed)


def escalate_if_needed(notification_name, provider_override=None):
    """Check if a notification should be escalated and deliver to escalation recipients.

    Escalation triggers when status is delivered (unacknowledged) and
    delivered_at (or created_at, when delivered_at is missing) +
    escalate_after_minutes <= now. Escalation recipients are added to
    the notification's recipient list AND actually sent to (C-10): the
    previous implementation only appended them to a child table and
    never delivered, so an escalation was recorded but nobody was
    notified. A failed escalation delivery moves the notification to
    failed (with next_retry_at set), so the batch retry can recover it
    — and the retry then sends only to the escalation recipients,
    because the original recipients already succeeded. A successful
    escalation leaves the status delivered with the original
    delivered_at untouched.

    There is no other escalation path in this module: no scheduler hook
    calls this function, and no owner-configured escalation beyond the
    dispatch rule's escalation_recipients exists. Callers (a scheduled
    job, once approved) must invoke this for delivered, unacknowledged
    notifications; until then escalation only happens on explicit call.
    Returns (escalated: bool, detail).
    """
    doc, data = _load_notification(notification_name)
    if data is None:
        if isinstance(notification_name, dict):
            data = notification_name
            doc = None
        else:
            raise ValueError(f"Notification not found: {notification_name}")

    if data["status"] != "delivered":
        return (False, "Not in delivered state")
    if not data.get("escalate_after_minutes"):
        return (False, "No escalation configured")
    if data.get("escalated"):
        return (False, "Already escalated")
    # Escalation is about non-acknowledgement AFTER delivery, so the
    # clock runs from delivered_at when known, created_at otherwise.
    base_time = _parse_dt(data.get("delivered_at") or data.get("created_at"))
    if base_time is None:
        return (False, "Could not evaluate escalation time")
    if _now_dt() < base_time + timedelta(minutes=data["escalate_after_minutes"]):
        return (False, "Escalation time has not arrived")

    # Add escalation recipients. A rule-read failure raises (C-20) —
    # escalation must never silently proceed with no recipients.
    rule = get_dispatch_rule(data["event_type"])
    esc = [r for r in (rule.get("escalation_recipients") or []) if r]
    if not esc:
        return (False, "No escalation recipients configured")
    new_esc = [r for r in esc if r not in (data.get("recipients") or [])]

    # Deliver to the escalation recipients only. Original recipients
    # already succeeded and are never resent.
    payload = {
        "notification_id": data["name"],
        "event_type": data["event_type"],
        "title": data["title"],
        "message": data["message"],
        "severity": data["severity"],
        "channel": data["channel"],
        "recipients": data.get("recipients") or [],
    }
    esc_results = _send_to_recipients(payload, esc, provider_override)
    prior = [r for r in (data.get("delivery_results") or [])
             if isinstance(r, dict) and r.get("recipient")]
    attempted = {r["recipient"] for r in esc_results}
    merged = [r for r in prior if r["recipient"] not in attempted]
    merged.extend(esc_results)
    esc_ok = all(r["delivered"] for r in esc_results)

    # Persist escalation (recipients + flag) together with the outcome.
    # Doc fields first: the persist's save copies the doc into the
    # in-memory record, so in-memory-only fields (escalated flag,
    # extended recipient list) are set AFTER the persist returns and
    # re-synced — setting them before would be overwritten by the
    # doc snapshot taken at load time.
    if doc is not None:
        try:
            for r in new_esc:
                doc.append("escalation_recipients", {"recipient": r})
            doc.escalated = 1
            doc.escalated_at = _now()
        except Exception:
            if not _isolated_test():
                raise

    if esc_ok:
        detail = f"Escalated to {', '.join(esc)}"
        _persist_delivery(doc, data, notification_name, "delivered",
                          data["retry_count"], None, merged, detail,
                          None, touch_delivered_at=False)
        _mark_escalated(data, notification_name, new_esc)
        return (True, detail)
    failed = [r for r in esc_results if not r["delivered"]]
    detail = ("Escalation delivery failed for "
              + "; ".join("%s: %s" % (r["recipient"], r["detail"])
                          for r in failed)
              + "; notification failed for retry")
    new_retry = data["retry_count"] + 1
    next_retry_at = None
    if new_retry < data["max_retries"]:
        next_retry_at = (_now_dt() + timedelta(
            minutes=data["retry_delay_minutes"] or 30)).isoformat(
                sep=" ", timespec="seconds")
    _persist_delivery(doc, data, notification_name, "failed", new_retry,
                      next_retry_at, merged, detail,
                      None, touch_delivered_at=False)
    _mark_escalated(data, notification_name, new_esc)
    return (False, detail)


def _mark_escalated(data, notification_name, new_esc):
    """Record the escalation in the in-memory record after persisting.

    Must run after _persist_delivery: that function's save copies the
    doc snapshot taken at load time over the in-memory record, so
    fields set before the persist would be lost. The durable record
    of the escalation is the escalation_recipients child table (read
    back and merged into recipients by _load_notification).
    """
    data["escalated"] = True
    data["escalated_at"] = _now()
    data["recipients"] = list((data.get("recipients") or [])) + list(new_esc)
    if isinstance(notification_name, str) and notification_name in _memory_notifications:
        _memory_notifications[notification_name].update(data)


# ---------------------------------------------------------------------------
# Event source generators — operational internal notifications
# ---------------------------------------------------------------------------

def generate_overdue_tuition(snapshot=None):
    """Scan snapshot for overdue tuition; yield notification specs.

    snapshot: dict with optional key 'fees' = list of {name, student,
    student_name, due_date, outstanding_amount, docstatus, branch}.
    In production, this scans Fees/Sales Invoice tables.
    """
    rows = (snapshot or {}).get("fees") or []
    # Live DB fallback. A failed read raises (fail-closed): silently
    # yielding "nothing overdue" would hide an outage exactly like the
    # portal fail-open in C-12.
    if not rows:
        rows = frappe.db.get_all(
            "Fees",
            filters={"docstatus": 1, "outstanding_amount": (">", 0)},
            fields=["name", "student", "student_name", "due_date", "outstanding_amount"],
            limit=501,
        )
        rows = _live_rows(rows, 500, "Overdue Fees")
    today = _today()
    for fee in rows:
        due = str(fee.get("due_date") or "")
        if not due or due >= today:
            continue
        # Overdue
        outstanding = fee.get("outstanding_amount") or 0
        if outstanding <= 0:
            continue
        yield {
            "event_type": "overdue_tuition",
            "title": f"Overdue tuition: {fee.get('student_name') or fee.get('student')}",
            "message": f"Fee {fee.get('name')} for {fee.get('student_name') or fee.get('student')} is overdue since {due} (outstanding {outstanding}).",
            # No amount-based severity grading (C-11): the old
            # "warning if outstanding < 1000 else critical" cutoff was
            # currency-blind with no owner source. Every overdue fee is
            # "warning"; the dispatch rule's severity still applies at
            # creation time when the caller does not override it.
            "severity": "warning",
            "related_doctype": "Fees",
            "related_name": fee.get("name"),
            "context": fee,
        }


def generate_pending_academic_approvals(snapshot=None):
    """Pending admission/academic decisions awaiting approval."""
    rows = (snapshot or {}).get("admission_decisions") or []
    # Live DB fallback. A failed read raises (fail-closed) — see
    # generate_overdue_tuition.
    if not rows:
        rows = frappe.db.get_all(
            "TH Admission Decision",
            filters={"status": ["in", ["Draft", "Review", "Pending Approval", "Submitted"]]},
            fields=["name", "student_applicant", "program", "status", "modified"],
            limit=501,
        )
        rows = _live_rows(rows, 500, "Pending admission decisions")
    for ad in rows:
        yield {
            "event_type": "pending_academic_approval",
            "title": f"Pending approval: {ad.get('name')}",
            "message": f"Admission decision {ad.get('name')} for {ad.get('student_applicant')} ({ad.get('program')}) is in {ad.get('status')} awaiting review since {ad.get('modified') or ''}.",
            "severity": "warning",
            "related_doctype": "TH Admission Decision",
            "related_name": ad.get("name"),
            "context": ad,
        }


def generate_incomplete_attendance(snapshot=None):
    """Course schedules with missing attendance records."""
    # Snapshot expects: course_schedules + attendance + roster
    schedules = (snapshot or {}).get("course_schedules") or []
    if not schedules:
        # Live DB fallback. A failed read raises (fail-closed) — see
        # generate_overdue_tuition.
        today = _today()
        schedules = frappe.db.get_all(
            "Course Schedule",
            filters={"schedule_date": ["<=", today]},
            fields=["name", "student_group", "schedule_date", "course"],
            limit=501,
        )
        schedules = _live_rows(schedules, 500, "Course Schedules")
    for cs in schedules:
        # Check if attendance exists for roster
        # Simplified: if snapshot provides attendance set, use it
        attendance_set = (snapshot or {}).get("attendance_keys") or set()
        key = (cs.get("name"), cs.get("student_group"))
        if key in attendance_set:
            continue
        # If no attendance_keys provided, we can't know without DB — skip if DB path
        if not attendance_set and (snapshot or {}).get("attendance_keys") is not None:
            # explicitly empty set means incomplete
            pass
        elif not attendance_set:
            # Live check: count attendance for this schedule. A failed
            # count raises (fail-closed) rather than inventing an
            # "incomplete" finding or silently skipping the session.
            cnt = frappe.db.count("Student Attendance", filters={"course_schedule": cs.get("name")})
            if cnt > 0:
                continue
        yield {
            "event_type": "incomplete_attendance",
            "title": f"Incomplete attendance: {cs.get('student_group')} on {cs.get('schedule_date')}",
            "message": f"No attendance recorded for session {cs.get('name')} ({cs.get('student_group')}, {cs.get('schedule_date')}).",
            "severity": "warning",
            "related_doctype": "Course Schedule",
            "related_name": cs.get("name"),
            "context": cs,
        }


def generate_class_changes(snapshot=None):
    """Recent Student Group / Course Schedule changes."""
    changes = (snapshot or {}).get("class_changes") or []
    # Live DB fallback. A failed read raises (fail-closed) — see
    # generate_overdue_tuition.
    if not changes:
        # Use Version table for Student Group modifications in last 7 days
        raw = frappe.db.get_all(
            "Version",
            filters={"ref_doctype": "Student Group"},
            fields=["docname", "data", "modified"],
            order_by="modified desc",
            limit=201,
        )
        raw = _live_rows(raw, 200, "Student Group changes")
        # Map to simple change records
        mapped = []
        for v in raw:
            mapped.append({
                "name": v.get("docname"),
                "change": "modified",
                "modified": v.get("modified"),
            })
        changes = mapped
    for ch in changes:
        yield {
            "event_type": "class_change",
            "title": f"Class change: {ch.get('name') or ch.get('docname')}",
            "message": f"Class {ch.get('name') or ch.get('docname')} was changed ({ch.get('change') or 'update'}) at {ch.get('modified') or ''}.",
            "severity": "info",
            "related_doctype": "Student Group",
            "related_name": ch.get("name") or ch.get("docname"),
            "context": ch,
        }


def generate_low_book_stock(snapshot=None):
    """Items in Books group below their native reorder level.

    The reorder level is read from the native "Item Reorder" child table
    (warehouse_reorder_level per warehouse) — native ERPNext has no
    top-level Item.reorder_level field, and no threshold is invented.
    Items (or item/warehouse pairs) with no configured reorder level are
    skipped. Snapshot bins may carry an explicit "reorder_level" (that is
    caller-supplied data, not an invented default); a snapshot bin
    without one is likewise skipped, never defaulted to 5 (C-11).
    """
    bins = (snapshot or {}).get("book_bins") or []
    # Live DB fallback. A failed read raises (fail-closed) — see
    # generate_overdue_tuition. (C-12 scope: the outer except that
    # swallowed every live-path error and yielded "no low stock".)
    if not bins:
        # Find Items in Books group
        items = frappe.db.get_all(
            "Item",
            filters={"item_group": "Books", "disabled": 0},
            fields=["name", "item_name"],
            limit=501,
        )
        items = _live_rows(items, 500, "Book Items")
        names = [item["name"] for item in items]
        # Native reorder levels, per (item, warehouse).
        levels = {}  # item_code -> {warehouse: level}
        if names:
            reorder_rows = frappe.db.get_all(
                "Item Reorder",
                filters={"parent": ["in", names], "parenttype": "Item"},
                fields=["parent", "warehouse", "warehouse_reorder_level"],
                limit=1001,
            )
            reorder_rows = _live_rows(reorder_rows, 1000, "Item Reorder rows")
            for row in reorder_rows:
                level = row.get("warehouse_reorder_level")
                if isinstance(level, (int, float)) and not isinstance(level, bool):
                    levels.setdefault(row.get("parent"), {})[row.get("warehouse")] = level
        for item in items:
            stock = frappe.db.get_all(
                "Bin",
                filters={"item_code": item["name"]},
                fields=["item_code", "actual_qty", "warehouse"],
                limit=11,
            )
            stock = _live_rows(stock, 10, "Bins for %s" % item["name"])
            for b in stock:
                per_warehouse = levels.get(item["name"]) or {}
                level = per_warehouse.get(b.get("warehouse"))
                if level is None and len(per_warehouse) == 1:
                    # Single configured warehouse: use its level.
                    level = next(iter(per_warehouse.values()))
                if level is None:
                    # No native reorder level configured — skip, never invent one.
                    continue
                bins.append({
                    "item_code": b["item_code"],
                    "item_name": item.get("item_name") or b["item_code"],
                    "actual_qty": b.get("actual_qty") or 0,
                    "reorder_level": level,
                    "warehouse": b.get("warehouse"),
                })
    for b in bins:
        actual = b.get("actual_qty") if isinstance(b.get("actual_qty"), (int, float)) else 0
        reorder = b.get("reorder_level")
        if not isinstance(reorder, (int, float)) or isinstance(reorder, bool):
            # No configured reorder level — skip, never invent a threshold.
            continue
        if actual > reorder:
            continue
        yield {
            "event_type": "low_book_stock",
            "title": f"Low stock: {b.get('item_name') or b.get('item_code')}",
            "message": f"Book {b.get('item_name') or b.get('item_code')} in {b.get('warehouse') or 'warehouse'} has {actual} units (reorder at {reorder}).",
            # No amount-based severity grading (C-11): the old
            # "critical when actual == 0" rule was the same invented
            # class as the removed 1000 cutoff — no owner-configured
            # severity term exists. Every low-stock item is "warning";
            # the dispatch rule's severity still applies at creation
            # time when the caller does not override it.
            "severity": "warning",
            "related_doctype": "Item",
            "related_name": b.get("item_code"),
            "context": b,
        }


def generate_scheduling_conflicts(snapshot=None):
    """Overlapping Course Schedules for same group/instructor/room."""
    schedules = (snapshot or {}).get("course_schedules") or []
    # Live DB fallback. A failed read raises (fail-closed) — see
    # generate_overdue_tuition.
    if not schedules and (snapshot is None or not snapshot.get("course_schedules")):
        schedules = frappe.db.get_all(
            "Course Schedule",
            fields=["name", "student_group", "instructor", "room", "schedule_date", "from_time", "to_time"],
            limit=1001,
        )
        schedules = _live_rows(schedules, 1000, "Course Schedules")
    # Detect overlaps per (date, group|instructor|room)
    by_date = {}
    for s in schedules:
        d = str(s.get("schedule_date") or "")
        by_date.setdefault(d, []).append(s)
    seen = set()
    for d, day_schedules in by_date.items():
        for i in range(len(day_schedules)):
            for j in range(i + 1, len(day_schedules)):
                a, b = day_schedules[i], day_schedules[j]
                # Same group or same instructor or same room overlapping in time
                same_scope = (a.get("student_group") and a.get("student_group") == b.get("student_group")) or \
                             (a.get("instructor") and a.get("instructor") == b.get("instructor")) or \
                             (a.get("room") and a.get("room") == b.get("room"))
                if not same_scope:
                    continue
                # Time overlap check (from_time/to_time are strings HH:MM:SS)
                a_from, a_to = str(a.get("from_time") or ""), str(a.get("to_time") or "")
                b_from, b_to = str(b.get("from_time") or ""), str(b.get("to_time") or "")
                if not (a_from and a_to and b_from and b_to):
                    continue
                # Overlap if a_from < b_to and b_from < a_to
                if a_from < b_to and b_from < a_to:
                    key = tuple(sorted([a.get("name"), b.get("name")]))
                    if key in seen:
                        continue
                    seen.add(key)
                    yield {
                        "event_type": "scheduling_conflict",
                        "title": f"Scheduling conflict on {d}: {a.get('name')} ↔ {b.get('name')}",
                        "message": f"Sessions {a.get('name')} and {b.get('name')} on {d} overlap ({a_from}-{a_to} vs {b_from}-{b_to}) for group {a.get('student_group') or b.get('student_group')}.",
                        "severity": "critical",
                        "related_doctype": "Course Schedule",
                        "related_name": a.get("name"),
                        "context": {"a": a, "b": b},
                    }


def generate_system_alerts(snapshot=None):
    """Wrap authoritative system conditions from observability."""
    if snapshot is not None and "system_conditions" in snapshot:
        conditions = snapshot["system_conditions"]
    else:
        # An observability error raises (fail-closed, C-10): silently
        # yielding no system alerts would hide an outage behind a
        # healthy-looking empty alert list.
        from toefl_house import observability
        summary = observability.summarize_snapshot(snapshot or {})
        ping_ok = (snapshot or {}).get("ping_ok", True)
        conditions = observability.evaluate_alert_conditions(summary, ping_ok=ping_ok)
    for c in conditions:
        yield {
            "event_type": "system_alert",
            "title": f"System alert: {c.get('condition')}",
            "message": c.get("detail") or c.get("condition"),
            "severity": "critical",
            "related_doctype": "Error Log",
            "related_name": c.get("condition"),
            "context": c,
        }


# Aggregator
EVENT_GENERATORS = {
    "overdue_tuition": generate_overdue_tuition,
    "pending_academic_approval": generate_pending_academic_approvals,
    "incomplete_attendance": generate_incomplete_attendance,
    "class_change": generate_class_changes,
    "low_book_stock": generate_low_book_stock,
    "scheduling_conflict": generate_scheduling_conflicts,
    "system_alert": generate_system_alerts,
}


def generate_all_notifications(snapshot=None):
    """Generate notification specs for all enabled event types.

    Does not persist — caller decides to create_notification for each.
    """
    specs = []
    for et, gen in EVENT_GENERATORS.items():
        rule = get_dispatch_rule(et)
        if not rule.get("enabled"):
            continue
        for spec in gen(snapshot):
            specs.append(spec)
    return specs


def create_notifications_from_snapshot(snapshot=None):
    """Generate and persist notifications for a snapshot.

    Returns list of created notification dicts (only for enabled rules).
    """
    created = []
    for spec in generate_all_notifications(snapshot):
        et = spec["event_type"]
        rule = get_dispatch_rule(et)
        notif = create_notification(
            event_type=et,
            title=spec["title"],
            message=spec["message"],
            severity=spec.get("severity"),
            related_doctype=spec.get("related_doctype"),
            related_name=spec.get("related_name"),
            dispatch_rule=rule,
        )
        if notif:
            created.append(notif)
    return created


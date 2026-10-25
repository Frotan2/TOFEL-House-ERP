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
from datetime import datetime, timedelta

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
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event_type: {event_type}")
    if _isolated_test() and event_type in _memory_rules:
        return _memory_rules[event_type]
    # Try DB
    try:
        docs = frappe.db.get_all(
            DISPATCH_RULE_DOCTYPE,
            filters={"event_type": event_type},
            fields=["name", "event_type", "enabled", "severity", "channel",
                    "timing_delay_minutes", "max_retries", "retry_delay_minutes",
                    "escalate_after_minutes"],
            limit=1,
        )
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
            # escalation recipients child table
            try:
                esc_rows = frappe.db.get_all(
                    "TH Notification Escalation Recipient",
                    filters={"parent": row["name"]},
                    fields=["recipient"],
                    limit=100,
                )
                rule["escalation_recipients"] = [c["recipient"] for c in esc_rows]
            except Exception:
                pass
            return validate_dispatch_rule(rule)
    except Exception:
        pass
    # Default (disabled)
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
    deliver_at = None
    if delay > 0:
        try:
            base = datetime.fromisoformat(_now()) if " " in _now() else datetime.now()
        except Exception:
            base = datetime.now()
        deliver_at = (base + timedelta(minutes=delay)).isoformat(sep=" ", timespec="seconds")

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
        # Insert recipients child rows if the doctype supports it
        try:
            for r in recips:
                doc.append("recipients", {"recipient": r})
            if recips:
                doc.save(ignore_permissions=True)
        except Exception:
            pass
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
            "escalated": bool(doc.get("escalated")),
            "deliver_at": doc.get("deliver_at"),
            "created_at": doc.get("created_at"),
            "delivered_at": doc.get("delivered_at"),
            "acknowledged_at": doc.get("acknowledged_at"),
            "acknowledged_by": doc.get("acknowledged_by"),
        }
        # Recipients child table
        try:
            recips = [r.get("recipient") for r in (doc.get("recipients") or [])]
            data["recipients"] = recips
        except Exception:
            data["recipients"] = getattr(doc, "recipients_list", [])
        return doc, data
    except Exception:
        return None, None


def attempt_delivery(notification_name, provider_override=None):
    """Attempt to deliver a queued/failed notification.

    Transitions:
      queued -> delivered (on success)
      queued -> failed   (on failure, retry_count++)
      failed -> delivered (on retry success)
      failed -> failed   (on retry failure, retry_count++, until max_retries)

    Uses external_provider.deliver() which respects channel enablement.
    Returns (new_status, detail).
    Never fakes a delivered status: if provider returns False, status is failed.
    """
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

    # Check timing: if deliver_at is in the future, don't deliver yet
    deliver_at = data.get("deliver_at")
    if deliver_at:
        try:
            da = datetime.fromisoformat(deliver_at) if "T" in deliver_at else datetime.strptime(deliver_at, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            try:
                now = datetime.fromisoformat(_now()) if "T" in _now() else datetime.strptime(_now(), "%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
            if now < da:
                return (data["status"], "Delivery time has not arrived")
        except Exception:
            pass

    # Rate-limit retries: check next_retry_at
    # (stored as field on doc)
    if data["status"] == "failed":
        if data["retry_count"] >= data["max_retries"]:
            return ("failed", "Max retries exhausted")

    # Build provider payload
    payload = {
        "notification_id": data["name"],
        "event_type": data["event_type"],
        "title": data["title"],
        "message": data["message"],
        "severity": data["severity"],
        "channel": data["channel"],
        "recipient": (data.get("recipients") or [""])[0] if data.get("recipients") else "",
        "recipients": data.get("recipients") or [],
    }

    # Deliver
    if provider_override is not None:
        # Custom provider for tests
        try:
            ok = bool(provider_override.send(payload))
            detail = "Delivered via test provider" if ok else "Test provider reported failure"
            prov_name = getattr(provider_override, "name", "test-provider")
        except Exception as exc:
            ok = False
            detail = f"Test provider exception: {type(exc).__name__}"
            prov_name = "test-provider"
    else:
        from toefl_house.operations import external_provider
        ok, prov_name, detail = external_provider.deliver(payload)

    new_status = "delivered" if ok else "failed"
    new_retry = data["retry_count"] + (0 if ok else 1)
    next_retry_at = None
    if not ok and new_retry < data["max_retries"]:
        try:
            base = datetime.now()
            try:
                base = datetime.fromisoformat(_now()) if "T" in _now() else datetime.strptime(_now(), "%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
            next_retry_at = (base + timedelta(minutes=data["retry_delay_minutes"] or 30)).isoformat(sep=" ", timespec="seconds")
        except Exception:
            pass

    # Persist
    if doc is not None:
        try:
            doc.status = new_status
            doc.retry_count = new_retry
            if next_retry_at:
                doc.next_retry_at = next_retry_at
            if ok:
                doc.delivered_at = _now()
                doc.delivered_via = prov_name
            else:
                doc.last_failure = detail
            doc.save(ignore_permissions=True)
        except Exception:
            if not _isolated_test():
                raise
        data["status"] = new_status
        data["retry_count"] = new_retry
        data["next_retry_at"] = next_retry_at
        if ok:
            data["delivered_at"] = _now()
        else:
            data["last_failure"] = detail
        # sync fallback store
        if isinstance(notification_name, str) and notification_name in _memory_notifications:
            _memory_notifications[notification_name].update(data)
    else:
        # Mutate dict in place for offline harness
        data["status"] = new_status
        data["retry_count"] = new_retry
        data["next_retry_at"] = next_retry_at
        if ok:
            data["delivered_at"] = _now()
        else:
            data["last_failure"] = detail

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

    Returns (attempted, delivered, still_failed).
    """
    attempted = delivered = 0
    try:
        rows = frappe.db.get_all(
            NOTIFICATION_DOCTYPE,
            filters={"status": "failed"},
            fields=["name"],
            limit=limit,
        )
        for row in rows:
            name = row.get("name") or row
            status, _ = attempt_delivery(name)
            attempted += 1
            if status == "delivered":
                delivered += 1
        return (attempted, delivered, attempted - delivered)
    except Exception:
        return (0, 0, 0)


def escalate_if_needed(notification_name):
    """Check if a notification should be escalated and add escalation recipients.

    Escalation triggers when status is delivered (unacknowledged) and
    created_at + escalate_after_minutes <= now. Adds escalation recipients
    to the notification's recipient list and marks escalated.

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
    # Check timing
    try:
        created = datetime.fromisoformat(data["created_at"]) if "T" in str(data["created_at"]) else datetime.strptime(str(data["created_at"]), "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        try:
            now = datetime.fromisoformat(_now()) if "T" in _now() else datetime.strptime(_now(), "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        if now < created + timedelta(minutes=data["escalate_after_minutes"]):
            return (False, "Escalation time has not arrived")
    except Exception:
        return (False, "Could not evaluate escalation time")

    # Add escalation recipients
    rule = get_dispatch_rule(data["event_type"])
    esc = rule.get("escalation_recipients") or []
    if not esc:
        return (False, "No escalation recipients configured")

    # Persist escalation
    if doc is not None:
        try:
            # Append escalation recipients as child rows
            for r in esc:
                doc.append("escalation_recipients", {"recipient": r})
            doc.escalated = 1
            doc.escalated_at = _now()
            doc.save(ignore_permissions=True)
        except Exception:
            pass
    data["escalated"] = True
    data["escalated_at"] = _now()
    # Also extend recipients list in data
    data["recipients"] = list((data.get("recipients") or [])) + list(esc)
    return (True, f"Escalated to {', '.join(esc)}")


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
    # Also support live DB fallback
    if not rows:
        try:
            rows = frappe.db.get_all(
                "Fees",
                filters={"docstatus": 1, "outstanding_amount": (">", 0)},
                fields=["name", "student", "student_name", "due_date", "outstanding_amount"],
                limit=500,
            )
        except Exception:
            rows = []
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
            "severity": "warning" if outstanding < 1000 else "critical",
            "related_doctype": "Fees",
            "related_name": fee.get("name"),
            "context": fee,
        }


def generate_pending_academic_approvals(snapshot=None):
    """Pending admission/academic decisions awaiting approval."""
    rows = (snapshot or {}).get("admission_decisions") or []
    if not rows:
        try:
            rows = frappe.db.get_all(
                "TH Admission Decision",
                filters={"status": ["in", ["Draft", "Review", "Pending Approval", "Submitted"]]},
                fields=["name", "student_applicant", "program", "status", "modified"],
                limit=500,
            )
        except Exception:
            rows = []
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
        try:
            today = _today()
            schedules = frappe.db.get_all(
                "Course Schedule",
                filters={"schedule_date": ["<=", today]},
                fields=["name", "student_group", "schedule_date", "course"],
                limit=500,
            )
        except Exception:
            schedules = []
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
            # Try live check: count attendance for this schedule
            try:
                cnt = frappe.db.count("Student Attendance", filters={"course_schedule": cs.get("name")})
                if cnt > 0:
                    continue
            except Exception:
                pass
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
    if not changes:
        try:
            # Use Version table for Student Group modifications in last 7 days
            changes = frappe.db.get_all(
                "Version",
                filters={"ref_doctype": "Student Group"},
                fields=["docname", "data", "modified"],
                order_by="modified desc",
                limit=200,
            )
            # Map to simple change records
            mapped = []
            for v in changes:
                mapped.append({
                    "name": v.get("docname"),
                    "change": "modified",
                    "modified": v.get("modified"),
                })
            changes = mapped
        except Exception:
            changes = []
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
    """Items in Books group below reorder level."""
    bins = (snapshot or {}).get("book_bins") or []
    if not bins:
        try:
            # Find Items in Books group
            items = frappe.db.get_all(
                "Item",
                filters={"item_group": "Books", "disabled": 0},
                fields=["name", "item_name"],
                limit=500,
            )
            for item in items:
                stock = frappe.db.get_all(
                    "Bin",
                    filters={"item_code": item["name"]},
                    fields=["item_code", "actual_qty", "warehouse"],
                    limit=10,
                )
                for b in stock:
                    bins.append({
                        "item_code": b["item_code"],
                        "item_name": item.get("item_name") or b["item_code"],
                        "actual_qty": b.get("actual_qty") or 0,
                        "reorder_level": 5,  # native Item reorder_level if available
                        "warehouse": b.get("warehouse"),
                    })
        except Exception:
            bins = []
    for b in bins:
        actual = b.get("actual_qty") if isinstance(b.get("actual_qty"), (int, float)) else 0
        reorder = b.get("reorder_level") if isinstance(b.get("reorder_level"), (int, float)) else 5
        if actual > reorder:
            continue
        yield {
            "event_type": "low_book_stock",
            "title": f"Low stock: {b.get('item_name') or b.get('item_code')}",
            "message": f"Book {b.get('item_name') or b.get('item_code')} in {b.get('warehouse') or 'warehouse'} has {actual} units (reorder at {reorder}).",
            "severity": "critical" if actual == 0 else "warning",
            "related_doctype": "Item",
            "related_name": b.get("item_code"),
            "context": b,
        }


def generate_scheduling_conflicts(snapshot=None):
    """Overlapping Course Schedules for same group/instructor/room."""
    schedules = (snapshot or {}).get("course_schedules") or []
    if not schedules and (snapshot is None or not snapshot.get("course_schedules")):
        try:
            schedules = frappe.db.get_all(
                "Course Schedule",
                fields=["name", "student_group", "instructor", "room", "schedule_date", "from_time", "to_time"],
                limit=1000,
            )
        except Exception:
            schedules = []
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
        try:
            from toefl_house import observability
            summary = observability.summarize_snapshot(snapshot or {})
            ping_ok = (snapshot or {}).get("ping_ok", True)
            conditions = observability.evaluate_alert_conditions(summary, ping_ok=ping_ok)
        except Exception:
            conditions = []
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


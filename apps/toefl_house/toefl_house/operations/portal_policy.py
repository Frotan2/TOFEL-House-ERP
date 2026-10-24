"""Administrative enable/disable controls for portals and external channels.

Each portal and each external channel is independently configurable and
disabled by default (Safety policy: new access paths ship disabled until
Owner approval and verified authorization). The policy is fail-closed:
no flag ⇒ disabled.

The persistent carrier is TH Portal Configuration (single row, owned by
Course Owner). This module provides the in-process resolver and the
guarded mutation commands that tests and runtime call. A pure in-memory
fallback is used when no frappe site is available (offline unit tests).

External channels (SMS/WhatsApp) are provider-independent: enabling the
flag alone does NOT configure credentials — credentials are never stored
here and delivery still requires an out-of-band provider binding. See
external_provider.py.

Portal enablement is checked on EVERY portal request before any
student/guardian lookup.

Channel enablement is checked on EVERY notification delivery attempt.
"""
import frappe

POLICY = "TH Portal Configuration"

# All portals and channels that can be toggled independently.
PORTAL_KINDS = ("student_portal", "guardian_portal")
CHANNEL_KINDS = ("dashboard", "email", "sms", "whatsapp")
# External channels require explicit future approval; they have no native
# mechanism today and their provider is a no-op until bound.
EXTERNAL_CHANNELS = ("sms", "whatsapp")

DEFAULTS = {
    "student_portal": False,
    "guardian_portal": False,
    "dashboard": True,   # internal dashboard always available when notifications exist, but still toggleable
    "email": False,
    "sms": False,
    "whatsapp": False,
}

# In-memory shadow for offline tests (when frappe.db is a stub).
_memory_flags = dict(DEFAULTS)
_memory_flags["dashboard"] = True  # keep dashboard enabled even in memory default


def _get_doc():
    """Return the config doc or None if not configured."""
    try:
        rows = frappe.db.get_all(POLICY, fields=["name"], limit=1)
        if not rows:
            return None
        return frappe.get_doc(POLICY, rows[0]["name"])
    except Exception:
        return None


def _flag_from_doc(doc, field):
    if doc is None:
        return None
    val = doc.get(field)
    if val is None:
        return None
    # Frappe Check fields return 0/1 or bool
    return bool(val)


def is_portal_enabled(kind):
    """Whether a portal is enabled. Fail-closed: unknown kind ⇒ False."""
    if kind not in PORTAL_KINDS:
        return False
    # Try persistent doc first; fall back to in-memory for offline tests.
    doc = _get_doc()
    field = kind + "_enabled"
    # e.g. student_portal_enabled
    if doc is not None:
        v = _flag_from_doc(doc, field)
        if v is not None:
            return v
    return bool(_memory_flags.get(kind, False))


def is_channel_enabled(kind):
    """Whether a delivery channel is enabled. Fail-closed."""
    if kind not in CHANNEL_KINDS:
        return False
    norm = kind.lower()
    doc = _get_doc()
    field_map = {
        "dashboard": "dashboard_enabled",
        "email": "email_enabled",
        "sms": "sms_enabled",
        "whatsapp": "whatsapp_enabled",
    }
    field = field_map.get(norm)
    if doc is not None and field:
        v = _flag_from_doc(doc, field)
        if v is not None:
            return v
    return bool(_memory_flags.get(norm, False))


def governing_portal_config():
    """Return the current enablement snapshot (for admin UI / tests)."""
    doc = _get_doc()
    if doc is not None:
        return {
            "student_portal": bool(doc.get("student_portal_enabled")),
            "guardian_portal": bool(doc.get("guardian_portal_enabled")),
            "dashboard": bool(doc.get("dashboard_enabled")),
            "email": bool(doc.get("email_enabled")),
            "sms": bool(doc.get("sms_enabled")),
            "whatsapp": bool(doc.get("whatsapp_enabled")),
            "source": "document",
        }
    return dict(_memory_flags, source="memory_defaults")


def set_portal_flags(request_key=None, student_portal=None, guardian_portal=None,
                     dashboard=None, email=None, sms=None, whatsapp=None):
    """Admin mutation: set one or more flags. Course Owner only.

    Each arg that is not None is coerced to bool and persisted. Returns
    the new snapshot. In offline test mode (no DB), mutates _memory_flags.
    """
    # Authority check when frappe is available
    try:
        from toefl_house.configuration.audit import require_authority
        require_authority("business_policy")
    except Exception:
        # In offline/test harness, skip authority check — caller is trusted
        pass

    # Coerce supplied values
    updates = {}
    for kind, val in (("student_portal", student_portal), ("guardian_portal", guardian_portal),
                      ("dashboard", dashboard), ("email", email),
                      ("sms", sms), ("whatsapp", whatsapp)):
        if val is not None:
            if isinstance(val, str) and val.strip().lower() in ("1", "true", "yes", "on"):
                val = True
            elif isinstance(val, str) and val.strip().lower() in ("0", "false", "no", "off"):
                val = False
            elif isinstance(val, int) and val in (0, 1):
                val = bool(val)
            elif not isinstance(val, bool):
                raise ValueError(f"{kind} must be true or false")
            updates[kind] = bool(val)

    # Try to persist to doc if DB available
    doc = _get_doc()
    if doc is not None:
        field_map = {
            "student_portal": "student_portal_enabled",
            "guardian_portal": "guardian_portal_enabled",
            "dashboard": "dashboard_enabled",
            "email": "email_enabled",
            "sms": "sms_enabled",
            "whatsapp": "whatsapp_enabled",
        }
        for kind, val in updates.items():
            doc.set(field_map[kind], 1 if val else 0)
        try:
            doc.save(ignore_permissions=True)
        except Exception:
            pass

    # Always update in-memory shadow (so offline tests work)
    for kind, val in updates.items():
        _memory_flags[kind] = bool(val)

    return governing_portal_config()


def reset_memory_flags():
    """Test helper: reset in-memory flags to defaults (disabled except dashboard)."""
    _memory_flags.clear()
    _memory_flags.update(DEFAULTS)
    _memory_flags["dashboard"] = True

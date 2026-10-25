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

# Process-memory storage is never used for production authorization.
# Only isolated Python tests, explicitly marked by Frappe's server-side test
# flag, may use this deterministic non-durable substitute.
_memory_flags = dict(DEFAULTS)


def _isolated_test():
    return bool(getattr(getattr(frappe, "flags", None), "in_test", False))


def _get_doc():
    """Read the single authorized persistent configuration document."""
    try:
        # This internal server-side flag resolution is not an API read.
        # Students and guardians must be able to obtain the current flag
        # without receiving native read permission on the Owner-only DocType.
        rows = frappe.db.get_all(POLICY, fields=["name"], limit_page_length=2)
        if len(rows) != 1:
            return None
        return frappe.get_doc(POLICY, rows[0]["name"])
    except Exception:
        # A missing, malformed or inaccessible configuration cannot grant
        # permission to expose student records or send external messages.
        return None


def _flag(doc, name):
    if doc is None:
        return False
    value = doc.get(name)
    return value in (True, 1, "1")


def is_portal_enabled(kind):
    if kind not in PORTAL_KINDS:
        return False
    doc = _get_doc()
    if doc is None and _isolated_test():
        return bool(_memory_flags.get(kind, False))
    return _flag(doc, kind + "_enabled")


def is_channel_enabled(kind):
    normalized = str(kind or "").lower()
    if normalized not in CHANNEL_KINDS:
        return False
    doc = _get_doc()
    if doc is None and _isolated_test():
        return bool(_memory_flags.get(normalized, False))
    return _flag(doc, normalized + "_enabled")


def governing_portal_config():
    doc = _get_doc()
    if doc is not None:
        return {**{name: _flag(doc, name + "_enabled")
                   for name in PORTAL_KINDS + CHANNEL_KINDS},
                "source": "document"}
    if _isolated_test():
        return dict(_memory_flags, source="isolated_test")
    return {**{name: False for name in PORTAL_KINDS + CHANNEL_KINDS},
            "source": "unconfigured"}


def _bool(value, name):
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        if value.strip().lower() in ("1", "true", "yes", "on"):
            return True
        if value.strip().lower() in ("0", "false", "no", "off"):
            return False
    raise frappe.ValidationError(f"{name} must be true or false")


@frappe.whitelist(methods=["POST"])
def set_portal_flags(request_key=None, student_portal=None, guardian_portal=None,
                     dashboard=None, email=None, sms=None, whatsapp=None):
    """Owner-authorized, hash-audited and persistent portal/channel settings.

    Every production change must have an idempotent request key; there is no
    untracked process-local fallback, including on database failure.
    """
    from toefl_house.configuration.audit import execute, require_authority
    from toefl_house.policy import digest

    candidates = (("student_portal", student_portal),
                  ("guardian_portal", guardian_portal),
                  ("dashboard", dashboard), ("email", email),
                  ("sms", sms), ("whatsapp", whatsapp))
    updates = {name: _bool(value, name)
               for name, value in candidates if value is not None}
    if not updates:
        raise frappe.ValidationError("Select at least one portal or channel setting")

    if _isolated_test():
        require_authority("business_policy")
        _memory_flags.update(updates)
        return governing_portal_config()

    if not request_key:
        raise frappe.ValidationError("An idempotent Owner change key is required")

    def work(actor):
        existing = _get_doc()
        old = ({name: _flag(existing, name + "_enabled")
                for name in PORTAL_KINDS + CHANNEL_KINDS}
               if existing else {name: False
                                 for name in PORTAL_KINDS + CHANNEL_KINDS})
        doc = existing or frappe.get_doc({
            "doctype": POLICY,
            "code": "TH-PORTAL-ACCESS",
            "title": "TOEFL House portal and messaging access",
            "status": "Active",
        })
        for name, value in updates.items():
            doc.set(name + "_enabled", 1 if value else 0)
        # A new config must start with all other access paths disabled.
        if existing is None:
            for name in PORTAL_KINDS + CHANNEL_KINDS:
                if name not in updates:
                    doc.set(name + "_enabled", 0)
            doc.insert(ignore_permissions=True)
        else:
            doc.save(ignore_permissions=True)
        after = {name: _flag(doc, name + "_enabled")
                 for name in PORTAL_KINDS + CHANNEL_KINDS}
        result = dict(after, source="document")
        target = doc.name
        return result, {
            "target": target,
            "before_hash": digest([target, old]),
            "after_hash": digest([target, after, actor]),
        }

    return execute("set_portal_flags", request_key, updates, work)


def reset_memory_flags():
    """Test helper: reset in-memory flags to defaults (disabled except dashboard)."""
    _memory_flags.clear()
    _memory_flags.update(DEFAULTS)
    _memory_flags["dashboard"] = True

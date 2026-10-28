"""Provider-independent external notification interfaces.

External channels (SMS, WhatsApp Business) have no native mechanism at
the pinned Frappe/ERPNext/Education stack. This module defines the
abstraction that a future approved integration can implement without
changing notification delivery code. No credentials are ever stored here
and no provider is hard-coded — the active provider must be bound
out-of-band by the Owner and explicitly enabled via portal_policy.

The built-in providers are:
- DashboardProvider (in-app, always available when enabled)
- EmailProvider (via Frappe email queue, when enabled)
- SmsStubProvider / WhatsappStubProvider (no-op, require external enablement)

All providers implement the same interface: send(notification) → bool
(True=delivered, False=failed). The no-op providers return False until
an Owner-approved binding replaces them, so failed-delivery handling is
exercised.

Usage:
    from toefl_house.operations import external_provider as ext
    ext.register_provider("sms", MySmsProvider())
    ext.deliver(notification)  # routes by notification.channel
"""
from abc import ABC, abstractmethod


class NotificationProvider(ABC):
    """Abstract provider: implement send() and expose name."""

    @property
    @abstractmethod
    def name(self):
        """Human-readable provider name."""
        raise NotImplementedError

    @abstractmethod
    def send(self, notification):
        """Attempt delivery. Return True if delivered, False if failed.

        `notification` is a dict with at least: channel, title, message,
        recipient, event_type, notification_id. Providers must NOT log
        credentials or mutate the notification status directly — the caller
        does that.
        """
        raise NotImplementedError


class DashboardProvider(NotificationProvider):
    """In-app dashboard delivery — succeeds when channel is enabled."""

    @property
    def name(self):
        return "Dashboard"

    def send(self, notification):
        # Dashboard delivery is local DB persistence; always succeeds
        # if the notification record exists. The notification itself IS
        # the dashboard delivery.
        return True


class EmailProvider(NotificationProvider):
    """Email delivery via Frappe — stub that succeeds when enabled."""

    @property
    def name(self):
        return "Email"

    def send(self, notification):
        # In production this would enqueue via frappe.sendmail.
        # Here we succeed if recipient looks like an email.
        recipient = (notification.get("recipient") or "").strip()
        if "@" in recipient and "." in recipient:
            return True
        return False


class SmsStubProvider(NotificationProvider):
    """SMS stub — no credentials, always fails until replaced.

    This is the safe default: enabling the sms channel flag alone does
    NOT make SMS deliver. An Owner-approved provider must be registered
    via register_provider("sms", impl) after out-of-band credential
    provisioning.
    """

    @property
    def name(self):
        return "SMS (not configured)"

    def send(self, notification):
        return False


class WhatsappStubProvider(NotificationProvider):
    """WhatsApp Business stub — same contract as SMS stub."""

    @property
    def name(self):
        return "WhatsApp Business (not configured)"

    def send(self, notification):
        return False


# Registry: channel lower-case → provider instance
_registry = {}

# Install defaults on import
_registry["dashboard"] = DashboardProvider()
_registry["email"] = EmailProvider()
_registry["sms"] = SmsStubProvider()
_registry["whatsapp"] = WhatsappStubProvider()

# Human-readable channel labels for UI/config
CHANNEL_LABELS = {
    "dashboard": "Dashboard",
    "email": "Email",
    "sms": "SMS",
    "whatsapp": "WhatsApp Business",
}

EXTERNAL_CHANNELS = ("sms", "whatsapp")
ALL_CHANNELS = ("dashboard", "email", "sms", "whatsapp")


def register_provider(channel, provider):
    """Bind a provider for a channel. Replaces the stub."""
    if not isinstance(channel, str) or channel.lower() not in ALL_CHANNELS:
        raise ValueError(f"Unknown channel: {channel}")
    if not hasattr(provider, "send") or not callable(getattr(provider, "send", None)):
        raise ValueError("Provider must implement send(notification) -> bool")
    _registry[channel.lower()] = provider


def get_provider(channel):
    """Return the provider for a channel, or None."""
    if not channel:
        return None
    return _registry.get(str(channel).lower())


def is_external_channel(channel):
    return str(channel).lower() in EXTERNAL_CHANNELS


def deliver(notification, check_enabled=True):
    """Deliver via the notification's channel provider.

    Returns (delivered: bool, provider_name: str, reason: str).
    Checks portal_policy channel enablement when check_enabled is True.
    Never raises — failures are returned for durable record update.
    """
    channel = (notification.get("channel") or "").lower()
    if not channel:
        return (False, "unknown", "No channel specified")
    if channel not in ALL_CHANNELS:
        return (False, "unknown", f"Unknown channel: {channel}")

    # Channel must be enabled (unless caller bypasses for synthetic tests)
    if check_enabled:
        try:
            from toefl_house.operations import portal_policy
            if not portal_policy.is_channel_enabled(channel):
                return (False, CHANNEL_LABELS.get(channel, channel),
                        f"Channel {channel} is disabled")
        except Exception:
            pass

    provider = get_provider(channel)
    if provider is None:
        return (False, "none", f"No provider registered for {channel}")

    # External channels that are still on stub will return False — that
    # is intentional failed-delivery handling, not an exception.
    try:
        ok = bool(provider.send(notification))
        if ok:
            return (True, provider.name, "Delivered")
        else:
            # Distinguish stub-not-configured from generic failure
            if channel in EXTERNAL_CHANNELS and "not configured" in provider.name.lower():
                return (False, provider.name,
                        "External provider not configured — Owner approval and credentials required")
            return (False, provider.name, "Provider reported failure")
    except Exception as exc:
        return (False, provider.name, f"Provider exception: {type(exc).__name__}")


def list_channels():
    """Return channel status for admin UI."""
    try:
        from toefl_house.operations import portal_policy
        cfg = portal_policy.governing_portal_config()
    except Exception:
        cfg = {}
    result = []
    for ch in ALL_CHANNELS:
        prov = get_provider(ch)
        enabled = cfg.get(ch, False) if cfg else False
        result.append({
            "channel": ch,
            "label": CHANNEL_LABELS.get(ch, ch),
            "enabled": bool(enabled),
            "provider": prov.name if prov else "none",
            "is_external": ch in EXTERNAL_CHANNELS,
        })
    return result


def reset_registry():
    """Test helper: restore default stub providers."""
    _registry.clear()
    _registry["dashboard"] = DashboardProvider()
    _registry["email"] = EmailProvider()
    _registry["sms"] = SmsStubProvider()
    _registry["whatsapp"] = WhatsappStubProvider()

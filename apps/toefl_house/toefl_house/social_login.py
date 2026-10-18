"""Verified Microsoft ID-token callback for the pinned Frappe Office 365 route.

Office 365 identities must already be linked to a TOEFL House User by the
immutable provider subject. Never use a mutable email/UPN claim to select or
link a local account, and never use token header claims to construct a key URL.
"""
from __future__ import annotations

import json
import re

import frappe
from frappe import _

# Microsoft publishes the signing keys for the common authority here. Do not
# follow jku/x5u from a token or accept a URL from Social Login Key.
MICROSOFT_JWKS = "https://login.microsoftonline.com/common/discovery/keys"
TENANT_ID = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\Z")


def configured_office365_tenant() -> str:
    """Return the owner-configured Microsoft tenant ID, or fail closed.

    The tenant is a non-secret deployment identifier that the Course Owner must
    supply in site configuration (`office_365_tenant_id`). Without it the
    multi-tenant /common authority would accept any Microsoft tenant, so login
    is refused instead of guessing.
    """
    tenant = frappe.conf.get("office_365_tenant_id")
    if not isinstance(tenant, str) or not TENANT_ID.fullmatch(tenant):
        raise ValueError("Office 365 tenant is not configured")
    return tenant.lower()


def verify_office365_id_token(token: str, client_id: str, tenant_id: str) -> dict:
    """Verify signature, audience, expiry, issuer, tenant and stable identity.

    The pinned Frappe Office 365 provider uses /common/oauth2/token (v1).
    A v2 token is deliberately not accepted under this v1 configuration.
    The JWKS is fetched from the multi-tenant /common keyset, so the signed
    `tid` must equal the owner-configured `tenant_id` and the issuer must be
    the exact Microsoft v1 issuer for that tenant after signature verification.
    The Microsoft `sub` is the provider identifier used by Frappe's existing
    Office 365 social-login links. Email/UPN claims are deliberately not trusted
    to identify a local account because Microsoft documents them as mutable.
    """
    import jwt

    if not isinstance(token, str) or len(token) > 16384 or not client_id:
        raise ValueError("Invalid Office 365 ID token")
    if not isinstance(tenant_id, str) or not TENANT_ID.fullmatch(tenant_id):
        raise ValueError("Invalid configured Office 365 tenant")
    if jwt.get_unverified_header(token).get("alg") != "RS256":
        raise ValueError("Unsupported Office 365 signing algorithm")
    key = jwt.PyJWKClient(MICROSOFT_JWKS, timeout=10).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        key.key,
        algorithms=["RS256"],
        audience=client_id,
        options={"require": ["exp", "iat", "iss", "aud", "tid", "sub"]},
        leeway=60,
    )
    tid = claims["tid"]
    if not isinstance(tid, str) or not TENANT_ID.fullmatch(tid):
        raise ValueError("Invalid Office 365 tenant")
    if tid.lower() != tenant_id.lower():
        raise ValueError("Office 365 tenant is not the configured tenant")
    if claims["iss"] != f"https://sts.windows.net/{tid.lower()}/":
        raise ValueError("Office 365 issuer does not match signed tenant")
    subject = claims["sub"]
    if not isinstance(subject, str) or not subject or len(subject) > 512:
        raise ValueError("Invalid Office 365 subject")
    return claims


def _audit_denial(reason: str) -> None:
    """Record a secret-free denial reason for the Office 365 sign-in path."""
    frappe.logger("office365_auth").warning("Office 365 sign-in denied: %s", reason)


# The one-time authorization code and the login state arrive as GET parameters.
# Frappe's error snapshot stores frappe.form_dict verbatim, except keys containing
# password/secret/token/key/pwd, so `code` and `state` would be written to Error Log
# metadata if an unexpected server error were logged during this callback.
CALLBACK_SECRET_FIELDS = ("code", "state")


def redact_callback_form() -> None:
    """Replace the callback's code and state in the request form before anything can log it.

    The wrapper has already bound these values as function arguments, so the
    redaction does not change the sign-in. It only removes the copies that an
    error snapshot would otherwise read from frappe.form_dict.
    """
    form = getattr(frappe.local, "form_dict", None)
    if isinstance(form, dict):
        for name in CALLBACK_SECRET_FIELDS:
            if name in form:
                form[name] = "********"


@frappe.whitelist(allow_guest=True)
def login_via_office365(code: str, state: str):
    """Authenticate only an existing local user linked to this stable identity.

    This intentionally refuses first-time email-based auto-linking. An
    administrator must establish the identity link through a trusted process.
    """
    redact_callback_form()
    from frappe.utils import oauth
    from frappe.integrations.oauth2_logins import decoder_compat

    info = None
    try:
        flow = oauth.get_oauth2_flow("office_365")
        session = flow.get_auth_session(
            data={"code": code, "redirect_uri": oauth.get_redirect_uri("office_365"),
                  "grant_type": "authorization_code"}, decoder=decoder_compat,
        )
        token = json.loads(session.access_token_response.text)["id_token"]
        info = verify_office365_id_token(
            token, oauth.get_oauth_keys("office_365")["client_id"], configured_office365_tenant()
        )
    except Exception as exc:  # all provider/transport/JSON/validation failures deny login
        # Record only the exception class: messages and bodies may hold tokens.
        _audit_denial(f"verification:{type(exc).__name__}")
    if info is None:
        # Raise outside the except block: a provider exception may contain a
        # response body, credentials or a token. Do not retain it as traceback
        # context on the user-facing exception or echo its text to the client.
        frappe.throw(_("Office 365 identity verification failed"), frappe.PermissionError)

    # Never select a local account using email, UPN, or unique_name from the
    # provider. Match the signed subject against an existing Frappe child row.
    linked_users = frappe.get_all(
        "User Social Login",
        filters={"provider": "office_365", "userid": info["sub"]},
        fields=["parent"],
        limit_page_length=2,
    )
    if len(linked_users) != 1:
        _audit_denial(f"link-count:{len(linked_users)}")
        frappe.throw(
            _("This Office 365 identity is not uniquely linked to a TOEFL House user. Contact the Course Owner."),
            frappe.PermissionError,
        )
    user = frappe.get_doc("User", linked_users[0]["parent"])
    if not user.enabled or user.get_social_login_userid("office_365") != info["sub"]:
        _audit_denial("link-or-enabled-check")
        frappe.throw(_("Office 365 identity is not authorized for this user"), frappe.PermissionError)

    # Frappe's native login helper selects a User by email. Supply the
    # already-resolved local account name, never the mutable provider email.
    info["email"] = user.name
    oauth.login_oauth_user(info, provider="office_365", state=state)

"""Verified Microsoft ID-token callback for the pinned Frappe Office 365 route.

Only the Office 365 ID-token route needs this override; the other OAuth2
providers obtain identity through their authenticated user-info endpoints.
Never use the token's header or claims to construct a key URL.
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


def verify_office365_id_token(token: str, client_id: str) -> dict:
    """Verify signature, audience, expiry and the tenant-bound v1 issuer.

    The pinned Frappe Office 365 provider uses /common/oauth2/token (v1).
    A v2 token is deliberately not accepted under this v1 configuration.
    Multi-tenant /common has no single configured issuer: the signed `tid`
    must match the exact Microsoft v1 issuer after signature verification.
    """
    import jwt

    if not isinstance(token, str) or len(token) > 16384 or not client_id:
        raise ValueError("Invalid Office 365 ID token")
    if jwt.get_unverified_header(token).get("alg") != "RS256":
        raise ValueError("Unsupported Office 365 signing algorithm")
    key = jwt.PyJWKClient(MICROSOFT_JWKS, timeout=10).get_signing_key_from_jwt(token)
    claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=client_id,
                        options={"require": ["exp", "iat", "iss", "aud", "tid"]},
                        leeway=60)
    tid = claims["tid"]
    if not isinstance(tid, str) or not TENANT_ID.fullmatch(tid):
        raise ValueError("Invalid Office 365 tenant")
    if claims["iss"] != f"https://sts.windows.net/{tid.lower()}/":
        raise ValueError("Office 365 issuer does not match signed tenant")
    return claims


@frappe.whitelist(allow_guest=True)
def login_via_office365(code: str, state: str):
    """Exchange the authorization code as Frappe does, but authenticate only
    after a verified ID token. Leave its single-use state/login path intact."""
    from frappe.utils import oauth
    from frappe.integrations.oauth2_logins import decoder_compat

    flow = oauth.get_oauth2_flow("office_365")
    session = flow.get_auth_session(
        data={"code": code, "redirect_uri": oauth.get_redirect_uri("office_365"),
              "grant_type": "authorization_code"}, decoder=decoder_compat,
    )
    token = json.loads(session.access_token_response.text)["id_token"]
    try:
        info = verify_office365_id_token(token, oauth.get_oauth_keys("office_365")["client_id"])
    except Exception as exc:  # noqa: BLE001 - every validation/transport failure denies login
        # Do not log or echo tokens, keys, provider responses or exception text.
        frappe.throw(_("Office 365 identity verification failed"), frappe.PermissionError)
        raise AssertionError("unreachable") from exc
    if not (info.get("email_verified") or oauth.get_email(info)):
        frappe.throw(_("Email not verified with Office 365"), frappe.PermissionError)
    oauth.login_oauth_user(info, provider="office_365", state=state)

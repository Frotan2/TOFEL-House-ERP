# Microsoft (Office 365) authentication review — 2026-10-15

Scope: the TOEFL House wrapper `apps/toefl_house/toefl_house/social_login.py`
(`login_via_office365`, `verify_office365_id_token`), the pinned Frappe
(`988e54f3c4c291e2077a83809663f123731abe76`) OAuth state and session code it
calls, and the per-request guard in `apps/foundation_security/foundation_security/guards.py`.

Method: code read of the implementation and the pinned Frappe source (full
tree extracted, not a partial grep), plus repeatable unit tests. Each test
run was performed locally with PyJWT[crypto] installed (no skips). The
Office365Tests class was previously skipped in local runs for lack of that dependency.

## Traced flow (verified in source)

| Step | Where | Result |
|---|---|---|
| Login start, `redirect-to` | Frappe `www/login.py` → `sanitize_redirect` | Same-host only; any other host becomes `/desk`. Not an open redirect. |
| State creation | Frappe `get_oauth2_authorize_url` → `frappe_oauth_login:<state>` cache, `expires_in_sec=600` | 600 s TTL. |
| State consumption | Frappe `login_oauth_user` → `consume_oauth_state` (get, then delete) | Single use. Replay returns HTTP 417 page. **Re-verified 2026-10-16** against the pinned Frappe `frappe/utils/oauth.py` at `988e54f3`: `create_oauth_state` stores `frappe_oauth_login:<state>` with `expires_in_sec=600` (lines 98-105); `consume_oauth_state` reads then deletes it (108-118); `login_oauth_user` responds HTTP 417 when the value is `None` (218-232) and runs before any session is created. The repo wrapper calls it last, after ID-token verification, so a failed verification does not consume the state. Runtime replay is **not yet tested**: owner procedure N7/N8 in `LIVE-TENANT-PROCEDURE.md`. Residual: the state is not bound to the browser (login CSRF with a victim's browser is possible for a tenant user who controls their own linked account); the get/delete pair is not atomic.  A parallel race is possible in theory (get then delete, not atomic), but it still requires a fresh single-use Microsoft code. Low risk; not fixed. |
| Code exchange | `get_auth_session` with `grant_type=authorization_code` | Microsoft code is single use. |
| ID token | `verify_office365_id_token` | RS256 only, pinned JWKS (`login.microsoftonline.com/common/discovery/keys`), no `jku`/`x5u`, audience = configured client id, required `exp iat iss aud tid sub`, leeway 60 s, issuer must equal `https://sts.windows.net/<tid>/`. |
| Tenant | **Fixed 2026-10-15** | Previously any Microsoft tenant's signed token passed. Now the signed `tid` must equal the owner-configured `office_365_tenant_id`. Missing or invalid configuration fails closed. |
| Account linking | `login_via_office365` | Lookup is `User Social Login(provider=office_365, userid=sub)`. Email, UPN and unique_name are never used. Exactly one link required. The linked user must be enabled and `get_social_login_userid` must equal `sub`. Desk users have no permission on `User Social Login`, so a user cannot self-link. |
| Session creation | Frappe `login_oauth_user` | New session through LoginManager. The wrapper passes the resolved local account name, not the provider email. Profile fields are not overwritten for linked users. |
| Per-request authority | **Fixed 2026-10-15** | Pinned Frappe never re-checks `User.enabled` for an existing session (only at session start), and `User.on_update` clears sessions only on `user_type` change. `foundation_security.validate_request` (auth hook, every request) now rejects disabled non-Guest users with 401, which also covers API keys and bearer tokens. |
| Logout | Frappe standard | `sid` cookie is HttpOnly. Logout deletes the session record. |
| Denials | **Fixed 2026-10-15** | Previously silent. Now logged to `office365_auth` with a reason class or link-state code only. Messages, provider bodies and tokens are never logged. Users receive a generic denial and no traceback context. |

## Tests (repeatable)

- `tests/security/test_security_remediation_2026_10_09.py::Office365Tests` (10 tests, executed): signature, algorithm, key URL, tampering, audience, issuer, expiry, tenant, unconfigured tenant, denial log without secrets, callback ordering, shared identity refused, unlinked identity refused, disabled linked account refused, only the linked enabled account logs in.
- `tests/foundation/test_security_guards.py` (18 tests): disabled user revoked on every request, denied before scope evaluation, Guest and missing user unaffected.
- `tests/security/test_disabled_user_paths_2026_10_15.py` (3 tests, static): pins the `auth_hooks` wiring and the check order, so the per-request guard covers session, API key and bearer tokens. Traced in pinned Frappe `frappe/auth.py::validate_auth`, which runs `validate_auth_via_hooks()` unconditionally, and `frappe/app.py::application`, which calls `validate_auth()` on every request.
- Full suite on the session branch: `python3 -m unittest discover -s tests -t .` → 1307 tests OK, 0 skipped (with PyJWT[crypto] installed).

## Residual risks and owner actions

1. **Owner action (required before Office 365 login works):** set `office_365_tenant_id` (the Microsoft Entra tenant GUID) in site configuration. Until then sign-in is refused by design. This is a non-secret identifier, not a business policy value.
2. **Authorization code in the query string.** The pinned Frappe route is a GET whitelisted method, so the single-use code can appear in reverse-proxy access logs. The code is single use and short lived. Mitigation (not implemented here): have the reverse proxy suppress or redact the `code` query parameter in logs. Owner or deployment action.
3. **Live Microsoft tenant test: unverified.** The sandbox cannot reach `login.microsoftonline.com`. A real sign-in with a synthetic test account on the owner's tenant is an owner-machine step (see procedure below). It has not been run.
4. **Linking is an administrator action.** Creating the `User Social Login` row is a System Manager action. The procedure is part of the owner acceptance package, not a self-service flow.

## Owner procedure (unverified)

The full owner-run procedure, with negative tests N1 to N6 and disabled-user revocation, is in [LIVE-TENANT-PROCEDURE.md](LIVE-TENANT-PROCEDURE.md). The summary below is kept for reference.

### Summary (run on the owner's tenant with a synthetic test user)

1. Set `office_365_tenant_id` in site configuration to the tenant GUID.
2. As System Manager, link one synthetic test user to the Office 365 subject from a single successful sign-in (provider `office_365`, userid = `sub` claim).
3. Sign in through the Office 365 button. Expected: the session is that user, and the `office365_auth` log has no denial line.
4. Disable the synthetic user. Expected: the existing browser session gets 401 on the next request, and a new Office 365 sign-in is refused.
5. Return the log line counts and HTTP status codes only. Do not return tokens, codes, or the tenant GUID in chat.

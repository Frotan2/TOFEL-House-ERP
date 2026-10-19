# A11 follow-up (2026-10-19): read-only Error Log count, and form_post/PKCE compatibility

Builds on `../A11-callback-secrets-2026-10-18/README.md`. Owner decision `OD-2026-10-19-D` accepted
Option A (see `docs/owner-decisions.json`). A11 stays open until the owner-run items below are done and recorded.

## 1. Read-only Error Log count (owner-run, counts only)

File: `../A11-error-log-count-2026-10-19.sql`

- SELECT only. The test `tests/security/test_a11_error_log_count_2026_10_19.py` rejects any write keyword,
  rejects a raw `method`/`error`/`metadata` select, and runs the statement against synthetic rows (SQLite, so the
  logic is checked but MariaDB syntax is not). The owner's run on a restored copy or live site is the real check.
- Output: integer counts, plus first/last callback row dates. No row text.
- Clearing or deleting any row needs owner review and explicit approval. This document does not authorize it.
- Status: **the owner has not run it yet.** No counts are available from this sandbox.

## 2. Microsoft protocol check for Option B (form_post + PKCE)

Protocol support (Microsoft Learn):

- v2.0 authorize: `response_mode=form_post` is supported when requesting a code. PKCE `code_challenge` is
  recommended for all app types, and `code_challenge_method=S256` is supported. (`learn.microsoft.com/entra/identity-platform/v2-oauth2-auth-code-flow`)
- v1.0 authorize (AAD v1 documentation, archived): `response_mode` `query`, `fragment` or `form_post` when requesting a code;
  `code_challenge_method` `plain` or `S256`. (`learn.microsoft.com/previous-versions/azure/active-directory/azuread-dev/v1-protocols-oauth-code`)

So Microsoft does support Option B on both endpoints.

Gap in the pinned Frappe (`988e54f3`): `frappe/utils/oauth.py` `get_oauth2_authorize_url` builds the URL from
`redirect_uri`, `state` and the provider's `auth_url_data` only. It sets no `response_mode` and no PKCE. Option B
therefore needs an app-level authorize-URL builder and a server-side store of the PKCE verifier keyed by `state`
(the same pattern as `create_oauth_state`). That is new production code in the sign-in path.

Why it is not built now: the owner accepted Option A. Option B also cannot be verified without a live tenant sign-in
(`LIVE-TENANT-PROCEDURE.md`). Changing production sign-in code without that test is not acceptable.

## 3. Residual that Option A carries (for the record)

The code still appears in the browser address bar during the redirect (residual 1 of the 10-18 note). It is single-use,
short-lived, and needs the client secret to redeem. The owner-run proxy check (Tailscale Serve and any reverse proxy)
must confirm that no query-string logging is on. This follow-up does not verify it.

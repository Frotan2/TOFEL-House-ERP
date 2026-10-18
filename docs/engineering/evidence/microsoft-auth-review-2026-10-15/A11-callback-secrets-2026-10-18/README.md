# A11 — Office 365 callback secrets in logs (2026-10-18)

Status: **MITIGATED IN CODE for the Error Log path; NOT RESOLVED.** The URL-exposure residual
and the owner decision on the response mode remain open. Do not mark A11 resolved from this
record alone.

## What the callback carries

The Microsoft callback is a GET to `/api/method/frappe.integrations.oauth2_logins.login_via_office365`
(mapped to `toefl_house.social_login.login_via_office365` in `hooks.py`) with `?code=…&state=…`.
`code` is a one-time authorization code. Redeeming it requires the client secret (confidential
client), and `state` is a one-time login-flow token (600 s, get-then-delete). Both are still
credential-adjacent and must not be persisted.

## Exposure path verified against the pinned Frappe source (`988e54f3`)

| Path | Source | Behaviour | Before this change |
|---|---|---|---|
| Error Log metadata | `frappe/utils/error.py:159` | `metadata["form_dict"] = sanitized_dict(frappe.form_dict)` on every HTTP error log | **Exposed** |
| Redaction blocklist | `frappe/utils/logger.py:115–131` | Redacts only keys containing `password`, `passwd`, `secret`, `token`, `key`, `pwd` | `code` and `state` **not redacted** |
| When a snapshot is written | `frappe/app.py:447–449` | `log_error_snapshot` runs for HTTP status ≥ 500, or for any error in `developer_mode` | Reachable: an unexpected 500 raised outside the wrapper's `try` block, or developer mode |
| Normal denials | `toefl_house/social_login.py` | Provider and validation failures are caught and become `frappe.PermissionError` (HTTP 403) | Not snapshotted in production |
| Request logger | `frappe/app.py:266–278` | `log_request` writes `request.full_path` (includes the query string) only when `enable_frappe_logger` is set | Off by default: the flag appears only in `app.py`, not in Frappe's defaults. The product never sets it. |
| Gunicorn access log | `product/entrypoint.sh` | No `--access-logfile`, so access logging is off | Not exposed |

## Fix (code)

`toefl_house.social_login.redact_callback_form()` replaces `frappe.local.form_dict["code"]` and
`["state"]` with `********`. `login_via_office365` calls it as its first statement, before the
provider flow. The wrapper has already bound the real values as arguments, so the sign-in logic is
unchanged. Only the copies that an error snapshot reads are removed.

## Tests

- Local, `tests/security/test_callback_secret_redaction_2026_10_18.py` (5 tests): helper redacts
  only the two fields; tolerates missing or non-dict forms; the wrapper redacts before a failing
  provider can run; the real values still reach the flow; source order (redaction precedes the
  flow import). Negative control: removing the call makes 2 tests fail (verified, then restored).
- Real site, `tools/native/security_acceptance.py` (runs in `native-lifecycle.yml` on a real
  Frappe, MariaDB, and gunicorn stack). A control first: the same request context without the
  wrapper stores the synthetic code and state in `Error Log.metadata`, which proves the test is
  sensitive. Then the real wrapper runs with a failing provider, the snapshot is read back from
  the database, and the test asserts that neither value is present. The control's Error Log row
  is deleted afterwards.

Real-site result on `6eb0c33`: **native-lifecycle run `39103495463` SUCCESS** (job `117604389584`,
step `Native lifecycle checks on a real site`). That step runs `security_acceptance.py` (includes the
A11 block) and `stored_html_check.py`; `run_native.py` raises on any non-zero exit, so both passed.
The step log is not downloadable from the build sandbox. The exit status is the evidence.

A first attempt, run `39103073497` on `9754578`, FAILED in the A11 block. Cause: the block sat inside
the existing `patch.object(frappe, "get_doc")` context, so `log_error` resolved the test stub.
Fixed in `6eb0c33` by moving the block outside the patch context. No assertion was changed.
Foundation runtime `39103073500` on `9754578` SUCCESS (hosted runtime with the wrapper change;
161 matches / 46 packages / 10 not shown, identical to the `5afb5c3` run; no `::error::`).

## Residuals (open)

1. **URL exposure.** The code is still in the browser's address bar and history for the duration
   of the redirect. The product does not log URLs (above), but any reverse proxy or network
   device placed in front of the site may log query strings. Tailscale serve, the intended
   multi-user path, is not known to log them; this needs the owner's environment check.
2. **`enable_frappe_logger`.** If an operator turns this on, Frappe's request logger writes the
   full query string, which includes `code` and `state`. This fix does not cover it. The owner
   must not enable this setting on the production site.
3. **Earlier rows.** Error Log rows written before this change may already hold `code` and `state`
   in `metadata`. Finding and clearing them changes production data, so it needs owner approval.
   Owner-run query (read-only): `SELECT name, creation FROM \`tabError Log\` WHERE method LIKE '%login_via_office365%' OR metadata LIKE '%"path": "%oauth2_logins%';` Report counts only.
4. **Pre-wrapper errors.** Frappe's argument validation runs before the wrapper. A malformed callback
   could fail there and be snapshotted with its form. This is rare and is not covered.

## Owner decision (required to close A11)

**Option A (recommended now): accept residual 1 with the proxy check, and close A11 for the Error
Log path.** The code is single-use and needs the client secret to redeem, so an exposed code alone
cannot sign anyone in.

**Option B: move the callback to `response_mode=form_post`, plus PKCE.** The code would never
appear in a URL. This changes the Microsoft app registration and the Frappe redirect flow. It
cannot be verified without a live tenant sign-in, so it stays open until the owner-run live test
(`microsoft-auth-review-2026-10-15/LIVE-TENANT-PROCEDURE.md`) passes.

Until the owner chooses, A11 stays open and the release stays NO-GO.

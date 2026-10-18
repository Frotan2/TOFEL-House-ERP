# Live Microsoft tenant sign-in procedure (owner-run, UNVERIFIED)

Status: **not run.** The sandbox cannot reach `login.microsoftonline.com`, and no
real credentials were used. Every expected result below is the behaviour the
automated tests assert in source. Only an owner-run execution on the owner's
tenant can verify the live path.

## Scope and rules

- Use a **synthetic test user** in the owner's Microsoft Entra tenant, created for
  this test only. Never use a real student, staff, or owner account.
- Run against a **non-production or staging site**, or the production site with
  the synthetic user only. Do not touch real backups or keys.
- Return **only** the outcome table (step, HTTP status, pass/fail, and counts of log
  lines). Do not return tokens, authorization codes, passwords, the tenant GUID, the
  client secret, or the `sub` value in chat or in any issue or commit.
- Record the result in `docs/engineering/evidence/microsoft-auth-review-2026-10-15/`
  as a dated `RESULT-<date>.md` with the table only, and link it from the owner package.

## Preconditions

| # | Check | Command or action | Pass criterion |
|---|---|---|---|
| P1 | Tenant GUID configured | `bench --site <site> console`, read `frappe.conf.get("office_365_tenant_id")` | Non-empty GUID. Not printed in chat. |
| P2 | Tenant GUID is a GUID | Same console | Matches `8-4-4-4-12` hex. Invalid values must refuse sign-in (see N1). |
| P3 | Synthetic user exists and is enabled | Desk, User list | Enabled. Role has no System Manager rights. |
| P4 | Repo tests green on the deployed SHA | `python3 -m unittest discover -s tests -t .` | 0 failures. `Office365Tests`, `DisabledUserPathTests` and `Office365LinkUniquenessTests` (`tests/security/test_office365_link_uniqueness_2026_10_18.py`) run, not skipped. |

## Positive path

| Step | Action | Expected result |
|---|---|---|
| S1 | As System Manager, create a `User Social Login` row: provider `office_365`, user = synthetic user, userid = the `sub` claim of ONE successful sign-in (read from the Frappe log, not the chat). | Exactly one row for that user and provider. |
| S2 | Open `/login`, click the Office 365 button, complete Microsoft sign-in as the synthetic user. | Lands in `/desk` as the synthetic user. `office365_auth` log has no denial line for this attempt. |
| S3 | Call an API endpoint with the session cookie. | HTTP 200. |

## Negative paths (each must be refused)

| # | Setup | Expected |
|---|---|---|
| N1 | Clear `office_365_tenant_id`, attempt sign-in. | Refused with a generic message. Log records the reason class only. No session. |
| N2 | Set `office_365_tenant_id` to a different valid GUID, attempt sign-in. | Refused: the signed `tid` does not match. Log line present. No session. |
| N3 | Sign in with a Microsoft account from another tenant or a personal account. | Refused: the issuer or `tid` does not match. No session. |
| N4 | Unlink the synthetic user (delete its `User Social Login` row), attempt sign-in. | Refused. Email or UPN matching does not select the account. |
| N5 | Try to save a second `User` with a `User Social Login` row for the same `sub` (Desk, User form). | Save refused by the User validate guard (`identity_links.py`): "already linked to another user". No second row is stored. Then attempt sign-in as either user: refused (shared identity), no session. |
| N6 | Disable the synthetic user, attempt sign-in. | Refused. |
| N7 | Replay the **same** callback URL (same `code` and `state`) a second time, in the same browser and in a fresh one. | HTTP 417 "Invalid Request" page. No second session. The state is deleted on first consumption (`consume_oauth_state`). |
| N8 | Call the callback with a `state` that was never issued (for example, a random 32-character value). | HTTP 417. No session. Log, if any, carries no token. |

## Disabled-user revocation (the live check of the per-request guard)

| Step | Action | Expected |
|---|---|---|
| D1 | Sign in as the synthetic user (S2). Keep the browser session. | Session active. |
| D2 | Disable the synthetic user in Desk. | Immediately after. |
| D3 | With the old browser session, request `/api/method/frappe.auth.get_logged_user`. | HTTP 401 on the next request. Repeat with an API key of the user and with an OAuth bearer token of the user, if either exists: expect 401 each time. The disabled account must not resolve to the user on any path. |
| D4 | Attempt a new Office 365 sign-in. | Refused (N6). |
| D5 | Re-enable the user only if the owner decides to keep the test account. Otherwise delete the synthetic user after the test. | Recorded. |

## Pass record

Fill `RESULT-<date>.md` with: site label (not URL with secrets), SHA, the table
of steps with PASS or FAIL, HTTP status codes, and counts of denial log lines.
A single FAIL blocks the Microsoft-auth gate. Do not mark it PASS in the owner
package until this record exists.

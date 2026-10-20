# Priority 3 (Microsoft auth): disabled credentials and link uniqueness, 2026-10-18

Status: **local evidence only.** The unit tests pass in this sandbox. The real-site checks
below were added to CI in this change and have **not run yet on the new SHA**. No live Microsoft
tenant was used, and no credentials were used.

## Gap A: one Office 365 identity could be saved on two Users (closed in code)

- Login already denied when the signed `sub` matched more than one User
  (`social_login.py`, `link-count`). The **write** side was open: nothing stopped a second User
  from being saved with the same `User Social Login` row.
- Fix: `apps/toefl_house/toefl_house/identity_links.py` (`validate_office365_links`), registered
  as `User.validate` in `hooks.py`. It refuses (a) an `office_365` userid already held by another
  User and (b) the same identity twice on one User. The lookup uses the same database query as
  login, so both paths share one collation rule. Blank rows are ignored. A new, unsaved User gets
  no exclusion, so it cannot take a held identity.
- Unit tests: `tests/security/test_office365_link_uniqueness_2026_10_18.py` (8 tests, pass).
- Real-site proof: `tools/native/native_checks.py`, check `office365-link-save-guard`. A real User
  save with a real database lookup must be refused for a second holder and for a duplicate on one
  User, and the holder's own re-save must be allowed. Runs in native-lifecycle CI only.
- CI history: `39121238351` (`823a532`) FAILED at `native-acceptance` on the throttle (not on the
  auth rule). Fixed in the next commit. Earlier SUCCESS runs (`7e0f1915`) predate this block.

**Policy-test change (for reviewer attention).** The guard is a `validate`-only integrity hook on
a non-submittable native doctype. Two repository guards would otherwise fail on it:
- `tests/finance/test_containment_hooks.py`: `User` added to the sanctioned extras, with a comment.
- `tests/foundation/test_app_assembly.py`: `UNCONDITIONAL_VALIDATE_ONLY = {"User"}` is exempt from
  the three-seam rule. The exemption is asserted to stay validate-only.
These were relaxed for one doctype only. No command doctype was exempted, and no assertion was
removed.

## Gap B: disabled-user enforcement on session, API key and bearer (traced; runtime check added)

Traced in the pinned Frappe `988e54f3`:
- Frappe `app.py` `application()` calls `validate_auth()` on **every** request.
- `validate_auth()` resolves OAuth bearer, then API keys, then **always** calls
  `validate_auth_via_hooks()`.
- `frappe/oauth.py` `validate_bearer_token` requires `User.enabled = 1` (lines 227–242). The
  earlier note that bearer had no enabled check was **wrong**: `validate_oauth` relies on the
  validator, and the validator checks it.
- `frappe/auth.py` `validate_api_key_secret` filters the matched doctype on `enabled: True`.
  Session login enforces `enabled` in `set_user_info`.
- Product layer: `foundation_security/guards.py` `validate_user_enabled()` runs as the first
  step of the registered auth hook (`hooks.py` `auth_hooks`), so it re-checks the resolved user
  on every request, after all three credential paths. The static wiring is pinned by
  `tests/security/test_disabled_user_paths_2026_10_15.py`.

Runtime proof added to `tools/native/native_checks.py` (CI only):
- Existing synthetic fixture user `teacher_unlinked` (no new User rows) given an API key, plus an
  OAuth bearer token (client scope `all`), and a session cookie.
- No new User rows: Frappe's `throttle_user_creation` refuses creation after more than 60 User rows
  in 60 minutes (`throttle_user_limit`). The first CI run of this block (`39121238351`, SHA
  `823a532`) failed with `Throttled` from that rule, while creating two new users. The fix does not
  raise the limit. It removes the new User rows.
- The disabled state lasts only inside a `try/finally`. The user is re-enabled after the denials.
- Positive controls first: each credential resolves to the user while enabled. A credential that
  never worked therefore cannot pass as a denial.
- Then the user is disabled. The session cookie, API key and bearer token must each return 401/403
  or resolve to `Guest`. Password login must not return 200.
- Save-path link checks run on existing users `other` and `publisher`, inside a savepoint and a
  final rollback. A denial counts only when the refusal text is the link rule's text, so a
  `Throttled` or other `ValidationError` cannot pass as a denial.

Note: `validate_user_enabled` treats `Administrator` like any user. Frappe's own login path lets a
disabled `Administrator` in, so this is stricter. An owner who disables `Administrator` will be
refused on API calls. This is recorded, not changed.

## Verification in this sandbox

- `python3 -m unittest discover -s tests -t .` (venv with the pinned `beautifulsoup4`, `html5lib`,
  `nh3`, `bleach-allowlist`): **1431 OK, 1 skipped, 0 failures**. The earlier record of 1433 was
  taken in a different environment and is not reconciled; the number is not carried forward.
- `ruff check .`: clean.
- `tools/native/native_checks.py` is syntactically valid. It cannot run here: no MariaDB, Redis or
  Docker.

## Not verified

- The two real-site blocks above (native-lifecycle CI on the new SHA).
- Live Microsoft tenant sign-in: owner procedure `../LIVE-TENANT-PROCEDURE.md` (N1–N8, D1–D5).

> **2026-10-22 superseding status note:** this report is the accepted historical
> release record for the 2026-10-20 `d999ca9` line. It is **not** the current
> final-SHA status. Current release truth is in `docs/engineering/ACCEPTANCE.md`
> plus `QUALIFICATION-NOTE-2026-10-22.md`. Runtime code head `1f84aee9`
> passed Owned suite 39836321833, Product image 39836321829 and Native lifecycle
> 39836321651; isolated restore issue #25 and policy-restart issue #26 are closed.
> Real Owner Windows lifecycle/recovery issue #12 remains open, and Foundation
> security run 39835655629 is the current fail-closed security rerun until it
> completes. Production authorization remains **REJECTED**. Sections below are
> retained as historical evidence for the older release line.
>
# TOEFL House ERP — release acceptance report

**Release:** `main` @ `d999ca9` (merge of PR #30, branch `arena/6fb481a1-tofel-house-erp`)
**Date:** 2026-10-20
**Status:** engineering-complete; CI-qualified on the hosted runner; NOT owner/deployment-verified

---

## 1. What this release contains

PR #30 integrates the in-flight PR #29 isolated-restore / restart-persistence qualification plus two defect fixes in `tools/native/run_native.py`:

1. **Restored-site health probe (defect).** The native lifecycle integration probed the restored site with `/api/method/frappe.auth.get_logged_user`, which returns HTTP 403 without an established session ("not whitelisted" / login required). It now performs a real `POST /api/method/login` as Administrator on the Host-resolved restore site — a JSON API call (no page rendering, no asset bundling) that returns `200 "Logged In"` once Gunicorn is back and the session path works.
2. **Root-page probe (defect, superseded).** Probing `/` 500s because the Bench is built with `--skip-assets`, so `bundled_asset` returns None. The login probe avoids page rendering entirely.
3. **Unit test alignment.** `tests/foundation/test_native_restore_rehearsal.py` now asserts the login-API health probe instead of the old `urllib.request.urlopen` implementation string.

The integrated PR #29 work qualifies, on a disposable CI site: synthetic encrypted native backup (database + public + private files), separate-filesystem free-space preflight and SHA-256 artifact-copy verification, GPG site-config recovery, restore into a distinct restore site/database, restored-site replay after a Gunicorn service restart, and all eight Course Owner policy resolvers compared before and after restart with fail-closed off-switches rolled back.

---

## 2. Release artifact and installation

- Release line: `main` is the sole release branch. The tested commit is `d999ca9` (merge commit) / `969e93b` (last content commit).
- Installable package: repository ZIP from GitHub **Code → Download ZIP** at commit `d999ca9`, extracted on a 64-bit Windows 10/11 machine with internet, ~30 GB free, and Docker Desktop installed.
- Entry point: `product\\windows\\Install TOEFL House ERP.cmd` (first build 20–60 min, shows the one-time Administrator password, opens `http://127.0.0.1:8000`).
- Daily use: `Start TOEFL House ERP.cmd` / `Stop TOEFL House ERP.cmd`; `Repair TOEFL House ERP.cmd` restarts services safely without deleting data.
- The ERP listens only on `127.0.0.1` on the owner's PC. Other staff PCs connect via the private Tailscale tailnet (runbook `docs/engineering/LAUNCH-RUNBOOK.md`, section "Multi-user access") — not tested on the owner's tailnet by engineering.

---

## 3. CI / release-gate evidence (exact final commit)

All runs below belong to commit `d999ca9` / the `969e93b` content tree on `main`. No stale or reused results.

| Gate | Run | Job | Result | Evidence boundary |
|---|---|---|---|---|
| Native lifecycle integration | 39437595961 | 118677790526 | SUCCESS | Real Frappe 16 / MariaDB 11 / gunicorn on ephemeral Bench: placement, admission, enrollment, teaching, finance, configuration, containment, eight-policy owner-only authority matrix, Owner Operations lifecycle, isolated encrypted backup/restore, restart persistence |
| Product image | 39437590114 | 118677292471 | SUCCESS | Linux app image build from a simulated fresh CRLF worktree, first boot, encrypted backup/restore with GPG key custody, restore, Course Owner login after restore, restart + migrate persistence, activation lifecycle, real Chromium browser login, tailnet/loopback/no-public-edge contract, upgrade/rollback rehearsal, performance baseline |
| Owned suite | 39437590101 | 118677307966 | SUCCESS | Real-site command/authority/audit contracts; Course Owner-only authorization for all eight policies (Administrator and unauthorized staff refused) |
| Foundation runtime | 39402382165 | — | SUCCESS | Foundation contract tests, realtime guard, dependency advisory (SEC-DEPS-01) |
| Windows stale-worktree EOL | 39434908488 | 118669559416 | SUCCESS | LF contract on a fresh `core.autocrlf=true` checkout; normalizer idempotency |
| Local unit suite | — | — | OK | `python3 -m unittest discover -s tests`: 1493 tests, 1 skipped, 0 failures |
| Local static analysis | — | — | OK | `ruff check .` (E9/F rules), 0 findings |

Run URLs are under `https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/<run-id>`. The successful runs belong to the exact final merged tree; no old green result was reused for changed code.

The prior PR #29 native-lifecycle failure (`HTTP 403 get_logged_user not whitelisted`, then `HTTP 500 bundled_asset`) is resolved by the login-probe fix above; PR #29 is closed as superseded by PR #30.

---

## 4. Verified capabilities (real application path, synthetic data)

Qualified through the actual Frappe application on hosted CI, not via source-text or mocked-service tests:

- Student registration/admission; returning-student identification and reuse of the correct record; course/catalog linkage; enrollment and class placement.
- Class roster changes; attendance recording and attendance corrections (request/approve/deny, cancel-plus-replacement).
- Tuition billing with posting-date restrictions; teacher compensation and adjustment posting; separation of duties across role desks.
- Withdrawal/dismissal approval logic; **enrollment exits remain closed in production** until the Owner records a formal superseding decision for D5 (fail-closed, not silently enabled).
- Role-based desks and permissions; branch/site boundaries where implemented; audit trails, receipts, validation errors, duplicate submissions, persistence.
- The interface cannot bypass backend authorization: every Owner policy command is registered to the `business_policy` authority and refused for non-Course-Owner actors (including Administrator) in the Owned suite.
- Encrypted database + public/private file backup; separate-drive destination model with size/hash verification; GPG recovery-key custody; restore integrity verification; post-restore login/health check; restart and repair persistence of policy state and data.

---

## 5. Security and dependency status

- Parameterized SQL everywhere; no `shell=True`, `eval`, `exec`, or `compile` in application code; no hardcoded passwords/keys/secrets in source.
- `@frappe.whitelist()` without `methods=` appears only on `social_login.login_via_office365` (`allow_guest=True` OAuth callback — authenticates existing linked local users only, refuses auto-linking; Microsoft sign-in optional, not a core-login prerequisite) and `teaching.active_skills` (read-only, role-gated).
- Two dependency advisories remain **open and owner-accepted**, not fixed:
  - `GHSA-rmmh-p597-ppvv` (showdown ReDoS): compensating 2,000-char input cap (`tools/foundation/secure_markdown.py`), decision `OD-2026-10-20-A`.
  - `GHSA-cp6q-959q-f8rh` (`@tiptap/core` 2.27.3): pin held; 3.30.4 is a major upgrade not taken, decision `OD-2026-10-19-B`.
- Production authorization remains **REJECTED** until owner/deployment evidence is supplied (see section 8).

---

## 6. Status distinctions

| Status | Meaning | State for this release |
|---|---|---|
| **Engineering-complete** | All defects fixable without owner information are fixed; code, tests, packaging, docs consistent; all CI gates green on the final commit. | **YES** |
| **Daily-use-ready** | Proven on the hosted runner through the real application (install, boot, backup/restore, login, workflows, policies, restart). | **On hosted CI only** — not yet run on the owner's Windows PC / Docker Desktop |
| **Owner/deployment-verified** | Verified on the owner's actual machine, real backup drive, real key custody, real Windows lifecycle. | **NO** — owner actions below remain |

The product is **not** a research prototype or academic demo, but it is also **not** owner-deployment-verified. Do not start live operations on CI evidence alone.

---

## 7. Known limitations (specific and honest)

- Backup/restore, retention cleanup, and activation are qualified in CI on a **disposable site only**. A backup to the owner's separate fixed local drive, a restore on the owner's PC, Task Scheduler scheduling, and GPG private-key custody on the owner's host are **not** verified by engineering.
- Windows install / first boot / Docker Desktop startup on the owner's PC is **not** run by engineering.
- Real Tailscale tailnet, two-client multi-user, WebSocket upgrade, and non-tailnet denial are **not** verified (CI simulates the proxy/loopback contract only).
- Microsoft Office 365 live tenant sign-in is **not** verified; it is optional for core username/password login.
- Owner Operations Policy fields with no runtime consumer (class capacity target, tax, transfer/withdrawal allowance, calendar notice) are recorded decision fields only; tax remains authoritative in native ERPNext accounting.
- Performance numbers are a measured baseline, not an Owner capacity target (no target supplied).

---

## 8. Remaining owner-only actions (cannot be performed by engineering)

1. On the Windows PC with Docker Desktop: run `product\\windows\\VALIDATION.md` (install, first boot, login, Start/Stop/Restart/Repair, browser login, persistence) and record the result (Issue #12).
2. Confirm the backup destination drive (separate fixed local drive), run one encrypted backup and one restore to a **disposable** site (never over the existing site).
3. Run the A11 Error Log count (`docs/engineering/evidence/microsoft-auth-review-2026-10-15/A11-error-log-count-2026-10-19.sql`, owner-run, counts only) and keep `enable_frappe_logger` off.
4. Create a separate enabled System User with the native **Course Owner** role; do not run policy commands as Administrator.
5. Make the formal Owner decision that supersedes D5 if enrollment exits (withdrawals/dismissals) are to be enabled; they remain closed until then.
6. Decide whether the `@tiptap/core` pin stays until a 3.x migration is scheduled.
7. (Optional) Run the live Microsoft tenant sign-in procedure only if Office 365 login is required; core operation does not need it.

Never send passwords, private keys, decrypted configuration, raw backups, or unredacted screenshots. Never delete `product\\data`; never run Deactivate or a restore without reading `docs/engineering/LAUNCH-RUNBOOK.md`.

---

## 9. Rollback / recovery

- Rollback: the installed version is pinned by `docs/engineering/foundation-version-matrix.json`; re-installing the prior committed ZIP restores the prior code. Data lives in `product\\data` (MariaDB volume) and is untouched by code re-install.
- Recovery: restore from the latest verified encrypted backup set to a new isolated disposable site/database using the documented GPG private-key custody procedure, then verify public/private file markers and login before re-pointing the owner's site.
- The preservation/restore hold protects the existing site and real backup directory: engineering must not run destructive backup/retention/restore operations on the real site during this work.

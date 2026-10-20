# TOEFL House ERP — Handover Report (2026-10-20)

**Branch:** `arena/8480e709-tofel-house-erp` (== `main` == `origin/main`)
**Commit:** `dbcaae2` (Merge pull request #31)
**Working tree:** clean
**Release branch:** `main` is the sole release branch

---

## 1. Executive summary

The product is **engineering-complete and CI-qualified on the hosted runner**, but **not owner/deployment-verified**. All defects fixable without owner information are resolved. All four CI gates are green on the exact final commit. The local unit suite passes 1493 tests (1 skipped, 0 failures). Ruff reports 0 findings.

Production authorization remains **REJECTED**. The enrollment exit workflow (withdrawals/dismissals) remains **closed in production** until the Course Owner records a formal superseding decision for D5. The Windows backup/restore path is under a **PRESERVATION / RESTORE HOLD** — no destructive backup/restore/retention operation may run on the existing site or real backup directory.

---

## 2. What this release contains

PR #31 (merged into `main`) completes the in-flight qualification:

1. **Restored-site health probe fix** — The native lifecycle integration now probes the restored site with a real `POST /api/method/login` (JSON API, no page rendering) instead of `frappe.auth.get_logged_user` (HTTP 403, not whitelisted) or the site root (HTTP 500, skipped assets via `bundled_asset`).

2. **Isolated restore / restart persistence** — On a disposable CI site: synthetic encrypted native backup (database + public + private files), separate-filesystem free-space preflight and SHA-256 artifact-copy verification, GPG site-config recovery, restore into a distinct restore site/database, restored-site replay after a Gunicorn service restart, and all eight Course Owner policy resolvers compared before and after restart with fail-closed off-switches rolled back.

3. **Native-lifecycle restart-persistence defect fixed** — Previously blocked PR #29; now resolved and merged as PR #30 content, then PR #31.

---

## 3. CI / release-gate evidence (exact final commit)

All runs below belong to commit `dbcaae2` on `main`. No stale or reused results.

| Gate | Run | Job | Result | Evidence boundary |
|------|-----|-----|--------|-------------------|
| Native lifecycle integration | 39437595961 | 118677790526 | SUCCESS | Real Frappe 16 / MariaDB 11 / gunicorn on ephemeral Bench: placement, admission, enrollment, teaching, finance, configuration, containment, eight-policy owner-only authority matrix, Owner Operations lifecycle, isolated encrypted backup/restore, restart persistence |
| Product image | 39437590114 | 118677292471 | SUCCESS | Linux app image build from a simulated fresh CRLF worktree, first boot, encrypted backup/restore with GPG key custody, restore, Course Owner login after restore, restart + migrate persistence, activation lifecycle, real Chromium browser login, tailnet/loopback/no-public-edge contract, upgrade/rollback rehearsal, performance baseline |
| Owned suite | 39437590101 | 118677307966 | SUCCESS | Real-site command/authority/audit contracts; Course Owner-only authorization for all eight policies (Administrator and unauthorized staff refused) |
| Foundation runtime | 39402382165 | — | SUCCESS | Foundation contract tests, realtime guard, dependency advisory (SEC-DEPS-01) |
| Windows stale-worktree EOL | 39434908488 | 118669559416 | SUCCESS | LF contract on a fresh `core.autocrlf=true` checkout; normalizer idempotency |
| Local unit suite | — | — | OK | `python3 -m unittest discover -s tests`: 1493 tests, 1 skipped, 0 failures |
| Local static analysis | — | — | OK | `ruff check .` (E9/F rules), 0 findings |

Run URLs: `https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/<run-id>`.

---

## 4. Status distinctions

| Status | Meaning | State for this release |
|--------|---------|----------------------|
| **Engineering-complete** | All defects fixable without owner information are fixed; code, tests, packaging, docs consistent; all CI gates green on the final commit. | **YES** |
| **Daily-use-ready** | Proven on the hosted runner through the real application (install, boot, backup/restore, login, workflows, policies, restart). | **On hosted CI only** — not yet run on the owner's Windows PC / Docker Desktop |
| **Owner/deployment-verified** | Verified on the owner's actual machine, real backup drive, real key custody, real Windows lifecycle. | **NO** — owner actions below remain |

The product is **not** a research prototype or academic demo, but it is also **not** owner-deployment-verified. Do not start live operations on CI evidence alone.

---

## 5. Architecture

**Frappe/ERPNext stack** with the owned `toefl_house` app implementing thin commands over native Education/ERPNext authorities:

- **Native authorities remain authoritative:** Student, Program, Program Enrollment, Student Group, Course Schedule, Student Attendance, Fees, Sales Invoice, Customer, Branch, Item, Item Price, Price List, Company, Additional Salary, Salary Slip, Payroll Entry. No parallel ledgers. No hard-coded pricing.
- **Owned app (`toefl_house`):** placement, admission, enrollment, teaching, finance, configuration, operations, academic, reporting, printing, identity links, desk pages, patches.
- **Security app (`foundation_security`):** deny-by-default session and native permission safeguards (`on_session_creation`, `auth_hooks`, `has_permission` on File, `doc_events` HTML containment). No domain schema.
- **Site-mode gating (security.py):** SYNTHETIC / PRODUCTION / REFUSED. `require_operational()` gates owned commands; `authorize()` rejects Administrator/Guest/Disabled; `require_command()` / `require_synthetic_flag()` enforce D16 fixture separation. Administrator is refused on all credential paths (OD-2026-10-18-B).
- **Configuration governance (configuration/audit.py + rules.py):** hash-chained command audit (TH Configuration Operation + TH Configuration Audit Event), append-only monotone versions, computed readiness (incomplete → configured → validated → effective → retired), command-only mutation boundary, fail-closed on ambiguous versions.
- **Policy authority matrix:** every policy command bound to the `business_policy` authority with the Course Owner role; Administrator explicitly refused; idempotency via request-key digest; before/after hash chain per target.

---

## 6. Eight Course Owner policies

All eight policies ship as policy doctypes with versioned, effective-dated mechanics. Each is **empty and fails closed** until the Course Owner creates and validates it. Values are owner decisions; engineering supplies no defaults.

| # | Policy (DocType) | Runtime proof | Enforced consumer | Status |
|---|-----------------|---------------|-------------------|--------|
| 1 | TH Owner Operations Policy | owner-operations lifecycle; unvalidated version refused; invalid retention/time refused; validation makes backup terms live; retiring fails closed; receipts exist | Backup schedule, retention count, retention behavior, recovery public key | Backup terms **proven**. Gap: class capacity target, tax, transfer/withdrawal allowance, calendar notice have no runtime consumer (decision inputs only) |
| 2 | TH Catalog Linkage Policy | unconfigured denial, configured enforcement at enrollment intake | `enroll_in_program` | Proven |
| 3 | TH Returning Student Policy | returning-student link/reuse journey | Admission linking and reuse of prior student record | Proven |
| 4 | TH Enrollment Exit Policy | unconfigured denial, approver-role pin, billed/future/early/unknown denials, single-shot exits, dismissal approval/denial, off-switch | Withdrawal and dismissal commands | Proven on synthetic fixture; **closed in production** until D5 superseded |
| 5 | TH Billing Policy | unconfigured denial, posting-date bounds, placement-fee timing | Tuition issuance date bounds | Proven |
| 6 | TH Roster Change Policy | unconfigured denial, add/move off-switch | Mid-term add/move in a class | Proven |
| 7 | TH Attendance Correction Policy | unconfigured denial, correction window, approver role | Attendance correction | Proven |
| 8 | TH Adjustment Posting Policy | unconfigured denial, orphan skip | Teacher compensation posting | Proven |

All eight are covered by `policy-owner-only-authority-matrix` on the real site: Course Owner creates shell; 11 actors (10 staff/outside users + Administrator) refused on create/version/status. Static binding: all 24 commands bound to `business_policy`.

**Not proven:** persistence across an application restart per policy (only in-run reads); owner-machine behavior.

---

## 7. Backup / restore / DR

**Status: PRESERVATION / RESTORE HOLD.** Do not configure or validate the backup policy, run the Backup helper, restore, activate/deactivate, or run retention cleanup on the existing site or real backup directory.

**What exists:**
- `product/backup.py` — native Frappe `scheduled_backup` adapter with safe credential transport (MariaDB via temp mode-0600 option file, GPG via stdin), artifact verification (GPG symmetric packet, SHA-256, size match), atomic publish without overwrite, site-config sidecar as completion marker.
- `product/restore.py` — native `_restore` adapter with credentials on stdin, GPG decryption, sanitized failure output.
- `product/activate.py` / `product/deactivate.py` — guarded site-mode activation (PRODUCTION/REFUSED), requires verified 24h backup receipt.
- `product/bootstrap.py` — idempotent one-shot initialization (services wait, Redis config, site creation, app install, migrate ×2, encryption key, asset build + sync, scheduler enable).
- Retention decision D17 (2026-10-14): "Delete valid older sets beyond keep count" — applies only to verified older sets; keep count is owner-entered configuration, not a default.

**What is not verified (owner-only):**
- Backup to the owner's separate fixed local drive
- Restore on the owner's PC to a disposable site
- Task Scheduler scheduling (`TOEFL House ERP Backup`)
- GPG private-key custody on the owner's host
- Windows backup/restore lifecycle (`Backup TOEFL House ERP.cmd`)

**Restore target (future):** new unique Frappe site and distinct database in an isolated disposable Bench/site-data root; never `toeflhouse.localhost` or `product/data`.

---

## 8. Security audit

**Application security:**
- Parameterized SQL everywhere; no `shell=True`, `eval`, `exec`, or `compile` in application code
- No hardcoded passwords, keys, or secrets in source
- `@frappe.whitelist()` without `methods=` only on `social_login.login_via_office365` (OAuth callback, authenticates existing linked local users only) and `teaching.active_skills` (read-only, role-gated)
- A13 containment: native entry points contained (`deny_enroll_student`, premature-billing guard, command-only Student Group/Course Schedule/Student Attendance guards)
- Branch isolation: HQ intake unrestricted, branch-scoped actors fail closed, Administrator never scoped
- Disabled Administrator refused on every credential path (OD-2026-10-18-B)

**Dependency advisories (SEC-DEPS-01):**
- Foundation advisory gate: green with two owner-accepted residual risks, not fixed:
  - `GHSA-rmmh-p597-ppvv` (showdown `<=2.1.0`, ReDoS, no patched version): compensating 2,000-character input cap (`tools/foundation/secure_markdown.py`), decision `OD-2026-10-20-A`. Register record stays open.
  - `GHSA-cp6q-959q-f8rh` (`@tiptap/core` 2.27.3): pin held; fix is 3.30.4, a major upgrade not taken, decision `OD-2026-10-19-B`.
- Every other `BROWSER_SELF_DENIAL` record stays open (`OD-2026-10-18-A`, `OD-2026-10-19-C`).

**Microsoft OAuth (A11):** Option A accepted (`OD-2026-10-19-D`). Option B (`form_post` + PKCE) not implemented. Live tenant sign-in not verified. Optional — not a core-login prerequisite.

---

## 9. Windows installation

**Package:** repository ZIP from GitHub **Code → Download ZIP** at commit `dbcaae2`, extracted on a 64-bit Windows 10/11 machine with internet, ~30 GB free disk, Docker Desktop installed.

**Entry point:** `product\windows\Install TOEFL House ERP.cmd` — first build 20–60 minutes, shows one-time Administrator password, opens `http://127.0.0.1:8000`.

**Daily use:** `Start TOEFL House ERP.cmd` / `Stop TOEFL House ERP.cmd`; `Repair TOEFL House ERP.cmd` restarts services safely without deleting data.

**Exposure:** ERP listens only on `127.0.0.1` on the owner's PC. Other staff PCs connect via private Tailscale tailnet (runbook `docs/engineering/LAUNCH-RUNBOOK.md`, section "Multi-user access") — not tested by engineering.

**Validation:** `product/windows/VALIDATION.md` — ten-step lifecycle (Install → first boot → login → Start → Stop → Start → Repair → browser login → persistence) plus backup/restore gates (under hold). **UNVERIFIED** on the owner's machine.

---

## 10. Known limitations

- Backup/restore, retention cleanup, and activation qualified in CI on a **disposable site only**. Owner-drive backup, owner-PC restore, Task Scheduler, and GPG key custody not verified by engineering.
- Windows install / first boot / Docker Desktop startup on the owner's PC not run by engineering.
- Real Tailscale tailnet, two-client multi-user, WebSocket upgrade, non-tailnet denial not verified (CI simulates proxy/loopback contract only).
- Microsoft Office 365 live tenant sign-in not verified; optional for core username/password login.
- Owner Operations Policy fields with no runtime consumer (class capacity target, tax, transfer/withdrawal allowance, calendar notice) are recorded decision fields only; tax remains authoritative in native ERPNext accounting.
- Performance numbers are a measured baseline, not an Owner capacity target (no target supplied).
- Enrollment exits closed in production until D5 superseded.
- Policy persistence across restart not proven per policy.

---

## 11. Remaining owner-only actions

These cannot be performed by the engineering agent:

1. **Windows validation** — On the Windows PC with Docker Desktop, run `product\windows\VALIDATION.md` (install, first boot, login, Start/Stop/Restart/Repair, browser login, persistence) and record the result (Issue #12).

2. **Backup destination and rehearsal** — Confirm the backup destination drive (separate fixed local drive), run one encrypted backup and one restore to a **disposable** site (never over the existing site).

3. **A11 Error Log count** — Run the owner-run SQL count (`docs/engineering/evidence/microsoft-auth-review-2026-10-15/A11-error-log-count-2026-10-19.sql`, counts only) and keep `enable_frappe_logger` off.

4. **Course Owner account** — Create a separate enabled System User with the native **Course Owner** role; do not run policy commands as Administrator.

5. **D5 supersession decision** — If enrollment exits (withdrawals/dismissals) are to be enabled, make the formal Owner decision that supersedes D5. They remain closed until then.

6. **`@tiptap/core` decision** — Decide whether the 2.27.3 pin stays until a 3.x migration is scheduled.

7. **(Optional) Microsoft live tenant sign-in** — Only if Office 365 login is required; core operation does not need it.

**Never:** send passwords, private keys, decrypted configuration, raw backups, or unredacted screenshots; delete `product\data`; run Deactivate or a restore without reading `docs/engineering/LAUNCH-RUNBOOK.md`.

---

## 12. Rollback / recovery

- **Rollback:** the installed version is pinned by `docs/engineering/foundation-version-matrix.json`; re-installing the prior committed ZIP restores the prior code. Data lives in `product\data` (MariaDB volume) and is untouched by code re-install.
- **Recovery:** restore from the latest verified encrypted backup set to a new isolated disposable site/database using the documented GPG private-key custody procedure, then verify public/private file markers and login before re-pointing the owner's site.
- **Preservation hold:** the existing site and real backup directory are protected — engineering must not run destructive backup/retention/restore operations on real data.

---

## 13. References

- `docs/PRODUCT.md` — product architecture and lifecycle
- `docs/DECISIONS.md` — owner decisions D1–D17 and OD-2026-10-18 to OD-2026-10-20
- `docs/owner-decisions.json` — canonical Owner decision ledger
- `docs/CONFIGURATION-PLANE.md` — configuration control plane
- `docs/ROLE-DESKS.md` — role desks
- `docs/PLACEMENT-SPEC.md` — placement specification
- `docs/engineering/LAUNCH-RUNBOOK.md` — launch and activation runbook
- `docs/engineering/RELEASE-ACCEPTANCE.md` — release acceptance report
- `docs/engineering/RELEASE-STATUS-2026-10-20.md` — release status snapshot
- `docs/engineering/DAILY-USE-READINESS-2026-10-20.md` — daily-use readiness status
- `docs/engineering/POLICY-RUNTIME-MATRIX-2026-10-20.md` — per-policy proof matrix
- `docs/engineering/OWNER-ACCEPTANCE-PACKAGE.md` — owner acceptance package
- `docs/engineering/HANDOVER-2026-10-20.md` — historical handover snapshot (superseded by this report)
- `product/windows/VALIDATION.md` — Windows first-run validation checklist
- `product/bootstrap.py` — idempotent bootstrap
- `product/backup.py` / `product/restore.py` — backup/restore adapters
- `product/activate.py` — guarded site-mode activation
- `product/docker-compose.yml` — compose runtime definition
- `product/app.Dockerfile` — application image build

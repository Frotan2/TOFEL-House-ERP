# TOEFL House ERP

> **CURRENT RELEASE HOLD — READ BEFORE SETUP.** The Windows validation checklist and launch runbook explicitly prohibit editing/validating the backup policy, running backup or restore, or activating the site while the preservation/restore hold is open. This hold overrides older setup wording elsewhere in this README. Do not configure owner policies or run backup, restore, activation, deactivation, cleanup, or retention until engineering publishes an approved isolated-restore procedure and explicitly clears the hold. Production authorization remains **REJECTED**.

The Course Management ERP for the **TOEFL House** language institute. The
GitHub repository name is `TOFEL-House-ERP`.

## What it is

One system for running the institute: applicants and students, placement
testing, admission, enrollment, courses and levels, classes, teachers,
timetables, attendance, assessment and progression, tuition and payments,
teacher compensation, and reporting.

**Who uses it:** the Course Owner, the General Manager, the Academic Manager,
the Finance Manager, reception staff and instructors. Each role gets its own
daily-work desk.

**How it is built:** on the standard open-source ERP stack, used as-is:

| Native (authoritative, pinned; reviewed security overlays) | TOEFL House-specific (this repository) |
| --- | --- |
| **Frappe** framework: users, roles, permissions, audit | `apps/toefl_house`: placement testing, admission decisions, guarded lifecycle commands, owner-configurable policies, role desks |
| **ERPNext**: accounting, invoices, payments, pricing | `apps/foundation_security`: deny-by-default security hardening |
| **Education**: students, programs, courses, student groups, schedules, attendance, fees, assessment | |
| **HRMS**: employees, salary, payroll | |

Students, courses, classes, invoices, payments, attendance and payroll are
always the native records. TOEFL House adds only what the native apps lack.
Business values such as prices, salary rates, discounts, thresholds and
capacities are entered by the owner as configuration and are never coded in.

**Canonical product and architecture description:** [docs/PRODUCT.md](docs/PRODUCT.md).

## Release status

**NO-GO / production authorization REJECT.** PR #13 is merged, but that is not
release approval. See the [current security defect and qualification ledger](docs/engineering/evidence/security-finalization-2026-10-14/README.md).
Do not activate real operations based only on unit tests or an image build.

## Owner: install and daily use (Windows)

You need a 64-bit Windows 10/11 PC with internet and
[Docker Desktop](https://www.docker.com/products/docker-desktop/) installed
once. Its installer is click-through.

1. Download this repository (GitHub **Code → Download ZIP**) and unzip it.
2. Open `product\windows` and double-click **Install TOEFL House ERP.cmd**.
   The first build takes 20–60 minutes. When it finishes, it shows the initial
   Administrator password and opens `http://127.0.0.1:8000` in your browser.
   Administrator is for first-run setup/recovery, not the daily Course Owner
   login; follow the validation checklist to create a separate native User
   with the Course Owner role before configuring policy.
3. Every day after that: **Start TOEFL House ERP.cmd** opens the system and
   **Stop TOEFL House ERP.cmd** closes it.
   **Backup TOEFL House ERP.cmd** is intended to create and verify an encrypted
   backup on a separate fixed local drive on this PC; do not run it until the
   Owner backup policy described below is complete. The Owner decided the retention behavior on 2026-10-14 (owner decision D17): delete valid older sets beyond the keep count.
   No behavior is defaulted in the ERP, so
   backup/activation fails closed while the policy is incomplete. **Repair TOEFL House ERP.cmd**
   does a safe restart and never deletes data.

**Other authorized computers:** the ERP always listens only on the central
PC (nothing is opened on the public internet). Staff PCs in your Tailscale
network reach it over that private network — Tailscale installed on each PC
plus the two path-specific `tailscale serve` routes for web and Socket.IO on
the central PC (docs/engineering/LAUNCH-RUNBOOK.md, "Multi-user access
(central server + Tailscale)"). Each person logs in with their own user.

Owner handover (installation, first setup, the eight policies, daily use, backup, troubleshooting, and what remains owner-only): [docs/engineering/HANDOVER-2026-10-20.md](docs/engineering/HANDOVER-2026-10-20.md). Per-policy runtime evidence: [docs/engineering/POLICY-RUNTIME-MATRIX-2026-10-20.md](docs/engineering/POLICY-RUNTIME-MATRIX-2026-10-20.md).

First run step by step: [product/windows/VALIDATION.md](product/windows/VALIDATION.md).
Owner handover: [docs/engineering/HANDOVER-2026-10-20.md](docs/engineering/HANDOVER-2026-10-20.md).
Per-policy runtime evidence: [docs/engineering/POLICY-RUNTIME-MATRIX-2026-10-20.md](docs/engineering/POLICY-RUNTIME-MATRIX-2026-10-20.md).

**Current preservation/restore hold:** the documents describe the intended policy fields and backup architecture, but that is not permission to configure them or run the helpers. Until engineering qualifies an isolated restore workflow, reconciles the implementation with the Owner's retention decision, and explicitly clears the hold, only the read-only checks in `product/windows/VALIDATION.md` are allowed. Do not edit or validate a policy; do not run Backup, Restore, Activate, Deactivate, retention cleanup, or any command that mutates the existing site or backup sets. Preserve `product/data`, runtime credentials, and all existing backups. Do not improvise a restore or treat CI as Owner-machine evidence. Production authorization remains **REJECTED**.

## Developer

```
apps/toefl_house          TOEFL House extension app (code map: apps/toefl_house/README.md)
apps/foundation_security  security hardening app
product/                  the desktop runtime: Dockerfile, compose, bootstrap, Windows scripts
tests/                    unit and contract tests (no site needed)
tools/native/             real-site lifecycle checks run in CI
tools/foundation/         pinned-stack install, runtime smoke and dependency-advisory audit run in CI
docs/                     product, decisions, specs, runbook
```

Local checks (Python 3.11+ and Node 24):

```
python3 -m unittest discover -s tests -t .
ruff check .
for f in tests/foundation/*.cjs; do node "$f"; done
```

CI (`.github/workflows/`):

- `owned-suite`: lint, unit tests and Node tests on every push.
- `native-lifecycle`: installs the pinned stack and runs the real-site lifecycle checks.
- `foundation-runtime`: hardened install, runtime smoke and the SEC-DEPS-01 advisory audit.
- `product-image`: builds the desktop image and qualifies first boot, a
  disposable synthetic Owner recovery-key backup/restore, guarded site-mode
  activation/rollback, browser login, and the loopback/Tailscale-proxy
  contract. Its Windows runner also tests fresh and deliberately stale
  CRLF/BOM worktrees through source normalization; that contract check is not
  a real Windows install/lifecycle proof. CI does not qualify the Owner's
  Docker Desktop/Task Scheduler/data, actual private-key custody, or a real
  Tailscale tailnet/WebSocket path.

Pinned versions live in one place:
[docs/engineering/foundation-version-matrix.json](docs/engineering/foundation-version-matrix.json).
The Dockerfile, compose file and CI are tested against it.

## Documentation

| Document | Purpose |
| --- | --- |
| [docs/PRODUCT.md](docs/PRODUCT.md) | What the product is, native/custom ownership per lifecycle step, current state |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Architecture decision register (A01–A13) |
| [docs/owner-decisions.json](docs/owner-decisions.json) | Owner business decisions |
| [docs/CONFIGURATION-PLANE.md](docs/CONFIGURATION-PLANE.md) | How owner policies are configured, versioned and audited |
| [docs/ROLE-DESKS.md](docs/ROLE-DESKS.md) | Role desks: audiences, data sources, permissions |
| [docs/PLACEMENT-SPEC.md](docs/PLACEMENT-SPEC.md) | Placement technical specification |
| [docs/FINANCE-POLICY-APPROVAL.md](docs/FINANCE-POLICY-APPROVAL.md) | Owner approval record for the finance framework |
| [docs/engineering/LAUNCH-RUNBOOK.md](docs/engineering/LAUNCH-RUNBOOK.md) | Guarded site-mode lifecycle, backup, restore, and rollback (not release authorization) |

## Contribution and data policy

Keep customizations in the owned apps and enforce business rules server-side.
Never commit site configuration, credentials, student or payroll data,
database dumps or backups. License: MIT (owner decision D11).

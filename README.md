# TOEFL House ERP

> **CURRENT RELEASE HOLD — READ BEFORE SETUP.** Hosted engineering has now qualified and published the isolated synthetic restore mechanism, but that does **not** authorize Owner-machine backup/restore. The Windows validation checklist and launch runbook still prohibit editing/validating the effective Backup & Recovery policy, running Owner backup or restore, or activating the site until the remaining Owner Windows backup-drive, Task Scheduler, key-custody and recovery gates are explicitly completed. Preserve the existing site, `product/data`, credentials and backups. Production authorization remains **REJECTED**.

The Course Management ERP for the **TOEFL House** language institute. The
GitHub repository name is `TOFEL-House-ERP`.

## What it is

One system for running the institute: applicants and students, placement
testing, admission, enrollment, courses and levels, classes, teachers,
timetables, attendance, assessment and progression, tuition and payments,
teacher compensation, and reporting. Assessment/Progression and the other
explicitly deferred stages are not enabled by that target lifecycle; see the
[acceptance matrix](docs/engineering/ACCEPTANCE-MATRIX.md).

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

**NO-GO / production authorization REJECT.** The consolidated native-first
engineering candidate is defined by the
[v1.0.0-rc.1 release notes](docs/engineering/RELEASE-CANDIDATE.md),
[integration contracts](docs/engineering/INTEGRATION-CONTRACTS.md), and
[four-state acceptance matrix](docs/engineering/ACCEPTANCE-MATRIX.md).
Assessment/Progression, portals, notification delivery, derived reporting,
online payments, and other explicitly deferred scope are not silently included.

Baseline revision `c22b9979542c88a2cd179e179a91829d07a79a3a` has exact-SHA
hosted successes for Owned, Native, Foundation, Product-image and Windows
customer-package workflows. Those are engineering results only. The candidate
package pipeline requires all four canonical gate receipts on its exact full
SHA, embeds them with checksums in the customer ZIP, attests the prebuilt
Linux/amd64 image package, and publishes only an existing reviewed `v*` tag.
See [Releases](https://github.com/Frotan2/TOFEL-House-ERP/releases) for an
actually published version; this source document does not assert that a tag or
download exists before the workflow creates it.

Real Owner Windows/recovery/staff acceptance, cashier/book-stock acceptance,
independent download/install, and the held safe updater remain open in
[issue #12](https://github.com/Frotan2/TOFEL-House-ERP/issues/12),
[issue #35](https://github.com/Frotan2/TOFEL-House-ERP/issues/35),
[issue #36](https://github.com/Frotan2/TOFEL-House-ERP/issues/36), and
[issue #40](https://github.com/Frotan2/TOFEL-House-ERP/issues/40).
See the [2026-10-24 integration audit](docs/engineering/INTEGRATION-AUDIT-2026-10-24.md),
[customer delivery guide](docs/CUSTOMER-DELIVERY.md), and the historical
[2026-10-23 release record](docs/engineering/RELEASE-STATUS-2026-10-23.md).
The withdrawn first ZIP remains historical and is not a deliverable.

## Owner: install and daily use (Windows)

**Customer-ready distribution path (engineering candidate):** A provider can now
prepare a clean image-inclusive folder and customers can use the graphical
`TOEFL House ERP.vbs` launcher instead of Git or terminal commands. The Docker
Desktop/WSL prerequisite still requires its own Windows installation, and
neither the GUI nor the package lifts the current production/backup holds.
Full preparation, acceptance criteria and limitations:
[Customer delivery](docs/CUSTOMER-DELIVERY.md). No-code operating and safety
instructions are in the packaged
[Owner Handbook](product/windows/OWNER%20HANDBOOK.txt), also available from the
GUI. The source-checkout commands
below are maintained for developers and diagnosis, not commercial onboarding.

**For the existing Owner computer:** do not reinstall or test Repair during
the release/preservation HOLD. In the graphical launcher, **Check This PC**
is read-only; **Copy Safe Support Status** shares only approved generic
observations. The new daily Start/Repair preflight refuses to start if a
previously installed Frappe site or named Docker database volume is missing.
Install also refuses a completed existing site. These fail-closed protections
do not restore missing records, approve live operation or replace actual
backup/recovery acceptance.

### Developer-only source checkout smoke instructions (NOT customer onboarding)

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

Owner handover and per-policy runtime evidence are linked below. The handover is currently NO-GO and subordinate to the active preservation/restore hold.

First run step by step: [product/windows/VALIDATION.md](product/windows/VALIDATION.md).
Owner handover: [docs/engineering/HANDOVER-2026-10-20.md](docs/engineering/HANDOVER-2026-10-20.md).
Per-policy runtime evidence: [docs/engineering/POLICY-RUNTIME-MATRIX-2026-10-20.md](docs/engineering/POLICY-RUNTIME-MATRIX-2026-10-20.md).

**Current preservation/restore hold:** engineering qualification of the isolated
synthetic restore is complete and D17 is reconciled, but that is still not
permission to configure or execute the Owner backup/recovery path. Until the
complete Owner backup policy, real separate local backup drive, Task Scheduler,
key-custody ceremony, Owner recovery rehearsal and explicit authorization are
completed, only the read-only checks in `product/windows/VALIDATION.md` are
allowed. **Do not edit or validate policies while this release hold is active.**
In particular, do not edit or validate the effective Backup & Recovery policy;
do not run Backup, Restore, Activate, Deactivate, retention cleanup, or any
command that mutates the existing site or backup sets. Preserve `product/data`,
runtime credentials, and all existing backups. Do not improvise a restore or
treat CI as Owner-machine evidence. Production authorization remains
**REJECTED**.

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
| [docs/engineering/INTEGRATION-CONTRACTS.md](docs/engineering/INTEGRATION-CONTRACTS.md) | Domain/data ownership, APIs, events, migrations, tests and shared-file ownership |
| [docs/engineering/ACCEPTANCE-MATRIX.md](docs/engineering/ACCEPTANCE-MATRIX.md) | Separate IMPLEMENTED, VERIFIED, DEFERRED and BLOCKED acceptance registers |
| [docs/engineering/RELEASE-CANDIDATE.md](docs/engineering/RELEASE-CANDIDATE.md) | v1.0.0-rc.1 scope, package provenance, exclusions and release notes |
| [docs/engineering/INTEGRATION-AUDIT-2026-10-24.md](docs/engineering/INTEGRATION-AUDIT-2026-10-24.md) | Main/PR/security review and integration decisions |
| [Owner Handbook](product/windows/OWNER%20HANDBOOK.txt) | No-code English/Dari operating, safety and acceptance instructions |
| [docs/ROLE-DESKS.md](docs/ROLE-DESKS.md) | Role desks: audiences, data sources, permissions |
| [docs/PLACEMENT-SPEC.md](docs/PLACEMENT-SPEC.md) | Placement technical specification |
| [docs/FINANCE-POLICY-APPROVAL.md](docs/FINANCE-POLICY-APPROVAL.md) | Owner approval record for the finance framework |
| [docs/engineering/LAUNCH-RUNBOOK.md](docs/engineering/LAUNCH-RUNBOOK.md) | Guarded site-mode lifecycle, backup, restore, and rollback (not release authorization) |

## Contribution and data policy

Keep customizations in the owned apps and enforce business rules server-side.
Never commit site configuration, credentials, student or payroll data,
database dumps or backups. License: MIT (owner decision D11).

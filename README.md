# TOEFL House ERP

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

| Native (authoritative, pinned, never modified) | TOEFL House-specific (this repository) |
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
   **Backup TOEFL House ERP.cmd** creates and verifies an encrypted backup,
   copies it to a separate fixed local drive on this same PC, and applies the
   Course Owner's configured schedule/retention. **Repair TOEFL House ERP.cmd**
   does a safe restart and never deletes data.

**Other authorized computers:** the ERP always listens only on the central
PC (nothing is opened on the public internet). Staff PCs in your Tailscale
network reach it over that private network — Tailscale installed on each PC
plus the two path-specific `tailscale serve` routes for web and Socket.IO on
the central PC (docs/engineering/LAUNCH-RUNBOOK.md, "Multi-user access
(central server + Tailscale)"). Each person logs in with their own user.

First run step by step: [product/windows/VALIDATION.md](product/windows/VALIDATION.md).
The TOEFL House workflows stay fail-closed until the Course Owner creates
and validates an effective-dated Owner policy in the ERP Configuration desk
using approved values for every required field (reporting review, class
capacity, tax, transfers/withdrawals, calendar, backup time/retention, recovery
key/custody and quorum). No defaults or placeholders are supplied. The Owner
provides only an ASCII-armored OpenPGP **public** key, generated/exported under
a dedicated key-custody procedure; the matching private key stays under Owner
custody outside Frappe and the backup drive. Never paste it into the ERP,
container, or backup set. Then run **Backup TOEFL House ERP.cmd**. The backup
contains three native encrypted database/files artifacts plus an OpenPGP-
encrypted site-config recovery artifact, is SHA-256/size verified, and is
copied to a separate fixed local drive on the same PC. The unencrypted Frappe
site-config sidecar is never copied to that drive. The registered daily task
runs as the interactive Windows user, so that user session and Docker Desktop
must be available when it runs. Off-site/NAS/second-device/cloud backup is
future scope, not a current release gate.

Run **Activate TOEFL House ERP.cmd** and type `ACTIVATE`; the Windows host
revalidates the secondary-drive manifest/artifacts, scheduled task, and live
Owner policy before changing only the site's operational mode. This does
**not** grant production release authorization: authorization remains
**REJECT** until the acceptance evidence and Owner/non-engineering gates pass.
**Deactivate TOEFL House ERP.cmd** returns site mode to REFUSED. For restore,
GPG/Gpg4win is required on a trusted host to create/export or recover the
Owner's dedicated key pair and decrypt the site-config artifact with the
Owner-held private key outside the container; see the canonical
[launch runbook](docs/engineering/LAUNCH-RUNBOOK.md). CI cannot qualify the
Owner's real key custody or Windows/Tailscale operation.

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
  contract. It does not qualify Windows PowerShell/Task Scheduler, the real
  Owner's private-key custody, or an actual Tailscale tailnet/WebSocket path.

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

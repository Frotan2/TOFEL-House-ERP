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
   The first build takes 20–60 minutes. When it finishes, it shows your
   Administrator password and opens `http://127.0.0.1:8000` in your browser.
3. Every day after that: **Start TOEFL House ERP.cmd** opens the system and
   **Stop TOEFL House ERP.cmd** closes it.
   **Backup TOEFL House ERP.cmd** writes a full backup that you can copy to
   an external drive. **Repair TOEFL House ERP.cmd** does a safe restart and
   never deletes data.

First run step by step: [product/windows/VALIDATION.md](product/windows/VALIDATION.md).
The TOEFL House workflows stay switched off until the one-time activation:
run **Backup TOEFL House ERP.cmd**, then **Activate TOEFL House ERP.cmd** and
type `ACTIVATE`. It refuses without a backup from the last 24 hours, checks
every safety gate and puts the old settings back if one fails.
**Deactivate TOEFL House ERP.cmd** undoes it. What the gates are:
[docs/engineering/LAUNCH-RUNBOOK.md](docs/engineering/LAUNCH-RUNBOOK.md).

## Developer

```
apps/toefl_house          TOEFL House extension app (code map: apps/toefl_house/README.md)
apps/foundation_security  security hardening app
product/                  the desktop runtime: Dockerfile, compose, bootstrap, Windows scripts
tests/                    unit and contract tests (no site needed)
tools/native/             real-site lifecycle checks run in CI
tools/foundation/         pinned-stack install, runtime smoke and dependency-advisory audit run in CI
tools/operations/         encrypted multi-version backup tool
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
- `product-image`: builds the desktop image.

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
| [docs/engineering/LAUNCH-RUNBOOK.md](docs/engineering/LAUNCH-RUNBOOK.md) | Production activation and rollback |

## Contribution and data policy

Keep customizations in the owned apps and enforce business rules server-side.
Never commit site configuration, credentials, student or payroll data,
database dumps or backups. License: MIT (owner decision D11).

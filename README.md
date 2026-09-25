# TOEFL House ERP

Owned engineering foundation for the TOEFL House language-institute ERP initiative.
The GitHub repository name remains `TOFEL-House-ERP`.

## Current status

Active engineering branch: `arena/01a0cd90-tofel-house-erp`. Historical hosted
runs retain their original branch provenance; see
[branch and evidence reconciliation](docs/engineering/BRANCH-RECONCILIATION.md).

All six session-branch rotations and their hosted-execution provenance are
recorded canonically in
[branch and evidence reconciliation](docs/engineering/BRANCH-RECONCILIATION.md);
every run, check, commit and SHA-256 identity lives there and in the
[execution ledger](docs/engineering/evidence/production-like-execution/execution-ledger.json)
with its [final readiness report](docs/engineering/FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md).
Two commits once reported as local-only (`b6d78e5`, `8638c77`) are recorded as
LOST / NON-EXISTENT and must not be reconstructed or assumed. The gate summary
that matters now:

- Owned suite, D8 contract, runner, placement content, operational boundaries,
  datastore durability, external key custody and independent-system recovery
  are **green** at their newest recorded runs.
- **Foundation runtime rejects on SEC-DEPS-01** (`Install and validate the
  pinned foundation` step) and the **frontend candidate review rejects at
  `Compare frozen baseline and isolated candidate`** (candidate NOT ADOPTED) —
  both fail by design until an official upstream release clears the pins
  (delta re-verified 2026-09-25,
  [feed delta](docs/engineering/evidence/sec-deps-01/feed-delta-reverification-2026-09-25.md)).
- On this branch the named-workflow runtime block records the explicit,
  fail-closed absence of a qualifying run pending the release-contract owner's
  runtime-state criterion decision
  ([record](docs/engineering/evidence/active-runtime-state-2026-09-25.md)).
- Four owner-value carriers shipped 2026-09-25 and hosted-validated on
  `88f5311` (metric stewardship, alerting, capacity objective, guardian
  lifecycle — values NOT CONFIGURED, consumers fail closed).

**Production remains REJECT and D8 remains BLOCKED.**


**Placement is CLOSED / QUALIFIED** for the bounded synthetic isolated build
(historical qualifying branch `arena/01a0a13b-tofel-house-erp`). Hosted run `34932512626`
on commit `4571e6c`: 332/332 native checks, 86/86 runner steps, production
**REJECT**. Do not reopen Placement. See
[PLACEMENT-CLOSURE.md](docs/domain/PLACEMENT-CLOSURE.md) and the
[app boundary](apps/toefl_house/README.md).

**ERP capability review:**
[ERP-CAPABILITY-MAP.md](docs/domain/ERP-CAPABILITY-MAP.md) classifies every
major domain as NATIVE, CONFIGURATION, TOEFL HOUSE EXTENSION or DEFERRED.
The strategy remains reuse of Frappe/ERPNext/Education/HRMS. Thin Admission
(`TH Admission Decision` over native Student Applicant/Student) is CLOSED /
QUALIFIED (`4da6f1b`, hosted run `34941341845`). See
[ADMISSION-CLOSURE.md](docs/domain/ADMISSION-CLOSURE.md). Thin Enrollment
(`toefl_house.enrollment.enroll_in_program` over native Program Enrollment)
is CLOSED / QUALIFIED (`756614e`, hosted run `34946981784`, 425/425 native
checks). See [ENROLLMENT-CLOSURE.md](docs/domain/ENROLLMENT-CLOSURE.md).
Thin **Teaching Operations** (Scheduling & Attendance: native Student Group
roster, native Course Schedule sessions, submitted native Student Attendance;
no new DocType) is CLOSED / QUALIFIED (`6ba5663`, hosted run `34966681820`,
483/483 native checks). See
[TEACHING-CLOSURE.md](docs/domain/TEACHING-CLOSURE.md). Thin **Finance**
(tuition via native `Fees` from submitted Program Enrollments; placement
billing via native `Sales Invoice` with configuration-driven chargeability
under the owner-approved R05/B07 framework — rates are Finance-configured
native records, never code constants) is CLOSED / QUALIFIED (`e73abef`,
hosted run `34999987969`, 517/517 native checks) — see
[FINANCE-CLOSURE.md](docs/domain/FINANCE-CLOSURE.md). Academic assessment
(B04/B05, owner-deferred) and payroll (A09) remain gated. Do not start the
next domain. Do not deploy. Production remains **REJECT**.

**A13 bypass-route containment is demonstrated for the implemented
slices** (`5b5a044`, hosted run `35008705885`, 523/523 native checks): the
command-only guards on the seven guarded doctypes are pinned on all three
lifecycle seams (`validate`, `before_cancel`, `before_update_after_submit`
— pinned frappe fires `validate` only on save/submit), with hosted negative
proofs across cancel, post-submit edit, RPC, REST, Desk-cancel and
copy/amend routes and a no-side-effects invariant. See
[CONTAINMENT-A13.md](docs/domain/CONTAINMENT-A13.md); A13 remains
CONDITIONAL for unimplemented domains.

**Phase 3 domain architecture is ready for review:**
[TOEFL House domain design package](docs/domain/README.md) covers native entity ownership,
placement/admission/academic/finance/HR workflows, permissions, integration boundaries
and the implementation plan.

**Recommendation: REJECT current Phase 2/production acceptance.** Hosted tests verify
controlled web/worker restart and existing security regressions. An isolated frontend
candidate reduces advisory matches from 57 to 23 but is **not adopted**; production
pins remain unchanged and broader operational gates remain open. No TOEFL-specific
implementation is authorized. See the
[final qualification review](docs/engineering/foundation-final-qualification.md) and
[long-term architecture decision](docs/engineering/foundation-architecture-decision.md).

**Phase 2 qualification is incomplete. A clean pinned ERP installation and migrations
have passed on a controlled hosted runner. Product implementation remains blocked.**

The hosted runner resolved the local download/service blocker. Five upstream apps
install and build together, and synthetic academic-to-payment, backup/restore and worker probes passed.
Student REST/private-file isolation failed in the baseline configuration; native
User Permissions corrected those tested paths. The generic guard now has hosted proof
for 47 expanded isolation checks and five browser checks, including CSRF controls.
A later hardened run also passed encrypted-credential and permission recovery, copied-session
revocation, 47 recovered-site checks, and two upstream permission/sharing suites.
These scoped passes do not clear the broader security gate.
Full domain, authorization and payroll qualification is not complete. Frontend dependency advisories remain unresolved; installation and build
success do not establish a working, secure ERP.

- [Security diagnosis and regression status](docs/engineering/foundation-security.md).
- [Foundation validation checkpoint](docs/engineering/foundation-validation.md):
  actual attempts/results, blockers, reproduction instructions and conditional verdict.
- [Candidate version matrix](docs/engineering/foundation-version-matrix.json):
  exact source/release candidates; **not an approved runtime lock**.
- [Foundation test results](docs/engineering/foundation-test-results.json):
  executed checks and explicitly blocked runtime scenarios, with evidence hashes.
- [Initial engineering assessment](docs/engineering/initial-assessment.md) and
  [Phase 1 source inventory](docs/engineering/upstream-review.json): historical reconnaissance.

## Architecture direction

Select **controlled upstream-aligned maintenance** for Frappe + ERPNext + Education,
with MariaDB by default and HRMS for the justified native HR/payroll scope. Keep current
pins as an isolated qualification baseline; no production risk acceptance is granted.
Contracted, bounded upstream-aligned maintenance is the fallback if feasibility fails—not
a permanent private fork, replacement portal or forced dependency overrides.

Preserve native student, employee, academic and accounting authorities, and keep owned
security safeguards reversible. Placement is the only authorized custom domain and is
closed. Further custom work (thin Admission or anything else) needs explicit
authorization and must follow the [capability map](docs/domain/ERP-CAPABILITY-MAP.md).
English remains canonical; no UI redesign or localization changes are in scope. The
architecture choice is **not** production approval.

The branch-scoped **Foundation runtime validation** GitHub Actions workflow is the
reproducible clean-install qualification runner. It is not a production deployment
or a verified interactive local-development setup. See the validation report for limits.
Do not reopen Placement. Custom finance/HR or a second student lifecycle remain
unauthorized. Production remains **REJECT**.

## Cloning and running on your own machine

**Honest support statement, verified 2026-09-25.** The supported operating target
is the authorized local Linux server described in
[docs/engineering/LAUNCH-RUNBOOK.md](docs/engineering/LAUNCH-RUNBOOK.md) (owner
decision D15: one controlled local machine, operator reach via Tailscale). There is
**no native Windows support, no Windows installer, and no one-command consumer
setup in this repository**, and no Windows, WSL or macOS run has ever been
executed — none is claimed.

- **Cloning the repository itself is verified.** Every hosted run checks out this
  branch (`git clone -b arena/01a0cd90-tofel-house-erp
  https://github.com/Frotan2/TOFEL-House-ERP.git`), so the code, docs and pin
  files you receive match a state that passed its gates.
- **The full clean-machine chain — fresh Ubuntu → Python → bench → MariaDB + Redis
  → site creation → ERPNext/Education/HRMS install → migrations → asset build →
  running web/worker/scheduler/realtime → browser login and portal journey — is
  verified in a hosted environment only.** It runs on `ubuntu-24.04` via the
  branch-scoped **Foundation runtime validation** workflow (hosted run
  `36119829355`, 2026-09-25, **123/123 checks pass**, including native Chromium
  login + portal journey and guardian/realtime authorization probes). Its exact,
  self-contained implementation is
  [tools/foundation/runtime_install.py](tools/foundation/runtime_install.py).
- **The TOEFL House app on top of that foundation** (installing `apps/toefl_house`
  on a fresh controlled bench, then the whole placement journey end to end
  including backup/restore) is likewise **verified in a hosted environment only**
  — branch-scoped **Placement synthetic content qualification** workflow (hosted
  run `36161953566`, 2026-09-25, 596/596 native checks).
- **Running on your own Windows, WSL2-Ubuntu or personal Linux machine is
  documented but not executed by this engineering repository's gates.** The
  steps and pins are fully encoded in the hosted harness above and mirror the
  standard Frappe bench toolchain (Python per `pyproject.toml`, Node/Yarn per the
  pinned tool versions, MariaDB, Redis), but no local interactive run — with or
  without WSL — is packaged or certified here. Do not treat a working GitHub
  Actions clean install as proof that a local desktop install will work; treat it
  as a precise reference implementation you can follow.
- **Even after a successful local install**: production remains **REJECT**; the
  owner-value carriers (D1/D3/D4/D7) intentionally fail closed until the owner
  supplies their values via the TH policy DocTypes.

## Validation utilities

These utilities do not install a site or claim application compatibility:

```bash
python3 tools/foundation/preflight.py --method native --output .foundation/preflight.json
python3 -m unittest discover -s tests/foundation -v
```

Preflight exits nonzero for missing/mismatched prerequisites. See the report for
the integrity-preserving Yarn mirror and explicit dependency advisory commands.
A passing helper test suite is not a passing ERP test suite.

## Contribution and data policy

Use the authorized working branch and reviewed pull requests; do not modify `main`
directly or rewrite history. Keep future customizations in the owned application
and enforce business rules server-side. Never commit real site configuration,
credentials, student/payroll data, database dumps or backups.

**Product license: MIT — owner decision D11, decided 2026-09-19.** The Course
Owner selected MIT, so the three surfaces that previously contradicted each other
are now consistent: [LICENSE](LICENSE) carries the MIT text, both `hooks.py`
files already declared `app_license = "MIT"`, and this README now states the same
thing. `tests/foundation/test_licence_consistency.py` enforces that agreement so
the contradiction cannot silently return. MIT matches what the app metadata has
declared all along and is compatible with the pinned upstream
Frappe/ERPNext/Education/HRMS apps; it does not change any production posture,
which remains **REJECT**.

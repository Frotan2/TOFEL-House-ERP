# TOEFL House ERP

Owned engineering foundation for the TOEFL House language-institute ERP initiative.
The GitHub repository name remains `TOFEL-House-ERP`.

## Current status

Active engineering branch: `arena/01a0b5c4-tofel-house-erp`. Historical hosted
runs retain their original branch provenance; see
[branch and evidence reconciliation](docs/engineering/BRANCH-RECONCILIATION.md).

**Engineering review (2026-09-18):**
Continuing ERP semantic reconciliation work on this session branch.
The session boundary was rotated to `arena/01a0b5c4-tofel-house-erp` on
2026-09-18, and ten hosted workflows were then genuinely executed on this branch
at commit `e96de8a` by push trigger, so `active_branch_hosted_execution` is
`EXECUTED` with `ACTIVE_RUNTIME_RUN` pinned to `35384078097`. Eight gates
succeeded (owned suite `35384078106`, D8 contract `35384077993`, runner
`35384077956`, placement `35384078001`, operational boundaries `35384078024`,
datastore durability `35384078002`, external key custody `35384077977`,
independent-system recovery `35384078072`) and two rejected: **Foundation
runtime `35384078097` — failure** at `Install and validate the pinned
foundation`, and frontend candidate review `35384077998` — failure at
`Compare frozen baseline and isolated candidate`. That rotation also **corrected a stale claim**: the
previous active branch `arena/01a0b3a7-tofel-house-erp` was recorded as having
no hosted execution, but `Foundation runtime validation` genuinely ran there and
rejected — run `35361065542` at commit `82275fd`, conclusion `failure`, failing
at the step `Install and validate the pinned foundation`, with a second run
`35356041559` at `53aae30` failing identically. See
[branch and evidence reconciliation](docs/engineering/BRANCH-RECONCILIATION.md).
**Foundation runtime rejects on SEC-DEPS-01 exactly as predicted. Production
remains REJECT and D8 remains BLOCKED.** Re-executing the named hosted workflows
on this branch will replace the absence with observed results; until then no
execution is claimed. Runs cited further below that belong to earlier session
branches are historical provenance and are labelled as such.

The two commits previously reported as local-only on an earlier session
(`b6d78e5` and `8638c77`) are recorded as **LOST / NON-EXISTENT**. They are
absent from every reachable object in this repository's full history, and the
GitHub commits API returns HTTP 422 "No commit found for SHA" for both. They are
not cited as history anywhere in this repository and must not be reconstructed
or assumed.

**Production-like execution pass (2026-09-16, commit `d7df9ca`):** the readiness
harness was re-executed on a genuine Docker-capable runner (ubuntu-24.04, Docker
28.0.4, Compose 2.38.2) — runner qualification `35122242676` passed 18/18 with
real MariaDB health and Redis probes, placement `35122242728` passed 542/542
native checks with a real backup → separate-database restore → integrity
verification, and Foundation runtime `35122242581` **failed** again on
SEC-DEPS-01 (114/116 restricted checks). The requesting sandbox has no Docker
Engine and is recorded **ENVIRONMENT-BLOCKED**; no preflight or bounded result
was promoted to execution evidence. Probe-by-probe classification:
[execution ledger](docs/engineering/evidence/production-like-execution/execution-ledger.json)
and [final readiness report §8](docs/engineering/FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md).
**No D8 gate flipped to PASS. Production remains REJECT.**

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

**No product license has been selected — this is open owner decision D11.** The
declaration is currently inconsistent across three surfaces and engineering has
deliberately not resolved it: both `hooks.py` files declare `app_license = "MIT"`,
this README states that no license is selected, no `LICENSE` file exists in the
repository, and GitHub reports the repository license as `null`. A license is a
legal grant, it is effectively irreversible once published, and it constrains how
the pinned upstream Frappe/ERPNext/Education/HRMS apps may be combined and
distributed, so it is not an engineering choice. Options and the consistency
requirement: [OWNER-DECISIONS.md §D11](docs/engineering/OWNER-DECISIONS.md).
Review the initial assessment's licensing section before incorporating or
distributing upstream software.

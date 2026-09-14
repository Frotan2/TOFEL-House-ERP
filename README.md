# TOEFL House ERP

Owned engineering foundation for the TOEFL House language-institute ERP initiative.
The GitHub repository name remains `TOFEL-House-ERP`.

## Current status

**Phase 3 domain architecture is ready for review:**
[TOEFL House domain design package](docs/domain/README.md) covers native entity ownership,
placement/admission/academic/finance/HR workflows, permissions, integration boundaries
and the implementation plan. The user has authorized **design and planning only**.
No domain app, schema, API or UI has been implemented; production approval is not implied.

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
security safeguards reversible. Phase 3 domain design and planning are authorized; no
product app or TOEFL-specific implementation begins without review, explicit authorization
and the required gate agreement. English remains canonical; no UI redesign or localization
changes are in scope. The architecture choice is **not** production approval.

The branch-scoped **Foundation runtime validation** GitHub Actions workflow is the
reproducible clean-install qualification runner. It is not a production deployment
or a verified interactive local-development setup. See the validation report for limits.
Do not implement placement, scoring, custom finance/HR or student lifecycle until
those gates pass.

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

No product license has been selected yet. Review the initial assessment's licensing
section before incorporating or distributing upstream software.

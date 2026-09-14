# TOEFL House ERP

Owned engineering foundation for the TOEFL House language-institute ERP initiative.
The GitHub repository name remains `TOFEL-House-ERP`.

## Current status

**Recommendation: REJECT current Phase 2/production acceptance.** Guardian and realtime
resource guard corrections have scoped hosted proof, but dependency remediation and
broader production readiness remain open. GitHub access expired during final monitoring;
the latest private-file owner and scheduler changes are not yet runtime-approved.
See the [hardening remediation report](docs/engineering/foundation-hardening-remediation.md).

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

Provisionally qualify Frappe + ERPNext + Education, with HRMS justified for the full
HR/payroll scope, before creating an owned `toefl_house` application. Preserve
upstream student, employee, academic and accounting authorities. Do not copy or
modify upstream core in this repository. English is the canonical product and
engineering language; no UI redesign or localization changes are in scope now.

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

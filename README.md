# TOEFL House ERP

Owned engineering foundation for the TOEFL House language-institute ERP initiative.
The GitHub repository name remains `TOFEL-House-ERP`.

## Current status

**Phase 2 qualification is incomplete. No ERP site or compatible backend bundle has
been validated. Product implementation remains blocked.**

Education's standalone frontend installs from its frozen lock and builds on Node
24.21.0. Backend prerequisites could not be installed because required download
endpoints failed. The frontend dependency advisory gate also returned findings
requiring triage/remediation. A build is not proof of a working or secure ERP.

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

There is **no verified full-stack run command yet**. The validation report contains
commands for the toolchain/frontend experiment and lists the missing ERP gates.
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

# TOEFL House ERP

Owned engineering foundation for the TOEFL House language-institute ERP initiative.
The GitHub repository name remains `TOFEL-House-ERP`.

## Current status

**Reconnaissance only — no ERP application is installed or production-qualified.**
The repository began as a README-only project, not an upstream fork.

- [Initial engineering assessment](docs/engineering/initial-assessment.md): repository evidence, candidate architecture, domain ownership, security risks, operations and next-phase acceptance gates.
- [Pinned upstream review inventory](docs/engineering/upstream-review.json): inspected source commits and dependency declarations. This is **not** an installation lockfile.

## Architecture direction

Provisionally qualify Frappe + ERPNext + Education + HRMS as upstream dependencies,
then build an owned `toefl_house` app for placement testing and institute-specific
workflows. Preserve upstream student, employee, academic and accounting authorities.
Do not copy or modify upstream core in this repository.

There is no local run command yet. A reproducible environment, validated release
bundle and tested runbook are the next milestone; see the assessment before
starting implementation. Never commit real site configuration, credentials,
student/payroll data, database dumps or backups.

## Contribution policy

Use the authorized working branch and reviewed pull requests; do not modify `main`
directly or rewrite history. Keep customizations versioned in the owned application
once created, and enforce business rules server-side. Application builds alone are
not acceptance evidence.

No product license has been selected yet. Review the assessment's licensing section
before incorporating or distributing upstream software.

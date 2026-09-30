# toefl_house

The TOEFL House extension app for Frappe/ERPNext/Education/HRMS. Product scope,
native/custom ownership and the lifecycle are described in
[docs/PRODUCT.md](../../docs/PRODUCT.md); this file maps the code.

| Package | Contents |
| --- | --- |
| `placement/`, `api.py`, `allocation.py`, `scoring.py` | Placement: governed item bank, blueprints/policies/course maps, form allocation, supervised digital delivery, objective scoring, independent review/finalization, decision release. Spec: [docs/PLACEMENT-SPEC.md](../../docs/PLACEMENT-SPEC.md). |
| `admission/` | `TH Admission Decision` over native Student Applicant/Student; returning-student policy. |
| `enrollment/` | `enroll_in_program` over native Program Enrollment; enrollment exits (withdrawal/dismissal) and their policy. |
| `teaching/` | Student Group roster, Course Schedule sessions, Student Attendance, attendance corrections; instructor contracts, teaching assignments and compensation to native Additional Salary. |
| `finance/` | Tuition via native Fees, placement fee via native Sales Invoice, billing and correction policies. |
| `academic/` | Owner configuration of programs, levels, durations, discounts, assessment and catalog-linkage policies. |
| `operations/` | Guardian lifecycle and alerting policy carriers. |
| `configuration/` | Shared policy-version rules and the hash-chained configuration audit. |
| `desk/`, `public/` | Read-only role desks and guided command pages. Spec: [docs/ROLE-DESKS.md](../../docs/ROLE-DESKS.md). |
| `security.py`, `controllers.py`, `transactions.py`, `permissions.py` | Command context, role gates, idempotent receipts, deny-by-default document guards. |

## Invariants

- Every command runs under a server-created command context with an
  idempotency receipt and an audit event in the same transaction. Guarded
  native DocTypes refuse direct REST/RPC/Desk writes, cancel and amend.
- No business value (price, rate, threshold, capacity, tax) is a code constant;
  consumers of an unconfigured policy fail closed.
- Commands are REFUSED unless the site is activated for production
  ([LAUNCH-RUNBOOK](../../docs/engineering/LAUNCH-RUNBOOK.md)) or is one of the
  disposable synthetic test sites used by the native lifecycle checks
  (`allow_tests=1`, `toefl_house_synthetic_only=1`).
- Never uninstall the app to work around retention or audit records.

## Tests

- `python3 -m unittest discover -s tests -t .` — unit and contract tests (no site needed).
- `.github/workflows/native-lifecycle.yml` — installs the pinned stack on an
  ephemeral runner and runs `tools/native/native_checks.py` against real sites.

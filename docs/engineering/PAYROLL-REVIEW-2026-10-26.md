# Instructor payroll review — 2026-10-26

## Scope and decision

Reviewed PR #87 (`fix: financial reconciliation and Windows acceptance blockers`),
its current release-candidate source, the 2026-10-26 finance completion record,
the Owner operating policy and payroll/teaching tests. The current release
candidate already contains the instructor contract cadence, effective-dated
revision, native HRMS input and worked-month reporting changes described below;
this review did not introduce a parallel payroll ledger or duplicate those
changes.

**Payroll/production remains locked (NO-GO).** These source-level tests do not
constitute hosted Native HRMS, live browser, legal, accounting or Owner
acceptance. The repository's branch is `arena/85a5657f-tofel-house-erp`; the
session cannot switch to the requested `agents/payroll-finalization` branch.
PR #87 is the reviewed existing release candidate, not a new payroll-only PR.

## Review findings

- Teaching compensation creates native ERPNext Additional Salary inputs linked
to the originating teaching assignment or contract adjustment. Fixed salary
remains under native Salary Structure / Salary Structure Assignment. Salary
Slip calculations, submission and payments are not implemented as another
payroll engine.
- Contract revisions retain historical rows and use effective windows. A
revision cannot rewrite predecessor terms, earning basis or historical input
facts. Monthly-mode inputs require exact first-to-last day coverage of a
Solar Hijri month by both assignment and contract; unsupported partial months
fail closed.
- The per-assignment/per-month existing-input lookup is protected by
contract-level locks and a posting-time reread. Same-period reruns skip
existing inputs; the focused regression verifies cancelled/disabled records
are excluded by the production lookup predicates. Live Frappe cancellation and
row-lock semantics still require Native HRMS evidence.
- Payroll reporting separates the worked Solar Hijri month from actual
submitted Salary Slip and submitted native payment voucher dates. A submitted
slip alone is not treated as cash paid; partial, unlinked or excess
payments are rejected by the reconciliation helper.
- Owner policy separates draft Additional Salary preparation, Salary Slip
submission and real disbursement. Salary details must remain Finance/Owner
only; PR #87 records sampled role/Page/API denials, including payroll cases.
Those sampled checks are not a replacement for complete exact-head access
acceptance.

## Local synthetic test evidence

Executed with the repository's standard-library test runner because `pytest`
is not installed in this workspace:

```text
python -m unittest tests.teaching.test_compensation_guards \
  tests.teaching.test_compensation \
  tests.teaching.test_shamsi_payroll_periods -q
Ran 48 tests ... OK
```

Coverage includes one-off legacy behavior; monthly earning; an earlier
Solar Hijri month's payment not suppressing the next month; same-month
duplicate prevention; Gregorian-window and partial-month rejection;
contract/assignment coverage and supersession; invalid earning basis;
concurrent lock ordering and posting-time reread; synthetic Finance company
scope; additive native inputs; and earned-versus-paid month reconciliation,
including partial/excess/unlinked disbursement rejection. Tests use isolated
Frappe stubs and synthetic records, not a live HRMS database.

## Exact-head CI evidence

At payroll implementation/test commit `86d84f50a5ec8e6df3b9226f7aa222d27f0bd95d`,
the Owned Suite and Native lifecycle integration checks both completed
successfully. The Native job's real-site lifecycle step passed (run
[40423483125](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40423483125));
its retained artifact is `native-lifecycle-40423483125-1` with published
SHA-256 `88e56f7759466325663b151ce5ef008a6149ceee42e5582ab60421dba1e2daa5`.
Subsequent PR commits only refine isolated synthetic regression coverage and
this evidence document; they do not change payroll production code. The latest
Owned Suite reruns cover those updates. This evidence does not establish live
customer payroll acceptance, legal compliance or authorization to disburse
wages.

## Remaining blockers / policy dependencies

1. Run exact-head Native HRMS fixture acceptance in the supported hosted
   environment: create contracts/assignments, generate native inputs, prepare
   and submit Salary Slips under authorized roles, and reconcile posted native
   disbursement vouchers. Confirm cancellation/replacement and immutable
   posted-document behavior against the pinned ERPNext runtime.
2. Complete exact-head role tests for Finance/Owner allowed salary reads and
   Reception, Instructor, Manager and other unauthorized reads, across both
   Desk/API and native HRMS document routes.
3. Legal/accounting review must supply Afghanistan-specific tax and statutory
   treatment, applicable contracts, and any approved pay-date exceptions.
   No rate, withholding, proration, or penalty is inferred by this code.
4. Confirm Owner/Finance native salary structures, component setup, Holiday
   List assignments, opening teacher liabilities and accounting cutover. The
   Owner policy requires separately authorized payroll submission and actual
   payment.
5. Browser/UI acceptance and the broader release gates in PR #87 remain
   outstanding. No production payroll, real disbursement, merge or release is
   authorized by this review.

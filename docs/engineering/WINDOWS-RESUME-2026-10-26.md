# Preserved Windows acceptance continuation — 2026-10-26

Release decision: **NO-GO; acceptance remains in progress**.

The seven reported GitHub checks for `855533e3714c2a30e9421485d6fb2bbab3d761dd`
completed successfully: both Owned runs, Native, Foundation, Product Image,
Windows package smoke and stale-worktree EOL. These results do not qualify
subsequent changes or replace operational acceptance.

The existing Windows Docker Desktop 4.96.3 / Engine 29.9.2 installation and
`placement-test.localhost` storage were resumed without reinstalling or
resetting credentials. The preserved preview source was fast-forwarded from
`7ebecd0` to `855533e`; the underlying image remains the earlier `2b29571`
image. This is source-preview evidence, not the rebuilt package's acceptance.

## Observed local HTTP and native results

- All five independent existing staff logins returned their own identity,
  installed Page and Desk with HTTP 200. Each sampled foreign-role Desk
  returned HTTP 403 / PermissionError. These are HTTP checks, not rendered
  browser transaction evidence.
- Two new synthetic learners completed real HTTP placement authoring,
  independent configuration review/publication, delivery, scoring,
  independent review/finalization, release, admission, independent approval,
  conversion and submitted Program Enrollment. Existing academic masters and
  credentials were preserved. Additional synthetic support identities were
  created for required independent approvals; existing staff roles were not
  expanded. An initially absent catalog-linkage policy correctly refused
  enrollment; the Owner configured an enforcing synthetic policy before retry.
- Owner configured two Solar Hijri monthly installments. Finance posted two
  native Fees of AFN 2,500 for one enrollment and one native Fees of AFN 5,000
  for the second. Native Payment Entries received 1,000, then 1,500 against
  the first installment, and 2,500 against the second. Outstanding readbacks
  were 1,500, zero and zero respectively. Native cash reconciled to AFN 5,000;
  total native GL debits equaled credits. The other enrollment remained
  outstanding at AFN 5,000. Duplicate tuition and direct Reception payment
  creation were denied.

## QA-007: Education fee root cannot save accounting defaults

Normal native accounting setup failed with `Item Group Fee Component cannot
be a leaf node as it has children`. Readback showed Fee Component was the
sole item-group root, `is_group=0`, bounds 1–12, with five native ERPNext
preset children. Education's fee group can predate the ERPNext wizard; the
wizard reuses the existing root while its conditional fixture skips updating
the root flag.

The owned installation/wizard repair changes only that exact, unambiguous
root's group flag through native save. It never renames groups, moves items,
rewrites defaults or changes posting data. Existing ordinary Fee Component
leaves under a proper root and already-correct roots are untouched; ambiguous
roots and native validation errors fail closed. It is not a whitelisted API
and requires Administrator. Migrate covers existing installations and the
native wizard success hook covers new setup. Hosted real-wizard qualification
now also saves the fee group to verify accounting setup is usable.

Six targeted regressions passed; combined installation, setup-account and fee
item suites passed 30 tests. Applying the repair on the preserved synthetic
site returned true, and the previously failing native accounting setup then
completed, retaining the Fee Component name, all children and its fee Item.

## Still required

Unallocated advances and settlement, book stock/sale/return/cash refund,
attendance and cross-teacher denials, native payroll and liabilities,
Company/Branch and female-counter custody, restart/repair, encrypted isolated
Windows recovery, official rebuilt package qualification, staff-device access
and independent business/security acceptance remain open. Main is unmerged;
branches and production activation remain unchanged. No completed status is
claimed for these remaining gates.

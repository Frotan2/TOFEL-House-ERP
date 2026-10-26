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

## Continued Windows acceptance, 27 October

The preview was advanced to `9d7d1ab`; all seven hosted checks passed at that
revision. The following results are native synthetic-site evidence, not
qualification of the official rebuilt image or graphical Windows launcher:

- Books: receive 12, sell two for AFN 600, return both and refund AFN 600.
  Stock returned to 12 and cash to AFN 5,000; both sales documents settled.
- Attendance: two teachers recorded their own sessions; cross-teacher writes
  returned 403. Four native attendance records persisted.
- Payroll: two submitted native slips of AFN 1,500, including AFN 500 skill
  compensation each, produced AFN 3,000 payroll liability. Wages were not
  disbursed. The synthetic Finance fixture alone received HR Manager for the
  native payroll submit path. Twelve salary-privacy checks passed.
- Encrypted database, public/private files and site configuration were
  restored into the separate `placement-second.localhost` database. All 20
  table snapshots, both file markers and an encrypted secret matched. The
  original database was not overwritten or activated for production.
- On the restored copy, an AFN 500 unallocated advance was reconciled against
  the second learner's Fees: unallocated zero, outstanding AFN 4,500, one
  new Payment Entry. Cash close counted AFN 5,500 against AFN 5,500 expected;
  Reception was denied and unexplained variance was refused without GL edits.
- Restart retained the original site's records, AFN 5,000 cash and AFN 5,000
  outstanding. Native ERPNext scheduled GL/SLE numbering was accounted for by
  comparing every field except its three documented numbering fields, after
  verifying the restored pre-numbering reference against the backup hash.

## QA-008: guarded writes bypass native Branch User Permission

An authenticated scheduler restricted to Branch A created a Branch B class
and received its roster (HTTP 200). This was reproduced only on the restored
synthetic copy and blocks release despite the preceding green CI.

The fix scopes guarded command references before mutation and rechecks cached
receipt targets after permissions change. Restricted class creation resolves
a sole permitted branch and filters its derived roster by current membership,
falling back to applicant intake only before initial placement. Unrestricted
management retains its existing cross-branch administration behavior.

Eight focused regression tests passed, including initial enrollment using
the applicant's branch before first placement. The teaching suite passed all
334 tests. Six real authenticated HTTP checks
passed on the restored copy: own replay, foreign replay denial, fresh own
creation, fresh foreign denial, omitted-branch default and denial of that
receipt after changing the actor's scope. Hosted native qualification adds
positive replay plus foreign fresh-write and replay denials. The broader
2,538-test Windows run had three verifier-harness failures from inheriting
PowerShell 7's module path in a Windows PowerShell 5.1 subprocess; the harness
now lets the selected shell construct its own module path, removing the
environment key case-insensitively. All three previously failing verifier
cases passed on Windows in the targeted retest (26.110 seconds). This is a
test-process environment repair; no package integrity check was weakened.

## QA-009: saved cash-close receipt bypasses changed Company scope

On the isolated restored copy, native Company User Permission correctly
denied a fresh close for a second valid Company and left the GL unchanged.
However, after Finance's Company scope changed, replay of the existing cash
close returned HTTP 200 with the former Company's totals. The receipt path
returned before the work function's Company permission check.

The shared command gate now checks Company scope before fresh execution and
receipt replay, independently of Branch restrictions. It also resolves
Company through supplied native Fee Structure, Fees, Sales Invoice, Employee,
Salary Slip and Payroll Entry references, and checks a resolved result Company
when the original command used an implicit default. Unrestricted management
keeps its existing behavior. Two new regressions failed before the change;
all 12 focused tests, 214 Finance tests and 339 Teaching tests passed after it.
Native qualification now includes a real Company permission change followed
by cash-close receipt replay and a check that GL row count is unchanged.
Live HTTP retest and final-revision CI remain required.

## QA-010: real Android login lands in generic ERP navigation

The Owner opened the private Windows preview on an Android peer and reported
Organization, Accounting, Buying, Quality and Selling instead of Reception.
Native login activity matched that peer to `uat-reception@example.test`.
Its business roles were Reception and Admission Officer, with no Finance or
System Manager role. Its resolved home page was the generic `desk`.

The app-tile `app_home` hook did not govern native login. Hosted browser checks
had manually routed every account after login, masking this defect. The fix
uses native home/login/boot hooks and a private, noncached root redirect for
existing `/desk` bookmarks. It leaves explicit deep links, setup-wizard routing,
built-in accounts, roles, module preferences and document permissions intact.
Hosted acceptance now follows natural login for each primary role and adds
an Android device context with the old `/desk` return URL. Only Owner's
secondary configuration pages still require explicit navigation in that test.

Real Windows HTTPS checks pass for all seven identity landing destinations.
Reception's own Page passes; Finance/Administration Pages, their privileged
APIs, Payment Entry, Sales Invoice, Salary Slip, User Permission lists and full
Role configuration return 403. Native role-name selection is distinct from full
Role configuration permission. The Android user then confirmed the visible
heading "TOEFL House Reception Desk". This accepts mobile landing and the
tested permission boundaries, not collection/handover or all staff workflows.
The local owned run passed 2,572 tests with 172 platform skips; final routing
regressions and new-revision CI must also pass before release qualification.

## Still required

Final-revision CI, official rebuilt package and supported in-place Windows
update/repair qualification, graphical staff transaction acceptance,
Company-negative cases, female-counter collection/handover, staff-device
access and independent business/security acceptance remain open. The Windows
computer-use helper again stopped because it could not verify the current
browser URL, even after the user opened the ERP page. No further UI input was
attempted. Main remains unmerged, branches retained and production inactive.

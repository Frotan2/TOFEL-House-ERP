# TOEFL House ERP — Release candidate specification

**Release authorization: REJECT / NO-GO**  
**Package classification: TEST PACKAGE — NO REAL DATA**  
**Integration candidate: `work` (draft PR #120); `main` is not a release.**

This specification describes the **current review target**, not an issued
customer build. No version tag, Windows installer or GitHub artifact can be
called accepted merely because it exists. A qualifying source revision is the
full Git SHA of the final, independently reviewed source tree, with matching
native integration, foundation security, product image and Windows gate
receipts. Results from older commits are not transferable.

For source-of-truth precedence and the preserved audit archive, see
[Documentation authority](../DOCUMENTATION.md).

## Intended release contents

- Native Frappe 16, ERPNext, Education and HRMS, using the pinned
  [dependency matrix](foundation-version-matrix.json).
- Guarded role-specific institute workspaces for Owner, General Manager,
  Academic Manager, Finance Manager, Reception and Instructor.
- Fresh institute catalog, curriculum/levels, tuition and billing rules,
  academic calendar, rooms, timetables and teacher assignment; routine
  business policy configuration through English no-code controls.
- Placement, intake, admission, enrollment and attendance, using native
  students, classes and authoritative Education records.
- Native accounting/stock/cash operations for tuition, payments, book
  inventory, book returns and customer refunds; authorization-gated
  corrections and tuition refund mechanisms.
- Versioned assessment, grading, retake and progression commands, with
  defined approval and native record links. Their presence in source is
  **not** a claim of final installed-site qualification or authorization.
- Payroll-facing compensation integration under native HRMS authority;
  no second salary or tuition ledger.
- Auditable policy changes, native role enforcement, backup, safe updates
  and separate two-person recovery mechanisms with hard refusal boundaries.

## Initial dataset and setup

The customer receives **no operational history**. First-installation images
must contain zero real or synthetic student, applicant, enrollment,
attendance, invoice, payment, payroll or grading records. Approved catalog
templates and unactivated policy proposals are not historical transactions.
CI fixtures are disposable and must never be exported to the customer's
application volume.

The initial staffing plan is six logins **including the existing Owner**,
with the General Manager, Finance Manager, Academic Manager, Receptionist
and one Instructor added only after identity verification. Do not invent
real email addresses, create duplicate Owner logins or confer universal
administrator privileges on business co-owners.

Initial tuition, program duration, pass rules, calendar and other business
figures must match the latest explicit Owner-approved decision records in
`docs/owner-decisions.json`. Superseded values in previous engineering
reports have no authority. Ordinary future changes must be possible from
guarded GUI forms with effective dates and reasons, without editing code,
JSON or database records.

## Final customer distribution contract

The finished customer receives **one offline provider-signed Windows Setup
EXE**. The provider, not the customer, builds and verifies the application
image, packages compatible signed prerequisites, checks release identity
and tests a clean-machine first installation. A repository ZIP, embedded
nested ZIP, VBS/PowerShell engineering launcher or GitHub Actions source
artifact **does not satisfy this contract**.

A local-server architecture may use private Tailscale access for authorized
staff. Public internet publication is not implicitly approved.

## Mandatory acceptance before release

1. **Same commit:** all five hosted gates succeed on the exact reviewed full
   SHA — Owned suite, Native lifecycle integration, Foundation runtime,
   Product image, and Windows customer package smoke. Required checks may
   not be queued, skipped, cancelled, stale or failed.
2. **Real installed Windows:** a publisher-signed installer is verified,
   installed offline on a clean supported PC, and accepted graphically
   without developer commands. Startup, local access, restart, Stop/Start,
   update and safe rollback are recorded.
3. **Staff and permissions:** six role journeys pass, including cross-role,
   student/teacher, Company/Branch and finance denial tests. No real email
   invitation may be sent to an unverified address.
4. **Native business integrity:** positive and adversarial full journeys
   confirm the actual Fees/GL/Payment Ledger, stock, cashier close,
   refunds, assessment and native HRMS records; duplicate/replay/concurrent
   requests and failed transactions preserve integrity.
5. **Backup and independent recovery:** an encrypted versioned backup is
   verified against the real separate approved drive, with two distinct
   authorized recovery approvals and an isolated restore/replay on a
   different target. No restore overwrites the original installation.
6. **Independent review and Owner sign-off:** release-blocking defects,
   security advisories, branch protection and delivery provenance are
   resolved before the Owner issues explicit written production approval.

## Deferred or held operational scope

Do not activate public student/guardian portals, unapproved external
notifications, public payment channels, advanced cross-program or
cross-branch transfers, direct student payout shortcuts, unqualified
automatic updates or any feature whose required policy or native
integration has not been approved. Stored policy values are not evidence
of execution; a site-mode switch cannot authorize production by itself.

**Never** merge, delete audit evidence, weaken permission gates, install
over the Owner's preserved Windows site, reset Docker volumes or populate
live records to make a release gate pass. The release status remains
**REJECT** until all applicable evidence exists.

# TOEFL House ERP v1.0.0-rc.1 — Engineering Release Candidate

**Release status:** TEST PACKAGE — NO REAL DATA

**Production authorization:** REJECT / NO-GO

**Product shape:** native Frappe Desk on ERPNext + Education + HRMS

This is the consolidated native-first engineering candidate. It is not production approval and not a claim that every lifecycle stage or physical acceptance gate is complete.

## Source and provenance

- The Git tag `v1.0.0-rc.1` must resolve to the exact reviewed source commit. The tag, Product-image run and `product/release/release-manifest.json` are authoritative; a branch name or short SHA is not.
- The customer package contains a provider-built **Linux/amd64** image. A customer does not compile Frappe, build Docker images, use Git, or run database commands.
- `product/release/ci-gates.json` identifies the exact full source SHA and the successful Owned, Native, Foundation and Windows-package run IDs/URLs used by the package pipeline. Its SHA-256 is bound into the release manifest.
- The Product-image workflow verifies those four gates again, builds/runs the image, checks package image labels/config/layers, assembles the allowlisted ZIP, attests provenance, uploads the artifact, and only then publishes an existing `v*` tag release.
- These are hosted engineering gates. They are not real Owner Windows, recovery, staff-device, cashier/stock, payroll, or production acceptance.

## Included in the candidate

### Native institutional lifecycle subset

- Applicant/intake and the owned Placement Case journey: allocation, PDF/Digital delivery as configured, sealed responses, marking, review and placement decision.
- Admission conditions, approval/offer/conversion and native Student creation/reuse.
- Program/Course Enrollment, returning-student history reuse, roster/catalog linkage and idempotent commands.
- Native basic teaching groups, scheduling, sessions and attendance, including guarded corrections and rollback/permission checks.
- Native ERPNext tuition/placement billing, Sales Invoice, Payment Entry and GL integration; guarded correction framework with configured policy.
- Native book Item/Warehouse/stock sale, payment, return/restock/credit and separate cash-refund reconciliation. Books and tuition/placement services cannot share the custom book-sale path.
- Instructor Contract, Teaching Assignment and configurable fixed/skill/combined compensation calculation into native Additional Salary inputs.
- Role-specific Desk Pages, authorized configuration interfaces, native raw-fact reports/registers, branch/company scoping and deny-by-default security controls.

Assessment/Progression and full payroll posting are **not** included merely because their names appear in the target lifecycle or native applications.

### Integration and release controls

- Canonical domain/data ownership, API/idempotency/transaction, future event, migration and security contracts in `docs/engineering/INTEGRATION-CONTRACTS.md`.
- Exclusive ownership and sequencing rules for shared hooks, permissions, fixtures, configuration, tests and CI.
- A four-state acceptance matrix separating IMPLEMENTED, VERIFIED, DEFERRED and BLOCKED.
- Exact-SHA gate receipts embedded in the downloadable package and checksummed in its manifest.
- Same-directory staged ZIP and checksum files with non-overwriting publication and failed-staging cleanup; their sequential renames are not represented as one atomic transaction. Image platform/source/layer validation, customer allowlist, no `product/data`, and TEST/REJECT labels remain enforced.
- Offline English/Dari **Owner Handbook**, available from the Windows GUI without a terminal.

### Recently integrated security/reliability work

- Compatible filelock and HRMS frontend npm remediations, plus a narrowly scoped Linux/Windows setuptools advisory disposition protected by platform tests.
- Stronger native book GL/stock row-direction evidence validation.
- Product-image triggers for native financial acceptance changes.
- Existing dependency risk acceptances remain visible as accepted risk, not as vendor fixes or universal security claims.

## Explicitly excluded or deferred

- **PR #46:** signed/prebuilt updater remains KEEP UNMERGED under its special hold and independent changes-requested findings. This RC has no approved automatic updater.
- **PR #48:** notifications/provider stubs/student/guardian portals are excluded after integration changes-required review and failed Owned gates. Nothing from that PR is included.
- **PR #49:** Assessment/Progression runtime is excluded. D1 still defers that consumer, and the proposed progression read RPC requires permission corrections despite green hosted checks.
- **PR #50:** finance/installment/tax/cashier/refund changes are excluded pending correction of cashier-policy authority, company scoping, drift selection and native return-reversal defects, followed by fresh exact-head qualification and independent review.
- **PR #51:** class operations/mobility changes are excluded. The exact Native run failed fixture import, and D5 still defers the proposed transfer policy/consumer.
- **D1:** runtime Assessment, grading, pass bands, credits and Progression are deferred; native Education historical outcomes remain untouched.
- **D4:** advanced identity, guardian delegation and public/student/guardian portals are deferred.
- **D5:** repeat, transfer and withdrawal policy remains deferred; any fail-closed mechanism is not authorization to use it.
- **D6a/D6b:** no tax configuration is inferred and no online payment gateway is selected or enabled.
- **D7:** derived metrics/warehouse reporting is deferred; only source-owned raw-fact reporting is in scope.
- Notification delivery is not active. `TH Alerting Policy` is a configuration carrier, not proof that an email/SMS was sent or received.
- Public internet hosting is not selected. Current deployment remains local/server through authorized Tailscale.

## Installation and upgrade boundary

Use the complete customer ZIP only on a separate disposable Windows practice PC with no existing TOEFL House data. Extract the whole package and use `TOEFL House ERP.vbs`:

1. Choose **Check This PC** and preserve the safe result.
2. On a genuinely fresh practice PC only, choose **Install**.
3. Choose **Open / Start**, sign in privately, and open **Owner Handbook**.
4. Use synthetic people, books, fees, salaries and payments only.

If any existing site/database is present, **STOP**. Do not reinstall, repair, reset credentials, restore, replace volumes, or copy this package over the installation. Contact trusted support for a separately authorized migration/update procedure.

There is no supported production upgrade or automatic update in this RC. A migration requires an exact reviewed revision, preserved native history, backup and isolated restore, migrate replay, policy/native verification, service restart, and explicit approval. Never uninstall the app or delete data to bypass a failure.

## Evidence and acceptance

Read `docs/engineering/ACCEPTANCE-MATRIX.md` and the package’s CI receipt/manifest together:

- **IMPLEMENTED** does not mean runtime-qualified.
- **VERIFIED** is limited to the cited exact-SHA hosted/synthetic behavior.
- **DEFERRED** is intentional Owner/product scope and cannot be enabled by engineering convenience.
- **BLOCKED** requires the stated physical evidence, Owner input/approval or held-code resolution.

The baseline native/product runs do not qualify a later candidate SHA. Conversely, a later green Product run does not retroactively turn deferred scope into implementation or hosted evidence into Owner acceptance.

## Remaining release blockers

- [Issue #12](https://github.com/Frotan2/TOFEL-House-ERP/issues/12): real Owner Windows lifecycle, backup drive/key custody/recovery and private staff-device acceptance.
- [Issue #35](https://github.com/Frotan2/TOFEL-House-ERP/issues/35): real cashier/book-stock acceptance.
- [Issue #36](https://github.com/Frotan2/TOFEL-House-ERP/issues/36): independently downloaded package and real target-PC installation/usability acceptance. Publishing the asset alone does not close it.
- [Issue #40](https://github.com/Frotan2/TOFEL-House-ERP/issues/40) / PR #46: safe graphical prebuilt update path, still held.
- Real Owner policy/configuration and payroll/statutory/payable terms where not supplied.
- Independent final security/correctness review and explicit Owner production approval.

## Owner decision required later

Do not enter real student, guardian, staff, salary, stock or financial data until every applicable physical/recovery/staff/financial gate is complete and the Owner issues explicit written production approval. Until then, the decision remains **NO-GO**.

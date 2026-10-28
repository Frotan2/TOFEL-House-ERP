# TOEFL House ERP — exhaustive branch consolidation audit (2026-10-28)

**Target:** `work`. **Preserve:** `main` and `work`. **Production:** HOLD / NOT AUTHORIZED.

## Method and evidence

GitHub branch inventory had 21 branches. For every branch, compared its head against `work` using reachability (ahead/behind). Independently inspected original branch change-set paths and compared the actual blob SHA / complete file text of the candidate changes against `work` instead of equating GitHub's three-dot comparison with a missing final-tree change. Reviewed current hosted CI job logs and retained artifacts.

## Changes recovered or already included

- The original PR #87 release line, Owner-approved installment/book guard audit, and the independently integrated #117 same-level transfer, #118 GM-approved but **nonpaying** tuition refund request, and #119 academic retake are carried by `work`. All four PRs are closed; the consolidated draft PR is #120.
- `fix/calendar-query-overflow-20261028`: both calendar source and calendar test are byte-identical to `work`. Do not copy older trees and remove newer Finance/retake changes.
- `fix/finance-native-identities-20261028`: period reporting and test are byte-identical to `work`.
- `audit/deepmerge-reachability-20261028`: all three review, delta and regression files are byte-identical to `work`. The scope-limited `NOT_REACHABLE` audit is **not** an upstream patch or blanket acceptance of other advisory IDs.
- `fix/security-delta-release-ci-gates-20261028`: Foundation, Native, and Windows workflow source is byte-identical. `work` contains stricter Product Image release-gate triggers and tests; do not replace it with the older branch version.
- `arena/1d76efed-tofel-house-erp`: reviewed its three unmerged commits. Transferred the Windows-only customer package manifest test and its CI trigger regression. **Intentionally rejected** its proposed extension to `product/restore.py`, which would treat arbitrary names containing "recovery" as disposable: the already corrected hosted site is `restore-recovery.localhost`, and the existing stricter "restore" requirement must remain. The old branch's descriptive document falsely assumes the previous fixture remains in use; retained the more accurate `work` release audit instead.
- Fixed two independently reproduced final-head CI errors: Frappe v16 native DocType metadata field `is_submittable` was queried using an obsolete property, and Foundation recovered HTTP permission probe still allowed `recovery.localhost` instead of the now restore-named CI site. Added regression guards.
- Extended Windows CI to execute `test_customer_package_manifest`, which was previously skipped on Linux. This is a real Windows **synthetic** test, not owner-machine qualification.

## Branches whose commits are already ancestors of work

These 14 names had **ahead=0** relative to the checked integration head and no additional commits to port:

`audit/book-invoice-discount-guard-20261027`,
`audit/release-image-symlink-guard-20261027`,
`feat/academic-retake-progression-review-20261028`,
`feat/owner-same-level-class-transfers-20261028`,
`feat/toefl-house-guided-initial-setup-20261028`,
`fix/academic-retake-qualification-20261028`,
`fix/emergency-restore-qualification-20261028`,
`fix/same-level-transfer-qualification-20261028`,
`fix/tuition-refund-approval-hold-20261028`,
`fix/two-person-recovery-qualification-20261028`,
`fix/updater-live-host-observation-20261025`,
`integration/all-agent-work-20261027`,
`security/emergency-restore-recovery-20261028`,
`security/two-person-update-recovery-20261028`.

## Other five branch tips: audit before user deletes

`arena/1d76efed-tofel-house-erp`,
`audit/deepmerge-reachability-20261028`,
`fix/calendar-query-overflow-20261028`,
`fix/finance-native-identities-20261028`,
`fix/security-delta-release-ci-gates-20261028`.

Those branches may be removed by the user **only after** verifying the current `work` head, preserving this report and confirming those refs are no longer used by an agent. They held independent Git ancestry even where equivalent files were already present; they are eligible for an explicit provenance-preserving, content-resolved merge commit. The flagged unsafe restore broadening is deliberately not adopted into `work`.

## IMPORTANT: why main is not a cleanup branch

`main@241c8ad9fc427ff7821df88977e337163653218d` independently introduced a React/Vite application, removing most Frappe/ERPNext source files relative to `work`. It is NOT a patch to port blindly. Do **not** delete, force-reset or merge `main` through cleanup. First decide and document which architecture is the customer's intended product, while preserving both histories. No backup data, customer installation, keys or migration should be touched in the branch-cleanup task.

## Current production and release gates

The older combined head `0d6d3f5` passed Owned and Windows but failed Native, Foundation and therefore Product Image; native and foundation error logs were retrieved and corrected on later `work` commits. **These source corrections are not a green CI result.** An exact-final-head successful Owned + Native + Foundation + Windows + Product Image set remains mandatory. Real Owner Windows five-role browser/finance/payroll, backup/key custody, isolated restore, real staff/Tailscale, and independent signed product package acceptance remain required. The currently pinned Education/ERPNext tuition Fee mechanism cannot perform a valid partial refund; payout stays blocked. Production authorization remains REJECT until independently verified acceptance.

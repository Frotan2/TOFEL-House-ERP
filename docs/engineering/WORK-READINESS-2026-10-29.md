# TOEFL House ERP — work-branch source and release checkpoint (2026-10-29)

**Decision: HOLD / NOT AUTHORIZED FOR PRODUCTION.** This checkpoint describes the *work* branch. It does not replace a successful test run, independent review, Owner acceptance, or the real customer release package.

## Repository and evidence pins

- Repository: `Frotan2/TOFEL-House-ERP`; delivery PR [#120](https://github.com/Frotan2/TOFEL-House-ERP/pull/120), targeting `main` from `work`.
- Base of this focused review: `work@ab7a0209b855b86e1f4d2f4502d8d06c51d0afb1`.
- Finance source correction: `7158ba2218186b3a878e1a1be8d211d901b0c586`.
- Regression tests: `d559db3db02fe06846b3ffd0663da7917d9df847`. **This is the tested *candidate*, not a proven green head at the time of writing.** Later documentation-only commits must not be misrepresented as the code SHA of an earlier run.
- GitHub branch inventory during this review: **two** remote branches, `main@a5f64a51f9f6b8b9949041d2cd9a0788cf528e4a` and `work@ab7a0209...` before the finance commits. Comparison of those tips: **diverged**, `work` 387 commits ahead and 2 behind, with 247 reported changed paths. **Do not force-reset or casually merge**: the independent `main` architecture/history needs a deliberate release decision.
- Historic dated reports retain their original evidence pins. Their old SHA, PR, branch and gate assertions are **not** evidence for this candidate. Use this checkpoint and live GitHub Actions instead.

## Direct source inspection (not report-only)

| Area | Files inspected | Confirmed source behavior / evidence boundary |
| --- | --- | --- |
| Reception receipts and custody | `finance/collections.py`, `finance/collection_rules.py`, `finance/company_scope.py`, `command_scope.py` | Receipt creates and submits native Payment Entry against Fees; command checks the native outstanding movement. Handover creates a separate native Internal Transfer and marks original receipts. Server role, Company and Branch scoping are present. Real Windows cash/GL custody reconciliation **not performed in this review**. |
| Tuition refund | `finance/tuition_refunds.py`, `tuition_refund_commands.py`, `student_payout_policy.py`, `setup_presets/tuition_refund_review.py`, `controllers.py`, DocType JSON | Requested/Approved/Denied cases are durable and constrained; direct Student Pay is held. The pinned ERPNext/Education Fees path does not have a qualified partial-refund credit mechanism, so `pay_tuition_refund` **always refuses** before posting; an approval is not a payment. |
| Book return and payout | `finance/refunds.py`, `tests/finance/test_refund_guards.py` | Separate Sales Invoice credit-note and Customer Payment Entry guard. Do not describe this as a tuition refund mechanism. |
| Release delivery | `README.md`, `docs/engineering/ACCEPTANCE-MATRIX.md`, `LAUNCH-RUNBOOK.md`, `OWNER-GUIDED-SETUP-2026-10-28.md`, workflow inventory | Engineering test package and GUI checks are not physical Owner-install, backup/recovery, or live permissions acceptance. |

## Focused finance remediation in work

**FIN-RES-01 — inconsistent persisted open refund reservation can be undercounted.**

- Before: `tuition_refunds.open_amount()` accounted for a persisted Approved request using `requested_amount` even if a malformed/migrated row had a different `approved_amount`, and silently ignored an unrecognized status. Example: Approved requested 10 AFN / approved 90 AFN was counted as 10 AFN of open reservation.
- Risk: finance admission of an additional refund request could be based on a misleading reservation total if persisted source evidence is inconsistent. Standard authorized approval commands already set equal amounts; this is a **defense-in-depth / corrupt-source fail-closed repair**, not proof of an exploitable end-user bypass.
- Fix: unknown statuses and inconsistent Approved amounts now refuse the reservation calculation. Valid Requested/Approved/Paid/Denied semantics are preserved. Tests check an ordinary approved reservation, malformed approval, and unknown status. The request remains nonpaying.
- Location: `apps/toefl_house/toefl_house/finance/tuition_refunds.py` and `tests/finance/test_tuition_refunds.py`.

**FIN-RES-02 — malformed stored approved amount escapes the boolean match contract.**

- Before: `refund_payment_matches()` validated a Payment Entry amount but called `_money()` on the requested approval amount *outside* its exception guard; an invalid stored amount raised `RefundError` instead of returning `False`.
- Fix: malformed Approved amounts return `False`; valid exact match is unchanged. Regression inputs include NaN, blank, null, and excessive fractional precision. This predicate is a defensive matching helper, **not** production authorization or an active native tuition payout path.

## CI truth (as read from GitHub Actions on 2026-10-29)

The preceding code head `ab7a0209` had observed **success** for Owned Suite, Native Lifecycle and Windows Customer Package Smoke (runs `40801282207` / `40801276576` / `40801324598`). At the same observation, Foundation was **in progress** (run `40801322291`) and the Product Image workflow ended **cancelled** (run `40801276451`), so **no complete final-head gate set** existed.

After the focused changes, the GitHub runs for `d559db3` were **in progress** (Owned `40805643005`, `40805639041`; Product Image `40805639149`) when observed. Native and Foundation runs initiated against the intermediate `7158ba2` do **not** qualify `d559db3`. All final code-head gates must be rechecked before release; statuses here are a timestamped observation, **not claims about future completion**.

## 29-Oct source hardening addendum — filelock advisories

Review of the actual failed Foundation job
[40801322291](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40801322291)
identified the precise fail-closed cause:
`STACK-ADVISORY-UNTRIAGED` for `filelock@3.20.3` advisories
`GHSA-69hj-f68j-2879` and `GHSA-8mx5-7m5m-r77g`. Both are fixed
upstream starting in `filelock 4.2.1`. This candidate now pins
`filelock==4.2.4` across Native, Foundation and the customer app image,
and extends the SHA-256-verified pinned Frappe dependency overlay from
four to **five** requirements so the pinned Frappe's old `~=3.20.1`
metadata cannot disagree with the installed package. The regression
suite was updated; no untriaged advisory was waived.

Details and mandatory compatibility/CI tests:
[SEC-DEPS-01 filelock remediation](evidence/sec-deps-01/filelock-2026-10-29/README.md).
**This is a committed source remediation, not a successful CI qualification.**
Do not call the Foundation or Product Image gates green until their exact
subsequent runs complete with success. Revalidate all roles, installed
versions, `pip check`, application APIs and the image. The native tuition
refund and Owner-machine recovery holds are unchanged.

## Unresolved production blockers

1. **Native tuition Fees partial refund accounting:** request approval exists; safe actual payout does not. Never replace the refusal with a direct Student Payment Entry or unreviewed Journal Entry. A valid native credit/reversal and GL/Fees/outstanding reconciliation must be designed, independently audited and tested before enabling.
2. **Complete exact-head CI**: Owned Python/Node, database-backed Native lifecycle, Foundation security/browser, Product Image artifact, and Windows package gates need verified successful receipts on the release candidate and dependency/pin review. A cancelled/queued/missing workflow is not a pass.
3. **Owner PC acceptance**: clean installed-product workflow on the designated Windows hardware, independent ZIP/image verification, roles, month rollover, attendance, books, payroll, tuition payments and receipt/handover, safe preserved upgrade/rollback.
4. **Backups and recovery**: real separate-drive schedule, encryption/key custody, actual two-person authorized recovery and isolated restore; do not touch existing Owner data, keys or disks during the hold.
5. **Governance**: independently review diff and production risks, reconcile the *diverged* `main` history, confirm license/company and tax configuration, explicit Owner acceptance and authorization. The held updater remains held.

## Required release disposition

- Retain `work` as the engineering integration branch and `main` unchanged. PR #120 remains review-only until all applicable gates pass.
- Maintain **TEST PACKAGE — NO REAL DATA** on candidate artefacts and preserve all existing Owner test-site data.
- Do not infer new success from previous run numbers, old README release snapshots or the existence of source code.
- The next reviewer should inspect the **new diff**, execute the regression tests and full CI, audit native refund accounting and Windows/recovery evidence, then record exact SHA and receipts. Until then: **HOLD**.

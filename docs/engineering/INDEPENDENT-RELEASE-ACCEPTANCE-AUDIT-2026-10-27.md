# Independent release acceptance audit — 27 October 2026

**Disposition: HOLD / NOT CUSTOMER-AUTHORIZED.**  
**Scope:** independent source/document review, not execution on the owner's Windows installation.  
**Evidence pin:** release PR #87 at reported candidate `49484403f89aca8982ca1c3b8500b1fb08ba5d2a`. This report must be refreshed after the primary agent advances its head.  
**Related:** issue #91; payroll agent PR #92 is independent and must not be treated as integrated.

## What was independently inspected

- [PR #87](https://github.com/Frotan2/TOFEL-House-ERP/pull/87), including its evidence and remaining gates.
- `docs/engineering/WINDOWS-RESUME-2026-10-26.md`
- `docs/engineering/WINDOWS-UAT-FINDINGS-2026-10-26.md`
- `docs/engineering/FINANCE-COMPLETION-2026-10-26.md`
- `docs/OWNER-OPERATING-POLICY-AFGHAN-2026-10-25.md`
- `apps/toefl_house/toefl_house/security.py`
- `apps/toefl_house/toefl_house/finance/period_reporting.py`
- `apps/toefl_house/toefl_house/finance/shamsi.py`
- The actual mobile-navigation fix commit `4948440`.

This is a **static independent audit**. No hosted CI, Windows browser actions, native transactions or financial postings were performed by this reviewer. Neither the preserved Windows test installation nor the primary release branch was changed.

## Verified source observations

1. **Production activation is fail-closed in the inspected security module:** `site_mode()` distinguishes explicitly synthetic sites, an explicitly activated production site, and refused configurations. Mixed synthetic + production flags are refused. This does **not** replace a dynamic deployment test.
2. **Finance month reports are separated from GL revenue:** `solar_month_receivables()` describes invoice and allocated-payment movements, exposes `unallocated_advances_included=False`, and labels its reconciliation as a native invoice/allocation view. Reporting interfaces must keep these labels intact and retrieve native GL revenue/cash/advances independently.
3. **Calendar is algorithmic rather than a hardcoded month dropdown:** `MONTH_NAMES` includes all 12 Afghan Solar Hijri months; `following_month()` and `add_months()` cross month and year boundaries. This supports months after Aqrab in source, but the end-user selector/period creation and UI rollover still require live acceptance.
4. **Receipt proposal is non-posting:** `suggest_oldest_debt_allocation()` returns a proposal only. The caller is explicitly responsible for student, Company, currency, permissions, native outstanding validation and locking before payment submission. Test these invariants in the actual Reception handler introduced after this evidence pin.
5. **Role authorization is independently enforced at the domain command layer:** `authorize()` refuses Guest, Administrator and disabled users, and checks explicitly assigned roles. Role-based landing-page routing is not itself a permission grant.

## New owner decision requiring source and documentation alignment

At 03:35 Asia/Kabul on 27 October, the Owner approved:

> On successfully issuing a Reception cash receipt, post the actual collection exactly once and reduce the student's outstanding balance then. Later Finance handover is a custody transfer and must not create a second student payment.

The PR #87 narrative viewed during this audit still says this decision is pending. Update it with the implemented revision and explicit proof. A draft or failed receipt must **not** reduce receivables. Counter custody and Company/Branch isolation must remain explicit, including the female Reception counter.

## Mandatory independent negative/edge cases

| Control | Required evidence | Current audit determination |
| --- | --- | --- |
| Natural staff login and mobile landing | fresh authentication, old /desk bookmark, own desk and forbidden deep links | Android Reception heading confirmed by Owner; complete workflows not yet evidenced |
| Company and Branch scope | allowed original receipt; access changed; replay becomes 403 without totals; fresh foreign writes denied | previous reported tests; rerun on exact integrated final head |
| Reception duplicate protection | repeat request token, concurrent requests, retry after timeout, partial failure, multiple fee obligations | OPEN |
| Native GL behavior | issued receipt vs native Payment Entry, AR reduction once, drawer Cash increased once, no double income | OPEN |
| Male/female cash custody | separate accounts, authorized daily count, Finance handover, variance investigation, immutable audit | OPEN |
| Advance month-two tuition | native advance, subsequent allocation, no fictional due-month GL revenue | OPEN |
| Books | purchase price, selling price, stock, return/refund reversal and cash/GL/stock reconciliation | earlier synthetic results; final-head and UI gate OPEN |
| Instructor payroll | native Salary Slip liability, one-off/monthly earnings, cancellation and privacy | prior synthetic results; final-head acceptance OPEN |
| Financial period rollover | Aqrab -> Qaws -> Jadi -> Dalwa -> Hoot -> Hamal/year transition, including leap Hoot | source functions exist; rendered reporting UI acceptance OPEN |
| Windows customer update | exact signed SHA, clean disposable install, preserved-site upgrade, rollback, backup+restore and UI | OPEN |
| Cross-device operation | physical Android form submits and reads; same restriction boundaries | mobile landing only accepted; transactions OPEN |
| Owner decision | signed acceptance, manifest not test-only, explicit production authorization | OPEN |

## Integration protocol for parallel agents

- Primary Work owns Reception collection, Finance custody/handover and release integration. Other agents use separate branches and PRs, never edit primary Work's checkout or the preserved Windows acceptance volumes.
- Do not count a green CI result on `d0f4ad4` as CI coverage for `4948440` or a future head.
- For each agent PR record changed files, exact head SHA, passing tests, expected integration conflicts, and real limitations; merge only after review.
- After integration, run complete exact-head Owned, Native, Foundation, Image, Windows and negative acceptance gates again.
- No branch deletion, customer data, production activation or "customer-ready" label until signed Owner acceptance.

## Audit verdict

**Hold remains justified.** The reviewed architecture has meaningful safety controls and previous native evidence, but key Reception cash custody workflows and final Windows/browser/product qualifications remain outstanding. This report is evidence of review, not authorization to release.

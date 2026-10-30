# Finance policy approval record (R05 / B07) — owner decisions 2026-09-15

**Status: R05/B07 RESOLVED at framework level — Finance (tuition & placement
billing) implementation authorized within the recorded framework. Actual
price values remain owner-supplied configuration data, never code constants.
Academic assessment (B04/B05) and payroll (A09) remain GATED. Production
remains REJECT.**

This records the business owner's decisions, collected 2026-09-15 (preserved in this
repository's Git history), which unblock the Finance domain
(P3.6, A08 canonical billing route already DECIDED). Prior gate text:
R05 (Git history).

## 1. Recorded decisions (verbatim where custom)

1. **Billing framework — approved starter framework.** Enrollment-generated
   native billing (A08 route): tuition is billed through the pinned Education
   app's native `Fees` authority (requires `program_enrollment`; native
   student/enrollment validation; native GL receivable posting on submit).
   A published price/deposit/installment schedule is represented natively by
   the `Fee Structure` master configured by authorized Finance
   administration — the owner supplies the actual values; no price, deposit
   or installment figure is hard-coded or invented in code. Discounts and
   waivers operate only through native `Pricing Rule` mechanisms within
   finance-approved limits (native `Authorization Rule` remains the native
   limit authority). Payment-before-participation with legitimate native
   Customer-advance semantics; no discretionary credit.
2. **Billing identity: TOEFL House — Afghanistan — AFN.** Invoices and fee
   documents are issued by legal entity *TOEFL House* under Afghan
   jurisdiction in Afghani (AFN). No Afghanistan-specific chart of accounts
   ships in the pinned ERPNext; the native Standard chart applies until an
   owner-approved statutory chart is supplied. Tax templates remain
   unconfigured (zero) until the owner supplies the applicable tax policy —
   absence of configuration is explicit, not an invented tax rule.
3. **Placement fee — configuration-driven (owner's verbatim direction):**
   "Placement is an internal entrance assessment, but its fee policy must be
   configurable, not hard-coded. It may be offered free or for a fee,
   depending on TOEFL House policy. Authorized Finance/Administration
   configuration must control the applicable fee, waiver rules, and billing
   behavior. Do not invent a price or permanently assume free/charged
   status. Use the native ERPNext financial mechanisms where applicable, and
   keep Placement's academic purpose and authority separate from its
   financial policy."
   - Representation: a native service `Item` priced in a native selling
     `Price List`; the configured rate decides chargeability. Rate absent or
     zero ⇒ placement is not billable (billing attempt denied); rate > 0 ⇒
     billable via native `Sales Invoice` against a native `Customer` created
     by Finance/Administration. Waivers via native `Pricing Rule`. The
     Placement domain's code, roles and academic authority are untouched;
     the finance module reads placement records read-only.
4. **Academic assessment (B04/B05): DEFERRED** by owner decision; remains
   gated, unimplemented.
5. **Payroll (R06/A09): unchanged**, remains gated.

## 2. Engineering translation (no invented values)

| Requirement | Native mechanism | Owned code |
|---|---|---|
| Tuition receivable | Education `Fees` (submitted; GL posting; program_enrollment required) | Thin idempotent `issue_tuition_fees` command (receipt + audit), deny-by-default direct-write guard |
| Price schedule | `Fee Structure` (program + academic year + components) configured by Finance | None — native master, native permissions |
| Placement fee | `Item` + selling `Price List` rate; `Sales Invoice` vs `Customer` | Thin idempotent `issue_placement_fee` command; Custom Field link `th_placement_case` on Sales Invoice; deny-by-default guard chained after the existing premature-billing guard |
| Waivers / limits | `Pricing Rule`, `Authorization Rule` | None — native |
| Money-in | native `Payment Entry` / `Payment Request` | None — native, role-restricted |
| Currency/company | Company `TOEFL House` (Afghanistan, AFN), Fiscal Year | Fixtures only |

Refund/withdrawal *terms* are still owner policy deliverables (R04/R05
detail); the native `Credit Note` route stays available to authorized
Finance staff but no automated refund rule is implemented or invented.

## 3. Boundaries unchanged

Placement, Admission, Enrollment and Teaching Operations remain CLOSED /
QUALIFIED and are not reopened by finance work except for the shared
receipt/audit ledger (Finance Auditor read rows, Teaching Auditor
precedent). No parallel money master: `TH Invoice`-style DocTypes remain
prohibited; ERPNext accounts stay the only money authority. Synthetic
isolated build only; production remains **REJECT**.

## 4. Owner direction of 2026-10-25 — Afghan calendar, semester and carry-forward

**Status: approved business intent, NOT production activation and NOT approval
to migrate existing books.** This direction supplements the 2026-09-15
framework above. Where the older framework presumed payment before
participation, the Owner has now expressly required a controlled mechanism
for student arrears and payments crossing month boundaries. Exact credit
limits, due dates and collection permissions still require policy approval;
until then no unrestricted discretionary credit may be enabled.

**Confirmed requirements**

1. **Calendar:** Afghanistan's Solar Hijri calendar, using the Afghan
   month names Hamal, Saur, Jawza, Saratan, Asad, Sonbola, Mizan, Aqrab,
   Qaws, Jadi, Dalw and Hoot. Financial periods and reports group by these
   months, not Gregorian months or fixed 30-day approximations. The fiscal
   year runs from 1 Hamal to the last day of Hoot; previously posted fiscal
   period mappings are not
   altered without an approved migration. Operational timezone: Asia/Kabul.
   Native Frappe / ERPNext canonical accounting dates remain ISO dates
   internally; the conversion/display/reporting layer must be bijective
   across leap-year and year-boundary edge cases and tested before launch.
2. **Weekly closure:** Friday is the only routine weekly day off. Do not
   populate other recurring or public holidays automatically. Exceptional
   closures, if any, must be explicit, authorized and auditable. The academic
   teaching-days policy and native HRMS Holiday List Assignment must be
   configured consistently rather than disabling either validator.
3. **Academic duration:** semesters contain **two Solar Hijri calendar
   months**, not sixty fixed days. Exact cohort/rolling start rule, program
   exceptions, pause/makeup and partial enrollment policy await approval.
4. **Tuition across months:** students may pay early, in the current
   month, or after the month to which tuition relates. Track the
   student's current-period charge, advance/credit, outstanding balance,
   payment date and allocation to the underlying native Education Fees.
   Preserve prior-period arrears until paid or formally adjusted; do not
   count collection of old debts as new-period earned tuition. A receipt
   is not the same event as earning revenue or creating a receivable.
   The customer-facing view must disclose both semester and month balances.
   Native Fees, Payment Entry and GL remain the only money authorities.
5. **Teaching payroll across months:** teaching compensation is attributable
   to the **worked Solar Hijri month**, normally **paid in the following
   month**. Show separate earned/accrued, approved, due, paid, unpaid and
   adjustment amounts by pay period and actual payment period. Maintain
   Finance-authorized native HRMS Salary Structure, Additional Salary,
   Salary Slip and payment controls. Neither draft Additional Salary
   calculations nor a slip submission may silently mean cash paid.
6. **Immutable history:** changing a semester term, policy or calendar must
   not rewrite submitted Fees, Payment Entries, Salary Slips, GL Entries or
   archived student/teacher assignment evidence. Reversals and authorized
   corrections use native document workflows.

**Unresolved Owner choices (must be confirmed before product configuration)**

- Are semester start/end dates common fixed two-Shamsi-month blocks, or
  individual rolling two-month enrollments? Are different programs exempt?
- Should two monthly tuition obligations be issued independently up front,
  or should one two-month semester invoice be split into two due installments?
  When is each amount due? Is any overdue fee, late penalty or debt limit
  authorized, and may a student attend while owing a balance?
- Do advance payments automatically offset the oldest outstanding fees or
  apply to a specific selected Shamsi month? Who approves refunds, writeoffs,
  transfers and discounts?
- What are the instructor pay bases (fixed salary, class/session, hours or
  skills), authorization steps and **following-month** pay date? Is the
  monthly payroll boundary precisely 1st-to-last Solar Hijri day for all
  staff? Who authorizes exceptions or backpay?
- What are the existing opening unpaid balances, advances, instructor
  liabilities and physical cash ledgers on cutover day? No automated
  opening-balance migration without a verified backup, reconciliation and
  Owner signoff.
- Who may approve special academic closure, exceptional Friday teaching,
  timetable changes, debt/waivers, writeoffs, and late payroll? Confirm
  policies through Settings UI with effective dates and audit trails.

**Implementation / acceptance holds**

- Current `finance/installments.py` uses a **fixed-day** interval and
  current `TH Billing Policy` defaults installments **off**. Neither
  satisfies this approved two-month Shamsi billing intent by itself.
  Do not advertise semester billing or arrears as ready until live
  calendar-month scheduling, native ledger allocations, history migration,
  permission checks and cross-boundary tests pass.
- A native HRMS salary slip depends on a submitted Salary Structure Assignment
  and a covered Holiday List Assignment. The synthetic hosted acceptance
  can provision these; production must derive Owner-approved originals.
- Release stays **NO-GO** pending exact-head CI, disposable physical
  Windows Docker Desktop backup/restore and old→new upgrade, monetary
  reconciliation and explicit Owner acceptance.

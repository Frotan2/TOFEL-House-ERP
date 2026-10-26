# TOEFL House — confirmed Afghan operating policy (Owner, 2026-10-25)

**Business decisions: APPROVED.** **Product release: NO-GO.**
This is the single current owner decision record; earlier unconfirmed
questions in `FINANCE-POLICY-APPROVAL.md` are superseded where contradicted.
Accountant and Owner must still supply opening balances and identify the
supported contractual payroll and financial recognition method.

## Calendar, academic program and attendance

- Afghanistan **Solar Hijri** calendar and **Asia/Kabul** timezone govern
  daily schedules, fiscal periods, financial reports and payroll periods.
  Fiscal year: **1 Hamal** through the last day of **Hoot**. Native posting
  dates remain ISO for ERPNext database integrity.
- **Friday is the sole recurring weekly holiday.** All other closures
  require an explicit authorized event; do not automatically import
  country or religious holidays. Exceptional Friday opening requires
  a dated auditable Owner calendar override.
- GE (General English) and EAP: two **Solar Hijri calendar months** per
  semester. A class has one published common start/end and a late entrant
  joins the existing class period. No personal re-start of that semester.
- Special Speaking, TOEFL Preparation, and other programs: their
  durations are distinct Owner Settings values, **not fixed two months**.
  Start/end dates must be reflected in native Academic Term / Student Group
  linked scheduling. Late-join fee proration is not authorized without a
  separate owner decision.

## Tuition, receipts, debtor management

- Two **independent monthly tuition obligations** associated with a
  two-month semester. Advance payment of both months is allowed using
  legitimate **native ERPNext advance** controls. One Payment Entry cannot
  be falsely counted twice or automatically treated as revenue.
- Monthly contractual due date: **first day of the Solar Hijri month**
  plus an Owner-configurable grace period. Versioned `TH Billing Policy`
  determines the optional monthly installment cadence and grace. Existing
  policy revisions retain the older daily cadence; no automated retroactive
  rewrite of posted accounting records.
- Unpaid fees carry to the next month and display warnings. **No automatic
  class suspension merely for debt.** Authorized decisions on attendance,
  withdrawals and account restrictions require a separate reviewed action.
- Default suggested allocation of a receipt: **oldest unpaid invoice
  first**. Finance can authorize a different allocation to the student's
  specified month. Reception records the collection and issues a numbered
  receipt; Finance reconciles the real native payment and male/female
  reception cash handover; unusual adjustments need Manager/Owner approval.
- The used portion of a withdrawing/transferring student's fee remains
  accounted for. Refunds/credit notes depend on a recorded Finance decision
  under the approved policy, not a silent delete or arithmetic guess.
- Finance reports separate: (a) invoice due month, (b) actual native GL
  revenue posting month, (c) actual verified cash month, (d) opening and
  closing receivables, (e) advance balances, (f) discounts, (g) refunds.
  Merely grouping Fees by due date must never be labeled GL revenue.

## Teacher and staff payroll

- **Owner clarification, 2026-10-26:** variable skill earnings are selectable
  **per contract**: one-off per assignment or recurring per Solar Hijri worked
  month. Existing contracts retain one-off behavior; cadence changes require
  a new effective-dated revision. This does not approve partial-month proration
  or automatic payroll submission/payment. See
  [implementation and remaining acceptance](engineering/FINANCE-COMPLETION-2026-10-26.md).

- Contract rules may be **fixed pay** or **class/session/skill** based;
  calculation belongs to existing native HRMS Salary Structure,
  Additional Salary and Salary Slip authorities, not a parallel ledger.
- Earning period: first through last day of the *worked Solar Hijri
  month*. Payments normally occur in the **following** Solar Hijri
  month, priority **through day 15**. Later payment can remain due
  through the **last day** of that following month; any balance after
  that remains visible as unpaid and overdue, not silently written off.
  These are priority/monitoring dates, NOT permission for payroll
  auto-submission, wage withholding or auto-penalties.
- Finance authorizes pay. Posting an Additional Salary draft, submitting
  a Salary Slip and recording a real bank/cash disbursement are distinct
  events and distinct dates. Correct tax/regulatory details require
  reviewed Afghanistan-specific payroll policy before live payments.

## Cutover, approvals and customer safety

- Set a single cutover date. Reconcile opening per-student arrears,
  advances, uncollected bills, teacher payable liabilities, male/female
  cash handover, and physical safe/bank balances before publishing.
  Use native opening entries with backup and full signoff. Never fake
  historic receipts or import unsourced cash totals.
- Reception, Finance, Instructor, Manager and Owner receive minimum
  necessary role permissions; salary details are Finance/Owner only.
  Manager/Owner must approve high-risk adjustments, exceptions and
  unusual writeoffs.
- No production activation until exact-head hosted tests (Owned,
  Foundation, Product Image, Native HRMS, Windows), real disposable
  **Windows Docker Desktop install → backup → restore → old→new update →
  rollback**, browser/UI acceptance, permission tests, independent
  cash/GL reconciliation and explicit signed Owner acceptance.

## Engineering implementation register (not delivery claims)

| Capability | New source / existing authority | Current level |
|---|---|---|
| ISO ↔ Afghan Solar Hijri / fiscal / Friday | `finance/shamsi.py` | Pure source + unit tests; hosted CI and physical acceptance pending |
| Two-month Shamsi windows | `finance/shamsi.semester_bounds`, TH Level Duration `Solar Hijri Month`, `teaching.create_student_group` | Wires Owner-selected whole Shamsi months into fixed class dates, refusing mismatched explicit ends. Configure **2** months on each GE/EAP level in Owner Settings; end-to-end hosted/browser acceptance still pending |
| Friday scheduling closure | `teaching/calendars.py` | Scheduler refusal except audited explicit Working Day; live rollout pending |
| Versioned first-of-Shamsi-month tuition due/grace | `finance/policies.py`, `finance/installments.py`, TH Billing Policy Version | Policy field + generation; Frappe native posting/revenue deferrals and browser GUI acceptance not yet proved |
| Student arrears and oldest-first payment suggestion | `finance/period_reporting.py` | Read-only reconciliation/proposal, **not integrated** with secure finance desk or automatic native Payment Entry |
| Teacher earned-month versus paid-next-month | `teaching/payroll_periods.py` | Read-only native voucher reconciliation, **not integrated** with HRMS payroll desk or live payment |
| Opening balances/advance transfers | Native ERPNext accounting | **NOT migrated; Owner cutoff/reconciliation outstanding** |
| Customer release/upgrade | Product release gates and PR #87 | **NO-GO** until all required checks and Windows acceptance |

No synthetic acceptance fixture or developer tool should ever operate on
customer production DB volumes.

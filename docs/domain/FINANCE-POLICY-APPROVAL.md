# Finance policy approval record (R05 / B07) — owner decisions 2026-09-15

**Status: R05/B07 RESOLVED at framework level — Finance (tuition & placement
billing) implementation authorized within the recorded framework. Actual
price values remain owner-supplied configuration data, never code constants.
Academic assessment (B04/B05) and payroll (A09) remain GATED. Production
remains REJECT.**

This records the business owner's decisions, collected 2026-09-15 on branch
`arena/01a0a496-tofel-house-erp`, which unblock the Finance domain
(P3.6, A08 canonical billing route already DECIDED). Prior gate text:
[BUSINESS-DECISION-RESOLUTION.md](BUSINESS-DECISION-RESOLUTION.md) R05.

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

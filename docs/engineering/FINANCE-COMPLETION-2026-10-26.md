# Financial completion work — 2026-10-26

Production decision remains **NO-GO**. This record describes source changes,
not completed Windows or financial acceptance.

## Owner decision recorded in this session

The Owner selected **configurable per contract** when asked whether variable
instructor earnings recur monthly or are paid once per assignment.

`TH Instructor Contract.earning_basis` now selects `One-off` (the default for
existing and new contracts) or `Solar Hijri Monthly`. The separate free-text
payment frequency describes disbursement timing and does not control earning
recurrence. Fixed Salary still uses native HRMS Salary Structure.

Finance creates a new effective-dated revision to change earning basis. A
revision that omits the field preserves the predecessor's basis. Supersession
cannot change the predecessor's earning basis, amounts, terms or historical
inputs in place.

Monthly calculation requires the complete first-to-last day of one Solar
Hijri month and complete contract and assignment coverage. Each assignment
can generate one enabled, noncancelled native Additional Salary draft per
worked month. Another request key cannot generate a second input for that
month; contract locks and native input locking reads remain in effect.
Earlier months do not suppress later months. Bonus/deduction adjustments
remain one-off per adjustment row. Cancelled inputs do not block replacement.

No partial-month proration, session-count rate, tax rate, automatic submission
or disbursement is inferred from this decision. Partial months require an
explicit Finance decision. Native payroll approval and actual payment are
separate from preparing a draft input.

## Other corrections

- Cash close validation rejects NaN, infinities, booleans and invalid values
  in counted/expected amounts, variances and totals. Signed ledger overdrafts
  and explained differences remain valid. Nonfinite comparisons cannot bypass
  the variance or explanation checks.
- Solar month receivables include opening and closing invoice balances and
  the reconciliation difference: opening + invoices posted - allocations in
  month - closing. This is a native invoice/allocation view, not GL revenue,
  all cash receipts or advance balances.
- A receipt allocated before its invoice posting is refused by that helper;
  native advance reconciliation must handle it separately. A bill due on the
  last day of the month is outstanding but not yet overdue that day.

## Acceptance still required

Run the added native per-contract two-month fixture and the complete hosted
gates on the exact new revision. Verify the new contract field and calculation
through the browser. Validate reception receipts and male/female drawer
handover, native advance allocation, refunds, monthly GL revenue and opening
balance cutover with independent cash/GL reconciliation. Then complete the
separate Windows lifecycle, recovery and Owner acceptance gates. The above
source improvements do not close those gates or authorize production use.

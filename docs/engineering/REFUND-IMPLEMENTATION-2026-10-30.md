# Tuition refund implementation — 30 October 2026

**Engineering in progress. Production REJECT. Existing Owner installation and
all historical acceptance evidence remain preserved.** Baseline:
`bdf6260db783cab1566233c2bf684d542b6c5d43`, PR #120.

The mission first adds a missing containment boundary: native Journal Entry
can address Student receivable and Fees references independently of Payment
Entry. The existing Student Pay guard alone cannot enforce case approval on
that second native surface. New Student/Fees journals and post-submit edits
are therefore refused until the qualified paired workflow exists. Legacy
cancellation remains subject to the operational gate and native permissions;
employee payroll, ordinary supplier and operating journals retain native rules.
Native acceptance attempts actual inserts and checks the exact guard refusal
and unchanged Journal Entry/GL counts. Pure policy tests supplement that check.

## Native mechanism qualification

The pinned [Journal Entry schema](https://github.com/frappe/erpnext/blob/4048fb70e14d1843956fcdabb7c3cca75a1cbcdd/erpnext/accounts/doctype/journal_entry_account/journal_entry_account.json)
permits Fees references; native Journal Entry carries those references into GL.
The existing assertion that every positive allocation against fully paid Fees
must be rejected was too strong: native reference details can be recomputed
from generic grand total instead of live Fees outstanding. That premise is
corrected without enabling payout.

`tools/native/tuition_refund_accounting_probe.py` executes real native controllers,
GL/Payment Ledger posting and cancellation in a **new** `refund-probe.localhost`
database with ERPNext and Education only. It refuses local execution, missing
synthetic guards, an owned-app site, or an existing Company. The main owned
acceptance sites and Owner data are never used for these raw accounting writes.
No accounting, outstanding calculation or guard is mocked.

The probe tests 1,000 AFN billed with 1,000 and 600 collected, then a proposed
200 refund: debit original tuition income/credit Student receivable with a
native credit journal against the exact Fees; native Student Pay against that
same Fees; cancel payout before cancelling credit. It checks exact voucher GL
rows, balance, party/reference, Fees outstanding, active Payment Ledger totals,
net income and cash before/after each stage. Every transaction case rolls back.
These are synthetic test amounts, never configured business prices.

Expected invariant: after the complete pair, outstanding equals its original
value, while retained income and cash each decrease by the refund. A rejected
or divergent native result fails the gate and must be investigated. **Source
plausibility is not database qualification, nor an approved Journal Entry
workaround.** Native results belong to the exact pushed commit's artifact.

## Work still required before enabling #115

Continuation: the isolated upstream accounting mechanism passed Native
[40991917641](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40991917641)
at `1ef3e4e0e53c78d9921fb8d063b428c4c2f59a53`, for both fully paid and
part-paid Fees, including cancellation of payout before credit. The command
savepoint infrastructure subsequently passed all five gates at
`d327e758375d3be59a8ad4eeb4d155fd15c62f19`, including a real MariaDB
failure test retaining a prior caller write and removing failed command data,
operation and audit records without an outside rollback.

The next paired implementation uses exact in-process native document identity,
current locking ledger reads, original income/receivable dimensions, scoped
main-Cash authority and cash availability, locked receipt provenance, immutable
credit/payment links and command-local rollback. Original source receipts are
frozen during Requested/Approved/Paid cases, including dimension-only changes;
the independently audited Reception handover remains permitted without changing
financial facts. The actual owned Native test must prove payout, replay,
independent actors, scope denial, both real post-submit failure rollbacks and
source/artifact mutation refusal. **337 local finance tests and source review
are not that proof.** Paired reversal, user-facing queues, full race acceptance
and final Windows candidate acceptance remain required before delivery.

The earlier checklist below remains the full completion scope; it is not a
claim that the new owned paired command has passed its first database gate.

- Prove the native mechanism, then implement atomic request/Fees/source-receipt
  locks and independently authorized Finance payout with immutable linked
  credit/payment IDs, live Company/Branch/account checks and idempotent replay.
- Enforce paired cancellation/reversal and protect original receipt changes;
  failure after credit must roll back both accounting and request state.
- Display gross collections, credits/refunds and net retained tuition distinctly.
  Native Fees `grand_total - outstanding_amount` alone is not net cash after a refund.
- Exercise all amount, split-installment, race/retry, isolation and negative-role
  cases on real database-backed records, then final Windows/browser acceptance.
- Preserve the fail-closed product payout until the mechanism and guards pass
  their actual acceptance. No Production activation or main merge is authorized.

Local containment validation: 337 finance tests pass; Ruff and whitespace checks
pass. This does not claim completion of the new hosted database probes.

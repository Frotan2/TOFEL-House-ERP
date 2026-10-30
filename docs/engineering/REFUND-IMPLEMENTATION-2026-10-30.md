# Tuition refund implementation — 30 October 2026

## Owner priority and release boundary — 30 October 2026

The Owner has explicitly prioritized configured daily ERP operation over further
refund expansion. Native paired payout, independent management/Finance authority,
unpaid approval withdrawal and the real concurrency gate remain in the release.
Paid-refund cash-return recovery is **deferred and unavailable**. Its experimental
source and Windows evidence are preserved outside the shipping application for
the next version; it is not signed off for delivery. All four former recovery
API paths map to an unconditional server refusal before database access. No
client flag, staff role or site setting can enable them. Individual cancellation
of the existing payout or tuition credit remains server-blocked. Customers must
not use manual Student journals or independent cancellation as a workaround.

The current concurrency gate's fresh-CI catalog prerequisite now explicitly
creates its own native test Item/UOM, rather than relying on the existing Windows
installation's onboarding defaults. This changes test scaffolding only and does
not weaken any financial assertion. All previous evidence below remains history.

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

The first owned run failed closed before credit insertion: native Journal Entry
child defaults replaced an unassigned Fees receivable cost center with the
Company default. The correction transports original empty dimensions as explicit
empty Links, preserving native defaults elsewhere and retaining exact guard/GL
comparison. A disposable Windows helper using current source and fresh local
document hooks submitted the actual native credit on the synthetic site,
verified both GL rows and every original dimension, then rolled back; original
Journal Entry/Payment Entry/GL counts were unchanged. This targeted diagnostic
does not qualify the entire paired command or replace its hosted Native gate.

The subsequent real Windows backend command test passed on the existing
synthetic recovery site: 100 AFN billed, 60 collected, independent request and
General Manager approval, then 1 AFN paired credit/payout with 40 outstanding
preserved. Actual controller submissions were followed by injected failures
after the credit and after the payout, caught without an outside rollback;
all command-local financial/operation/audit counts returned to their baselines.
Successful payout replayed exactly with the same key, a different key was
refused, and both individual artifact cancellations were refused. Finally the
outer synthetic test transaction rolled back and all eight business table
hashes matched their pre-test values. Only the additive refund DocType schema
import persisted on that synthetic recovery site. No Owner site was initialized.

The hosted negative-role fixture needs an Officer-only control because its
existing `finance_officer` intentionally also holds Finance Manager. The
post-submit failure test must patch each concrete native controller because
Journal Entry overrides `Document.submit`; patching the base class cannot
exercise that stage. Both corrections retain their original negative assertions
and execute real accounting before fault injection. Hosted rerun is required.

The next hosted failure confirmed that the minimal Finance Manager payer has
no native Fees read permission for HRMS's reference-detail helper. The existing
transaction-private, read-only reference lease is reused only under the exact
refund pair's server context, independent payer, exact Fees/Student set and
current request/Company/Branch checks. No role or global permission flag is
changed; temporary rows are removed before commit and the existing unclean
lease commit guard remains in force. Real Windows tests then passed with an
FM-only payer, both post-submit failures, successful native posting/replay and
unchanged share counts; all thirteen business/security table hashes matched
after the synthetic rollback. The full and partial payment source tests both
passed previously; the minimal-payer change still requires exact-head hosted
qualification and final candidate browser acceptance.

Unpaid approval withdrawal now has a separate General Manager command:
Approved -> Voided, retaining original approver/amount/evidence and recording
withdrawal actor, reason and time. It locks Fees before the request to serialize
with payout, removes only the unused reservation, and refuses Paid or linked
native accounting cases. The staff queue offers the withdrawal separately from
payout. Real Windows synthetic tests passed wrong-role refusal, exact replay,
retained original decision, released capacity for a new request, refused payment
of the voided case, refused withdrawal of a Paid case and unchanged native
financial counts; the outer transaction restored all thirteen table hashes.
Independent source review found no concrete defect. Simultaneous payout versus
withdrawal still needs actual concurrent acceptance; locking review is not
that evidence. Paid-case paired reversal remains a release requirement.

The four concurrent cases subsequently passed on Windows through independent
MariaDB connections with overlapping transaction intervals, using a new
synthetic Company, Branch and role-specific staff (FM-only payer with explicit
permitted Company and Branch). Same-key callers returned the same single native
pair; different keys for one case produced one pair and one refusal; payout
versus withdrawal produced exactly one valid final outcome. Two different Fees
each proposing 40 against 60 shared Cash produced one payout, one insufficient
funds refusal and 20 remaining Cash. All five original Fees balances remained
50, original Company records were unchanged, and the payer's pre-existing
DocShare rows were retained exactly with no temporary reference access left.

`tools/native/tuition_refund_races.py` now runs these genuine concurrent commands
at the end of Native acceptance. It creates synthetic records rather than
altering existing Company settings, preserves its evidence and performs no
production activation or deletion. Hosted exact-head qualification is still
required. These checks do not substitute for paid-case reversal, printable
payout evidence, net reporting or final installed browser acceptance.

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

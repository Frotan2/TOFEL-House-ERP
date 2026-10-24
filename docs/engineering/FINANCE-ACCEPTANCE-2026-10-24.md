# Finance acceptance report — Mission 4 (billing, tax configuration, book commerce)

Date: 2026-10-24
Branch: `arena/2537b25b-tofel-house-erp` (base `c22b9979542c88a2cd179e179a91829d07a79a3a`)
Release decision: **NO-GO** (unchanged). Production authorization: **REJECTED**
(unchanged).

This report reconciles what was built for the finance mission with the evidence
that actually exists. It separates three kinds of claim and never blends them:

- **Implemented and proven offline** — synthetic Python tests that run anywhere.
- **Implemented, proven only by hosted native CI** — synthetic ERPNext/MariaDB
  checks; the exact-SHA run is named when it exists.
- **Unperformed** — real Windows cashier/book-shop acceptance and the Owner
  release gates. These stay open regardless of green CI.

## Premise that is *not* in scope

The native book-sales defects were corrected on `main` before this work
([#35](https://github.com/Frotan2/TOFEL-House-ERP/issues/35): narrow Books-only
invoice path; hosted native run
[39893520229](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/39893520229)
at `62e9d10742cbe6990067af4377beaede4b0dceca`). This report does not reopen them,
does not describe them as present, and does not weaken the guards that closed
them. The accounting-fixture investigation that made refunds post correctly is
recorded in [evidence/native-book-refund-2026-10-23.md](evidence/native-book-refund-2026-10-23.md).

## 1. Requirement-by-requirement reconciliation

| # | Requirement | Implementation | Evidence | Status |
| --- | --- | --- | --- | --- |
| 1 | Audit tuition, placement fees, discounts, installments, receivables, Payment Entry, Sales Invoice, corrections, refunds, book inventory, financial permissions | `finance/__init__.py`, `finance/policies.py`, `finance/corrections.py`, `finance/installments.py`, `finance/taxes.py`, `finance/cashier.py`, `finance/refunds.py`; native `Fees`/`Fee Structure`/`Item Price`/`Sales Invoice`/`Payment Entry`/`Stock Entry`; permission wiring in `hooks.py`, `permissions.py`, `security.py` | `tests/finance/` (161 tests: billing policy 23, corrections, policy, book-ledger contract, native refund accounting, installments 18, taxes 15, cashier 21, refund guards 28, containment hooks) | **Implemented; offline PASS** |
| 2 | Preserve native accounting, GL, inventory ledger, pricing, tax templates, payroll as source of truth | No parallel ledger, no owned arithmetic for money states. Installment plans are native `Fees` documents; cash close **posts nothing**; tax module only reads native templates and refuses unbacked lines | `test_cashier.py` (close posts nothing), `test_taxes.py`, desk “money states only from native `docstatus`/`status`/`outstanding_amount`” contract in `tests/desk/test_desk_contract.py` (105 tests) | **Implemented; offline PASS** |
| 3 | Policy-driven tuition billing, fee adjustments, installment schedules, discounts, authorized corrections | Billing policy versions carry posting bounds, placement timing and installment terms; terms default **OFF**; installment split in integer cents with remainder on the last row; discounts resolve from the Course Owner’s `TH Discount Rule`; corrections via the existing framework | `test_billing_policy.py` (23), `test_installments.py` (18), `tests/configuration/test_discount_math.py`, `test_corrections.py` | **Implemented; offline PASS** |
| 4 | Configurable tax via native ERPNext facilities; never invent Afghan tax law | `finance/taxes.py`: reads native default selling templates and Item Tax templates; refuses any invoice tax line not backed by them (pre-insert and pre-submit); sign rule is native (expectation = `grand_total − net_total`, sales ≥ 0, credit notes ≤ 0); reports `No native tax configured` | `test_taxes.py` (15); native check `finance-tax-configuration-native-state` | **Implemented; offline PASS; native pending exact-SHA run** |
| 5 | Book receiving, availability, stock-enabled sales invoices, payment allocation, credit notes, refunds, restocking consistent | Native-only path retained; return guard enforces cumulative quantity and value limits, same customer/company, stock-enabled sale, Books item group; refund guard requires a submitted credit note of the same customer, cash/bank payment, full allocation, cleared receivable | `test_refund_guards.py` (24); native checks `book-*` (receipt, sale+GL+stock, payment, return/restock, refund reconciliation, HTTP commerce) | **Implemented; native PASS on the run cited in #35; guards extended since — new checks pending** |
| 6 | Safe cashier workflows, outstanding visibility, daily reconciliation, transaction history, reliable reports | Finance desk sections: Today, Outstanding receivables, Awaiting billing, Cash close, Cash close history, Tax configuration; commands `reconcile_cashier_day`, `issue_tuition_installment_plan`; reports `th_tuition_billing_register`, `th_placement_billing_register`. The close also enforces the native Company User Permission scope before it reads or writes. | `test_cashier.py` (17), `tests/desk/test_desk_contract.py` (105), `tests/foundation/test_role_desks.cjs` (8 desks, 72 guided actions) | **Implemented; offline PASS; real-cashier acceptance open (#35)** |
| 7 | Verify payroll integration with existing HRMS without rewriting teacher compensation | No payroll code changed. Teaching-assignment/compensation projections are read-only and remain on native HRMS `Salary Slip`/`Additional Salary`; payroll containment checks unchanged | `tests/teaching/test_compensation*.py`; native `no-academic-finance-payroll-writes` containment | **Unchanged; native PASS on prior run; A09/R06 remain gated** |
| 8 | Reject duplicate billing, unauthorized invoices, invalid mixed invoices, accounting inconsistencies, incorrect returns, forged offsetting entries, cross-branch violations | Duplicate guards (enrollment row lock, first-writer-wins), placement/tuition command-only invoices, mixed Books+service invoices refused, non-stock-update book invoices refused, cumulative return limits, refund allocation checks, command-only GL/stock seams, branch-scoped reads and money documents | `test_refund_guards.py`, `test_cashier.py`, `test_taxes.py`, `test_corrections.py`, `tests/placement/test_native_check_actors.py`; native negative checks incl. HTTP races, CSRF, GET-mutation, revoked-session, containment probes | **Implemented; offline PASS; native PASS on prior run, extended checks pending** |
| 9 | Auditability and period-correct records; never silently edit submitted history | Submitted documents are never rewritten; corrections are new submitted records with receipts; cash closes are immutable once submitted (duplicate refused, drift surfaced); billing policy versions are append-only | `test_corrections.py`, `test_billing_policy.py`, `test_cashier.py`, `tests/desk/test_desk_contract.py` | **Implemented; offline PASS** |

### Fail-closed defaults introduced by this mission

- **Installments**: a policy version that does not mention them reads as
  `installments_allowed = 0`, `max_installments = 1`,
  `installment_interval_days = 0`, so split billing is refused. Enabling them
  requires a Course Owner version recorded strictly after the latest one.
- **Tax**: with no owner tax policy there is no template, so no tax line can be
  posted; the desk states `No native tax configured` rather than inventing one.
- **Cash close**: no billing policy ⇒ no close is accepted (the closing window
  comes from the policy’s backdate bound); expected amounts come only from the
  native ledger; a submitted close is never overwritten.
- **Refunds**: a customer refund without a matching submitted credit note is
  refused, so no hand-built Payment Entry can quietly reverse a sale.

### Defects found while reconciling this report (fixed here)

| Defect | Why only a real site would show it | Fix |
| --- | --- | --- |
| `TH Cashier Day` used `autoname: naming_series:` without declaring a `naming_series` field, so the first native insert would be refused | Offline tests stub Frappe's insert path | Field added with series `TH-CASH-.YYYY.-`; command passes the same series; regression test walks every owned doctype with a series autoname |
| The installment-plan command was missing from `security.FINANCE_COMMANDS`, so `guard_fees` would have refused the plan's own `Fees` writes | The guard is only consulted on a live insert | Registered as a `Fees` command; a wiring test now asserts every finance command declares a guarded doctype and a command role |
| The refund guard blocked *cancelling* or editing a submitted refund, because the settled credit note rightly owes nothing by then | Native cancel is not exercised offline | The cancel/post-submit paths re-assert settlement shape but not the "no more than it owes" ceiling; creation and submission keep the strict limit. Tests added |
| The cashier command's public `date` parameter shadowed `datetime.date`, so `date.fromisoformat(day)` raised `AttributeError` on the argument | Only visible on a real site; the offline shape tests never entered that branch | Class imported as `_date`; an executable regression asserts the business "valid business date" message, and an AST guard refuses the shadowing. Found by native run 40091964812 |

## 2. Evidence actually executed for this branch

Environment: offline checkout, Python 3.11.2, Node 22. No Docker, no installed
`frappe`/`bs4`/`ruff`, so native-site and lint gates cannot run locally and are
not claimed here.

| Command | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -t .` | **1,760 tests**, 10 skipped, **3 errors** — all three are the pre-existing `bs4`-dependent real-sanitizer modules failing to import `bs4` in this environment; **no test failure** |
| `python3 -m unittest discover -s tests/finance -t .` | **161 tests, OK** |
| `python3 -m unittest tests.finance.test_installments tests.finance.test_taxes tests.finance.test_cashier tests.finance.test_refund_guards` | **82 tests, OK** (18 / 15 / 21 / 28) |
| `python3 -m unittest tests.desk.test_desk_contract` | **105 tests, OK** |
| `python3 -m unittest tests.finance.test_billing_policy tests.finance.test_containment_hooks tests.foundation.test_app_assembly` | **OK** |
| `python3 -m unittest tests.placement.test_native_check_arity tests.placement.test_native_check_names tests.placement.test_native_check_actors tests.foundation.test_final_hosted_acceptance` | **65 tests, OK** (static guards over the harness edits) |
| `node tests/foundation/test_role_desks.cjs` | **Role desk contract OK (8 desks, 72 guided actions)** |

The three `bs4` errors are environmental, not product regressions: the modules
import `bs4` at module scope and the interpreter has no site packages. They are
owned by hosted CI, where the dependency exists.

## 3. Native (ERPNext/MariaDB) evidence

The native suite (`tools/native/native_checks.py`) is the only place the
synthetic ERPNext lifecycle runs. This branch **appends** finance checks to it:

| New native check | What it proves |
| --- | --- |
| `finance-installments-off-by-default-denied` | A policy version without installment terms refuses a split, with the actionable message, on a real site |
| `finance-installments-wrong-role-denied` | Enrollment Officer cannot split a tuition bill |
| `finance-installments-refusal-writes-nothing` | The refused split left zero `Fees` for that enrollment |
| `finance-tax-configuration-native-state` | The readiness surface reports the true native tax state, and an invented tax line is not permitted when nothing is configured |
| `finance-cashier-day-close-native-ledger` | Expected = native GL closing balance (independently re-read in SQL); unexplained variance refused; close submitted and stored; duplicate refused; desk position shows the close with no drift |
| `finance-cashier-close-wrong-role-denied` | Accounts User without Finance Officer cannot close a day |
| `finance-cashier-close-future-day-denied` | A future business date is refused |

**Status: PASS on the exact code SHA.** Native lifecycle integration
[run 40094216697](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40094216697)
**SUCCESS** at `0e8eee447bae79d4f4f8754a506ad481230e699f`, together with Owned
suite
[40094222085](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40094222085)
**SUCCESS** on the same SHA. Foundation runtime
[40094216664](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40094216664)
was still **in progress** when this report was written and is not claimed
either way; the preceding code SHA `6a183b5` completed all three workflows
(Native
[40092775298](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40092775298),
Owned
[40092775280](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40092775280),
Foundation
[40092775285](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40092775285)).
The first native attempt on this branch
([40091964812](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40091964812),
`e2882fc`) **failed** at `finance-cashier-day-close-native-ledger` with
`AttributeError: 'str' object has no attribute 'fromisoformat'` — the
shadowing defect in the table below — and passed after the fix. Per-check
counts are not quoted: the retained artifact and job logs could not be
downloaded from this environment, so the evidence here is the run conclusion
plus the recorded failure annotation from the failing attempt.

A positive installment plan is deliberately *not* asserted natively: owner terms
take effect from a date strictly after the latest recorded version, so the
split path cannot be positively exercised inside a single synthetic run. The
positive path is covered by `tests/finance/test_installments.py`, and the real
positive-path acceptance is steps C24–C26 of the cashier procedure.

## 4. Still unperformed — the real gates

| Gate | Issue | Why CI cannot substitute |
| --- | --- | --- |
| Real Windows cashier and book-stock acceptance (including the new close, installment and tax steps) | [#35](https://github.com/Frotan2/TOFEL-House-ERP/issues/35) | Physical counting, real screens, real operator; procedure: [CASHIER-ACCEPTANCE-PROCEDURE.md](CASHIER-ACCEPTANCE-PROCEDURE.md) |
| Real Owner Windows lifecycle and recovery | [#12](https://github.com/Frotan2/TOFEL-House-ERP/issues/12) | Requires the Owner’s machine, backup drive, Task Scheduler and key custody |
| Prebuilt verified Windows package | [#36](https://github.com/Frotan2/TOFEL-House-ERP/issues/36) | Requires a delivered, verified package — not a source build |
| Fail-closed graphical update path | [#40](https://github.com/Frotan2/TOFEL-House-ERP/issues/40) | Requires the real update UI and refusal behaviour on Windows |
| Payroll A09 / assessment B04–B05 decisions | `docs/FINANCE-POLICY-APPROVAL.md` | Owner decisions outstanding; no code change authorized |

Preservation/restore remains on **HOLD**. Do not back up, restore, clean up or
activate anything on the Owner site to close these gates.

## 5. Non-claims

- The native evidence is the run named above, on `6a183b5`. Later commits in
  this branch are documentation only and do not re-trigger the native
  workflow; re-run it on the final release commit before quoting it as the
  release evidence.
- No claim of cashier acceptance, physical counting, or Windows behaviour.
- No claim of ruff/lint or dependency-audit status (not runnable here).
- No Afghan tax rate, exemption, jurisdiction or accounting rule is encoded or
  implied anywhere in this change; the documented state is “no native tax
  configured”.
- No payroll or teacher-compensation change, and no release authorization.

## 6. Reproduce

```text
python3 -m unittest discover -s tests -t .
python3 -m unittest discover -s tests/finance -t .
node tests/foundation/test_role_desks.cjs
```

Native (hosted, pinned stack):

```text
python3 tools/native/run_native.py
```

Real-machine acceptance: follow
[CASHIER-ACCEPTANCE-PROCEDURE.md](CASHIER-ACCEPTANCE-PROCEDURE.md) on a
disposable Windows PC and attach the redacted evidence pack to #35.

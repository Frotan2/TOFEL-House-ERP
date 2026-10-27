# Book inventory, sales, returns and refunds — finalization (Agent 2, 2026-10-26)

**Scope:** Book catalog, purchase cost and selling-price configuration, stock
receipts and valuation, book sales, returns/refunds/credit notes, stock
adjustments, inventory reconciliation and book-sales reporting usability.
**Baseline:** `4948440` (PR #87 draft head, incl. merged #88/#89/#90).
**Authorities:** native ERPNext only — `Item`/`Item Group`, `Item Price`,
`Warehouse`, `Bin`, `Stock Ledger Entry`, `Sales Invoice`, `Payment Entry`,
`Stock Entry`, `Stock Reconciliation`, GL. No parallel ledger was added.
**Production decision: unchanged NO-GO.** This is source + synthetic-site
evidence, not Windows/staff acceptance (issue #35 / matrix B-04 stay open).

## Confirmed defects found and fixed

Both defects below were reproduced against the pre-fix code before patching.

| # | Defect (pre-fix behavior) | Fix |
|---|---|---|
| 1 | **A submitted full return could never be cancelled.** `prior_returns_for` counted the return itself as a prior return and `book_return_permitted` added it again as the current return (2 + 2 > 2 sold), so the authorized native reversal was refused. | `prior_returns_for(..., exclude=doc.name)` for already-submitted returns (`finance/refunds.py`); regression test + native check `book-native-return-cancel-reverses-stock`. |
| 2 | **A 1-of-2-books return credited at 2× the sold rate into a different warehouse passed every guard** — full sale value out, half the books back, into the wrong branch's stock. Quantity/value ceilings were keyed by item only, totals only. | Return quantities are now keyed by `(item, warehouse)` and a per-unit rate cap (`return_rates_ok`) refuses credit above the sold net rate; native check `book-native-return-warehouse-and-rate-abuse-denied`. |
| 3 | **Book sale rates were free-typed.** No configured selling price was required or checked (the synthetic fixture itself sold at a hardcoded rate with no Item Price). A cashier could bill any amount and pocket the difference. | New-sale terms (`finance/books.py: book_sale_terms_ok`): a positive configured selling `Item Price` in the invoice's price list/currency is mandatory and the line rate must equal it; below-list only via a native Pricing Rule; hand-typed document discounts refused. Fixture now seeds the Item Price. |
| 4 | **Overselling a warehouse bin relied solely on site Stock Settings.** With `allow_negative_stock` on, book sales could drive bins negative. | Stock-cover check per `(item, warehouse)` on new sales refuses quantities beyond the bin before posting (setup guidance below still recommends the native setting off). |
| 5 | **Only the exact `Books` group sold.** Program shelves (GE, EAP, Special Speaking, TOEFL Preparation, …) as sub-groups were rejected. | Nested-set subtree test `book_item_group_ok`: `Books` or any descendant; native check `book-native-program-subgroup-sale`. |
| 6 | **Stock documents had no integrity seam.** Zero-value Material Receipts poison moving-average valuation; Material Issue / Stock Reconciliation could silently write books off. | New `doc_events` guards (`finance/books.py`): book receipts require a positive purchase cost (Basic Rate); book issues and count corrections are approved adjustments — Stock Manager or Finance Manager, stated reason, Company User Permission. Non-book stock documents pass untouched. |
| 7 | **Company/Warehouse User Permissions were not asserted on the native book/refund paths** (PR #90 scoped the commanded paths only). | Book sale guard asserts Company + per-line Warehouse permission; customer-refund guard asserts Company permission (native semantics: no rows = unrestricted HQ). |
| 8 | Finance-desk book shortcuts stopped at sales; purchases, stock movements and counts were unreachable from the desk. | Added permission-gated native links: Purchase Receipt, Stock Ledger Entry, Stock Reconciliation (each appears only with real native rights). |

Reversal safety is deliberate: cancel and post-submit-edit paths skip the
new-sale price/stock-cover terms, so a later price change or an emptied bin
can never trap a legitimate sale against authorized cancellation.

## How each workflow now runs (all native)

- **Catalog:** create `Item Group` *Books* (tick *Is Group*), optional program
  sub-groups under it, stock+sales `Item`s per title (UOM *Nos*).
- **Selling price:** authorized staff (native *Sales Master Manager*) maintain
  selling `Item Price` rows in *TOEFL House Standard*; the invoice rate is
  then enforced against that configuration. Discounts, if ever approved,
  belong in native Pricing Rules — never typed on the invoice.
- **Purchase cost:** buying `Item Price` records are the cost reference;
  `Purchase Receipt` rate carries the actual cost into valuation. `Stock
  Entry` Material Receipts (opening stock) must state a positive Basic Rate.
- **Sale:** Finance Officer + Accounts User posts a stock-updating Sales
  Invoice (Books lines only, own Company/Warehouse scope); native stock and
  GL post together. Settlement is the native `Payment Entry` (shared receipt
  orchestration remains the Work agent's seam — see dependency below).
- **Return/refund:** native credit note against the original sale, capped
  cumulatively per item **and warehouse**, per-unit rate and document total;
  cash refund only as a `Pay` Payment Entry settling that credit note from
  Cash/Bank with no unallocated remainder (pre-existing guard, now also
  Company-scoped). Duplicate returns/refunds remain impossible: ceilings are
  cumulative across every submitted return, and a refund cannot exceed what
  the credit note still owes.
- **Adjustments:** Material Issue / Stock Reconciliation on book lines only
  by Stock Manager/Finance Manager with a stated reason; everything stays in
  the native immutable ledger history.
- **Reconciliation:** `finance.books.reconcile_book_stock` compares every
  book Bin against the sum of its Stock Ledger rows (quantity **and** value);
  the native cycle asserts this after sale → payment → return → refund →
  cancel, draining the queued native Repost Item Valuation first so the
  settled state is what is judged (`book-native-stock-ledger-reconciliation`), alongside the existing
  row-direction GL/SLE evidence validator
  (`book-native-return-cash-refund-reconciliation`, unchanged).

## Evidence in this change

- Owned unit tests: `tests/finance/test_book_commerce_guards.py` (price
  resolution incl. slabs/validity, rate equality, Pricing-Rule-only
  below-list, stock cover, warehouse/rate-capped returns, cancellable full
  return vs. refused second return, Company-scoped refunds, valued receipts,
  approved write-offs, reconciliation discrepancies, hook wiring).
- Native-site checks (synthetic, in `tools/native/native_checks.py`, now
  required by `final_acceptance_report.py`): `book-native-unconfigured-price-denied`,
  `book-native-oversell-beyond-bin-denied`,
  `book-native-return-warehouse-and-rate-abuse-denied`,
  `book-native-return-cancel-reverses-stock`,
  `book-native-program-subgroup-sale`,
  `book-native-stock-ledger-reconciliation`.
- Existing book cycle, HTTP cashier cycle, refund guards, containment hooks
  and ledger-reconciliation contracts continue to pass.

## Dependency on the primary Work agent (not implemented here)

Book sales today are Finance-officer native invoices; there is no Reception
counter book-sale command, because receipt/counter-cash orchestration is
exclusively Work's seam. If the Owner wants Reception to sell books at the
counter, the minimal shared patch for Work is:

1. register one new guarded kind (e.g. `sell_books`) in `security.py`
   (`KIND_ROLES` → the Owner-chosen counter role, `FINANCE_COMMANDS` →
   `Sales Invoice`) executed through `_execute(request_key, …)` so replayed
   submissions are idempotent — native free-form invoices cannot offer
   request-key duplicate protection;
2. build the invoice **without client-supplied rates** (item codes,
   quantities, warehouse only), letting native pricing fill rates — the
   guards in this change already enforce configured price, stock cover,
   Company/Warehouse scope on the resulting document;
3. collect payment through the same counter-cash/handover decision as
   tuition (Work's pending Owner choice); until then, do **not** widen
   Reception with Accounts User as a shortcut.

No file owned by that seam was modified in this change; `finance/cashier.py`,
`finance/corrections.py`, `security.py` and the receipt commands are
untouched.

## Owner setup checklist before first real book sale

1. Create *Books* (Is Group) and program sub-groups; create book Items.
2. Enter selling Item Prices (and buying prices as cost reference) — sales
   fail closed until a selling price exists for each title/currency.
3. Keep **Stock Settings → Allow Negative Stock = OFF** (the sale-time cover
   check is a second line of defense; the native setting is the race-safe
   one at submit).
4. Assign native roles minimally: cashier = Finance Officer + Accounts User;
   price configuration = + Sales Master Manager; receipts = + Stock User;
   write-offs/counts = Stock Manager or Finance Manager; invoice/return
   cancellation requires native cancel permission (Accounts Manager).
5. Company- or Warehouse-scoped staff get explicit User Permissions; book
   documents now honor them on every path.

## Known limits (explicitly not claimed)

- Two *simultaneous* submits racing the same bin are serialized only by the
  native negative-stock setting; the validate-time cover check narrows but
  does not lock the window.
- Purchase Receipt rates are native PO/PR authority and are not hard-capped
  to Buying Item Prices in this change (valuation enters from the receipt,
  as ERPNext intends); only Stock Entry book receipts enforce a positive
  cost on our seam.
- Return/refund lookups are bounded at 1,000 lines/returns per document.
- Selling-price equality compares the invoice rate to the tax-exclusive
  list rate. The Owner has configured no book tax today; if a future
  tax-inclusive ("included in print rate") template is approved, the
  comparison must be revisited with the tax module before use — sales
  fail closed until then.
- No graphical, Windows, Android or staff-device acceptance is claimed;
  B-04/#35 and the PR #87 release gates remain exactly as they were.

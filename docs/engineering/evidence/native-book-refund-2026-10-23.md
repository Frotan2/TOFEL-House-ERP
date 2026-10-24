# Native book refund: missing wizard accounting fixture

Baseline: `57763a81f7579982a5dfb6136c4e8aed7318bd43`.
Failure: [native run 39986241609](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/39986241609),
job `120526044911`, retained artifact `native-lifecycle-39986241609-1`
(artifact ID `12516675158`). The retained failure diagnostics are historical
evidence, not a passing qualification. They record a Customer Pay entry from
Cash to Debtors, paid/received/base amounts 600 AFN, document difference 0,
and a Sales Invoice return with total/outstanding/allocation -600 and
`update_outstanding_for_self=1`. The reported GL difference is -1200.

The earlier inference that this pinned release does not support a direct cash
refund is incorrect. Failed qualification alone did not establish that.
Actual pinned source explicitly implements the refund sign reversal.

## Source trace

ERPNext `4048fb70e14d1843956fcdabb7c3cca75a1cbcdd` was read from the local
`toefl-house-erp-app:ci` image `87d19595add8` using a disposable, read-only,
network-disabled container without volumes. Checkout HEAD was verified; the
three accounting/fixture files match their committed blobs byte-for-byte.

| Source | Full file SHA-256 |
| --- | --- |
| `erpnext/accounts/doctype/payment_entry/payment_entry.py` | `15cb6287ad4e726e09dcb310c13920a7327aab10d66cf7bda379929b340611bd` |
| `erpnext/accounts/general_ledger.py` | `9a315ae0618d5e1ed6da0f0e09a03f01438c309cb5a22806ee4f405fc9a81702` |
| `erpnext/setup/setup_wizard/operations/install_fixtures.py` | `3ec261fff410fc63c5d908c3ed0a177452b7e73cd82c179535c056eb685387b1` |

1. The wizard's `get_preset_records` supplies `Customer: Receivable`,
   `Supplier: Payable`, `Employee: Payable`, and `Shareholder: Payable`
   (lines 296–299). Wizard `stage_fixtures` invokes fixture installation;
   ERPNext's ordinary `after_install` does not install these records.
2. The native suite explicitly skips the wizard. Its `finance_catalog`
   recreated UOM, Item Group, Customer Group, Territory and related setup
   prerequisites, but omitted Party Type. No other setup path in that suite
   seeded those records.
3. `PaymentEntry.add_party_gl_entries` reads `Party Type.account_type` at
   line 1352. Lines 1377–1386 reverse the side for a negative invoice reference
   only when that mapping is Receivable + Pay (or Payable + Receive).
4. Without the Customer mapping, the -600 allocation goes into **debit -600**.
   Native `toggle_debit_credit_if_negative` turns it into **credit 600**.
   The bank line is also **credit 600**: debit minus credit is **-1200**.
5. With the wizard fixture, the party line starts as **credit -600**, then
   normalizes to **debit 600**. Cash remains **credit 600**. The original
   negative allocation and invoice reference stay intact.

## Fix and verification

`seed_native_party_types` obtains the actual pinned wizard presets, inserts
only missing Party Type records during synthetic finance setup, and verifies
all mappings. Replay writes nothing; a conflicting existing mapping fails
explicitly without overwriting it. The country argument is required by the
pinned preset function and matches this synthetic finance company's Afghanistan
setting; unrelated country/catalog presets are not inserted.

`tests/finance/test_native_refund_accounting.py` executes hash-checked verbatim
upstream functions. Six tests reproduce the exact -1200 error before setup;
verify full/partial refunds across company/account/transaction currencies;
retain negative invoice allocations; cover customer receipts, mixed invoice
and credit-note receipts, supplier payments and refunds; verify idempotence
and conflict handling; and prove the native validator still rejects a wrong
cash amount after setup. Currency coverage here means the three AFN amount
columns, not a claim of foreign-exchange integration coverage.

Validation command:

```text
python -m unittest tests.finance.test_native_refund_accounting tests.foundation.test_final_hosted_acceptance tests.placement.test_native_check_names tests.placement.test_native_check_arity tests.placement.test_native_check_actors -q
```

Result: 71 tests, OK, one existing skip. Targeted Ruff check passed.

The existing native refund diagnostics and both native/HTTP sale-payment-return-
refund qualification requirements are unchanged. No product accounting code,
ledger validation, tolerances, or expected accounting evidence were changed.
A fresh hosted native-site qualification is still required: these site-free
regressions do not claim a successful persisted posting or stock reconciliation.
No operational container, site, or data was mutated during this investigation.

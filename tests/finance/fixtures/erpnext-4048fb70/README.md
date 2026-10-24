# Pinned ERPNext refund accounting source

These are verbatim function excerpts from ERPNext commit
`4048fb70e14d1843956fcdabb7c3cca75a1cbcdd` (v16.34.2), read from the
`toefl-house-erp-app:ci` image, ID `87d19595add8`. The image's source checkout
HEAD was verified, and each full file was compared byte-for-byte with
`git show HEAD:<path>` before recording its SHA-256.

`manifest.json` records upstream paths, complete-file hashes, original inclusive
line ranges, and excerpt hashes. Each excerpt joins the listed ranges in order
with one additional newline. Tests check the excerpt hashes before execution;
only the common class indentation is removed to bind the methods to a small
document double. No accounting logic is translated or rewritten.

Upstream sources:

- [Payment Entry](https://github.com/frappe/erpnext/blob/4048fb70e14d1843956fcdabb7c3cca75a1cbcdd/erpnext/accounts/doctype/payment_entry/payment_entry.py)
- [General ledger](https://github.com/frappe/erpnext/blob/4048fb70e14d1843956fcdabb7c3cca75a1cbcdd/erpnext/accounts/general_ledger.py)
- [Wizard fixtures](https://github.com/frappe/erpnext/blob/4048fb70e14d1843956fcdabb7c3cca75a1cbcdd/erpnext/setup/setup_wizard/operations/install_fixtures.py)

Copyright Frappe Technologies Pvt. Ltd. and contributors. These upstream
excerpts retain ERPNext's GNU General Public License v3 licensing; see
[upstream license](https://github.com/frappe/erpnext/blob/4048fb70e14d1843956fcdabb7c3cca75a1cbcdd/license.txt).

The tests double document storage, metadata defaults, exchange-rate precision,
and framework utilities. They execute the actual allocation conversion,
party/bank GL construction, negative normalization, native imbalance rejection,
and wizard preset function. They do not claim database posting, payment-ledger
updates, HTTP authorization, or stock reconciliation; the existing native
qualification remains responsible for all of those.

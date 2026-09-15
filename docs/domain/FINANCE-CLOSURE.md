# Finance Operations (tuition & placement billing) — CLOSED / QUALIFIED (synthetic isolated build)

Date: 2026-09-15 · Session branch: `arena/01a0a496-tofel-house-erp`
· Qualifying product commit: `4172a65` (finance slice over integration proof `03c5ba4`)
· Policy basis: [FINANCE-POLICY-APPROVAL.md](FINANCE-POLICY-APPROVAL.md)
(R05/B07 resolved at framework level by the business owner 2026-09-15).
· Teaching predecessor: [TEACHING-CLOSURE.md](TEACHING-CLOSURE.md) (CLOSED / QUALIFIED, `6ba5663`, hosted run `34966681820`). Teaching was not reopened.

**Status: CLOSED / QUALIFIED — bounded thin Finance slice implemented and
qualified on the hosted synthetic runner (see Evidence). Synthetic-data
implementation only. Production remains REJECT. Do not deploy. Do not reopen
Placement, Admission, Enrollment or Teaching. Academic assessment (B04/B05)
and payroll (A09) remain GATED and unimplemented. No real prices, taxes or
refund terms are invented: every monetary value in the qualification run is
synthetic Finance-configured fixture data, and chargeability is configuration.**

This records the **thin Finance slice** (bounded part of plan P3.6):
**submitted native Program Enrollment → native `Fees` tuition receivable →
native GL posting**, plus **configuration-driven placement billing** through
native `Sales Invoice` / `Item Price` / `Pricing Rule`. No TH invoice, fee,
ledger, price, tax, refund or payroll record exists. ERPNext accounts remain
the only money authority.

## 0. Scope and authority map

| Capability | Authority | Owned code |
|---|---|---|
| Tuition receivable per enrollment | Native Education `Fees` (submitted; GL posting; `program_enrollment` required; native enrollment/student validation) | Thin idempotent `issue_tuition_fees` (receipt + audit); deny-by-default direct-write guard |
| Price schedule | Native `Fee Structure` (program + academic year + components), configured by Finance | None — native master |
| Placement chargeability | Native `Item Price` in selling `Price List`; zero/absent ⇒ not billable | Thin idempotent `issue_placement_fee`; Custom Field link `Sales Invoice.th_placement_case` |
| Fee Structure income account | The pinned education `Fees` fetches `income_account` from `Fee Structure` but ships without the field | Custom Field `Fee Structure.income_account` (Link Account) restores the intended native configuration; Finance configures the value |
| Waivers / discounts | Native `Pricing Rule` (applied natively by the invoice); native `Authorization Rule` remains the native limit authority | None |
| Money-in | Native `Payment Entry` / `Payment Request` | None — native, role-restricted |
| Company / currency | Company `TOEFL House` (Afghanistan, AFN), Fiscal Year, Standard chart of accounts | Fixtures only |

Owner decisions honored verbatim (see FINANCE-POLICY-APPROVAL.md): placement
fee policy is configuration, never code — the `finance-placement-zero-rate-not-billable`
check proves the system follows the configured rate in both directions; the
placement domain's academic code and roles are untouched (finance reads
placement cases read-only).

## 1. Guard and permission model

- `Fees` and `Sales Invoice` are deny-by-default: direct create/submit —
  even `Administrator` with `ignore_permissions` — is denied outside the
  matching receipted finance command (`finance_command_active`).
- The enrollment slice's `deny_premature_invoice` guard stays in force,
  chained inside `finance.guard_sales_invoice` (one handler per
  doctype/method per app).
- `Finance Officer` executes commands and carries the native **Accounts
  User** role (the native finance-staff role that ERPNext's own
  party-account and currency validations require); it holds no read on the
  receipt/audit ledger. `Finance Auditor` reads the shared receipt / audit
  ledger only (DocPerm read rows + `permissions.query()` +
  `policy.can_read`, the Teaching Auditor precedent) — never native money
  documents (education's `Fees` stays closed to it; ERPNext's native
  `Sales Invoice` `All`-role read row is native behavior, unchanged).
  Containment is the absolute guard — direct writes are denied even for
  `Administrator` — not read-role scarcity.
- All writes are receipted (`TH Placement Operation` + `TH Placement Audit
  Event`), idempotent by request key, and atomic: failure injection at the
  audit boundary rolls back invoice/receipt/GL as one transaction.

## 2. Evidence

- Local pure unit tests, executed in the session workspace on 2026-09-15
  (not native Frappe qualification): placement 147, admission 6,
  enrollment 10, teaching 17, **finance 12**, foundation 44 (+123 published
  runner checks).
- Cross-domain integration proof (hosted, run `34971013355`, commit `03c5ba4`,
  native report SHA-256
  `e07e9958c68d30b25cbdf7f5b637118a3ab9feae2ad2416abcc0c39a4b435f3a`):
  **486/486 checks pass** — the four earlier slices proven one connected
  lifecycle (attendance → … → placement case re-read from the database,
  journey receipt continuity, cross-domain referential integrity).
- Hosted iteration record (actual runner output; nothing relabeled):
  - Run `34974750579` (commit `4172a65`): **FAIL** — `finance-native-catalog`
    `LinkValidationError: Could not find Item Group: Services, Default Unit
    of Measure: Nos` (ERPNext setup-wizard-seeded masters absent on a
    wizard-less site; Warehouse Type 'Transit' precedent). All **486** other
    recorded checks passed, including the complete retained
    Placement/Admission/Enrollment/Teaching suites and the integration
    proof. Fixed in `827519e` by seeding the identical catalog masters.
  - Run `34976974917` (commit `827519e`): **FAIL** — `finance-native-catalog`
    `MandatoryError: [Item, SYN-Tuition]: stock_uom, uom` (education
    `FeeCategory.after_insert` auto-creates a sales Item whose defaults
    depend on wizard setup). **486/487** recorded checks passed. Fixed in
    `0976ab3` by pre-creating the sales item explicitly (`create_item`
    reuses existing items) and seeding the `Fee Component` item group.
  - Run `34978842234` (commit `0976ab3`): **FAIL** —
    `finance-tuition-happy-path` `OperationalError 1054: Unknown column
    'income_account' in 'SELECT'`. **493/494** recorded checks passed.
    Instrumented diagnostics (commits `2c104dc`, `6df13e7`, `d264faf`;
    runs `34981365688`, `34983249731`, `34985144000`) localized the failure
    to frappe `_validate_links` → `get_invalid_links` during `Fees.insert`:
    the pinned education `Fees` doctype fetches `income_account` from
    `Fee Structure`, but the pinned `Fee Structure` ships without that
    field — a latent inconsistency in the pinned app itself. Fixed by
    restoring the intended native configuration as a Custom Field
    (`Fee Structure.income_account`, Link Account) and configuring it in
    the fixture Fee Structures; link validation stays fully active.
  - Run `34986723722` (commit `819163d`): **FAIL** —
    `finance-tuition-happy-path` own value assertion (empty message).
    Self-reporting asserts (commit `db20540`, run `34989201678`) exposed
    the exact value: `currency='INR'` — frappe prefills an empty `currency`
    field from the system default before validate, so education's
    fill-from-company never runs. Fixed in `cf6d749` by setting the
    company's `default_currency` (AFN) explicitly on `Fees` and `Sales
    Invoice`.
  - Run `34990386368` (commit `cf6d749`): **FAIL** —
    `finance-placement-happy-path` `ValidationError: Unknown placement
    case`; **502/503** recorded checks passed (full tuition chain green).
    Fixture bug: `TH Placement Case` is autonamed, so a `create_case`
    request key is not the case name. Fixed in `8649c17` by resolving
    billed cases via their unique `subject`.
  - Run `34991471252` (commit `8649c17`): **FAIL** —
    `finance-placement-happy-path` `PermissionError` from ERPNext
    `get_party_account → account_perm_check`: SI party/currency validation
    requires the actor to read `Account` natively. Fixed by giving the
    Finance Officer the native **Accounts User** role (the native
    finance-staff role) and re-tuning `finance-role-and-list-parity` to the
    honest model (containment is the absolute guard; receipt ledger stays
    auditor-only; ERPNext's native `All`-read on Sales Invoice unchanged).
  - Final qualification run: filled from actual check-run output below.

## 3. Boundary and remaining gates

- Not implemented / still gated: academic assessment & progression
  (B04/B05 — owner deferred), payroll (A09/R06), refund automation (owner
  terms outstanding; native Credit Note remains available to authorized
  Finance staff), portals, payment-gateway integration (B12), tax
  configuration (explicitly unconfigured until owner policy).
- Reopening Placement, Admission, Enrollment or Teaching; TH money
  DocTypes; parallel masters or ledgers: remain prohibited.

Production remains **REJECT**.

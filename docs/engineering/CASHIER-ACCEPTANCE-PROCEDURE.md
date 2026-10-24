# Finance and cashier acceptance procedure (real disposable Windows)

Status: **EXECUTABLE, NOT YET EXECUTED.** This procedure is the only accepted
evidence for the physical cashier and book-shop gates. Hosted CI — however
green — is **not** evidence of cashier acceptance and cannot close the gate.
Release decision remains **NO-GO**.

| Item | Value |
| --- | --- |
| Closes | [#35](https://github.com/Frotan2/TOFEL-House-ERP/issues/35) finance/cashier portion once executed and recorded |
| Does not close | [#12](https://github.com/Frotan2/TOFEL-House-ERP/issues/12) Owner Windows lifecycle, [#36](https://github.com/Frotan2/TOFEL-House-ERP/issues/36) verified package, [#40](https://github.com/Frotan2/TOFEL-House-ERP/issues/40) graphical update path |
| Product surfaces | Finance desk `/app/th-finance-desk`; native `Fees`, `Sales Invoice`, `Payment Entry`, `Stock Entry`, `Item Price`, `Bin`, `Sales Invoice` (return), `TH Cashier Day` (read-only) |
| Guarded commands exercised | `toefl_house.finance.issue_tuition_fees`, `…issue_placement_fee`, `…installments.issue_tuition_installment_plan`, `…cashier.reconcile_cashier_day`, correction commands |
| Data rule | **Invented data only.** No real student, staff, payer, price, cash or tax figure. |

This procedure is written to be followed by a non-developer with the packaged
kit: every step names the screen, the actor, the action and the exact
observable that decides pass or fail. No Git, PowerShell, SQL or container
command is required at any step.

---

## 0. What this procedure is deciding

Two separate questions, decided separately:

1. **Does the finance product behave on a real Windows machine the way the
   synthetic native suite says it does?** (book receiving → sale → settlement →
   return/credit note → restock → cash refund; tuition billing; installment
   plans; cashier day close; outstanding visibility; tax configuration state;
   permission refusals).
2. **Is the physical cashier workflow usable by a real cashier with real
   counting?** (drawer count, expected from the ledger, variance note, close,
   history, daily reconciliation, reports).

A "pass" on this procedure means *the tested build on the tested machine
behaved as recorded*. It does not authorize live operation: production
authorization stays **REJECTED** until the Owner gates are separately closed.

---

## 1. Preconditions and safety rules

Do all of this on a **separate, clean, disposable Windows 10/11 64-bit PC**
with Docker Desktop (WSL 2). Follow the packaged
`product/windows/OWNER ACCEPTANCE GUIDE.txt` steps 7–16 first (install, login,
password change, synthetic records, stop/start, reboot persistence, repair).

Stop immediately and do not proceed if any of the following is true:

- The PC has ever held TOEFL House data, or `product\data`, `secrets\db.env`,
  Docker volumes or backups exist on it.
- A report says **BLOCKED**, **NOT VERIFIED**, **HOLD** or **REJECTED**.
- You are about to type a real student, staff or payer name, a real price, a
  real tax rate, or to record real cash.

Never, at any step: restore or overwrite a site; delete volumes or backups;
edit the database or files directly; cancel a submitted document to "retry"
a step; backdate a business date outside the billing policy window; copy
credentials, keys, raw logs or raw backups into the evidence pack.

---

## 2. Record the tested identity before anything else

Write these into the evidence pack (and into the issue comment) **before** step
C1. A result without them is not evidence.

| Field | How to obtain | Recorded value |
| --- | --- | --- |
| Git commit SHA of the tested build | Release note / package `BUILD-INFO` supplied with the kit | |
| Package archive SHA-256 | `Verify Package Image` in the kit launcher, or the value printed by `Install TOEFL House ERP.cmd` | |
| Windows edition and build | `winver` | |
| Docker Desktop version | Docker Desktop → About | |
| Test PC identity | invented label, e.g. `SYN-CASHIER-PC-1` | |
| Date/time and time zone | system clock | |
| Operator | name or initials (never a credential) | |

---

## 3. Users to create (native ERPNext roles only)

Create these as invented accounts on the test site. Do not invent new roles and
do not grant extra permissions to make a step pass.

| Label used below | Native roles | Scope |
| --- | --- | --- |
| **Cashier** | Finance Officer, Accounts User, Finance Manager | Company in scope |
| **Bookkeeper** | Finance Officer, Accounts User | Company in scope |
| **Storekeeper** | Stock User, Stock Manager | Warehouse in scope |
| **Auditor** | Finance Auditor | read-only |
| **Staff no finance** | Accounts User only | Company in scope |
| **Other-branch cashier** | Finance Officer, Accounts User | a *different* Branch User Permission |

The Finance desk only offers an action when the viewer may execute it. If the
Cashier cannot see a guided action, the account is missing a native role —
record that as a failure rather than granting Administrator.

---

## 4. Configuration inputs (invented values only)

Configure in native screens, with invented numbers; these are *test data*, not a
proposal for the Owner's real prices or tax policy.

1. Company `SYN Test Company`, country Afghanistan, currency `AFN`, with a
   postable **Cash** account in the chart and a default receivable account.
2. Selling Price List `SYN Test Prices` in `AFN` (must match the company
   currency; do not invent an exchange rate).
3. `Fee Category` `SYN Tuition`, `Fee Structure` for the test program/year with
   one component at an invented amount (for example 30 000).
4. Placement fee `Item` `SYN Placement Fee` (service, sales item) with a selling
   `Item Price` in `SYN Test Prices` (for example 4 000).
5. `Item Group` `Books`, stock Item `SYN Textbook` (Stock Item + Sales Item),
   selling `Item Price` (for example 300), `Warehouse` `SYN Book Shop`.
6. Billing policy: `Finance → Billing policy` → one version effective **from
   tomorrow**, bounds (for example 30 back / 7 forward), placement timing
   `any`, **Installments left OFF** (leave the box clear, maximum 1, interval 0).
   The version must start strictly after the latest one; a same-day or
   backdated version is refused by design.
7. Native tax: **nothing**. The owner has supplied no Afghan tax policy, so the
   correct state is "No native tax configured" (step C28 checks exactly that).

---

## 5. Procedure

Record every step as `PASS`, `FAIL` or `BLOCKED` with the exact on-screen text
and a redacted screenshot. Steps that assert a refusal must show the refusal
message; a silent success is a **FAIL**.

### A. Book receiving and stock

| # | Actor | Action | Expected observable (pass criterion) |
| --- | --- | --- | --- |
| C1 | Storekeeper | `Stock Entry → Material Receipt`: `SYN Textbook`, qty 12, target `SYN Book Shop`, invented basic rate | Submitted document; `Bin`/`Stock Ledger` quantity becomes 12 |
| C2 | Staff no finance | Try the same receipt | Refused: no Stock permission. Record the message |
| C3 | Cashier | Finance desk → **Book sales and stock** section | Shortcuts appear for items, prices, stock, receive stock, sell, receive payment (only those the roles allow) |
| C4 | Storekeeper | Open `Bin` for the test warehouse | Quantity and valuation match the receipt; no manual correction applied |

### B. Cash sale, settlement and outstanding visibility

| # | Actor | Action | Expected observable |
| --- | --- | --- | --- |
| C5 | Cashier | Native `Sales Invoice`: test customer, `SYN Textbook` × 2, price from the Price List, `Update Stock` **on**, warehouse `SYN Book Shop`, submit | Document submitted; stock 12 → 10; a native receivable/GL entry exists; invoice status **Unpaid**, outstanding = 600 |
| C6 | Cashier | Finance desk → **Outstanding receivables** | The book invoice appears with outstanding 600 and currency `AFN` |
| C7 | Cashier | Native `Payment Entry`: Receive, party = that customer, paid from the test **Cash** account, allocate the invoice, submit | Invoice outstanding becomes 0; invoice status **Paid**; GL cash line posted |
| C8 | Cashier | Finance desk → **Outstanding receivables** | The invoice is gone from the queue (nothing outstanding) |
| C9 | Cashier | Native `Payment Entry`: partial receipt of 200 against a second invented invoice | Invoice stays **Unpaid** with outstanding reduced by exactly 200; desk shows the reduced figure |
| C10 | Cashier | Native `Sales Invoice` mixing `SYN Textbook` with `SYN Placement Fee` | Refused. Record the message (`Sales Invoice requires an authorized finance command or a stock-book invoice`) |
| C11 | Staff no finance | Native `Sales Invoice` for books | Refused (no Finance Officer). Record the message |
| C12 | Cashier | Native `Sales Invoice` for `SYN Textbook` with `Update Stock` **off** | Refused. Stock and ledger unchanged (verify in `Bin` and the invoice list) |

### C. Return, credit note, restock, cash refund, and wrong-return refusals

| # | Actor | Action | Expected observable |
| --- | --- | --- | --- |
| C13 | Cashier | Native return/credit note against the C5 invoice: 1 copy, `Update Stock` on | Submitted; stock 10 → 11; credited total = −300; invoice outstanding/credit balance reflects it |
| C14 | Cashier | Second return against C5 for 2 copies (only 1 remains returnable) | Refused (cumulative restocked quantity would exceed the sale). Record the message |
| C15 | Cashier | Third return against C5 for 1 copy with a value above the remaining credit | Refused (cumulative credited value would exceed the invoice). Record the message |
| C16 | Cashier | Native `Payment Entry`: **Pay** 300 to the customer, allocated to the C13 credit note, paid from the test Cash account, submit | Submitted; credit note outstanding becomes 0; no unallocated amount remains |
| C17 | Cashier | Native `Payment Entry`: **Pay** to the customer **without** a credit note reference | Refused with `A customer refund must settle a submitted credit note of the same customer, for no more than it owes, paid from a Cash or Bank account with no unallocated remainder` |
| C18 | Cashier | Native `Payment Entry`: **Pay** a credit note of a *different* customer, or from a non-cash/bank account | Refused with the same message |
| C19 | Cashier | Native return against a **service/placement** invoice | Refused (only stock-book invoices may be returned here; placement/tuition corrections use the correction framework) |

### D. Tuition billing and installment plans

| # | Actor | Action | Expected observable |
| --- | --- | --- | --- |
| C20 | Cashier | Desk → **Awaiting billing** → **Issue tuition fee** for a confirmed enrollment | Native `Fees` submitted for the configured Fee Structure total (30 000), outstanding = total |
| C21 | Cashier | Repeat the same bill for the same enrollment | Refused (tuition already billed); still exactly one submitted `Fees` for that enrollment |
| C22 | Cashier | Read the **Installments** fact on the Finance desk, then look at the unbilled-enrollment row | Fact says **Not enabled**; the row offers only **Issue tuition fees** and no split action. (The server refusal for an unauthorized split is `Installments are not authorized by the governing billing policy; the Course Owner must enable them on an effective version`; it is proven by the synthetic tests, not typed by the cashier.) |
| C23 | Staff no finance | Open the Finance desk | The desk refuses the audience; no guided billing action is offered. Record the message |
| C24 | — | Optional second round only: record a *new* billing policy version effective tomorrow with Installments on (for example 3 installments, 30-day interval), wait until that date, then issue a plan on a **fresh** unbilled enrollment | The row now offers **Issue installment plan**; submitting it produces exactly the authorized number of submitted `Fees` rows, one per installment, sequence 1..N, total equal to the configured price, due dates spaced by the policy interval, remainder on the last installment |
| C25 | Cashier | Read the installment action's pre-filled count | It equals the policy's **Maximum installments** — the desk never offers a bigger split, and the server re-judges every term |
| C26 | Cashier | Receive the first installment with a native `Payment Entry` | Only that installment's `Fees` outstanding becomes 0; the others remain outstanding; desk shows each separately |

### E. Cashier day close and reconciliation

| # | Actor | Action | Expected observable |
| --- | --- | --- | --- |
| C27 | Cashier | Finance desk → **Cash close** | Drawers in scope, today's **Opening**/**today movement**, state **Open**, expected = native ledger closing balance |
| C28 | Cashier | Desk **Tax configuration** fact | Shows `No native tax configured` for the company (owner supplied no tax policy). No rate, exemption or jurisdiction is displayed or implied |
| C29 | Cashier | Record today's close: counted amount **equal** to the expected figure, submit | `TH Cashier Day` submitted; variance 0.00; state becomes **Closed**; **no** GL/stock entry is posted by the close (compare GL count before/after) |
| C30 | Cashier | Close the same company/day again | Refused with `This business day is already closed for this company; a submitted close is never overwritten` |
| C31 | Cashier (second day or second company) | Record a close with counted ≠ expected and **no** note | Refused with `Explain the … variance for … before closing` |
| C32 | Cashier | Record the same close with the variance and a plain-language note | Submitted; variance stored exactly as counted − expected; desk **Variance recorded** shows it; history shows **Variance** |
| C33 | Cashier | Record a close for a **future** business date | Refused with `A cashier close cannot cover a future business day` |
| C34 | Cashier | Record a close older than the billing policy's window | Refused with `The business day is older than the billing policy's closing window` |
| C35 | Auditor | Finance desk → **Cash close history** | Submitted closes listed newest first with expected, counted, variance; entries cannot be edited |
| C36 | Cashier | Post a small native `Payment Entry` dated **today** after the close | Desk shows **Drift** for that company; nothing is silently restated |
| C37 | Staff no finance | Attempt a close | Refused (role). Record the message |

### F. Permissions, branch and audit integrity

| # | Actor | Action | Expected observable |
| --- | --- | --- | --- |
| C38 | Other-branch cashier | Open the Finance desk and try to bill/receive for the first company's records | Company/branch-scoped records are not visible or are refused; no cross-branch posting is possible |
| C39 | Auditor | Read desks/receipts | Read-only: no guided create/submit action is offered; `Fees`/invoice creation refused |
| C40 | Cashier | Correction: create a correction request for a submitted invoice within the policy window, approve it, post it | Submitted correction record; the original document is untouched (its name, totals and docstatus unchanged); the correction carries its own receipt/audit entry |
| C41 | Cashier | Attempt to post a correction outside the policy window, or without a second author | Refused. Record the message |
| C42 | Cashier | Edit a **submitted** invoice or fee directly in the native form | Refused (submitted documents cannot be amended in place); no silent edit is possible |
| C43 | Auditor | Compare a submitted document's totals before and after C40 | Unchanged; the audit trail shows who/when/what |

### G. Reports and daily use

| # | Actor | Action | Expected observable |
| --- | --- | --- | --- |
| C44 | Cashier | Finance reports → tuition billing register | One row per submitted `Fees` with student, program/year, posting/due date, total, outstanding — matching the documents |
| C45 | Cashier | Finance reports → placement billing register | One row per submitted placement invoice with case, payer, total, outstanding |
| C46 | Cashier | Finance desk → **Today** (payments) | Every `Payment Entry` posted today is listed, with party, amount and currency |
| C47 | Cashier | Filter the desk by company/branch in scope | Only in-scope rows; totals per currency; nothing computed desk-side that contradicts the ledger |

For C24 and C32 you may need to wait for the effective date or to post a second
day's business. Both are legitimate parts of the test; a blocked step is
recorded as `BLOCKED` with the reason, never as `PASS` by inference.

---

## 6. Evidence pack

One folder named `finance-cashier-acceptance-<sha7>-<YYYY-MM-DD>` containing:

1. Step table C1–C47 with `PASS` / `FAIL` / `BLOCKED`, the exact message for
   every expected refusal, and the operator's initials.
2. Redacted screenshots named after the step (`C05-invoice-submitted.png`,
   `C30-duplicate-close-refused.png`, …). Redact customer names, emails,
   addresses, credentials and anything that identifies a real person.
3. The §2 identity table.
4. The GL/stock comparison for C29 (count before/after the close).
5. A short plain-language summary: what a cashier can do unaided, what needed
   help, and every wording that confused the operator.

Never include: passwords, `db.env`, private keys, raw backups, raw logs,
unredacted site configuration, or real personal data.

---

## 7. If a step fails

1. Stop the step; do not "make it pass" by granting Administrator, disabling a
   guard, editing the database, or cancelling a submitted document.
2. Record: step number, actor, screen, exact text, timestamp, screenshot.
3. Continue with the remaining independent steps; note which ones became
   `BLOCKED` because of the failure.
4. Report the failure on [#35](https://github.com/Frotan2/TOFEL-House-ERP/issues/35)
   with the evidence pack name. A failure is a release blocker; it is never
   waived by CI.

---

## 8. Sign-off

| Field | Value |
| --- | --- |
| Tested build SHA | |
| Package SHA-256 | |
| Steps passed / failed / blocked | / / |
| Decision | **PASS** / **FAIL** / **BLOCKED** |
| Operator | |
| Reviewer | |
| Date | |

Signing this procedure records finance/cashier **product** acceptance only.
Release remains **NO-GO** until #12 (Owner Windows lifecycle and recovery),
#36 (verified package) and #40 (fail-closed graphical update) are separately
closed and the Owner explicitly approves.

---

## 9. When to repeat

Repeat the whole procedure on the final release candidate whenever any of
these change after a pass: `apps/toefl_house/toefl_house/finance/**`,
`permissions.py`, `security.py`, `hooks.py`, the desk projections, the native
ERPNNext/Education/HRMS pins, or the packaged Windows kit. Attach the new
evidence to the same issue; do not reuse an earlier pass for a later build.

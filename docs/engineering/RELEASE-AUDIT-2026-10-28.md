# Independent release audit — 28 October 2026

**Disposition: HOLD. Production authorization remains REJECTED.**
**Branch audited:** `arena/1d76efed-tofel-house-erp` (session branch of release PR #87).
**Code head audited:** `98c32110a13f9dc3bbeef17a3629cf944f16618a`.
**Final head of this work:** the docs commit that contains this record; no
application or test source changed after `98c3211`, so every result in §5
applies to that code unchanged.
**Baseline before this audit:** `aeda63fcaeb000d083d4c27c8bc909cbf634709d`.

This record states exactly what was executed and what was not. A green
result here is engineering evidence for the stated scope only; it is not
Owner acceptance and it is not production authorization.

## 1. Method and environment

| Item | Value |
| --- | --- |
| Sandbox | Linux, Python 3.11.2, Node 22.22.3 |
| Static analysis | `ruff 0.16.8`, hash-pinned, `ruff check .` |
| Python suite | pinned PyJWT 2.15.0 / cryptography 50.0.2 venv (the CI crypto set) |
| Node suites | the six desk/portal/realtime harnesses used by the Owned gate |
| Hosted CI | the repository's own workflows, on the exact head above |
| **Not available in this sandbox** | a Windows machine, Docker Desktop, MariaDB/Redis server, a browser on customer hardware |

A local Frappe site **cannot** be installed in this sandbox: there is no
MariaDB/Redis service, no Docker, and package installation is not
permitted. Native execution is therefore evidenced only through the
repository's hosted `Native lifecycle integration` workflow.

Two hosted workflows that the release protocol names —
`Product image` and `Windows customer package` — are **branch-gated by
configuration** (`push.branches: main, fix/**`, and a path filter that this
change does not touch). They cannot be triggered from this session branch,
and workflow dispatch returned `HTTP 403: Resource not accessible by
integration` (the session token has no `actions:write`). Their results are
therefore **absent**, not passing.

Candidate attacks were reproduced by importing the pure guard modules
directly and fuzzing their documented contracts (malformed money, NaN,
bools, non-finite values, negative and oversized quantities, duplicate
references), then fixing and pinning any behaviour that contradicted the
module's own stated invariant.

## 2. Baseline

The tree as received was **green**: `ruff check .` clean, and
`python3 -m unittest discover -s tests -t .` = **2,763 tests OK,
23 skipped**. The skips are Windows-PowerShell-only runtimes
(`test_customer_package_manifest`, `test_windows_backup_discovery`,
`test_windows_package_hashing`, `test_windows_pc_inventory`); none was
converted into a pass.

## 3. Confirmed defects fixed

### D-1 (security/finance) — a hand-typed line discount on a book was accepted

`sale_prices_ok()` refused an unreviewed invoice **header** discount, and
`book_sale_terms_ok()` refused `discount_amount` /
`additional_discount_percentage` on the invoice. Neither looked at the
`Sales Invoice Item` `discount_percentage` / `discount_amount` fields, and
`book_sale_terms_ok()` did not even forward them to the judge. A row could
therefore carry the configured `rate` (so the price check passed) while a
native discount field still reduced what the student was charged.

*Reproduction (before the fix):* `sale_prices_ok([{item_code:"A", rate:100,
qty:1, discount_percentage:10}], {"A":100})` returned **True**.

*Fix:* the row discount is refused unless the row carries a native Pricing
Rule — the same authority rule already applied to a below-list rate and to
the header. `book_sale_terms_ok()` now forwards both fields, so the seam
cannot silently drop them again.

*Verified after the fix:* clean sale **True**, explicit zero discount
fields **True**, `discount_percentage=10` **False**, `discount_amount=25`
**False**, Pricing-Rule sale **True**. Regression test:
`tests/finance/test_book_commerce_guards.py::InvoiceDiscountBoundaryTests::test_a_hand_typed_line_discount_is_refused_like_a_header_discount`.
The native book journeys (sale, mixed-service denial, no-stock denial,
oversell denial, pricing-rule waiver) still pass on hosted native Frappe —
see §5.

### D-2 (finance/desk) — the billing prefill proposed a date the command must refuse

The finance desk computed the first installment due date as *the first of
the month plus grace*, ignoring the contracted day. Under a policy that
sets a different contracted day, the guided action offered a date the
server refuses.

*Fix:* the prefill reads `installment_due_day` and composes the same date
the command will accept; the guidance text names the contracted day.

## 4. Completed workflow — Owner-approved installments

The approved Owner policy (2026-10-28 closure) authorizes **variable
contractual installments** (e.g. 50/50 or 60/40) that must total the full
net tuition, and a due-date choice of **the 25th of the starting Afghan
month or the first of the following month**, plus the configured grace.
The engine could express neither: every split was equal, and the Solar
cadence was pinned to the first of the month.

Both are now **policy values**, never code, on the effective-dated
`TH Billing Policy Version`:

| Field | Meaning | Fail-closed behaviour |
| --- | --- | --- |
| `installment_due_day` | `0` = first of the month (preferred default, and what every older version means); `1–29` = contracted day, e.g. the approved `25` | A day above 29 does not exist in every Solar Hijri month (Hoot has 29), so it is **refused, never clamped**; a due day supplied for a day-spaced cadence is refused |
| `allow_unequal_installments` | authorizes a per-plan share list | Off by default; a share list is refused unless an effective version enables it, and enabling it without installments on the same version is refused |

Money remains exact. Shares are percentages that must total **exactly
100%** in at most four decimals; each component row is split in integer
cents with the remainder on the last installment, and a share too small to
carry one cent is refused rather than dropped. A plan therefore still
totals the configured net tuition to the cent.

The authorized shape is part of the command receipt, of its after-hash and
of its idempotency payload, so a retry (as a JSON string, a comma list or
an array) resolves to one plan instead of a second one.

**Evidence boundary:** this is source plus owned-test evidence. There is
**no** native check that posts a positive unequal-installment plan, and no
browser or Windows acceptance of one. The first-run preset still does not
enable installments. Those remain OPEN — see §6.

## 5. Exact results on the audited head

| Gate | Result | Evidence |
| --- | --- | --- |
| Static analysis | **PASS** | `ruff check .` → `All checks passed!` |
| Owned Python suite | **PASS** | 2,781 tests, 23 Windows-only skips, ~153 s |
| Owned Node suites | **PASS** | `test_product_ingress`, `test_command_pages`, `test_design_system`, `test_role_desks`, `test_portal_views`, `test_realtime_guard` |
| Owned suite (hosted) | **PASS** | run `40669413045`, head `98c3211` |
| Native lifecycle (hosted) | **PASS** | run `40669412938`, head `98c3211` — real Frappe/ERPNext/Education/HRMS on MariaDB, including the book and finance journeys |
| Foundation runtime (hosted) | **FAIL** | run `40669412989`, head `98c3211`, step 7 `Install and validate the pinned foundation` — **not caused by this change**, see §6.1 |
| Product image (hosted) | **NOT RUN** | branch-gated to `main` / `fix/**`; dispatch denied (403) |
| Windows customer package (hosted) | **NOT RUN** | path-gated; this change touches none of those paths |

The suite grew by **18** tests over the 2,763 baseline: exact unequal
shares, remainder and refusal cases, the contracted due-day schedule and
its bounds, policy validation and governing terms, share input
normalization, and the book line-discount regression.

Earlier heads of this work also passed hosted Native (`40668818245`,
`3d5df71`) and hosted Owned (`40668818090`).

## 6. Unresolved blockers — exact evidence

### 6.1 Foundation runtime gate is broken repository-wide (blocking)

The `Install and validate the pinned foundation` step fails on **every**
branch, not only this one. Across the whole repository there are **zero**
successful `Foundation runtime` runs after `2026-10-28T08:31Z`, and every
failure in that window is the same step 7, on unrelated branches
(`fix/tuition-refund-approval-hold-20261028`, `feat/owner-same-level-class-transfers-20261028`, …).
The last success was `f150734f` at `08:28Z`, about 90 minutes before this
session's first commit (`10:01Z`).

Upstream pin drift is **excluded**: every pinned source-file SHA-256 in
`docs/engineering/foundation-version-matrix.json` (frappe, erpnext,
education, hrms, bench) was re-fetched from the pinned commits and
**matches**.

The cause cannot be diagnosed from this sandbox: the workflow's retained
evidence artifact and the job log both redirect to
`productionresultssa*.blob.core.windows.net`, which this environment's
network policy blocks. **Required next action:** retrieve
`foundation-runtime-40669412989-1` (artifact `12807848217`) or the step-7
log from an environment with normal network access, fix the install
regression, then re-run the gate on this head. Until then the release
gate set is incomplete and no release may be declared.

### 6.2 Real Windows and real-device acceptance (blocking, unchanged)

Blockers B-01 … B-06 of the acceptance matrix all require the physical
Owner PC, Docker Desktop/WSL, the staff devices and the backup drive.
Nothing in this audit changes them, and no hosted result can close them.
Specifically still unevidenced: fresh install, start/stop/restart,
persistence, preserving update and rollback, backup-drive schedule, key
custody, isolated recovery, five-role browser workflows on real hardware,
cashier/book stock acceptance and independent download/install.

### 6.3 Two-person production recovery (blocking, unchanged)

The cryptographic two-person restore authorization paths from PR #114/#116
are present and covered by owned tests, but **no executed** two-approver
production recovery has been evidenced, and a signed static document is
not evidence of two independent approvers.

### 6.4 Native acceptance of the new installment terms (open, not blocking release policy)

No native check posts a positive unequal-installment plan or a
25th-of-month schedule, so the new terms are proven in owned tests only.
Adding those journeys requires editing `tools/native/native_checks.py`,
which cannot be validated from this sandbox (CI logs and artifacts are
unreachable, so a failing journey could not be debugged). They are
deliberately **not** added unverified.

### 6.5 Fail-closed behaviour accepted in this change

Both new policy fields default to the previous behaviour, so `bench
migrate` needs no data patch and older rows read as "first of the month,
equal splits". A client replaying a request key created **before** this
upgrade now receives `Idempotency key conflicts with an existing request`
(the payload hash changed). That is a refusal, never a double bill.

## 7. Governance

* No merge into `main`. No branch deletion. No customer or Owner data
  touched; no backup, restore, key or production state was modified.
* No release tag, package or "customer-ready" claim is made by this
  document.
* Production authorization remains **REJECT** until every B-row, the
  Foundation gate in §6.1, an independent security review and explicit
  signed Owner acceptance are complete.

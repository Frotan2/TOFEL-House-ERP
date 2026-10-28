# Independent release audit — 28 October 2026

**Disposition: HOLD. Production authorization remains REJECTED.**
**Branch audited:** `arena/1d76efed-tofel-house-erp` (session branch of release PR #87).
**Audited heads:** `98c32110a13f9dc3bbeef17a3629cf944f16618a` (first two fixes),
`83574722699bb0937032ffb7ba7004c994459718` (plus the restore fix), and
`5f8dca875b743f748158c8746ef724e4c4242b84` (plus the Windows coverage fix).
The final head of this work is the docs commit that contains this record and
changes no application, product or CI source relative to `5f8dca8`.
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

`Product image` is **branch-gated by configuration** (`push.branches: main,
fix/**`). It cannot be triggered from this session branch, and workflow
dispatch returned `HTTP 403: Resource not accessible by integration` (the
session token has no `actions:write`). Its result is **absent**, not passing.

`Windows customer package` is path-gated to the Windows launcher, product
updater and Windows-documentation paths. A genuine defect fix described in
§6.2 touches its own workflow file, so that gate **did** run on a real
`windows-2022` runner (run `40703876516`) and passed.

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

### D-3 (release infrastructure) — the hardened restore cycle refused its own lab site

`product/restore.py` refused the disposable target `recovery.localhost` because
its guard required the site name to contain `"restore"`. That made the
Foundation runtime's hardened encrypted-recovery check fail with exit 2 on
every branch for ~2 hours before this audit. Fixed by recognizing both lab
markers while keeping production and business names refused. Full detail and
evidence in §6.1.

### D-4 (test coverage) — Windows-only package tests were never executed

Nine `skipUnless(os.name == "nt")` contracts guarding the customer package
verifier, preparer and tar selector were skipped by the Linux suite and run by
no workflow. Fixed by executing the module on the `windows-2022` runner and
pinning the coverage. Full detail and evidence in §6.2.

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

## 5. Exact results

| Gate | Result | Evidence |
| --- | --- | --- |
| Static analysis | **PASS** | `ruff check .` → `All checks passed!` |
| Owned Python suite (local) | **PASS** | 2,784 tests, 23 Windows-only skips, ~146 s |
| Owned Node suites (local) | **PASS** | `test_product_ingress`, `test_command_pages`, `test_design_system`, `test_role_desks`, `test_portal_views`, `test_realtime_guard` |
| Owned suite (hosted) | **PASS** | run `40703876518`, head `5f8dca8` |
| Windows customer package (hosted, **real windows-2022**) | **PASS** | run `40703876516`, head `5f8dca8` — all 11 steps, including the newly executed verifier/preparer suite |
| Native lifecycle (hosted, real Frappe/ERPNext/Education/HRMS on MariaDB) | **PASS** | run `40699261699`, head `8357472` |
| Foundation runtime (hosted) | **PASS — gate restored** | run `40699261827`, head `8357472`, **zero failure annotations** |
| Product image (hosted) | **NOT RUN** | branch-gated to `main` / `fix/**`; dispatch denied (403, no `actions:write`) |

**Exact-SHA note.** Owned and Windows are green on `5f8dca8`; Native and
Foundation are green on `8357472`. The only difference between those two
heads is `.github/workflows/windows-customer-package.yml` and
`tests/foundation/test_release_workflow_triggers.py` — no application,
product or native-check code. Native and Foundation do not path-trigger on
those two files and cannot be dispatched from this environment, so they
were not re-run on `5f8dca8`. The canonical four-receipt exact-SHA
requirement is therefore **not** satisfied by this audit alone; it must be
produced by the Product-image pipeline, which cannot run from this branch.

The suite grew by **21** tests over the 2,763 baseline.

## 6. Unresolved blockers — exact evidence

### 6.1 RESOLVED — repository-wide Foundation failure (fixed, gate green)

**Symptom.** `Foundation runtime` failed on every branch. Zero successful runs
after `2026-10-28T08:31Z`; every failure was step 7
`Install and validate the pinned foundation`; the last success was `f150734f`
at `08:28Z`. Job logs and evidence artifacts redirect to
`productionresultssa*.blob.core.windows.net`, which is blocked here, but the
workflow's own check-run **annotations** named the failing sub-check:

```
hardened-restore-with-files: exit 2
last failed check: hardened-restore-with-files
```

The same annotation appeared on unrelated branches
(`36265aa3`, `453b0089`, `7c9e8583`), confirming this was not caused by any
one change.

**Root cause.** Exit 2 from `product/restore.py` is a `RestoreInputError`, and
the failing check is the *second* (hardened, encrypted) restore cycle; the
first cycle passed. `_validate_payload` required a disposable target's site
name to contain `"restore"`, but the hosted runtime names the hardened
recovery site **`recovery.localhost`** (a first-class lab host in the runtime
nginx site map, next to `restore.localhost`). The hardened payload was refused
before any restore ran. Reproduced against the pre-fix adapter:

```
Restore refused: a disposable restore must target a restore site,
never the production site        -> exit 2
```

**Fix.** The guard's invariant is unchanged and still fail-closed: a
disposable restore may never target `PRODUCTION_SITE` and must carry an
unmistakable lab marker. Both hosted lab markers are now recognized
(`DISPOSABLE_SITE_MARKERS = ("restore", "recovery")`). Production names and
ordinary business names (`toeflhouse.localhost`, `acme-academy.localhost`,
`foundation.localhost`, `upstream-tests.localhost`) are still refused.

**Evidence.** The new regression tests fail on the pre-fix file and pass on
the fix. Hosted `Foundation runtime` **run `40699261827` on `8357472` is
success with zero failure annotations** — the first green run since `08:28Z`.
Other branches remain red until this fix is integrated into them.

### 6.2 RESOLVED — Windows-only package tests never executed anywhere (fixed, green)

`tests/foundation/test_customer_package_manifest.py` protects the shipped
customer package: `Verify Package Image.ps1` (archive, manifest, checksum and
loaded-image identity), `Prepare Customer Package.ps1` (dirty checkout /
wrong-head refusal) and the built-in `tar` selector. Nine of its tests are
`skipUnless(os.name == "nt")`.

The Linux owned suite skipped them on every run, and **no workflow executed
the module as a test suite** — the Windows package workflow only imported
`write_image_archive` from it. A broken verifier or preparer could therefore
have shipped unnoticed.

**Fix.** The Windows package workflow now runs
`python -m unittest tests.foundation.test_customer_package_manifest -v` on the
`windows-2022` runner, and a trigger-contract test pins that coverage.

**Evidence.** Hosted `Windows customer package` run `40703876516` on
`5f8dca8` passed all 11 steps, including the new step 9. These are the first
real-Windows executions of those contracts in this repository's CI.

### 6.3 Real Owner hardware acceptance (blocking, unchanged)

Blockers B-01 … B-06 of the acceptance matrix all require the physical
Owner PC, Docker Desktop/WSL, the staff devices and the backup drive.
Nothing in this audit changes them, and no hosted result can close them.
Specifically still unevidenced: fresh install, start/stop/restart,
persistence, preserving update and rollback, backup-drive schedule, key
custody, isolated recovery, five-role browser workflows on real hardware,
cashier/book stock acceptance and independent download/install.

### 6.4 Two-person production recovery (blocking, unchanged)

The cryptographic two-person restore authorization paths from PR #114/#116
are present and covered by owned tests, but **no executed** two-approver
production recovery has been evidenced, and a signed static document is
not evidence of two independent approvers.

### 6.5 Native acceptance of the new installment terms (open, not blocking release policy)

No native check posts a positive unequal-installment plan or a
25th-of-month schedule, so the new terms are proven in owned tests only.
Adding those journeys requires editing `tools/native/native_checks.py`,
which cannot be validated from this sandbox (CI logs and artifacts are
unreachable, so a failing journey could not be debugged). They are
deliberately **not** added unverified.

### 6.6 Fail-closed behaviour accepted in this change

Both new policy fields default to the previous behaviour, so `bench
migrate` needs no data patch and older rows read as "first of the month,
equal splits". A client replaying a request key created **before** this
upgrade now receives `Idempotency key conflicts with an existing request`
(the payload hash changed). That is a refusal, never a double bill.

## 7. Governance

* No merge into `main`. No branch deletion. No customer or Owner data
  touched; no backup, restore, key or production state was modified.
* The two resolved blockers in §6.1/§6.2 are **integration-critical**: other
  branches stay red on the Foundation gate until the `product/restore.py` fix
  reaches them.
* No release tag, package or "customer-ready" claim is made by this
  document.
* Production authorization remains **REJECT** until every B-row, the
  Foundation gate in §6.1, an independent security review and explicit
  signed Owner acceptance are complete.

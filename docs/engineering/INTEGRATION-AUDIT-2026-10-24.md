# Integration audit — 2026-10-24

## Decision

**Consolidated engineering RC only. Production remains REJECT / NO-GO.**

Audited main baseline: `c22b9979542c88a2cd179e179a91829d07a79a3a`.

The native-first architecture is coherent when the lifecycle is read as the sequence in `docs/PRODUCT.md` and bounded by the canonical domain decisions D1–D11 and the separate D8 business-requirements record. The release integration gaps were not solved by adding another business module. They are addressed by a normative cross-domain contract, exclusive shared-file ownership, exact-SHA evidence carried inside the customer package, and a no-code Owner operating/acceptance handbook.

No Owner data, keys, disks, backups, production configuration, or real staff devices were accessed or changed.

## Authority and scope findings

- **D1:** custom Assessment/Progression/grading/credits are deferred. The lifecycle name remains part of the target architecture, but the RC must not claim those stages are implemented or verified.
- **D2:** native HRMS/payroll remains authoritative. Instructor Contract/Teaching Assignment and Additional Salary calculations do not prove Salary Slip, Payroll Entry, statutory correctness, or payment.
- **D3:** the guarded finance correction/refund framework is approved only with configured policy; exact refund, partial-refund and Fees-side terms are not invented.
- **D4:** advanced identity, guardian delegation, and portal policy are deferred. Public/student/guardian portals are not part of the RC.
- **D5:** use the native basic calendar/lifecycle. Repeat, transfer and withdrawal policy remains deferred; the presence of an exit mechanism is not authorization to use it.
- **D6a/D6b:** no tax configuration is inferred, and no online payment gateway is selected or enabled.
- **D7:** raw-fact reports may ship; derived metrics require later named stewards, denominators, disclosure and retention policy.
- **D8:** operational authority, deployment, branch isolation, recovery, capacity, change and rollback requirements remain subject to the recorded evidence blocks and production REJECT.
- **D9/D10/D11:** no separate attendance register is selected; role Pages add no authority; the owned-code MIT decision remains unchanged. The original D01–D13 question crosswalk in `docs/DECISIONS.md` is not silently renumbered.
- `TH Alerting Policy` is the only current notification-policy carrier. It has no approved runtime delivery consumer in this RC.

## Baseline hosted evidence reviewed

All five rows below target the exact baseline SHA, not a short display name or an earlier commit:

| Workflow | Run | Result | Evidence boundary |
|---|---:|---|---|
| Owned suite | [40087474249](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40087474249) | Success | Unit/static/contract evidence |
| Native lifecycle | [40087484777](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40087484777) | Success | Synthetic Frappe/MariaDB/Redis/HTTP, migration, restore/restart and native business checks |
| Foundation runtime | [40087486356](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40087486356) | Success | Hosted Linux runtime, dependency and authenticated browser evidence |
| Product image | [40087474300](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40087474300) | Success | Hosted Linux/amd64 image/product/package evidence |
| Windows customer package | [40087487984](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40087487984) | Success | Hosted Windows packaging/smoke only; **not real Owner Windows acceptance** |

The native final-report contract requires at least 638 executed check receipts and named journey groups. A green job is accepted only with its exact-SHA binding and that fail-closed verifier; it is not treated as proof of deferred journeys or physical hardware.

## Independent review of recently merged work

The following reviews examined the merged diff and its current-main interaction, then reconciled the stated evidence with the exact baseline runs above. No production approval is inferred.

| PR | Merge | Review result |
|---|---:|---|
| [#39](https://github.com/Frotan2/TOFEL-House-ERP/pull/39) | `f83d13f` | `filelock==3.20.3` is applied inside both isolated Frappe virtual-environment install paths, with `--no-deps`; tests prevent a host/global override. Foundation rerun on main is green. Scope is the specific dependency remediation only. |
| [#42](https://github.com/Frotan2/TOFEL-House-ERP/pull/42) | `9ff2b1f` | The setuptools disposition is narrowly bound to the Windows-only advisory path and the shipped Linux/amd64 runtime. Saved-image `os`/`architecture` checks and launcher/allowlist tests protect that premise. It is not a blanket claim that setuptools 80.9.0 is secure or that all findings are closed. |
| [#43](https://github.com/Frotan2/TOFEL-House-ERP/pull/43) | `c638664` | HRMS frontend resolutions move `fast-uri` to 3.1.9, `serialize-javascript` to 7.1.3, and `undici` to 6.29.1; lock/manifest hashes and regression tests match. The evidence addresses seven npm findings, not unrelated future advisories or physical release acceptance. |
| [#44](https://github.com/Frotan2/TOFEL-House-ERP/pull/44) | `6acec26` | Customer ZIP/checksum creation uses `.part` files, refuses preexisting outputs, enforces the size bound before publication, and cleans failed staging. Publication remains a provider CI operation; it does not attest real Windows installation. |
| [#45](https://github.com/Frotan2/TOFEL-House-ERP/pull/45) | `f38f84c` | Native book reconciliation now rejects double-sided/negative GL rows, incorrect directions, split offsets, and opposite stock-value movements even when net balances look correct. This strengthens evidence validation; native GL/stock remain the only ledgers. |
| [#47](https://github.com/Frotan2/TOFEL-House-ERP/pull/47) | `c22b997` | Product-image push filters include `tools/native/native_checks.py` and `tests/finance/**`; the exact-SHA four-gate requirement and non-authorization guard remain. Current main has the resulting Product-image success. |

Security issues #38/#41 are remediated only to the extent shown by these bounded dependency records and current Foundation evidence. They do not close release issues #12/#35/#36/#40.

## Held and rejected integration work

### PR #46 — signed/prebuilt Windows updater

Exact head reviewed: `e8145954cdc081e84cc8aa2356e152c5ceda415d`.

**KEEP UNMERGED.** The PR has hosted green checks but an independent changes-requested review and a special hold. The current findings include caller-editable authorization without durable issuer authentication, replay consumption scoped to a run rather than durable trusted state, and failure to rebind trusted host/image/journal/volume state at apply.

Integration controls applied:

- No merge, cherry-pick, partial updater implementation, or competing update path.
- Hosted Windows jobs are not described as real Windows or Owner-machine acceptance.
- Issue #40 remains open. The Owner Handbook tells users not to install an updater or replace an existing installation.
- An integration-control notice was added at PR comment `#issuecomment-6383876089`; this does not change the formal review state or lift the hold.

### PR #48 — notifications/providers/student and guardian portals

Exact head reviewed: `d7dffdb` (full head is identified by the PR). **CHANGES REQUIRED; excluded from this RC.**

- Owned runs `40091218467` and `40091210170` failed. Focused tests passing did not override the complete Owned suite.
- Local full-suite reproduction found the two product-contract failures `test_no_owned_python_module_contains_assessment_numeric_policy` and `test_no_unguarded_doctype_events`; three additional errors were the local missing-`bs4` environment dependency, not product failures.
- The proposed duplicate notification/configuration plane conflicts with `TH Alerting Policy` and D4. In-memory/regex success must not be called durable persistence or provider delivery.
- Invented financial/stock/privacy defaults, unaudited configuration writes, unsafe portal rendering, self-attested guardian consent, excessive grade exposure, and missing native/exact-revision qualification are release blockers.
- GitHub rejected a formal same-author request-changes review. The substance is recorded as PR comment `#issuecomment-6383878246`; it is **not** represented as a formal independent GitHub review.
- A temporary local cherry-pick used only for review was removed with a hard reset to the clean baseline. Nothing from PR #48 is in the RC.

### PR #49 — Assessment/Progression runtime

Exact head reviewed: `50ca132aa437eb7e491556599e0ea9a12a1f56c5`. **CHANGES REQUIRED; excluded from this RC.**

- Canonical D1 still says `DEFER` and `A06 remains unstarted`. Configurable values and fail-closed behavior do not authorize the new grading, publication, progression and enrollment-gate consumers.
- `progression_state` checks native Student read permission and then bypasses the new result/decision role and branch permissions with `frappe.get_all`; the RPC needs the same denial boundaries as its owned records and negative cross-role/cross-branch tests.
- Native run `40091858486`, Foundation run `40091858494` and the exact-head Owned runs passed, but green checks cannot supersede D1 or substitute for independent review.
- The integration findings are recorded in PR comment `#issuecomment-6384072302`; this is not a formal independent GitHub review decision.

### PR #50 — finance/installments/tax/cashier/refund changes

Exact head reviewed: `6a183b5c400555630526166f33bcc8668aab26d7`. **CHANGES REQUIRED; excluded from this RC.**

- Cashier close incorrectly reuses the billing policy's invoice backdate bound instead of an explicit cashier-policy authority.
- Cashier write and tax-read RPCs do not consistently enforce the actor's native Company/User Permission scope.
- Cashier drift detection watches every company GL account rather than only the reconciled Cash/Bank accounts, so unrelated backdated entries can cause false drift.
- Existing-return reversal paths can count the current submitted return once in prior returns and again as the current return, refusing valid native cancellation as an over-return.
- Exact-head Owned runs passed; Native run `40092775298` was still running when the integration findings were posted. Any result for that head cannot qualify a corrected later head.
- The integration findings are recorded in PR comment `#issuecomment-6384075236`; this is not a formal independent GitHub review decision.

### PR #51 — class operations/scheduling/capacity/mobility

Exact head reviewed: `96330eaec7572094b8826f0045fb98f63ff641fa`. **CHANGES REQUIRED; excluded from this RC.**

- Native run `40092388242` failed during `custom_field.json` import with `KeyError: 'name'`; the four new Course Schedule fixture rows omit the stable fixture name. Offline tests did not establish native installability.
- Canonical D5 expressly defers repeat, transfer and withdrawal policy. The PR's class/program/branch transfer policy and execution consumers require an explicit superseding Owner decision; its narrower PR-description reading of D5 is not authoritative.
- The exact-head Owned runs passed but cannot override the failed Native gate, D5, or the need for independent shared-file review.
- The integration findings are recorded in PR comment `#issuecomment-6384073275`; this is not a formal independent GitHub review decision.

## Integration defects addressed in this candidate

1. **Portable gate traceability:** `verify_ci_gates.py` can now emit a validated receipt only after all four canonical workflows pass on the exact full SHA. The receipt includes run IDs/URLs and retains `production_authorization=REJECT`.
2. **Package evidence completeness:** customer package creation now requires that receipt, validates all four workflows and exact revision before output, embeds `product/release/ci-gates.json`, writes its SHA-256 sidecar, and binds the digest/run references in `release-manifest.json`.
3. **No-code handoff:** the package allowlist and Windows preparer include `OWNER HANDBOOK.txt`; the GUI opens it without a terminal. It distinguishes implemented/deferred/blocked capabilities and preserves all data/recovery/update holds.
4. **Integration governance:** `INTEGRATION-CONTRACTS.md` defines data ownership, API/idempotency/transaction rules, future event compatibility, migrations, role/security boundaries, exact-head qualification, and exclusive shared-file/CI ownership.
5. **Evidence semantics:** `ACCEPTANCE-MATRIX.md` separates IMPLEMENTED, VERIFIED, DEFERRED and BLOCKED rather than hiding incomplete lifecycle stages behind a single “done” label.

These changes require fresh exact-head independent review and hosted qualification. This audit itself is not the independent approval of the new candidate.

## Open release controls

- Issue #12: real Owner Windows lifecycle, backup drive/key custody/recovery, and private staff-device acceptance — **BLOCKED / HOLD**.
- Issue #35: real cashier/book-stock acceptance — **BLOCKED**.
- Issue #36: independently downloadable package plus real installation acceptance — package engineering can be published; real-machine acceptance remains **BLOCKED**.
- Issue #40 / PR #46: safe graphical prebuilt update path — **BLOCKED / HOLD**.
- Real institutional policy values and real payroll/statutory/payable terms not supplied by the Owner — **BLOCKED**, never defaulted.
- Production authorization — **REJECT** until every applicable physical, recovery, staff, financial, configuration and Owner approval gate is actually satisfied.

# Consolidated acceptance matrix

Baseline evidence SHA: `c22b9979542c88a2cd179e179a91829d07a79a3a`

Candidate scope: native-first engineering release candidate

Production authorization: **REJECT / NO-GO**

## How to read the four states

Each assertion is assigned at the narrowest honest granularity.

- **IMPLEMENTED** — a mechanism exists in source or in the candidate change set, but this register does not claim its final exact-revision runtime acceptance.
- **VERIFIED** — the stated behavior has the cited exact-baseline engineering evidence. Verification is limited to the stated synthetic/hosted scope.
- **DEFERRED** — intentionally not enabled in this candidate by an Owner/product decision. It is not a failed test and must not be silently implemented.
- **BLOCKED** — required acceptance cannot honestly be completed yet because physical access, Owner input/approval, a held unsafe change, or another explicit gate is missing.

The final candidate’s exact source SHA and four gate runs are supplied by its embedded `product/release/ci-gates.json` and release evidence. That later evidence can move a candidate mechanism from IMPLEMENTED to VERIFIED without changing any DEFERRED policy or BLOCKED physical/Owner gate. A green hosted run never does so by itself.

## VERIFIED — exact baseline engineering evidence only

| ID | Verified assertion | Exact evidence and limit |
|---|---|---|
| V-01 | Owned architectural, transaction, security and product contracts passed on the baseline. | Owned run [40087474249](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40087474249), SHA `c22b997…`; not native or Owner acceptance. |
| V-02 | Synthetic Applicant/Placement, Admission, Enrollment, Teaching Group/Session/Schedule and Attendance journey groups completed, including allocation, sealed delivery/marking/review/decision, conversion, idempotent enrollment and attendance rollback. | Native run [40087484777](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40087484777), SHA `c22b997…`; final-report required receipt groups. This is not Assessment/Progression evidence. |
| V-03 | Synthetic tuition/placement billing and native invoice/payment flows, guarded finance corrections, policy bounds/timing and integration-through-fees completed. | Native run `40087484777`; native Sales Invoice, Payment Entry and GL authority. No real money, tax configuration or online gateway. |
| V-04 | Synthetic native book sale → stock/GL → payment → return/restock/credit → separate cash refund reconciliation completed; converted-student book-only, mixed-service denial, no-stock-update denial and unauthorized-role denial were exercised. | Native run `40087484777`; row-direction validation strengthened by PR #45. Real cashier/Windows acceptance remains B-04. |
| V-05 | Teacher contract authority and fixed/skill/combined compensation calculation produced the tested native Additional Salary inputs with Employee/component/date/concurrency controls. | Native run `40087484777`, required `teaching-compensation-*` receipts. **Not Salary Slip, Payroll Entry, statutory or payment verification.** |
| V-06 | Role Desk Pages, Page API audiences, CSS delivery, role revocation, guest/CSRF denials, branch isolation and native write containment passed their synthetic checks. | Native run `40087484777`; Foundation run [40087486356](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40087486356). Role visibility alone is not permission. |
| V-07 | Authorized configuration HTTP commands and denial paths passed; missing/invalid policy remains fail-closed. | Native run `40087484777`, `role-desk-configuration-http*` receipts. No Owner policy value was invented. |
| V-08 | Disposable native fresh install/migration, migrate replay, isolated backup/restore with files, wrong-key refusal, restored-site migration, web-service restart and post-restart policy/HTTP checks passed. | Native run `40087484777` and its native artifact metadata. Synthetic isolated infrastructure only; Owner recovery remains B-02. |
| V-09 | Hosted Foundation runtime, pinned dependency audit, authenticated Chromium role/security checks and browser evidence completed on the baseline. | Foundation run `40087486356`, SHA `c22b997…`; accepted residual risks remain visible under the advisory register, not “fixed.” |
| V-10 | Baseline Linux/amd64 product image and image-inclusive customer package passed the hosted product pipeline with source/image binding and REJECT labeling. | Product-image run [40087474300](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40087474300), SHA `c22b997…`; not a real download/install. |
| V-11 | Hosted Windows package/static/smoke checks passed on the baseline. | Windows customer-package run [40087487984](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40087487984), SHA `c22b997…`. **Not real Windows, Docker Desktop, Owner-machine or staff acceptance.** |
| V-12 | The merged filelock/npm remediations and narrow setuptools platform disposition are present and qualified by the current Foundation gate. | PRs #39/#42/#43; Foundation run `40087486356`. Scope is limited to the recorded advisories and shipped platform. |
| V-13 | Native book-ledger evidence rejects forged net-balanced GL/SLE trails, and native/finance changes trigger Product-image qualification. | PRs #45/#47; Owned `40087474249`, Native `40087484777`, Product `40087474300` on the same baseline. |

## IMPLEMENTED — mechanism present; final candidate evidence is separate

| ID | Implemented assertion | Qualification boundary |
|---|---|---|
| I-01 | Cross-domain data ownership, lifecycle, configuration, API, transaction, future event, migration, qualification and merge contracts are documented in `INTEGRATION-CONTRACTS.md`. | Source/integration review required; documentation does not create a runtime capability. |
| I-02 | Exclusive ownership for shared hooks, permissions, fixtures, API/transaction executors, workflows, release tooling, native checks, Windows files and held updater scope is assigned. | Process control enforced by integration review, not a GitHub ACL claim. |
| I-03 | Exact-SHA gate receipts can be written only after all four canonical workflows pass; malformed, wrong-SHA, incomplete and non-REJECT receipts are rejected. | Focused local release tests passed during integration; final hosted Owned/Product evidence must target the candidate SHA. |
| I-04 | Customer packaging requires and embeds `ci-gates.json`, its SHA-256 sidecar and manifest run references alongside the prebuilt image evidence. | Final package/run/digest is recorded by the tagged Product-image pipeline; no physical install claim. |
| I-05 | `OWNER HANDBOOK.txt` is in both customer allowlists and is available from an offline **Owner Handbook** GUI button, with English and Dari safety guidance. | Local installer/package contracts passed; hosted Windows GUI smoke is required on the final SHA, and real usability remains B-01/B-05. |
| I-06 | Native raw-fact reports/registers and role-authorized source records remain available without a custom ledger or warehouse. | Baseline native register checks support the raw scope; every new derived metric remains D-06. |
| I-07 | `TH Assessment Policy` and `TH Alerting Policy` remain configuration/reference carriers with validation. | A carrier is not a runtime grading, progression, notification-delivery, consent or portal consumer. |
| I-08 | Guarded withdrawal/exit mechanisms fail closed unless an effective policy cites a superseding Owner decision. | D5 still defers authorization; do not describe the mechanism as an enabled business policy. |
| I-09 | Release notes, integration audit and this matrix provide a consolidated engineering handoff. | Independent review and the exact-candidate package evidence are still mandatory before a versioned tag is published. |

## DEFERRED — deliberately not enabled in this candidate

| ID | Deferred scope | Authority / consequence |
|---|---|---|
| D-01 | Runtime Assessment, grading, pass bands, credits, Progression/next-level decisions and their portal exposure. | **D1 DEFER.** Native Education remains future authority; historical outcomes stay untouched. |
| D-02 | Advanced identity, guardian delegation, public admission/student/guardian portals and portal policy. | **D4 DEFER ADVANCED POLICY.** PR #48 cannot unlock this scope. |
| D-03 | Repeat, transfer and withdrawal business policy beyond the native basic calendar/lifecycle. | **D5.** A05/A11 remain unstarted; fail-closed mechanism is not policy approval. |
| D-04 | Tax configuration and any invented tax default. | **D6a TAX NOT CONFIGURED YET.** This is an Owner business-configuration gate. |
| D-05 | Online payment gateway integration. | **D6b NO ONLINE PAYMENT GATEWAY AT LAUNCH.** Payments app pinning is not gateway enablement. |
| D-06 | Derived metric/warehouse/reporting layer, including invented risk, ranking, denominators, disclosure or retention semantics. | **D7 DEFER / RAW REPORTS NOW.** Named stewards and policy are required first. |
| D-07 | Notification provider runtime and delivery claims; student/guardian notification consumption. | Current product has only `TH Alerting Policy` as carrier and no approved consumer. Portal-related portions also fall under D-02. |
| D-08 | Public internet hosting, public edge/DNS/TLS topology and uncontrolled exposure. | Current deployment is local/server through authorized Tailscale; future values are not selected. |
| D-09 | A separate custom attendance register/report anchor. | **D9:** guarded API/native facts remain the status quo; no second attendance master. |

## BLOCKED — required acceptance or approval is not yet available

| ID | Blocked assertion | Exact blocker / permitted next action |
|---|---|---|
| B-01 | Real Owner Windows install, start/stop/restart, persistence, repair and nontechnical usability acceptance. | Issue #12; requires the designated real Windows PC and authorized testers. Hosted Windows run `40087487984` does not close it. |
| B-02 | Owner backup-drive schedule, encryption/key custody, isolated Owner recovery and RPO/RTO acceptance. | Issue #12 and D8 preservation/recovery holds. Do not touch Owner keys, disks, backups or production state; use a separately authorized procedure. |
| B-03 | Real staff-device/Tailscale access, permission and responsiveness acceptance. | Issue #12; requires actual staff devices/network and redacted observations. No public port exposure. |
| B-04 | Real cashier/book-stock sale, payment, return/restock and cash-refund acceptance. | Issue #35; requires authorized staff on the designated Windows installation with synthetic practice records before any live decision. |
| B-05 | Independently downloaded versioned customer package installed and used on the real target PC. | Issue #36. Publishing an attested asset is engineering evidence only; actual download, checksum/attestation verification, install and usability remain open. |
| B-06 | Safe graphical prebuilt update path and existing-installation update/recovery acceptance. | Issue #40 and PR #46 special hold. Do not merge or reimplement the updater while authentication/replay/trusted-state findings remain. |
| B-07 | Real payroll posting, statutory/tax/payable correctness and payment approval. | D2 leaves full payroll posting gated; D6a supplies no tax configuration. Requires explicit Owner terms and native HRMS qualification; never invent rates or rules. |
| B-08 | Owner capacity/performance targets and real-device responsiveness acceptance. | Hosted performance numbers are baselines, not Owner targets. D8/operations evidence and real staff workloads are required. |
| B-09 | Production authorization for real students, guardians, staff, payroll, stock or money. | **REJECT / NO-GO.** All applicable B-rows, independent security review and explicit Owner production approval must be resolved; no CI result can override this. |

## Release assertion allowed by this matrix

The permitted conclusion is: **a native-first engineering release candidate with hosted synthetic evidence and clearly bounded deferred/blocked scope**. It is not a completed institution-wide production deployment, and it does not assert the full Assessment/Progression/payroll/portal lifecycle.

# TOEFL House ERP — Release Candidate Dossier

Date: 2026-09-16 · Active branch: `arena/01a0a9f7-tofel-house-erp`
**Production: REJECT.** This dossier consolidates the evidence index
for Release Candidate status of the *implemented* product surface.
RC definition (from the Release Gap Map): every engineer-executable gap
closed with hosted evidence; owner decision packet delivered; upstream
and operational items precisely tracked. Deferred owner policy gates,
upstream items and D8 deployment-scope operations remain outstanding —
production stays REJECT until D8-class gates are independently satisfied.

## 1. Verdict

| Question | Answer | Evidence |
|---|---|---|
| Domains closed with runtime proof? | **YES** (5/5) | §2 domain runs |
| Bypass routes contained (implemented slices)? | **YES** | A13 run + R3 |
| Read-side paths (attachment/export/print) contained? | **YES** | R3, run 35053305607 |
| Role-scoped navigation shipped? | **YES** (2 Workspaces plus 13 D10 Pages) | R1 + T3, current run 35073376790 |
| Factual registers shipped? | **YES** (tuition + placement billing) | R2, run 35049742120 |
| Observability probes green? | **YES** (Error Log roundtrip, scheduler, ping) | R3 |
| Owner decision packet delivered? | **YES** | OWNER-DECISIONS.md (D1–D10) |
| Upstream risk tracked with evidence? | **YES** | UPSTREAM-TRACKING.md |
| Production deployable? | **NO — REJECT** | §5 outstanding classes |

## 2. Hosted evidence index (single synthetic runner, per-push re-execution)

The end-to-end suite is one connected lifecycle proof (placement →
admission → enrollment → teaching → finance → containment → release
gates). Each row is a full green run of the entire suite at that point:

| Milestone | Run | Commit | Checks | Scope added |
|---|---|---|---|---|
| Placement closed | 34932512626 | `4571e6c` | 332/332 | Placement domain |
| Admission closed | 34941341845 | `4da6f1b` | 397/397 | Admission qualification |
| Enrollment closed | 34946981784 | `756614e` | 425/425 | Enrollment lifecycle |
| Teaching closed | 34966681820 | `6ba5663` | 483/483 | Teaching operations |
| Finance closed | 34999987969 | `e73abef` | 517/517 | Finance money chain |
| A13 containment | 35008705885 | `5b5a044` | 523/523 | Bypass-route containment (RPC/REST/edit/cancel/amend seams; report SHA-256 `a66a1b5d…`) |
| R1+R2 release surfaces | 35049742120 | `69a8a95` | 530/530 | Workspaces (visibility model, no-escalation), query-report registers, probe-user restoration |
| R3 read-side + observability | 35053305607 | `46e5040` | 533/533 | Attachment parent-gate, list/export/print denial, Error Log/scheduler/ping probes |
| D2 teaching compensation | 35066349129 | `fa02137` | 536/536 | Contract authority, skill-area assignment facts, native Additional Salary calculation path |
| D3 correction framework | 35069740378 | `ed2d81d` | 539/539 | Fail-closed policy carrier, SoD/window/dual-key denials, native credit-note posting with GL proof |
| **T3 D10(ii) command Pages (recorded hosted proof)** | **35073376790** | **`3587700`** | **542/542** | 13 role-gated Page records/assets; 12 member audiences + 7 non-members; `app_home`; native no-escalation proof (report SHA-256 `54112b38…`) |

All release/D2/D3/T3 check IDs in the current suite (19):
`release-probe-users-restored`, `release-workspaces-configured`,
`release-workspace-role-visibility`,
`release-workspace-no-privilege-escalation`,
`release-command-pages-configured`,
`release-command-page-role-visibility`,
`release-command-pages-no-privilege-escalation`,
`release-registers-configured`, `release-registers-role-access`,
`release-registers-facts-only`, `release-attachment-paths-guarded`,
`release-read-export-print-paths-denied`, `release-observability-probes`,
`teaching-compensation-contract-authority`,
`teaching-assignment-facts`, `teaching-compensation-calculation`,
`finance-correction-fail-closed`, `finance-correction-sod-and-window`,
`finance-correction-posting`.

Diagnostic runs kept for the record (failures that produced decisive
evidence): 35046096047 (invigilator module-gate — D10 root cause),
35047650086 (officer visibility — role-strip root cause), 35048606232
(diag: roles `["All","Guest"]`, education SI Custom DocPerm mechanism),
35052640625 (Error Log field name `method`≠`title` — fixed same day).

## 3. Local verification index (all green at tip)

| Suite | Tests |
|---|---|
| tests/foundation | 77 |
| tests/placement | 148 |
| tests/admission | 6 |
| tests/enrollment | 10 |
| tests/teaching | 17 |
| tests/finance | 15 |
| D10 command-page contract + native-dialog client smoke (Node) | 1 script |

## 4. Shipped configuration surface (no parallel masters)

- 2 Desk workspaces as native module files: **TH Receipts** (module
  Placement; five auditor roles) and **TH Finance** (module Accounts;
  Finance Officer; Registers card). They remain the only Workspaces.
- 13 standard native **Page** exports: the role-filtered **TH Command
  Centre** and 12 one-role command Pages for Placement Author/Publisher/
  Invigilator/Assessor/Reviewer/Releaser, Admission Officer/Reviewer/
  Approver, Enrollment Officer, Teaching Scheduler and Attendance Recorder.
  Page Has-Role authorization (not a Workspace/module gate) is proven in
  run 35073376790; all use one native Dialog client that calls only existing
  guarded endpoints and no document/list/read API. Finance Officer remains
  on its qualified Workspace/report surface by scope, not by a Page authority
  denial.
- 2 role-restricted Query Reports (raw facts only, no derived
  metrics): **TH Tuition Billing Register** (ref Fees), **TH Placement
  Billing Register** (ref TH Placement Operation) + minimal
  report-only permission rows on the TH operations doctype.
- `foundation_security` 0.2.1: Guardian/Student file-permission hooks
  + deny-by-default realtime subscription guard (under runtime
  qualification, not security-approved — see version matrix).
- Integration note: education's `after_install` Custom DocPerms void
  native Sales Invoice permission rows site-wide; all shipped surfaces
  avoid that dependency (anchored on Payment Entry / Fees / TH
  operations doctype).

## 5. Outstanding classes (the only remaining ones)

1. **Owner/deployment gates** — the canonical [D8 production-operations
   decision matrix](d8-production-operations-decision-matrix.json) and
   [D8 operational-input packet](D8-OPERATIONAL-INPUT-PACKET.md) isolate the
   seven minimum owner decisions and their post-selection evidence. The
   provider-neutral contract validator and fail-closed template are already
   executable; no engineering workaround exists that would invent business
   rules or infrastructure. Status: D2, D3 and D10(ii) executed & qualified;
   D6a/D6b/D9 closed; D1/D4/D5/D7 deferred; D8 charter delivered but
   authority, selected topology/controls, and operating evidence remain open
   with D8 **BLOCKED** and production **REJECT**.
2. **Upstream items** — SEC-DEPS-01 remains **UPSTREAM-BLOCKED / REJECT**. The
   latest Foundation runtime `35090904508` at
   `6e7ccb99fc9d5f80fe550aa187787c56d72fea47` ran 116 restricted checks; 114
   passed. Its post-build resolved-stack audit recorded 14 PyPI/OSV finding
   records across four packages and 97 npm advisory findings; both the full-stack
   and Education frontend advisory checks failed. Runtime/remaining-gate Checks
   `104787576338` / `104787579362` have SHA-256
   `08b0453bf78adfc7096dbef3535877feedbb415da31407b5aa77d497b1f86b3f` /
   `3e229cb48c15c8a73d465b82d3f73bbca02f69ba8112b0bddae1e56f2e4cf1aa`.
   The diagnostic failed as intended; it has no OS-package/container-CVE,
   exploitability/reachability, full-SBOM, remediation, or production claim.
   The active-branch Education frontend comparison `35090760597` had 57 baseline
   advisory entries across 21 packages and 23 isolated-candidate entries across
   six; both audits failed and the candidate is not adopted. A maintained
   upstream migration and clean scoped re-runs are required. An evidence review
   of all current newer official v16 inputs rejects a fabricated candidate before
   build: Frappe/ERPNext's dependency inputs are byte-identical, Education has
   no newer release and unchanged branch locks, pdfkit has no listed patch, and
   Bench constrains setuptools below its fixed version. See
   [`dependency-remediation-candidate-assessment-2026-09-16.json`](evidence/phase-2/dependency-remediation-candidate-assessment-2026-09-16.json).
   Also open: SEC-RT-TASK-01 (upstream realtime task room; product-side
   exposure proven nil — UPSTREAM-TRACKING.md §1).
3. **Deployment-scope operations** — independent-host DR, measured restart
   downtime, HA, full-bundle upgrade/rollback, public TLS/proxy qualification,
   capacity, and monitoring operation (D8). The recorded hosted qualification additionally
   proved a disposable product SQL/files backup and separate-site restore in
   `35076449739` at `ebe7767`, with 542/542 native checks. It is explicitly
   not independent-host, production, RPO/RTO, SLA, or availability evidence;
   running production claims "somewhere else" would be evidence theater.
4. **SEC-GUARDIAN-01** — fail-closed Guardian isolation awaits D4;
   narrow explicit-User-Permissions remedy already passes hosted.
5. **Explicit deferrals (do not affect RC):** portals/self-service,
   candidate portal, performance tuning (no measured need), payment
   gateway, analytics platform (prohibited).

## 6. RC readiness statement

Every gap classified as engineer-executable in the Release Gap Map
(§1.2 config-assembly and the non-owner parts of §1.5 security) is
closed with a green hosted run. The product surface shipped is
exactly: five closed domains + A13 containment + release navigation/
registers/read-side containment/observability + T3 role-gated command Pages —
all natively carried, no rewrite, no parallel authorities, no invented policy.
**Release Candidate status of the implemented surface: QUALIFIED. Production:
REJECT** pending D8-class operational gates and deferred owner policy answers.

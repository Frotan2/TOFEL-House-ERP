# TOEFL House ERP — Release Gap Map & Execution Plan

Date: 2026-09-15 · Role: technical & product release leader · Session branch:
`arena/01a0a496-tofel-house-erp`
**Production remains REJECT. Nothing is deployed. No qualified domain is
reopened. No business rule, price, grading policy or legal/tax assumption
is invented anywhere in this plan.**

## 0. Verified current state (evidence, not narrative)

- Five domains CLOSED / QUALIFIED on the hosted synthetic runner:
  Placement `34932512626` (332/332, `4571e6c`), Admission `34941341845`
  (397/397, `4da6f1b`), Enrollment `34946981784` (425/425, `756614e`),
  Teaching `34966681820` (483/483, `6ba5663`), Finance `34999987969`
  (517/517, `e73abef`).
- A13 bypass-route containment demonstrated for the implemented slices:
  run `35008705885` (523/523, `5b5a044`, report SHA-256
  `a66a1b5d5dd2793a1e43bf6b90610a79f3afeda4d789c7d7b562e1fce3176f89`) —
  see [CONTAINMENT-A13.md](../domain/CONTAINMENT-A13.md).
- The 523-check suite is a single connected end-to-end lifecycle proof
  (placement → admission → enrollment → teaching → finance → containment),
  re-executed on every code push. Integration is continuously proven, not
  separately asserted.
- Foundation pins (docs/engineering/foundation-version-matrix.json):
  frappe v16.33.1 `988e54f3c4c2`, erpnext v16.34.2 `4048fb70e14d`,
  education v16.1.0 `93bc7075`, hrms v16.18.1.
- App assembly: 15 TH placement doctypes + `TH Admission Decision` +
  shared receipt/audit ledger; 18 role fixtures; 2 Custom Fields;
  command-only guards pinned on three lifecycle seams for seven
  doctypes; command surfaces for all five domains; owned indexes at
  install. No parallel masters, ledgers or UI stack.
- Phase 2 production ledger (2026-09-14,
  foundation-production-acceptance-ledger.json): REJECT; scoped passes
  for web/worker restart, scheduler, framework patch upgrade, hardened
  restore; open items SEC-DEPS-01, SEC-GUARDIAN-01, SEC-RT-TASK-01 and
  deployment-scope operations.

## 1. Classification of everything that remains

### 1.1 Already fully provided natively (no work; cite in RC dossier)
Student/Applicant identity records, programs/courses/terms catalog,
Program/Course Enrollment lifecycle, Student Group/Course Schedule/
Student Attendance, Fees/Sales Invoice/Payment Entry/GL money chain,
Fee Structure/Category price configuration, Item/Price List/Pricing
Rule, Customer/Company/COA, Desk permission model incl. User
Permissions, Version/audit trail, Email Queue/Notification engine,
backup/restore tooling, scheduler/RQ. Verified by the domain closure
runs, which exercised these authorities directly.

### 1.2 Configuration / assembly only (engineer-executable now)
| ID | Item | Treatment | Status |
|---|---|---|---|
| R1 | Role-scoped staff Desk workspaces (navigation; grants no read — pinned frappe `get_workspaces → is_permitted` Has-Role intersection) | Native `Workspace` module files (`<module>/workspace/…`), 6 workspaces, explicit roles | **In execution this turn**; hosted checks `release-*` |
| R2 | Factual operations registers (tuition billing, placement billing) as role-restricted native Query Reports — raw facts only, no denominators/thresholds (metrics layer is A12, owner stewards). Native access model: Report Has-Role table gates execution (pinned `Report.is_permitted`), ref-doctype `report` permission gates the query surface (pinned `query_report._run`). Attendance-coverage register awaits D9 (no narrow teaching role holds the native `report` flag on Student Attendance; widening options are owner decisions) | Native `Report` module files (`finance/report/…`) + minimal report-only grants on the TH operations doctype | **In execution this turn**; hosted checks `release-registers-*` |
| R3 | Export/attachment/print-path containment proofs for the guarded doctypes (addresses ledger "broad roles/attachment/export/print paths" for implemented slices) + native health/error-observability probes | Hosted negative checks | Next after R2 |

### 1.3 Genuinely requires further implementation (only behind owner decisions)
Academic assessment & progression (B04/B05 → A06); payroll input path
(B08 → A09); refund/credit-note command surface (owner refund terms);
identity/guardian lifecycle (B01/B02 → A02/A03); calendar/repeat/
transfer/withdrawal (B03 → A05/A11); payment gateway (B12). None may be
started without the named decision — building any of them now would
invent business rules.

### 1.4 Business-policy gates blocking release (precise owner asks)
| Gate | Exact decision required | Unblocks |
|---|---|---|
| D1 = B04/B05 | Level vocabulary, sections/components, rubrics/units/cutoffs, course-mapping; academic grading scales & progression | A06 assessment slice |
| D2 = B08 | Employment classification, pay basis, payable units, statutory rules; single native payroll input path | A09 |
| D3 | Refund/cancellation/credit-note terms (who approves, windows, partial refunds) | Finance correction command surface |
| D4 = B01/B02 | Identity/merge/activation policy; guardian delegation & pre-admission proxy rules | A02/A03 + SEC-GUARDIAN-01 closure |
| D5 = B03 | Real intake calendars, same-term repeat requirement, transfer/withdrawal semantics with history preservation | A05/A11 |
| D6 = B07 remainder/B12 | Tax configuration policy; payment-gateway selection (or explicit none) | Tax setup, payments |
| D7 = A12 stewards | Named metric stewards; denominators/disclosure/retention rules | Reporting metrics layer (over R2 registers) |
| D8 | Deployment topology ownership: independent-host DR, capacity/monitoring ownership, TLS/proxy/session policy | Phase 2 production acceptance |
| D9 | Attendance-coverage register access anchor: native `report` flag on Student Attendance belongs to Academics User/Student/Guardian only. Options (owner picks): (a) grant teaching roles native Academics User — widens direct write access beyond the guarded teaching API; (b) Custom DocPerm replication on Student Attendance — invasive, replaces native permission rows wholesale; (c) new TH anchor doctype for teaching facts; (d) no register (current state — teaching facts reachable via guarded APIs only) | TH Attendance Coverage Register (R2 remainder) |

### 1.5 Security gates (non-owner parts vs upstream/owner parts)
- **Closed here:** A13 implemented-slice containment (523/523).
- **SEC-DEPS-01** (frontend dependency advisories): requires coherent
  maintained upstream toolchain migration — upstream scope, tracked; not
  patchable in-repo without inventing a fork.
- **SEC-GUARDIAN-01**: fail-closed Guardian isolation requires D4 policy;
  the narrow explicit-User-Permissions remedy already passes hosted.
- **SEC-RT-TASK-01**: upstream realtime task-room behavior. Product-side
  containment verified by code inspection: owned code enqueues no task/
  progress events with business payloads (R5 records the grep evidence).

### 1.6 Operational gates (deployment-scope; cannot be closed without deploy)
Independent-host disaster recovery, measured restart downtime, HA,
full-bundle upgrade/rollback, public TLS/proxy qualification, capacity
and monitoring ownership (D8). Scoped hosted passes exist
(ledger 2026-09-14); these are correctly deferred until an authorized
deployment target exists — running them "somewhere else" would be
evidence theater.

### 1.7 Explicitly deferred (does not affect RC readiness)
Portals/student self-service (B11 + D4), placement candidate portal,
performance tuning (no measured need — capability-map rule: projections
only after measurement), payment gateway integration, analytics
platform/warehouse (prohibited), any new ERP-adjacent platform.

## 2. Execution plan (ordered by release criticality & dependencies)

| # | Work | Depends on | Parallel-safe? |
|---|---|---|---|
| R1 | Workspaces + hosted proof (this turn) | — | yes (native module files + own check block) |
| R2 | Query-Report registers + hosted proof | R1 merged (shares suite) | yes (disjoint module files) |
| R3 | Export/attachment containment proofs + observability probes | R2 merged | yes (own check block) |
| R4 | Owner decision packet (D1–D8 one-page asks, current state per gate) | — | yes |
| R5 | Upstream tracking evidence: realtime non-exposure grep, dependency advisory triage summary, upgrade-path note | — | yes |
| RC | Release Candidate dossier: consolidated evidence index (runs, SHAs, gates, deferrals) | R1–R5 | — |

Parallelization note: this environment executes sequentially; R2/R3/R5
are marked parallel-safe because they touch disjoint files (separate
fixtures, separate check blocks, docs), with `native_checks.py` as the
only shared file — sequenced through the single hosted suite by design.

**Release Candidate definition used here:** every engineer-executable gap
(1.2/1.5-non-owner) closed with hosted evidence, owner decision packet
delivered (1.4), upstream/ops items precisely tracked (1.5/1.6). Owner
gates and deployment-scope operations then remain as the *only*
outstanding classes — production stays REJECT until D8-class gates are
independently satisfied.

## 3. What will NOT be done (guardrails)
No rewrite, no new ERP, no parallel masters/ledgers/UI stack; no
invented prices, grades, taxes, refund or operational rules; no reopening
of Placement/Admission/Enrollment/Teaching/Finance; no deployment; no
custom platform "to get ready" for deferred domains.

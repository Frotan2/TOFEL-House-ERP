# TOEFL House ERP — Release Gap Map & Execution Plan

Date: 2026-09-16 · Role: technical & product release leader · Active branch:
`arena/01a0aafe-tofel-house-erp`
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
- The current **542-check** suite is a single connected end-to-end lifecycle
  proof (placement → admission → enrollment → teaching → finance → containment
  → release surfaces), re-executed on every code push. Recorded hosted run
  `35073376790` at `3587700110d21816b239779c93c32f4060cd3c63` passed 542/542,
  including the T3 Page records/assets, role visibility and no-escalation
  checks. Integration is continuously proven, not separately asserted.
- Foundation pins (docs/engineering/foundation-version-matrix.json):
  frappe v16.33.1 `988e54f3c4c2`, erpnext v16.34.2 `4048fb70e14d`,
  education v16.1.0 `93bc7075`, hrms v16.18.1.
- App assembly: 15 TH placement doctypes + `TH Admission Decision` +
  shared receipt/audit ledger; 23 role fixtures (18 operational/auditor roles plus five governance roles); 2 Custom Fields;
  command-only guards pinned on three lifecycle seams for seven
  doctypes; command surfaces for all five domains; owned indexes at
  install. No parallel masters, ledgers or UI stack.
- Phase 2 production ledger (2026-09-14,
  foundation-production-acceptance-ledger.json): REJECT; scoped passes
  for web/worker restart, scheduler, framework patch upgrade, hardened
  restore; open items SEC-DEPS-01, SEC-GUARDIAN-01, SEC-RT-TASK-01 and
  deployment-scope operations. Latest active-branch Foundation run `35090904508`
  at `6e7ccb99fc9d5f80fe550aa187787c56d72fea47` ran 116 restricted checks; 114
  passed. Its post-build full-stack resolved-tree audit recorded 14 PyPI/OSV
  findings across four packages and 97 npm advisory findings; the full-stack and
  Education frontend audits failed. Both Phase 2 and security gates remain false;
  this is not OS-package, container-CVE, exploitability/reachability, full-SBOM,
  or production evidence. Runtime/remaining-gate Checks `104787576338` /
  `104787579362` have SHA-256 `08b0453bf78adfc7096dbef3535877feedbb415da31407b5aa77d497b1f86b3f` /
  `3e229cb48c15c8a73d465b82d3f73bbca02f69ba8112b0bddae1e56f2e4cf1aa`.
- D8 engineering now has a hosted disposable product SQL/public-files/private-files
  backup and distinct-site restore rehearsal: run `35076449739` at `ebe7767`
  passed its 542 native checks and restore verifier. This does not reopen a
  qualified domain or satisfy independent-host/production recovery. Exact
  boundary, retained initial failure, and remaining owner inputs:
  [D8 operational-input packet](D8-OPERATIONAL-INPUT-PACKET.md).

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
| R1 | Role-scoped Desk workspaces (navigation; grants no read). Pinned visibility model (frappe `988e54f3c4c2` `desktop.py Workspace.__init__` + `utils/user.py allow_modules`): reachable only when the workspace's module holds a doctype the user can natively read/write/create, then Has-Role scopes it. Shipped surfaces match who actually has native reads under A13 containment: **TH Receipts** (module Placement; five auditor roles — they read the TH operations ledger) and **TH Finance** (module Accounts; Finance Officer via native Accounts User reads; cards include the R2 registers). API-first operational roles (invigilator, author, admission/enrollment/teaching staff) have existing, narrowly scoped TH-DocType reads, further constrained by `policy.can_read`; no native Education/ERPNext CRUD authority is granted. The pinned Workspace/module gate did not produce a compliant staff Workspace, so a separately Page-gated command surface is the selected D10(ii) path and must not widen authority | Native `Workspace` module files, explicit roles | **CLOSED** — run 35049742120 @ 69a8a95, 530/530; checks `release-workspace-*` (+ `release-probe-users-restored`) |
| R2 | Factual operations registers (tuition billing, placement billing) as role-restricted native Query Reports — raw facts only, no denominators/thresholds (metrics layer is A12, owner stewards). Native access model: Report Has-Role table gates execution (pinned `Report.is_permitted`), ref-doctype `report` permission gates the query surface (pinned `query_report._run`). Attendance-coverage register awaits D9 (no narrow teaching role holds the native `report` flag on Student Attendance; widening options are owner decisions) | Native `Report` module files (`finance/report/…`) + minimal report-only grants on the TH operations doctype | **CLOSED (registers shipped)** — run 35049742120 @ 69a8a95, 530/530; checks `release-registers-*`; attendance register remains gated by D9 |
| R3 | Export/attachment/print-path containment proofs for the guarded doctypes (addresses ledger "broad roles/attachment/export/print paths" for implemented slices) + native health/error-observability probes. Proven against pinned core behavior (`988e54f3c4c2`): private attachments on the guarded ledger resolve through the parent-document permission fallback (auditor reads; invigilator/outsider denied on `File.has_permission` and `is_downloadable`); list/export reads via the `db_query` permission layer leak nothing to non-member roles; `download_pdf` denied via `validate_print_permission`. Observability: native Error Log roundtrip (persist→retrieve→cleanup), active Scheduled Job Type registry, health ping | Hosted negative checks | **CLOSED** — run 35053305607 @ 46e5040, 533/533; checks `release-attachment-paths-guarded`, `release-read-export-print-paths-denied`, `release-observability-probes` |

**Integration note (proven by hosted diagnostics, run 35048606232):** the
education app's `after_install` creates Custom DocPerm rows on Sales Invoice
(Student invoice access). Under the pinned `frappe.permissions.get_valid_perms`,
any Custom DocPerm on a doctype replaces its standard permission rows entirely,
so native Accounts-role reads on Sales Invoice are void site-wide after
education installs. R2 register gates avoid the dependency (Fees and the TH
operations doctype carry their own permission rows), and the TH Finance
workspace's module gate is fed by the officer's untouched Payment Entry read.
Any future surface that assumes native Sales Invoice reads must re-check this.

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
| D8 | [Canonical D8 decision matrix](d8-production-operations-decision-matrix.json), [canonical owner-decision record](canonical-owner-decision-record.json), [operational qualification packet](D8-OPERATIONAL-INPUT-PACKET.md), and [final evidence closure report](FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md): selected authority roles, current local/Tailscale boundary, local state, encrypted versioned backup/recovery requirement, preservation priority, audit/health visibility, and change responsibility; numeric capacity/availability remains unresolved | Bounded encrypted backup/restore, preservation, offboarding, audit, alert fail-closed and rollback proofs are reproducible. Selected-operation implementation and independent evidence remain **BLOCKED**; production remains **REJECT** |
| D9 | Attendance-coverage register access anchor: native `report` flag on Student Attendance belongs to Academics User/Student/Guardian only. Options (owner picks): (a) grant teaching roles native Academics User — widens direct write access beyond the guarded teaching API; (b) Custom DocPerm replication on Student Attendance — invasive, replaces native permission rows wholesale; (c) new TH anchor doctype for teaching facts; (d) no register (current state — teaching facts reachable via guarded APIs only) | TH Attendance Coverage Register (R2 remainder) |
| D10 | Desk workspaces for API-first staff roles (invigilator, placement author/publisher, admission, enrollment, teaching): the pinned frappe module-visibility gate makes workspaces reachable only for users with at least one native document read in the workspace's module. Their existing TH-DocType reads remain narrowly contained by `policy.can_read`, and no native Education/ERPNext read should be added. The pinned Workspace/module-gate composition did not yield a compliant staff Workspace; D10(ii) selects a role-gated native Page surface per role with no authority change. **T3 is shipped and qualified** in run `35073376790` @ `3587700` (542/542): Page roles/assets, 12 member audiences + seven non-members, and no native-read escalation. | Staff-facing native Page navigation |

### 1.5 Security gates (non-owner parts vs upstream/owner parts)
- **Closed here:** A13 implemented-slice containment (523/523).
- **SEC-DEPS-01** (resolved dependency advisories): latest hosted runtime
  `35090904508` at `6e7ccb99fc9d5f80fe550aa187787c56d72fea47` reports 14
  PyPI/OSV finding records across four packages plus 97 npm advisory findings;
  both the full-stack and Education frontend advisory checks fail (runtime Check
  `104787576338`, SHA-256
  `08b0453bf78adfc7096dbef3535877feedbb415da31407b5aa77d497b1f86b3f`).
  Remaining-gate Check `104787579362` has SHA-256
  `3e229cb48c15c8a73d465b82d3f73bbca02f69ba8112b0bddae1e56f2e4cf1aa`.
  A coherent maintained upstream stack migration and clean re-run are required;
  patching the pinned upstream bundle in-repo would invent a fork. The audit
  explicitly does not cover OS packages or container image CVEs, and does not
  establish exploitability/reachability, an SBOM, or production acceptance.
  Official newer Frappe/ERPNext v16 releases and Education's official
  `version-16` head retain byte-identical reviewed dependency inputs, while
  current Python findings include a no-fixed-version pdfkit advisory and a
  Bench-constrained setuptools fix. No credible official candidate can pass
  this gate yet; the verified rejection and smallest viable upstream input are
  in [`dependency-remediation-candidate-assessment-2026-09-16.json`](evidence/phase-2/dependency-remediation-candidate-assessment-2026-09-16.json).
- **SEC-GUARDIAN-01**: fail-closed Guardian isolation requires D4 policy;
  the narrow explicit-User-Permissions remedy already passes hosted.
- **SEC-RT-TASK-01**: upstream realtime task-room behavior. Product-side
  containment verified by code inspection: owned code enqueues no task/
  progress events with business payloads (R5 records the grep evidence).

### 1.6 Operational gates (deployment-scope; cannot be closed without deploy)
Independent-host disaster recovery, measured restart downtime, HA,
full-bundle upgrade/rollback, public TLS/proxy qualification, capacity,
branch-isolation runtime proof and deployed monitoring operation (D8). The
final closure harness supplies bounded encrypted SQL/files-shaped preservation,
revocation, audit, alert fail-closed and rollback evidence; it is tracked in
[FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md](FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md)
and is not production evidence. The minimal owner inputs and closure evidence
are in the [D8 operational-input packet](D8-OPERATIONAL-INPUT-PACKET.md). These
remain blocked until an authorized deployment target exists — running them
"somewhere else" would be evidence theater.

### 1.7 Explicitly deferred (does not affect RC readiness)
Portals/student self-service (B11 + D4), placement candidate portal,
performance tuning (no measured need — capability-map rule: projections
only after measurement), payment gateway integration, analytics
platform/warehouse (prohibited), any new ERP-adjacent platform.

## 2. Execution plan (ordered by release criticality & dependencies)

| # | Work | Depends on | Parallel-safe? |
|---|---|---|---|
| R1 | Workspaces + hosted proof | — | done (run 35049742120) |
| R2 | Query-Report registers + hosted proof | R1 merged (shares suite) | done (run 35049742120); D9 remainder owner-gated |
| R3 | Export/attachment containment proofs + observability probes | R2 merged | **DONE** — run 35053305607 @ 46e5040, 533/533 |
| R4 | Owner decision packet (one-page asks, current state per gate) | — | **DONE** — docs/engineering/OWNER-DECISIONS.md (D1–D10, 2026-09-16) |
| R5 | Upstream tracking evidence: realtime non-exposure grep, dependency advisory triage summary, upgrade-path note | — | **DONE** — docs/engineering/UPSTREAM-TRACKING.md (grep: 0 emit sites; advisories triaged; upgrade path + hazards, 2026-09-16) |
| RC | Release Candidate dossier: consolidated evidence index (runs, SHAs, gates, deferrals) | R1–R5 | **DONE** — docs/engineering/RELEASE-CANDIDATE-DOSSIER.md (implemented surface QUALIFIED; production REJECT) |
| T1 | D2 teaching compensation: `TH Instructor Contract` (+skill-term/adjustment children) + `TH Teaching Assignment` doctypes, fixtures, guarded command surface | Owner answer 2026-09-16 | **DONE** — shipped @ 8c92e2f; qualified in run 35066349129 |
| T2 | D2 hosted checks: multi-instructor/skill facts, effective dating, duplicate-payable prevention, idempotent calc, fixed-salary exclusion, audit chain | T1 merged (shares suite) | **DONE** — run 35066349129 @ fa02137, **536/536**; checks `teaching-compensation-contract-authority`, `teaching-assignment-facts`, `teaching-compensation-calculation` |
| T3 | D10 (ii): role-based native Page surfaces for API-first staff roles (no **additional** native reads; containment unchanged) | T5 charter + D10(ii) answer | **DONE** — 13 qualified standard command Pages + shared guarded-command client, current-branch run 35073376790 @ 3587700, **542/542**; the additional Course Owner/General Manager control-centre Page is locally contract-tested and adds no business-document authority; checks `release-command-pages-*` |
| T4 | D3 framework: guarded correction/refund command framework, approval terms configurable (owner terms pending) | T1 done | **DONE** — run 35069740378 @ ed2d81d, **539/539**; checks `finance-correction-*` (fail-closed, SoD/window/dual-key, native credit-note posting). v1 scope: full-amount corrections of TH placement invoices; partials + Fees-side await owner exact terms (refused fail-closed) |
| T5 | D8: code-derived operational ownership charter and canonical owner-authority reconciliation | Owner decision record 2026-09-16 | **DONE** — [OPERATIONAL-OWNERSHIP-CHARTER.md](OPERATIONAL-OWNERSHIP-CHARTER.md) and [canonical-owner-decision-record.json](canonical-owner-decision-record.json); selected engineering implementation/evidence remain blocked, production REJECT |

Owner gate dispositions (2026-09-16): D1 defer · D2 unlocked (T1/T2) ·
D3 framework (T4) · D4 defer · D5 defer · D6a no tax · D6b no gateway ·
D7 defer · D8 owner/business requirements recorded in the canonical record
(charter delivered; implementation and evidence remain D8-blocked; numeric
capacity/availability target not supplied) · D9 CLOSED at (d) · D10 (ii)
**EXECUTED & QUALIFIED** (T3, run 35073376790). Details:
[OWNER-DECISIONS.md](OWNER-DECISIONS.md),
[canonical-owner-decision-record.json](canonical-owner-decision-record.json), and
[TEACHING-COMPENSATION-DESIGN.md](TEACHING-COMPENSATION-DESIGN.md).

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

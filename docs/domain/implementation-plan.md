# Review decisions and implementation plan

> Supporting design detail. The current authoritative gate is
> [ARCHITECTURE-DECISIONS.md](ARCHITECTURE-DECISIONS.md),
> [DOMAIN-CONTRACT.md](DOMAIN-CONTRACT.md) and
> [IMPLEMENTATION-READINESS.md](IMPLEMENTATION-READINESS.md).
> A01–A13 supersede earlier alternatives; old D01–D13 references are legacy questions
> mapped in the decision record. Nothing here authorizes implementation or production.


**Planning only.** The user authorized Phase 3 architecture before implementation. No application/schema/API/UI changes are authorized by this plan; no production acceptance is implied. Estimated order below is dependency-based, not a promised delivery schedule.

**Capability governance:** [ERP-CAPABILITY-MAP.md](ERP-CAPABILITY-MAP.md) is the
authoritative reuse-versus-custom map. Placement is CLOSED. Do not implement
P3.4 enrollment orchestration as a second ledger. A future Admission slice is
`TH Admission Decision` plus native Student Applicant only.

## 1. Approval gates

- **G0 — Architecture review:** approve native ownership, placement-before-program route, proposed owned entities, security and transaction boundaries. Resolve the business decisions relevant to the next slice.
- **G1 — Implementation authorization:** explicitly authorize a bounded slice and its synthetic acceptance tests. The earlier Phase 2 implementation hold is not silently cleared by this design request. Agree which isolated development, if any, may proceed while foundation production blockers remain open.
- **G2 — Domain acceptance:** prove workflows and invariants on exact approved candidate artifacts, including native alternate routes and failures. Design/source checks do not pass this gate.
- **G3 — Production acceptance:** separately close or formally adjudicate all applicable foundation/domain/deployment gates, with accountable operators and approved residual risk. Current Phase 2/production recommendation remains **REJECT**. No pilot with real data is implicitly approved.

## 2. Authoritative decisions and explicit inputs

The former D01–D13 open-question list is now mapped to **A01–A13** in
[ARCHITECTURE-DECISIONS.md](ARCHITECTURE-DECISIONS.md), which includes options,
nine consequence dimensions, native constraints, recommendations and migration risk.
The crosswalk retains every original question and B01–B13 business/input dependency.

- **DECIDED:** A01 pre-program routing, A07 claim boundaries, A08 canonical billing,
  A10 admission separation, A12 metric/source ownership.
- **CONDITIONAL:** A02 identity, A03 guardian access, A04 mixed-role accounts,
  A06 internal scoring policy, A13 backend containment.
- **BLOCKED:** A05 unsupported same-term repeat representation, A09 compensation/input
  path, A11 history-affecting cancellation.

The old D identifiers in the sequencing table below identify legacy planning inputs,
not thirteen still-unnamed architecture decisions. The current readiness labels,
remaining user approvals and source/runtime proof requirements are authoritative in
[IMPLEMENTATION-READINESS.md](IMPLEMENTATION-READINESS.md). No implementation is authorized.

## 3. Recommended vertical slices after authorization

| Slice | Scope / native dependencies | Required acceptance before advancing |
|---|---|---|
| **P3.0 — Contract and schema review** | Confirm exact pinned source contracts; ERD/data dictionary, permission predicates, state diagrams, Custom Fields/indexes and migration/uninstall plan | G0; no redundant identity/enrollment/ledger/HR authority; review current upstream mapper/side effects |
| **P3.1 — Intake and identity** | Native Lead/Applicant links, staff-assisted intake, dedup review and account/guardian provisioning boundary | D01/D02/D10; two-person/family/returning-student fixtures; duplicate conversion and no-premature-invitation tests |
| **P3.2 — Placement governance** | Owned published item/key/rubric/form/policy revisions and content rights | D04/D05; key separation, immutable versions and invalid configuration rejection; no real test content without rights |
| **P3.3 — Attempt delivery and marking** | Case/Sitting/Attempt/Response, assigned ratings, moderation and decision release/review | D02/D04/D05/D11; sealed responses, concurrent submit/autosave, timeouts/retakes, media privacy, scoring boundary fixtures and scope tests |
| **P3.4 — Admission and native registration** | Native applicant plus owned decision/request; Student/Customer activation and native Program Enrollment side effects | D03/D06/D07; no duplicate conversion/course/billing, approval checks on native API/REST/import/job paths, capacity race, safe recovery of partial state |
| **P3.5 — Teaching and academic operations** | Native groups/schedules/attendance/results and reviewed correction/progression decisions | Schedule conflicts, substitution access, partial attendance retries, attendance denominator and transfer/cancel history preservation |
| **P3.6 — Finance controls** | Native pricing/fee route/invoices/payments/refunds/close; optional provider adapter only after decision | Approved chart/tax/currency/aid policy, one charge chain, reconciled refund/advance/partial payment, cross-company denial and retry-safe provider fixtures |
| **P3.7 — Workforce and payroll** | Native Employee/Instructor, HR and work inputs; optional Teaching Work Approval only if needed | D08; no student-attendance/payroll conflation, approved units once, employee privacy, actual native payroll posting and accounting reconciliation |
| **P3.8 — Reporting and end-to-end hardening** | Scoped operational/academic/financial/HR projections and export lifecycle | Source/GL reconciliations, denominator tests, asynchronous revocation, historical correctness, migration/recovery and full role matrix |

Finance design is a prerequisite of registration even though broader finance features appear later. HR identity and instructor assignment precede teaching; payroll implementation follows approved native work semantics. Portal implementation is a separate bounded decision and cannot piggyback on unresolved frontend upgrades. Do not implement all proposed DocTypes at once before proving a vertical slice.

## 4. Mandatory acceptance scenarios

### Canonical lifecycle

- Inquiry without program → prospect placement → released recommendation → genuine Applicant → approved admission → exactly one Student/Customer and native enrollment chain.
- Known-program Applicant → valid released internal placement → conditional offer; missing conditions block enrollment. Returning Student reuses native identity.
- Native Applicant may be Admitted before registration completes; reports and entitlement do not falsely show active enrollment.
- Same-term duplicate/retake conflict, last-seat race, transfer/cancel history, enrollment side effects and failure recovery preserve native authorities.

### Assessment correctness and privacy

- Missing/duplicate criteria, zero denominators, out-of-range scores, rounding/threshold boundaries, incompatible scales and incomplete rubrics reject or route to review.
- Policy/item changes after attempt start cannot alter historical decisions; objective key and human rubric revisions are reproducible.
- Offline/late upload, timeout, autosave race, duplicate submit, assessor reassignment, blind moderation, override, appeal and retake preserve immutable evidence.
- Applicants cannot fetch bank/keys or peer responses through any route; former owners/assessors cannot download private evidence after scope revocation.

### Finance, work and integration

- A08 enrollment-generated tuition invoicing is the single selected producer; competing batch/legacy Fees routes cannot create the same charge; advance/allocation/refund/credit/chargeback and amended invoices reconcile to native ledgers.
- Provider duplicate/out-of-order/forged events, changed request payload and actor revocation cannot post unauthorized effects.
- Canceled/substituted lessons do not automatically become deductions; duplicate approved work does not duplicate payroll inputs; native payroll posting and payment reconcile.
- Jobs and notifications execute after commit with reauthorization, bounded retries and visible reconciliation states. Partial failure is not reported as a completed enrollment/payment.

### Security and release

Use the complete [permission matrix](permission-model.md), including multi-role, cross-site/company/branch and generic API bypass cases. Preserve all existing foundation regressions. Test private files, reports/exports/print/ZIP, permissions after restore, backup key handling, failed migrations, forward-only or restore-based rollback, service restart and full public deployment controls on the relevant candidate. No positive UI-only demo substitutes for negative server-side cases.

## 5. Migration, rollout and review deliverables

Every implementation slice needs a reviewed DocType/field/index manifest; repeatable fixtures/migrations; non-destructive backfill and conflict report; explicit native hook order; data retention/uninstall behavior; synthetic seed data; permission/transition tests; and a scoped rollback/recovery plan. Do not run migrations against real student/payroll data as part of this architecture review.

An architecture approval record should state decisions accepted/deferred, named accountable owners, authorized scope, foundation gate dependencies and acceptance fixtures. Revisit ADR-FND-001 only for a real maintenance/compatibility decision; do not force dependency changes to make a domain slice convenient.

**Completion of this review package means the design is ready for review, not that implementation, domain acceptance, risk acceptance or production deployment is approved.**

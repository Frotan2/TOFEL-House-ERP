# Phase 3 — architecture review and decision lock

## Current placement revision

[PLACEMENT-ASSESSMENT-MODEL.md](PLACEMENT-ASSESSMENT-MODEL.md) is the authoritative revised placement model: managed bank, constrained randomized blueprints, six skills, digital/physical/hybrid delivery and objective/manual marking. It supersedes earlier narrow placement-slice restrictions, not native ownership or the production REJECT. M01–M05 consolidate remaining business policy approvals. Implementation is not authorized. Earlier architecture/source-review metadata records historical snapshots, not a new validation of this revision.


Date: 2026-09-14. **Review record, not architecture sign-off or implementation authorization.** Selected Frappe + ERPNext + Education + HRMS/payroll foundation unchanged. Production acceptance remains **REJECT**.

## Mandatory placement meaning

TOEFL House is a language-training center. Placement is an **internal entrance and English-level assessment**, used before the relevant enrollment to determine current English level and recommend an appropriate TOEFL House course/level.

**Prospect/Applicant → Placement Test → Determine English Level → Recommend Course/Level → Admission → Enrollment.** Placement Result, enrolled Academic Assessment and external Official TOEFL Score are separate concepts. Placement produces neither an official nor mock TOEFL performance score, nor an official CEFR certificate. Baseline CEFR mapping and external-examination features are excluded.

## Authoritative gate artifacts

1. [ARCHITECTURE-DECISIONS.md](ARCHITECTURE-DECISIONS.md) — all 13 decisions, options, nine consequence dimensions, native constraints, status, reversibility and explicit missing inputs. A01–A13 follow the latest required topics; the original D01–D13 questions have a complete crosswalk.
2. [DOMAIN-CONTRACT.md](DOMAIN-CONTRACT.md) — authoritative domain ownership, lifecycle, placement/result separation, permissions, billing/payroll, transactions, retries and reporting rules.
3. [IMPLEMENTATION-READINESS.md](IMPLEMENTATION-READINESS.md) — scoped readiness labels, user approvals, native proof obligations and unchanged Phase 2 production blockers.
4. [architecture-gate-review.json](architecture-gate-review.json) — source/consistency and change-scope audit, expressly not runtime proof.
5. [review-status.json](review-status.json) — machine-readable decision and approval status.

| Status | Decisions |
|---|---|
| **DECIDED** | A01 pre-program placement; A07 official/CEFR exclusions; A08 canonical invoice billing; A10 admission separation; A12 reporting ownership |
| **CONDITIONAL** | A02 identity; A03 guardians; A04 mixed-role accounts; A06 internal level/scoring policy; A13 backend containment |
| **BLOCKED** | A05 unsupported same-term repeat representation; A09 compensation/native input path; A11 history-affecting cancellation |

DECIDED means the architectural boundary is explicit, **not** that the user has approved implementation or that all policy parameters/native behavior are proven. The package is decision-complete in coverage but not unconditionally implementation-ready. No code, DocType/schema, API, UI, dependency, foundation pin or deployment change is included.

## Supporting design detail

These documents are reconciled to, and subordinate to, the authoritative contract:

- [Domain context and invariants](domain-architecture.md)
- [Entity ownership/cardinalities](entity-ownership.md)
- [Detailed workflows](workflows.md)
- [Permission matrix](permission-model.md)
- [Integration/reporting detail](integration-boundaries.md)
- [Sequenced implementation plan](implementation-plan.md)
- [Unchanged pinned source evidence](pinned-source-review.json)

All prior Phase 2 evidence remains unchanged: [foundation architecture](../engineering/foundation-architecture-decision.md), [production acceptance ledger](../engineering/foundation-production-acceptance-ledger.json), [qualification report](../engineering/foundation-final-qualification.md). Any implementation slice requires explicit user authorization and the applicable business/native gates. No pilot, deployment, risk exception or production approval is implied.

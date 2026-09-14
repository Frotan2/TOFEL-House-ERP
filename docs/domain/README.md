# Phase 3 — TOEFL House domain architecture review

**Date:** 2026-09-14
**Status:** DESIGN PROPOSAL FOR REVIEW — no implementation or production authorization
**Foundation:** unchanged Frappe + ERPNext + Education + justified HRMS/payroll, Payments dependency, MariaDB and owned foundation security extension.

The user's Phase 3 instruction authorizes domain architecture and implementation planning. It supersedes the earlier prohibition on TOEFL-specific **design**, not the requirement for review before implementation. Phase 2 remains incomplete; current production acceptance remains **REJECT**. None of the proposed entities, roles, endpoints, fields, workflows or integrations is installed or runtime-qualified.

## Review package

1. [Domain architecture and invariants](domain-architecture.md)
2. [Entity ownership and proposed logical model](entity-ownership.md)
3. [End-to-end workflows and exception paths](workflows.md)
4. [Permission, identity and privacy model](permission-model.md)
5. [Integration, transaction and reporting boundaries](integration-boundaries.md)
6. [Implementation sequence, acceptance tests and review decisions](implementation-plan.md)
7. [Pinned source cross-check](pinned-source-review.json) — immutable source URLs, hashes and native schema facts; **not runtime proof**.
8. [Machine-readable review status](review-status.json)

## Decisions proposed for approval

- Native Lead owns prospect identity; native Student Applicant owns an application once a **real** Program/year is selected. A prospect-linked placement case handles earlier testing without fake enrollment.
- Native Student, Guardian, Program/Course Enrollment, Student Group, Course Schedule, attendance and academic results remain authoritative. No second student or class-enrollment ledger.
- A future `toefl_house` extension would own only placement instruments/attempts/ratings/decisions, institution-specific approvals and necessary coordination records. Names beginning `TH` below are **proposed DocTypes**, not existing tables.
- Separate placement, academic achievement, admission, registration, payment and employment states. One does not silently imply another.
- ERPNext owns receivables, cash, refunds and GL; HRMS owns employment/payroll workflows over the native Employee and accounting authorities. No custom balances or payroll engine.
- Native Desk-first staff workflows; defer any portal implementation/redesign until dependency and security qualification. Applicants, students and guardians receive different server-side scopes.
- No official TOEFL score generation, CEFR equivalence, cutoffs, tuition values, tax formulas, retention periods or legal assumptions are invented. Academic, finance and privacy owners must approve those policies.

## Review gates

Approve the **architecture and policy decisions** before schema/API implementation. Any subsequent development needs explicit implementation authorization and an agreed relationship to the still-open Phase 2 gates. Synthetic experiments, domain acceptance and production release are separate approvals. There is no deployment approval, new risk acceptance or dependency upgrade in this package.

Historical foundation decisions and failed evidence remain intact: [architecture ADR](../engineering/foundation-architecture-decision.md), [production ledger](../engineering/foundation-production-acceptance-ledger.json), [qualification report](../engineering/foundation-final-qualification.md).

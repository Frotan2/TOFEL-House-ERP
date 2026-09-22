# TOEFL House ERP — Decision Register

Date: 2026-09-22 · Location: `docs/operating-system/DECISION-REGISTER.md`
Status: **authoritative consolidated decision index**.

Authority note: this register is an INDEX, not a second decision source.
Canonical owner answers live in
`docs/engineering/canonical-owner-decision-record.json` (projected readably
in `docs/engineering/OWNER-DECISIONS.md`). Architecture rulings live in
`docs/domain/ARCHITECTURE-DECISIONS.md` + `docs/domain/DOMAIN-CONTRACT.md`.
If this index ever disagrees with those sources, those sources win and this
index must be corrected. Never convert an unresolved decision into an
implementation default.

Sections: RESOLVED · OWNER DECISION REQUIRED · ARCHITECTURAL DECISION
REQUIRED · EVIDENCE REQUIRED · DEFERRED. (DEFERRED = explicitly postponed by
the owner; OWNER DECISION REQUIRED = awaiting an answer the owner has not
yet given. A deferred item returns to OWNER DECISION REQUIRED only when the
owner reopens it.)

---

## RESOLVED (binding)

### R-A01 — Pre-program placement routing (A01) — DECIDED
- Domain: placement/identity. Authority: architecture (A01).
- Statement: dual-route — native Lead-linked case when program unknown;
  native Student Applicant when a real Program/year is genuinely intended.
- Status: RESOLVED. Rationale: native Applicant requires real Program/year;
  placement must precede enrollment without fake identities.
- Source: `docs/domain/ARCHITECTURE-DECISIONS.md` (A01), `DOMAIN-CONTRACT.md` §1.
- Consequences: one placement domain, one original native subject per case;
  no placement command creates Student/Enrollment/Assessment.
- Affected consumers: placement, admission, enrollment.

### R-A07 — Official/mock TOEFL + CEFR exclusion (A07) — DECIDED
- Domain: placement claims. Authority: architecture (A07) + owner direction.
- Statement: no official/mock TOEFL output; no CEFR output in the baseline
  contract; external-exam evidence entity removed from the active model.
- Status: RESOLVED. Rationale: center name/labels must not misrepresent
  internal placement as certification. Source: ARCHITECTURE-DECISIONS (A07).
- Consequences: reports/exports/APIs/notifications obey the boundary, not
  just field names. Affected: placement, reporting.

### R-A08 — Single canonical billing flow (A08) — DECIDED
- Domain: finance. Authority: architecture (A08).
- Statement: ERPNext invoice/payment/GL authority; one native
  enrollment-generated tuition invoice chain (route E); no parallel producer.
- Status: RESOLVED. Rationale: one obligation → one active posting chain.
- Source: ARCHITECTURE-DECISIONS (A08); FINANCE-CLOSURE (qualified).
- Consequences: legacy Fees/batch producers prohibited for the same charge;
  producer switches need new decisions + reconciliation, never a runtime flag.
- Affected: finance, enrollment, corrections.

### R-A10 — Admission separation (A10) — DECIDED
- Domain: admission. Authority: architecture (A10).
- Statement: separate owned Admission Decision; placement, offer acceptance,
  Student conversion, enrollment remain distinct; initial entry requires a
  valid released internal placement; no automatic exemptions.
- Status: RESOLVED. Source: ARCHITECTURE-DECISIONS (A10); ADMISSION-CLOSURE.
- Affected: admission, enrollment.

### R-A12 — Source-owned metrics (A12) — DECIDED
- Domain: reporting. Authority: architecture (A12).
- Statement: scoped source queries first; rebuildable projections only after
  measured need; no placement/academic union; stewards own definitions.
- Status: RESOLVED. Source: ARCHITECTURE-DECISIONS (A12).
- Affected: reporting, desks.

### R-D2 — Teaching compensation framework — UNLOCKED / FRAMEWORK SELECTED
- Domain: HR/payroll. Authority: owner (2026-09-16).
- Statement: configurable fixed, skill-based, combined compensation feeding
  the single native HRMS/payroll authority; rates/terms remain configuration.
- Status: RESOLVED (framework). Source: OWNER-DECISIONS (D2); T1/T2 run
  `35066349129` @ `fa02137`, 536/536; TEACHING-COMPENSATION-DESIGN.
- Affected: teaching assignments, payroll inputs.

### R-D3F — Correction framework — FRAMEWORK APPROVED
- Domain: finance corrections. Authority: owner (2026-09-16).
- Statement: guarded fail-closed correction framework; approver role +
  correction window as owner-entered terms; exact terms later.
- Status: RESOLVED (framework). Source: OWNER-DECISIONS (D3); T4 run
  `35069740378` @ `ed2d81d`, 539/539; HEAD `2f8b681` versions.
- Affected: finance corrections.

### R-D6B — No gateway at launch — CLOSED
- Domain: payments. Authority: owner (2026-09-16).
- Statement: no online payment gateway at launch; payments app stays
  pinned-but-unapproved (pin ≠ approval).
- Status: RESOLVED. Source: OWNER-DECISIONS (D6b). Affected: integration, finance.

### R-D9 — No separate attendance register — CLOSED at (d)
- Domain: reporting. Authority: owner (2026-09-16).
- Statement: option (d) — teaching facts via guarded APIs only; no TH
  Attendance Coverage Register.
- Status: RESOLVED. Source: OWNER-DECISIONS (D9). Affected: reporting.

### R-D10 — Role-based Page surfaces — EXECUTED & QUALIFIED
- Domain: navigation. Authority: owner (2026-09-16, option ii).
- Statement: 13 native command Pages, role-filtered, no new native
  Education/ERPNext authority.
- Status: RESOLVED. Source: OWNER-DECISIONS (D10); T3 run `35073376790` @
  `3587700`, 542/542. Affected: desks, Pages, workspaces.

### R-D11 — Product license MIT — DECIDED 2026-09-19
- Domain: legal/distribution. Authority: Course Owner.
- Statement: MIT (matches ratified app metadata); LICENSE + hooks + README
  made consistent in one change; `test_licence_consistency.py` enforces it.
- Status: RESOLVED. Source: OWNER-DECISIONS (D11); LICENSE; hooks.
- Affected: distribution. (Upstream terms still govern upstream apps.)

### R-D12 — Payables one-off + window closing — DECIDED 2026-09-19
- Domain: compensation. Authority: Course Owner.
- Statement: (a) each assignment compensated exactly once, in the first
  payroll period covering it; (a) revision closes the predecessor the day
  before the successor starts. Scope: `teaching.compensation` only.
- Status: RESOLVED. Source: OWNER-DECISIONS (D12).
- Consequences: `already_compensated_prior_period` reporting; no retroactive
  successor rates; history reproducible from superseded contracts.
- Affected: payroll inputs, teaching assignments.

### R-D13 — RPO 24h / RTO 8h targets — DECIDED 2026-09-19
- Domain: continuity. Authority: Course Owner.
- Statement: targets for the local-server + Tailscale scope (not measurements).
- Status: RESOLVED (as targets). Source: OWNER-DECISIONS (D13).
- Affected: backup/recovery (measurement still EVIDENCE REQUIRED).

### R-D14 — Off-site class: owner-controlled hardware — DECIDED 2026-09-19
- Domain: continuity. Authority: Course Owner.
- Statement: destination class + custody selected; no device/hostname/vendor;
  no third-party cloud; not built yet.
- Status: RESOLVED (as class). Source: OWNER-DECISIONS (D14).
- Affected: backup/recovery.

### R-D15 — LOCAL LAUNCH ONLY — DECIDED 2026-09-19
- Domain: deployment scope. Authority: Course Owner.
- Statement: local server + Tailscale is the authorized launch target; the
  internet edge stays unselected and unauthorized. Scope ≠ gate passage.
- Status: RESOLVED. Source: OWNER-DECISIONS (D15); LAUNCH-RUNBOOK.
- Affected: deployment, edge/TLS evidence.

### R-D16 — Build the controlled activation — DECIDED 2026-09-19
- Domain: activation mechanism. Authority: Course Owner.
- Statement: explicit named-site triple; mixed mode refused; qualification
  hostnames never production; `require_synthetic` unchanged on
  qualification paths. Mechanism ≠ GO.
- Status: RESOLVED. Source: OWNER-DECISIONS (D16); `security.py` site_mode.
- Affected: all guarded commands.

### R-ODCP1 — Single discount per charge (Policy A) — DECIDED
- Domain: academic config/discounts. Authority: Course Owner.
- Statement: zero or one discount per charge line; explicit precedence;
  record which rule applied; never stack; centralized catalog.
- Status: RESOLVED. Source: CONFIGURATION-PLANE §6; `TH Discount Rule`;
  `rules.resolve_charge_discount`; `tests/configuration`.
- Affected: fee issuance, finance desk.

### R-ODCP2 — Fees corrections, full-amount only (Option B) — DECIDED
- Domain: finance corrections. Authority: Course Owner.
- Statement: extend the fail-closed framework to issued Fees; full-amount
  only; same owner-entered terms (approver + window); native reversal.
- Status: RESOLVED. Source: CONFIGURATION-PLANE §6; `request/approve/deny_
  fees_correction`; `tests/finance/test_corrections.py`.
- Affected: finance corrections.

### R-ODCP3 — Global-only configuration (Option A) — DECIDED
- Domain: academic config/branch. Authority: Course Owner.
- Statement: single global configuration; no branch-override layer.
- Status: RESOLVED. Source: CONFIGURATION-PLANE §6; `test_contract.py` global
  authority pin. Affected: all config consumers.

### R-R05 — Finance policy framework — RESOLVED 2026-09-15
- Domain: finance. Authority: business owner.
- Statement: TOEFL House / Afghanistan / AFN; enrollment-generated native
  billing; configuration-driven placement fee; native Pricing Rule waivers.
- Status: RESOLVED (framework). Source: FINANCE-POLICY-APPROVAL; FINANCE-CLOSURE.
- Affected: finance, corrections.

### R-R010307 — R01/R02/R03/R07 initial-slice directions — APPROVED
- Domain: placement entry/policy/ownership/privacy. Authority: owner direction.
- Statement: staff-assisted first; assessor-led first (effective = most recent
  reviewed/valid/released); organizational owners (Academic / Admissions &
  Student Records / Administration-Records-Privacy); staff-assisted intake,
  no routine recording. Detailed P01–P05 policy deliverables remain.
- Status: RESOLVED (directions only). Source: BUSINESS-DECISION-RESOLUTION;
  PLACEMENT-IMPLEMENTATION-GATE. Affected: placement (closed slice).

### R-DEPLOY — Local/Tailscale current deployment + branch isolation — SELECTED
- Domain: operations/tenancy. Authority: owner (canonical record).
- Statement: local/server deployment via Tailscale; local DB/files;
  multi-branch architecture + branch operational isolation; role-based access,
  auditability, offboarding with preservation; automated multi-version
  encrypted backup/recovery with preservation priority; configurable policy.
- Status: RESOLVED (requirements). Source: canonical-owner-decision-record.
- Affected: D8 implementation/evidence (still BLOCKED).

### R-SEC-REJECT — Standing REJECT until findings readable — DECIDED 2026-09-19
- Domain: security. Authority: Course Owner (standing decision).
- Statement: keep SEC-DEPS-01 REJECT until advisory findings can actually be
  read. Production stays REJECT.
- Status: RESOLVED. Source: PRODUCTION-READINESS-2026-09-19; gap map.
- Affected: security, release.

---

## OWNER DECISION REQUIRED (awaiting owner answers)

### O-D1 — Assessment & progression values (B04/B05 → A06)
- Domain: academic. Statement: level vocabulary, sections/components,
  rubrics/units/cutoffs, course mapping, grading scales, progression rules.
- Authority: owner (Academic Owner deliverables). Status: OWNER DECISION REQUIRED.
- Rationale: grading policy is academic business policy; no native default
  may stand in. Source: OWNER-DECISIONS (D1: Defer); A06 CONDITIONAL.
- Consequences: A06 slice cannot start; carriers hold structure only.
- Affected: assessment activation, progression, academic desk, reporting.

### O-D3P — Partial-refund terms
- Domain: finance corrections. Statement: partial-refund amount/eligibility
  terms (+ any Fees-side scope beyond full-amount).
- Authority: owner (Finance). Status: OWNER DECISION REQUIRED.
- Source: OWNER-DECISIONS (D3: exact terms later); corrections module refuses
  partials fail-closed. Affected: finance corrections.

### O-D4 — Identity & guardian advanced policy (B01/B02 → A02/A03)
- Domain: identity/guardian. Statement: merge/activation policy; delegation +
  pre-admission proxy rules; consent/evidence/expiry; records/recording rights.
- Authority: owner. Status: OWNER DECISION REQUIRED (advanced; narrow remedy stands).
- Source: OWNER-DECISIONS (D4: Defer advanced); A02/A03 CONDITIONAL.
- Affected: portals (future), SEC-GUARDIAN-01 closure, admission conversion.

### O-D5 — Calendar/repeat/transfer/withdrawal (B03 → A05/A11)
- Domain: enrollment lifecycle. Statement: real intake calendars; same-term
  repeat requirement; transfer/withdrawal semantics with history preservation.
- Authority: owner. Status: OWNER DECISION REQUIRED.
- Source: OWNER-DECISIONS (D5: native basic; advanced later); A05/A11 BLOCKED.
- Affected: enrollment advanced, finance (refund linkage), reporting counts.

### O-D6A — Tax configuration policy (B07 remainder)
- Domain: finance/tax. Statement: company/currency/tax/fiscal/pricing/
  clearance/aid/refund/payer rules; placement charge scope.
- Authority: owner (Finance). Status: OWNER DECISION REQUIRED.
- Source: OWNER-DECISIONS (D6a: not configured yet). Recorded as a decision,
  not an omission. Affected: tax setup, billing consumers.

### O-D7 — Derived-metric stewards & terms (A12)
- Domain: reporting. Statement: named stewards; denominators, disclosure,
  retention rules for any derived metric.
- Authority: owner (management). Status: OWNER DECISION REQUIRED.
- Source: OWNER-DECISIONS (D7: defer; raw now). Affected: metrics layer.

### O-D8N — Numeric capacity/availability objectives
- Domain: operations. Statement: concurrency profile, data scale, workload
  mix, availability objective (numbers only; mechanism is engineering).
- Authority: owner. Status: OWNER DECISION REQUIRED (only unresolved numeric
  business objective; D8-CAPACITY-AVAILABILITY NOT_SELECTED).
- Source: canonical record; gap map. Affected: capacity/availability evidence.

### O-GO — Production authorization + synthetic-only lift
- Domain: production. Statement: (a) GO for the local/Tailscale target after
  gates close; (b) lift-or-keep synthetic-only for that site.
- Authority: Course Owner. Status: OWNER DECISION REQUIRED (and gated on
  evidence — a GO without closed gates is invalid).
- Source: readiness report (blocking issues 1–3); backlog item 1.
- Affected: everything serving real students.

---

## ARCHITECTURAL DECISION REQUIRED (technical design still open)

### T-A05 — Same-term repeat representation
- Domain: enrollment. Statement: native-compatible representation for an
  independent same-key repeat (if D5 requires it), with race-safe capacity +
  preserved histories/charges.
- Status: ARCHITECTURAL DECISION REQUIRED (BLOCKED; A05). Source: A05.
- Affected: enrollment advanced, billing, attendance/grades lineage.

### T-A11 — History-preserving cancellation/transfer path
- Domain: enrollment. Statement: safe representation (prospective change vs
  reviewed cancel/amend) with dependency/finance/recovery plan.
- Status: ARCHITECTURAL DECISION REQUIRED (BLOCKED; A11). Source: A11.
- Affected: enrollment, finance amendments, teaching evidence.

### T-A13U — Unimplemented-domain writer inventory + containment
- Domain: platform. Statement: full native writer/side-effect inventory and
  supported containment for each future domain (B10/B11/B13 inputs).
- Status: ARCHITECTURAL DECISION REQUIRED (CONDITIONAL; A13).
- Source: CONTAINMENT-A13 (implemented slices demonstrated; remainder open).
- Affected: every future domain slice.

### T-A09P — Canonical payroll input path + reconciliation proof
- Domain: HR/payroll. Statement: exactly one native input path per pay basis
  + unique ingestion + amendments + payroll/GL/payment reconciliation.
- Status: ARCHITECTURAL DECISION REQUIRED (CONDITIONAL/FRAMEWORK; A09).
- Source: A09; compensation design. Affected: payroll posting.

---

## EVIDENCE REQUIRED (design may be known; proof is missing)

### V-SEC — SEC-DEPS-01 clean audits on an official candidate
- Domain: security. Statement: full-stack + Education-frontend advisory
  audits passing on a coherent maintained upstream stack, with readable
  detail and full-suite re-qualification.
- Status: EVIDENCE REQUIRED (currently REJECT with verified rejection).
- Source: gap map §1.5; readiness report; candidate assessments.
- Affected: production GO.

### V-BKP — Real-server restore rehearsal + measured RPO/RTO
- Domain: backup/recovery. Statement: rehearsal record (date, digest,
  elapsed, outcome) on the real server; measured objectives vs D13 targets;
  multi-version retention/rotation; session revocation on recovery.
- Status: EVIDENCE REQUIRED. Source: readiness report; gap map §1.6.
- Affected: D8 backup-restore/durability gates.

### V-TLS — TLS/session evidence on the Tailscale URL
- Domain: edge/session. Statement: independent TLS + session-cookie evidence
  on the exact deployment URL at the release SHA.
- Status: EVIDENCE REQUIRED. Source: readiness report (blocking issue 5).
- Affected: D8 topology-edge-session gate.

### V-OBS — Deployed monitoring + audit-trail operation
- Domain: observability. Statement: alert receiver/delivery, retention/
  rotation/archival, deployed fail-closed behavior, incident response.
- Status: EVIDENCE REQUIRED. Source: readiness report; gap map.
- Affected: D8 observability gate.

### V-CUST — Real trust-boundary key custody
- Domain: custody. Statement: KMS/HSM/owner-provisioned secret store with
  authorization, revocation, destruction, audit log, and durability beyond
  artifact retention.
- Status: EVIDENCE REQUIRED (P4 structural model executed; trust boundary not).
- Source: gap map §1.6 (P4). Affected: backup-restore/durability gates.

### V-BRANCH — This-branch hosted qualification
- Domain: release. Statement: hosted suite execution on the working branch
  at its HEAD (branch-boundary pins updated; no relabeling of older runs).
- Status: EVIDENCE REQUIRED (working branch
  `arena/01a0c987-tofel-house-erp` has no cited hosted run at HEAD `e82936f`;
  branch-boundary pins rotated to this branch 2026-09-22 per procedure, still
  awaiting genuine push-triggered execution — see CURRENT-BASELINE.md).
- Source: CURRENT-BASELINE.md; branch-boundary tests. Affected: release.

---

## DEFERRED (explicitly postponed by the owner)

- **F-PORTAL** — Student/guardian portal + candidate portal (future scope;
  R01/B11 + D4). Reopen only via new owner scope decision.
- **F-GATEWAY** — Payment-gateway integration (D6b: none at launch).
- **F-PERF** — Performance tuning/projections (only after measured need).
- **F-ANALYTICS** — Analytics platform/warehouse (prohibited direction).
- **F-OFFLINE** — Offline sync protocol (no genuine requirement recorded).
- **F-I18N** — Persian/Dari desk UI (not shipped; future product scope).
- **F-ADV-GRADE** — Advanced grading surfaces beyond D1 activation (gated on D1).
- **F-INTERNET** — Internet-hosted topology/edge (future phase; D15 excludes
  from launch).

Each deferred item records: authority = owner (or architecture where noted);
status = DEFERRED; source = the cited gate/capability record; consequence =
no implementation, no consumer assumption, no placeholder.

## OPEN OWNER QUESTIONS (principal-owner domain audit, 2026-09-22)

Authority = owner; status = AWAITING ANSWER; source =
`docs/operating-system/DOMAIN-AUDIT-AND-PLAN.md`; consequence = the S4 lifecycle
design slices stay scoped-only until answered. No owner answer is invented or assumed.

- **OD-NEW-01** returning-student identity + continuation rules (new placement per term?).
- **OD-NEW-02** conditional-satisfaction authority + upgrade path.
- **OD-NEW-03** billing date bounds (future/backdate policy).
- **OD-NEW-04** placement-fee timing (upfront vs on-delivery) + one-customer-per-person guidance.
- **OD-NEW-05** roster-change authority (who may add/move students post-creation).
- **OD-NEW-06** attendance-correction authority + window.
- **OD-NEW-07** student exit/unenroll policy + financial consequences.

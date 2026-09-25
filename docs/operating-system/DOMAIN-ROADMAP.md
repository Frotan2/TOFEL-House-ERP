# TOEFL House ERP — Domain Roadmap

Date: 2026-09-22 · Reconciled 2026-09-25 · Location: `docs/operating-system/DOMAIN-ROADMAP.md`
Status: **authoritative evidence-based roadmap**. No dates or business
priorities are manufactured; ordering follows proven dependencies and recorded
decisions only.

Reconciliation note (2026-09-25): rows describing identity/guardian (D4),
reporting/metrics (D7) and numeric capacity objectives record mechanism state
as it stood on 2026-09-22. Since then the four owner-value carriers were
shipped and hosted-validated (metric stewardship `f2663b6`, alerting, capacity
objective `43922f0`, guardian lifecycle `4b9d251`; suite `36151148191`,
placement content qualification `36151148183`): every mechanism is shipped
fail-closed with values NOT CONFIGURED, so the OWNER DECISION REQUIRED
postures below stand unchanged — the pending input is the owner's VALUES, not
the mechanism. Role fixtures are now 24.

Status vocabulary (only these): COMPLETE · READY · IN PROGRESS · BLOCKED ·
OWNER DECISION REQUIRED · EVIDENCE REQUIRED · DEFERRED · REJECTED.
"Qualified" below always means hosted synthetic qualification with a cited
run/commit/checks/hash; anything else is explicitly labeled local-only.

Production posture: **REJECT**; D8 **BLOCKED** (see `CURRENT-BASELINE.md`).

---

## Foundation (pins, guards, assembly, suites)

- **Status**: COMPLETE (as a qualification baseline; not production approval).
- **Dependencies**: none (root).
- **Completed evidence**: pinned stack Frappe v16.33.1 `988e54f3` / ERPNext
  v16.34.2 `4048fb70` / Education v16.1.0 `93bc7075` / HRMS v16.18.1
  (`docs/engineering/foundation-version-matrix.json`); owned app assembly
  (15 placement doctypes + admission decision + receipt/audit ledger + config
  carriers + 24 role fixtures + 2 Custom Fields + command-only guards on three
  lifecycle seams); owned suite gate on push + PR; `ruff` E9+F zero-suppression.
- **Blockers**: none for baseline use; production use blocked by §Security /
  §Backup / §Production rows below.
- **Owner decisions required**: none for the baseline itself.
- **Implementation slices**: none remaining (maintenance only, via upstream
  tracking).
- **Consumer wiring restrictions**: every domain consumes these pins; no
  domain may force dependency overrides or fork upstream to pass a gate.
- **Acceptance evidence**: hosted runtime/install/build probes across the
  closure runs listed below; `tests/foundation` + `test_app_assembly` +
  `test_branch_boundary` (branch pins must match the working branch).

## Placement (internal entrance assessment)

- **Status**: COMPLETE (CLOSED / QUALIFIED — bounded synthetic isolated build).
- **Dependencies**: Foundation.
- **Completed evidence**: increments 1–7 + closure slice; qualifying run
  `34932512626` @ `4571e6c`, 332/332 native checks, 86/86 runner steps,
  production REJECT (`docs/domain/PLACEMENT-CLOSURE.md`). Assessment model:
  governed bank, blueprint randomized forms, six-skill auto/manual assessment,
  digital/physical/hybrid delivery (`PLACEMENT-ASSESSMENT-MODEL.md`).
- **Blockers**: none within the closed slice.
- **Owner decisions required**: none for the closed slice (M01–M05 business
  policies remain future activation prerequisites, not reopeners).
- **Implementation slices**: none — do not start another increment.
- **Consumer wiring restrictions**: Admission reads released decisions
  read-only; Finance reads cases read-only for placement billing. No writer
  outside the closed command surface.
- **Acceptance evidence**: cited run + report hash in the closure doc.

## Admission (thin decision over native Applicant/Student)

- **Status**: COMPLETE (CLOSED / QUALIFIED).
- **Dependencies**: Foundation, Placement (released decisions as read-only input).
- **Completed evidence**: `TH Admission Decision` lifecycle; run `34941341845`
  @ `4da6f1b`, 397/397 (`docs/domain/ADMISSION-CLOSURE.md`).
- **Blockers**: none within the closed slice.
- **Owner decisions required**: advanced admission conditions/validity (B06)
  for any future extension — not for the closed slice.
- **Implementation slices**: none remaining in the closed slice.
- **Consumer wiring restrictions**: approval/conversion must not create
  Program Enrollment, invoices, payments, attendance, or payroll.
- **Acceptance evidence**: cited run in the closure doc.

## Enrollment & Lifecycle — native basic (thin command over Program Enrollment)

- **Status**: COMPLETE for native basic lifecycle (CLOSED / QUALIFIED);
  advanced repeat/transfer/withdrawal semantics are BLOCKED (see D5 row).
- **Dependencies**: Foundation, Admission (eligibility inputs).
- **Completed evidence**: `enroll_in_program`; run `34946981784` @ `756614e`,
  425/425 (`docs/domain/ENROLLMENT-CLOSURE.md`).
- **Blockers**: A05/A11 advanced semantics blocked (see D5).
- **Owner decisions required**: D5 (B03) for anything beyond native basic.
- **Implementation slices**: none for native basic; advanced slices are not
  authorized until D5 answers + native-path proof exist.
- **Consumer wiring restrictions**: completion requires submitted native
  enrollment + expected Course Enrollments + roster/entitlement + finance
  predicates — never a returned Student ID alone.
- **Acceptance evidence**: cited run in the closure doc.

## Teaching Operations — timetable/teacher ops (Scheduling & Attendance)

- **Status**: COMPLETE (CLOSED / QUALIFIED — thin slice, no new DocType).
- **Dependencies**: Foundation, Enrollment (submitted enrollments feed rosters).
- **Completed evidence**: roster/session/attendance commands; run `34966681820`
  @ `6ba5663`, 483/483 (`docs/domain/TEACHING-CLOSURE.md`).
- **Blockers**: none within the closed slice.
- **Owner decisions required**: none for the closed slice (payable-work rules
  belong to HR/payroll, not to scheduling/attendance).
- **Implementation slices**: none remaining in the closed slice.
- **Consumer wiring restrictions**: Classroom attendance never feeds payroll;
  schedule facts never auto-create payables.
- **Acceptance evidence**: cited run in the closure doc.

## Finance — tuition & placement billing (thin slice over native money)

- **Status**: COMPLETE (CLOSED / QUALIFIED — bounded thin slice).
- **Dependencies**: Foundation, Enrollment (submitted enrollments), Placement
  (read-only case reference for placement billing), R05/B07 framework.
- **Completed evidence**: `issue_tuition_fees` (native Fees) +
  `issue_placement_fee` (native Sales Invoice, configuration-driven
  chargeability); run `34999987969` @ `e73abef`, 517/517, report SHA-256
  `663aad8c…b06` (`docs/domain/FINANCE-CLOSURE.md`).
- **Blockers**: correction exact terms (D3 remainder), tax (D6a) for any
  tax-bearing future.
- **Owner decisions required**: D3 exact terms (partials); D6a tax policy
  before any tax configuration.
- **Implementation slices**: none for the closed slice; corrections/tax are
  separate rows below.
- **Consumer wiring restrictions**: one obligation → one active native posting
  chain; no competing producer; legacy Fees never duplicates enrollment-
  generated invoices.
- **Acceptance evidence**: cited run + hash in the closure doc.

## A13 containment (implemented slices)

- **Status**: COMPLETE for implemented slices (demonstrated); CONDITIONAL for
  unimplemented domains.
- **Dependencies**: all implemented command surfaces.
- **Completed evidence**: guards pinned on `validate`/`before_cancel`/
  `before_update_after_submit` for the seven guarded doctypes; hosted negative
  proofs across cancel/post-submit-edit/RPC/REST/Desk-cancel/copy-amend; run
  `35008705885` @ `5b5a044`, 523/523 (`docs/domain/CONTAINMENT-A13.md`).
- **Blockers**: full writer/side-effect inventory for unimplemented domains
  (B10/B11/B13) remains open.
- **Owner decisions required**: none for the demonstrated coverage.
- **Implementation slices**: extend containment with each new domain slice; no
  standalone containment project.
- **Consumer wiring restrictions**: every new writer must satisfy A13 (server
  invariants + supported containment + negative tests) before acceptance.
- **Acceptance evidence**: cited run in the containment doc.

## D1 — Academic configuration (control plane carriers)

- **Status**: COMPLETE (carriers + commands + desks + local/hosted tests).
- **Dependencies**: Foundation; native Program/Fee/Academic-Year masters.
- **Completed evidence**: slices 1–5 per `docs/product/CONFIGURATION-PLANE.md`
  (programs, levels-as-native-Programs, durations, fee orchestration,
  discounts under OD-CP-1 A, Fees corrections under OD-CP-2 B, global-only
  under OD-CP-3 A, reporting register); controller-registration fix @
  `c2b779b`, hosted run `35317973709` (75 checks + 600+ scenarios, 0 errors);
  `tests/configuration` (contract + lifecycle + foundation + discount math).
- **Blockers**: none for carriers.
- **Owner decisions required**: D1 **values** (level vocabulary, rubrics,
  cutoffs, grading, progression — B04/B05) remain OWNER DECISION REQUIRED;
  carriers hold structure only, zero business values.
- **Implementation slices**: (a) D1-value activation slice — authorized only
  after D1 answers (native per-group Assessment Plans scheduled from owned
  policy; no invented thresholds). No other slice.
- **Consumer wiring restrictions**: enrollment/billing/classes/assessments
  consume carriers via native keys only; no consumer invents a threshold the
  carrier does not hold.
- **Acceptance evidence**: plane doc §8 suites + cited hosted run; D1-value
  activation needs its own hosted qualification when authorized.

## D1-values — assessment & progression policy content (B04/B05 → A06)

- **Status**: OWNER DECISION REQUIRED (deferred by design; zero implementation started).
- **Dependencies**: D1 carriers (COMPLETE).
- **Completed evidence**: none (by design).
- **Blockers**: owner must supply level vocabulary, sections/components,
  rubrics/units/cutoffs, course mapping, grading scales, progression rules.
- **Owner decisions required**: D1 (all values).
- **Implementation slices**: gated entirely on D1 answers; one activation
  slice when they arrive.
- **Consumer wiring restrictions**: no consumer may read assessment meaning
  until the carrier holds owner-supplied values.
- **Acceptance evidence**: EVIDENCE REQUIRED after authorization (native
  grading/progression behavior + hosted qualification).

## D3 — Finance correction policy (framework + effective-dated versions)

- **Status**: COMPLETE for framework + versioning (HEAD `2f8b681`); exact
  partial-refund terms remain OWNER DECISION REQUIRED.
- **Dependencies**: Finance closed slice (native Fees/Invoice authorities).
- **Completed evidence**: T4 framework run `35069740378` @ `ed2d81d`, 539/539
  (`finance-correction-*`); HEAD append-only versions + request pinning +
  latest-only status + snapshot validation + singleton hash-chained stream +
  Finance-desk surface; `tests/finance/test_corrections.py` (full-amount rule,
  window validation, dual-key, native reversal, pinning, re-validation under
  lock); hosted TOCTOU proofs (`1fada99`, `991f097`); invoice re-validation
  (`7e1f346`); concurrent first-writer billing (`3eaed7d`).
- **Blockers**: partial-refund amount/eligibility terms (owner).
- **Owner decisions required**: D3 remainder (partials; any further Fees-side
  scope beyond OD-CP-2 B full-amount).
- **Implementation slices**: partial-refund slice — authorized only after
  exact owner terms. Nothing else.
- **Consumer wiring restrictions**: corrections post only through native
  credit-note / Fees-cancellation artifacts; request rows carry facts + trail,
  never a second posting.
- **Acceptance evidence**: cited runs for framework; partials need new hosted
  qualification when authorized.

## D6a — Tax readiness

- **Status**: OWNER DECISION REQUIRED (recorded decision: tax not configured yet).
- **Dependencies**: Finance closed slice; D6a owner policy.
- **Completed evidence**: explicit non-configuration (no tax records anywhere;
  native tax behavior untouched) — recorded as a decision, not an omission.
- **Blockers**: owner tax configuration policy (company/currency/tax/fiscal
  rules per B07 remainder).
- **Owner decisions required**: D6a (all tax policy).
- **Implementation slices**: tax-setup slice — authorized only after D6a
  answers; native tax configuration, no owned tax engine.
- **Consumer wiring restrictions**: no consumer may assume tax treatment;
  pricing/waiver/tax behavior stays native and unconfigured until D6a.
- **Acceptance evidence**: EVIDENCE REQUIRED after authorization.

## D4 — Student & Guardian (identity lifecycle, B01/B02 → A02/A03)

- **Status**: DEFERRED (advanced policy). Narrow explicit-User-Permissions
  guardian remedy stands (hosted-proven); full fail-closed isolation
  (SEC-GUARDIAN-01) awaits D4.
- **Dependencies**: Foundation guards; D4 owner policy.
- **Completed evidence**: narrow remedy hosted proof (see release gap map);
  portals explicitly future scope.
- **Blockers**: identity merge/activation policy; guardian delegation +
  pre-admission proxy rules (B01/B02).
- **Owner decisions required**: D4 (all advanced policy).
- **Implementation slices**: none authorized until D4 answers.
- **Consumer wiring restrictions**: no pre-admission proxy access; no fake
  Student for login; Applicant guardian rows never satisfy Student-parent
  lookup; contact/payer ≠ permission.
- **Acceptance evidence**: EVIDENCE REQUIRED after authorization (isolation +
  revocation + private-evidence tests).

## D5 — Enrollment & Lifecycle advanced (calendar/repeat/transfer/withdrawal, B03 → A05/A11)

- **Status**: BLOCKED for same-term repeat/transfer representation; native
  basic lifecycle COMPLETE (see above).
- **Dependencies**: Enrollment native basic; D5 owner policy; native-path proof.
- **Completed evidence**: native basic (closed slice). No advanced semantics.
- **Blockers**: real intake calendars; same-term-repeat requirement; transfer/
  withdrawal semantics with history preservation; native-compatible
  representation + race-safe capacity + preserved histories/charges; safe
  history-preserving cancellation path (A11 — native cancel deletes Course
  Enrollments).
- **Owner decisions required**: D5 (B03 + withdrawal/transfer + history rules).
- **Implementation slices**: none authorized until D5 answers + proof.
- **Consumer wiring restrictions**: no per-student fake terms; no duplicate
  Course/Program masters; no destructive cancellation as a uniqueness
  workaround; placement retakes stay independent (new Attempt + Decision
  revisions, history preserved).
- **Acceptance evidence**: EVIDENCE REQUIRED after authorization.

## D7 — Reporting & Metrics (A12; raw facts vs derived metrics)

- **Status**: COMPLETE for raw facts (R2 registers + canonical definitions);
  derived metrics DEFERRED (OWNER DECISION REQUIRED for stewards/terms).
- **Dependencies**: source domains (all closed slices); D7 owner policy for
  anything derived.
- **Completed evidence**: R2 tuition/placement registers (Query Reports, raw
  facts only), run `35049742120` @ `69a8a95`, 530/530
  (`release-registers-*`); `toefl_house.reporting` definition register;
  R3 export/attachment/print containment + observability probes, run
  `35053305607` @ `46e5040`, 533/533. Attendance-coverage register: D9 CLOSED
  at (d) — no separate register; facts via guarded APIs only.
- **Blockers**: named metric stewards; denominators, disclosure, retention
  rules for any derived metric.
- **Owner decisions required**: D7 (all derived-metric policy).
- **Implementation slices**: metrics-layer slice — authorized only after D7
  answers; scoped queries first, rebuildable projections only after measured
  need.
- **Consumer wiring restrictions**: no derived metric exists anywhere until
  D7; placement vs academic outputs never unioned; no official-score headers.
- **Acceptance evidence**: cited runs for raw facts; metrics need new
  qualification when authorized.

## Remaining operational consumers (desks, Pages, workspaces)

- **Status**: COMPLETE for shipped surfaces (T3 + desks + R1/R3).
- **Dependencies**: all closed slices + config plane.
- **Completed evidence**: 13 native command Pages (T3), run `35073376790` @
  `3587700`, 542/542 (`release-command-pages-*`); R1 workspaces @ `69a8a95`;
  eight role desks (`docs/product/ROLE-DESKS.md`; `tests/desk` + client suites).
- **Blockers**: none for shipped surfaces.
- **Owner decisions required**: none (D10 (ii) executed; D9 (d) closed).
- **Implementation slices**: none — new desks/Pages only with new authorized
  domain slices, under the same audience/projection/allow-list contracts.
- **Consumer wiring restrictions**: no new native Education/ERPNext authority;
  no audience widening; guided actions prefill existing commands only.
- **Acceptance evidence**: cited runs + `tests/desk` + `test_role_desks.cjs`.

## HR / payroll (A09; contract-driven compensation → native HRMS)

- **Status**: COMPLETE for framework (T1/T2 + D12 semantics); full payroll
  posting remains gated (BLOCKED where B08/proof unsupplied).
- **Dependencies**: Foundation (HRMS pin); D2/D12 owner answers (received);
  B08 remainder + native-path proof for full posting.
- **Completed evidence**: `TH Instructor Contract` (+skill terms/adjustments)
  + `TH Teaching Assignment`; T1/T2 run `35066349129` @ `fa02137`, 536/536;
  D12 one-off payable + window-closing semantics; design doc
  (`TEACHING-COMPENSATION-DESIGN.md`).
- **Blockers**: employment classification/pay-basis/statutory remainder (B08);
  chosen native path proof; unique source ingestion; amendments; payroll/GL/
  payment reconciliation.
- **Owner decisions required**: D2/B08 remainder (rates are configuration;
  statutory/classification rules are owner policy).
- **Implementation slices**: payroll-posting slice — authorized only after
  B08 remainder + native-path proof. No parallel ledger, ever.
- **Consumer wiring restrictions**: exactly one canonical native input path
  per employee/pay-component/period/source-basis; no simultaneous Timesheet +
  Additional Salary ingestion for the same basis; classroom attendance never
  an input.
- **Acceptance evidence**: cited run for framework; posting needs new hosted
  payroll/GL/payment reconciliation when authorized.

## Integration (provider events, queues, realtime)

- **Status**: DEFERRED (no gateway at launch — D6b CLOSED as none; no approved
  provider events; realtime task-room containment verified by inspection).
- **Dependencies**: owner selection for any future integration.
- **Completed evidence**: R5 upstream tracking (0 owned emit sites with
  business payloads); native queue/report/realtime authorization rules in the
  domain contract.
- **Blockers**: no selected provider, gateway, or event source.
- **Owner decisions required**: any future integration needs explicit owner
  selection (commercial + data-sharing policy).
- **Implementation slices**: none authorized.
- **Consumer wiring restrictions**: no exactly-once/distributed-transaction
  promises; provider events (if ever approved) need signature/freshness +
  unique identity + amount/currency/party/obligation validation.
- **Acceptance evidence**: EVIDENCE REQUIRED if ever authorized.

## Security hardening

- **Status**: BLOCKED (SEC-DEPS-01 REJECT / UPSTREAM-BLOCKED; owner standing
  decision 2026-09-19: keep REJECT until findings can be read).
- **Dependencies**: readable advisory output (environment with log access);
  compatible upstream migration; hosted re-qualification.
- **Completed evidence**: verified rejection (not a waiver): active-branch
  runtime `35122242581` @ `d7df9ca` — 114/116 restricted checks, both
  dependency audits fail (14 PyPI/OSV records across pdfkit/pypdf/setuptools/
  weasyprint + 57 npm findings); candidate `35122242647` failed, not adopted;
  prior-branch provenance `35090904508` retained. Classification: evidence/
  inspection limitation — neither demonstrated exploit nor all-clear; no CVE
  IDs invented. Scoped passes retained: 47 isolation checks, browser/CSRF,
  encrypted-credential/permission recovery, copied-session revocation.
- **Blockers**: scanner detail unreachable here (blob-log EOF; annotations
  carry no CVE IDs); no credible official candidate passes yet (pdfkit
  no-fixed-version advisory; Bench-constrained setuptools fix); byte-identical
  reviewed inputs in newer v16 releases.
- **Owner decisions required**: none pending (standing REJECT recorded);
  future upgrade needs compatibility evidence, not a waiver.
- **Implementation slices**: (a) readable-audit slice in a log-capable
  environment; (b) coherent maintained-stack migration slice with clean
  re-run. No in-repo patching of the pinned bundle (that would invent a fork).
- **Consumer wiring restrictions**: no production operation while REJECT;
  no dependency change without re-qualification of the full hosted suite.
- **Acceptance evidence**: EVIDENCE REQUIRED (clean full-stack + frontend
  audits on an official candidate).

## Backup / recovery

- **Status**: BLOCKED (mechanism exists; rehearsal + off-site + measured
  objectives remain EVIDENCE REQUIRED).
- **Dependencies**: D13 targets (received), D14 class (received), real-server
  rehearsal, off-site hardware build.
- **Completed evidence**: interim mechanism (`tools.operations.interim_backup`;
  different-volume refusal, openssl encrypt/digest sidecar, `--files-root`,
  `--restore` staging verify; `tests/operations/test_interim_backup.py`);
  P1 key defect CLOSED (`35133062884`); P2 durability probes (`35135793802`…);
  P3 separate-VM destructive recovery (`35170062251`); P4 encrypted backup +
  custody retrieval/rotation (`35179445639`) — structural proofs, not gate
  passage (see gap map §1.6 + final evidence report §§9–11).
- **Blockers**: restore rehearsal on the real server (date/digest/elapsed/
  outcome unrecorded); off-site hardware build; measured RPO/RTO vs D13
  targets; multi-version retention/rotation on the target; session revocation
  on recovery; real trust-boundary custody (KMS/HSM/owner store —
  ENVIRONMENT-BLOCKED here).
- **Owner decisions required**: none pending for the interim class (D13/D14
  received); specific device/site/address supplied by the owner at build time.
- **Implementation slices**: (a) real-server rehearsal slice; (b) off-site
  build slice. No off-site fiction, no invented measurements.
- **Consumer wiring restrictions**: no production data until rehearsal is
  recorded on the real target.
- **Acceptance evidence**: EVIDENCE REQUIRED (rehearsal record + measured
  objectives + custody proof).

## Production readiness & release (D8 + launch)

- **Status**: BLOCKED (production REJECT; D8 BLOCKED; local launch readiness
  NOT YET READY).
- **Dependencies**: all rows above + owner authorization.
- **Completed evidence**: D8 business requirements selected + recorded
  (canonical record + charter + decision matrix + implementation contract +
  input packet); D15 local-only scope; D16 activation mechanism;
  launch runbook; release candidate dossier; closure register. Launch-critical
  satisfied: domain-qualification, authorization-isolation, ownership.
  Launch-critical unsatisfied: backup-restore, dependency-security,
  durability, observability (audit-trail subset), topology-edge-session
  (TLS/session on Tailscale), production-authorization.
- **Blockers**: (1) owner has not authorized production; (2) SEC-DEPS-01
  REJECT; (3) synthetic-only REQUIRED; (4) backup-restore rehearsal;
  (5) TLS/session evidence on the Tailscale URL; (6) durability +
  observability measurements. Operational hardening deferred (not
  launch-blocking, not passing): off-site DR, upgrade-rollback, realtime,
  capacity-availability, change-control.
- **Owner decisions required**: production GO (only after gates close);
  synthetic-only lift for the local site (backlog item 1).
- **Implementation slices**: evidence slices only — no feature work unblocks
  this row; only proofs do.
- **Consumer wiring restrictions**: nothing serves real students until GO.
- **Acceptance evidence**: EVIDENCE REQUIRED for every gate (see `SKILL.md`
  §J + final evidence report). No documentation-only substitution.

# TOEFL House ERP — Agent Operating Skill

Date: 2026-09-22 · Location: `docs/operating-system/SKILL.md`
Status: **authoritative operational entry point for future engineering agents**.
Scope: **governance/operating documentation only** — this file authorizes no code,
schema, permission, deployment, or production change by itself.

This skill teaches an agent how to operate this repository from the current
state through final production readiness. It is one of seven operating-system
documents with exactly one authority per information kind (see §0).

Production posture at the time of writing: **REJECT**. D8: **BLOCKED**.
SEC-DEPS-01: **REJECT / UPSTREAM-BLOCKED**. Synthetic-only: **REQUIRED**
(D16 activation mechanism exists; it is not activated). Nothing in this skill
changes that posture. See `CURRENT-BASELINE.md`.

---

## 0. Document authority map (one source of truth per kind)

| Question | Authoritative answer lives in | This skill's role |
|---|---|---|
| How do I operate this repo day to day? | **This file (`SKILL.md`)** | Primary |
| What is the project, its scope, and who decides what? | `PROJECT-CHARTER.md` | Reference |
| What architectural patterns must I preserve? | `ARCHITECTURE-CONSTITUTION.md` (patterns) + `docs/domain/ARCHITECTURE-DECISIONS.md` + `docs/domain/DOMAIN-CONTRACT.md` (domain architecture record) | Reference |
| What is the status/ordering of every domain? | `DOMAIN-ROADMAP.md` | Reference |
| What is decided vs still open? | `DECISION-REGISTER.md` (consolidated index) + `docs/engineering/canonical-owner-decision-record.json` (canonical owner answers) + `docs/engineering/OWNER-DECISIONS.md` (readable projection) | Reference |
| What is the exact current state (branch/HEAD/tests/blockers)? | `CURRENT-BASELINE.md` | Reference; update it at milestones |
| How do I continue after another agent? | `HANDOFF-PROTOCOL.md` | Reference; follow it every session |
| Academic control-plane contract | `docs/product/CONFIGURATION-PLANE.md` (unchanged authority) | Reference, never duplicate |
| Role-desk product contract | `docs/product/ROLE-DESKS.md` (unchanged authority) | Reference |
| Release/production evidence | `docs/engineering/RELEASE-GAP-MAP.md`, `FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md`, `PRODUCTION-READINESS-2026-09-19.md`, `LAUNCH-RUNBOOK.md` | Reference |

If this skill and a higher authority conflict, the higher authority wins
(see §C). If two authorities appear to conflict, **STOP** and escalate —
never pick the convenient one.

---

## A. Mission

Build a complete, production-ready **TOEFL House ERP**: a native-first
Frappe/ERPNext/Education/HRMS operating system for a language-training center,
covering the lifecycle below **only as authorized by the domain contract,
capability map, owner decisions, and architecture decisions**:

- **Visitors / prospects**: native ERPNext Lead as the pre-program identity
  (A01 route P); no parallel applicant/person master.
- **Applicants**: native Education Student Applicant once a real Program/year
  is genuinely intended (A01 route K); business "applicant" intention is not
  automatically a native document.
- **Placement**: internal entrance/English-level determination + course/level
  recommendation before enrollment (owned TH Placement Decision + supporting
  governance/execution records). CLOSED / QUALIFIED for the bounded synthetic
  isolated build. Never an official/mock TOEFL score, never a CEFR certificate
  (A07). Do not reopen.
- **Admission**: explicit admission decision over native Applicant/Student
  (thin `TH Admission Decision`). CLOSED / QUALIFIED. Admission, offer
  acceptance, Student conversion, and enrollment remain distinct facts (A10).
- **Students**: native Education Student (email required; conversion may
  provision User/Customer and flip Applicant status — none of which equals
  enrollment or institutional approval).
- **Guardians**: explicit native Guardian–Student relationship post-conversion;
  pre-admission proxy remains conditional/deferred (A03, D4). Contact/payer
  status is not permission.
- **Programs / levels / courses**: Academic Control Plane — `TH Academic
  Program` families; each level IS a native `Program` record anchored once by
  the guarded command; native Course/Program Enrollment/Student Group/
  Assessment Plan consume the anchor with zero TOEFL-specific masters.
- **Classes / timetables**: native Student Group roster (submitted enrollments
  only), native Course Schedule sessions (calendar-window + overlap validation,
  row-locked), native Room. CLOSED / QUALIFIED (Teaching Operations).
- **Teachers**: native Employee ↔ Education Instructor link (explicit
  `Instructor.employee`); teacher desk resolves `User → Employee.user_id →
  Instructor.employee → TH Teaching Assignment` and fails closed when unlinked.
- **Teacher workload / skill assignment**: `TH Teaching Assignment` facts
  (skill, class, window); scheduler-owned assignment facts, payroll-owned
  compensation. No second roster authority.
- **Attendance**: native Student Attendance (Present/Absent/Leave, submitted
  rows only). Student Attendance is never Employee Attendance and never
  auto-pays.
- **Academic progression**: effective-dated duration versions + `next_level`
  chain (shipped); assessment-policy carrier `TH Assessment Policy` + versions
  (structure only, zero business values — shipped); grading/progression
  **values** remain owner-deferred (D1/B04/B05). Never invent a threshold.
- **Finance / fees / invoices / payments**: native `Fee Structure`/`Fee
  Category`/`Fees` tuition chain (enrollment-generated, A08 route E) +
  native `Sales Invoice`/`Item Price`/`Pricing Rule` placement billing with
  configuration-driven chargeability. CLOSED / QUALIFIED. ERPNext accounts are
  the only money authority. No TH money master, ledger, price, or tax record.
- **Correction / refund controls**: D3 framework — `TH Correction Policy`
  (append-only effective-dated versions, approver role + correction window as
  owner-entered terms) + `TH Correction Request` (pins governing version at
  creation; full-amount only; native credit-note / Fees-cancellation postings).
  Partial refunds await exact owner terms; fail closed meanwhile.
- **HR / payroll**: HRMS is the single canonical payroll authority. ratified
  configurable fixed/skill-based/combined compensation feeds native inputs
  (one Additional Salary per teaching assignment, one-off in the first
  covering period — D12); rates/statutory rules/exact payable policy remain
  configuration or gated (A09, D2 remainder). No parallel payroll ledger.
- **Reporting**: raw-fact registers only (R2: tuition/placement billing Query
  Reports; central canonical definition register `toefl_house.reporting`).
  Derived metrics require named stewards + denominators + disclosure/retention
  policy (D7/A12) — deferred. Never union placement and academic scores.
- **Configuration**: the Academic Control Plane + D3 correction policy are the
  governed pattern: Course-Owner/Finance-Owner gated guarded commands,
  request-key idempotency, row locks, effective dating, native `Version` +
  hash-chained audit, business-language refusals. See `CONFIGURATION-PLANE.md`.
- **Audit**: native `Version` (track_changes) + `TH Placement Audit Event` /
  `TH Configuration Audit Event` hash-chained streams + operation receipts
  (`TH Placement Operation` / `TH Configuration Operation`). Audit is evidence,
  not a second business log.
- **Security**: deny-by-default guards on all seven command-only doctypes
  (pinned on `validate`, `before_cancel`, `before_update_after_submit`),
  role-gated commands, `policy.can_read` projection scoping, synthetic-only /
  D16 site-mode gate, no secrets in Frappe, private-file parent+purpose
  visibility. A13 containment demonstrated for implemented slices only.
- **Backup / recovery**: interim backup mechanism exists (different-volume
  refusal, openssl AES-256-CBC PBKDF2, sha256 sidecar, `--files-root` second
  artifact, `--restore` verify-then-decrypt to staging). Rehearsed restore on
  the real server, off-site hardware (D14 class selected, not built), and
  measured RPO/RTO remain BLOCKED/EVIDENCE REQUIRED.
- **Operational readiness / production readiness**: D8 business requirements
  selected and recorded; engineering implementation + independent evidence
  remain BLOCKED; production stays REJECT until every applicable gate is
  actually proven. Scope authorization (D15) and activation mechanism (D16)
  are not gate passage.

Do not invent functionality the repository does not authorize. Deferred means
deferred; blocked means blocked; closed means closed (do not reopen Placement,
Admission, Enrollment, Teaching, or Finance to add scope).

---

## B. Operating Principle

Every session follows this loop, in order, with no skipping:

```
READ → UNDERSTAND → AUDIT → PLAN → IMPLEMENT → TEST → AUDIT → RECORD → COMMIT → CONTINUE
```

- **READ**: baseline, decision register, domain contract, native ground truth,
  existing implementation.
- **UNDERSTAND**: restate the slice's authority, dependencies, and consumer
  restrictions in your own words before touching code.
- **AUDIT (pre)**: read-only dependency/design audit; identify exactly one
  authorized slice.
- **PLAN**: state exact scope (files, commands, tests, evidence). If scope is
  unclear → keep auditing. If authority is missing → STOP.
- **IMPLEMENT**: one slice only. No unrelated cleanup, no broad refactor.
- **TEST**: targeted tests first, then the canonical full suites.
- **AUDIT (post)**: read-only diff audit; verify no scope creep, no hidden
  policy, no security/production drift, no weakened assertions.
- **RECORD**: update baseline + decision/register/roadmap entries the slice
  actually changed.
- **COMMIT**: only after SAFE TO COMMIT (see §Quality Gates).
- **CONTINUE**: hand off the exact next state per `HANDOFF-PROTOCOL.md`.

Never jump directly into coding.

---

## C. Authority Hierarchy

Strict precedence, highest first. No implementation may override a higher
level for the convenience of a lower one:

1. **Safety / security / production controls** — fail-closed guards,
   synthetic-only/D16 site mode, permission boundaries, audit integrity,
   backup/recovery custody, release gates, production REJECT. These are
   code/evidence controlled, never configuration toggles.
2. **Explicit owner decisions** — the canonical owner-decision record
   (`docs/engineering/canonical-owner-decision-record.json`) and its
   projections (`OWNER-DECISIONS.md`, `DECISION-REGISTER.md` index).
   Only the authorized owner (Course Owner final; GM/Academic/Finance/
   Reception by scope) supplies business policy.
3. **Architecture decisions** — `ARCHITECTURE-CONSTITUTION.md`,
   `docs/domain/ARCHITECTURE-DECISIONS.md` (A01–A13),
   `docs/domain/DOMAIN-CONTRACT.md`, `docs/domain/ERP-CAPABILITY-MAP.md`.
4. **Domain contracts** — `docs/product/CONFIGURATION-PLANE.md`,
   `docs/product/ROLE-DESKS.md`, closure docs, finance-policy approval,
   compensation design, D8 implementation contract.
5. **Established implementation patterns** — guarded commands, effective
   dating, hash-chained audit, idempotency, row locking, desk projection
   rules, test/evidence conventions already proven in this repo.
6. **Agent convenience** — last, always. Convenience never justifies
   weakening, bypassing, or reinterpreting levels 1–5.

---

## D. Human-vs-Agent Boundary

### Agent may decide autonomously

- Implementation details within an authorized slice (function layout,
  validation order, error-message wording in established business language).
- Refactoring strictly within ratified scope that preserves behavior + evidence.
- Test design (unit matrices, lifecycle rehearsals, negative-route proofs)
  using established harnesses and fixtures.
- Code organization consistent with existing module boundaries.
- Technical validation (locks, transactions, idempotency, hash chains,
  permission checks) against pinned native semantics.
- Use of established native ERPNext/Education/HRMS patterns after inspecting
  the pinned sources.
- Implementation sequencing **only where the architecture already determines
  it** (roadmap dependencies + decision register).

### Agent MUST stop

Stop (do not guess, do not implement around, do not default) when:

- a new business policy is required (rate, threshold, window, vocabulary,
  approver, denominator, retention, jurisdiction, calendar, mapping…);
- an owner decision is missing (see `DECISION-REGISTER.md` → OWNER DECISION
  REQUIRED / DEFERRED);
- architecture is ambiguous or two authorities appear to conflict;
- native ERP semantics are insufficient **and** no owned architecture exists
  for the gap (needs B13-style justification first);
- historical meaning could change (effective-date reinterpretation, status
  rewrite, retroactive rate/threshold application);
- safety/security/production boundaries would change (guards, gates, site
  mode, custody, permissions, audit);
- evidence is missing (native behavior unproven, hosted proof absent where
  the contract requires it);
- a value/default/threshold would need to be invented to proceed;
- two authoritative decisions conflict.

When stopped: record a precise blocker (what is missing, who owns it, what
is blocked, what evidence would unblock it) in the working notes and — if
the milestone warrants it — in `CURRENT-BASELINE.md` / `DECISION-REGISTER.md`.
Never solve an owner decision by guessing.

---

## E. Non-Negotiable Engineering Rules

Preserved from the project's established principles and proven implementation.
Every rule below is binding on every slice:

1. Business policies are configurable where designated (control-plane
   carriers, correction policy, compensation contracts, fee masters).
2. No invented business defaults — zero grading thresholds, rates, windows,
   percentages, retention periods, or mappings from the agent.
3. No hidden business-policy literals in owned code (the hard-coded-policy
   audit test enforces this; technical constants must be named and bounded).
4. Effective-dated policies where required (durations, assessment versions,
   correction versions, contracts); new versions start strictly after the
   latest; predecessors are superseded/closed, never rewritten.
5. Immutable historical meaning — every transaction answers "what
   policy/version governed this at the time?" and preserves it.
6. Command-only mutation where governed — all writes through guarded
   whitelisted POST commands; controllers refuse native/REST/import writes
   outside command context.
7. Idempotent guarded commands — stable request keys; same key + same payload
   + same actor returns the existing outcome; different payload conflicts.
8. Request-key protection on every mutating command surface.
9. Row locking / TOCTOU protection where required (policy rows, enrollment/
   invoice/fee facts re-proven under lock at decision time).
10. Hash-chained audit where required (placement + configuration audit
    streams; singleton policy streams span versions via stable target keys).
11. Fail-closed behavior everywhere — unknown → deny with a business-language
    reason naming the owner/action, never a raw traceback or silent skip.
12. Native ERPNext semantics where sufficient — Program, Enrollment, Fees,
    Invoice, Attendance, HRMS payroll remain the authorities.
13. Owned carriers only where native semantics are demonstrably insufficient
    (B13 justification; minimum footprint; no duplicate masters/ledgers).
14. No duplicate engines — one payroll authority (HRMS), one money authority
    (ERPNext accounts), one enrollment ledger (Program Enrollment).
15. No unnecessary custom DocTypes — thin slices over native records are the
    default; each new doctype needs B13-level justification.
16. No silent history rewrites — corrections supersede via new audited
    actions (native amend/cancel/credit/return; never delete posted history).
17. No destructive cancellation to evade constraints (A11) — history-
    affecting cancel/transfer stays blocked until a safe path is proven.
18. No secrets in Frappe — keys live in site_config/custody channels, never
    in doctypes, code, or committed config.
19. No production authorization by checkbox/settings — production GO requires
    evidence gates + owner authorization; config flags cannot flip posture.
20. No weakening gates to make tests pass — fix the implementation, not the
    contract, unless the contract itself is proven wrong (then escalate).
21. No simulated evidence — hosted/synthetic claims require real runs with
    run IDs, commits, check counts, and report hashes.
22. No fake operational readiness — mechanisms are not rehearsals; rehearsals
    are not gate passage; gate passage needs independent evidence.
23. No test assertion weakening — failing tests indict the implementation
    (or, rarely, a proven-wrong contract via escalation), never the assertion.
24. No bypass of existing authority boundaries — A13 containment, desk
    audiences, projection allow-lists, workspace gates, and role scopes stay
    intact; every alternate writer (RPC/REST/Desk/import/job/cancel/export/
    file) must satisfy the same invariants.

---

## F. Configuration Principle

```
BUSINESS CONFIGURATION ≠ SAFETY/SECURITY/PRODUCTION CONTROL
```

- **Business values** (programs, levels, durations, fee plans, discount rules
  under Policy A, correction approver role + window, assessment facets once
  D1 answers arrive, compensation rates/terms, RPO/RTO targets) may be
  configurable by the authorized business authority through governed carriers.
- **Safety, security, evidence, custody, production authorization, and release
  gates** remain code/evidence controlled. They are never feature flags,
  settings checkboxes, per-request options, or "temporary" bypasses.
- Configuration must never become a bypass mechanism: no runtime flag that
  lets two billing producers race, no per-request policy override, no settings
  switch that disables a guard, gate, audit chain, or permission check.
- Typo-guards and technical bounds (code shape, reason-length bounds, query
  limits, the 0–3650 correction-window bound) are engineering constants with
  names and tests — never confused with business policy.

---

## G. Historical Integrity

Every agent must ask, for every transaction it touches:

> **"What policy/version governed this transaction at the time?"**

- Where required, transactions preserve the governing policy/version
  (duration version at enrollment date; correction version pinned at request
  creation; assessment version at evaluation date; contract window at payroll
  period; fee-structure snapshot copied into issued `Fees`).
- Future configuration changes must never silently reinterpret historical
  transactions: append + supersede/close, never rewrite; successor rates apply
  from their own start date only (D12); retired policies fail closed for new
  requests while pinned historical requests keep judging their pinned terms.
- Live facts (existence, submitted state, totals, outstanding amounts) are
  always re-proven against the live document under lock at decision time —
  the pin carries policy terms, not a stale copy of the world.

---

## H. Native-First Principle

Before creating custom behavior, in order:

1. Inspect native ERPNext/Education/HRMS semantics **in the pinned sources**
   (`docs/engineering/foundation-version-matrix.json`: Frappe v16.33.1,
   ERPNext v16.34.2, Education v16.1.0, HRMS v16.18.1) — never from memory.
2. Determine whether native behavior is sufficient for the authorized slice.
3. Reuse it if sufficient (native links, native postings, native workflows).
4. Wrap it only if governance/readiness/audit requires ownership (guarded
   commands + deny-by-default guards + receipts, preserving native effects).
5. Build custom mechanics only when native semantics are demonstrably
   insufficient — with B13-level justification and the minimum footprint.

Never create a parallel ERP engine unnecessarily. The capability map
(`docs/domain/ERP-CAPABILITY-MAP.md`) classifies every domain as NATIVE /
CONFIGURATION / TOEFL HOUSE EXTENSION / DEFERRED — follow it.

---

## I. Project-wide guardrails (permanently prohibited)

- Inventing business values, defaults, or policy thresholds.
- Hidden fallback policy (silent defaults when configuration is absent —
  fail closed with a named owner/action instead).
- Silently changing historical meaning.
- Implementing consumers before their policy carrier / readiness / audit
  foundation exists (carrier → readiness → consumer, strictly).
- Weakening evidence gates or production controls.
- Creating configuration switches for security/safety controls.
- Bypassing command-only mutation or audit.
- Writing directly to native records when the contract requires guarded
  commands (including "just this once" scripts against production-shaped data).
- Changing tests merely to accommodate incorrect behavior.
- Simulated operational evidence or fake readiness.
- Unauthorized migrations (every migration needs authorization + rollback story).
- Unrelated cleanup during a scoped slice; broad refactors during domain work.
- Introducing new engines/capabilities without explicit architectural
  authorization.

---

## J. Quality gates

### Before implementation

- [ ] Architecture known (constitution + domain contract section identified).
- [ ] Dependencies known (roadmap predecessors satisfied or explicitly staged).
- [ ] Authority known (owner decision cited by ID, or correctly identified as
      missing → STOP).
- [ ] Business decisions available (no placeholder values needed).
- [ ] Native semantics inspected in pinned sources (file + behavior noted).

### Before commit (SAFE TO COMMIT)

- [ ] Targeted tests green (the slice's own suites).
- [ ] Canonical full suites green (`python3 -m unittest discover -s tests -t .`,
      `ruff check .`, Node suites where touched; hosted suites only where the
      slice contract requires them — never claim unexecuted hosted evidence).
      Recorded-baseline exception: a result that exactly matches
      `CURRENT-BASELINE.md` — same failures, same causes, re-verified
      unrelated to the change — satisfies this gate for that change. The
      exception never covers a newly failing test or a check the change
      itself could affect.
- [ ] Diff audited (read-only review; every hunk belongs to the slice).
- [ ] Scope exact (one slice; unrelated work removed/isolated).
- [ ] No hidden policy (hard-coded-policy audit passes; no new literals).
- [ ] No security/production drift (guards, gates, site mode, permissions,
      audit chains untouched except as the authorized slice requires).
- [ ] Historical semantics preserved (effective dating intact; no rewrites).
- [ ] No artifacts (no dumps, backups, credentials, local config, caches).
- [ ] No weakened assertions (tests strengthened or unchanged in meaning).

### Before production (evidence, not documentation)

Actual evidence required for: data readiness, operational readiness,
security, backup/recovery, custody, reconciliation, monitoring, deployment,
rollback, and production authorization. No documentation-only claim may
substitute for operational evidence. Production stays REJECT until the D8
gates + SEC-DEPS-01 + owner authorization are independently satisfied.

---

## K. Continuation algorithm (deterministic)

```
IF current slice is unclear:
    AUDIT (read-only; narrow to one authorized slice)
ELIF owner decision is missing:
    STOP (record blocker; do not implement around it)
ELIF architecture is missing:
    STOP (record what design is needed and who owns it)
ELIF evidence is missing:
    STOP or remain in evidence phase (reproduce native behavior; do not assume it)
ELIF architecture is established:
    IMPLEMENT ONE SLICE (only one; exact scope stated first)
IF tests fail:
    FIX THE IMPLEMENTATION — not the contract — unless the contract itself
    is proven wrong (then STOP and escalate with proof)
IF diff contains unrelated work:
    REMOVE / ISOLATE it (separate change, separate review)
IF historical semantics change:
    STOP
IF security/production boundary changes:
    STOP
IF safe (all §J commit gates hold):
    COMMIT, update CURRENT-BASELINE.md, select the next authorized slice
    per DOMAIN-ROADMAP.md, and hand off per HANDOFF-PROTOCOL.md
```

---

## L. Project completion definition

"Finished" is not "all screens implemented." The project is complete only when
the evidence supports production readiness:

- Required business domains implemented per the ratified roadmap.
- Business policies configurable where intended (carriers + validators +
  commands + desks), with owner-supplied values installed.
- Historical integrity proven (governing-version preservation + no-rewrite
  proofs across durations, assessments, corrections, contracts, fees).
- Native ERP behavior correctly integrated (no parallel masters/ledgers;
  containment proofs for every governed writer).
- All consumers wired only after their foundations are proven
  (carrier → readiness → consumer, with tests pinning the order).
- Permissions/security proven (role gates, projection scoping, negative-route
  proofs across RPC/REST/Desk/import/job/cancel/export/file).
- Audit proven (native Version + hash-chained streams verified end to end).
- Finance/reconciliation proven (one posting chain per obligation; native
  amend/credit/return semantics; no orphaned receivables).
- Backup/recovery proven (rehearsed restore on the real target; off-site
  class built; measured RPO/RTO against D13 targets).
- Operational readiness proven (runbook executed by the owner; TLS/session
  evidence on the Tailscale URL; monitoring/reconciliation in place).
- Production readiness proven (all D8 gates + SEC-DEPS-01 independently
  closed; owner authorization recorded; activation rehearsed).
- Evidence gates satisfied with run IDs, commits, check counts, hashes.
- Release/rollback procedure proven (versioned artifacts; tested rollback).
- No unresolved production blockers.
- Final acceptance evidence recorded.

---

## M. Session startup checklist (do this first, every time)

1. `git status`, `git branch --show-current`, `git log --oneline -5` —
   establish HEAD + clean/dirty state.
2. Read `CURRENT-BASELINE.md` (this directory).
3. Read the relevant `DECISION-REGISTER.md` entries + `DOMAIN-ROADMAP.md`
   rows for your slice.
4. Read the domain contract section + native ground truth (pinned sources).
5. Read the existing implementation + its tests.
6. Perform the read-only pre-audit; state the one slice and its exact scope.
7. Only then implement — per §B, §J, §K, and `HANDOFF-PROTOCOL.md`.

---

## N. Critical rule about business ownership (read twice)

This skill must never become a mechanism for the agent to make business
decisions. It makes the agent highly autonomous in **engineering** while
preserving **human authority over business policy**.

If the repository does not define a grading threshold, salary amount, refund
percentage, retention period, guardian authority, enrollment rule, metric
denominator, or tax rate, the agent MUST NOT invent one. It must instead
create the correct configuration structure, validator, command, audit,
readiness mechanism, or documented blocker — as appropriate — and STOP at the
policy boundary.

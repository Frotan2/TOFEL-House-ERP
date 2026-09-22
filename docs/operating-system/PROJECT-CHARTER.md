# TOEFL House ERP — Project Charter

Date: 2026-09-22 · Location: `docs/operating-system/PROJECT-CHARTER.md`
Status: **authoritative project charter** (scope, authorities, principles).
This charter creates no code, schema, or production authorization. Production
posture at adoption: **REJECT** (see `CURRENT-BASELINE.md`).

Related authorities (referenced, not duplicated):
`SKILL.md` (operations), `ARCHITECTURE-CONSTITUTION.md` (patterns),
`DOMAIN-ROADMAP.md` (sequencing), `DECISION-REGISTER.md` (decisions),
`CURRENT-BASELINE.md` (state), `HANDOFF-PROTOCOL.md` (continuity),
`docs/domain/DOMAIN-CONTRACT.md` + `ARCHITECTURE-DECISIONS.md` (domain
architecture), `docs/engineering/canonical-owner-decision-record.json`
(canonical owner answers).

---

## 1. Purpose

Deliver a production-ready, native-first ERP operating system for TOEFL House,
a language-training center, covering the learner lifecycle
(Prospect → Applicant → Placement → Admission → Student → Enrollment → Course
Participation → Academic Assessment → Completion), teaching operations,
tuition/placement finance with governed corrections, teacher compensation
through native payroll, role-based daily-work surfaces, and the audit,
security, backup/recovery, and operational-readiness foundations that make the
system trustworthy with real student data.

## 2. Non-goals (explicit exclusions)

- No second ERP: no parallel student, enrollment, invoice, ledger, attendance,
  payroll, permission, or reporting masters. Native Frappe/ERPNext/Education/
  HRMS remain the authorities (`docs/domain/ERP-CAPABILITY-MAP.md`).
- No official-exam business: no official/mock TOEFL score generation, no CEFR
  certification, no external-examination integration (A07). Placement is an
  internal entrance/level determination only.
- No launch-scope portals/gateway: student/guardian portal is future scope;
  online payment-gateway integration is not required at launch (D6b: none).
- No custom frontend platform, analytics warehouse, offline sync protocol, or
  replacement portal (rejected; see legacy-extraction + capability-map records).
- No production operation until evidence gates close: scope authorization and
  activation mechanisms are not GO decisions.

## 3. Authorities and ownership

| Authority | Role | Scope |
|---|---|---|
| Course Owner | System owner; final strategic/ownership authority | Business policy, academic structure configuration, strategic releases, final escalation |
| General Manager | Routine administration + operations | Day-to-day operations, recovery/incident coordination, routine release coordination |
| Academic Manager | Academic operations | Academic operations, student progress, academic-side review |
| Finance Manager | Finance + payroll | Finance/payroll through native authorities, correction approvals by configured role |
| Reception | Intake | Student intake + reception operations |
| Engineering (agents + reviewers) | Implementation mechanics | MFA/RBAC mechanics, network/session controls, encryption/secrets, backup rotation/recovery, monitoring, configuration versioning, rollback, CI/CD, deployment hardening — **never** business values |

Staff access is role-based; important activity is auditable; offboarding
revokes access while preserving history. Multi-branch architecture with
branch-level operational isolation is required (native Company/Branch + User
Permission + server-side command checks; Company/Branch alone is not tenant
isolation). Organization-level aggregates for senior management must not
bypass branch operational isolation.

## 4. Deployment and data posture

- Current authorized launch target: **local server + Tailscale** (D15: LOCAL
  LAUNCH ONLY). The public internet edge (provider, hostname, DNS, public
  edge/TLS) is not authorized and stays unselected.
- Automated multi-version encrypted backup + recovery onto another system are
  required; data preservation has priority over minimizing recovery time
  (RPO 24h / RTO 8h are owner-selected **targets** — D13 — not measured results).
- Off-site destination class: **owner-controlled hardware** (D14) — selected
  as a class; no device/hostname/vendor invented; not built yet.
- No real site configuration, credentials, student/payroll data, dumps, or
  backups are ever committed. Secrets live in site_config/custody, never in
  Frappe doctypes or code.

## 5. Product principles (binding)

1. **Native-first**: reuse Frappe/ERPNext/Education/HRMS; thin guarded slices
   over native authorities; owned carriers only where native semantics are
   demonstrably insufficient (B13 justification, minimum footprint).
2. **Configured, not coded, policy**: business rules live in governed,
   versioned, effective-dated configuration owned by the authorized role —
   never as code literals or invented defaults.
3. **History is immutable**: append + supersede/close; never rewrite. Every
   transaction preserves its governing policy/version.
4. **Command-only mutation**: governed writes flow through guarded, idempotent,
   role-gated commands with request keys, row locks, and hash-chained audit;
   controllers refuse off-path writes.
5. **Fail closed**: unknown → deny in business language naming the owner and
   action. Denial is a feature, not a bug.
6. **Evidence before claims**: hosted/synthetic qualification with run IDs,
   commits, check counts, and report hashes; mechanisms are not rehearsals;
   rehearsals are not gate passage.
7. **Security/production controls are code/evidence governed**, never
   configuration toggles. Business configuration never becomes a bypass.
8. **Least authority**: desks project minimal declared fields; workspaces and
   Pages grant navigation without widening document authority; containment
   (A13) covers every alternate writer.

## 6. Scope control

- **Closed stays closed**: Placement, Admission, Enrollment, Teaching
  Operations, and Finance are CLOSED / QUALIFIED for their bounded synthetic
  slices. Follow-on work extends via new authorized slices — never by
  reopening a closed slice's meaning or evidence.
- **Consumers follow foundations**: policy carrier → readiness → consumer,
  strictly. No consumer is wired before its carrier/readiness/audit foundation
  is proven and tested.
- **One slice at a time**: exact scope stated before implementation;
  unrelated cleanup and broad refactors are separate changes.
- **Deferred stays deferred** until the owning authority decides: D1 values,
  D4 advanced identity/guardian, D5 advanced calendar/repeat/transfer, D6a tax,
  D7 derived metrics, D8 numeric capacity/availability + operational evidence.

## 7. Acceptance

The project is accepted only per the completion definition in `SKILL.md` §L:
required domains implemented, policies configurable with owner values,
historical integrity proven, native integration + containment proven, audit +
finance/reconciliation proven, backup/recovery + operational + production
readiness proven with independent evidence, release/rollback proven, zero
unresolved production blockers, final acceptance evidence recorded.
Documentation alone never constitutes acceptance.

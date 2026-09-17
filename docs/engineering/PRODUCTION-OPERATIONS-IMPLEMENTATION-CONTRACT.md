# TOEFL House ERP — Production Operations Implementation Contract

Date: 2026-09-16 · Active branch: `arena/01a0aef4-tofel-house-erp`

**Purpose:** record the engineering-selected mechanisms that implement the
business requirements in [`canonical-owner-decision-record.json`](canonical-owner-decision-record.json).
This is an implementation contract and evidence checklist, not production
qualification. Production remains **REJECT** and the synthetic-only hard stop
remains mandatory.

## 1. Native authority and fail-closed boundary

- Frappe User, Role, User Permission, Session, File and Version remain the
  identity, authorization, file and history authorities.
- ERPNext/Education/HRMS remain the authorities for students, courses,
  enrollment, attendance, accounting, employees and payroll.
- TOEFL House roles are least-privilege role names. A role fixture does not
  grant native document permission; permission rows and branch scopes are
  configured through native authorities.
- Custom commands derive the actor from the authenticated server session and
  recheck role, state, relationship, branch scope, idempotency key and
  synthetic-site guard server-side. Client controls are convenience only.
- No custom role, page or endpoint may create a parallel student, course,
  pricing, accounting, payroll, branch, monitoring or audit authority.

## 2. Authentication, MFA, sessions and offboarding

- Use native Frappe authentication and session lifecycle. Do not add a second
  login, password store, token authority or public portal login.
- Require native MFA for privileged Course Owner, General Manager, Finance
  Manager and other management/admin accounts in the selected deployment
  configuration. Engineering owns the exact supported native MFA setting and
  its tested recovery path; no secret or recovery code is stored in source.
- Enforce secure session/cookie, CSRF and timeout/revocation settings at the
  local/Tailscale deployment boundary. Future internet hosting must repeat the
  edge/session qualification rather than inherit a local assumption.
- Offboarding is a native User disable plus role/permission/session revocation
  workflow. It must not delete User, Student, Employee, accounting, audit,
  File or historical operational records. Active queued/realtime work must
  reauthorize after revocation.
- Evidence required: privileged MFA login/recovery, session revocation,
  copied-session denial, offboarding preservation, and role-union denial tests.

## 3. Branch isolation and aggregate visibility

- Branch scope is authorization/data scope, not tenant isolation by merely
  populating Company or Branch.
- Use native User Permission on Branch/Company and native document permission
  where available. Custom commands must require an explicit branch scope and
  recheck it at write/read/submit/export/attachment/job boundaries.
- Course Owner and explicitly authorized senior management may receive
  organization-level aggregates only after branch-scoped source authorization;
  aggregation must not expose unauthorized drill-down rows.
- The controlled owner interface may assign/revoke only the allow-listed TOEFL
  roles through the native User document and records the change in native
  Version. Protected identities and the Course Owner role are not routine
  targets. Native User Permission/Company/Branch routes remain the authority for
  branch scope and other native permissions.
- Evidence required: cross-branch read/write/submit/export/file/job denial,
  permitted same-branch operation, aggregate-vs-drill-down separation, and
  offboarding/role revocation across every relevant path.

## 4. Current deployment and future hosting contract

- Current phase: local/server-based application, database and files; authorized
  staff reach the service through Tailscale. The service is not enabled as a
  public internet endpoint.
- Bind and firewall the service to the selected local/Tailscale boundary; use
  Tailscale ACL/device/user controls and native application authorization
  together. No hostname, DNS, provider, cloud/VPS, public edge or public TLS
  value is invented here.
- Future internet hosting is a separate phase. Before enablement it requires a
  selected edge/origin/session/TLS/CSRF/private-file/realtime topology and
  independent evidence for each.

## 5. Encrypted versioned backup and recovery

- Back up the native database and public/private files as one versioned product
  snapshot using supported Bench/native database tooling; preserve site
  configuration references needed for restoration without copying live
  credentials.
- Encrypt backups at rest and in transit using an engineering-selected,
  externally injected key mechanism. Keys never live in Git, backup filenames,
  logs or the dashboard. Rotation and retrieval are separate from application
  role permissions and must be tested.
- Maintain multiple immutable/versioned backup points with deterministic
  rotation. Exact retention counts and destination are deployment configuration,
  not invented owner policy. Future off-site destination is an adapter boundary,
  not a selected provider.
- Restore onto another system/site with a separate database credential, restore
  the site key through controlled custody, migrate, verify representative native
  records and public/private file digests, and revoke copied sessions/credentials
  before any access is allowed.
- Data preservation has priority over minimizing recovery time. Do not claim a
  numeric RPO/RTO until an owner-selected objective is measured in the selected
  architecture.
- Evidence required: scheduled encrypted versions, key retrieval, retention
  rotation, failed-backup alert, alternate-system restore, record/file integrity,
  session revocation and documented reconciliation of interrupted work.

## 6. Configuration, policy and change control

- Fees, discounts, courses, levels, skills, semesters/terms, compensation
  models, statutory payroll values and sensitive financial terms are versioned
  configuration/native policy, never hard-coded in commands or client code.
- Configuration promotion uses reviewed, immutable version/ref provenance and
  native document history where applicable. Secrets and environment-specific
  values are injected at runtime, not committed.
- Course Owner is final authority for strategic/ownership change; General
  Manager coordinates routine operational change without unnecessary approval
  bottlenecks. Sensitive finance/strategic changes retain management controls.
- Every material change records actor, target, before/after reference, reason,
  request identity and resulting native references. Correction/rollback must
  supersede history rather than delete posted facts.
- Evidence required: configuration version/review, unauthorized promotion
  denial, immutable build provenance, native audit/version trail and rollback
  rehearsal.

## 7. Health, monitoring, alerting and rollback

- The Course Owner/General Manager control centre is a sanitized, role-gated
  attention projection; it does not query unrestricted business lists or create
  a second health ledger. Native Error Log, Scheduled Job, queue, database,
  web, backup and application signals are the source evidence.
- Engineering owns structured logs, metrics, redaction, retention/rotation,
  alert rules, health checks and delivery adapters. General Manager owns routine
  operational response; Course Owner receives strategic/final escalation.
- A missing alert receiver is a fail-closed attention state, not a green
  health result. Dashboards must never expose passwords, keys, private file
  contents, student details or financial secrets.
- Rollback is versioned-artifact restore or a tested supported migration
  rollback, never an unsupported database downgrade. Preserve the failed
  artifact, logs, audit trail and data snapshot; reauthorize sessions after
  restore.
- Evidence required: alert delivery/redaction/retention, dashboard role scope,
  queue/DB/web failure attention, restore-based rollback and communication
  record.

## 8. CI/CD and release gate

- CI runs on the active branch and records immutable commit/ref, dependency
  inputs, generated assets, test reports and artifact hashes. No workflow may
  silently promote a historical branch result to the active branch.
- Narrow validation precedes broad useful validation: JSON/static contracts,
  governance/page tests, D8 contract validation, then the foundation/domain
  suites and hosted qualification when available.
- Release promotion is blocked if any required gate is `BLOCKED` or `REJECT`,
  if SEC-DEPS-01 is `UPSTREAM-BLOCKED / REJECT`, if synthetic-only is absent,
  or if production enablement is attempted without an evidence-linked decision.
- The current CI/D8 validator intentionally reports `BLOCKED` and production
  `REJECT`; that is correct until implementation and independent evidence close
  the gates.

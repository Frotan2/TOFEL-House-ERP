# TOEFL House ERP — Architecture Constitution

Date: 2026-09-22 · Location: `docs/operating-system/ARCHITECTURE-CONSTITUTION.md`
Status: **authoritative architectural pattern record**. It preserves the
patterns future agents must keep; it does not replace
`docs/domain/ARCHITECTURE-DECISIONS.md` (A01–A13),
`docs/domain/DOMAIN-CONTRACT.md`, or `docs/domain/ERP-CAPABILITY-MAP.md`,
which remain the domain-architecture record. On any conflict, those domain
records + explicit owner decisions win — and the conflict must be escalated,
not resolved by convenience.

---

## 1. Domain boundaries (native authorities + thin owned slices)

| Domain | Authority | Owned slice (thin, proven) |
|---|---|---|
| Identity/prospect | ERPNext Lead; Education Student Applicant/Student; Frappe User/Role/User Permission | None (no TH person master). A01 dual-route: Lead-linked case (program unknown) / native Applicant (program known). Returning learners reuse Student. |
| Placement | Owned TH Placement Decision (+ governance/execution records) | Bounded synthetic slices 1–7 + closure (CLOSED / QUALIFIED). No native academic/finance writes. |
| Admission | Native Applicant/Student + owned TH Admission Decision | Thin decision lifecycle (CLOSED / QUALIFIED). No enrollment/billing side effects. |
| Enrollment | Native Program Enrollment (+ Course Enrollment side effects) | Thin `enroll_in_program` (CLOSED / QUALIFIED). No second registration ledger. |
| Teaching ops | Native Student Group / Course Schedule / Student Attendance | Thin roster/session/attendance commands (CLOSED / QUALIFIED). No new DocType. |
| Finance | Native Fees / Fee Structure / Fee Category / Sales Invoice / Item Price / Pricing Rule / Payment Entry / GL | Thin `issue_tuition_fees` / `issue_placement_fee` + D3 correction framework (CLOSED / QUALIFIED + HEAD versions). No money master. |
| Academic config | Native Program/Course/Academic Year/Fee masters + TH carriers | TH Academic Program / TH Program Level (level IS a native Program) / TH Level Duration versions / TH Discount Rule / TH Assessment Policy(+versions). Course-Owner governed. |
| Compensation | HRMS (sole payroll authority) + native Employee/Instructor | TH Instructor Contract (+skill terms/adjustments) + TH Teaching Assignment facts; one Additional Salary per assignment, one-off (D12). No payroll engine. |
| Reporting | Source owners; `toefl_house.reporting` canonical definitions; R2 raw-fact Query Reports | No derived-metric engine (D7 deferred). |
| Operations | Native backup/scheduler/RQ + owned interim tooling + desks | Desks/Pages project facts; commands stay the only writers. |

## 2. Authority boundaries

- Native permission AND domain scope/state are conjunctive; role unions and
  client flags never override denials.
- Branch/company scope: native permission plus server-side command checks.
- Desk audiences are pinned (`desk/__init__.py` + Page Has-Role + contract
  tests); projections expose only `PROJECTION_FIELDS`, bounded queries, one
  round trip.
- Workspaces grant navigation, not authority (`TH Receipts` for auditors,
  `TH Finance` for finance staff; API-first officer roles intentionally land
  on no workspace — desks + command Pages instead).
- Guided actions embed prefills for existing guarded commands only when the
  server confirms the viewer holds the acting role; the client never decides
  authority (courtesy guards mirror server rules; the server re-validates all).

## 3. Configuration architecture

- Carriers: `TH Academic Program`, `TH Program Level` (+`TH Level Duration`
  child versions), `TH Discount Rule`, `TH Assessment Policy`
  (+`TH Assessment Policy Version`), `TH Correction Policy` (append-only
  versions), native Fee/Academic-Year masters orchestrated by guarded commands.
- Identity immutability: `code`/`family`/`native_program` are set-once
  (doctype level); no command changes them.
- No delete/cancel on configuration for any role; retire/reactivate is the
  only destructive-shaped action (latest-only for correction policy).
- Global-only authority (OD-CP-3 A): no branch-override layer. Fee plans
  already carry native Company dimensions; no second override axis.
- Hard-coded-policy audit: owned code contains zero program/level/fee/
  discount/assessment literals (permanent test). Technical constants are
  named, bounded, and tested (statuses, reason lengths, query limits,
  typo-guard ceilings such as the 0–3650 correction-window bound).

## 4. Versioning and effective dating

- Duration, assessment, correction, and contract windows are effective-dated
  version sets: new versions start strictly after the latest; predecessors
  close (`superseded_on` / `effective_end`) and are never rewritten.
- Resolution rule: the latest version effective on a date governs that date;
  every date resolves to exactly one governing version (tested, including
  boundary semantics).
- Requests pin the governing version at creation (correction requests;
  assessment evaluations; payroll periods). Approvals judge pinned terms even
  after supersession/retirement, while live document facts are re-proven.
- Contract supersession closes the predecessor the day before the successor
  starts (D12); successor rates apply from their own start date only.

## 5. Audit

- Native `Version` via `track_changes` on configuration doctypes (who/what/
  before/after/when) + first-class business dates (`set_by`/`set_on`/
  `reason`/`effective_from`) where the date IS business meaning.
- Hash-chained streams: `TH Placement Audit Event` and
  `TH Configuration Audit Event` (per-target chains; singleton policy streams
  use a stable target key so the chain spans versions).
- Operation receipts: `TH Placement Operation` / `TH Configuration Operation`
  (kind, actor, input hash, result; private per-key receipts).
- GM/Owner desks project recent recorded actions from existing receipts —
  a projection, never a second log. Hashes/keys/payloads stay off desks.

## 6. Readiness

- Readiness is a computed fact over configuration + native state, never a
  stored flag: progression-chain integrity (names contradictions), per-level
  billing readiness for the current academic year, levels without fee plans,
  unanchored native programs, governed-duration resolution.
- Billing prefill resolves each enrollment's configured plan; missing/
  incomplete/ambiguous plans name the Course Owner + Academic Setup instead
  of offering a button that can only fail.
- `validate_*` commands commit to the exact snapshot (D1/D3 mechanics):
  structural checks over the precise version set, not over "current" drift.

## 7. Command-only mutation

- Every governed write flows through a whitelisted POST command:
  gate (role + site mode) → request-key validation → pure-rule validation →
  row-locked reads → native writes inside command context → receipt + audit
  in the same transaction → business-language result/refusal.
- Controllers (`validate`, plus `before_cancel` / `before_update_after_submit`
  on the seven guarded doctypes) refuse any write outside command context —
  native form, REST, import, cancel, post-submit edit, copy/amend — with
  business language. Guards are pinned on all three lifecycle seams because
  pinned Frappe fires `validate` only on save/submit.
- Idempotency: stable request keys; same key + same payload + same actor →
  existing outcome; changed payload/actor → conflict. Whole-command
  transactions persist no partial state.
- Concurrency: canonical lock orders per spec (e.g. allocation: case →
  pins → guard → exposures → writes); TOCTOU-sensitive facts (fee totals,
  window closure, invoice state) re-validated under lock at decision time
  (hosted-proven on MariaDB).

## 8. Historical resolution

- The pair (version set, date) always resolves to the same governing version;
  changing "Starter = 2 months" to "3 months from July" leaves June
  enrollments at 2 months forever (proven by `tests/configuration`).
- Issued `Fees` copy components at issuance (native snapshot semantics);
  price changes never touch posted documents.
- Native amendments/credits/returns/refunds preserve original references;
  posted history is corrected, never deleted. Deleting Course Enrollments to
  free a uniqueness key is prohibited (A05/A11).

## 9. Native-first design

- Order: inspect pinned native sources → reuse if sufficient → wrap with
  governance only where required → custom mechanics only with B13-level
  justification and minimum footprint.
- Level-AS-native-Program is the constitutive example: enrollment, billing,
  classes, and assessments consume configured structure through native keys
  with zero TOEFL-specific masters and zero changes to qualified commands.
- The alternative designs that break native granularity (family = Program,
  levels = Courses — breaks per-Program Fee Structures) are rejected by the
  control-plane contract.

## 10. Fail-closed behavior

- Absent policy → deny naming the missing configuration + owning role
  (no active correction policy; no fee plan; no published course map; no
  placement-fee item on production; fixture markers on production).
- Ambiguous state → deny, never guess (two editable fee structures; two
  contracts covering a period — closed by D12; ambiguous billing plan).
- Unauthorized actor/mode → deny (wrong role; synthetic-only REQUIRED;
  mixed synthetic+production mode → REFUSED; qualification hostnames can
  never be the production site).
- Unsafe lifecycle → deny with real counts (retire a level with live
  enrollments; retire a program with active levels; close a pool with
  insufficient distinct families).

## 11. Security boundaries

- Synthetic-only guard + D16 site-mode resolution (`SYNTHETIC` / `PRODUCTION`
  / `REFUSED`; mixed → REFUSED; default REFUSED). `require_synthetic` on
  qualification paths is unchanged by D16; `require_operational` accepts
  SYNTHETIC or activated PRODUCTION at guarded business commands.
- `KIND_ROLES` maps every command kind to its executing role; dual-key checks
  (command role + policy-configured approver role) where policy requires it.
- `DOCTYPES` + `CONFIG_DOCTYPES` registries bound the guarded surface;
  `controllers.py` + `guards.py` enforce command context; `policy.can_read`
  narrows reads; private files require parent permission + purpose/time/
  assignment visibility.
- No secrets in Frappe: `encryption_key` / `backup_encryption_key` /
  production flags live in site_config/custody channels; backups scanned for
  generated secrets before transfer; no plaintext key in published artifacts.

## 12. Production authorization boundaries

- `production_state` REJECT is enforced by five guards in
  `tools/foundation/d8_validate.py`; editing a document cannot change it.
- D15 authorizes local-server + Tailscale as the launch **target**; D16
  authorizes building the controlled activation **mechanism** (explicit
  named-site triple; mixed mode refused). Neither closes SEC-DEPS-01,
  backup-restore rehearsal, TLS/session evidence, durability, observability,
  or any other gate. Activation is rehearsed by the owner via the launch
  runbook and is immediately reversible (key removal → REFUSED).
- Synthetic fixture markers (`SYN-…`) are forbidden on production; the
  production placement-fee item must be a real native Item configured in
  site_config + native price list, or billing stays denied.

## 13. Evidence requirements

- Local suites prove logic (`tests/…`, `ruff`, Node suites); hosted runners
  prove native behavior (install exact pins on disposable sites; native
  checks with run IDs, commits, check counts, report SHA-256).
- Every closure cites: qualifying commit, hosted run, check counts, report
  hash, retained failures + fixes. Failed evidence is retained, never
  relabeled.
- Documentation is not runtime proof. A passing helper suite is not a passing
  ERP suite. Green on one branch is not green on another (branch-boundary
  pins + `NOT_EXECUTED_ON_THIS_BRANCH` fail-closed state).

## 14. Backup / recovery / custody boundaries

- Interim mechanism: different-volume destination (`st_dev` must differ),
  openssl AES-256-CBC PBKDF2, sha256 sidecar (cipher + plaintext digests),
  `--files-root` second artifact (private/public files only, never
  site_config), `--restore` verify-then-decrypt into staging (never the live
  root), 14/8/12 retention reported not auto-deleted.
- Classification: INTERIM_PRODUCTION_BACKUP, not disaster recovery.
  Same-machine second drives do not protect against site loss; D14 off-site
  hardware is not built; restore rehearsal on the real server is not executed.
- Custody: keys issued/split/retrieved/rotated across separate machines in
  the P4 model (structural custody, not a trust boundary — no KMS/HSM/secret
  store selected); repository Actions secrets are ENVIRONMENT-BLOCKED for this
  session's credential and are not worked around.

## 15. Testing and release requirements

- Canonical gates: `python3 -m unittest discover -s tests -t .`, `ruff
  check .` (E9+F, zero suppressions), Node suites, `d8_validate.py` exit 0
  with D8 BLOCKED / production REJECT, `.github/workflows/owned-suite.yml`
  on push + pull_request.
- Contract tests (doctype JSON, command signatures, desk audiences,
  projection allow-lists, hook wiring), lifecycle rehearsals on in-memory
  backends, mutation-checked guards (branch boundary, app assembly,
  safe extraction, restore verification), hostile-payload client tests
  (escaping, dialog signature mirroring, forbidden primitives).
- Release: every engineer-executable gap closed with hosted evidence; owner
  decision packet delivered; upstream/ops items precisely tracked; owner
  gates + deployment-scope operations remain the only outstanding classes.

## 16. Core distinctions (never collapse for convenience)

| Concept | Meaning | Example |
|---|---|---|
| **Policy carrier** | The governed structure that HOLDS policy | TH Correction Policy versions; TH Assessment Policy versions; Fee Structure |
| **Policy execution** | The guarded command that APPLIES policy to a case | `approve_invoice_correction`; `issue_tuition_fees`; `calculate_teaching_compensation` |
| **Operational fact** | The native/business record that RESULTED | Submitted Fees; Sales Invoice (incl. credit notes); Program Enrollment; Attendance |
| **Evidence** | The proof that it happened correctly | Operation receipt; hash-chained audit event; native Version row; hosted run + report hash |
| **Readiness** | The computed answer "can the next step proceed?" | Billing readiness; progression-chain integrity; `validate_*` snapshot checks |
| **Authorization** | The permission for a human/system to act | Owner GO; role gate; dual-key approver; site-mode PRODUCTION |

A receipt is not authorization. A projection is not a master. A mechanism is
not a rehearsal. A rehearsal is not gate passage. A target (RPO/RTO) is not a
measurement. Scope authorization is not production GO.

## 17. Decision classification (standing rule, adopted 2026-09-25)

Adopted verbatim as a permanent project architecture rule by direct owner
instruction on 2026-09-25. It formalizes what §§3–5, 10, 12 and 14 already
practice and what DECISION-REGISTER.md records as the OD-NEW pattern
("Mechanism SHIPPED … owner values still AWAITING ANSWER").

**Classify first.** For every decision encountered during implementation,
classify before acting:

- **A — application / technical architecture decision.** Security controls;
  authorization boundaries; concurrency and locking; audit integrity;
  historical data integrity; fail-closed behavior; native
  ERPNext/Education/HRMS integration; code architecture; test strategy;
  reliability and recovery mechanisms; technical validation and release
  gates. These are engineering decisions: make them autonomously using this
  constitution, the established safety rules, the native-first principle
  (§9) and evidence. Do NOT repeatedly ask the owner for decisions that are
  fundamentally technical.
- **B — TOEFL House business / operational management decision.** Class
  capacity; availability rules; enrollment/progression rules;
  refund/correction business policy; assessment/progression business
  policy; payroll/teacher compensation policy; tax/business policy;
  reporting definitions; backup RPO/RTO; retention/scheduling rules; other
  rules describing HOW TOEFL HOUSE chooses to operate.

**Category B handling (binding):**

- Never hard-code a Category B value as an arbitrary engineering constant.
- Whenever technically appropriate, build the ERP-native or application
  configuration/policy UX so an authorized business owner manages the value
  from inside the ERP, following the existing configuration architecture
  (§§3–5): Owner/Admin UI → versioned business configuration/policy →
  validation/readiness → effective-dated behavior → immutable historical
  reference → audit trail → operational consumers. The pattern is the
  existing `TH … Policy(+Version)` carrier: guarded Course Owner commands,
  computed readiness, mandatory change reasons, and the hash-chained
  `TH Configuration Audit Event`, with the command-context boundary of §7.
- Do NOT turn safety/security/release controls into ordinary business
  settings merely because they are configurable. §§10–15 behavior (deny
  lists, DESKs/audiences, gates, `d8_validate` guards, synthetic/prod mode)
  stays engineering-controlled; the custody authority is **never** bound to
  a Frappe role (§14) and production authorization never flows through
  configuration (§12; `configuration/audit.py` enforces this in code).
- Do NOT invent business values or defaults. If a business policy is not
  yet configured, represent it explicitly as **NOT CONFIGURED** and make
  the dependent operation fail safely where required (§10: deny, naming the
  missing configuration and the owning role).
- "Owner decision required" does NOT automatically mean "stop and ask the
  owner." First ask: can this decision be represented as a legitimate
  configurable business policy inside the ERP? If yes, implement the
  configuration mechanism and UX autonomously, without inventing the
  owner's actual value. If no — genuinely an external-authority decision,
  legal/compliance requirement, destructive migration, production
  authorization, secret/custody decision, or another true human-authority
  boundary — stop at that boundary and request the specific decision with
  exact evidence and no invented assumptions.
- Continue autonomous engineering everywhere else.

First application: the 18 standing closure-register items were re-classified
under this rule in
`docs/engineering/evidence/decision-classification-review-2026-09-25.md`;
remaining Category B surface gaps (metric stewardship, service objective,
alerting policy, guardian lifecycle policy) are ordinary build tracks, not
decision blockers.

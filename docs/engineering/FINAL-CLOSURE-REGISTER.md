# Final closure register (human-readable projection)

Date: 2026-09-19 · Active branch: `arena/01a0ba0d-tofel-house-erp` @ `523fe5e`

> Projected from `final-closure-register.json` (the machine-readable source of
> truth). Regenerate — do not hand-edit — via:
> `python3 tools/foundation/project_closure_register.py`

## IMPLEMENTABLE NOW (6)

### `obs-engineering-layer` — Actionable operational visibility inside the product (mission §7, engineering layer).

- **source:** FINAL-COMPLETION mission §7; gap map 1.6 Monitoring row
- **current_state:** Attention projections + native Error Log roundtrip, scheduler registry, health ping (R3). No health endpoint, worker-health projection, failed-job visibility, or alert-condition generator in product.
- **reason:** Actionable in-repo work; needs no owner policy or environment.
- **dependency:** None (in-repo).
- **responsible:** Engineering.
- **implementation_or_evidence_required:** Read-only health/worker/failed-job probes over native sources + alert-condition generation with documented receiver boundary.
- **acceptance_test:** Unit + hosted contract tests green for the new probes; desks surface worker/failed-job facts from native sources only.

### `broad-isolation-proofs` — Broad branch/role isolation proofs across product surfaces (mission §9).

- **source:** FINAL-COMPLETION mission §9; RELEASE-GAP-MAP.md 1.5
- **current_state:** A13 (523/523) + R3 (533/533) prove containment for implemented slices; broad matrix (branches, stale/revoked/disabled actors, job surfaces) not yet encoded as hosted checks.
- **reason:** Isolation must be proven by execution across surfaces, not asserted from source.
- **dependency:** None (hosted suite runs on push).
- **responsible:** Engineering.
- **implementation_or_evidence_required:** Extend tools/placement/native_checks.py with the §9 matrix (allow + deny paths); qualify on push-triggered hosted runs.
- **acceptance_test:** Hosted placement-content run green with new checks; two-branch/two-student/role-matrix fixtures exercised over Desk/REST/RPC/list/report/export/print/file surfaces.

### `teacher-daily-use` — Teacher daily-use path (mission §10).

- **source:** FINAL-COMPLETION mission §10; STAFF-JOURNEY-AUDIT gap 4
- **current_state:** Backend implemented (contracts, assignments, groups, schedules, attendance); no teacher-facing desk (journey gap J4). Identity chain verified native: session User → Employee.user_id → Instructor.employee → Teaching Assignment → Student Group; users outside the chain get a fail-closed empty state, no invented link.
- **reason:** Daily-use completeness for the teacher role; fail-closed on native identity.
- **dependency:** None (native identity chain; no new policy).
- **responsible:** Engineering.
- **implementation_or_evidence_required:** Teacher desk surface (My Classes → Today → Session → Attendance → Students → Academic Work → Compensation Facts) + desk contract tests incl. wrong-role refusal.
- **acceptance_test:** Teacher desk + contract tests: assigned-only classes, today/next-action clarity, empty/closed/unavailable states, finance facts clearly non-authoritative; no unrelated data reachable.

### `finance-polish` — Finance final operational polish (mission §12).

- **source:** FINAL-COMPLETION mission §12
- **current_state:** Finance desk exists as projection + command-launch surface; usability gaps listed in mission §12 unaddressed.
- **reason:** Daily-use completeness without touching native finance authority.
- **dependency:** None (in-repo).
- **responsible:** Engineering.
- **implementation_or_evidence_required:** Desk projection improvements with native-record references; contract tests.
- **acceptance_test:** Finance desk surfaces outstanding/next-action/correction-status/blocked-reason/duplicate/config-guidance/invoice-state/native-ref from facts only; contract tests green; no settlement logic added.

### `academic-setup-finalization` — Academic Setup finalization (mission §13).

- **source:** FINAL-COMPLETION mission §13
- **current_state:** Academic desk exists; completeness against the §13 question list unverified.
- **reason:** Setup transparency for daily operation.
- **dependency:** None (in-repo). D1 grading stays out.
- **responsible:** Engineering.
- **implementation_or_evidence_required:** Desk completeness pass + contract tests; D1 answers stay fail-closed placeholders.
- **acceptance_test:** Academic Setup desk answers program/levels/duration/progression/year/fee-type/fee-structure/discount/active-retired/actor/version from configuration records; contract tests green; no grading policy invented.

### `lifecycle-journey-audit` — Reception → Academic → Finance lifecycle audit (mission §11).

- **source:** FINAL-COMPLETION mission §11
- **current_state:** STAFF-JOURNEY-AUDIT-2026-09-19 covers the ordinary path on synthetic sites; no hosted click-through on a live site (journey gap J3).
- **reason:** End-to-end usability proof for the RC journey.
- **dependency:** Deployment for the click-through half.
- **responsible:** Engineering (audit) + owner (live click-through).
- **implementation_or_evidence_required:** Complete 18-step audit now; hosted click-through becomes REAL-ENVIRONMENT follow-up.
- **acceptance_test:** Journey document traces all 18 steps with source-of-truth/actor/permission/record/next/failure/audit each; hosted click-through recorded when the deployment exists.

## OWNER DECISION REQUIRED (10)

### `gate-capacity-availability` — Capacity/availability objective + measurement (D8 capacity-availability gate).

- **source:** d8-production-operations-decision-matrix.json (capacity-availability: BLOCKED)
- **current_state:** No numeric objective selected; only descriptive timings exist.
- **reason:** Measuring against an invented number would be evidence theater.
- **dependency:** Owner capacity/availability decision (D8-CAPACITY-AVAILABILITY: NOT SELECTED).
- **responsible:** Owner (objective) then engineering (measurement).
- **implementation_or_evidence_required:** Owner supplies concurrency/availability targets; engineering measures against them on the real host.
- **acceptance_test:** Owner-recorded numeric objective; only then can measurement be scheduled.

### `gate-production-authorization` — Production authorization (D8 production-authorization gate).

- **source:** d8-production-operations-decision-matrix.json (production-authorization: REJECT)
- **current_state:** Owner has not authorized production; five d8_validate.py guards keep REJECT.
- **reason:** Only the owner can accept serving real students.
- **dependency:** All blocking gates + explicit owner authorization.
- **responsible:** Owner.
- **implementation_or_evidence_required:** Owner authorization act after gates close; no engineering substitute exists.
- **acceptance_test:** Owner records production authorization in the canonical record; all blocking gates independently satisfied.

### `D1` — Academic assessment/progression policy (D1).

- **source:** canonical-owner-decision-record.json (D1: DEFER)
- **current_state:** DEFER recorded; no assessment slice built; no invented grades anywhere.
- **reason:** Grading/progression values are business policy, not engineering derivable.
- **dependency:** Owner academic policy.
- **responsible:** Owner (Academic).
- **implementation_or_evidence_required:** Closure packet delivered in this mission (§14); implementation only after owner values.
- **acceptance_test:** Owner supplies level vocabulary, rubrics, cutoffs, progression; A06 slice implemented after.

### `D3` — Exact refund/partial-refund terms (D3).

- **source:** canonical-owner-decision-record.json (D3: FRAMEWORK APPROVED / EXACT TERMS LATER)
- **current_state:** Framework shipped + qualified (T4, 539/539); full-amount placement-invoice corrections work; partials and Fees-side refused fail-closed.
- **reason:** Refund terms are business policy with financial consequences.
- **dependency:** Owner exact terms.
- **responsible:** Owner (Finance).
- **implementation_or_evidence_required:** Closure packet in this mission; enablement only after owner values.
- **acceptance_test:** Owner supplies approver/windows/partial terms; partials + Fees-side enabled after.

### `D4` — Identity/guardian lifecycle policy (D4).

- **source:** canonical-owner-decision-record.json (D4: DEFER ADVANCED POLICY)
- **current_state:** Advanced policy deferred; narrow explicit-User-Permissions remedy passes hosted (SEC-GUARDIAN-01 contained).
- **reason:** Identity/merge/guardian rules determine who may act for a learner.
- **dependency:** Owner identity policy.
- **responsible:** Owner.
- **implementation_or_evidence_required:** Closure packet in this mission; no guardian portal until policy exists.
- **acceptance_test:** Owner supplies identity/merge/guardian-delegation rules; advanced lifecycle after.

### `D5` — Calendar/repeat/transfer/withdrawal semantics (D5).

- **source:** canonical-owner-decision-record.json (D5: NATIVE BASIC LIFECYCLE / ADVANCED LATER)
- **current_state:** Native basic lifecycle used; advanced semantics deferred; no invented transfer/withdrawal engine.
- **reason:** Transfer/withdrawal semantics change learner history and billing.
- **dependency:** Owner lifecycle policy.
- **responsible:** Owner (Academic).
- **implementation_or_evidence_required:** Closure packet in this mission.
- **acceptance_test:** Owner supplies calendars/repeat/transfer/withdrawal semantics; advanced lifecycle after.

### `D6a` — Tax policy (D6a).

- **source:** canonical-owner-decision-record.json (D6a: TAX NOT CONFIGURED YET)
- **current_state:** No tax configured anywhere; no invented tax behavior.
- **reason:** Tax configuration is jurisdiction/business policy.
- **dependency:** Owner tax policy.
- **responsible:** Owner (Finance).
- **implementation_or_evidence_required:** Closure packet in this mission; native tax setup only after owner values.
- **acceptance_test:** Owner supplies tax configuration values applied to native tax masters.

### `D7` — Metric stewards/derived-metric policy (D7).

- **source:** canonical-owner-decision-record.json (D7: DEFER / RAW REPORTS NOW)
- **current_state:** R2 raw-fact registers shipped; no derived metrics, no invented denominators.
- **reason:** Derived metrics need named stewards and disclosure rules.
- **dependency:** Owner steward/policy decision.
- **responsible:** Owner.
- **implementation_or_evidence_required:** Closure packet in this mission.
- **acceptance_test:** Owner names stewards + denominator/disclosure/retention rules; metrics layer after.

### `offsite-destination` — D14 off-site destination selection.

- **source:** OWNER-DECISIONS.md (D14); LAUNCH-RUNBOOK rehearsal table
- **current_state:** D14 decided (owner-controlled off-site hardware, separate location, no third-party cloud) but no specific device/site selected — deliberately left to the owner.
- **reason:** Only the owner can choose who physically holds student data.
- **dependency:** Owner hardware/location selection.
- **responsible:** Owner.
- **implementation_or_evidence_required:** Owner names device/site; engineering rehearses encrypted copy + restore to it.
- **acceptance_test:** Owner selects off-site hardware destination + verifies physical separation.

### `key-custody-destination` — Key custody inside a real trust boundary.

- **source:** RELEASE-GAP-MAP.md 1.6 Key custody row
- **current_state:** Structural custody over artifact channels executed (P4); encryption_key_custody_reference and site_configuration_custody_reference NOT SELECTED; Actions secrets 403 to this session.
- **reason:** Executing a custody model is not an owner selection of a custody destination.
- **dependency:** Owner custody destination (KMS/HSM/owner store).
- **responsible:** Owner.
- **implementation_or_evidence_required:** Owner provisions/selects store; custody ceremony re-executed against the real boundary.
- **acceptance_test:** Owner selects key-custody destination; retrieval + rotation re-proven against it.

## EXTERNAL/UPSTREAM BLOCKED (1)

### `sec-deps-01` — Resolved dependency trees must carry no advisory match (D8-SECURITY-DEPENDENCY).

- **source:** d8-production-operations-decision-matrix.json (dependency-security: REJECT)
- **current_state:** Finding set readable and triaged (register + reachability trace, 2026-09-19). Newest Frappe v16.34.0 still pins pypdf==6.15.0, WeasyPrint==68.0, pdfkit~=1.0.0; Bench v5.31.0 still caps setuptools<82.0.0; pdfkit/weasyprint-CSS advisories list no patched version. Hosted audits fail closed (runs 35451785714, 35450528487).
- **reason:** No officially released compatible bundle clears the finding set; fixes exist on PyPI but are unreachable through reviewed Frappe/Bench inputs, and two advisories list no fix at all.
- **dependency:** Upstream releases (Frappe, Bench, pdfkit/weasyprint maintainers).
- **responsible:** Upstream maintainers; engineering re-verifies.
- **implementation_or_evidence_required:** Re-run the official-input review on every newer upstream release; construct an immutable candidate record only when one exists; never override pins.
- **acceptance_test:** A newer official release clears the pins; disposable-bench audits exit 0; native qualification + regressions green; adopted only then.

## REAL-ENVIRONMENT EVIDENCE REQUIRED (8)

### `gate-recovery` — Independent recovery proven with measured objective (D8 recovery gate).

- **source:** d8-production-operations-decision-matrix.json (recovery: BLOCKED)
- **current_state:** Destructive recovery onto a separate ephemeral VM executed (35170062251); encrypted-backup recovery with custody-held keys executed (35179445639). No rehearsal on the selected local server; no owner-selected off-site destination.
- **reason:** Recovery onto another disposable VM would be evidence theater; the gate needs the real host.
- **dependency:** D14 off-site destination selection; local server access.
- **responsible:** Owner (execution) + engineering (procedure).
- **implementation_or_evidence_required:** Owner runs LAUNCH-RUNBOOK + interim-backup restore procedure on the real server; records rehearsal row.
- **acceptance_test:** Owner-executed rehearsal on the local server with recorded date, digests, elapsed time, outcome; RPO<=24h/RTO<=8h measured.

### `gate-backup-restore` — Bounded encrypted versioned backup with proven restore (D8 backup-restore gate).

- **source:** d8-production-operations-decision-matrix.json (backup-restore: BLOCKED)
- **current_state:** Interim backup tool exists (AES-256-CBC, sha256 sidecars, different-volume refusal, retention model). Staging verify-and-decrypt exists; real-server restore not executed; backup-set rotation and recovery session-revocation unproven outside the closure harness.
- **reason:** Mechanism without a real rehearsal is not recovery evidence.
- **dependency:** Local server access; D14 destination.
- **responsible:** Owner (execution) + engineering (tooling).
- **implementation_or_evidence_required:** Real-server rehearsal; multi-set rotation record; post-recovery session/credential verification.
- **acceptance_test:** Same rehearsal row as gate-recovery plus rotation-of-sets and session-revocation behavior recorded.

### `gate-upgrade-rollback` — Safe upgrade with proven rollback (D8 upgrade-rollback gate).

- **source:** d8-production-operations-decision-matrix.json (upgrade-rollback: BLOCKED)
- **current_state:** Isolated Frappe patch upgrade qualified (33/33). No rollback rehearsal; no full-bundle (ERPNext/Education/HRMS/payments + owned app) upgrade.
- **reason:** Upgrade/rollback cannot be proven without a real bench to break and repair.
- **dependency:** Real bench environment; upstream releases.
- **responsible:** Engineering (procedure) + owner (execution window).
- **implementation_or_evidence_required:** Executable rollback procedure + rehearsal record; full-bundle upgrade plan on upstream release.
- **acceptance_test:** Rollback rehearsal recorded on a real bench; full-bundle upgrade qualified when upstream ships it.

### `obs-deployed-operation` — Deployed monitoring operation with fail-closed alerting (D8 observability gate).

- **source:** d8-production-operations-decision-matrix.json (observability: BLOCKED)
- **current_state:** No receiver, no delivery path, no retention operation, no incident runbook.
- **reason:** Alerting without a receiver is simulation; deployed behavior needs the deployment.
- **dependency:** Owner-selected receiver/infrastructure; deployed environment.
- **responsible:** Owner (receiver) + engineering (qualification).
- **implementation_or_evidence_required:** Owner selects receiver; engineering qualifies delivery + outage fail-closed + retention; incident runbook recorded.
- **acceptance_test:** Receiver configured on the deployment; delivery + fail-closed-on-outage demonstrated; retention operated.

### `gate-topology-edge-session` — TLS/session/private-file/realtime qualification on the selected edge (D8 topology-edge-session gate).

- **source:** d8-production-operations-decision-matrix.json (topology-edge-session: BLOCKED)
- **current_state:** Proven on disposable runners: CSRF token presence + 13 negatives, cross-site replay denial, private-file isolation; TLS protocol-policy probe green (38/38). Nothing evidenced on the selected Tailscale deployment.
- **reason:** Edge behavior is a property of the real deployment, not the codebase.
- **dependency:** Local server + Tailscale deployment (D15).
- **responsible:** Engineering (procedure) + owner (deployment).
- **implementation_or_evidence_required:** Owner/engineering capture of TLS + session + cookie + CSRF + private-file checks against the Tailscale URL.
- **acceptance_test:** Independent TLS/session/cookie/CSRF evidence captured on the Tailscale URL at a recorded SHA.

### `gate-durability` — Durability across host failure with measured objectives (D8 durability gate).

- **source:** d8-production-operations-decision-matrix.json (durability: BLOCKED)
- **current_state:** MariaDB/Redis durability proven on disposable runners incl. SIGKILL crash recovery (P2). Host-loss, region-loss, measured restart downtime unproven.
- **reason:** Durability is a property of the real host and its volumes.
- **dependency:** Selected local/server host.
- **responsible:** Owner (host access) + engineering (procedure).
- **implementation_or_evidence_required:** Host-level disruption rehearsal + measured recovery timings on the real server.
- **acceptance_test:** Power-loss/volume-loss/restart-downtime evidence on the selected host; RPO/RTO measured.

### `gate-change-control` — Exercised change/rollback control (D8 change-control gate).

- **source:** d8-production-operations-decision-matrix.json (change-control: BLOCKED)
- **current_state:** D8-CHANGE-ROLLBACK selected as responsibility; no exercised change path; rollback unrehearsed.
- **reason:** Change control without changes to control is prose, not evidence.
- **dependency:** Real deployment receiving changes.
- **responsible:** Owner + engineering.
- **implementation_or_evidence_required:** Change path exercised end-to-end on the deployment; rollback rehearsal record.
- **acceptance_test:** Documented promotion/approval/communication path exercised for one real change + rollback rehearsal.

### `launch-rehearsal` — D16 activation rehearsal on the selected deployment (D15 scope).

- **source:** docs/engineering/LAUNCH-RUNBOOK.md §9
- **current_state:** Runbook exists with exact commands + acceptance conditions; never executed (no server access from this environment).
- **reason:** Activation on any other machine would be evidence theater.
- **dependency:** Local server access; owner execution.
- **responsible:** Owner (runs) + engineering (runbook).
- **implementation_or_evidence_required:** Owner runs LAUNCH-RUNBOOK steps 0-9 on the local server and records the rehearsal.
- **acceptance_test:** Rehearsal table in LAUNCH-RUNBOOK filled with date/site/mode/mirror/mixed/elapsed/outcome from the local server.

## INTENTIONALLY DEFERRED (5)

### `deferred-portals` — Portals / student self-service.

- **source:** RELEASE-GAP-MAP.md 1.7; mission §15
- **current_state:** Not built; D4 advanced policy absent.
- **reason:** Candidate/guardian/student portals need identity policy first.
- **dependency:** D4 policy + future product decision.
- **responsible:** Owner (future).
- **implementation_or_evidence_required:** None in this mission.
- **acceptance_test:** No portal code, routes, or roles introduced; register + dossier keep the deferral explicit.

### `deferred-gateway` — Payment gateway integration.

- **source:** canonical-owner-decision-record.json (D6b)
- **current_state:** No online payment gateway (D6b CLOSED as none-at-launch).
- **reason:** Gateway selection is an explicit owner non-selection at launch.
- **dependency:** D6 owner gateway selection.
- **responsible:** Owner (future).
- **implementation_or_evidence_required:** None in this mission.
- **acceptance_test:** No gateway code or credentials; D6b NO-GATEWAY decision stands.

### `deferred-public-edge` — Public internet edge.

- **source:** OWNER-DECISIONS.md (D15); mission §15
- **current_state:** Local + Tailscale only; internet edge never selected.
- **reason:** Public edge explicitly out of authorized scope.
- **dependency:** None (forbidden by D15).
- **responsible:** Owner (future).
- **implementation_or_evidence_required:** None; D15 forbids.
- **acceptance_test:** No public DNS/hosting/edge configuration; D15 local-only scope honored.

### `deferred-assessment-metrics` — Official TOEFL engine / CEFR certification / BI scoring.

- **source:** RELEASE-GAP-MAP.md 1.7; mission §15
- **current_state:** Internal course mapping only; no external claims; no invented metrics.
- **reason:** External certification and derived metrics need owner stewards first.
- **dependency:** Owner policy (D1/D7) + future product decision.
- **responsible:** Owner (future).
- **implementation_or_evidence_required:** None in this mission.
- **acceptance_test:** No TOEFL/CEFR/BI/derived-metric code; R2 registers stay raw facts.

### `deferred-lifecycle-engines` — Waitlist/transfer/freeze engines.

- **source:** mission §15; canonical-owner-decision-record.json (D5)
- **current_state:** Not built.
- **reason:** Lifecycle engines need D5 semantics first.
- **dependency:** D5 policy.
- **responsible:** Owner (future).
- **implementation_or_evidence_required:** None in this mission.
- **acceptance_test:** No waitlist/transfer/freeze invented engines; transfer/withdrawal use native semantics until D5.

## CLOSED (6)

### `gates-passed` — D8 scoped PASS gates stay green.

- **source:** d8-production-operations-decision-matrix.json
- **current_state:** Proven and retained; nothing outstanding.
- **reason:** domain-qualification, authorization-isolation, realtime, ownership are PASS with hosted evidence.
- **dependency:** None.
- **responsible:** Engineering (preserve).
- **implementation_or_evidence_required:** None; preserve evidence.
- **acceptance_test:** Existing hosted proofs retained (A13 523/523, R3 533/533, realtime grep 0 emit sites, ownership charter PASS).

### `D16-closed` — D16 production activation mechanism.

- **source:** canonical-owner-decision-record.json (D16: DECIDED)
- **current_state:** Implemented, qualified (950/950 then), hosted placement runs green on D16 commits.
- **reason:** Controlled activation with fail-closed default shipped and evidenced.
- **dependency:** None.
- **responsible:** Engineering.
- **implementation_or_evidence_required:** None; preserve.
- **acceptance_test:** Retained: D16 validators + 23 activation tests + runbook; REFUSED default proven.

### `D15-closed` — D15 local-launch scope.

- **source:** canonical-owner-decision-record.json (D15: DECIDED)
- **current_state:** Decided 2026-09-19; runbook scoped to local + Tailscale.
- **reason:** Launch scope authorized and bounded.
- **dependency:** None.
- **responsible:** Owner.
- **implementation_or_evidence_required:** None; preserve.
- **acceptance_test:** Retained: scope recorded in both decision surfaces; no internet-edge work.

### `D13-D14-decisions` — D13/D14 recovery objectives and off-site class.

- **source:** canonical-owner-decision-record.json (D13/D14: DECIDED)
- **current_state:** Decided 2026-09-19; targets are targets, not measurements.
- **reason:** Objectives recorded; evidence tracked separately.
- **dependency:** None for the decisions; evidence tracked under gate-recovery/gate-backup-restore.
- **responsible:** Owner.
- **implementation_or_evidence_required:** None; preserve. Do not mistake decisions for evidence.
- **acceptance_test:** Retained: RPO 24h / RTO 8h targets; off-site hardware class; rehearsal items tracked separately.

### `earlier-decisions` — D2/D6b/D9/D10/D11/D12 dispositions.

- **source:** canonical-owner-decision-record.json; RELEASE-GAP-MAP.md §2
- **current_state:** D2 unlocked + qualified (536/536); D6b no-gateway; D9 closed at (d); D10(ii) qualified (542/542); D11 MIT tested; D12 supersession qualified.
- **reason:** Decided and, where applicable, implemented + qualified.
- **dependency:** None.
- **responsible:** Owner + engineering.
- **implementation_or_evidence_required:** None; preserve.
- **acceptance_test:** Retained: T1/T2 qualified; D6b/D9/D10/D11/D12 recorded and tested.

### `sec-deps-readability` — Readable SEC-DEPS-01 findings (owner ballot sub-ask).

- **source:** docs/engineering/evidence/sec-deps-01/
- **current_state:** 7 unique Python vulns + 97 npm entries readable with severity/fix/advice; reachability traced at pinned framework; audits still exit 1 by design.
- **reason:** The evidence-limitation sub-issue is closed; the gate stays upstream-blocked.
- **dependency:** None for readability; remediation tracked under sec-deps-01.
- **responsible:** Engineering.
- **implementation_or_evidence_required:** None; preserve. Readability is not remediation.
- **acceptance_test:** Retained: readable register + enrichment + reachability trace; gate still fails closed on counts.

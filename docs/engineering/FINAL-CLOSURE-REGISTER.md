# Final closure register (human-readable projection)

Date: 2026-09-19 · Active branch: `arena/01a0cd90-tofel-house-erp` @ `62b3c58`

> Projected from `final-closure-register.json` (the machine-readable source of
> truth). Regenerate — do not hand-edit — via:
> `python3 tools/foundation/project_closure_register.py`

## IMPLEMENTABLE NOW (0)

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

- **source:** canonical-owner-decision-record.json (D1: DEFER); mechanism verified in apps/toefl_house/toefl_house/configuration/audit.py KIND_AUTHORITY + academic doctypes; decision-classification-review-2026-09-25.md
- **current_state:** DEFER recorded. The policy mechanism already shipped: TH Assessment Policy (+ TH Assessment Policy Version) with guarded create/status/version/validate commands and seven facet setters (components, weights, pass rules, rubrics, progression, retakes, mapping) under the versioned configuration engine. No owner values have been entered; no grading/execution slice is built; no invented grades anywhere.
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

- **source:** canonical-owner-decision-record.json (D5: NATIVE BASIC LIFECYCLE / ADVANCED LATER); carriers verified in placement/enrollment/admission doctypes; decision-classification-review-2026-09-25.md
- **current_state:** Native basic lifecycle used. Policy carriers already shipped for the adjustable facets: TH Enrollment Exit Policy, TH Roster Change Policy and TH Returning Student Policy (effective-dated versions, hash-chained audit). No owner values entered for advanced semantics; no invented transfer/withdrawal engine.
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

## CLOSED (12)

### `obs-engineering-layer` — Actionable operational visibility inside the product (mission §7, engineering layer).

- **source:** FINAL-COMPLETION mission §7; gap map 1.6 Monitoring row
- **current_state:** Shipped + green: toefl_house/observability.py (summarize_snapshot, evaluate_alert_conditions; pure, no thresholds/severity/receivers) + desk/operations._system_health shared by the GM desk and owner cockpit (ping, unseen errors, failed jobs, verbatim worker states, stopped schedules, failed runs; conditions generated, never delivered). RQ reads use the native registries confined to the allow-list with a Not readable fallback (2788eda).
- **reason:** Operational visibility shipped with evidence; deployed alerting remains with obs-deployed-operation (needs a real environment).
- **dependency:** None (in-repo).
- **responsible:** Engineering.
- **implementation_or_evidence_required:** None; preserve. Evidence: hosted placement run 35466677597 @62b3c58 (574/574 pass, report 5bbf9173…fb0a); GM + owner health cells in role-desk-hosted-qualification + role-desk-observability-hosted; desk-contract health worlds + test_rq_fallback green.
- **acceptance_test:** MET 2026-09-19: contract + hosted tests green; desks surface worker/failed-job facts from native sources only, tracebacks stay on native forms.

### `gates-passed` — D8 scoped PASS gates stay green.

- **source:** d8-production-operations-decision-matrix.json
- **current_state:** Proven and retained; nothing outstanding.
- **reason:** domain-qualification, authorization-isolation, realtime, ownership are PASS with hosted evidence.
- **dependency:** None.
- **responsible:** Engineering (preserve).
- **implementation_or_evidence_required:** None; preserve evidence.
- **acceptance_test:** Existing hosted proofs retained (A13 523/523, R3 533/533, realtime grep 0 emit sites, ownership charter PASS).

### `broad-isolation-proofs` — Broad branch/role isolation proofs across product surfaces (mission §9).

- **source:** FINAL-COMPLETION mission §9; RELEASE-GAP-MAP.md 1.5
- **current_state:** desk-broad-isolation-matrix green: two branches, two students, LIST + DESK + REST + EXPORT + PRINT + REPORT + desk-RPC (7 desks x 8 logins) allow/deny cells with three asserted boundaries (desk-path UP-blindness, Student master role-wide, non-strict branchless visibility). Exact scoping proven between populated branches (9edf821); teacher identity resolves scope-exempt (4837bee); export header matched to runtime CSV (62b3c58).
- **reason:** Isolation proven by execution across surfaces, not asserted from source.
- **dependency:** None (hosted suite runs on push).
- **responsible:** Engineering.
- **implementation_or_evidence_required:** None; preserve. Evidence: hosted placement run 35466677597 @62b3c58 (574/574 pass, report 5bbf9173…fb0a); desk-broad-isolation-matrix pass with branch_groups [SYN-GRP-ISOL-A, SYN-GRP-ISOL-B] observation.
- **acceptance_test:** MET 2026-09-19: hosted placement-content run green with the S9 matrix over Desk/REST/RPC/list/report/export/print/file surfaces.

### `teacher-daily-use` — Teacher daily-use path (mission §10).

- **source:** FINAL-COMPLETION mission §10; STAFF-JOURNEY-AUDIT gap 4
- **current_state:** th-teacher-desk live for the Instructor audience (desk/teacher.py work(): classes, today, sessions/attendance, roster-only students, academic work without thresholds, compensation facts without calculation); native chain User to Employee.user_id to Instructor.employee to TH Teaching Assignment; unlinked logins get the named empty state; student identity is the learner (676d8d4); identity resolves scope-exempt under branch rules (4837bee, mutation-pinned contract test).
- **reason:** Daily-use completeness for the teacher role; fail-closed on native identity.
- **dependency:** None (native identity chain; no new policy).
- **responsible:** Engineering.
- **implementation_or_evidence_required:** None; preserve. Evidence: role-desk-teacher-hosted + teacher cells in role-desk-hosted-qualification green in hosted placement run 35466677597 @62b3c58 (574/574 pass, report 5bbf9173…fb0a); TeacherDeskWorldTests green.
- **acceptance_test:** MET 2026-09-19: assigned-only classes, today/next-action clarity, empty/closed/unavailable states, non-authoritative finance facts; no unrelated data reachable; wrong-role refusal tested.

### `finance-polish` — Finance final operational polish (mission §12).

- **source:** FINAL-COMPLETION mission §12
- **current_state:** Collected-today sums per paying-account currency (finance._summarize currency_key=paid_from_account_currency; Payment Entry carries no flat currency column at the pin, verified against the pinned schema ledger). Billing/corrections/outstanding/today/money-facts sections green in contract + hosted finance cells.
- **reason:** Daily-use completeness without touching native finance authority.
- **dependency:** None (in-repo).
- **responsible:** Engineering.
- **implementation_or_evidence_required:** None; preserve. Evidence: FinanceOutstandingWorldTests (3000.00 USD pin, mutation-verified) + finance cells in role-desk-hosted-qualification, hosted placement run 35466677597 @62b3c58 (574/574 pass, report 5bbf9173…fb0a).
- **acceptance_test:** MET 2026-09-19: outstanding/next-action/correction-status/blocked-reason/duplicate/config-guidance/invoice-state/native-ref from facts only; no settlement logic added.

### `academic-setup-finalization` — Academic Setup finalization (mission §13).

- **source:** FINAL-COMPLETION mission §13
- **current_state:** Setup desk answers programs/levels/duration/progression/year/fee-type/fee-structure/discount/active-retired/actor/version (setup.py: academic-years coverage, governing duration actor+reason, discount modified_by); grading stays the permanent D1 placeholder (no grading rules anywhere).
- **reason:** Setup transparency for daily operation.
- **dependency:** None (in-repo). D1 grading stays out.
- **responsible:** Engineering.
- **implementation_or_evidence_required:** None; preserve. Evidence: SetupDeskWorldTests (years/duration/grading/discounts) + setup cells in role-desk-hosted-qualification, hosted placement run 35466677597 @62b3c58 (574/574 pass, report 5bbf9173…fb0a).
- **acceptance_test:** MET 2026-09-19: configuration health/programs/levels/progression/fee plans/discounts/years from configuration records; D1 answers stay fail-closed placeholders.

### `lifecycle-journey-audit` — Reception → Academic → Finance lifecycle audit (mission §11).

- **source:** FINAL-COMPLETION mission §11
- **current_state:** docs/audit/LIFECYCLE-JOURNEY-AUDIT-2026-09-19.md traces the learner chain (candidate5, applicant, admission, Student, enrollment, SYN-GRP-MAIN-1/2, tuition, corrections) across 8 stages and 18 governed steps, each step carrying source-of-truth/actor/permission/record/next/failure/audit; every claim points at a check, command, or pinned behavior.
- **reason:** End-to-end usability proof for the RC journey.
- **dependency:** Deployment for the click-through half (moved to launch-rehearsal).
- **responsible:** Engineering (audit) + owner (live click-through).
- **implementation_or_evidence_required:** Audit half done; the hosted click-through on a live deployment is future work owned by launch-rehearsal (no deployment exists to click through).
- **acceptance_test:** MET 2026-09-19 for the audit half: 18 steps x 7 facets traced; click-through pending deployment (see launch-rehearsal).

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

- **source:** docs/engineering/evidence/sec-deps-01/; docs/engineering/evidence/sec-deps-01/triage-integrity-verification-2026-09-25.md
- **current_state:** 7 unique Python vulns + 97 npm entries readable with severity/fix/advice (readable-register-2026-09-19.json: pypi_unique_vulnerabilities 7, npm_entries 97); reachability traced at pinned framework; readability is preserved and this sub-issue stays closed. Two mechanism claims recorded here are now stale and are corrected rather than left standing: audit_stack.py no longer fails on counts (its own note reads 'status now depends on triage, not raw counts') and exits 0 when every finding is triaged closed, observed in run 36119457187; audit_frontend.py still exits 1 while the frontend candidate carries advisories. The release posture is unchanged: SEC-DEPS-01 stays UPSTREAM-BLOCKED / REJECT, D8 stays BLOCKED, production stays REJECT.
- **reason:** The evidence-limitation sub-issue is closed; the gate stays upstream-blocked.
- **dependency:** None for readability; remediation tracked under sec-deps-01.
- **responsible:** Engineering.
- **implementation_or_evidence_required:** None; preserve. Readability is not remediation.
- **acceptance_test:** Retained: readable register + enrichment + reachability trace, and the register still changes no gate. The gate mechanism named here when this item was closed is no longer accurate and is corrected below: audit_stack.py grades on per-finding triage disposition rather than raw advisory counts, and fails closed on any untriaged or open finding, asserted by tests/security/test_advisory_triage.py.

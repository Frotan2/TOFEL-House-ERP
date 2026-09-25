# Decision-classification review — 2026-09-25

First application of the standing rule adopted 2026-09-25
(`docs/operating-system/ARCHITECTURE-CONSTITUTION.md` §17; index entry
R-CLASSIFY in `docs/operating-system/DECISION-REGISTER.md`). Every standing
closure-register item was classified and its mechanism state verified in the
codebase, not assumed. No disposition, gate, pin or owner value changed.

## Findings (before the per-item table)

**F1 — the rule is already this architecture's own law.**
The constitution (§§3–5, 10, 12, 14) and the configuration engine encode
it: `configuration/rules.py` computes readiness from records and declares
authorities with the custody authority *never* bound to a Frappe role;
`configuration/audit.py` states in code that "no safety control or evidence
gate reads or writes this ledger; production authorization never flows
through it". The OD-NEW items in the decision register already read
"Mechanism SHIPPED … owner values still AWAITING ANSWER". Adoption
formalizes the practice; it changes no existing behavior.

**F2 — mechanism-first is already proven at least seven times**
(OD-NEW-02 posting-window, OD-NEW-04 billing timing, OD-NEW-05 roster-change
cutoff, OD-NEW-06 attendance-correction terms, OD-NEW-07 enrollment-exit
terms, OD-NEW-08 orphan-posting posture, OD-NEW-09 catalog-linkage
enforcement) — each a `TH … Policy(+Version)` carrier, guarded Course Owner
commands, hash-chained audit, owner values still awaiting answer.

**F3 — the remaining Category B gaps are exactly four surfaces.**
Verify-and-build; none is a decision blocker under the rule:

| gap | consumers today | fail-safe today |
|---|---|---|
| D7 metric stewardship/derived-metric policy surface | none (R2 raw-fact registers only; no derived metrics anywhere) | nothing derives |
| capacity/availability objective surface | descriptive timings only; no numeric objective anywhere | D8 capacity gate stays BLOCKED |
| alerting/receiver+escalation+retention policy surface | none (`observability.py` receiver boundary: "No receiver exists in this product") | conditions generated, never delivered |
| D4 guardian lifecycle policy surface | none (SEC-GUARDIAN-01 narrow explicit-User-Permissions containment only) | no guardian portal; deployment stays denied |

Each build follows the proven domain template: parent+version doctype pair,
command-context-enforced controllers, guarded whitelisted POST commands with
idempotency receipts and hash-chained audit, a fail-closed read resolver,
computed readiness, Course Owner R/W + managers read-only, contract and
pure-logic tests — and zero invented values.

**F4 — three items are NOT representable as configuration UX**, because the
rule itself names them true external-authority boundaries: production
authorization, the off-site destination selection (physical custody of
student data), and the key-custody destination selection. They stay
stop-and-ask with exact evidence — unchanged.

**F5 — the eight REAL-ENVIRONMENT items are not decisions.**
They are evidence executions on the real host (recovery, backup-restore,
upgrade-rollback, deployed observability delivery, edge/session, durability,
change-control, launch rehearsal). The rule changes nothing about them; two
of them gain a *buildable policy surface* from F3 (capacity objective,
alerting policy) while their measurement/delivery parts stay real-host. The
standing instruction to build no further backup machinery and to keep
B12/D14 values explicitly NOT_CONFIGURED remains in force.

**F6 — two register entries carried stale mechanism claims** (corrected in
the same change as this review): D1 said "no assessment slice built" while
the TH Assessment Policy carrier with 11 guarded commands exists; D5's
wording omitted the three shipped lifecycle policy carriers. The dated R4
packet `OWNER-DECISIONS.md` line "zero implementation started" for D1 is a
historical record of 2026-09-16 and stays; the living register is corrected.

## Per-item classification

| item | register disposition | class | mechanism state (verified) | under the rule |
|---|---|---|---|---|
| D1 academic assessment/progression | OWNER DECISION REQUIRED | B | EXISTS: TH Assessment Policy (+Version), 11 guarded commands (create/status/version/validate + 7 facet setters: components, weights, pass rules, rubrics, progression, retakes, mapping), computed readiness | values = owner entry; grading/execution slice not built |
| D3 refund/correction terms | OWNER DECISION REQUIRED | B | EXISTS: TH Correction Policy(+versions), correction framework (full-amount placement-invoice corrections work; partials and Fees-side refuse fail-closed), TH Adjustment Posting Policy for the posting side | exact partial terms = owner entry; fail-closed refusal is the designed NOT-CONFIGURED behavior |
| D4 guardian/identity lifecycle | OWNER DECISION REQUIRED | B (policy) + A (enforcement) | GAP: no policy carrier; narrow SEC-GUARDIAN-01 containment only | build carrier; enforcement stays engineering; no guardian portal until policy exists (unchanged) |
| D5 calendar/repeat/transfer/withdrawal semantics | OWNER DECISION REQUIRED | B | EXISTS across three carriers: TH Enrollment Exit Policy, TH Roster Change Policy, TH Returning Student Policy (effective-dated); native basic lifecycle | advanced-semantics values = owner entry; no invented engine (unchanged) |
| D6a tax policy | OWNER DECISION REQUIRED | B — realized NATIVELY | ERPNext tax configuration (Item Tax Template, Sales Taxes and Charges Template, Tax Rule) IS the ERP-native policy UX; nothing custom to build (§9 native-first) | owner configures natively; no tax configured anywhere today (unchanged) |
| D7 metric stewards/derived-metric policy | OWNER DECISION REQUIRED | B | GAP: raw-fact registers (R2) shipped; no stewardship surface; no derived metrics | build carrier (named stewards + disclosure rules); consumers refuse while unconfigured |
| gate-capacity-availability | OWNER DECISION REQUIRED | B (objective) + real-host (measurement) | GAP: descriptive timings only; no objective surface | build service-objective carrier (versioned targets); measurement against them stays REAL-ENV on the real host |
| obs-deployed-operation | REAL-ENV EVIDENCE REQUIRED | B (receiver/escalation/retention policy) + real-host (delivery) | GAP: no receiver surface; observability generates conditions, never delivers | build alerting carrier; delivery qualification stays REAL-ENV |
| gate-production-authorization | OWNER DECISION REQUIRED | EXTERNAL AUTHORITY | by design: only the owner can accept serving real students; five `d8_validate` guards keep REJECT | stop-and-ask, unchanged; never a setting (§12) |
| offsite-destination (D14 execution) | OWNER DECISION REQUIRED | EXTERNAL AUTHORITY (custody of student data) | D14 direction decided (owner-controlled off-site hardware); device/site selection is the owner's | stop-and-ask, unchanged |
| key-custody-destination | OWNER DECISION REQUIRED | EXTERNAL AUTHORITY (secret/custody) | custody authority never bound to Frappe — enforced in `configuration/rules.py` (NEVER_BOUND); ceremonies outside Frappe; Actions secrets remain ENVIRONMENT-BLOCKED | stop-and-ask, unchanged; never a setting (§14) |
| gate-recovery | REAL-ENV EVIDENCE REQUIRED | real-host evidence | disposable-VM recoveries proven (35170062251, 35179445639) | unchanged: LAUNCH-RUNBOOK rehearsal on the real server |
| gate-backup-restore | REAL-ENV EVIDENCE REQUIRED | real-host evidence | interim tool exists; real-server restore not executed | unchanged; no new backup machinery (standing instruction) |
| gate-upgrade-rollback | REAL-ENV EVIDENCE REQUIRED | real-host evidence | isolated patch upgrade 33/33 qualified | unchanged: rollback rehearsal + full-bundle upgrade on real bench |
| gate-topology-edge-session | REAL-ENV EVIDENCE REQUIRED | real-host evidence | runner-side TLS protocol policy 38/38 green | unchanged: capture on the selected Tailscale deployment |
| gate-durability | REAL-ENV EVIDENCE REQUIRED | real-host evidence | SIGKILL crash recovery proven on disposable runners (P2) | unchanged: host-level disruption rehearsal |
| gate-change-control | REAL-ENV EVIDENCE REQUIRED | real-host evidence | responsibility selected; no exercised path | unchanged: exercise end-to-end on the deployment |
| launch-rehearsal | REAL-ENV EVIDENCE REQUIRED | real-host evidence | runbook complete, never executed | unchanged: owner execution on the selected server |

## Consequences

- Work looks different from here on: the four F3 surfaces become ordinary
  build tracks executed autonomously (template above); the three F4
  boundaries stay with the owner; the eight F5 evidence items wait on the
  owner host. Nothing on this list invents an owner value, weakens a gate,
  or converts a safety control into a setting.
- The closure register's factual claims were corrected where stale (D1, D5
  mechanism presence); dispositions are unchanged — no owner value exists
  yet, so "OWNER DECISION REQUIRED" remains literally true for the *value*
  dimension even where the mechanism shipped.

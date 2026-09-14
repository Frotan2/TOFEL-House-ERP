# Placement — approved business-policy baseline and implementation prerequisites

Date: 2026-09-14 · Repository baseline: `b9e5cf274dc7c9fe03ab3ebe093d13216fc43bc6`

**F01–F05: APPROVED by the user's explicit instruction. Implementation authorization: NOT GRANTED. Implementation-entry readiness: NOT YET CLEARED. Production: REJECT.**

This is the current approval record for [PLACEMENT-FINAL-APPROVAL.md](PLACEMENT-FINAL-APPROVAL.md). It closes that business-choice questionnaire, not outstanding policy artifacts, empirical validation or technical proof. The [multi-mode architecture](PLACEMENT-ASSESSMENT-MODEL.md) remains the design boundary. Earlier proposal/source-review metadata is historical and is not retroactively rewritten as runtime or approval evidence.

## 1. Approved baseline — no repeat approval requested

| Decision | Approved policy |
|---|---|
| **F01 — Academic placement** | Placement uses actual TOEFL House course prerequisites and evidence-based academic rules. No universal percentage cutoff, invented level ladder or automatic admission/enrollment. **Academic / Academic Affairs Manager** owns final course mapping and decision rules. |
| **F02 — Delivery and duration** | No assumed 16+ restriction. Support supervised digital, physical and hybrid delivery; remote deferred. **120-minute appointment / 90-minute active-work target** is an initial operational specification subject to trial and academic review, not a validated duration or fixed section split. Needs-based accommodations remain available. |
| **F03 — Learner entitlements** | **90-day validity**, **14-day ordinary retest wait**, no hard attempt-count cap; targeted reassessment normally within **seven days** and ordinary appeals within **seven days**, with documented exceptions. Latest valid released result governs, not the highest score. |
| **F04 — Review and release** | Assessor calibration; second review for consequential concerns; **one-in-five independent routine speaking/writing review**; independent release. **Two-working-day ordinary release** and **five-working-day appeal-response** targets. Unresolved evidence or conflicts cannot be waived to meet a target. |
| **F05 — Evidence and privacy** | Optional **audio-only speaking recording with a live alternative**; **90-day audio**, **180-day non-audio raw-evidence**, and **three-year result/necessary-audit retention**, subject to lawful holds and applicable legal/privacy rules defined by the Records/Privacy Owner. No blanket authorization to collect live personal data. |

The user approved F01–F05 **as proposed**. Preserve the event anchors and safeguards in the final approval document: validity runs from assessment completion; appeals from release; audio/raw-evidence retention from release; result/audit retention from the last substantive release or case closure, whichever is later. Abandoned/voided evidence has a 90-day closure-based period. Incidental reads/edits do not restart retention. Holds require recorded authority and review. A newer unfinished/invalid attempt does not silently replace a valid released result.

Also preserve documented interruption remedies, fresh/compatible evidence requirements for partial reassessment, independent speaking evidence where no recording exists, and no routine video/biometrics/marketing/model-training reuse. The earlier 70% / 3-of-4 routing, 16+ cutoff, hard retake-count cap, five-minute interruption cutoff and automatic 25% accommodation rule remain withdrawn. The earlier item counts and exact section minutes are **not** adopted by this approval.

Organizational ownership is unchanged:

- **Academic Owner:** Academic / Academic Affairs Manager.
- **Identity Owner:** Admissions & Student Records Manager.
- **Records/Privacy Owner:** Administration / Records & Privacy Officer.

No personal names are needed at this gate. Actual operational actions will require authenticated individual assignments and auditable delegation; organizational ownership is not a shared account or automatic permission grant.

## 2. Remaining policy prerequisites — deliverables under approved authority

These are not new F01–F05 votes. Owners may provide existing approved policies where suitable. Delegation does not supply missing facts or rules.

| ID | Required artifact | Accountable owner | Why needed before affected implementation authorization |
|---|---|---|---|
| **P1 — Curriculum and decision mapping** | Actual native Program/Course catalog and internal labels; prerequisite skills; task/rubric benchmarks; course-specific decision, uncertainty, support and reassessment rules; version and approval. | Academic Owner | No universal fallback score or fabricated catalog can stand in for recommendation logic. Numeric thresholds, if used, need academic justification and validation before consequential use. |
| **P2 — Instrument and population** | Actual initial age groups; age-appropriate content/blueprints; section quotas, timings, playback/navigation, rubrics/partial-credit and completeness rules; accommodation/mode-transition procedures; validation plan. | Academic Owner, with Identity/Records Owners for population and authority | “No 16+ restriction” does not identify the center's actual learner population. The 90-minute target does not settle section limits, question counts or construct equivalence. Unvalidated values remain clearly designated trial parameters. |
| **P3 — Identity and guardian authority** | Accepted identity evidence and ambiguous-match procedure; lawful guardian/delegate scope; candidate-account/contact arrangements, including no-ID/no-unique-email cases; supported physical alternative and revocation process. | Identity Owner with Records/Privacy Owner | Digital candidate access cannot be inferred from Student/Guardian permissions, shared contacts or a staff session. No fabricated identity/email or fake Student is permitted. |
| **P4 — Operational decision procedures** | Qualified-assessor/calibration criteria; role-level scoring/review/release/exception matrix; routine sampling procedure; unrecorded-speaking second-evidence procedure; working-day calendar; retest/partial-evidence freshness, interruption and appeal handling. | Academic Owner; other owners for their authorities | Implements the approved rates/rights without inventing delegation, sample selection, expiry anchors or exception authority. No individual-name prerequisite. |
| **P5 — Lawful evidence and retention** | Applicable jurisdiction; population/age authority rules; notices/lawful bases and recording/live alternatives; access/disclosure and rights handling; content/media licenses; hold/release/closure and deletion procedures, including backups and restored copies. | Records/Privacy Owner | Approved retention periods are institutional policy, not proof of legal compliance or permission to use copyrighted content. Any conflict requires an explicit lawful policy revision, not silent override or indefinite retention. |

Owner sign-off must identify version, scope and effective rules. For unresolved workflow-critical content, hold the affected implementation request. Policies for payroll, tuition, enrollment changes and academic grading are not prerequisites for unrelated placement work and remain outside this slice.

## 3. Technical prerequisites and proof obligations

**Before requesting implementation authorization:** produce a bounded, documentation-only technical specification and acceptance plan using exact pinned native source. Confirm supported extension behavior wherever the design depends on it. Record each uncertainty and its resolution; if source cannot establish a critical behavior, request a separately authorized isolated investigation rather than assume compatibility or execute code under this gate.

| Area | Required before authorization request | Proof required after separately authorized implementation, before acceptance/use |
|---|---|---|
| **Native ownership and candidate identity** | Logical entity/cardinality map; verified Lead/Applicant/returning-Student linkage; minimal native User/account path; explicit exclusion of enrollment, academic results, finance and payroll writes. | No fake Student/Enrollment prerequisite; no duplicate native masters or excluded side effects; correct actor/subject links and candidate isolation. |
| **Bank and form allocation** | Version/approval boundaries; taxonomy and stimulus-family dependencies; quota/difficulty/mark/time constraints; exposure reservation, retake exclusion and shortage rules; protected reproducibility manifest. | Feasible balanced allocations, no key leakage, no reroll on retry, concurrent exposure/capacity safety, deterministic replay from the frozen manifest, fail-closed shortage handling and realistic bank/load behavior. |
| **Scoring and evidence** | Objective answer/partial-credit contracts; human rubric/review separation; immutable response/score versions; handling of incomplete/corrupt evidence and uncertain recommendations. | Correct scoring and rounding; missing is not zero; reproducible corrections; all six skills represented; no official-score/academic-result output; no release before required evidence/moderation. |
| **Delivery, timing and incidents** | Digital/physical/hybrid session boundaries, server timing, approved pause/resume/replacement rules, accessibility constraints, print/script custody and media lifecycle. | Deadline/retry/late-upload cases, concurrent sessions, outages and mode changes preserve evidence; physical timing remains honestly invigilator-attested; accommodations do not silently change constructs. |
| **Authorization and alternate writers** | Exact native writer/extension inventory for CRUD/RPC/import/jobs/cancel/files/print/export/reports/realtime; trusted actor, subject, assignment, state and field predicates; composition with existing guards. | Cross-candidate/role/site denials, revocation, key/media protection, native-route bypass containment and independent release. UI-only controls or wrappers are insufficient; existing guards do not prove new parent/session coverage. |
| **Transactions, history and privacy** | Transaction/commit boundaries, stable idempotency and locking strategy, correction/compensation, retention/hold/deletion and backup-restoration design; migration/reversibility plan. | Duplicate/stale/concurrent/partial-failure recovery; no silent history rewrite; lawful hold/deletion behavior across evidence and restored backups; qualified audit and report access. |

Engineering—not the user—chooses algorithms, supported hooks, minimal physical records and test mechanisms within the unchanged foundation. Test fixtures may use synthetic users and policies explicitly marked non-operational; fixture values cannot become business defaults. Actual runtime proof cannot exist for an unimplemented slice: a plan is required before authorization, executed evidence is a later acceptance gate. No existing failed evidence is waived or relabeled.

## 4. Gate status and next action

| Gate | Current state |
|---|---|
| F01–F05 institutional approval | **CLOSED / APPROVED** by the user's instruction |
| Applicable owner artifacts P1–P5 | **OUTSTANDING**; none is assumed supplied by approval |
| Bounded technical specification / native compatibility review / acceptance plan | **PENDING** for the approved multi-mode scope |
| Implementation authorization | **NOT GRANTED**; requires a subsequent explicit instruction after applicable prerequisites are reconciled |
| Empirical assessment validation | **NOT CLAIMED**; trials and course-fit evidence required before consequential use; live trials need separate data/operational authorization |
| Implemented-domain runtime acceptance | **NOT EXECUTED**; hosted reproducible evidence on exact candidate artifacts required later |
| Deployment and production | **BLOCKED / REJECT**; unchanged Phase 2 and later domain/operational gates apply |

**Next permissible work:** assemble P1–P5 through the organizational owners and prepare the bounded technical specification, native-source compatibility findings and acceptance matrix as documentation. Report unresolved prerequisites by workflow; then present a scoped implementation-authorization request. Do not ask the user to reapprove F01–F05 or provide individual owner names.

The whole-domain A02/A03/A04/A06/A13 conditional records are not automatically closed by narrower business approval; their remaining native/policy proof still applies. A05/A09/A11 remain blocked for their separate repeat/payroll/cancellation capabilities. This gate grants neither blanket architecture sign-off nor production approval.

**Change boundary:** documentation only. No code, schema, API, UI, dependency, foundation pin, upstream source, deployment configuration or infrastructure change; no runtime tests or deployment action. Earlier source hashes and Phase 2 evidence remain immutable historical records, not certification of this new document.

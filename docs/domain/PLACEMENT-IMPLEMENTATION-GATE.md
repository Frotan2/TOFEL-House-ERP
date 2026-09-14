# Placement-first implementation-entry gate

> **Placement scope revision:** [PLACEMENT-ASSESSMENT-MODEL.md](PLACEMENT-ASSESSMENT-MODEL.md)
> is the current authoritative placement design: governed question bank, blueprint-based
> randomized forms, six-skill automatic/manual assessment and digital/physical/hybrid delivery.
> It supersedes earlier staff-assisted-only/assessor-led-only scope and blanket exclusions
> of objective-bank delivery or digital speaking evidence. Recording permissions and
> operational policies remain conditional; R03 organizational owners and other domain
> boundaries are unchanged. Earlier approval/checklist text below is historical where
> it conflicts. No implementation authorization or production approval is granted.


Date: 2026-09-14 · Review baseline: `6e6f6c4c85c50025b4128e4377ecf116e06a9956`

**Prior gate business direction: APPROVED for R01, R02, R03 and R07; delivery/method/evidence scope subsequently revised. Implementation: NOT AUTHORIZED. Entry gate: NOT YET CLEARED. Production: REJECT.**

This records the user's instruction to proceed with the approved policy direction and use organizational accountable owners, not individual names. It governs the current placement-first approval/blocker checklist, alongside [BUSINESS-DECISION-RESOLUTION.md](BUSINESS-DECISION-RESOLUTION.md). It does not replace [DOMAIN-CONTRACT.md](DOMAIN-CONTRACT.md), change A01–A13 architecture statuses, grant blanket architecture sign-off or close native/Phase 2 proof gates.

## 1. Approved direction — do not reopen these choices

| Decision | Approved scope/direction | Still not supplied by direction approval |
|---|---|---|
| **R01** | Staff-assisted placement; staff verify identity and refer disputed matches to the Identity Owner. No applicant/guardian portal or offline synchronization. | Accepted identity evidence and dispute-handling procedure. Student email/mailbox policy is deferred because conversion is excluded. |
| **R02** | Assessor-led internal English-level assessment, component evidence, appropriate course/level recommendation and rationale; no mandatory overall score. Most recent reviewed, valid, explicitly released decision is effective; preserve all earlier attempts. | Actual levels/course mappings, rubrics, validity and operating rules listed below. No numeric thresholds or official exam scales are implied. |
| **R03** | Organizational accountable owners as listed in §2, with bounded delegation and required approval separation. | Operational delegation limits and procedures, not individual names. |
| **R07** | Staff-assisted service for the actual learner population; verified guardian/delegate authority where required; minimum necessary evidence; no routine audio/video recording or pre-admission proxy portal. | Whether the actual initial population includes adults, minors or both; applicable age/authority, privacy and retention rules. Approval does not invent these facts or select an adult-only restriction. |

Placement is an **internal entrance/current-English-level determination before enrollment**, not an official or mock TOEFL performance score, academic assessment or CEFR certification. Approval of the no-routine-recording direction does not authorize collecting real learner data now.

## 2. Approved accountable roles

| Responsibility | Exact organizational role | Placement-slice accountability |
|---|---|---|
| Academic Owner | **Academic / Academic Affairs Manager** | Approve placement policy, level/course mappings, assessor/reviewer eligibility, release and academic review/appeal rules. |
| Identity Owner | **Admissions & Student Records Manager** | Approve identity evidence, resolve disputed person matches and govern verified prospect/applicant provenance. No automatic merges based on shared contact details. |
| Records/Privacy Owner | **Administration / Records & Privacy Officer** | Approve population/delegation evidence, lawful collection/disclosure, rights handling, retention and content-use rules. |

These are business responsibilities, **not newly created Frappe roles or shared login accounts**. Individual assignment/deputies can be configured later without changing the domain architecture. No individual names are an entry requirement for design or implementation authorization. Before operational use, actions must nevertheless resolve to authenticated, authorized individuals with auditable assignments; vacant authority or an unresolved conflict cannot imply approval. Preserve separation and use another qualified authorized reviewer when the actor is conflicted.

## 3. Remaining policy blockers — owned deliverables, not repeated votes

Each policy must identify its version, effective scope and approval by its accountable organizational role. Existing approved center policies may satisfy these deliverables. Delegation is approved; missing policy content is not.

| ID | Required policy deliverable | Accountable role | Blocks |
|---|---|---|---|
| **P01** | Internal English-level vocabulary; actual Program/Course/level mapping; assessed components, tasks/rubrics, completeness and recommendation criteria. Any numeric units/thresholds must be explicit, not assumed. Use owned/licensed content. | Academic Owner; Records/Privacy Owner confirms content rights | Assessment configuration, marking and valid course recommendations. |
| **P02** | Assessor/reviewer eligibility, release/delegation limits, conflicts and moderation; result validity; retest eligibility/wait; handling of interruptions, no-shows, accommodations and appeals. Define when an earlier result becomes superseded/revoked and how an unreleased newer attempt affects validity; retain history. | Academic Owner | Attempt/review/release/retest transitions. The latest-valid-released selection direction is already approved, not an open choice. |
| **P03** | Accepted person-verification evidence, ambiguous-match escalation, authority to confirm/correct links and permitted correction procedure. No fabricated identity or destructive merge shortcut. | Identity Owner, with Records/Privacy Owner for evidence minimization | Subject matching and identity-related access. No Student conversion or mailbox provisioning in this slice. |
| **P04** | Confirm initial adult/minor population; applicable jurisdiction and age/guardian/delegation evidence; collection notices/legal bases, sensitive disclosures, retention/legal holds, access/correction/export/deletion handling and permitted assessment-content use. No routine recordings. | Records/Privacy Owner | Affected identity/evidence/access/retention behavior. Minor-specific operations stay unavailable until lawful authority rules exist; this is not an assumed adult-only business policy. |
| **P05** | A short role-level authority matrix: who may assess, review, release, correct, resolve identity disputes and disclose records; delegation scope, escalation and absence/conflict handling. No personal names or new technical permission scheme required at this gate. | All three owners for their respective responsibilities | Authorization and approval-transition acceptance criteria. |

**Policy gate rule:** no affected workflow implementation is authorized while its required policy is absent. Preparation of the bounded technical design and synthetic acceptance scenarios may continue as documentation only. There is no requirement to resolve payroll, tuition, admission offers or academic grading before unrelated placement work.

## 4. Candidate implementation slice — prepared, not authorized

**In scope after a separate authorization:** staff-assisted prospect/applicant-linked placement; approved policy references; attempts and component observations; assigned assessment/review; released internal level/course recommendation; preserved retests/revisions; restricted evidence and separately grained placement reporting. References to real Programs/Courses support recommendations but do not create curriculum or enrollments.

**Excluded:** Student/User/Customer conversion or provisioning; admission/enrollment execution and roster changes; academic Assessment Result writes; charging/refunds/payroll; objective item-bank expansion without approved need; official/mock TOEFL or CEFR outputs; routine recordings; public learner/guardian delivery; offline synchronization; real-data pilot and production deployment. R04–R06 and their affected A05/A09/A11 capabilities remain deferred/blocked, not approved by this slice.

Engineering must provide a **documentation-only slice design** before an implementation request: minimum logical records versus native reuse, command/state boundaries, role-level permissions and field/evidence visibility, supported extension points/native writer inventory, retry/concurrency and historical correction behavior, migration/reversibility considerations and a hosted acceptance plan. These are professional engineering decisions, not new business votes. No schema, API or application is created at this gate.

## 5. Implementation-entry checklist

| Gate | Current state | Evidence required to clear |
|---|---|---|
| Approved direction and organizational ownership | **RECORDED** | This user-approved scope and the three exact role titles; no personal-name prerequisite. |
| Applicable policy content | **WAITING — P01–P05** | Versioned, role-approved policy deliverables covering the proposed workflow. |
| Bounded engineering design and acceptance plan | **PENDING** | Reviewed minimal slice specification, supported native integration/containment plan and test/recovery matrix. Resolve uncertain extension behavior before relying on it; any executable investigation needs separate authorization. |
| Explicit implementation authorization | **NOT GRANTED** | A subsequent user instruction approving the reconciled, bounded slice and an isolated synthetic-data environment; not inferred from this policy approval. |
| Implemented-domain qualification | **NOT EXECUTED; later acceptance gate** | Hosted reproducible evidence on exact candidate artifacts after separately authorized implementation. A test plan is not a pass. |
| Deployment/production acceptance | **BLOCKED / REJECT** | Separate closure of applicable Phase 2 and domain/operational gates. No risk waiver or production authorization. |

Required future acceptance coverage: no fake Student/Enrollment prerequisite; no admission, academic, finance or official-score writes; valid level/course evidence and reviewer rationale; retained attempts and effective-result rules; role/subject/assignment access and revocation across native UI/RPC/REST/import/jobs/files/reports/exports/realtime; alternate-writer containment; duplicate/stale/concurrent request and partial-failure recovery; preservation and reconciliation of historic evidence. Exercise only routes relevant to this slice while proving excluded effects cannot be triggered through it. Do not weaken existing global guards or claim a wrapper alone protects native routes.

**Next action:** obtain P01–P05 through the organizational owners and prepare/review the bounded technical design. Then submit the reconciled implementation authorization request. No further choice of owner names is needed now. Missing institutional rules and native proof obligations remain visible rather than silently replaced by defaults.

## 6. Change and evidence boundary

This gate changes domain documentation only. Earlier architecture-review JSON and source hashes describe their historical snapshots; they are not retroactively relabeled as verification of this gate. A02/A03/A04/A06/A13 remain CONDITIONAL as whole-domain records, and A05/A09/A11 remain BLOCKED for their recorded capabilities. The approved narrower business direction resolves questions, not implementation or runtime behavior.

Foundation, pins, upstream/application source, schema, APIs, UI, dependencies, deployment configuration, main and retained Phase 2 evidence remain unchanged. No runtime tests, infrastructure actions or implementation are performed. Business-direction approval is not blanket architecture approval, technical readiness or production acceptance.

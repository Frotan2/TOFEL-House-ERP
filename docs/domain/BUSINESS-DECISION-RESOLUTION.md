# Phase 3 — minimum business decision set

Date: 2026-09-14 · Baseline: `c11c9a6baac1f6fba692dfe13bd4fb53a4136823`

**Current status: R01/R02/R03/R07 policy direction APPROVED; remaining policy detail and implementation entry NOT CLEARED. No implementation authorized. Production: REJECT.**

The current approval record, exact organizational owner roles, outstanding policy blockers and next gate are in [PLACEMENT-IMPLEMENTATION-GATE.md](PLACEMENT-IMPLEMENTATION-GATE.md). That record supersedes the original approval prompts below for the initial slice. No individual owner names are required at this stage; individual assignments can be configured later without changing the domain architecture.

This is the authoritative **business-question list** for this gate. It consolidates B01–B13 from [IMPLEMENTATION-READINESS.md](IMPLEMENTATION-READINESS.md), using [ARCHITECTURE-DECISIONS.md](ARCHITECTURE-DECISIONS.md) and [DOMAIN-CONTRACT.md](DOMAIN-CONTRACT.md). It supersedes the earlier questionnaire, not the architecture contract, recorded A statuses or proof requirements. The original alternatives below remain rationale/history; approval applies only to the direction explicitly recorded in the current gate, not unsupplied policy values or later slices.

## 1. Minimum gate, not thirteen independent approvals

**Seven decision topics cover the full domain. Four initial-slice directions are now approved; their detailed policy deliverables remain outstanding.** Do not delay internal placement for payroll rules, or interpret placement approval as permission to implement payroll.

**Recommended first slice:** staff-assisted internal placement, from native prospect/applicant reference through preserved attempts and reviewed English-level/course recommendation. Exclude Student conversion, admission/enrollment execution, charging, payroll, public applicant/guardian portals and offline synchronization. These exclusions are included in the approved initial-slice direction.

Before that slice: complete the P01–P05 policy deliverables in the current gate under **R01, the placement part of R02, placement authority in R03, and R07**. Then separately authorize a bounded implementation after its engineering design is reviewed. Use synthetic data in an isolated environment; no live-data pilot is implied. R04–R06 and academic/admission extensions of R02/R03 remain gates for their respective later slices.

Approval of a policy owner is acceptable delegation, **not resolution of missing policy values**. An affected workflow stays blocked until the owner supplies and approves the actual rules. Existing policies may be provided instead of answering a new questionnaire.

## 2. Decision rationale and original approval prompts

### R01 — How should learners enter the service?

**Business choice:** staff-assisted entry first, or learner/guardian online service from the outset? This affects support workload, identity verification and who can operate without email. **Covers B01/B11 and the operational part of A02–A04.**

- **Staff-assisted first:** fastest bounded scope; staff verifies the person and records assessment evidence. No applicant login/recovery or pre-admission proxy portal is needed. It does **not** solve the native Student email requirement when conversion is later added.
- **Online first:** more learner convenience, but requires verified account claims, recovery, guardian delegation and additional security/accessibility qualification before that service can be delivered.

**Recommendation:** staff-assisted first, online and offline synchronization deferred. Use verified native identities; disputed identity matches go to an authorized reviewer, never automatic merging by shared phone/email. Distinct accounts for incompatible staff/Student/Guardian privileges are a security-derived requirement, not a vote on whether to weaken the guard.

**Exact decision from you:** approve the recommended first-slice scope, or identify the online/offline service that is essential now. Approve staff verification with disputed matches referred to the R03 identity owner, who must document the accepted evidence. **Before Student conversion only:** confirm whether the center can operate legitimate individual managed mailboxes for learners without usable unique email; otherwise conversion for those learners must remain unavailable. No fabricated addresses or required-field relaxation.

### R02 — What constitutes a valid placement and academic outcome?

**Business choice:** how the center judges current English level, recommends a course, handles another attempt, and separately judges learning after enrollment. **Covers B04/B05 and A06; placement-retake policy also supports A05.**

- **Assessor-led placement:** approved interview/tasks and component rubrics with a reviewed recommendation; lower item-bank complexity, greater dependence on assessor calibration.
- **Mixed placement:** approved objective components plus human review; potentially more consistent component scoring, but adds item/key governance and marking/security work. It still needs an internal level policy.

**Recommendation:** assessor-led first, with short reading/writing/listening evidence where the academic lead finds it useful. Record component observations, current internal level, course recommendation and rationale; no forced overall total. Add objective scoring only for a demonstrated need. Prefer the most recent **reviewed, valid, explicitly released** decision as the effective recommendation, not the highest historical score; preserve every earlier attempt. The user has approved this selection direction; detailed validity and transition rules remain Academic Owner deliverables.

**Exact decision from you:** approve assessor-led first or specify necessary objective components; approve/delegate to the Academic Owner organizational role a versioned placement policy containing actual internal levels, course mappings, components/rubrics, release/moderation rules, validity, retest eligibility/wait, interrupted attempts, accommodations and appeals. Supply existing rules if available; none of these values can be inferred from the center's name. **Before academic assessment/progression implementation:** separately approve native course grading, weights, pass/completion criteria and correction rules. Placement thresholds cannot substitute for them.

### R03 — Who is accountable for decisions and offers?

**Business choice:** centralized sign-off or explicit delegated authority, and what admission promises the center makes. **Covers B06/B10, ownership parts of B01/B04/B07/B08/B09/B12, A10/A12 and the business side of A13.**

- **Centralized:** an academic lead reviews placement release and designated managers approve admissions/financial exceptions; clearer oversight but greater bottlenecks.
- **Delegated:** named qualified reviewers and admissions staff act within documented limits; faster service, but requires training, deputies and escalation rules.

**Approved initial-slice direction:** organizational domain owners with bounded delegation and independent review for conflicts, corrections and exceptions; preserve the contract's required approval separation. The academic owner governs levels/grades, admissions governs eligibility/offers, finance governs charges/refunds, HR/payroll governs payable work, and the records owner governs disclosures. Do not invent a manager for every technical operation or require you to approve database roles.

**Recorded R03 approval:** Academic Owner — **Academic / Academic Affairs Manager**; Identity Owner — **Admissions & Student Records Manager**; Records/Privacy Owner — **Administration / Records & Privacy Officer**. These are organizational responsibilities, not individual names. A concise role-level authority/delegation matrix for placement release, identity disputes and records access remains a policy deliverable. **Before admission execution:** have the admissions owner approve eligibility/prerequisites, offer conditions, acceptance evidence and expiry. A valid internal placement remains required for initial entry; finance or an external score cannot silently exempt it. Individual assignments can be configured later without changing the domain architecture; they are not a current design/implementation-entry blocker. Actual delegation limits still require organizational policy, and operational actions require auditable individual authorization.

### R04 — What do a repeat, transfer and withdrawal mean commercially and academically?

**Business choice:** operate genuine scheduled intakes, or require independent overlapping/same-term repetitions; decide whether a transfer continues the same learning commitment or begins a new one. **Covers B03, withdrawal aspects of B07, A05/A11.**

- **Real intake periods; continued participation where appropriate:** simpler enrollment/calendar model. A new independent repeat normally belongs to a genuinely new intake; moving groups may continue the original enrollment only if native behavior safely preserves history.
- **Independent repeat in the same period:** supports a more flexible service, but the pinned native enrollment uniqueness rule cannot simply represent another identical student/program/year/term registration. This requirement remains a technical blocker, not permission for fake terms or destructive cancellation.

**Recommendation:** real published intakes; prospective withdrawal/transfer with earned history retained. Distinguish changing a class time from buying another course attempt. Never cancel old records merely to free an enrollment key.

**Exact decision from you, before enrollment/change implementation:** supply the actual intake/calendar model and confirm whether independent same-term repeats are essential. Approve whether each transfer/repeat continues the original learning/fee obligation or creates a new one, its effective date, and treatment of earned work. Refund amounts belong to R05, not a second policy here. Even approval leaves A05/A11 blocked until safe native representation and history/recovery behavior are proven.

### R05 — When does the center charge, grant credit and refund?

**Business choice:** payment clearance before participation versus installments/approved credit, and the learner's financial rights on changes. **Covers B07 and policy dependencies of A08/A10/A11.**

- **Payment-first:** simpler clearance and lower collection exposure; less affordable/flexible for some learners. Any pre-invoice deposit must use legitimate native Customer advance semantics.
- **Installments/approved credit:** more accessible, but creates receivable risk, approval limits, collection and exception workload.

**Recommendation:** a published course price/deposit/installment schedule, with credit and discounts only within finance-approved limits—not unrestricted discretionary promises. Keep payment and academic approval separate. Retain the already selected enrollment-generated tuition invoice route; do not ask you to choose competing technical billing producers again.

**Exact decision from you, before charging or financial enrollment clearance:** approve/delegate a finance policy naming the actual legal entity, applicable jurisdiction, currencies/taxes/fiscal rules, prices, payment/credit limits, aid authority, payer relationships, and withdrawal/transfer/refund terms. Explicitly state whether placement is free or charged; if charged, its price/waiver rule. An isolated uncharged placement slice does not establish a center-wide free-placement policy.

### R06 — What work are teachers contractually paid for?

**Business choice:** salary, approved hours/sessions, or genuine contracted services—not which payroll DocType to use. **Covers B08 and A09.**

- **Salary:** predictable pay and preparation/continuity coverage; teaching-session counts are not automatic deductions.
- **Hourly/session employee pay:** variable teaching-load alignment; requires precise rules for preparation, substitutions, canceled classes, leave and overtime.
- **Genuine supplier contractor:** purchasing/payment rather than employee payroll; valid only where the actual relationship and applicable law support that classification. It is not a shortcut around employment obligations.

**Recommendation:** honor actual contracts. For new regular core teaching appointments, favor salary with explicit workload expectations; use variable pay for genuinely variable assignments where legally appropriate. A language-center label does not establish existing employment terms or jurisdiction.

**Exact decision from you, before workforce/pay input implementation:** provide/approve classification and pay basis per teacher cohort, payable-work and cancellation rules, period/rate/currency and statutory obligations, with an accountable payroll owner. A09 remains blocked until engineering qualifies one native input path per pay basis and proves reconciliation; you are not asked to choose Timesheet versus Additional Salary by intuition.

### R07 — Whose information may the center collect and disclose?

**Business choice:** serve minors/proxies in the initial scope or defer those cases, and retain written assessment evidence only or recordings as well. **Covers B02/B09, guardian aspects of A03 and privacy dependencies of A02/A06/A12/A13.**

- **Staff-assisted adult and minor intake with verified delegation:** inclusive, but requires an approved age/authority rule and evidence of who may act for or receive information about a learner. Payer/contact status alone grants no access.
- **Adult-only initial scope:** fewer proxy cases, but excludes younger learners; choose only if operationally acceptable, not as an assumed demographic fact.
- **Written component evidence only versus recordings:** written evidence reduces sensitive storage; recordings may assist moderation/appeals but add consent/legal-basis, access, retention and content-rights obligations. This is a separate collection choice, not a consequence of admitting minors.

**Recommendation:** staff-assisted intake for the actual learner population, verified guardian/delegate authority where required, no pre-admission proxy portal, and no routine audio/video recording initially. Keep the minimum evidence needed to explain and review a recommendation; use owned/licensed assessment content only.

**Exact decision from you:** confirm whether the first slice serves adults, minors or both; approve the no-routine-recording recommendation or justify required recordings. The approved Records/Privacy Owner organizational role must approve applicable jurisdiction, age/delegation and evidence rules, notices/legal bases, permitted disclosures, retention/legal holds and rights-request handling before affected implementation. No legal regime, age cutoff, retention duration or licensing permission is invented here.

## 3. Questions removed, safely determined or deferred

| Earlier input | Final treatment; not another user questionnaire |
|---|---|
| B01 identity | R01 service/evidence policy; R03 dispute owner. Native authority, no fake identity and conservative matching remain engineering requirements. |
| B02 guardians | R07 population/delegation; portal scope decided once in R01. Native Student membership remains required for native Guardian access. |
| B03 calendar | R04; placement retakes handled once in R02, not confused with course repetition. |
| B04/B05 learning policies | R02; authority assigned once in R03 and content/recording rights once in R07. |
| B06 admission | R03; no repeat vote on separate admission versus placement/enrollment. |
| B07 finance | R05; learning continuity in R04. No duplicate billing-producer decision. |
| B08 workforce | R06; engineering selects the qualified native payroll input after business terms exist. |
| B09 privacy/rights | R07; one records policy applies across domains with domain-specific schedules. |
| B10 authority/accounts | R03 ownership and delegation. Separate incompatible accounts and fail-closed access are derived security requirements, not optional weakening choices. |
| B11 delivery/devices | R01 scope; collect actual accessibility/device constraints during delivery design, test a justified compatibility set. No framework/browser-brand vote or speculative offline platform. |
| B12 operations | **Deferred from this implementation-entry questionnaire, not waived.** Before deployment/operational design, obtain an operator, business outage/data-loss tolerances, capacity and recovery obligations. Engineers derive topology, backup/key handling and monitoring; Phase 2 independently blocks production. |
| B13 minimum entities | **Engineering review, not a business choice of DocTypes.** Minimize against approved requirements and native facilities; show justified scope/migration impact before implementation authorization. No unproven payroll bridge or parallel masters. |

No new approval is needed to preserve A01 routing, A07 internal-only claims, A08 native money authority, A10 separated admission or A12 separately grained source-owned reporting. In particular, placement remains **internal entrance/current-English-level determination and course recommendation before enrollment**, never academic results, official/mock TOEFL performance or baseline CEFR output.

A13's hook coverage, native RPC/CRUD/import/job containment, file/report permissions, concurrency/idempotency and recovery are **engineering proof obligations**, not business preferences. Approval of R01/R03/R07 cannot make these tests pass. No CONDITIONAL or BLOCKED A record changes status in this document.

## 4. Current next gate

R01/R02/R03/R07 direction is approved. Do not repeat requests for individual names or re-vote the approved method/scope. [PLACEMENT-IMPLEMENTATION-GATE.md](PLACEMENT-IMPLEMENTATION-GATE.md) records role ownership, remaining P01–P05 policy deliverables, the bounded candidate slice and evidence needed before a separate implementation authorization.

R04/R05/R06, academic grading and admission-offer rules remain gates for later slices. Missing policy content is not resolved by delegating its approval. No implementation starts from business-direction approval alone; production remains **REJECT**.

**Evidence boundary:** the original business-resolution gate added this document; the subsequent policy-approval gate updates it and adds the placement implementation-entry record. Historical architecture/source-review metadata and Phase 2 evidence remain unchanged and do not claim to cover these later files. No code, schema, API, UI, dependency, foundation pin, upstream source or deployment change; no runtime tests or deployment action.

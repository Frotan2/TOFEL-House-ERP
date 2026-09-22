# Phase 3 architecture review and decision lock

> **Placement scope revision:** [PLACEMENT-ASSESSMENT-MODEL.md](PLACEMENT-ASSESSMENT-MODEL.md)
> is the current authoritative placement design: governed question bank, blueprint-based
> randomized forms, six-skill automatic/manual assessment and digital/physical/hybrid delivery.
> It supersedes earlier staff-assisted-only/assessor-led-only scope and blanket exclusions
> of objective-bank delivery or digital speaking evidence. Recording permissions and
> operational policies remain conditional; R03 organizational owners and other domain
> boundaries are unchanged. Earlier approval/checklist text below is historical where
> it conflicts. No implementation authorization or production approval is granted.


Date: 2026-09-16 · Active branch: `arena/01a0c987-tofel-house-erp`. Scope: architecture and business-boundary reconciliation only. **No production approval is granted; production acceptance remains REJECT.** The canonical business input is the [owner-decision record](../engineering/canonical-owner-decision-record.json); engineering mechanism choices remain implementation work, not invented owner policy.

## Authority, status and business invariant

This record, [DOMAIN-CONTRACT.md](DOMAIN-CONTRACT.md) and [IMPLEMENTATION-READINESS.md](IMPLEMENTATION-READINESS.md) supersede conflicting proposals in the earlier Phase 3 documents. A01–A13 follow the thirteen topics in the latest instruction. The earlier D01–D13 questions are preserved through the crosswalk below; they are not silently renumbered or discarded.

**Placement Test = TOEFL House's internal entrance and English-level placement assessment.** Its purpose is to determine current English level and recommend a suitable TOEFL House course/level before enrollment. It is not an official TOEFL exam, a mock TOEFL performance score, an enrolled academic final exam, an external certificate or an official CEFR certification.

**Business flow:** Prospect/Applicant → Placement Test → Determine English Level → Recommend Course/Level → Admission → Enrollment. A placement recommendation, admission decision, Student identity and actual enrollment are separate facts.

- **DECIDED:** a definite architectural boundary is selected for this contract; it is not approval to implement, proof of native behavior or approval of operational parameters.
- **CONDITIONAL:** one recommended architecture is stated, but named business choices or native proof are still required to lock the affected slice.
- **BLOCKED:** a necessary policy or safe native-compatible path is unknown. The affected capability must not be implemented by guessing. A conservative denial boundary applies meanwhile.
- Options below are the materially viable alternatives **within the selected foundation**, with eligibility conditions stated. Fake identities/enrollments, duplicate ledgers, forged certifications, weakened permission checks and forced dependency upgrades are not viable options.

| ID | Topic | Status | Selected direction / limiting condition |
|---|---|---|---|
| A01 | Pre-program placement | **DECIDED** | Native prospect-linked placement when actual program is unknown; native Applicant when meaningful |
| A02 | Prospect/applicant identity | **CONDITIONAL** | Native identities and verified links; actual contact/account policy needed |
| A03 | Guardian relationship/access | **CONDITIONAL** | Explicit native post-Student relationship; pre-admission proxy and privacy policy unresolved |
| A04 | Mixed-role accounts | **CONDITIONAL** | Fail closed; prefer distinct native staff/self-service accounts for conflicting scopes, subject to identity policy |
| A05 | Rolling terms, repeat enrollment, retakes | **BLOCKED** | Real calendars; immutable placement retakes; same-term academic repeat representation unproven |
| A06 | Placement and academic scoring | **CONDITIONAL** | Internal level policy and section results separated from native academic results; academic policy required |
| A07 | Official TOEFL / CEFR claims | **DECIDED** | No official/mock TOEFL output; no CEFR output in baseline placement contract |
| A08 | Single canonical billing flow | **DECIDED** | ERPNext invoice/payment/GL authority; one native enrollment-generated tuition invoice chain |
| A09 | Teacher compensation/payroll inputs | **CONDITIONAL / FRAMEWORK SELECTED** | Configurable fixed, skill-based and combined teacher compensation feeds the single native HRMS/payroll authority; rates, statutory rules and exact payable policy remain configurable/blocked where unsupplied |
| A10 | Admission approval semantics | **DECIDED** | Explicit admission decision; placement, offer acceptance and registration remain distinct |
| A11 | Enrollment cancellation | **BLOCKED** | No destructive cancellation as a transfer/repeat shortcut; safe history-preserving path must be proven |
| A12 | Reporting and derived data | **DECIDED** | Source-owned metrics with separated grains, provenance, permissions and rebuildable projections |
| A13 | Backend containment of native bypass routes | **CONDITIONAL** | Server invariants plus contained native entry points; coverage must be demonstrated. Implemented-slice coverage now demonstrated: hosted negative route proofs for the seven command-only doctypes (cancel/post-submit-edit/RPC/REST/Desk-cancel/copy-amend seams, run `35008705885`, 523/523) — see [CONTAINMENT-A13.md](CONTAINMENT-A13.md). Full writer/side-effect inventory for unimplemented domains (B10/B11/B13) remains open |

## Evidence register

All source references below resolve to exact commits, paths and SHA-256 records in [pinned-source-review.json](pinned-source-review.json). Source inspection is not new runtime qualification.

- **S1:** Education Student Applicant schema/controller: real Program and Academic Year required; native status Applied/Approved/Rejected/Admitted; not submittable. Student Admission is intake configuration, not a person's approval record.
- **S2:** Education Student schema/controller: email required; native Applicant/User/Customer links; validation can provision User, update Applicant to Admitted, and create/update Customer. The supported skip-user-creation setting and explicit links matter.
- **S3:** Program Enrollment schema/controller: duplicate student/program/year/term check; submit creates Course Enrollments and configured Sales Order/Invoice effects; cancel deletes Course Enrollments. The check is not by itself evidence of race-safe uniqueness.
- **S4:** Course Enrollment, Student Group, Course Schedule, Student Attendance and Assessment Plan/Result schemas: native academic identities, scheduling and enrolled-learning records. They are not a pre-enrollment placement/result model.
- **S5:** ERPNext Lead/Employee and Education Instructor schemas: prospect and employment authorities; explicit Instructor.employee link, not identity by matching names.
- **S6:** HRMS Additional Salary/Payroll Entry source schemas and retained native qualification: native payroll inputs/processing exist; complete jurisdictional teaching-pay behavior and posting have not been proven.
- **S7:** Exact owned foundation guard sources: Student/Guardian global exact native scopes; Guardian lookup requires actual Student membership; existing File protection is scoped and does not prove every new placement/staff attachment path.
- **S8:** Pinned `education/education/api.py`: `enroll_student` uses `get_mapped_doc(..., ignore_permissions=True)` before native Student save and Program Enrollment creation; bulk attendance explicitly commits. This identifies containment/transaction requirements, not a new claim of observed exploitation.
- **R1:** [Retained qualification](../engineering/foundation-final-qualification.md) and [acceptance ledger](../engineering/foundation-production-acceptance-ledger.json): baseline 57 frontend matches; unadopted experimental candidate 23; scoped native/security/restart passes; production REJECT. None qualifies a future domain implementation.

Frappe supplies native document/identity/permission/transaction mechanisms throughout; application-specific APIs and bypasses must be inspected. HRMS has no ownership of learner placement or academic results. Conversely, Education does not own payroll or GL. No support guarantee is inferred from a declared field or release.

**Owner boundary:** Course Owner is system/strategic final authority; General
Manager owns routine administration/operations; Academic Manager owns academic
operations/progress; Finance Manager owns finance/payroll; Reception owns intake.
Role-based access, auditability, offboarding with historical preservation,
multi-branch authorization/data isolation, configurable business policy, and
controlled owner administration/health visibility are required. Current operation
is local/server-based through Tailscale with local database/files. Future internet
hosting, provider/hostname/DNS/public edge, and off-site backup destination are
not selected. Automated encrypted multi-version backup and alternate-system
recovery are required, with data preservation prioritized. Portal and online
payments are not launch scope.

## A01 — Pre-program placement

**Status: DECIDED. Problem:** placement must precede course enrollment, but native Student Applicant requires a real Program/year. How can a learner be assessed without inventing academic participation?

**Options:** P — attach a placement case to native ERPNext Lead until program choice is meaningful; K — create native Applicant first only for someone with a genuine intended Program/year, then assess before enrollment. These are complementary entry routes, not two person masters. Forcing everyone through K is not viable when the program is unknown.

| Consequence | P: prospect-linked case | K: known-program applicant |
|---|---|---|
| Data model | Case references Lead; no copied identity | Case references native Applicant |
| Ownership | Lead owns prospect; owned placement owns attempt/result | Education owns application; same owned placement authority |
| Lifecycle | Placement/recommendation before native application materialization | Application intention precedes placement; no enrollment yet |
| Permissions | Verified subject or assigned staff; not Student privileges | Applicant scope, not Student/academic access |
| Workflows | Create real Applicant after recommendation and choice | Review chosen program after placement |
| Reporting | Count prospect and application stages separately | Do not count application as enrollment |
| Integrations | Later native provenance link; idempotent conversion | Native application intake checks preserved |
| Operational complexity | Requires explicit late linking and dedup | Simpler linking, but limited to meaningful program choice |
| Migration/reversibility | Preserve original subject on historical attempts | Preserve original application; do not relabel old attempts |

**Native constraints:** S1/S2/S5. Frappe Links do not require a fake Student to own a custom placement case. ERPNext Lead is the pre-program identity; Education's required fields remain unchanged. HRMS is not involved.

**Recommendation / lock:** use P when program is unknown and K when genuinely known. This is one placement domain with exactly one original native subject per case. No placement command creates Student, Program Enrollment, Course Enrollment or Assessment Result. No enrollment is a prerequisite to placement.

**Irreversible consequences:** none enacted now. After data collection, subject provenance and consent cannot safely be rewritten; future conversion needs stable links and an audited merge policy. **Business decision required:** none to choose this architectural routing; identity/consent details remain A02/A03. No arbitrary “general intake” placeholder Program.

## A02 — Applicant/prospect identity

**Status: CONDITIONAL. Problem:** represent one person across inquiries, applications and returning study without treating shared contact information as identity, bypassing required email, or duplicating Student/Customer.

**Options:** S — staff-assisted native Lead/Applicant intake with separately verified activation; U — verified applicant self-service using native User plus explicit business links, after account/contact policy approval. Both preserve native person/application ownership; no new `TH Applicant` master is viable.

| Consequence | S: staff-assisted first | U: verified self-service |
|---|---|---|
| Data model | Native Lead → applications; verified existing-Student reference | Same records plus controlled User-to-subject claim |
| Ownership | Native identity and application authorities | Native User owns authentication, not application decisions |
| Lifecycle | Account activation may be deferred | Identity claim must precede online response access |
| Permissions | Assigned staff with purpose-limited PII | Strict own-subject scope, recovery and revocation |
| Workflows | Manual duplicate review and returning-student match | Adds invitation, claim, recovery and suspicious-claim review |
| Reporting | Application counts separate from unique people | Same grains; account counts are not learner counts |
| Integrations | Avoid premature welcome messages | Native User/email integration, no parallel auth provider chosen |
| Operational complexity | More staff work; does not solve required Student email | Greater support/abuse/recovery burden |
| Migration/reversibility | Activation can be added later; merging is sensitive | Account relinking requires audit and session revocation |

**Native constraints:** S1/S2/S5/S7. Native Student email is required; native creation may create a User/Customer and change Applicant status. Frappe User is not a learner master. Reapplication must reuse an existing Student when verified; ERPNext party records cannot be merged just because email matches. HRMS Employee remains separate from learner identity.

**Recommendation:** S first, U only after the claim/recovery design is approved. Keep original `Student.student_applicant` provenance; a later genuine application may refer to the verified existing Student through its admission decision. Do not fabricate email, relax required fields or infer one person from a family address.

**Business decision required (B01; unresolved):** accepted identity evidence, duplicate/merge authority, required-email policy for minors/learners without their own address, whether legitimate institution-managed mailboxes are available, and whether applicant online access is in scope. Until resolved, affected conversion/activation is blocked. Staff assistance alone does not remove native email constraints.

**Irreversible consequences:** identity merges and payer relinking can corrupt historical academic/financial ownership; require rehearsed non-destructive reconciliation. No merge, field or account is created here.

## A03 — Guardian relationship and access

**Status: CONDITIONAL. Problem:** a parent/guardian may assist a prospect before Student creation, but the existing Guardian login guard requires actual Student membership. Legal relationship, payer status and online access are distinct.

**Options:** N — staff-mediated pre-admission contact/consent evidence, then explicit native Guardian–Student access after Student exists; P — a separately verified pre-admission proxy relationship over Lead/Applicant using native User, only after policy and native-compatible access design are approved.

| Consequence | N: staged native access | P: pre-admission proxy |
|---|---|---|
| Data model | Relationship evidence first; native Guardian/child links later | Adds narrowly scoped proxy evidence and User link, not a new guardian master |
| Ownership | Native Guardian/Student own eventual membership | Same native owners; owned evidence records delegation only |
| Lifecycle | No Guardian portal entitlement before Student | Proxy expires/revokes independently of later guardianship |
| Permissions | Staff purpose scope; later exact linked-child scope | Explicit permitted actions, not all Applicant/Student data |
| Workflows | Assisted intake; audited post-conversion activation | Requires claim, delegation, consent and revocation workflow |
| Reporting | Distinguish contact, payer and authorized guardian | Separate proxy status; never infer parental entitlement |
| Integrations | Preserve current guard contract | Must prove coexistence with guard and native APIs |
| Operational complexity | Lower online complexity; more staff handling | Higher privacy, account recovery and evidence burden |
| Migration/reversibility | Add explicit native links without rewriting attempts | Revoke proxy separately; retain legally required evidence |

**Native constraints:** S1/S2/S7. Applicant guardian child rows do not satisfy the current Student-parent lookup. Shared email and File.owner are not authorization. Frappe sharing must not be used to bypass the guard. ERPNext payer Customer access is separate; HRMS grants no guardian authority.

**Recommendation:** N as initial scope; do not offer P until separately approved. No fake Student for login. Existing students retain explicit native Guardian links, current child/customer scopes and revocation checks. Assisted actions record actor and subject, not impersonation.

**Business decisions required (B02/B09):** who may consent/act for a minor or adult, evidence and expiry of delegation, custody/access restrictions, records/recording rights, pre-admission online scope and retention. **Irreversible consequences:** releasing a recording or child's data cannot be undone; historical delegation evidence must survive later relinking. No access is granted by this decision.

## A04 — Mixed-role accounts

**Status: CONDITIONAL. Problem:** a teacher may also be a learner/guardian. Current global exact Student/Guardian permissions cannot be widened by a UI role selector without conflicting with the foundation guard.

**Options:** A — distinct verified native User accounts for each incompatible staff/Student/Guardian scope, linked to the same underlying Employee/Student/Guardian authorities; L — allow only a limited combined account whose entire access remains inside the current strict intersection, with conflicting functions unavailable. Broad combined-account privileges would require a separately qualified security architecture and are not a current option.

| Consequence | A: separated native accounts | L: limited intersection |
|---|---|---|
| Data model | More User links, not duplicate people/ledgers | One User with deliberately constrained capabilities |
| Ownership | Native User authenticates; native business masters remain | Same ownership; no contextual identity override |
| Lifecycle | Provision/offboard each account and linked relationship | Grant/revoke roles only if the intersection stays valid |
| Permissions | Staff and self-service sessions have distinct authority | Global guard remains binding; no “switch role” escalation |
| Workflows | Explicit account switch, independent invitations/recovery | Some teaching/guardian tasks require staff assistance |
| Reporting | Resolve actor account and business person separately | Reports cannot union denied scopes |
| Integrations | Native account/session handling; qualify MFA/recovery | No client claims accepted as privileged role context |
| Operational complexity | More account management and mistakes to prevent | Lower account count, potentially unacceptable usability |
| Migration/reversibility | Splitting an existing account needs session/job reassignment | Later split must preserve actor history |

**Native constraints:** S2/S5/S7. Frappe/owned global checks apply before domain command choice; native User Permission applies across doctypes. HRMS Employee and Education Student are distinct roles of a person; ERPNext finance permissions cannot leak through either.

**Recommendation:** prefer A for genuinely conflicting access, with L's denial behavior until account policy is approved. Do not modify the foundation guard or introduce a permissive second login path to make a combined account work.

**Business decision required (B01/B10):** approve separate staff/self-service accounts, legitimate distinct contact/recovery arrangements, responsibility for provisioning and acceptable assisted workflows. Hosted mixed-role security/usability proof remains required. **Irreversible consequences:** audit records must preserve the original actor account; do not rewrite historical authors to a new login. A single combined Student+Guardian self-service account is not assumed compatible either. No accounts are created now.

## A05 — Rolling terms, repeat enrollments and placement retakes

**Status: BLOCKED for same-term academic repeat/transfer representation. Problem:** placement retesting is not course repetition. Native enrollment uniqueness and cancellation behavior may conflict with rolling language-center intakes.

**Options:** T — real intake terms with actual dates and native groups, repeats only in a genuinely different valid enrollment key; C — continue/reassign participation within an existing valid enrollment only where native semantics and retained history fit the approved service. C is not a second independent enrollment in the same key. If the center requires independent same-key repeats, neither is proven sufficient.

| Consequence | T: genuine term-based offerings | C: continued participation |
|---|---|---|
| Data model | Native Program/year/term/enrollment + groups | Same native enrollment; approved effective roster changes |
| Ownership | Education owns enrollment/calendar | Education still owns enrollment/participation |
| Lifecycle | New valid period permits legitimate new enrollment | No new enrollment lifecycle is fabricated |
| Permissions | Period/group assignment gates teacher/learner access | Must retain past scope and revoke old active assignments |
| Workflows | Publish actual intake calendars before registration | Reassignment requires explicit continuity/charge decision |
| Reporting | Separate true enrollments and participation periods | Continued participation must not inflate admissions/enrollment counts |
| Integrations | Uses native uniqueness key | Must qualify impacts on attendance, grades and billing |
| Operational complexity | More real calendar administration | More effective-date/history reconciliation |
| Migration/reversibility | Calendar relabeling after use is unsafe | Later splitting participation into enrollments is migration-heavy |

**Native constraints:** S3/S4. Duplicate check includes draft/submitted records for student/program/year/term; Course Enrollment links its Program Enrollment. Canceling the parent deletes course records. Frappe links/transactions do not prove history-safe transfer; ERPNext billing effects and HRMS schedule/pay evidence must not be erased by a repeat workaround.

**Recommendation:** T for ordinary defined intakes; C only after semantics are demonstrated. Never create per-student fake terms, duplicate Course/Program masters or cancel history to evade uniqueness. **Placement retakes are independently locked:** new Attempt and Decision revisions under the same verified subject/case purpose; preserve all attempts and never overwrite the previous result. Waiting interval, validity and which decision is effective remain A06 business policy.

**Business decision required (B03):** actual calendar granularity and whether the business requires an independent repeat of the same Program/year/term, including overlapping offerings. **Proof required:** native-compatible representation, race-safe capacity and preserved histories/charges. **Irreversible consequences:** used calendar keys and deleted Course Enrollments cannot safely be reconstructed from a renamed label. Block unsupported repeats; no calendar/schema change now.

## A06 — Internal placement and academic scoring policy

**Status: CONDITIONAL. Problem:** determine current English level and course recommendation using valid internal evidence without copying TOEFL examination scoring or confusing it with enrolled academic achievement.

**Options:** H — assessor-led, rubric/section-based internal placement with reviewed level decision; M — approved mixed objective-component scoring and assessor moderation. Both need an approved internal policy. Neither assumes TOEFL sections, weights, scaled totals or CEFR certification.

| Consequence | H: assessor-led | M: mixed scoring |
|---|---|---|
| Data model | Versioned rubric, section observations/ratings, decision rationale | Adds objective item/key definitions and deterministic component results |
| Ownership | Owned Placement Decision is the Placement Result | Same result owner; calculation outputs are evidence, not a second result |
| Lifecycle | Assigned review → moderation as required → release | Automatic component calculation still precedes required review/release |
| Permissions | Assigned assessor access; conflict/independence controls | Keys separated from candidate-readable delivery; restricted scoring worker |
| Workflows | More human assessment; explicit rationale | Adds key publication, scoring failures and human exception handling |
| Reporting | Internal level and section evidence, rubric/policy version | Comparable internal components only under matching policy/units |
| Integrations | Native references to recommended Program/Course | Same; no native Assessment Result or official-score API writes |
| Operational complexity | Assessor calibration, workload and consistency | Additional key/security/algorithm validation plus calibration |
| Migration/reversibility | Preserve rubric/version/raw observations | Preserve original keys/raw scores; never recalculate history in place |

**Native constraints:** S4/S7. Education Assessment Plan/Result belong to enrolled academic learning and cannot be reused merely to avoid a pre-enrollment model. Frappe child tables do not create independent key visibility boundaries. ERPNext and HRMS have no scoring authority; teacher employment does not authorize access to every attempt.

**Recommendation:** use one versioned internal placement contract supporting H and, only for approved components, M. The effective Placement Result is a released TH Placement Decision with current English-level determination, appropriate internal course/level recommendation, section results where applicable, reviewer and rationale. Do not assume an overall total is necessary. Decimal normalization is permitted only if an approved policy defines compatible units, bounds, rounding and aggregation; no formula or cutoff is approved here. Enrolled Academic Assessment stays native and separate. Academic owners must separately approve native grading scales, assessment/component weights, pass/progression criteria, correction authority and comparability across course-policy revisions; placement rubrics or thresholds cannot supply those defaults.

**Business decisions required (B04/B05/B09/B11):** sections actually used, rubric/level vocabulary, objective versus human components, cutoffs/mappings, moderation, conflict rules, accommodations, delivery mode, retest interval/validity/effective-result rule, interruption/appeal rules and content/recording rights. Missing required evidence cannot silently become zero or be normalized away. Default initial entry flow requires a valid released internal placement result; no automatic external-result or payment exemption.

**Irreversible consequences:** released labels, disclosed content and admissions made from them have lasting effects. Preserve every attempt, response/rating revision and original recommendation; corrections supersede with rationale. A policy change cannot rewrite historic academic or placement records.

## A07 — Official TOEFL and CEFR claim boundaries

**Status: DECIDED. Problem:** the center's name and English-level labels must not misrepresent internal placement as official examination performance or certification.

**Options:** I — internal level vocabulary only; R — a separately approved, explicitly labeled internal CEFR reference mapping, supported by calibration and provenance, never certification. R is viable only under a future explicit business requirement; it is not enabled in this contract. Official/mock TOEFL score generation is not an option.

| Consequence | I: internal labels | R: future internal reference |
|---|---|---|
| Data model | Internal level/policy/recommendation fields only | Separate optional reference field and mapping revision, never replacing internal result |
| Ownership | Owned placement decision, no certification authority | Same; mapping owner cannot certify on behalf of an external body |
| Lifecycle | Internal result reviewed/released | Additional approved mapping and withdrawal lifecycle |
| Permissions | No official-score write/display capability | Mapping publication and display separately controlled |
| Workflows | Admission consumes internal recommendation | Mapping must not bypass placement or admission |
| Reporting | “TOEFL House Internal Placement Result” | “Internal CEFR reference — not certification,” distinct from primary result |
| Integrations | No official result creation/export endpoint | Explicit mapping export semantics; no official examination claim |
| Operational complexity | Lowest claim/calibration burden | Calibration, licensing/legal review and display governance |
| Migration/reversibility | Preserve internal label meaning by revision | Removing a mapping cannot undo prior disclosure; retain provenance |

**Native constraints:** S4/R1. Native numeric/grade fields and report customization are not authority to issue official scores. Frappe/ERPNext/Education/HRMS supply no official TOEFL/CEFR certification rights through this installation.

**Recommendation / lock:** I. Do not generate or represent an official TOEFL score, a mock TOEFL performance score or a CEFR certificate. Remove the previously proposed conditional external-exam evidence DocType from the active Phase 3 model. External official results and any internal CEFR reference require separate future scope/decision records; neither is an automatic admission substitute.

**Business decision required:** none for this exclusion; the latest instruction fixes it. R would require a new explicit request and evidence before any fields, mapping or UI. **Irreversible consequences:** misleading certificates/claims cannot be recalled reliably; treat reports, exports, labels, APIs and notifications as part of the boundary, not only database field names.

## A08 — Single canonical billing flow

**Status: DECIDED for authority and tuition generation route. Problem:** native enrollment and fee schedules can create commercial documents; enabling parallel generation or treating placements/payments as enrollment creates duplicate charges and misleading balances.

**Options:** E — native enrollment-generated tuition Sales Invoice, using reviewed fee configuration, one obligation/active posting chain; B — native batch Fee Schedule-generated invoices with enrollment generation suppressed for those same charges. Both use ERPNext accounting; they are mutually exclusive producers for any obligation.

| Consequence | E: enrollment-generated invoice | B: batch-generated invoice |
|---|---|---|
| Data model | Native fee references → Sales Invoice; operation records hold IDs only | Batch membership/source → same native invoice authority |
| Ownership | ERPNext Invoice/Payment Entry/GL owns money | Identical financial ownership, no batch balance master |
| Lifecycle | Authorized native enrollment submission generates tuition | Approved batch generation follows defined billing cycle |
| Permissions | Registration command and invoice writer both constrained | Batch operator/job constrained per student/company/charge |
| Workflows | Closely couples one authorized registration to one charge | Requires reconciliation between registration and billing batch |
| Reporting | Invoice/allocations/GL, not enrollment counts as revenue | Same; pending batch items are not receivables |
| Integrations | Must reconcile native submit side effects/idempotency | Must guard async jobs and retries across batch membership |
| Operational complexity | Fewer independent producers; partial submit recovery required | More asynchronous lag/reconciliation and duplicate risk |
| Migration/reversibility | Amend/credit native posting chain; never delete GL | Switching producer requires closed/mapped obligations and no double-generation |

**Native constraints:** S2/S3/R1. Student maintains Customer; Program Enrollment consults fee configuration and can create Sales Order or Invoice. ERPNext alone owns receivable/settlement/GL. HRMS payroll must not offset learner balances through a custom field. Frappe wrapper transactions do not guarantee side-effect rollback.

**Recommendation / lock:** E for new tuition in this contract: target invoice generation, not a parallel Sales Order receivable or batch producer. Legacy Fees is not another billing route for the same charge. Native batch/native API paths must be constrained under A13; configuration is **not changed now**. Placement fees, if approved, are separately identified native charges and never hidden tuition duplicates. A later producer switch is an explicit architecture/migration decision, not a per-request flag.

**Business decisions required (B07):** company/currency/tax/fiscal/price rules, deposits or credit clearance, aid/refund approvals, authorized payer relationships and whether placement is charged. These block financial implementation/configuration, not the selected canonical authority. If a deposit precedes an enrollment-generated invoice, use approved native Customer advance/credit semantics after legitimate Customer creation; do not require a nonexistent invoice or mark it paid from a redirect.

**Irreversible consequences:** submitted financial history is corrected through native amendments/credits/refunds, never erased. Producer changes require obligation-to-posting reconciliation. No invoice, configuration or money movement is created here.

## A09 — Teacher compensation and payroll-input authority

**Status: BLOCKED for compensation/input implementation. Problem:** planned class time, delivered teaching, legally payable work and actual payroll are different. The center's employment/pay basis and a single native input path have not been selected.

**Options:** F — salaried Employee with native Salary Structure/Assignment and native HR inputs, Additional Salary only for authorized adjustments; T — native time-based payroll if the selected HRMS/ERPNext path supports the approved work rule; C — native supplier purchasing/payment for genuine legally approved contractors, not fake Employee/payroll records. C is a distinct workforce classification, not a payroll workaround.

| Consequence | F: salary-based | T: approved time-based | C: genuine supplier contractor, if legally approved |
|---|---|---|---|
| Data model | Native employment/pay setup and approved adjustments | Native Timesheet/work inputs with unique approved source references | Native Supplier/Contact, approved service evidence and purchasing/payment references; no fake Employee |
| Ownership | HRMS owns payroll inputs/calculation; ERPNext accounting | Same; classroom records are supporting evidence only | ERPNext purchasing/payables owns service payment, not HRMS salary |
| Lifecycle | Periodic salary plus approved exceptions | Work approval precedes one native payroll input/posting chain | Approved service → supplier invoice/credit/payment; distinct from employment |
| Permissions | HR/payroll separation; teacher cannot approve own pay | Supervisor approves work, payroll approves financial application | Academic work verification separate from procurement/finance approval |
| Workflows | No automatic per-session salary deductions | Explicit cancellations, substitutions, prep/overtime and corrections | Contract/service acceptance and native payable workflow, no payslip |
| Reporting | Planned/delivered/payable/posted/paid remain separate | Same; approved hours are not proof of cash paid | Contractor service costs are not employee salary/headcount |
| Integrations | Native payroll and accounting; no fee-to-pay offset | Qualify native time-based path; bridge only if a concrete gap exists | Reviewed Instructor-to-supplier reference and service idempotency, no payroll double-payment |
| Operational complexity | Simpler if true salaried policy fits | Higher unit/rate/timesheet and replay reconciliation burden | Contract, tax/classification and supplier reconciliation burden |
| Migration/reversibility | Historic terms/periods retained; corrective native adjustments | Pay-basis change effective-dated; no rescore/rewrite of old slips | Reclassification cannot erase earlier statutory liabilities or historical payables |

**Native constraints:** S5/S6/R1. Instructor.employee is explicit; HRMS uses native Employee and payroll objects. Native Student Attendance is not Employee Attendance. Additional Salary schema existence is not proof of every teaching-pay formula, statutory rule or completed GL/payment path.

**Recommendation:** select F or T for employees from actual approved employment terms, and C only for genuine approved contractors, then designate **exactly one canonical native payroll input path per employee/pay component/period/source basis**. A TH Teaching Work Approval, if necessary, may approve evidence and hold the resulting native input reference; it cannot independently calculate salary, own a payslip or post a second payroll amount. No simultaneous timesheet and Additional Salary ingestion for the same payable basis.

**Business decision required (B08):** employees versus genuine contractors, salary/hour/session model, paid cancellations/preparation/substitution, leave/overtime, period boundaries, currency and statutory jurisdiction. **Proof required:** chosen native path, unique source ingestion, amendments and native payroll/GL/payment reconciliation. **Irreversible consequences:** tax/pay obligations and employee disclosures require retained historical terms and compensating adjustments; wrong classification is not repairable by relabeling a report. No pay rule selected by inference from location.

## A10 — Admission approval semantics

**Status: DECIDED. Problem:** a placement recommendation or native Applicant “Admitted” status must not stand in for academic admission, offer acceptance, financial clearance or actual enrollment.

**Options:** D — a separate owned Admission Decision referencing native Applicant and released placement; W — a reviewed native Applicant Workflow plus durable decision/condition evidence. W is viable only if it can preserve the same decision history despite native status side effects; it is not permission to use the stock status alone.

| Consequence | D: separate decision | W: native workflow plus evidence |
|---|---|---|
| Data model | Owned decision/evidence links; no new application master | Workflow fields and sufficient separate immutable history |
| Ownership | Education owns Applicant; domain owns institutional approval | Same conceptual ownership but closer coupling to Applicant changes |
| Lifecycle | Decision, conditions, offer acceptance/expiry independent | Must separate workflow state from native application_status changes |
| Permissions | Explicit admissions approver, conflict controls | Native role/workflow checks plus equivalent domain validation |
| Workflows | Clear input to enrollment coordinator | More native-status reconciliation and alternate-route checks |
| Reporting | Approved/accepted/fulfilled/enrolled distinguished | Reports must reconstruct equivalent distinctions, not read one status |
| Integrations | Native conversion rechecks decision, not UI state | Native mapped calls cannot treat status transitions as authority |
| Operational complexity | One justified approval record and coordinator | Potentially fewer visible forms but tighter native coupling |
| Migration/reversibility | Supersede decision; retain native identity provenance | Future extraction requires recovering approver/condition history |

**Native constraints:** S1/S2/S3/S8. Applicant is not submittable and its Admitted status can change on Student creation. Program Enrollment submission has separate effects. Frappe workflow buttons and ERPNext payment state do not confer academic authorization. HRMS has no admission role merely by employing the teacher.

**Recommendation / lock:** D. Initial entry admission requires a valid released internal placement decision. Determine internal level/recommendation first; admissions separately approves the eligible course/intake and offer. No automatic placement exemption for official external scores, finance or prior learning is included. Any future exception policy requires explicit business authorization without manufacturing a placement result. Re-enrollment's placement validity/retake rule remains A06; it does not recreate the Student.

**Business decisions required (B06):** actual eligibility, prerequisites, admission conditions, validity/offer expiry, independent approvers and acceptance evidence; no waiver exists by default. Placement reviewer must revise a disputed recommendation through its own audited decision, not let admissions edit the raw result. **Irreversible consequences:** accepted offers and acted-on decisions require preserved history; revocation is a new event, not deletion. Architecture choice is fixed; operational policy/sign-off remains absent.

## A11 — Enrollment cancellation semantics

**Status: BLOCKED for a history-affecting cancellation/transfer implementation. Problem:** native cancellation deletes Course Enrollments; using it to transfer or repeat a course could damage participation/result/billing lineage.

**Options:** P — prospective withdrawal/roster change while retaining valid historical enrollment, only where native effective participation semantics can express it; X — reviewed native cancellation/amendment with an explicit dependency, finance and recovery plan, only where safe. Neither path is proven for all requested cases.

| Consequence | P: prospective change | X: cancel/amend |
|---|---|---|
| Data model | Retain enrollment and linked historic records | Native canceled/amended chain; affected child records require protection plan |
| Ownership | Education owns past participation; domain records request | Same; domain cannot replace deleted authority with a fake enrollment ledger |
| Lifecycle | Access/participation ends prospectively, history remains | Cancellation is a separate authorized destructive lifecycle event |
| Permissions | Change approver plus current scoped roster writer | Strong independent approval and dependency checks |
| Workflows | Finance refund considered separately | Coordinate academic and financial amendments; no blind retry |
| Reporting | Past participation and withdrawal date distinct | Canceled status cannot erase attended sessions/earned results from history |
| Integrations | Revoke future access/jobs; preserve evidence | Inspect child deletion, finance effects, files, reports and recovery |
| Operational complexity | Effective-date and entitlement proof required | Higher reconciliation/restore risk and intervention cost |
| Migration/reversibility | Future re-entry must not overwrite original dates | Deleted child rows/history may not be automatically reconstructable |

**Native constraints:** S3/S4/S8/R1. `on_cancel` invokes deletion of Course Enrollments. Existing framework patch/restore evidence is not proof of this domain migration. ERPNext credits/refunds must stay native; HRMS historical teaching work/pay evidence cannot be deleted along with a roster. Frappe transaction rollback does not prove undo of committed/external effects.

**Recommendation / containment:** prefer P when native semantics demonstrably suffice. **Deny historical cancellation as a transfer, withdrawal or uniqueness workaround until the affected path is qualified.** X only after reviewed impact and recovery proof. Do not simply disable UI buttons while leaving native cancellation RPC/import routes open (A13).

**Business decision required (B03/B07):** effective withdrawal/transfer rules, earned-credit/history treatment and independent refund obligations. **Proof required:** dependency graph, native-compatible representation, canceled/amended billing behavior and restored historic records. **Irreversible consequences:** high; deletion can break lineage and externally acted-on financial changes cannot be undone by deleting a request. No safe universal cancellation algorithm is asserted.

## A12 — Reporting metrics and derived data

**Status: DECIDED. Problem:** similar-looking scores, persons/applications and monetary/work quantities can be conflated in reports, creating unofficial certification claims or a parallel system of record.

**Options:** Q — scoped on-demand queries over authoritative sources; P — rebuildable scoped projections when measured volume justifies them, with source lineage/as-of/cutoff. An independently editable warehouse balance/result master is not viable.

| Consequence | Q: source queries | P: derived projections |
|---|---|---|
| Data model | No duplicate result/balance tables | Derived rows carry source IDs, revisions, grain and refresh state |
| Ownership | Domain/natives own facts; metric steward owns definition | Same; projection service cannot change source facts |
| Lifecycle | Current/as-of query rules explicit | Refresh/invalidate/rebuild distinct from business transitions |
| Permissions | Scope rows/fields before aggregation | Scope materialization, access, drill-down and refresh actor |
| Workflows | Reports do not approve admission/payroll | Stale projections must not drive irreversible decisions |
| Reporting | Separate placement, academic, finance and work metrics | Same semantic partitioning; no mixed “test score” aggregate |
| Integrations | Native/owned source reads only | Idempotent refresh and revocation/retention propagation |
| Operational complexity | Simpler ownership; performance must be measured | More freshness, purge, consistency and authorization operations |
| Migration/reversibility | Definition revisions retained | Rebuildable, but exported PII cannot be recalled automatically |

**Native constraints:** S2/S3/S4/S6/R1. Native Applicant status is not completed enrollment; placement is not Assessment Result; invoices/orders/cash/GL and planned/worked/paid units have different meanings. Frappe report/export permissions require separate validation; native links do not authorize every join.

**Recommendation / lock:** Q first; P only for proven need. Placement metrics use released internal Placement Decisions at decision/attempt/person grains explicitly stated. Academic metrics use native Assessment Results and approved academic policies. No official TOEFL metric or default CEFR mapping. Academic, admissions, finance and HR stewards approve their own metric definitions; platform/report code does not invent denominators or financial totals.

**Business decisions required (B09/B10 plus B04/B07/B08):** named stewards, permitted disclosures/exports/retention and the domain-specific policy parameters used by metrics. **Irreversible consequences:** projections are rebuildable; published/downloaded data is not. Metric-definition changes need explicit version/cutoff and must not rewrite historic decisions or finance.

## A13 — Backend enforcement despite native/UI bypass paths

**Status: CONDITIONAL. Problem:** a wrapper/UI can be bypassed through native RPC, generic CRUD, imports, jobs or direct native document operations. Some native paths bypass mapping permissions or commit internally.

**Options:** H — supported domain document/lifecycle hooks plus scoped service commands and specific containment of unsafe native entry points; R — restrict a particular unsafe workflow/endpoint until an equivalent supported, fully checked path is proven. R is a fallback for that action, not a claim that hiding a route protects the whole domain.

| Consequence | H: server invariant coverage | R: unavailable unsafe action |
|---|---|---|
| Data model | Decision/operation references, atomic uniqueness where justified | No alternate shadow data model to compensate for disabled feature |
| Ownership | Native controllers keep academic/financial effects | Same native authority; no direct SQL replacement |
| Lifecycle | Every writer validates required approvals/state | Deny transition rather than silently perform partial unsafe work |
| Permissions | Native permission AND domain scope/state; service actor constrained | Server-side denial of all identified alternate entry routes |
| Workflows | Supported wrappers/hook composition, not client checks | Explicit assisted/unavailable workflow, no operator backdoor |
| Reporting | Record applied/failed/partial operations separately | Report unmet demand without pretending completed registration |
| Integrations | Reauthorize jobs/exports/files/events; idempotent after-commit effects | Provider/background routes cannot bypass restriction |
| Operational complexity | Comprehensive route inventory, tests, recovery and version maintenance | Reduced service; ongoing verification that no alternate writer remains |
| Migration/reversibility | Supported hooks removable only after replacement controls; preserve operation history | Re-enable only after qualification; no automatic release of old queued work |

**Native constraints:** S7/S8/S3/R1. Mapper `ignore_permissions=True` does not prove every subsequent write bypasses all checks, but forbids relying on the UI/source mapping permission as approval. `db_set`, internal commits and privileged imports may not traverse the expected validation hooks. Existing guard tests do not prove new domain coverage. HRMS controller composition and ERPNext posting side effects must remain intact; Frappe sharing/admin privileges are not routine domain authorization.

**Recommendation:** H, with R for any path whose invariant coverage cannot be demonstrated. Commands recheck actual subject, approver, policy, tenant/branch/company, current state and stable request identity. Use supported server hooks and, where justified, narrowly scoped supported API containment; no upstream core edits, client bypass flags or arbitrary privileged CRUD. A service's technical authority is not authority to invent an admission, grade or payment. Privileged database/operator access remains governed/audited, not magically prevented by app code.

**Required proof / business decisions (B10/B11/B12/B13):** full native writer and side-effect inventory; reviewed role/delegation/assisted-workflow scope; exact extension point behavior; negative tests across native RPC/REST/Desk/import/jobs/cancel/export/files; race and recovery tests; approved minimal technical records. Until those exist, new domain enforcement is **unimplemented and unproven**. No production topology or risk waiver is selected.

**Irreversible consequences:** an unsafe financial or admission effect can outlive its failed request; losing idempotency records can make retries duplicate actions. Preserve evidence and use native compensation. No blanket atomicity, exactly-once or rollback guarantee.

## Original D01–D13 crosswalk and required business inputs

These inputs remain explicitly unsatisfied, not thirteen silently discarded questions. IDs B01–B13 are business/input or capability confirmations, **not a second set of architecture approvals**. An input need only be resolved for an explicitly authorized slice; production remains separately blocked.

| Original question | Authoritative decisions | Explicit input/approval still required |
|---|---|---|
| D01 pre-program route | A01 | Routing locked; B01 identity implementation policy still needed |
| D02 identity/guardian/accounts | A02–A04 | **B01** identity/email/merge/activation; **B02** legal guardian/delegation and pre-admission access |
| D03 catalog/terms/repeats | A05, A11 | **B03** actual calendars, same-term repeat requirement and history/effective-date rules |
| D04 test content/scoring | A06, A07 | **B04** internal levels/components/rubrics/thresholds/course mappings/rights and separately approved native academic grading/progression policy; never TOEFL-style scoring by assumption |
| D05 moderation/retests/appeals | A06 | **B05** assessor/conflict/moderation/accommodation/retest/validity/interruption/appeal policy |
| D06 admission conditions | A10 | **B06** eligibility, conditions, approvals, offer expiry/acceptance; no automatic exemption |
| D07 legal/financial configuration | A08, A11 | **B07** company/currency/tax/pricing/clearance/payer/aid/refund rules and fee scope |
| D08 compensation/work | A09 | **B08** employment classification, pay basis, payable units and statutory rules, plus native-path proof |
| D09 records/privacy/licensing | A02, A03, A06, A07, A12 | **B09** consent/legal bases, content/recording rights, retention, legal hold and deletion/export policy; external examination integration excluded |
| D10 roles/approval separation | A03, A04, A10, A13 | **B10** named approvers, scoped roles, account separation, self-approval exclusions and break-glass policy |
| D11 delivery/device/offline scope | A02–A04, A06, A13 | **B11** staff-assisted versus online scope, supported devices/accessibility and any offline delivery requirement; no new UI chosen |
| D12 operations/recovery | A13 and production gate | **B12** topology/operators, RPO/RTO, capacity, security and recovery targets; existing Phase 2 gates remain open |
| D13 minimum extension records | A01, A06, A09, A12, A13 | **B13** approve justified entity/technical-record inventory only after checking native facilities; no duplicate masters or unproven payroll bridge |

**Decision-lock result:** five DECIDED boundaries, five CONDITIONAL decisions, three BLOCKED capabilities. The record is decision-complete in coverage, **not globally implementation-ready or approved**. See [IMPLEMENTATION-READINESS.md](IMPLEMENTATION-READINESS.md) for slice-level readiness and required user approval.

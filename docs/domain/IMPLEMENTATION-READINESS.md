# Phase 3 implementation-readiness gate

Date: 2026-09-14. **Architecture review only. Implementation authorization: NOT GRANTED. Architecture approval: NOT GRANTED. Deployment/production approval: NOT GRANTED. Production acceptance: REJECT.**

The [decision record](ARCHITECTURE-DECISIONS.md) is complete in topic coverage: 5 DECIDED, 5 CONDITIONAL, 3 BLOCKED. The [domain contract](DOMAIN-CONTRACT.md) is authoritative for this review. Neither implies that all business policies are known, all native paths are containable, or the whole domain is implementation-ready.

## 1. Meaning of readiness labels

The required labels below describe **different dimensions**, not mutually exclusive release permissions:

- **READY FOR IMPLEMENTATION:** the listed bounded architectural requirement is specified sufficiently for an eventual authorized slice; this gate authorizes **no coding**, including these rows.
- **WAITING FOR EXPLICIT BUSINESS DECISION:** named choices/parameters/owners are missing; do not supply defaults silently.
- **DEPENDENT ON UPSTREAM BEHAVIOR:** exact extension/native transaction/permission/history behavior needs source-level design and reproducible hosted proof. This is not a request to modify upstream.
- **BLOCKED BY UNRESOLVED PHASE 2 PRODUCTION GATES:** the production use of **every** future slice remains blocked. It does not erase the distinction between design readiness and an eventual separately authorized isolated experiment.

## 2. Slice-level checklist

| Requirement / decision | Design-readiness category | What remains before any implementation or promotion |
|---|---|---|
| A01 no-enrollment placement routing and native subject links | **READY FOR IMPLEMENTATION** (boundary only) | Explicit architecture/slice authorization; B01/B02 determine usable identity/consent path. No fake Applicant/Student/Program/Enrollment |
| A07 internal-only naming and result/claim exclusion | **READY FOR IMPLEMENTATION** (boundary only) | Explicit authorization; carry exclusions through fields, reports, APIs, exports and content review. No CEFR/official/mock TOEFL feature |
| A08 single invoice/ledger owner and tuition producer rule | **READY FOR IMPLEMENTATION** (ownership contract only); **WAITING FOR EXPLICIT BUSINESS DECISION**; **DEPENDENT ON UPSTREAM BEHAVIOR** | B07 approved; every native fee writer identified/contained; native generation, advances, amendments and replay reconciled |
| A10 separate admission decision and enrollment completion | **READY FOR IMPLEMENTATION** (state/authority contract only); **WAITING FOR EXPLICIT BUSINESS DECISION**; **DEPENDENT ON UPSTREAM BEHAVIOR** | B06/B10; native Admitted/Student/Customer side effects and mapper cannot skip approval |
| A12 separate source-owned metrics and derived-data rules | **READY FOR IMPLEMENTATION** (semantic boundary only); **WAITING FOR EXPLICIT BUSINESS DECISION** | Named stewards, policy/denominator/retention/disclosure decisions; tests for placement/academic separation and native reconciliation |
| A02 identity and activation | **WAITING FOR EXPLICIT BUSINESS DECISION**; **DEPENDENT ON UPSTREAM BEHAVIOR** | B01 actual email/merge/claim/recovery policy; native required fields, returning Student and premature invitations tested |
| A03 guardian/proxy access | **WAITING FOR EXPLICIT BUSINESS DECISION**; **DEPENDENT ON UPSTREAM BEHAVIOR** | B02/B09; no applicant-only relationship treated as current Guardian login entitlement; revocation and private evidence tests |
| A04 staff/self-service account separation | **WAITING FOR EXPLICIT BUSINESS DECISION**; **DEPENDENT ON UPSTREAM BEHAVIOR** | B01/B10 account policy; strict current guard retained; usability, actor linkage and offboarding proof |
| A05 rolling/repeat representation | **WAITING FOR EXPLICIT BUSINESS DECISION**; **DEPENDENT ON UPSTREAM BEHAVIOR** | B03; prove genuinely valid keys or continued-participation semantics. Independent same-key repeat remains BLOCKED; do not invent a schema workaround |
| A06 internal level policy, components, review and retakes | **WAITING FOR EXPLICIT BUSINESS DECISION** | B04/B05/B09/B11; approve actual language-level/rubric/course-mapping/retake and delivery policies. No TOEFL defaults, no assumed total or CEFR labels |
| A09 compensation and native payroll input | **WAITING FOR EXPLICIT BUSINESS DECISION**; **DEPENDENT ON UPSTREAM BEHAVIOR** | B08 and native path proof; BLOCKED until one justified input path per pay basis exists, without duplicate salary authority |
| A11 history-affecting cancellation | **WAITING FOR EXPLICIT BUSINESS DECISION**; **DEPENDENT ON UPSTREAM BEHAVIOR** | B03/B07 plus history/finance/recovery plan. BLOCKED; source shows Course Enrollment deletion |
| A13 server enforcement/coordination | **WAITING FOR EXPLICIT BUSINESS DECISION**; **DEPENDENT ON UPSTREAM BEHAVIOR** | B10/B11/B13, native writer inventory, hook composition, supported containment and negative route/race/recovery tests |
| Privacy, content rights, delivery/accessibility and minimal entity footprint | **WAITING FOR EXPLICIT BUSINESS DECISION** | B09/B11/B13; no extra recordings, official-exam evidence entity, offline protocol or technical platform added by assumption |
| Deployment and operation of any slice | **BLOCKED BY UNRESOLVED PHASE 2 PRODUCTION GATES** | B12 and current production ledger: dependencies, full deployment boundary, data-store/host durability, independent recovery/rollback, capacity/monitoring and wider security/business coverage |

No checkbox is evidence of implementation. No domain runtime test, migration, end-to-end transaction or approval was performed in this architecture gate.

## 3. Explicit decisions/approvals required from the user

Before implementation, approve/revise this contract and identify the authorized slice; explicitly agree how isolated work relates to still-open Phase 2 gates. Then supply or delegate the applicable inputs to accountable owners:

1. **B01 identity/accounts:** acceptable identity/merge evidence, learners without unique email, legitimate managed mailboxes, activation/recovery and desired applicant access.
2. **B02 guardian/proxy:** permitted guardians/delegation, adult/minor distinctions, evidence, expiry and whether pre-admission online proxy access is actually required.
3. **B03 academic calendar:** real intake periods, overlap, independent same-term repeat requirement, prospective transfer/withdrawal and preservation of earned history.
4. **B04 placement and separate academic policies:** internal English-level vocabulary, sections/components, human/objective modes, rubrics/units/cutoffs/rounding and course-level recommendation mappings. Separately approve native academic grading scales, weights, pass/progression criteria and correction authority. No official/mock TOEFL or default CEFR outputs.
5. **B05 placement operations:** assessors, conflicts/moderation, accommodations, interruptions, retest interval/validity/effective-result and appeal rules.
6. **B06 admission:** eligibility/prerequisites, conditions, approver separation, offer validity/acceptance. No exemption is assumed from external scores/payment/prior learning.
7. **B07 finance:** legal companies, currency/tax/fiscal rules, price/clearance/deposits/credit, aid/refunds/payer relationships and placement fee scope. Invoice authority is locked; amounts/policies are not.
8. **B08 workforce:** employment classification, salary/hour/session basis, legally payable work/cancellations/leave/overtime and payroll jurisdiction. Native input-path evidence is also required.
9. **B09 privacy/rights:** recording/content permissions, sensitive disclosures, retention/legal holds and correction/export/deletion obligations.
10. **B10 authority:** actual role assignments, independent approvers, account-separation acceptance, delegation and audited break-glass rules.
11. **B11 delivery scope:** staff-assisted versus applicant online use, supported devices/accessibility and whether offline placement is a genuine requirement.
12. **B12 operations:** accountable operators, deployment/security topology, recovery/key custody, RPO/RTO, capacity and monitoring targets; these do not approve deployment.
13. **B13 extension necessity:** approve the minimum logical/physical entity inventory after native facilities are assessed; in particular no unproven work-pay bridge, duplicate master or unnecessary technical platform.

These are explicit missing inputs, not invented assumptions or a request to approve all possible features at once. The user can narrow scope (for example no online pre-admission proxy); the matching decision and readiness rows must then be revised before implementing that narrower slice.

## 4. Mandatory proof obligations after authorization

- **Placement integrity:** no Student/Enrollment prerequisite; no native academic or official-score writes; preserved attempt/rating/decision history; section completeness, reviewer/rationale, valid internal-level/course mapping; no automatic TOEFL/CEFR conversion.
- **Lifecycle:** native Applicant/Student status does not collapse placement, admission, enrollment or participation; retesting is not academic repetition; eligibility and actual registration rechecked separately.
- **Authorization:** Desk, native RPC including mapped enrollment, generic REST/list/search, imports, background/scheduled jobs, cancellation, private file/ZIP/print/export/report/realtime and revoked assignments. UI-only success never satisfies this requirement.
- **Consistency/retries:** conversion, active decisions, capacity and enrollment uniqueness races; duplicate charge/input/webhook; different payload for same key; effects already committed on lost response; safe reconciliation rather than blind replay.
- **Finance/HR:** one invoice/GL chain per obligation, one native payroll input per approved pay basis, separate approved/posted/paid states and reconciliations. No custom ledger or payroll algorithm.
- **History/recovery:** cancellation dependencies and forward/restore-based recovery, scoped exports after revocation and backup/retention treatment. Existing patch-upgrade proof does not qualify these domain transitions.
- **Reporting:** explicit metric steward/grain/units/denominator/as-of and source revision; separate placement versus academic outputs; no official-score headers/labels; scoped aggregates and drill-downs.

## 5. Architecture consistency re-audit

These are **document/source review conclusions, not executed application tests**. The associated machine record is [architecture-gate-review.json](architecture-gate-review.json).

| Mandatory check | Contract result / evidence |
|---|---|
| Entrance placement before the relevant enrollment | A01; contract §1 routing; returning Student may have prior history, never a fabricated new enrollment |
| No fake Student/Enrollment or placeholder Program | A01/A02; S1/S2; no placement command owns those writes |
| No academic results created by placement | A06; contract §§1–3 and ownership table |
| No official or mock TOEFL score generation/representation | A07; contract §§1/3/8; external result entity excluded |
| Current English level, course recommendation and rationale exist | A06; released Placement Decision output contract; numeric policy still conditional |
| Section results/assessor review where applicable | A06; H/M options; no forced official exam component set |
| Recommendation, admission and actual enrollment distinct | A10; S2/S3/S8; contract §4 |
| Retests preserve prior attempts and decisions | A05/A06; new attempt and explicit supersession, no overwrite |
| Placement owner and private access explicit | A02/A03/A06/A13; contract §§2/5 |
| No placement/academic metric mixing | A12; contract §8 source/grain and output rules |
| CEFR claims limited | A07: absent baseline; any future internal reference separately approved and explicitly not certification |
| One canonical billing flow | A08; no parallel enrollment/batch/legacy Fees producer for tuition |
| One canonical payroll-input authority | A09: HRMS/native input only; pay-basis path blocked, not silently selected |
| Ownership/permissions respect states | Subject/assignment/purpose/release predicates; conditional mixed-role/guardian capabilities not assumed working |
| Native permission-bypass routes contained by design | A13; S8. **Containment implementation is unproven**, with explicit denial requirement for unqualified paths |

## 6. Change-scope and release boundary

The audit compares the final documentation patch with baseline commit `e0cafcd5bab2851dec3c3b7917c81ef174816094` and records hashes/ref identity in [architecture-gate-review.json](architecture-gate-review.json).

Only `docs/domain/` documentation/decision metadata may change. No application code, schema/migration, API, UI, dependency/lock version, foundation pin, upstream source, deployment config or infrastructure is changed. Main remains at its original commit; existing Phase 2 engineering evidence and acceptance documents remain byte-identical. No new runtime proof or risk exception is claimed. This gate does not relabel any failed test or turn production **REJECT** into conditional acceptance.

**Final readiness statement:** architectural coverage and explicit decisions are complete for review. Five locked boundaries can guide an eventual authorized slice; five decisions remain conditional and three capabilities blocked. The full domain is **not unconditionally implementation-ready**. User sign-off, the listed decisions, native-behavior proof and separate implementation/deployment authorizations cannot be replaced by internal document consistency.

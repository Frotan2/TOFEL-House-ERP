# Placement Test: Independent Operational Readiness Review

**Status:** DRAFT / NOT APPROVED FOR LIVE CANDIDATES  
**Scope:** Reception-to-placement intake, invigilation, candidate experience,
security and branch isolation, scoring, review, release and admissions handoff.
**No seed candidates, real customer records, or operational activation.**

## How this should work for a real customer

1. A receptionist searches by real name or contact and registers a walk-in inquiry
   without creating an invented email address or duplicate Student.
2. An authorized placement officer establishes a verified candidate identity and
   Branch of origin. A branchless case must never be offered to Reception.
3. A publisher selects an approved, published question blueprint and operational
   policy; allocation creates the sealed form and prevents family reuse.
4. A separate invigilator checks the candidate's physical identity, test station,
   program and Branch before verifying and delivering a digital attempt.
5. The candidate needs a **separate, purpose-built authenticated exam session**:
   large legible questions; listening audio where needed; accessible keyboard
   navigation; visible time and saved/unanswered indicators; reconnect recovery;
   explicit final submission. **The current system does not have this safe
   candidate login/kiosk.**
6. The staff console in `th-placement-invigilation` is for a trusted invigilator.
   It provides a bounded, branch-filtered Attempt picker, server-checked attempt
   status, physical identity confirmation, verification, timed-session start,
   answer navigation and recovery of confirmed server responses; it must not be
   handed to a candidate because the same Desk account also has administrative
   actions. The verified exam is bound to its original invigilator; any staff
   handover requires a separately authorized and audited workflow, not yet built.
7. The scorer uses server-side keys, not browser-visible answers. Independent
   assessment, review, finalization and release stay separate, audited roles.
8. An approved level and native Program mapping must be calibrated, published
   and traceable to the exact academic term before an Admission Officer creates
   the native applicant/decision. No fees or enrollment should be created from
   an unapproved placement result.

## Verified gaps and dispositions

| Area | Observed in source | Remediation / required acceptance |
| --- | --- | --- |
| Registration | A walk-in has no verified link to a native candidate User; `create_case` still requires an enabled native User subject. | **BLOCKER**: devise and implement a secure unique identity bridge without inventing addresses or extending staff privileges to candidates. |
| Branch provenance | Earlier case/attempt workflow did not carry an authoritative Branch. | Draft adds immutable Case branch, requires it in production, scopes reception and all eight live exam commands. Requires MariaDB cross-branch tests. |
| Invigilator UI | Legacy command page requires manual Attempt/version/occurrence fields. | Draft adds a supervised staff workspace with question-by-question navigation, saved revisions, secure resume, and confirmation before seal. Requires browser and keyboard evaluation on Windows. |
| Candidate self-service | No candidate-only authenticated exam route; invigilator role cannot safely be lent to students. | **BLOCKER**: a separately authenticated candidate token/session limited to exactly one allocated attempt, no Desk route, expiry, revocation and anti-replay. |
| Audio and productive skills | Current `validate_content` accepts objective single-choice / true-false only and rejects Speaking/Writing. | **BLOCKER for full coverage**: approved multimedia player, recording/storage, scoring rubrics, moderation and accessible accommodations. |
| Scoring / level assignment | Current `course-map-v1` uses `any_correct`: one correct answer can assign a course. | **BLOCKER**: draft now fails closed in production. Academic Owner must approve calibrated per-skill thresholds, validation dataset, moderation and native Program mapping before release can be enabled. |
| Session recovery | Delivery projection was returned only on initial POST, without a safe way to reload responses. | Draft adds GET recovery for authorized invigilators only, branch and live-deadline checked; latest submitted response revisions only. |
| Test clock | Server enforces overall deadline; current UI shows server time but not a candidate-visible accurate countdown. | Candidate portal must use an authoritative clock and server-verified deadline; no browser clock used for authorization. |
| Exam integrity | Different roles handle allocation, invigilation, scoring, review and release. | Require MariaDB role separation, parallel response revision, same-key replay, timeout and case-transfer tests. |
| Final admission | Native Student Applicant / Student / Program mapping remains a separate protected admission journey. | **BLOCKER**: verify candidate identity→case→released decision→Applicant→Student linking, old students, school year, Branch and duplicate denial in the native integration suite. |

## Acceptance matrix to execute before production

- **Receptionist:** new visitor, no phone, repeated visitor, visually searchable
  history, follow-up, cross-branch denial and no accidental payment or enrollment.
- **Candidate:** identity check, first-day instructions, accessible controls,
  long/short questions, reconnect, no answers leaked, wrong-login refusal,
  timeout, interrupted network, final submission, no administrative navigation.
- **Invigilator:** separate role, known case, foreign case, wrong operator,
  expired deadline, reload with confirmed responses, concurrent saves and
  escalation on unknown write outcome.
- **Assessor and reviewer:** confidential keys, scorer/reviewer separation,
  inconsistent responses, corrected moderation, second attempt and best-result
  policy evidence.
- **Admission officer:** expired/revoked results, foreign branch, new applicant,
  returning applicant, exact linked native Student, unknown native Program,
  concurrent intake, no invented email address.
- **Owner / release engineer:** exact-head CI; real isolated MariaDB HTTP and
  Windows UI checks; immutable schema migration; backup/recovery; independent
  review; explicit Owner approval.

## Release rule

The current work is an *engineering and safety improvement* only.
Passing source-unit tests is not equivalent to validating an actual exam.
Until the candidate identity model, candidate-only portal, academic course
mapping, content coverage and native Windows acceptance are independently
qualified, the product must remain **TEST PACKAGE — NO REAL DATA**.

# TOEFL House Student Journey — Reception → Placement → Admission → Student

**Status:** Engineering review, Draft PR #124. **NO-GO** for real learners
until native Frappe/MariaDB and Windows multi-role acceptance pass. All user
interfaces and labels remain English LTR.

## Required operator journey

| Station | Staff action | Exact record | Safety boundary |
| --- | --- | --- | --- |
| Reception | Search before registering, capture actual name and optional phone, confirm Branch | TH Reception Inquiry | Inquiry alone does not confer Student status, billing, or access to an exam |
| Reception → Placement | Mark Awaiting Placement and hand over reference | Inquiry.name | Inquiries must have verified Branch and be available to authorized publisher |
| Placement Publisher | Link Inquiry, allocate from published approved blueprint | TH Placement Case → Attempt | Real visitor gets opaque internal `THV-` candidate reference; no email, User or fabricated address |
| Invigilator | Physically check person, supervise digital attempt | TH Placement Attempt | Candidate must never be given staff Desk credentials; separate exam kiosk is not yet qualified |
| Assessor/Reviewer/Releaser | Independent scoring, review and release | TH Placement Decision | Current real course-level mapping is uncalibrated; production release **blocked** |
| Admission Officer | Create native Applicant only from released decision | Student Applicant | Unique internal candidate identity and original Reception reference, real email optional |
| Admission Approver | Validate separate approval and offer; convert one Applicant | Student (plus native Customer) | Native Student creation only via approved command, not an unrestricted desk form; no Website User auto-created |
| Enrollment Officer | Validate identity again, then submit Program Enrollment | Program Enrollment | Student enabled, native Applicant link, candidate reference, Branch and original Inquiry must still match |
| Reception — student service | Lookup by Student ID, Candidate reference, name, or optional real email | Branch-limited Student projection | Clearly show disabled students; no automatic reactivation or tuition collection |

## Problems found and concrete remediation

1. **Identity drift before enrollment:** earlier returning admission checked only
   declared existing Student; enrollment could proceed without revalidating
   the full referral identity chain. The updated enrollment gate checks
   case/attempt, Reception Inquiry, native Applicant, native Student, exact
   candidate reference, native Applicant link and Branch before writing
   Program Enrollment. It also denies disabled learners.
2. **Post-conversion identity tampering:** read-only Desk fields are not
   server-side protection. The new native Student controller and Applicant
   validate hook prevent normal form writes changing `student_applicant`,
   `th_candidate_ref` or `th_reception_inquiry`. Identity corrections must
   be a separately approved audited process, never a silent overwrite.
3. **Bypassing intake via native forms:** in production, direct creation
   of Student Applicant or Student outside the appropriate active guarded
   command is denied. Native Education validations, Student-to-Customer
   linkage and accounting responsibilities are retained.
4. **Email-dependent search:** Reception now searches with internal Candidate,
   Student and Inquiry references in addition to name, email and optional
   contact; staff displays verified walk-in name and internal reference
   together for admission handover.
5. **Disabled students invisible:** previous Reception lookup filtered
   `Student.enabled=1`. The branch-limited lookup now also locates disabled
   records and labels them **Inactive**, without a reactivation button or
   authorizing enrollment.

## Explicit unfinished release blockers

- **Returning person with a NEW inquiry:** the current `THV-` reference
  derives from the initial inquiry, not from an independently established
  permanent person identity. A fresh visit may produce a distinct reference.
  The system **must not silently merge** people by same name, household phone,
  email-like placeholder or guessed Tazkira. Requires a governed staff
  verification and second-authority review, repeat-visit linkage, and a
  safe tested re-entrance to the existing native Applicant/Student (no
  duplicate Student or Customer). This is **not complete**.
- **Identity/name corrections:** the original name and native identity links
  need an approved, versioned correction process; normal form editing cannot
  reassign them. The new guard refuses unauthorized corrections but does not
  yet provide the approved repair workflow.
- **Candidate-only digital exam station:** no independently authenticated
  candidate kiosk with one-use attempt binding, timeout and revocation. Staff
  placement Desk credentials may never be shared.
- **Academically justified mapping:** real placement level recommendation
  and release remain blocked until calibrated and independently approved.
- **Independent native acceptance:** still need actual MariaDB migration of
  optional Student email and unique identity fields, real no-email/no-phone
  visit-to-Student replay, first enrollment, disabled/foreign branch refusals,
  concurrency/idempotency, browser keyboard checks and Windows recovery.
- **Optional future portal:** email-free students are valid offline learners;
  future online access requires separate proof and opt-in, never automatic
  Website User creation.

## Concrete native acceptance scenarios

1. New person with **no email and no phone**, proper Branch: Inquiry →
   Placement → reviewed decision → Applicant → Student → enrollment. Confirm
   one Student, one Customer, one submitted Program Enrollment and **zero
   Website Users, unsolicited emails, invoices and tuition postings**.
2. Two children sharing one household mobile; different people remain
   separate and Branch-scoped. Never auto-merge.
3. Wrong Applicant reference, changed Student link, wrong Inquiry/Branch,
   expired/rejected result, Student disabled, and foreign staff account:
   deny before any enrollment, invoice or roster write.
4. Returning Student with new Inquiry: the unfinished verification lane
   must refuse creating a second Student until approved. Test approval
   concurrency and audit before enabling this route.
5. Simultaneous duplicate Student and enrollment attempts: enforce
   database-unique candidate references, native Applicant link and
   per-program/year/term enrollment uniqueness.
6. Migration before activation, Customer/Fees intact, backup/restore,
   branch revocation and independent two-role acceptance on the Owner's
   Windows deployment.

This document records engineering facts and acceptance requirements; it
does not grant production authorization. **TEST PACKAGE – NO REAL DATA.**

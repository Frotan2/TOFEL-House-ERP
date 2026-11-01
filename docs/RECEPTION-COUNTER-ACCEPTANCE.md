# TOEFL House — Reception counter acceptance

**Engineering status:** Draft PR #124. NOT a physical employee-login acceptance.
The staff UI is English LTR and the actual Owner Windows ERP was not
accessed. Tests use synthetic records, pinned native schemas and branch-
aware code projections; no real learner information was entered.

## One visitor, one traceable journey

1. Reception searches by **name, optional phone, printed Inquiry ID,
   Candidate reference or native Student ID** before creating anything.
   Native document IDs require an exact match; user-visible text/name
   search supports contained matching. All results use branch-scoped,
   allow-listed projections.
2. A new inquiry requires only a real name and valid Branch. Phone and email
   are not mandatory. Reception does NOT create a Student, Website User,
   invoice, fee or placement decision.
3. If the exact same **name + normalized contact + Branch** has an open
   inquiry, the receptionist receives a "search and update" error. A
   database-unique, nullable open identity stamp closes the simultaneous
   double-click/two-counter race. The key is released on closing; no-phone
   records have no stamp. This is **duplicate prevention, not proof of
   personal identity**; different people on one household phone may coexist.
4. The Admission Officer's Applicant name is prefilled from the exact
   branch-verified Reception Inquiry. In production, the server rejects
   an Applicant name that differs from the registered person, even if
   the candidate reference is copied correctly. An Applicant or Student
   cannot later be silently renamed to another person through native
   Education forms; use an independently reviewed identity correction,
   which is still a separate acceptance requirement.
5. When Ready for Placement, mark Awaiting Placement; the desk assigns
   **Placement Publisher** as the next role and displays the Inquiry ID.
   The Publisher links the exact inquiry and Branch and generates an internal
   non-authenticating Candidate ID. Once a case consumes the referral,
   Reception cannot downgrade it to Contacted, though notes and closure
   remain permitted.
6. The desk displays source-verified stage transitions for a live inquiry:
   Awaiting placement allocation; Placement case opened; Placement result
   released; Admission in progress; Student profile created; Enrollment on file. Student profile creation alone **never** means an approved
   enrollment, paid tuition or assigned class.
7. The desk checks native `Student Applicant`, `Student`, and submitted
   `Program Enrollment` through the same Branch scope. It never links by a
   name-only guess, family phone, or a fabricated email. Conflicting
   applicant/Student links are routed to Academic Manager review.
8. Student converted but NOT rostered must still be visible to the correct
   Branch when their native Applicant/Admission linkage is verified.
   A foreign, mixed or branchless roster disallows disclosure across
   branches. Disabled Students are searchable as **Inactive**, not silently
   skipped or automatically re-enrolled.
9. Any approved admission-to-enrollment command independently checks
   the native candidate, original Reception inquiry, matched Branch and
   Student Applicant relationship again immediately before writing
   Program Enrollment.

## Scenarios to run with six role accounts on an isolated Owner Windows site

| Test | Expected result |
| --- | --- |
| Visitor without email or phone | Receives Inquiry ID; no User, Applicant or Student yet |
| Two different people share household number | Two separate referrals; no auto-merge |
| Two Reception counters submit same name/phone/Branch simultaneously | Exactly one open inquiry; other counter sees a clear duplicate warning |
| Open inquiry changed to Awaiting Placement | Placement Publisher is next role |
| Inquiry already consumed by case then downgraded to Contacted | Denied and audited; previous state remains |
| Placement result issued | Desk shows released stage, not a fabricated enrollment |
| Applicant approved and Student created, before any class membership | Correct Branch can find native Student; other Branch cannot |
| One Student active in classes at Branches A and B | Neither single-Branch counter receives a mixed-scope Student profile |
| Student converted but no submitted Program Enrollment | Student profile created; Enrollment Officer next |
| Correct submitted Program Enrollment | Enrollment on file; Academic Manager verifies that its academic period matches the inquiry |
| Disabled Student | Visible as Inactive; no reactivation or enrollment control |
| Same Candidate ref on two native applicants | Stop and refer to Academic Manager, do not pick one |
| Printed Student/Inquiry ID with a Branch permission | Exact lookup works and intersects the scoped name list |
| Native Student created directly through Education form | Denied in live mode unless authorized conversion command |
| Unmigrated metadata or index not installed | Installation acceptance fails; no actual candidate records |

**Still blocked:** an approved person-verification/merge process for a
returning student with a brand-new Inquiry, independent candidate exam
kiosk, academically calibrated placement course mapping, live
MariaDB+Windows role/branch acceptance, backup/recovery and Owner
release approval. An internal Candidate reference is never a login token.
**TEST PACKAGE – NO REAL DATA.**

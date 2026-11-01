# Afghanistan-first, email-optional candidate and student intake

**Status:** Implementation under qualification in Draft PR #124. This is not an
Owner release authorization and must not be used to open real candidate data.

## Day-one operator journey

1. **Reception:** Search for an existing inquiry, applicant and Student using
   the branch-limited desk. Record the visitor's actual name, authorised Branch,
   intended course and **optional** mobile. Do not require an email, telephone,
   national ID, date of birth, document photo, device or online account.
   Write only necessary follow-up details. Shared household phones are not
   unique identities. Give the visitor their inquiry reference and set status
   to **Awaiting Placement** when referred for a test.
2. **Placement Publisher:** Confirm the inquiry exists, is at the same Branch
   and is ready. On Create placement case, leave **Candidate reference** empty
   for a real visitor, select the Branch and enter a real purpose and inquiry
   reference. The server produces an opaque `THV-...` reference bound to
   that inquiry; it does **not** create a User/email/login or accept a
   staff-invented candidate account.
3. **Invigilator:** Physically confirm the person and the issued inquiry.
   A branch-scoped staff workstation can verify, start, resume and seal the
   digital attempt. The invigilator must **not** share a Desk login with
   the candidate. A separate candidate kiosk is a required product gate
   before unsupervised candidate operation.
4. **Admission Officer:** After the independent marker/reviewer/releaser and
   valid academic level mapping, record the Student Applicant under the
   original internal candidate reference. The native applicant email stays
   **null** if the person has none. Never insert a synthetic address.
5. **Admission Approver:** After independently approved admission and offer
   acceptance, convert to native Student. Student has an optional email via
   an app-owned, versioned Property Setter; its internal Student name and
   `th_candidate_ref` remain the identity. The overridden native Student
   validation never creates a Website User or sends welcome mail. Billing,
   customer creation and enrollment remain native and separately guarded.

## Data integrity and safeguarding

- The internal candidate reference is an **identifier**, not a bearer token or
  proof of identity. Never allow it alone to log in, see exam questions or
  retrieve a student's data.
- A name or household phone match is a **possible duplicate prompt**, never
  authorization to merge records. A returning visitor must be manually verified
  against an existing native Student and previous applicant by authorized staff.
  A controlled returning-identity lookup/merge and repeated-inquiry workflow
  **remains a release blocker**; it is unsafe to silently combine people.
- All sensitive reads and writes preserve authenticated staff roles, branch
  scope, immutable origin, audit receipts and document controller protection.
- If a person later supplies a real email, saving contact information does not
  grant online access. Explicit account enrolment and identity verification
  are a separate consent-based operation.
- Do not force or centrally store a Tazkira number, document image, biometric
  or minor's guardian details for ordinary English placement. Record only
  evidence actually needed by approved institute policy, protected under
  appropriate role permissions and retention rules.
- An operator must never "solve" missing email by giving the candidate the
  receptionist's, publisher's or invigilator's credentials.

## Deployment / acceptance

- On an isolated qualification site, run migrate and confirm:
  `Student.student_email_id` is no longer required, both Applicant and Student
  expose the unique `th_candidate_ref` field, and
  `THEmailOptionalStudent` is active. If this metadata is not installed,
  the admission command stops before Student conversion.
- Test a real-name/no-email/no-phone inquiry, correct-Branch placement,
  independently checked attempt, valid reviewed academic outcome, admission,
  conversion and enrollment, without any User being created. Test different
  people sharing a phone, duplicate submissions, cross-Branch denial,
  returning Student reuse, timeout, loss of connection, backup and restore.
- Current placement algorithm `any_correct` is not academically calibrated,
  so real course assignment/release stays blocked. No physical Windows
  session, live database or real candidate test has been qualified through
  this Draft PR. The installed package remains **TEST PACKAGE – NO REAL DATA**.

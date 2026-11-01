# TOEFL House — Reception daily registration (staff procedure)

**Scope:** front-counter intake only. This page is for an authorized Reception login. No developer tools, JSON editing, or manual database changes are part of daily registration. Changes in PR #124 remain **TEST PACKAGE — NO REAL DATA** until release acceptance.

## Walk-in: no email or placement result
1. Sign in with your own Reception account and open **TOEFL House Reception Desk**.
2. Under **New visitors and follow-ups**, choose **Register a new visitor**.
3. Enter the person's **real full name**. Add an optional contact phone, interested program and brief operational note. Every inquiry needs a valid Branch. With one assigned branch the backend selects it; with multiple assigned branches the staff member must choose one. An unassigned branch is rejected.
4. Save once. The system provides a unique internal inquiry reference and keeps an auditable operation receipt. The visitor appears in the follow-up queue.
5. Search by name or phone before registering another contact; same-family phone numbers alone are not proof of the same identity.
6. Use **Update follow-up** to mark **Contacted**, **Awaiting Placement**, or **Closed**, adding the real next-step note. The queue displays only a short preview of the latest note. Closing a visit requires explicit confirmation; its record remains in the audit trail and is no longer editable from this queue.

**This is not student registration.** No actual Student, User, placement case, academic enrollment, receipt, invoice or tuition charge is created merely because a visitor walks in. Do not enter invented or third-party email addresses.

## After verified placement
1. A designated Placement Publisher must have a separately verified candidate account and create/allocate the placement case. The invigilator, assessor, reviewer and releaser execute their respective independently authorized steps.
2. A *released and still-valid* result appears in **Ready for admission intake** only when its original Placement Case has a verified branch that this Reception account may access. Expired, branchless or foreign-branch results must not appear, even if present in history. The Placement Publisher must choose the real branch when creating the case.
3. If the candidate already has a native Applicant record, **Open admission** uses that record. An already-Admitted returning applicant must have exactly one visible, enabled, natively linked Student with the same verified email; only then does **Open returning admission** prefill the Student reference. Otherwise the desk stops and asks Academic Manager to resolve the identity or branch before a new admission. For new applicants an Admission Officer uses **Record applicant** and enters the verified real first name, optionally surname, an existing native Program, academic year and authorized branch.
4. The admission then follows **Draft → Review → Approved / Conditional / Deferred / Rejected**. A reviewer and approver must have the required distinct authority.
5. **Conditional** requires an independent Admission Approver to record evidence through **Verify conditions**; do not attempt student conversion while still Conditional. The original deciding approver may not approve their own conditions.
6. Once **Approved**, an Admission Officer records offer acceptance; an Admission Approver converts into the native Student. **Enrollment Officer** then submits the real Program Enrollment.
7. Academic staff place the student in a class with available capacity. Authorized finance staff issue tuition separately under the Owner-approved billing policy, without duplicate billing.

## Student class, timetable and teacher — front-counter answers
1. In Reception Desk, search the enrolled Student by their exact Student ID, Candidate reference or verified name. Do **not** equate an initial Inquiry or an approved Applicant with a Student.
2. The latest submitted **Program Enrollment** establishes the academic **program, year and term** shown in the result. It does **not** establish a class assignment. Confirm the period the learner is asking about before promising their current class.
3. **Enrolled, class not confirmed** means no verified active roster membership in a planned or active native Student Group matches that particular submitted enrollment. A class existing for other students is not a match. Ask Teaching Scheduler to assign/confirm the learner; Reception must not change roster membership.
4. **Class planned** means this learner has an active native Student Group Student roster row in a planned class. No meeting time or permanent teacher is promised yet.
5. **Class assigned, schedule pending** means the confirmed active class has no upcoming Scheduled Course Schedule record. Ask Teaching Scheduler for the dated timetable. Do not tell the learner that the usual weekly period is already published.
6. **Class assigned, sessions scheduled** shows the class ID/name and up to three actual dated Course Schedule records: date, start/end time, course, room, and *session instructor* only when a valid native Teaching Assignment covers that class/session/date and the Instructor is active. Otherwise show **Instructor assignment unverified** and refer to Teaching Scheduler. A dated session is not a weekly recurrence or a permanent teacher assignment. Only upcoming Scheduled sessions are shown: a meeting whose end time has already passed today is no longer called the next session, and malformed times require academic verification. Cancelled/postponed meetings are not advertised.
7. If the student is **Inactive**, the enrollment read is incomplete, more than one matching class roster appears, or a timetable read is truncated, stop and refer to Academic Manager or Teaching Scheduler. Do not guess a class, room, teacher or attendance status. Do not reveal or act on records from another Branch.
8. An already **Scheduled** session may later overlap a class-wide suspension or an individual attendance restriction. The lookup now shows **Class sessions under review** (Teaching Scheduler) or **Attendance eligibility needs review** (Academic Manager) instead of announcing confirmed meeting/attendance. The suspension's private reason and the names of other students must not be displayed. If the suspension window is malformed or the bounded evidence is incomplete, stop and refer for verification.
9. A pending class transfer is **not** proof that the learner has moved. Reception search now shows **Transfer REQUESTED** (target class and effective date) only when both source and destination belong to its assigned Branch and the source is the learner's verified current roster. The private reason is never displayed. Multiple pending or overdue requests are referred to Academic Manager; do not promise approval. The native roster changes only after independent authorized execution on the effective date. An overdue request must be cancelled and re-requested rather than backdated. Advanced transfer types remain Owner-deferred.
10. **Available seats and class waiting list:** the native `class_availability` and `waiting_list_board` server endpoints now enforce the Reception login's explicit Branch User Permissions. A class ID, branch parameter or direct API URL cannot select a foreign branch; a Reception login without an assigned Branch gets a permission error. An academic role with a narrower Branch assignment is also scoped. Do not promise a seat or waiting-list position from a different branch, or assume an available seat equals successful enrollment.
11. Reception can explain and search these facts but cannot create or transfer class memberships, change teacher assignments, schedule sessions, mark attendance or alter enrollments. Those actions remain with their authorized academic roles.

## Staff safety and exceptions
- The reception intake workspace is explicitly English LTR, and a test checks authored English-only source strings. Keep authentic visitor names in their original spelling; never manufacture an English name.
- An inquiry is not linked automatically to an email-based candidate account. Only a verified identity and an authorized placement/admission journey may make that association. Never assume two matching names or shared phone numbers are the same person.
- If the result is expired, the case does not exist, the selected Program differs from approved academic placement, or required approver roles are missing: **stop and refer to Academic Manager**. Do not bypass the guards or choose arbitrary levels.
- A Reception account without at least one explicit Branch User Permission is denied access to the desk. The Owner must assign the permitted branch before that account views customer records. Placement cases without branch provenance remain hidden from Reception.
- Save your contact records only in Reception Desk. Do not write sensitive medical or family information in free-text notes; use a short operational follow-up description.
- An interrupted or repeated request should be retried from the **same dialog** so its idempotency key is preserved; opening a separate form starts a new request.
- No final production readiness is implied by successful static tests. Test full Windows on a restored, synthetic-only site first, including role boundaries, same-key replay, branching, candidate verification, admission and ledger reconciliation.

## Acceptance checklist for an independent reviewer
- [ ] All UI labels, statuses, dialogs, validation messages, staff help, and developer-authored code comments in this workflow are in English. Real visitor names remain as provided.
- [ ] Search results never revert to an older query response, even when HTTP requests finish out of order.
- [ ] Double-clicking Save while one registration POST is pending cannot send two requests; a failed request can be retried with the same operation key.
- [ ] Visitor wildcard characters are treated literally, and updating a visit without any changed data does not create an audit revision.
- [ ] New, phone-free walk-in records without any email or candidate account.
- [ ] Afghan and Latin phone numerals normalize and search consistently.
- [ ] Same-key replay yields exactly one inquiry; different-key multi-submit is explicitly monitored.
- [ ] Other-branch Reception is unable to read, query or update the inquiry, including cached receipts.
- [ ] Invalid or expired placement cannot create admission from the queue.
- [ ] Existing applicant does not receive a duplicate-registration action.
- [ ] Conditional admission cannot convert until another approver verifies conditions with evidence.
- [ ] The real Account/Student/Program Enrollment/Fees ledger is unchanged by a preliminary inquiry.
- [ ] The release is signed, CI exact-head passes, and Owner Windows acceptance authorizes use of real data.

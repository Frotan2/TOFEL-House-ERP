# TOEFL House ERP — five-role operational acceptance, 2026-10-26

**Decision: NOT ACCEPTED for customer production.**
**Data policy:** all executable tests use authentic Frappe, ERPNext,
Education and HRMS **document types and operations**, with clearly
synthetic learners, salaries and cash amounts on disposable CI sites.
No customer database was reached or modified; no human impersonation and
no claim of actual authenticated access to the Owner's Windows instance.

## Audit method and evidence boundary

1. Inspected live source of all five Desk controllers, guarded operations,
   user/role bindings and native Education/HRMS source.
2. Reviewed hosted Actions for previous `89bb34ad0`: both Owned suites and
   hosted Windows package smoke passed; **Native failed before full five-role
   acceptance** when a *test fixture* attempted to rebill the same
   Program Enrollment using another Fee Structure. The underlying
   production prohibition on double billing is correct, so **do not
   weaken it**. Product-image qualification failed its exact-source gate.
3. Current branch replaces that invalid fixture with three separate,
   *approved* synthetic candidate→placement→admission→enrollment chains.
   A second acceptance point, `five-role-populated-native-http-journey`,
   now logs in five independent HTTP sessions and requests the installed
   Page and Desk for each role, using populated native student/Fees and
   teaching data, and proves another role's Desk denies access.
4. The separately isolated Chromium browser check logs in as all five
   roles (plus Academic and Configuration roles) and verifies mounted
   Page, route, sections, JavaScript errors and bundled CSS. **That
   fixture has no populated transaction dataset**, so Chromium green
   alone cannot prove daily business execution. The browser fixture
   now seeds an Afghanistan Hamal-to-Hoot fiscal year instead of a
   January-to-December one.
5. Exact-current-commit Native, Chromium, Foundation and physical
   Windows acceptance results must be attached below before checking
   any end-to-end cell as PASS. In-progress CI is *not* a pass.

## Role-by-role walkthrough

| Persona/login role | Native operational expectation and scope | Finding as of source audit | Acceptance result |
| --- | --- | --- | --- |
| Reception: `Reception` | Locate and follow applicant/student intake, placement release, admissions and enrollment; gender-separated cashier collects and hands cash to Finance | `reception.work` offers the view and requests next actions from `Admission Officer`. A user with *only* Reception does **not** automatically receive Admission Officer, Enrollment Officer or native payment authority. A dedicated, audited reception-collection / Finance handover path is not proven by this Desk. | **INCOMPLETE** |
| Finance Manager: `Finance Manager` | Identify posted receipts, dues by Afghan month, advance balances, overdue amounts, expense, native payroll and corrections | Finance Desk contains read projections and Finance Officer actions. Holding *only* Finance Manager does not meet the `Finance Officer` command gate. Native receipt entry, advance allocations, cross-month GL/deferred income and a cutover reconciliation remain separate acceptance items. | **INCOMPLETE** |
| General Manager: `General Manager` | Cross-role funnel, staffing, operational exceptions, service failures, attendance and follow-up | `operations.work` contains funnel, exceptions, staffing and health; limited view intentionally does not grant Finance or Owner write powers. Live escalation and role-specific workflow completion have not been physically tested. | **PARTIAL / NOT SIGNED OFF** |
| Teacher: `Instructor` | See only assigned classes, students, sessions; mark attendance for own scheduled session; inspect work without payroll leakage | `teacher.work` resolves own Employee→Instructor and reads assigned group. Mark-attendance action currently requires `Attendance Recorder`, *not* Instructor. Generic `record_attendance` verifies group/roster but has no own-login-to-session-instructor authorization; blindly giving every teacher the Attendance Recorder role would risk cross-class marking. Implement a separately scoped instructor command and test own vs cross-class refusal before claiming daily usability. | **INCOMPLETE / SECURITY HOLD** |
| Course Owner: `Course Owner` | Versioned academic/fee/calendar policies; see summaries of intake, enrollment, money, payroll, risks and release posture | `owner.cockpit`, Academic Setup and Configuration are role-gated. Solar Hijri income vs actual receipts, outstanding payroll, physical backup/restore evidence, installation acceptance and owner signoff are not certified from the login screen. | **PARTIAL / NOT SIGNED OFF** |

## Required business scenarios before declaring complete

- **Reception:** place a walk-in candidate into the correct cohort, verify
  a late joiner and identity/guardian limits, generate a numbered receipt,
  collect cash at the female counter, hand it to Finance without creating
  a second receipt, and prove that Reception cannot inspect payroll.
- **Finance:** two Shamsi-month Fees for each approved enrollment; partial
  and advance payments, oldest-first settlement, intentional specific-month
  allocation, refunds through approved correction, same-student
  cross-structure duplicate denial, books stock/return, cashier daily
  close by gender, *real GL reconciliation* by worked/billed/received
  month, no double counted advances.
- **General Manager:** tasks and pending approvals visible, role-denied
  record access, separate room/teacher conflicts, exception follow-up,
  report data confined to entitled branches.
- **Teacher:** two distinct logins with distinct courses/classes/rosters;
  successful attendance of an *own* unmarked scheduled session; refusal of
  another teacher's session even if someone grants an auxiliary role;
  Friday closure; evidence of permitted assessment and secure payroll view.
- **Owner:** set fixed GE/EAP class duration to exactly two Shamsi months,
  independent other-program lengths, Friday-only regular closure,
  15th-next-month priority wage report with unpaid balance remaining,
  signed authorization and owner-reviewed native month-close; validated
  local-only backup and disposable Windows recovery.

## Blocking controls — not optional

1. Native five-role populated HTTP test and the real Chromium Page checks
   both pass on the *identical* source commit.
2. Native write/receipt cross-role denial and instructor-own-session
   authorization proven with two teachers and cross-class hostile tests.
3. Customer-equivalent daily Finance workflow and GL reconciled to
   **AFN, Afghanistan Solar Hijri periods**; genuine opening arrears and
   payroll liabilities migrated only following approved cutover and
   backup validation.
4. Physical Windows Docker Desktop install, restart, upgrade, backup,
   restore, privacy, and actual staff network test on disposable
   environment. Existing Owner installation stays untouched.
5. Security/owner independent acceptance; main merge, update channel,
   and production activation remain **REJECT / NO-GO** until completed.

The words *role page loads*, *authorized API responds*, *own records visible*,
*full workflow executes*, *bank/cash reconciles*, and *safe for customers*
refer to six distinct proofs. Do not collapse them into a single green label.

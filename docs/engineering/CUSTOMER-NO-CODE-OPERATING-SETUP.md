# TOEFL House — no-code customer setup and daily operation

**Owner requirement:** A customer can operate the course without source code,
JSON, terminal commands, GitHub, Docker, database editing or recurring developer
intervention for routine policies. This is a **fresh institute ERP** with zero
previous business history. Native Frappe/ERPNext/HRMS own their authoritative
records; the TOEFL House GUI provides the business workflow.

**Status:** Work-branch implementation and acceptance criteria. Not a released,
signed, independently verified Windows product. No production authorization.

## First-run experience I would require as the paying customer

1. **Install:** Receive *one offline signed Setup EXE*. Double-click, accept
   Windows UAC/restart if required. The provider builds the EXE and bundles all
   prerequisites; customers must never download runtimes, unpack nested ZIPs,
   run PowerShell, or build Docker images. Do not include test database or
   developer assets.
2. **Open the Owner dashboard:** It welcomes the owner and displays clear
   progress: Programs and Tuition → Academic/Billing Rules → Rooms/Staff/Classes
   → Finance/Operations → Final Check. Navigate using real buttons.
3. **Verify starting data:** One native legal Company with AFN and correct
   receivable account; Kabul timezone; Solar Hijri fiscal/academic calendar;
   Friday closure; four program families, 11 canonical levels with their
   native Course links and approved semester tuition. No historic students,
   invoices, payments, grades or demo data.
4. **Set editable numbers:** The Owner sees useful units and controls:
   tuition AFN, duration and capacity numbers, GE/EAP pass mark %, one retake
   waiting days, grade A/B/C/D minimums, billing cutoff and grace days,
   two-month due dates and authorized installment choices, teacher skill
   rates/quantities and any fully approved adjustments. No JSON editor.
5. **Approve policies safely:** A page displays the old and new values,
   effective date, approver, reason and impact. Ordinary changes append one
   auditable version; existing receipts/grades remain unchanged. The Owner
   does not obtain unrestricted native administrator powers.
6. **Configure staff and classes:** Six initial sign-ins **including the existing
   Owner**; verify real staff identities and role permissions. No fabricated
   email addresses. Select instructors and native Rooms with their actual
   measured capacities, assign skills and sessions using the already-confirmed
   timetable. Do not invent classes or students.
7. **Prove everyday operations:** Reception registers/collects, Academic manages
   classes/attendance/results, Finance bills/reconciles, GM approves
   exceptions and Owner reviews. No second ledger. Backup runs against an
   independently verified external encrypted target with two-person recovery
   and a real isolated restore test.

## Implemented source-level UX changes in this review

| Customer need | Work-branch solution | What remains unqualified |
| --- | --- | --- |
| Initialize course catalog | Owner-only guarded click-to-initialize after clean-site and release preflight | Real clean Windows acceptance and signed deliverable |
| Find the next task | Owner Setup routes to five normal work areas | Full readiness checklist persisted in an approved site |
| Grade without JSON | A/B/C/D percentages entered as numbers; F starts at zero; server native scale created through guarded POST | Physical browser dialog & native submit acceptance |
| Configure GE/EAP grades | Enter pass %, retake waiting days, date and reason. The server builds seven verified assessment facets | Native integration; specialist progress-report editor separately |
| Revise GE/EAP numbers | One effective-dated, audited policy version instead of seven JSON operations | Show current vs proposed values and test real version promotion |
| Edit tuition and billing | Link pickers for catalog values, AFN amount; Afghan month/grace/due-day choices | Confirm month-based native Fees on a real installed site |
| Create future programs/policies | Human-readable titles; application generates validated unique internal codes | Non-English title fallback uses a short English name |
| Instructor contracts | Select skills, rates, units and adjustments in normal controls; client assembles validated native payload; revision requires full replacement confirmation | Real Finance/HRMS role/ledger acceptance; larger custom term editors |
| Data protection | No migrated/test business records in initial package, explicit permission and audit gates | Independent real database backup and restore acceptance |

## Verified design corrections in later source changes

- **Duplicate writes:** Guided program creation serializes the first
  creation and rejects different identifiers with the same business title.
  Level creation refuses an already linked family/title, native Course
  display title, native Education Program title or native abbreviation;
  assessment policy shells also reject duplicate family/title. These
  checks live server-side, not only in the preview.
- **Scalar policy safety:** Passing mark and retake waiting days may be
  revised independently. Blanks retain the current governed value.
  A percentage field such as `60.0` is accepted as a whole number,
  while 60.5, nonfinite values and out-of-range percentages are refused.
- **Skills and exams:** Six subject weights plus continuous/final share
  can be edited in the initial GE/EAP policy and in one later audited
  version. The server refuses anything other than an exact 100% skill
  distribution and preserves all other facets.
- **Least-privilege selectors:** Submitted grading scales, academic
  years, levels, program families, fee categories and legal Companies
  are provided by one Course Owner-only, read-only and bounded server
  endpoint. No broad native Accounts/Education Administrator rights are
  granted merely to load UI choices. Invalid names and oversized lists
  stop the form.
- **Teacher attendance:** The raw attendance JSON field is excluded
  when the teacher's own server-projected class roster is displayed.
  The instructor selects Present/Absent/Leave for each authorized student,
  and the application assembles the checked backend format. No student
  defaults to Present.
- **Finance instructor revisions:** The active contract is loaded only
  after native Finance read permission AND company-scope approval.
  Skill rates, quantities, units, pay bounds and approved adjustments
  prefill the nontechnical form. Oversized contracts are rejected rather
  than silently truncated. A new effective start is mandatory, and
  the existing terms are not mutated when a successor is recorded.
- **First-run page:** The normal customer sees readable setup counters,
  navigation to five work areas and a qualified action. Internal code
  names and technical plan operations are collapsed as optional detail.
  One hidden idempotency key is retained per opened form and reused on a
  retry even if Frappe omits hidden field values.

## Explicit incomplete work — never conceal from the customer

- The seven low-level assessment facet commands can still accept structured
  schemas internally, but the Owner's ordinary desk no longer exposes them
  as raw JSON editors. A **general no-code editor for arbitrary rubric,
  weighting, criteria and progression changes** remains a separate release
  requirement, not a claim of completion.
- Other specialized configuration surfaces (including contractor models
  exceeding the six-skill/two-adjustment guided form) still need scalable,
  secure row editors. Current guided revisions **fail closed** for such
  contracts; never truncate pay terms or instruct customers to paste JSON.
  The Finance cash-day close form is not yet a fully qualified
  nontechnical workflow; do not misrepresent raw counts input as finished.
- Initial staff provisioning, native legal Company, real timetable/rooms,
  role-specific first-day work, tax classification and backup recovery remain
  separately gated. No external email or production data is invented.
- A single installer, signed Windows dependencies, actual offline installation,
  updating, two-person restore and exact-head CI must pass before release.
- Test-only configuration records and synthetic CI evidence are not real course
  operating history. Never ship that database or convert test data to live.

## Required acceptance scripts (nontechnical, recorded screen and native ledger)

- Customer changes Starter tuition from AFN 1,000 to an explicitly approved
  different future price **in a GUI**; previous posted Fees are unchanged.
- Owner adds a new program and level by typing its name, dates, duration and
  tuition: system creates one native Program, Course and Fee Structure, never a
  duplicate. A replay returns the original receipt.
- Owner changes passing grade and retake waiting days with two number fields;
  version dates, roles and existing results retain integrity.
- Finance creates/revises one instructor contract using the six-skill form,
  including honest replacement confirmation, without JSON, and confirms
  no salary was posted merely because a contract exists.
- Reception/Finance/GM/Academic/Instructor each complete permitted work, with
  attempted unauthorized cross-role operations denied by the server.
- Disconnect external recovery drive and simulate power failure; backup
  status must not invent success. Restore on separate clean PC must verify
  actual records and two distinct approvers.

**Release rule:** If the customer needs a programmer for a normal academic
or tuition policy edit, or a real Windows image/restore cannot pass, the
product is NOT ready for customer handover.

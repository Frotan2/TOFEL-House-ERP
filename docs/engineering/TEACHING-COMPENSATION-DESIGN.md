# D2 — Teaching Compensation: Smallest-Architecture Determination

Date: 2026-09-16 · Owner requirement received 2026-09-16 · Branch:
`arena/01a0a496-tofel-house-erp`
**No rates, amounts, statutory rules, taxes or contract terms are
invented here.** All values are owner-entered configuration. Production
remains REJECT.

## 1. Verified ground truth (this design is derived from it, not assumed)

- **Teaching module owns no doctypes today**
  (`apps/toefl_house/toefl_house/teaching/` = api only). It operates the
  native authorities: **Student Group** (class roster), **Course
  Schedule** (session), **Student Attendance** (participation) —
  closed and hosted-proven (run 34966681820, 483/483).
- **`Course Schedule.instructor` is a single Link** (pinned education
  `93bc7075`): native sessions carry exactly one instructor and have
  **no skill-area concept**. The required facts (up to 3 skill areas
  per class, 1–3 instructors sharing them) exist in **no** native or
  current TH doctype.
- **Pinned HRMS `a4768b44` verified schemas:**
  - `Additional Salary`: employee, salary_component (Link), amount,
    type (Earning/Deduction), `payroll_date` or `is_recurring` +
    `from_date`/`to_date`, **`ref_doctype` + `ref_docname`
    (Dynamic Link)**, `disabled`, `amended_from` (native amend).
  - `Salary Structure Assignment`: employee, salary_structure,
    from_date, base/variable — the native fixed-salary mechanism the
    owner confirmed for fixed-salary instructors.

## 2. Requirement → capability mapping (no gaps left implicit)

| Requirement | How it is satisfied |
|---|---|
| Multiple instructors per class | One `TH Teaching Assignment` row per (class, skill area, instructor) |
| Multiple skills per class (max 3) | Skill area is a Select of exactly the three named areas; uniqueness of (class, skill, period) caps at three active rows per class |
| One instructor across many classes / skills / mixed assignments | Rows are independent facts; no instructor-level exclusivity |
| Different rates per instructor | Rate lives on each instructor's own `TH Instructor Contract` |
| Different rates by skill | Contract child table `TH Contract Skill Term` (per-skill unit/rate/quantity) |
| Fixed-salary instructors | Native `Salary Structure` + `Salary Structure Assignment` — untouched, no extension |
| Hybrid contracts | Contract model = Hybrid: fixed component via native SSA, variable component via the same single payable path |
| Contractual effective dates | Contract effective start/end; only the contract effective for the calculated period applies |
| Historical reproducibility | Contracts immutable once effective (amend = new effective-dated version, existing `th_*_revision` pattern); assignments immutable; calculation is a pure projection of (facts × then-effective contract) |
| Approved corrections | Contract adjustments child table (approver + reason + effective date) and native `Additional Salary` amend (`amended_from`); `disabled` records excluded |
| No duplicate payable teaching records | Unique index + command-level guard: one payable record per (assignment, payroll period); the command is idempotent (re-run finds existing Additional Salary via `ref_docname` and skips) |
| Auditable chain assignment → amount → payroll | `Additional Salary.ref_doctype/ref_docname` → `TH Teaching Assignment` → contract link + class + instructor; Salary Slip consumes Additional Salary natively |
| One controlled input path, no second engine | The only artifact the teaching side produces for payroll is native `Additional Salary`; statutory/tax/slip math stays entirely in HRMS Salary Slip/Payroll Entry |
| Teaching Ops vs Payroll separation | Teaching Ops records facts (assignments, existing guarded APIs); the compensation command is a finance/payroll-side guarded command that only *reads* facts + contracts |

## 3. The minimal extension set (everything else is native)

1. **`TH Instructor Contract`** (new doctype, Teaching module) —
   contract authority: instructor (Link Instructor), employee (Link
   Employee, for payroll linkage), compensation model (Select:
   `Fixed Salary` / `Skill-Based` / `Hybrid`), class/course assignment
   basis, payment frequency, effective start/end, applicable
   conditions (text), status.
   - Child **`TH Contract Skill Term`**: skill area, unit of payment,
     rate, workload/payable quantity, minimum/maximum rules —
     owner-entered, no defaults.
   - Child **`TH Contract Adjustment`**: type (bonus/deduction),
     amount, effective date, approver, reason.
   - Immutability: submitted contracts cannot be edited; a change
     creates a new version with new effective dates.
2. **`TH Teaching Assignment`** (new doctype, Teaching module) — the
   skill-area responsibility fact: student_group (class), skill_area
   (Select: `Speaking & Listening` / `Writing & Grammar` / `Reading &
   Vocabulary`), instructor, contract (Link TH Instructor Contract),
   optional course_schedule (session evidence link), effective
   start/end. Unique index on (student_group, skill_area) for
   period-overlapping active rows. Does **not** replace or duplicate
   Course Schedule (sessions) or Student Attendance (participation).
3. **One guarded command** (finance/payroll side, existing command +
   guard pattern): `calculate teaching compensation (period)` →
   for each active assignment overlapping the period, resolve the
   contract effective in that period, apply its terms (rate ×
   payable quantity, min/max, adjustments) and create/refresh native
   `Additional Salary` (Earning, `ref_doctype` = TH Teaching
   Assignment). Fixed-salary instructors produce nothing here.
   Idempotent; refuses overlapping contracts; refuses assignments
   without an effective contract; logs through the existing audit
   event pattern.

Explicitly **not** created: no payroll engine, no salary/payable
ledger (Additional Salary *is* the payable record), no second
assignment/teaching ledger, no rates or policy values in code or
fixtures, no parallel masters.

## 4. Why this is the smallest sufficient architecture

- The two facts the requirement needs that exist nowhere (contract
  terms; skill-area responsibility) each get exactly one owned
  doctype; every other noun (employee, session, roster, payable,
  slip, component) is an existing native authority.
- The single controlled input path is a native HRMS doctype with
  native linkage fields — zero custom payroll plumbing.
- All ten "required behavior" bullets are satisfied by structure
  (uniqueness, effective dates, immutability, refs) rather than by
  new machinery.

## 5. Delivery plan (next slices, each hosted-proven)

- **T1**: doctypes + fixtures (roles, guarded command surface,
  permission rows) + local fixtures tests. **DONE** — shipped @
  `8c92e2f`; local teaching suite 17→35.
- **T2**: hosted checks — assignment facts (1–3 instructors, ≤3
  skills), contract effective dating, duplicate-payable prevention,
  idempotent calculation, fixed-salary exclusion, supersession
  reproducibility, audit-chain assertions. **DONE — QUALIFIED**: run
  **35066349129** @ `fa02137`, **536/536**, sha256-verified envelope.
  Failure closures on the way (evidence-based, no invariant weakened):
  35058054173 (v16 Salary Component autoname `field:salary_component`),
  35058898380 (Gender master absent on fresh sites), 35059623949
  (series-named Instructor links), 35060611969 (fixture superseded the
  contract before assigning — sequence fixed; superseded/future
  contract assignment denials promoted to regression checks),
  35065212627 (open-ended probe window genuinely overlaps — probe
  bounded; overlap logic unchanged).
- **T3**: gap-map/dossier updates with run evidence. **DONE** —
  reconciled 2026-09-17.

No qualified domain is reopened: Course Schedule/Student Attendance
authorities and their guarded commands are untouched.

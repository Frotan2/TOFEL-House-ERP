# Legacy extraction — alfrotan-glitch/TOEFL-House @ arena/01a02d63-toefl-house

Owner directive §6. Extracted 2026-09-19 from a shallow clone of that exact
branch. **Behavioural knowledge only.** The legacy architecture (React/Vite
SPA, Express, SQLite, custom ledger, custom payroll, custom RBAC, custom
event bus) is not a candidate to copy.

This record exists so a later reader does not have to re-mine 180 invariants
and 180 decisions to find what still matters.

## Source

- Repository: `alfrotan-glitch/TOEFL-House`
- Branch: `arena/01a02d63-toefl-house`
- Shape: Windows-first LAN app, SQLite, React frontend, Express API.
- Registries read: `docs/registries/invariants.md`, `canonical-authority.md`,
  `decisions.md` (D-11 through D-180 plus work-package certifications).

## Adopted — already true in this product, or kept as a rule

These are behaviours the current Frappe/ERPNext product already implements,
or that this extraction confirms we must keep.

| Behaviour | Legacy origin | Current home |
|---|---|---|
| Fail closed on unreadable policy; never treat a missing store as "no rule" | D-111, invariant on discount-authorization read | Guarded commands; correction policy absence is named on the Finance desk rather than approved blindly |
| At most one discount per charge line; never stack | D-111 / Policy A in current owner decisions | `TH Discount Rule` + issuance; owner Policy A |
| A refund reverses one named payment, not an unattributed bucket | D-113 / D-114 | Tuition correction v1 is full-amount only (current owner policy); native credit note / Payment Entry for money movement |
| Placement sitting is an immutable snapshot; operational views do not expose answer keys | D-80, test-bank security | TH Placement Attempt / Decision; desk projection allow-lists ban answers, hashes, seeds |
| Session with recorded attendance cannot be rewritten by a second store | D-94, D-97 | Native `Student Attendance` is the only attendance authority; teaching command is the only writer |
| Certificate / status change is a transition, not a delete | D-95 | Standing rule: retire/supersede/archive, never rewrite history |
| Idempotent replay is the same business event, or 409 | D-109 | `_execute` request_key on owned commands |
| Branch is operational scope, not independent policy | D-60 / C-8 | Current owner decision: no branch-specific policy overrides |
| Departed instructor cannot be scheduled | teacher active-work guard | `schedule_session` refuses `Instructor.status == Left` |
| Payroll correction posts a new fact; it does not edit the old one | D-163 | D12 + native HRMS Salary Slip; compensation module is fail-closed on policy it does not own |
| Automated backup: different volume, integrity hash, retention generations, restore rehearsal | D-62 / A-11 | `tools/operations/interim_backup.py` — adapted, see below |
| Visitor conversion is an admission transaction, not a client-priced transfer | D-75 | `record_applicant` → admission commands → native Student |
| One role vocabulary, permissions from live assignment, session carries identity not authority | D-20, D-21, D-72 | Native Frappe User / Role / User Permission. No JWT role claim. |

## Adapted — same intent, different authority

| Behaviour | Legacy | Adaptation here | Why not copied |
|---|---|---|---|
| GFS backup 7 daily / 4 weekly / 12 monthly, SQLite online backup, Windows second drive | D-62 | 14/8/12, mysqldump + openssl AES-256-CBC, volume `st_dev` check | Live store is MariaDB, not SQLite. RPO 24h (D13) wants more dailies. Same-machine second volume is still interim. |
| Program → version → level → class | custom catalog graph | Program (native) ← TH Program Level ← TH Academic Program family; class = Student Group | Native Education is the academic authority |
| Role dashboards | React BOS / dashboard views | Six native Frappe Pages (role desks) that project native records | SPA dashboards would be a second product |
| Tuition obligation + allocation | custom `student_obligations` | Native Fees / Sales Invoice / Payment Entry outstanding_amount | Custom ledger is forbidden |
| Teacher payroll ledger | `teacher_salary_ledger` | TH Teaching Assignment payable (D12, one-off) posted through native HRMS | Custom salary ledger is forbidden |
| Attendance union over two tables | rosters + day-level | Single native Student Attendance | A second store is exactly the drift D-94 spent a work package removing |
| Document numbers | custom counters | Native naming series | Do not invent a second series |

## Rejected — architecture or policy we will not take on

Rejected means **do not build this in TOEFL House ERP**. The knowledge is
kept so the rejection is deliberate.

| Item | Why rejected |
|---|---|
| React/Vite SPA + Express API | Frappe is the app foundation. Native UX first. |
| SQLite as the system of record | MariaDB via Frappe. |
| Custom `financial_transactions` ledger | ERPNext Accounts is the financial authority. |
| Custom `teacher_salary_ledger` / `employee_salary_ledger` | HRMS payroll is the employee/payroll authority. |
| Custom RBAC (`user_roles`, permission catalog, JWT claims) | Frappe Role / User Permission. |
| Custom workflow/automation/event bus (WP-12) | Unnecessary event infra is forbidden. |
| Custom BOS profit-distribution / six-month reserve engine (D-61) | Owner has not selected treasury policy here; inventing percentages would be business policy. |
| AFN-only integer money with no FX (legacy D-11) | Current product uses native ERPNext currency. Changing that is an Owner money-policy decision, not an import. |
| Scholarship/sponsorship cash engine as a second settlement authority | Native Fees + Policy A discounts. Donor/campaign impact is future scope. |
| Books commerce + lending domain (D-16 / WP-10) | Not selected. Native Stock exists if the Owner later wants it. |
| Student / guardian portal | Explicitly future-scope in the 2026-09-19 directive. |
| Payment gateway | Same. |
| Advanced gradebook / grade-lock workflow | Same. |
| Waitlist / transfer / freeze engines | Current unresolved business inputs; fail closed, do not invent. |
| Windows `.bat` LAN launchers as the product | Selected deployment is local-server + Tailscale on Frappe. |
| Branch-specific fee/policy overrides | Current owner: branch is operational scope only. |
| Teacher-facing desk keyed on a User↔Instructor link the Owner has not decided | ROLE-DESKS.md: fake authority. |

## Hostile cases worth keeping as a test idea list

These are attack shapes from the legacy suites that remain valid against
*this* product, even though the tables are different. They are not all
implemented here yet; they are the backlog of adversarial ideas.

- Replay of an idempotency key against a **different** fee / invoice / assignment.
- Correction approval after the fee total or window has changed (already
  hosted-proven in this product).
- Discount store unreadable → must fail, must not charge full price silently.
- Scheduling a Left instructor; assigning to a Completed class.
- Cross-branch read of another branch's Fees / Student.
- Payment method / amount the native form did not post, smuggled via REST.
- Attendance for a student not on the scheduled roster.
- Two fee plans for the same level+year: billing must pause (already on the
  Finance desk).

## What this extraction does not do

It does not copy schema, UI, or percentages. It does not treat a legacy
Owner decision (AFN-only, 15% profit tier, six-month reserve) as a decision
of *this* Owner. Those numbers stay in the legacy repo.

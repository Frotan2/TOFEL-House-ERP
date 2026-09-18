# TOEFL House ERP — Semantic Reconciliation Audit
**Date:** 2026-09-18
**Branch:** `arena/01a0b3a7-tofel-house-erp`
**Status:** Audit complete; change set implemented 2026-09-18 (814 tests pass). See §11 for implementation notes and remaining open decisions.

---

## 1. What the legacy system taught us

The independently inspected legacy system established these useful patterns:

- **Curriculum → Delivery separation:** The legacy system's chain
  *Program → Program Version → Level → Offering → Class* demonstrates a
  useful distinction between permanent curriculum identity (Program/Level) and
  operational delivery instances (Offering/Class). We retain that *distinction*
  without retaining every layer.
- **Effective-dated policy:** Duration, pricing and compensation policies that
  change over time must not rewrite historical records. The legacy used
  versioning rows; we already use effective-dated child tables (TH Level
  Duration versions).
- **Central Control Center:** A single owner-facing plane for curriculum,
  levels, rooms, time slots, terms and configuration — a useful UX pattern we
  preserve through the Owner Control Center over native masters.
- **Teacher skill compensation:** Pay varies by skill area taught, requiring a
  configurable skill master and contract terms — not hard-coded lists.

The legacy also contained defects we reject (see §4).

## 2. What the current ERP already does correctly

- **TH Academic Program / TH Program Level architecture** correctly separates
  curriculum family from level, anchors each level to a native Education
  `Program` (set once, never changed), and sequences levels.
- **Effective-dated TH Level Duration** is a child table with monotone version
  appends, `superseded_on` closure and set_by/set_on audit — a sound
  duration-policy mechanism that just needs clearer semantics in field
  descriptions.
- **Native Fee Structure / Fee Category / Fees** are already the financial
  authorities. Tuition billing reads from configured native Fee Structure rows
  and snapshots components at issuance; the client never supplies an amount.
- **TH Discount Rule with precedence** already enforces OD-CP-1 Policy A
  (single discount per charge line; explicit precedence resolves competition;
  no stacking).
- **D3 correction framework** already enforces OD-CP-2 Option B: full-amount
  corrections only, using native Sales Invoice returns (credit notes) and
  native Fees cancellation. Partial amounts are refused with an explicit
  message.
- **Native Student Group / Course Schedule / Student Attendance** are already
  the class/session/attendance authorities through guarded teaching commands.
  No competing `TH Class` or `TH Cohort` roster exists.
- **TH Instructor Contract** with effective-dated supersession and immutable
  terms, plus TH Teaching Assignment for who teaches what skill for which
  class, already provides the contract-driven compensation input path into
  native HRMS Additional Salary.
- **Global (non-branch) configuration** is already the design — no branch
  policy override layer exists. Operational records may belong to a branch
  without creating branch-specific business rules.
- **Containment (A13)** guards all seven command-only doctypes on all three
  lifecycle seams, preventing direct writes outside authorized commands.

## 3. What must change now

### 3.1 Configurable TH Skill master (removes hard-coded skill lists)

**Defect:** `policy.py` hard-codes `TEACHING_SKILLS = ("Speaking & Listening",
"Writing & Grammar", "Reading & Vocabulary")`, and both `TH Teaching
Assignment.skill` and `TH Contract Skill Term.skill` are hard-coded `Select`
fields with those same three strings. If Skill is a configurable business
concept (as the owner compensation model requires), it must not be hard-coded.

**Correction:** Add a new `TH Skill` DocType:

| Field | Type | Notes |
|---|---|---|
| `code` | Data (unique, set_only_once) | Stable identity (2–32 chars A-Z/0-9/-) |
| `title` | Data | Presentation label |
| `status` | Select (Active/Retired) | Lifecycle — retire, never delete |
| `description` | Small Text | Optional |
| `set_by` / `set_on` | Audit | Auto-recorded |

Permissions mirror TH Academic Program / TH Discount Rule: Course Owner writes,
General Manager / Academic Manager / Finance Officer / Finance Auditor /
Teaching Scheduler / Teaching Auditor read. No role may delete.

Both `TH Teaching Assignment.skill` and `TH Contract Skill Term.skill` become
`Link → TH Skill` instead of hard-coded Select. The `validate_skill` function
resolves against active TH Skill records (and rejects retired ones for new
assignments/contracts). A migration preserves the three canonical skills as
seeded TH Skill records so existing data (if any) keeps its identity.

### 3.2 Thin Student Group extension for class lifecycle

**Defect:** Native Student Group lacks explicit fields for the real
operational class facts: actual class start/end date, delivery mode,
branch/company context and a lifecycle status. Today those facts are implicit
(the academic term and group existence imply them), which is ambiguous for
operational reporting and for future scheduling/attendance integrity.

**Correction:** Add these Custom Fields on the native `Student Group` DocType
(not a new competing roster DocType):

| Field | Type | Notes |
|---|---|---|
| `th_class_start_date` | Date | Real class start (operational fact) |
| `th_class_end_date` | Date | Real class end; must be ≥ start |
| `th_delivery_mode` | Select (On-site/Online/Hybrid) | Delivery mode is on the *class*, not a separate Program |
| `th_branch` | Link → Branch | Operational branch (data scope, not policy override) |
| `th_class_status` | Select (Planned/Active/Completed/Cancelled) | Lifecycle status with guarded transitions |

Student Group remains the roster and class authority. The Custom Fields are
thin additions — no second roster, no second enrollment ledger.

The class-creation command (`create_student_group`) accepts these fields,
uses the governing TH Level Duration to *suggest* an end date from the start
date (policy default only — the staff-entered actual end date is what is
stored), and enforces lifecycle transitions (Planned → Active → Completed;
Planned/Active → Cancelled; no terminal-state regression).

### 3.3 Clarify TH Level Duration semantics

The structure is correct; field descriptions are clarified to emphasize that
TH Level Duration is a **duration policy / planning default**, not a class.
Issued classes (Student Groups) carry their own real start/end dates; changing
the duration policy never rewrites existing class records, enrollments, fees
or attendance. The `resolve_duration` rule already behaves this way.

### 3.4 Delivery mode on the class, not on the Program

`Online`, `On-site` and `Hybrid` are operational delivery modes. They are not
separate curricula and must never appear as separate TH Academic Programs.
The new `th_delivery_mode` field on Student Group (3.2) is the canonical
home. No new DocType is required.

## 4. What is explicitly rejected

- **Do not copy legacy five-layer stack (Program → Program Version → Level →
  Offering → Class) wholesale.** The layers beyond what native already covers
  are deferred (§5) or rejected.
- **No `TH Class`, `TH Cohort`, or `TH Course Offering` DocType.** Native
  Student Group with the thin extension in §3.2 is the class/roster
  authority. A competing roster authority is an architecture defect.
- **No branch-specific business configuration.** OD-CP-3 = A is enforced;
  there is no branch override layer. Branch exists as an operational scope on
  class records only.
- **No partial refunds.** OD-CP-2 = B is enforced; the existing correction
  framework already posts only full-amount reversals.
- **No hard-coded fees, discounts, skill lists, program names or curriculum
  titles in application code.** Rates, percentages, skill vocabularies and
  level titles are owner configuration data, not code constants.
- **No client as pricing authority.** Tuition resolves from Fee Structure; the
  issued Fees record snapshots amounts; later configuration changes do not
  rewrite issued documents.
- **No discount stacking.** OD-CP-1 = A remains enforced.
- **No Program Version DocType now.** Architecture is preserved for a future
  version layer (§5) but nothing is added until a real trigger occurs.
- **Do not import legacy bugs, abandoned policies or hard-coded values.**

## 5. What is deferred

- **TH Offering (intake-publication layer):** Defer until a real requirement
  demonstrates that one published intake must fan out into multiple class
  sections with waitlisting or shared publication state that native Student
  Group + Academic Term cannot represent cleanly. Trigger: a concrete owner
  workflow that cannot be expressed in ≤1 thin command over native records.
- **TH Program Version (curriculum versioning):** Defer. The architecture
  requirement is: permanent Program/Level identity must coexist with future
  curriculum revisions; historical enrollments/classes must never be
  retroactively changed by configuration edits. The current anchor via
  `native_program` (set once) already prevents retroactive mutation of
  history through level identity. A version layer becomes justified only when
  two *different curricula* legitimately coexist under the same permanent
  Program/Level identity (e.g. a TOEFL iBT refresh that materially changes
  the Starter syllabus while existing Starter classes continue on the old
  syllabus).
- **Academic assessment / progression (B04/B05):** Remain owner-deferred.
- **Full payroll posting (A09):** Native HRMS Additional Salary is the input
  path; full payroll runs remain gated.
- **Student/guardian portal & online payments (D4, D6b):** Not launch scope.

## 6. Native authority map

| Business fact | Canonical native authority | TH extension (thin only) |
|---|---|---|
| Curriculum family | `TH Academic Program` (config master) | — |
| Curriculum level | `TH Program Level` → native `Program` anchor | `native_program` set once |
| Duration policy default | `TH Level Duration` (child table, effective-dated) | — |
| Class / roster / cohort | Education `Student Group` | Custom fields for start/end, delivery mode, branch, lifecycle status |
| Class sessions / timetable | Education `Course Schedule` | — (orchestrated by teaching commands) |
| Attendance | Education `Student Attendance` | — |
| Academic assessment | Education Assessment Plan/Criteria/Result | Deferred |
| Academic Year / Term | Education `Academic Year` / `Academic Term` | — |
| Fee types / categories | Education `Fee Category` (→ native Item) | — |
| Per-level fee plans | Education `Fee Structure` | TH commands manage Draft structures |
| Tuition receivable | Education `Fees` | `issue_tuition_fees` command |
| Placement fee receivable | ERPNext `Sales Invoice` | `issue_placement_fee` command |
| Discounts | `TH Discount Rule` (thin config) | Single-discount resolution (OD-CP-1) |
| Refunds / corrections | Native return / cancel | `TH Correction Policy` + `TH Correction Request` (OD-CP-2) |
| Teacher employment | HRMS `Employee` + Education `Instructor` | — |
| Teacher contracts | `TH Instructor Contract` | Effective-dated, supersession-only |
| Teacher skill assignment | `TH Teaching Assignment` | Skill now a Link to `TH Skill` |
| Skill master | **`TH Skill`** (new, see §3.1) | — |
| Teacher pay input | HRMS `Additional Salary` | `calculate_teaching_compensation` command |
| Branch / company | ERPNext `Company` / `Branch` | `th_branch` Custom Field on Student Group |
| Access control | Frappe Role / User Permission | TH role fixtures + has_permission hooks |

## 7. Final academic hierarchy

```
TH Academic Program (curriculum family, permanent)
 └── TH Program Level (stage inside family, permanent)
       ├── native Program anchor (set once, immutable)
       ├── TH Level Duration[] (effective-dated policy defaults, never rewrite history)
       └── next_level link (progression within same family, acyclic)
```

Example:
```
General English (GE)
 ├── Pre-Starter (GE-PS)  → native Program "General English — Pre-Starter"
 ├── Starter     (GE-S)   → native Program "General English — Starter"
 ├── Prep One    (GE-P1)  → ...
 ├── Prep Two    (GE-P2)  → ...
 └── Prep Three  (GE-P3)  → ...

Academic English / EAP (EAP)  [only if curriculum genuinely differs]
 └── ... levels ...
```

Delivery mode is on the Student Group (class), not here.

## 8. Final class/delivery lifecycle

```
TH Program Level (permanent curriculum)
  + TH Level Duration (governing duration at class creation → suggests end date)
  + Academic Year / Term (native scheduling context)
  → Student Group (the real class / cohort)
      ├── th_class_start_date, th_class_end_date  (operational facts)
      ├── th_delivery_mode (On-site / Online / Hybrid)
      ├── th_branch (operational scope)
      └── th_class_status: Planned → Active → Completed
                                  └→ Cancelled (from Planned or Active)
      → Course Schedule[] (native sessions via schedule_session command)
          → Student Attendance[] (native, submitted via record_attendance command)
      → TH Teaching Assignment[] (per skill, instructor, contract, effective window)
```

- Class start/end dates are operational facts stored on the Student Group.
- The duration policy is used **only** to suggest a default end date when
  creating the class; the user-entered actual dates are authoritative.
- Changing duration policy after the class exists never touches the class.
- Student Group status controls scheduling: only Active classes accept new
  Course Schedule entries; Completed/Cancelled classes are closed.

## 9. Final fee/discount/refund authority

```
Course Owner (central config)
 ├── Fee Category (native)                  ← fee types (e.g. Tuition, Registration)
 ├── Fee Structure (native, Draft, per native Program × Academic Year)
 │    └── Fee Component rows                ← canonical amounts per category
 ├── TH Discount Rule (central)             ← code, percentage, precedence, optional scope
 │    └── OD-CP-1: at most one discount per charge line (highest precedence wins)
 └── TH Correction Policy                   ← approver role + window

Finance Officer (operational)
 ├── issue_tuition_fees:
 │    1. reads submitted Program Enrollment
 │    2. resolves Fee Structure for (program, year)
 │    3. for each component, resolves ≤1 eligible Discount Rule
 │    4. snapshots components and applied discount into native Fees
 │    5. submits native Fees → GL receivable
 ├── issue_placement_fee:
 │    1. reads native Item Price for SYN-PLACEMENT-FEE on TOEFL House Standard
 │    2. zero/missing → denied (configuration, not client, decides chargeability)
 │    3. creates & submits native Sales Invoice
 └── corrections:
      ├── request_*_correction (full amount only, within policy window)
      ├── approve posts native credit note (Sales Invoice) or native cancel (Fees)
      └── partial amounts are refused (OD-CP-2)
```

- The client never supplies an amount.
- Issued Fees/Invoices snapshot amounts at issuance; later Fee Structure edits
  do not mutate them.
- No branch-specific fee/discount overrides (OD-CP-3).
- Exactly zero or one discount per charge line.
- Refunds are full-amount reversals through native accounting; no parallel
  ledger.

## 10. Exact files and DocTypes that change

### New DocType
- `apps/toefl_house/toefl_house/teaching/doctype/th_skill/th_skill.json` — TH Skill master
- `apps/toefl_house/toefl_house/teaching/doctype/th_skill/th_skill.py` — controller (permissions, audit stamps)
- `apps/toefl_house/toefl_house/teaching/doctype/th_skill/__init__.py`

### Changed DocType JSON (schema)
- `apps/toefl_house/toefl_house/teaching/doctype/th_teaching_assignment/th_teaching_assignment.json` — `skill` field changes from hard-coded Select to Link → TH Skill
- `apps/toefl_house/toefl_house/teaching/doctype/th_contract_skill_term/th_contract_skill_term.json` — `skill` field changes from hard-coded Select to Link → TH Skill
- `apps/toefl_house/toefl_house/academic/doctype/th_level_duration/th_level_duration.json` — improved field descriptions emphasizing policy/default semantics
- `apps/toefl_house/toefl_house/fixtures/custom_field.json` — adds five Custom Fields on Student Group (th_class_start_date, th_class_end_date, th_delivery_mode, th_branch, th_class_status)

### Changed Python modules
- `apps/toefl_house/toefl_house/policy.py` — remove hard-coded `TEACHING_SKILLS`; `validate_skill` resolves against TH Skill; add delivery-mode / class-status validators
- `apps/toefl_house/toefl_house/teaching/__init__.py` — `create_student_group` accepts class start/end, delivery mode, branch, status; suggests end date from level duration; enforces status transitions
- `apps/toefl_house/toefl_house/teaching/compensation.py` — `validate_skill` via Link; reject retired skills for new contracts/assignments
- `apps/toefl_house/toefl_house/controllers.py` — add immutability guards for TH Skill; Student Group lifecycle guards
- `apps/toefl_house/toefl_house/hooks.py` — register TH Skill permissions; add Student Group custom-field fixtures; add doc_events guards for TH Skill; load install hook for skill seeding
- `apps/toefl_house/toefl_house/install.py` — seed three canonical TH Skills (Speaking & Listening, Writing & Grammar, Reading & Vocabulary) so existing references remain valid; add indexes
- `apps/toefl_house/toefl_house/permissions.py` — has_permission/query entries for TH Skill mirroring other config masters

### Changed / new tests
- `tests/teaching/test_policy.py` — configurable skill validation (no hard-coded list; reject retired skills)
- `tests/teaching/test_compensation.py` — skill validation against TH Skill; default skills seeded
- `tests/configuration/test_lifecycle.py` — class lifecycle; duration policy as default only; historical stability after policy changes
- `tests/configuration/test_contract.py` — no hard-coded skills/fees/discounts/program names audit
- `tests/foundation/test_owned_suite_gate.py` — unchanged (workflow already covers all changes)

---

## Reconciliation matrix summary

| Legacy pattern | Disposition | Rationale |
|---|---|---|
| Program (curriculum family) | **ADAPT** → TH Academic Program | Already implemented correctly |
| Program Level | **ADAPT** → TH Program Level + native Program anchor | Already implemented correctly |
| Program Version | **DEFER** | Trigger required (future coexisting curricula); architecture preserved |
| Level duration versions | **KEEP / ADAPT** → TH Level Duration (effective-dated) | Already correct; clarified semantics |
| Offering | **DEFER** | Native Student Group + Academic Term sufficient until multi-section intake publishing proven necessary |
| Class | **NATIVE** → Student Group + thin custom fields (§3.2) | No competing roster |
| Session / timetable | **NATIVE** → Course Schedule | Already used |
| Attendance | **NATIVE** → Student Attendance | Already used |
| Hard-coded skills | **REJECT** → new TH Skill configurable master | Central configuration, auditable, no destructive delete |
| Delivery mode as separate Program | **REJECT** → field on Student Group | Delivery mode ≠ curriculum |
| Branch-specific fee overrides | **REJECT** (OD-CP-3) | Global config only |
| Arbitrary client tuition | **REJECT** (already enforced) | Fee Structure is authority |
| Discount stacking | **REJECT** (OD-CP-1) | Already enforced |
| Partial refunds | **REJECT** (OD-CP-2) | Already enforced |
| Academic Control Center pattern | **KEEP** → Owner Control Center UX over native masters | Already the desk design |

---

## 11. Implementation notes and open decisions (2026-09-18 follow-up)

### 11.1 Implemented controls beyond the original audit

The original audit specified the three code changes in §3. The
implementation adds the following defence-in-depth and product-journey
integrity controls that were found necessary during code review:

1. **TH Skill controller hardened.** `on_trash` and `before_rename` raise
   `PermissionError`; code is immutable after insert (controller enforcement
   supplements the client-side `set_only_once` hint); only the single
   transition `Active → Retired` is permitted (Retired → Active requires an
   explicit owner decision and a new skill code, which prevents retroactive
   resurrection of a retired skill into historical contracts); `set_by`/`set_on`
   audit metadata is frozen after creation. The DocType JSON has
   `allow_rename: 0` and no role holds `delete`.
2. **Class-fact invariants enforced at the Student Group guard.** All save
   paths (native form, REST, Python API, bulk edit, background jobs — even
   with `ignore_permissions=True`) pass through `guard_student_group`, which
   now additionally enforces:
   - On insert: class status must be `Planned`, delivery mode valid, dates
     valid with end ≥ start, branch (if set) must exist.
   - After insert: class-fact fields (`th_class_start_date`, `th_class_end_date`,
     `th_delivery_mode`, `th_branch`) are **immutable**; only
     `transition_class` may change `th_class_status` and only through the
     legal state machine.
   The command therefore cannot silently invent an amendment pathway: any
     future end-date / delivery-mode / branch amendment must be added as an
     explicit command with explicit owner policy.
3. **`schedule_session` now requires the class to be Active.** Planned,
   Completed and Cancelled classes reject session creation.
4. **Instructor–Employee integrity enforced.** `create_teaching_contract`
   verifies that the employee argument matches the Employee linked on the
   native Instructor record and that the Employee is Active — payroll
   inputs created against a mismatched or inactive employee would never
   reach payroll correctly.
5. **Retired skills blocked at command layer.** Both contract-term parsing
   and `assign_teaching_skill` call `_assert_active_skill()`, which checks
   existence and Active status against the database. Historical references
   on already-issued contracts/assignments are never rewritten.
6. **Security surface cleaned.** `active_command_kind()` helper added so
   guards can vary behaviour by active command without reading private
   `_CONTEXT`; `transition_class` registered in `KIND_ROLES` and
   `TEACHING_COMMANDS`.
7. **Indexes added** for TH Skill (status) and Student Group
   (th_class_status, th_branch, th_class_start_date) to support the
   operational lookups used by scheduling and assignment commands.

### 11.2 Open owner decisions explicitly NOT invented

The implementation deliberately **fails closed** on several questions the
owner has not yet decided:

- **Class amendment policy.** After a class is created, the only permitted
  change is lifecycle status via `transition_class`. Changes to the end date,
  delivery mode, branch or start date are refused with an explicit message
  that an owner amendment policy is required. When the owner decides what
  amendments are legitimate (e.g. "end date may be extended if sessions are
  rescheduled" or "branch transfer requires Academic Manager approval"), a
  thin `amend_class` command will be added that records the change, the
  authorizing actor, the reason and a delta audit event. Until then the system
  will not accept ad-hoc edits.
- **Class cancellation/Completion side effects.** Today `transition_class`
  only flips the status. The owner must decide whether Cancelling a class
  should void or refund issued Fees; whether Completing a class has a
  progression consequence; and whether attendance must reach a threshold
  before completion is permitted. These are business policies and are not
  invented here.
- **Skill reactivation.** Once retired, a skill stays retired. If the owner
  ever needs a skill to return, the safe path is a new code (preserving
  history); reusing a retired code is refused.
- **Program Version / Offering layers.** Still deferred (§5). No code was
  added to pre-empt them.

### 11.3 Verified, out of scope, and remaining blockers

Verified via the 814 local unit tests (which include static-AST wiring,
schema-shape, state-machine, containment and permission tests):

- TH Skill config master exists with correct shape, permissions, index, seed
  migration and delete/rename/transition protections.
- All eight Student Group Custom Fields are present, required, indexed and
  read_only, with th_delivery_mode and th_class_status Select options correct.
- Skill fields on TH Teaching Assignment and TH Contract Skill Term are Link
  → TH Skill.
- Hard-coded `TEACHING_SKILLS` tuple removed entirely; `validate_skill` in
  policy.py is a bounded-name check and DB lifecycle enforcement lives at
  the command layer.
- Transition state machine, active-command gating, TERMINAL statuses, and
  session scheduling gating are all correct.
- Containment hook tests pin TH Skill as a sanctioned governance doc_events
  target; all seven command-only doctypes retain three-seam guard coverage.
- Instructor↔Employee integrity verified at contract creation.

Not verified in these unit tests (require hosted Frappe runtime or external
infrastructure):

- Actual Frappe Custom Field application against a migrated site (`bench
  migrate` applies fixtures; the static fixture shape is tested, but runtime
  rendering on the native Student Group form requires a real site).
- `bench execute` runtime acceptance (the d8_validate.py hosted runner still
  gates production; prior hosted runs on ancestor branches remain the
  evidence for the unchanged Placement/Admission/Enrollment slices).
- SEC-DEPS-01 upstream security blocker remains unchanged and out of scope
  for this slice; production authorization stays BLOCKED per the standing
  D8 decision matrix.

## 12. Hosted runtime qualification — Class + TH Skill (2026-09-18)

Mechanism: the repository's existing hosted qualification harness
(`.github/workflows/placement-content.yml` → `tools/placement/run_native.py`)
builds a pinned bench on GitHub's synthetic runner (frappe 988e54f3c4c2,
education 93bc70757533, erpnext 4048fb70…, hrms a4768b44…, MariaDB, Redis,
gunicorn HTTP), creates `placement-test.localhost` and
`placement-second.localhost`, installs `foundation_security` + `toefl_house`,
runs `bench migrate` twice per site, then executes
`tools/placement/native_checks.py` (559 native DB/controller/HTTP checks at
close of this slice)
and a true bench backup/restore rehearsal. Evidence is published as check
runs ("Placement native checks" / "Placement runner result", gzip+base64 with
SHA-256 digest). Unit tests and static analysis are NOT counted as runtime
evidence anywhere below.

Run ledger (branch `arena/01a0b3a7-tofel-house-erp`):

| Run | Result | Meaning |
| --- | --- | --- |
| 35332459813 | fail (fresh-site install) | **Product defect found:** `install.py` added the `th_sg_class_status` / `th_sg_branch` / `th_sg_start_date` indexes during `after_install` before the Custom Field fixtures created the columns → MariaDB 1072. Fixed at root cause (`frappe.db.has_column` guard; the next migrate applies the index) with a regression test in `tests/teaching/test_class_lifecycle.py`. |
| 35333228021 | fail (harness) | Qualification-harness arity defect (message needle mis-parenthesized into `check()`); fixed. Now permanently guarded by `tests/placement/test_native_check_arity.py`. |
| 35334186130 | fail (harness, deep) | **552/552 native checks passed** — every Class + TH Skill runtime proof listed below went green on the real site. The failure was afterwards, in this slice's new fixture code (instructor↔employee linker key), before the retired-skill/instructor-integrity checks could run. Fixed (Left instructor binds to its fixed-contract employee). |
| 35335044988 | fail (harness, 555/556 green) | Re-run carrying the 552 green proofs plus the item 9/10 probes. Read-out transcribed from the "Placement native checks" check run (report SHA-256 `8e0070050a54b70a8dc9cd2b3d268e0ddd48d183b0dab45efb6c8e404c24acd2`): **555/556 checks passed**; `teaching-compensation-contract-authority` passed with `employee_mismatch_denied` and `inactive_employee_denied` both true (item 10 proven). The single failure was again harness, not application: the retired-skill probe passed 12 positional arguments to `create_teaching_contract()` (signature accepts 7–11) — a stray `''` left from an older signature. The crash aborted the sequence, so the three downstream `finance-correction-*` checks never ran. |
| 35337366200 | **success** | Final qualification on commit `bdbacc0`: **559/559 native checks passed** on both fresh pinned sites (report SHA-256 `df108f6a9428dcbdd74491f158e3acac6daa828ace29fa993e3cad00ce276694`, `status: pass`, `production: REJECT`). Items 1–10 are all proven here; the harness fix also restored the three `finance-correction-*` checks, which passed. Paired owned suite run 35337366214: success (819 tests, ruff 0.16.8 clean, node guards, D8 BLOCKED assertions). |

Runtime behavior **proven on the real Frappe site** (runs 35334186130 and
35337366200 — every item below green in the final 559/559 run; check names
as published in the report):

1. **Custom Fields applied by migrate** — `teaching-class-fields-present`:
   `th_class_start_date`/`th_class_end_date` (Date, read-only),
   `th_class_status`/`th_delivery_mode` (Select with the pinned options),
   `th_branch` (Link→Branch) all exist on the migrated `Student Group` meta.
2. **TH Skill master + seeded vocabulary** — `teaching-skill-seeds-present`:
   doctype exists on the migrated site; SL/WG/RV are present as Active with
   the canonical titles.
3. **`create_student_group` on the real site** — `teaching-group-happy-path`
   (+`teaching-group-idempotent-replay`, name/capacity/roster/program/year
   refusals, `teaching-second-group`): roster derived only from submitted
   Program Enrollments; class facts recorded; Planned status.
   `teaching-group-no-duration-policy-denied` proves the duration-policy
   default fails closed when no TH Level Duration governs the level.
4. **`transition_class` on the real Student Group** —
   `teaching-transition-groupA-active` / `-groupB-active`; role refusals
   `teaching-transition-outsider-denied` / `-recorder-denied`; illegal jump
   refused `teaching-transition-invalid-target-denied`.
5. **`schedule_session` only for Active classes** —
   `teaching-session-happy-path`, `teaching-second-session`,
   `http-teaching-session-positive` (REST), idempotent replay, and group/
   instructor/room/calendar refusals.
6. **Planned / Completed / Cancelled refusals** —
   `teaching-session-before-activate-denied` (Planned),
   `teaching-session-completed-denied`, `teaching-session-cancelled-denied`
   — each asserted against the exact guard message
   "Sessions can only be scheduled for Active classes (current status: X)";
   terminal states cannot regress (`teaching-transition-completed-terminal-
   denied`, `teaching-transition-cancelled-terminal-denied`).
7. **Direct Desk/form editing refused** — `teaching-class-fact-save-denied`:
   Administrator `doc.save(ignore_permissions=True)` on each protected fact
   (delivery mode, both dates, status) is refused by the guard with the
   message, and the persisted values are re-read and confirmed unchanged.
8. **REST/Python RPC writes refused** — same check proves
   `frappe.client.set_value` refusal plus value persistence, and
   `http-teaching-protected-fact-put-denied` refuses `PUT /api/resource/
   Student Group/<name>` on a protected fact at the web seam (pre-existing
   A13 containment checks cover cancel/edit/delete/amend-copy seams).

9. **Retired TH Skill runtime policy** (item 9, run 35337366200) —
   `teaching-retired-skill-runtime-policy`: after RV is retired on the live
   site, the historical assignment remains readable and operable
   (`historical_assignment_valid`: the assignment doc still references
   skill RV and its class; `end_teaching_assignment` succeeds against it),
   the historical contract skill term stays intact
   (`historical_contract_term_valid`, rate preserved), reactivation is
   refused (`retirement_one_way`), a **new contract** whose skill terms
   cite RV is refused with the exact guard message "is retired; only
   Active skills" (`new_contract_denied`), a **new assignment** for RV is
   refused likewise (`new_assignment_denied`), and a code absent from the
   master is refused with "Unknown skill" (`unknown_skill_denied`) — the
   TH Skill master is the vocabulary.
10. **Instructor → Employee integrity** (item 10, runs 35335044988 and
    35337366200) — `teaching-compensation-contract-authority`: creating a
    contract whose employee does not match the native Instructor's linked
    `employee` is refused with "does not match the instructor's HRMS
    employee record" (`employee_mismatch_denied`), and a contract against a
    now-Inactive employee is refused with "Only active employees can hold
    teaching contracts" (`inactive_employee_denied`, exercised by flipping
    the Temp employee to Left at the data layer and restoring). Same check
    proves scheduler/outsider write-and-read refusals and contract tamper
    refusal.

Harness note: both harness-only failures (35333228021, 35335044988) were
the same bug class — miscounted positional arguments in the probe code —
and `tests/placement/test_native_check_arity.py` now AST-checks every
helper and app-API call site in `native_checks.py` against real callee
signatures before any push is trusted for a hosted run.

Standing blockers (unchanged by this qualification): **SEC-DEPS-01
UPSTREAM-BLOCKED**, D8 gate **BLOCKED**, production decision **REJECT** — the
hosted synthetic runtime is not a production deployment, and a green
qualification does not lift any of them. No class-amendment policy, no
cancellation/completion side effects, no Offering/Program Version layers were
invented (§11.2 remains the open-owner-decision list).

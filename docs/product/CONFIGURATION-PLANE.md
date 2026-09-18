# The Academic Control Plane — Owner-Managed Configuration

Date: 2026-09-18 · Active branch: `arena/01a0b084-tofel-house-erp`

This document is the contract for the Business Configuration & Academic Control
Plane: the layer that turns the Owner's operating rules into governed,
versioned, auditable, reusable configuration — and makes every module consume
the same rules. It follows the mission's first directive: **verify the native
model before creating anything**.

Governing principle: **native Frappe / ERPNext / Education / HRMS remain the
system of record.** The control plane configures and extends them; it never
duplicates them. There is no second Program, Student, Invoice, Ledger,
Attendance, Payroll or permission authority anywhere in this design.

---

## 1. Native model verification (done, not assumed)

Verified against the actual pinned sources on 2026-09-18 (foundation matrix,
`docs/engineering/foundation-version-matrix.json`):

| Component | Pin |
| --- | --- |
| Frappe | v16.33.1 @ `988e54f3` |
| ERPNext | v16.34.2 @ `4048fb70` |
| Education | v16.1.0 @ `93bc7075` |
| HRMS | v16.18.1 @ `a4768b44` |

Field-level verification (read from the pinned Education source):

- **`Program`** — fields: `program_name` (unique, required), `department`,
  `program_abbreviation`, `courses` (child). **No levels, no ordering, no
  duration, no effective dating, no hierarchy.** It is the consumption key for
  Student Applicant, Program Enrollment, Student Group, Assessment Plan,
  Fee Structure, Fee Schedule and Assessment Result (native links).
- **`Fee Structure`** — required `program` link, required `academic_year`,
  `components` (child `Fee Component`), `total_amount`, receivable account,
  company, submittable. **Per-program fee policy is native.**
- **`Fee Component`** — `fees_category` (Link → Fee Category, required),
  `amount`, `discount` (percent), `item` (fetched from the category), `total`.
- **`Fee Category`** — unique `category_name`, description, auto-created
  `Item` link, accounting defaults (`item_defaults`). **Fee types are native.**
- **`Program Enrollment`** — required `student`, `program`, `academic_year`,
  `enrollment_date`; submittable; enrolled-courses and fees children.
- Consumed daily by the qualified flows (hosted-qualified code paths):
  `Student Group`, `Course Schedule`, `Student Attendance`, `Fees`.

Also verified for the record: the placement domain deliberately forbids
business policy content (percentages, cutoffs, CEFR) inside its content
pipeline (`policy.py`, `controllers.py`), and assessment thresholds / payroll
policy are recorded owner-deferred (D1/B04/B05, D2/A09 in
`docs/engineering/OWNER-DECISIONS.md`). This control plane does not reopen
those decisions — it prepares the carriers for them.

## 2. Classification of the requirement (NATIVE / CONFIGURATION / THIN EXTENSION / DEFERRED)

| Requirement | Classification | Resolution |
| --- | --- | --- |
| Programs (families like a language track) | **THIN EXTENSION** | `TH Academic Program` (shipped) — native `Program` has no family concept and none is invented onto it |
| Ordered levels with codes | **THIN EXTENSION** | `TH Program Level` (shipped); **each level IS a native `Program` record**, created and anchored by the guarded command |
| Level duration (e.g. months per level) | **THIN EXTENSION** | `TH Level Duration` effective-dated version rows (shipped); native has nothing effective-dated |
| Progression (next level) | **THIN EXTENSION** | `next_level` link with same-family + acyclicity validation (shipped); threshold policy stays owner-deferred (D1) |
| Per-level fees | **CONFIGURATION** | Native `Fee Structure` keyed on the level's native `Program` + `academic_year`; no new doctype needed |
| Fee types (ID card, diploma, retake, tuition…) | **NATIVE** | `Fee Category` + auto `Item`; the Owner creates categories natively; our setup surface will orchestrate it (slice 2) |
| Component discounts on a fee plan | **NATIVE** | `Fee Component.discount` percent exists natively |
| Discount rules (catalog, eligibility, stacking) | **DEFERRED** | Model designed (below), **blocked on OD-CP-1** (stacking policy) — decision requested, other work continues |
| Assessment weights / pass marks / retakes | **DEFERRED (owner)** | Native carriers exist (`Assessment Plan`, `Assessment Criteria`, `Grading Scale`); policy values are D1/B04/B05 — not invented here |
| Teacher compensation configuration | **DEFERRED (owner)** | Architecture already preserved (D2/A09, `TH Instructor Contract` + skill terms); configuration surface is a later slice on the same principles |
| Refunds / cancellations / credits | **DEFERRED** | Native credit-note authority + correction framework exist; policy model will be built and the Owner asked (slice 4) |
| Branch availability / overrides | **CONFIGURATION (later slice)** | Global definition + explicit override pattern (§16); deferred until the global layer is consumed in production-like use |
| Reporting definitions (§29) | **CONFIGURATION (later slice)** | The owner cockpit already states definitions inline; a central register is a later slice |

**Architecture decision (engineering, per §36): a level is modeled AS a native
`Program` record.** Rationale: native `Program Enrollment`, `Fee Structure`
(required program link), `Student Group`, `Assessment Plan` and every native
dashboard key on `Program` — making each level a native `Program` means
enrollment, billing, classes and assessments consume the configured structure
with **zero** TOEFL-specific masters and zero changes to the qualified
admission/enrollment/finance commands. The alternative (family = Program,
levels = Courses) breaks native fee granularity, because `Fee Structure` is
keyed per Program, not per Course.

## 3. What shipped (slice 1 + slice 2)

- **`TH Academic Program`** (module Academic) — the family: stable `code`
  (set-once, unique), `title`, `status` (Active/Retired), description.
- **`TH Program Level`** — `family` (set-once), stable `code` (set-once,
  unique), `title`, `sequence`, `native_program` (set-once anchor to the
  native Education `Program`), `status`, `next_level` (progression), and
  `durations` (effective-dated `TH Level Duration` versions).
- **`TH Level Duration`** (child) — `duration_value` + `duration_unit`
  (Month/Week/Day), `effective_from`, `reason`, `set_by`, `set_on`,
  `superseded_on`. **Older versions are closed, never rewritten.**
- **Guarded commands** (`toefl_house.academic`): `create_program`,
  `create_level`, `set_level_duration`, `set_next_level`,
  `set_program_status`, `set_level_status`. Course-Owner-gated
  (governance precedent, deliberately NOT synthetic-gated — same boundary as
  `administration.py`), request-key idempotent, row-locked mutations,
  native `Version` audit via track_changes, refusals in business language.
- **Fee configuration (slice 2)** — guarded commands over *native* finance
  masters: `create_academic_year` (native `Academic Year` — required by fees,
  enrollment and classes, yet created by nothing until now), `create_fee_type`
  (native `Fee Category`; Education's pinned controller creates and maintains
  the accounting `Item` itself — verified server-side `after_insert`), and
  `set_level_fee_component` / `remove_level_fee_component` (upsert/remove of
  `Fee Component` rows on the native `Fee Structure` keyed on the level's
  anchored program + academic year — exactly the structure the qualified
  Finance issuance command consumes). Managed plans stay **Draft/editable**:
  the issuance command reads structures regardless of docstatus (verified),
  and issued `Fees` copy their components at issuance, so a price change
  never touches a posted document — native snapshot semantics, no invented
  versioning on top. Safety: components must reference existing fee types;
  the company is explicit or unambiguous (refuses when several exist); the
  receivable account is resolved from the company's native default (refused
  in business language when unset); a plan keeps at least one component; the
  native "Fee Component" Item Group must exist before fee types can be
  defined (fail closed with an administrator action, never a raw link error);
  ambiguity (two editable structures for one program+year) is refused, not
  guessed.
- **Academic Setup desk** (`th-academic-setup`, audience Course Owner) —
  configuration health facts (integrity faults surface, never hide — including
  native `Program` records defined *outside* the control plane), the program
  and level queues with the *governing* duration of each level, per-enrollment
  configuration history ("which version governed this enrollment"), and
  contextual multi-actions into the guarded commands: a button appears only
  when the server rule lets it succeed (retire a program only with no active
  levels; retire a level only with no live enrollments), so no row dead-ends
  and no button can only fail. Part of the desk registry, the landing-page
  strip, and every desk contract. Two answers are computed for the Owner on
  every load: the **progression chain** of each program reads as the plain
  ordered chain (`Pre-Starter → Starter → Prep One`) and *names* any
  configuration that contradicts itself (a level progressing past the next
  position, a chain with a gap, a final level pointing onward); and every
  active level states its **billing readiness** for the current academic
  year ("Fee plan ready for 2026-2027." / "No complete fee plan for
  2026-2027 yet."), so the Owner and Finance look at one truth. A
  data-driven runtime suite exercises the desk against a configured world
  (chains, mismatch naming, title-vs-code resolution, readiness, the
  outside-the-plane audit) — not merely source scans.

### Integrity rules (§23, §32, §39 — all enforced)

1. Identity is immutable: `code`, `family`, `native_program` are set-once at
   the doctype level; no command can change them.
2. No role holds **delete** or **cancel** on configuration; deactivation
   (retire) is the only destructive action.
3. Deactivating a level is **refused while submitted enrollments run on it**,
   with the real count in the message; deactivating a program is refused while
   it has active levels.
4. Duration versions are monotone: a new version must start strictly after the
   latest one, so every date resolves to exactly one governing version.
5. A retired program/level refuses mutations until reactivated; progression
   must point at an active, same-family, acyclic next level.
6. Codes validate to stable identifiers (2–32 chars of A-Z/0-9/dashes); the
   duration ceiling is a typo guard, not business policy.

### The historical-integrity guarantee (§7, §17, §39)

Because duration versions are only appended and closed, the pair
(versions, date) always resolves to the same governing version — proven by
`tests/configuration`. The Owner changes "Starter = 2 months" to
"Starter = 3 months from July": a June enrollment resolves to 2 months
forever; a July enrollment resolves to 3 months; the June version row still
exists with `superseded_on = 2026-07-01`, `set_by`, `reason`, and the native
`Version` audit records who changed what, when. The same guarantee is what the
fee path inherits natively: `Fees` documents are native submitted records;
the `Fee Structure` match (program + academic year) is validated at issue time
by the qualified finance command and the resulting document is never
retroactively rewritten by configuration.

## 4. Consumption map (§18, §43) — one source of truth

```
TH Academic Program (family, order)          [control plane]
   └─ TH Program Level ──is──▶ native Program  [native anchor, set once]
            ├─▶ Program Enrollment            (qualified enrollment command)
            │      └─▶ Fees ◀── Fee Structure  (qualified finance command;
            │            matched program+academic_year, native components)
            ├─▶ Student Group                  (qualified teaching command)
            ├─▶ Assessment Plan / Grading      (native carriers; policy = D1)
            └─▶ Duration versions (TH)         resolved by date, for class
                                               planning and reporting
```

The qualified flows already validate `Program` existence (enrollment) and
match `Fee Structure.program` to the enrollment (finance): once the Owner
defines structure here, **every** consumer reads the same configuration with
no code change — the integration requirement of §43 is satisfied by native
keys, not by new plumbing.

## 5. Dependency graph (§30)

```
Program → Level → Duration version ─┐
                → Fee Structure ────┼─▶ Enrollment → Fees → Payment
                → Progression link ─┘
Program → Level → Assessment policy (D1, deferred) → Progression decision
Program/Level → Class → Skill → Instructor assignment → Compensation (A09)
```

## 6. OWNER DECISION REQUIRED

```text
OD-CP-1

Decision:
When several discount rules apply to the same charge, how may they combine?

Recommended:
A — One discount only per charge line (the best eligible rule wins).

Why:
Simplest for staff to apply correctly, safest for finance to audit, and the
easiest to explain to a student. Native Fee Component already carries a
percent discount per component, so option A maps cleanly onto native
authority. Options B/C can be added later without rework, but they cannot be
removed later without rework — so the restrictive default is the safe start.

Options:
A — One discount only (recommended)
B — Multiple discounts with explicit priority (configurable order, capped)
C — Unlimited stacking

Blocking:
Only the discount-rule module (slice 3). Programs, levels, durations,
fees and everything else shipped here continue independently.
```

Recorded answers (Owner): _awaiting answer — will be recorded here verbatim
and implemented with tests when it arrives._

```text
OD-CP-2

Decision:
What may be refunded, under what terms?

Recommended:
B — Extend the existing fail-closed correction framework to issued tuition
Fees: full-amount refunds only, through the native reverse Payment Entry,
governed by the same owner-entered terms (approver role + correction window)
as placement-invoice credit notes today.

Why:
The machinery already exists and is qualified (D3: TH Correction Policy +
Request, native credit notes, no parallel ledger). Fees refunds have one
native money artifact too (a reverse Payment Entry against the same
receivable) — no new ledger, no new policy engine. Partial refunds are the
only part that needs genuinely new owner terms (amount rules); deferring
them keeps this decision answerable today without inventing policy.

Options:
A — Placement invoices only (status quo): Fees refunds refused with an
    explicit message.
B — Placement invoices + issued Fees, full-amount only (recommended)
C — Placement invoices + issued Fees, partial refunds allowed (owner must
    also supply amount/eligibility terms before build)

Blocking:
Only the Fees-refund module (slice 4). Everything shipped continues.
```

```text
OD-CP-3

Decision:
Which configuration may individual branches override, if any?

Recommended:
A — None for now. The global configuration is the only configuration;
branch differentiation happens only through native dimensions that already
exist (each fee plan already carries a Company; items already carry
per-company defaults).

Why:
Overrides multiply every later answer ("which price was active in which
branch when?") and the effective-dating question becomes two-dimensional.
No current, demonstrated need has been recorded. Adding an override layer
later is additive; removing one is not.

Options:
A — No overrides; global only (recommended)
B — Durations may be overridden per branch
C — Fee plans may be overridden per branch (beyond the native company
    dimension already on each plan)
D — Both durations and fee plans overridable per branch

Blocking:
Only the branch-override slice (slice 5). Nothing else waits on it.
```

Recorded answers (Owner): _awaiting answers — will be recorded here
verbatim and implemented with tests when they arrive._

Folded into existing owner-deferred decisions (not re-asked): assessment
weights/pass marks/retakes = D1 (B04/B05); payroll policy = D2 (A09).

## 7. Hard-coded policy audit (§31)

Codified as a permanent test (`tests/configuration`): the owned Python
application contains **no** program names, level names, fee amounts, or
discount literals. Verified today across the app: zero occurrences. What
looked like candidates were technical constants (state-machine statuses,
reason-length bounds, query limits, typo-guard ceilings) and the qualified
test fixtures, which stay isolated in `tests/`. The audit test fails the
suite if a future change reintroduces hard-coded policy.

## 8. Verification

- `tests/configuration/test_contract.py` (26 tests) — pure rules (validation
  matrices, effective-date resolution incl. the §17 boundary semantics,
  monotone versions, progression integrity, refusal messages), doctype JSON
  contracts (set-once identity, uniqueness, **no delete for any role**,
  Course-Owner-only writes, native Version audit), command contracts
  (whitelisted, request-key-first, gated, never synthetic-gated, rules
  reused), registry/Page/hooks/projection ties, hard-coded-policy audit.
- `tests/configuration/test_lifecycle.py` (11 tests) — the §33/§45 lifecycle
  against the real commands on an in-memory backend: build a program with
  ordered levels, link progression, change the duration policy, prove the new
  version governs only new dates, prove the old version is closed untouched,
  prove deactivation is refused with real counts, prove the gate refuses
  every other role.
- Desk contracts extended: the Academic Setup desk is tied into the registry,
  Page JSON, hooks, projection allow-lists, client surfaces and the
  signature-mirroring dialog map; its endpoint executes in the runtime smoke.

## 9. Roadmap (each slice gated on the previous, decisions requested in parallel)

1. **Shipped** — programs, levels, durations, progression, setup desk.
2. **Shipped** — fee configuration orchestration: academic years, fee types
   (native Fee Category + Item), per-level native fee plans with component
   upsert/remove; the desk shows fee types, the editable plans with their
   components and sums (display arithmetic, clearly labeled), and the
   readiness fact "active levels without a fee plan for the current academic
   year" — the honest preview of what would block future billing (posted
   documents are, by native semantics, never affected).
   **Consumed where the work happens (§18/§43):** the Finance Manager desk's
   awaiting-billing queue resolves each enrollment's configured plan into the
   issuance prefill — the Officer never types a structure name; a missing or
   incomplete plan names the Course Owner and Academic Setup instead of
   offering a button that can only fail, and an ambiguous plan pauses
   billing in explicit language. Pinned and mutation-checked by
   `tests/configuration`.
3. Discount rules — **blocked on OD-CP-1**; smallest model (§14) on the chosen
   policy, consumed at fee preparation, native percent discipline preserved.
4. Refund/cancellation policy model — will carry its own OWNER DECISION
   block; native credit-note authority stays the only execution path.
5. Branch availability + explicit overrides (§16) and the reporting
   definition register (§29) once the global layer has production-like use.
6. Progression and assessment policy activation — the moment the Owner
   answers D1, the configured structure is already the carrier.

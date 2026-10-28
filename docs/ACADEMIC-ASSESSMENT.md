# Academic assessment, grading and progression

Status: **implemented and exercisable offline** (Mission B04/B05), with
Owner-approved retake safety bounds under independent release qualification.
Grading weights and pass thresholds remain policy configuration; the explicit
Owner-approved retake cap (one retake) and minimum wait (seven calendar days)
are now also enforced as lower/upper safety bounds in code. Every value an academic decision depends on is an
Owner-configured facet of an effective-dated assessment policy, or a record the
native Education app already owns. An unconfigured policy is an explicit,
explained refusal.

Owner decision **D1** (grading policy deferred) is therefore *not* overridden
here. What this slice adds is the machinery that consumes the policy the Owner
configures; the policy itself is still the Owner's to supply. See
[Remaining Owner inputs](#remaining-owner-inputs).

## Approved retake and best-result policy (28 October 2026)

The Course Owner approved the student-protective implementation:

- First assessment books are **class-wide and unique** for the class and level.
- Each approved retake book records exactly **one named failed student** in
  `TH Assessment Book.retake_student`. The Academic Manager opens it through
  `open_assessment_book(..., retake_student="STUDENT-ID")`; the instructor
  records marks only for that student. Submission, approval, native result
  creation and publication cannot include classmates.
- A Retake decision follows a Failed published result, at least seven days
  after publication, and is consumed by one second-attempt book for that
  student. A new policy version does not restart the attempt allowance.
  An abandoned book remains a protected hold until an independently authorized
  cancellation/replacement feature is audited; deleting/recreating its record
  is not a supported recovery.
- The governing result is chosen only from current Published, finite results.
  An earned **Pass always outranks a Fail**. Among Passes choose the highest
  overall percentage; if none passed, choose the highest valid percentage.
  Ties resolve to earliest publication, attempt ordinal, then result ID.
  Historical revisions are never deleted or overwritten.
- Earlier `latest`/`first` policy versions remain readable for historical
  audit, but **new** assessment policy authoring only accepts `best`. The
  Owner-approved Pass-preserving selection is authoritative.
- A student's accepted promotion remains valid if another student retakes.
  An academic correction to that same student's own published result can
  still require a new, independently authorized progression decision.

This is **not live-production acceptance**. Migration of the new book field,
native ERPNext Assessment Result behavior, role separation, report integrity,
and Windows staff/browser tests must pass before activation.

## 1. Native boundary

Native Education stays the authority. This slice reuses, and never duplicates,
its records:

| Native record | Role in this slice |
| --- | --- |
| `Student Group` + `Student Group Student` | the class and its active roster — the only source of who is in a book |
| `Assessment Plan` (+ `Assessment Plan Criteria`) | the scheduled assessment the marks belong to; its criteria are matched to policy components by title |
| `Assessment Result` (+ `Assessment Result Detail`) | the native per-student score record, written on publication and cancelled (never deleted) by a correction |
| `Grading Scale` + `Grading Scale Interval` | the only source of grade codes and their boundaries |
| `Student Attendance` (submitted) | the only source of attendance percentage |
| `Program Enrollment` | the record a progression decision admits; the enrollment command now asks progression before it writes |
| `Student`, `Program`, `Academic Year`, `Instructor`, `Employee` | unchanged native masters |

There is no parallel student master and no parallel grade store: `TH Academic
Result` is a published *snapshot* that links the native result, not a second
gradebook.

## 2. Configuration the runtime consumes

`TH Assessment Policy` holds effective-dated version rows. Each version carries
canonical-JSON facets set by guarded Course Owner commands
(`set_assessment_components`, `set_assessment_weights`,
`set_assessment_pass_rules`, `set_assessment_progression`,
`set_assessment_retakes`, `set_assessment_mapping`, …):

| Facet | Consumed as | Unconfigured behaviour |
| --- | --- | --- |
| `components` | `{code, title, maximum_score}` rows the marks must match | book cannot open |
| `weights` | per-component weight; normalized by their total (a 1/3 set is not "invented" as 100) | book cannot open |
| `pass_rules` | `components[]` minimums (`percent` or `grade`) plus one `overall` minimum | book cannot open |
| `rubrics` | reference evidence only (no runtime effect) | no effect |
| `progression` | required evidence (`assessment_pass`, `attendance`, `approval`) and the `target` (`next` = catalog link, or an explicit level code) | progression refused |
| `retakes` | `max_attempts`, `wait_days`, `scope`, `governing` | retake decisions refused |
| `level_mapping` | the level codes this version governs | book cannot open |
| `grading_scale` (version field) | native `Grading Scale` name | no grade code can be produced |

Every facet is versioned and pinned. A book pins `policy`, `policy_effective_from`
and `policy_digest`; a published result keeps that pin even after the Owner
publishes a later version, so history answers "which rules graded this?" forever.

## 3. Doctypes

| DocType | Purpose | Writes |
| --- | --- | --- |
| `TH Assessment Book` | one class's mark book for one pinned policy version and attempt | commands only |
| `TH Assessment Book Mark` | one (student, component) mark, or a mark missing for a recorded reason | commands only |
| `TH Assessment Book Correction` | append-only log of every changed mark with previous value, new value, reason and actor | commands only |
| `TH Academic Result` | published, digest-pinned result per student (revision, supersedes chain, native result link) | commands only |
| `TH Academic Result Component` | the per-component numbers and the pass rule that applied | commands only |
| `TH Progression Decision` | authorized Promote/Repeat/Retake/Complete with its eligibility snapshot | commands only |

Controllers subclass `ProtectedRecord`, so a save outside a receipted command
meets the business-language refusal. A published result's academic fields are
frozen; a superseded result is final.

## 4. Command surface

All commands are role-gated through the shared `security.authorize` +
`api._execute` receipt/idempotency/audit path.

| Command | Role | Notes |
| --- | --- | --- |
| `open_assessment_book` | Academic Manager | pins the governing version, checks level mapping, scale and facet completeness; attempt ordinal is derived |
| `record_assessment_marks` | Instructor | only the class's assigned instructor (`TH Teaching Assignment` → `Instructor` → `Employee.user_id`); roster and component membership checked; a blank needs a missing reason |
| `submit_assessment_book` | Instructor | refused while any roster student × component has no row |
| `review_assessment_book` | Academic Manager | `Review` or `Return` (+ mandatory note); the submitter can never review |
| `correct_assessment_mark` | Academic Manager | between submission and approval; logs the previous value |
| `approve_assessment_book` | Academic Manager | requires a completed review; the submitter can never approve |
| `publish_assessment_results` | Academic Manager | requires approval; one snapshot-pinned result per roster student; writes the native `Assessment Result` when the book names an `Assessment Plan` |
| `correct_published_result` | Academic Manager | corrects marks and publishes a new revision; the superseded result and its native result are preserved (native one cancelled, never deleted) |
| `decide_progression` | Academic Manager | requires the policy's own approval role; one decision per result |
| `override_progression` | General Manager | records `override_used` with the requirements that were *not* met; never rewrites eligibility |
| `assessment_state`, `progression_state`, `next_level_eligibility` | read | read-only projections, permission-checked |

Book state machine:

```
Open ──submit──> Submitted ──review──> Reviewed ──approve──> Approved ──publish──> Published
                     │                    │
                     └────return──────────┘ (Returned → marks again → Submitted)
```

Nothing publishes from any state but `Approved`, and a second publication is
refused: a change after publication is an academic correction, not a re-run.

## 5. Grading algorithm (`th-grading-v1`)

Deterministic, documented, and stored with every result:

1. Component percentage = `mark / maximum_score × 100`.
2. Weighted contribution = `component percentage × weight / Σ weights`.
3. Overall percentage = sum of the **unrounded** contributions, quantized once
   at the end (4 decimal places, ROUND_HALF_UP). Per-component display rounding
   can therefore never move a result.
4. Grade code = highest configured native interval threshold at or below the
   overall percentage — exactly `education.education.api.get_grade` semantics.
5. Pass rules are evaluated as configured: component minimums, then the overall
   minimum (`percent` or native `grade`).
6. A mark that is absent makes the result `Incomplete` — never a zero, never a
   pass — and blocks progression and native publication until resolved.

The stored snapshot contains the algorithm id, quantization rule, the sorted
scale intervals, weights and weight total, every component row, every pass-rule
check with target and actual value, the explanations, and the policy pin. Its
SHA-256 (`snapshot_digest`) is the audit fingerprint; identical inputs produce
identical bytes regardless of input ordering.

## 6. Progression

Progression is a governed decision, never an automatic consequence of a pass:

* it requires a **valid, configured** progression facet on the result's *pinned*
  policy version;
* it requires **authorized academic approval** — the role named in the facet's
  `approval` requirement must be held by the deciding actor;
* one published result carries **exactly one** decision;
* `Promote`/`Complete` require every configured requirement to be met and the
  target level to exist in the catalog (`next_level`);
* `Repeat`/`Retake` are the governed negative outcomes; `Retake` additionally
  requires the retake facet to allow another attempt right now;
* an **override** is a separate senior act (General Manager only), records the
  unmet requirements it overrode, and never edits the evidence.

A decision never enrolls. What changes is the enrollment command: when the
target program is a configured successor level and the student already has an
enrollment in its predecessor, `Program Enrollment` is refused unless an
approved decision admits that level. Entry levels, students with no predecessor
enrollment and catalogs without successor links are unaffected — exactly the
previous behaviour.

## 7. Refusals worth knowing

| Situation | Result |
| --- | --- |
| policy has no version effective on the date | refusal naming the missing Owner configuration |
| version has no weights / components / pass rules | refusal listing what is missing, naming the Course Owner |
| class's program is not mapped to a level | refusal pointing at Academic Setup |
| policy does not name this level | refusal naming the level |
| retired policy | refusal — no version governs new assessment |
| mark outside `0..maximum_score` | refusal |
| blank row without a missing reason | refusal |
| instructor not assigned to the class | `PermissionError` |
| submitter trying to review/approve own book | `PermissionError` |
| publish before approval / approve before review | refusal |
| second publication for the same book | refusal (correction instead) |
| native plan criteria do not match policy components | refusal naming the component |
| progression without the configured approval role | refusal |
| override when requirements are already met | refusal |

## 8. Read scope

| Role | Books | Results | Decisions |
| --- | --- | --- | --- |
| Academic Manager / Teaching Auditor | all | all | all |
| Instructor | own classes only | own classes only | — |
| Enrollment Officer | — | all published | all |
| Enrollment Auditor | — | — | all |
| Everyone else | — | — | — |

Instructor scope is resolved natively (`TH Teaching Assignment` → `Instructor` →
`Employee.user_id`) and applied in both the list query and the document check, so
a class's marks never leak to another class's instructor. Academic records are
also branch-scoped through their class when the user carries a Branch user
permission.

## 9. History

* Policy versions are append-only and effective-dated; a book and its results
  pin the exact version that graded them.
* A correction publishes a new revision with `supersedes`; the previous result
  keeps every value, its digest and its native result link (status
  `Superseded`), and its native `Assessment Result` is cancelled, not deleted.
* Progression decisions are never edited; an override adds a decision row with
  its own snapshot rather than modifying an earlier one.
* Marks changed after a return or after publication are appended to the
  correction log with previous value, new value, reason and actor.

## 10. Remaining Owner inputs

These are configuration, not code, and are still required before real
assessments run:

1. **Components and weights** per program (General English, EAP, Special
   Speaking, TOEFL Preparation, future programs).
2. **Maximum score** per component and the matching native `Assessment Plan`
   criteria (titles must correspond).
3. **Pass rules**: overall minimum (percent or grade) and any component minimums.
4. **Native `Grading Scale` intervals** — the only place grade codes come from.
5. **Level mapping** of each level to the policy version that governs it.
6. **Progression requirements**, including the approval role the Owner delegates.
7. **Retake terms**: maximum attempts, wait days, scope, governing attempt.
8. **Attendance minimum** per program, if progression is to require attendance.
9. Whether a `repeat` is charged and recorded as a new `Program Enrollment`
   (a fee/catalog decision, outside this slice).
10. Whether publication should be blocked when the book has no linked native
    `Assessment Plan` (today it is optional: without a plan no native
    `Assessment Result` is written, and the result records the omission by
    leaving `native_assessment_result` empty).

## 11. Tests

| Suite | Covers |
| --- | --- |
| `tests/academic/test_grading_rules.py` | the pure engine: weighting, native scale, pass rules, missing marks, completeness states, determinism/digests, progression evidence, retake windows |
| `tests/academic/test_assessment_workflow.py` | configuration → marks → submission → review → approval → publication, corrections, native result writing, permission refusals, read scope, controller immutability |
| `tests/academic/test_progression_workflow.py` | decisions, retakes, overrides, next-level eligibility, enrollment gate, historical policy preservation |

The suites run without a site: `tests/academic/_harness.py` installs a scripted
Frappe store and imports the real owned modules, so the same validation,
authorization, pinning and calculation code the hosted site runs is exercised on
every commit.

# Placement — closure slice implementation record

Date: 2026-09-15 · Session branch: `arena/01a0a13b-tofel-house-erp`
· Predecessor: increment 7 qualified in hosted run `34930396690` (commit `a98871a`).

**Status: NOT YET QUALIFIED — bounded closure slice implemented; hosted
synthetic-runner evidence is not yet recorded. Do not treat this document as
domain closure. Production remains REJECT. F01–F05 remain CLOSED/APPROVED;
no policy value is invented or reopened. Increments 1–7 are not redesigned.**

This records the **final bounded Placement slice** (not a numbered increment
after increment 7): **Finalized Result → Internal Placement Decision →
Recommended Course/Level → Controlled Staff Release.**

## 1. What was implemented

- **Course map configuration** via the existing increment-2 RPCs
  (`create_draft_config` / `revise_draft_config` / `review_config` /
  `publish_config` / `retire_config`) with `config=course_map`. New DocType
  `TH Placement Course Map Revision`. Increment-2 policy exact fields are
  unchanged. Fixture algorithm `course-map-v1`, match `any_correct`, SYN-
  codes only. Fail closed unless exactly one published valid map exists.
- **`release_decision`:** `Placement Releaser` only. SoD: actor ≠ `scored_by`,
  ≠ `reviewed_by`, ≠ `finalized_by`. Requires a Finalized Digital attempt and
  its sealed score. Attempt stays Finalized; Case stays a FrozenRecord with
  no decision pointer.
- **`TH Placement Decision`:** FrozenRecord, unique `(attempt, revision)`,
  hash-bound internal recommendation. Validity days come from the attempt's
  pinned published policy. Missing/invalid policy or map fails closed.
- **No** percent, cutoff, CEFR, composite, official TOEFL, candidate portal,
  or unauthorized post-finalization mutation.

## 2. Files changed (closure slice)

| File | Change |
|---|---|
| `apps/toefl_house/toefl_house/policy.py` | `validate_course_map`, `recommend_course`, Releaser/`decision`/`course_map` reads |
| `apps/toefl_house/toefl_house/api.py` | `course_map` config type; `release_decision` |
| `apps/toefl_house/toefl_house/security.py` | course-map kinds + `release_decision` |
| `apps/toefl_house/toefl_house/permissions.py` / `hooks.py` / `install.py` | course map + decision |
| `apps/toefl_house/toefl_house/controllers.py` | `DecisionRecord` |
| course-map + decision DocTypes; Role fixture `Placement Releaser` | new |
| attempt/case/response/score JSON | Releaser read |
| `tests/placement/test_decision.py` | map/recommend/read-boundary |
| `tools/placement/native_checks.py` | native + HTTP closure checks (1–7 retained) |

## 3. Evidence

<!-- Filled from actual execution output only; no inferred or relabeled results. -->

- Local pure unit tests, executed in the session workspace on 2026-09-15
  (this commit, not yet hosted):
  - `python3 -m unittest discover -s tests/placement -v`: **139/139 OK**
  - `python3 -m unittest discover -s tests/foundation -v`: **44/44 OK**
- Hosted qualification (`.github/workflows/placement-content.yml`):
  - **Not yet executed for this commit.** Unique `check(` names in
    `tools/placement/native_checks.py` are **331**. Do not claim native or
    runner pass counts until the hosted check-run JSON is recorded.

## 4. Remaining out of scope (unchanged after this slice)

- Official TOEFL score / mock TOEFL performance score / official CEFR certificate
- Academic assessment of enrolled students (separate from placement)
- Candidate portal / Website User / Subject Access
- Physical/Hybrid delivery (Physical still fail-closed in session commands)
- Human analytic rubrics, audio, retention deletion, productive-skill rating
- Institutional cutoffs, composites, or owner artifacts P1–P5

When hosted evidence is recorded, Placement is **CLOSED / QUALIFIED** for
this synthetic isolated build. Do not start another Placement increment
unless a future business requirement explicitly requires it.

**Recommended next ERP domain: Admission** (Prospect/Applicant → Placement
Result → Admission → Enrollment). Production remains REJECT. Do not deploy.

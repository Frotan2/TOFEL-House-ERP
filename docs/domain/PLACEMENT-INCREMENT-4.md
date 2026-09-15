# Placement — increment 4 implementation record (staff-supervised Digital delivery)

Date: 2026-09-15 · Session branch: `arena/01a0a13b-tofel-house-erp`
· Predecessor: increment 3 qualified in hosted run `34888352524` (commit `c7277a4`).

**Status: COMPLETE — bounded increment-4 slice implemented and qualified on the
hosted synthetic runner (see Evidence). Synthetic-data implementation only,
authorized for the bounded isolated build. Production remains REJECT.
F01–F05 remain CLOSED/APPROVED; no policy value is invented or reopened.**

This records increment 4 of the vertical-increment sequence in
[PLACEMENT-TECHNICAL-SPEC.md](PLACEMENT-TECHNICAL-SPEC.md) §4/§5.5/§6:
**Verify / start / deliver → save response / seal**, using **server clocks**
and converting **Reserved → Delivered exposure before the projection leaves
the server**. Capture is **staff-supervised Digital only** (Placement
Invigilator). Subject Access, candidate Website User, scoring, audio, physical
packets and hybrid components remain out of scope.

## 1. What was implemented

- **Session operator role:** `Placement Invigilator` (Desk staff). Commands
  `verify_attempt`, `deliver_attempt`, `save_response`, `seal_attempt` require
  that role. The only extra SoD is **allocator ≠ session operator**
  (`allocated_by` frozen on the attempt at allocation). Author/outsider
  DocType grants are not added; the seed-bearing manifest stays
  Publisher/Auditor.
- **Attempt state:** `Allocated → Verified → In Progress → Sealed` under
  command context with integer version CAS. Case/manifest/exposure/response
  rows remain FrozenRecord (insert-once). Clock and verification fields are
  one-way once set.
- **Verify:** Invigilator records `verified_by` / `verified_at`. Physical and
  Hybrid modes fail closed in this increment (`Only digital delivery is
  implemented in this increment`).
- **Deliver:** loads the frozen manifest without granting Invigilator manifest
  read; builds a **projection** (prompts + display options in seed-derived
  order; True/False canonical). **Delivered exposure rows are inserted before
  the projection is returned.** Reserved rows remain. Server clock starts;
  deadline = started + pinned blueprint `total_minutes` (engineering bound,
  not institutional timing). Seed, algorithm, pool digest, family, item
  identity and answers never appear in the projection.
- **Save:** append-only `TH Placement Response` unique
  `(attempt, occurrence, revision)`; option ids from the occurrence's allowed
  set; `missing=1` requires an empty option. Every save checks the server
  deadline; a reached deadline seals as **Timeout** in the same command and
  does not accept the late payload.
- **Seal:** `Submitted` before the deadline, or `Timeout` when the deadline is
  reached (server clock wins over a late Submitted). Unanswered occurrences
  are recorded as explicit missing revisions. Scoring is not implemented.
- **No candidate portal, Subject Access, audio, physical packet, or scoring.**
  No native Student/Enrollment/academic/finance/payroll writes.

## 2. Files changed (increment 4)

| File | Change |
|---|---|
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_attempt/*` | version, allocated_by, clocks, AttemptRecord transitions |
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_response/*` | new append-only response DocType |
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_exposure/th_placement_exposure.json` | `Delivered` event; Invigilator read |
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_case/th_placement_case.json` | Invigilator read |
| `apps/toefl_house/toefl_house/api.py` | `verify_attempt`, `deliver_attempt`, `save_response`, `seal_attempt`; `allocated_by` on allocate |
| `apps/toefl_house/toefl_house/security.py` | four Invigilator command kinds; Response DocType |
| `apps/toefl_house/toefl_house/policy.py` | `project_form`, clocks, Invigilator/response `can_read` |
| `apps/toefl_house/toefl_house/controllers.py` | `AttemptRecord` |
| `apps/toefl_house/toefl_house/permissions.py` | response kind; Invigilator query |
| `apps/toefl_house/toefl_house/hooks.py` / `install.py` / `fixtures/role.json` | Invigilator role + response hooks/unique index |
| `apps/toefl_house/README.md` | increment-4 boundary |
| `tests/placement/test_delivery.py` | projection, clocks, read-boundary |
| `tests/placement/test_allocation_policy.py` | Author still reads no session records |
| `tests/placement/test_native_check_actors.py` | Invigilator grants, HTTP signatures, Author-only denials |
| `tools/placement/native_checks.py` | increment-4 native + HTTP scenarios (increments 1–3 retained) |

Increment 1–3 product behaviour is otherwise unchanged; foundation pins are
untouched.

## 3. Evidence

<!-- Filled from actual execution output only; no inferred or relabeled results. -->

- Local pure unit tests, executed in the session workspace on 2026-09-15
  (this commit):
  - `python3 -m unittest discover -s tests/placement -v`: **98/98 OK**
    (84 increment 1–3 tests retained, plus 12 delivery projection/clock/read
    tests and 2 HTTP-session/signature guards).
  - `python3 -m unittest discover -s tests/foundation -v`: **44/44 OK**.
  - `node tests/foundation/test_realtime_guard.cjs`: **PASS**.
- Hosted qualification (`.github/workflows/placement-content.yml`):
  **not yet executed for this increment.** Increment 3 remains independently
  qualified by run `34888352524` (135/135 native checks, commit `c7277a4`).

## 4. Known limitations (unchanged outer boundary)

- Hosted runner evidence is the only runtime qualification; local unit tests
  do not qualify native Frappe/MariaDB/Redis/HTTP behavior.
- Controller invariants constrain generic CRUD/RPC/`ignore_permissions`
  writes; privileged raw SQL/Python remains governed administration, not
  tamper-proof storage (spec S5).
- All fixture content is synthetic and non-operational; owner artifacts
  P1–P5 remain prerequisites before any operational use.
- Physical/Hybrid delivery, candidate Website User / Subject Access, scoring,
  audio, release and retention are not implemented and remain disabled.

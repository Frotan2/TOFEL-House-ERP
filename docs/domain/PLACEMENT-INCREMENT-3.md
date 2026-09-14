# Placement — increment 3 implementation record (blueprint allocation / candidate form generation)

Date: 2026-09-14 · Session branch: `arena/01a0a055-tofel-house-erp` · Baseline: `857352e4afa74f6eb300b75fb8e50a8e8e036fdd`
· Predecessor: increment 1–2 qualified in hosted run `34865327509` (commit `c0048dc`).

**Status: PENDING HOSTED QUALIFICATION — synthetic-data implementation only,
authorized for the bounded isolated build. Production remains REJECT.
F01–F05 remain CLOSED/APPROVED; no policy value is invented or reopened.**

This records increment 3 of the vertical-increment sequence in
[PLACEMENT-TECHNICAL-SPEC.md](PLACEMENT-TECHNICAL-SPEC.md) §1/§3/§5: the
**Register/allocate** command boundary (spec §4) — a synthetic case, selection
of a published blueprint/policy revision, and generation of a candidate-specific
frozen form from the governed question bank with deterministic auditable
randomization, quotas, difficulty balancing, exposure/reuse controls, attempt
identity/idempotency, fail-closed missing configuration and a complete audit
trail of allocation decisions. Scoring, response capture, clocks, delivery,
identity verification and every later increment remain out of scope.

## 1. What was implemented

- **Case identity (synthetic):** `TH Placement Case` (synthetic native-User
  subject, fixed synthetic purpose marker, `Open` status in this increment,
  unique subject). `create_case` is `Placement Publisher`-only.
- **Allocation command:** `allocate_attempt(case, blueprint + expected
  version, policy + expected version)` — atomically: locks the case row,
  resolves and re-verifies the **Published** blueprint/policy (status, version
  CAS, definition re-validation, stored-hash integrity), locks the blueprint's
  allocation guard, builds the eligible pool (published items of the blueprint
  skills, families already exposed to the subject excluded), runs the bounded
  deterministic solver, locks the selected families' exposure rows in
  canonical order and rechecks, then commits attempt + manifest + exposure
  reservations + audit + operation receipt in one transaction.
- **Solver (`toefl_house/allocation.py`, pure stdlib, no Frappe import):**
  `allocation-v1`. Exact per-section skill quotas; at most one item per family
  per form (family = exposure unit, matching the unique
  `(attempt, family, event)` ledger); round-robin difficulty-stratum balance
  within each section (engineering stratification — not an approved
  psychometric/institutional value); low-exposure-family preference on ties;
  seed-derived HMAC nonce as final deterministic tiebreak. Bounded by spec
  §5.4 (≤10 000 candidate evaluations or ≤2 s wall time); exhaustion or
  infeasibility raises an explicit operator reason (`Allocation unavailable:
  insufficient eligible families for skill …: need N, have M`), never a silent
  relaxation. Single-choice display order is a seed-derived permutation of
  stable option IDs (answer-preserving); True/False stays canonical.
- **Frozen form manifest:** `TH Placement Form Manifest`, unique per attempt
  (exactly one allocation; never regenerated — same-key replay returns the
  stored result). Carries algorithm version, 64-hex server-generated seed
  (`secrets.token_hex(32)`, never client input), pool digest and the canonical
  form JSON whose hash (`form_hash`) is re-verified by the manifest controller
  at insert even under `ignore_permissions`. Time profile = the published
  blueprint's section minutes (items in this increment carry no per-item
  duration/marks; marks belong to the scoring increment).
- **Attempt identity:** `TH Placement Attempt`, unique `(case_name, ordinal)`,
  pins blueprint/policy name + version + content hash and the blueprint mode;
  status `Allocated` in this slice (later increments extend the state path).
  The case row lock serializes attempt creation.
- **Exposure/reuse controls:** `TH Placement Exposure` ledger (`Reserved`
  events; unique `(attempt, family, event)`). A family once exposed to a
  subject is never allocated to that subject again; new item IDs do not reset
  family history. The pool shrinks site-wide as families are exposed, so a
  finite bank makes a safe form unavailable rather than relaxing. No arbitrary
  reuse window is inherited from any earlier proposal; cross-subject caps are
  later activation config, not invented here.
- **Idempotency:** shared HMAC-bound operation receipts — same key + same
  authorized payload + same actor replays the stored result (a retry with the
  same operation returns the existing manifest, never a new form); changed
  payload or actor conflicts. Bounded whole-command retry (3 retries, 5 s
  session lock-wait bound) with the original key.
- **Fail-closed:** missing case, draft/retired/missing blueprint or policy,
  stale expected version, missing skill, infeasible pool, or pool change
  during allocation → explicit denial with operator reason; the
  whole-command transaction persists no partial state on failure.
- **Audit trail:** operation receipt (kind/actor/input hash/result) +
  `create_case`/`allocate_attempt` audit events (target, after_hash = form
  hash) in the same transaction, plus the attempt pins and the manifest
  provenance (seed/pool digest/algorithm) and exposure ledger.
- **Permissions:** case/attempt/manifest/exposure are staff-only (`Placement
  Publisher` + `Placement Auditor`; the manifest is never candidate feedback);
  the allocation guard is readable by no business role. Authors, unrelated
  roles and guests read nothing; all records are immutable after creation.
- **No side effects:** no native Student/Enrollment/academic/finance/payroll
  writes; no scoring, speaking/writing, candidate portal, live learner
  workflow, enrollment, finance, payroll or production deployment in this
  increment.

## 2. Files changed (increment 3)

| File | Change |
|---|---|
| `apps/toefl_house/toefl_house/allocation.py` | new pure solver module (deterministic, bounded, auditable) |
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_case/*` | new DocType (json/py/init) |
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_attempt/*` | new DocType (json/py/init) |
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_form_manifest/*` | new DocType (json/py/init) |
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_exposure/*` | new DocType (json/py/init) |
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_allocation_guard/*` | new DocType (json/py/init) |
| `apps/toefl_house/toefl_house/api.py` | `create_case`, `allocate_attempt`; published-pin helper |
| `apps/toefl_house/toefl_house/security.py` | two new command kinds (Placement Publisher); five new protected DocTypes |
| `apps/toefl_house/toefl_house/policy.py` | `can_read` for case/attempt/manifest/exposure/guard |
| `apps/toefl_house/toefl_house/controllers.py` | `FrozenRecord` / `ManifestRecord` bases (immutable after creation; manifest self-integrity) |
| `apps/toefl_house/toefl_house/permissions.py` | kinds/tables/query conditions for the new records |
| `apps/toefl_house/toefl_house/hooks.py` | hook registrations for the five new DocTypes |
| `apps/toefl_house/toefl_house/install.py` | unique constraints + pool/exposure indexes |
| `apps/toefl_house/README.md` | increment-3 boundary documentation |
| `tests/placement/test_allocation.py` | new pure local solver tests |
| `tests/placement/test_allocation_policy.py` | new read-boundary matrix tests |
| `tools/placement/native_checks.py` | increment-3 hosted scenarios (+ increment-1/2 regression) |

Increment 1–2 files are otherwise unchanged; foundation pins, dependency
strategy, workflow and shared foundation tooling are untouched.

## 3. Evidence

<!-- Filled from actual execution output only; no inferred or relabeled results. -->

- Local pure unit tests, executed in the session workspace on 2026-09-14
  (final state of the branch):
  - `python3 -m unittest discover -s tests/placement -v`: **PENDING**
    (70 tests after increment-3 additions: 48 increments 1–2, 15 solver,
    7 allocation read-boundary).
  - `python3 -m unittest discover -s tests/foundation`: **PENDING** (unchanged).
  - `node tests/foundation/test_realtime_guard.cjs`: **PENDING** (unchanged).
- Hosted qualification (`.github/workflows/placement-content.yml` on
  `arena/01a0a055-tofel-house-erp`): **PENDING** — first increment-3 run
  triggered by the increment-3 commit; previous increments remain qualified
  by run `34865327509` (85/85 native checks, commit `c0048dc`).
- Baseline for increments 1–2: hosted run `34865327509` (success, head
  `c0048dc86fd5cc772a3b8db1f887a0cff7b997ce`).

## 4. Known limitations (unchanged boundary)

- Hosted runner evidence is the only runtime qualification; local unit tests
  do not qualify native Frappe/MariaDB/Redis/HTTP behavior.
- Controller invariants constrain generic CRUD/RPC/`ignore_permissions`
  writes; privileged raw SQL/Python (trusted operator shell) remains governed
  administration, not tamper-proof storage (spec S5).
- All fixture content, subjects, blueprints and policies are synthetic and
  non-operational; owner artifacts P1–P5, empirical validation and the
  real-data gate remain prerequisites before any operational use.
- Difficulty balancing is an engineering stratification spread within the
  published blueprint's section quotas, not an approved psychometric
  property; quotas do not prove psychometric equivalence (spec §5).
- The synthetic case is a stand-in for the verified native subject reference;
  the identity increment (Subject Access) remains a later activation
  prerequisite. Delivery/printing (reservation → irreversible exposure),
  response capture, server clocks, scoring, release and retention are not
  implemented and remain disabled.

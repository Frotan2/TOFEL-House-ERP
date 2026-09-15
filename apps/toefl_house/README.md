# TOEFL House Placement — increments 1–7 plus closure slice

**Synthetic-only, not production.** Implements the first protected content-governance
path (increment 1), the versioned blueprint/policy configuration lifecycle
(increment 2), the bounded allocation / candidate form generation slice
(increment 3), the staff-supervised Digital verify/deliver/save/seal slice
(increment 4), the objective scoring slice (increment 5), independent
review of marked Digital attempts (increment 6), independent
finalization of reviewed Digital attempts (increment 7) and the bounded
closure slice (internal Decision, synthetic course/level recommendation,
controlled staff release) from the approved technical specification. This
is NOT a complete placement assessment system.

Requires the unchanged pinned Frappe/ERPNext/Education foundation and `foundation_security`. Build backend is the same pinned setuptools used by the existing owned app; no new runtime dependencies. Install only on an explicitly authorized disposable test site through supported Bench app installation/migration.

All operations and scoped reads fail closed unless `allow_tests=1`, `toefl_house_synthetic_only=1`, and the site is `placement-test.localhost` or `placement-second.localhost`. These switches do not certify that arbitrary input is synthetic: the qualification runner creates only test users/content, and operators must not supply live data. No default activation or live-data seed is installed.

## Implemented boundary

### Increment 1 — content governance

- Three native authenticated POST RPCs: `toefl_house.api.create_draft`, `revise_draft`, `publish`.
- Exact bounded content DTO; initially Single Choice and True False authoring for vocabulary, grammar, reading and listening only. Productive-skill rubric task formats remain unimplemented and are rejected rather than misrepresented as objective speaking/writing evidence. This does not score candidate responses.
- Stable synthetic author-namespaced families, database family/revision uniqueness, optimistic revision checks under native row locks, durable actor/payload-bound idempotency receipts.
- Whole-command deadlock/lock-timeout recovery uses the original key, at most three retries and a five-second session lock-wait bound (restored afterward). Native rollback clears failed writes/callbacks; no service commit. Commands must be standalone transaction units: automatic retry is refused when the caller already has pending writes or transaction control is disabled. Exhaustion fails closed.
- Separate restricted answer-key versions; changing a draft appends a new key and retains the old key. Public content hashes deliberately exclude answer values; audit records reference restricted keys without containing their answers or hashes. Operation request fingerprints use HMAC with the existing native site encryption key to prevent guessing low-entropy answers from a public payload hash. Key initialization uses the native helper at install, never request-time generation. Key rotation/recovery must preserve a qualified receipt-verification strategy; mismatched fingerprints fail closed rather than re-executing the old key.
- Independent publisher, immutable published revisions and append-only audit/key history. Actor, operation, before/after public content hashes and key references recorded in the same transaction.
- No native CRUD write roles. Owned controller guards apply even when a caller supplies `ignore_permissions`; direct document setters/update/insert without a server-created context are denied. Privileged raw SQL/Python remains governed administration, not claimed tamper-proof storage.
- Equivalent role/document/query restrictions; no candidate access, guest authoring, files, attachments or learner provisioning through the app.

An author family starts `SYN-` + the first 12 uppercase hex characters of `digest(native_user_name)` + `-` + a fixture suffix. Revision is a positive integer. `content` contains only `skill`, `difficulty`, `question_type`, `prompt`, `options`, `answer`; prompts start `SYNTHETIC: `. Options use stable IDs and plain text. Requests carry 16–96-character safe idempotency keys; edit/publish require an integer `expected_version`. Do not log keys/answers as public prompt metadata. The namespace is an engineering fixture constraint, not a business policy.

### Increment 2 — blueprint/policy configuration governance

- Five native authenticated POST RPCs: `toefl_house.api.create_draft_config`, `revise_draft_config`, `review_config`, `publish_config`, `retire_config`; each takes `config` = `blueprint` | `policy` (anything else is denied).
- Two new restricted DocTypes, `TH Placement Blueprint Revision` and `TH Placement Policy Revision`, with the spec state machine **Draft → Reviewed → Published → Retired** (forward-only; Retired terminal). Unique `(code, revision)` database constraints; codes must be synthetic `SYN-…` fixtures.
- Bounded structural definition validation only: a blueprint carries ordered sections (1–12 sections; bounded skills/modes/minutes/item counts) and a `total_minutes` that must equal the sum of section minutes (contradictory quotas fail closed at create and are re-validated at publication); a policy carries parameterized retake/release/retention integer ranges and a synthetic course code list. Ranges are engineering bounds, **not** institutional values; fixture values are not approved operational policy (P1–P5 remain owner deliverables), and no withdrawn default (70%/16+/hard attempt cap) can be expressed.
- Separation of duties enforced server-side: the author (document owner) may only create/revise Drafts; review requires a non-author `Placement Publisher` and records an immutable `review_actor`; publication requires a `Placement Publisher` who is neither the author **nor the recorded reviewer**, then re-validates the stored definition and its hash before freezing meaning; retirement requires a non-author publisher. Content is mutable only while a revision remains a Draft; Published/Retired revisions are immutable.
- Audit ledger extended: config events reference `target` (exactly one of `item_revision`/`target` per event, enforced in the controller), with before/after definition hashes in the same transaction as the operation receipt. The append-only audit, immutable completed operation receipts, actor/payload-bound idempotency, bounded whole-command retry and site isolation gate are shared unchanged with increment 1.
- Fail-closed activation: allocation may pin only `Published` blueprint/policy revisions; missing, draft, reviewed-only, retired or contradictory configuration therefore never enables a workflow. Nothing in increment 2 scores, delivers, records learner evidence, or writes any native Student/Enrollment/academic/finance/payroll record.

The record-level `code` is identity (unique `(code, revision)` constraint) and never travels inside the definition. A blueprint definition contains exactly `mode`, `sections`, `total_minutes`; a section contains exactly `id`, `skill`, `minutes`, `item_count`. A policy definition contains exactly `result_validity_days`, `retest_wait_days`, `release_working_days`, `appeal_working_days`, `retention_years`. Definitions may be sent as JSON objects or JSON strings ≤ 20 000 characters.

### Increment 3 — allocation and candidate form generation (bounded slice)

- Two native authenticated POST RPCs: `toefl_house.api.create_case` (synthetic subject case; one case per subject in this increment) and `toefl_house.api.allocate_attempt` (registers and allocates atomically: new `Allocated` attempt plus exactly one immutable form manifest). Both require `Placement Publisher`; no author/auditor/outsider/guest path exists.
- Five new restricted DocTypes: `TH Placement Case`, `TH Placement Attempt` (unique `(case_name, ordinal)`; pins the published blueprint/policy name + version + content hash and the blueprint mode), `TH Placement Form Manifest` (unique `attempt` — exactly one allocation per attempt), `TH Placement Exposure` (unique `(attempt, family, event)`; `Reserved` reservations in this increment) and `TH Placement Allocation Guard` (internal per-blueprint lock row, readable by no business role). Case, manifest, exposure and guard are **immutable after creation**; attempt identity is frozen at allocation and status advances only through later session commands. All carry `synthetic=1`; the manifest additionally self-verifies its integrity at insert (form hash binds the canonical form JSON, seed is 64 hex chars, occurrences ordered 1..N) even under `ignore_permissions`.
- Selection is a pure, deterministic bounded solver (`toefl_house.allocation`, no Frappe import): exact per-section skill quotas from the pinned blueprint, at most one item per family per form (the family is the exposure unit), round-robin difficulty-stratum balance within each section (engineering stratification, not an approved psychometric value), low-exposure-family preference on ties, then a seed-derived HMAC nonce. Bounded by spec 5.4: at most 10 000 candidate evaluations or 2 s solver wall time; exhaustion is an explicit `Allocation unavailable` failure, never a silent quota/exposure relaxation.
- Randomness is server-generated (`secrets.token_hex(32)`); the client can never supply a seed. The manifest stores the seed, the pool digest and the algorithm version (`allocation-v1`) so an authorized reader can re-derive the exact selection — the hosted acceptance checks re-run the solver and compare. Single-choice option display order is a seed-derived permutation of stable option IDs (answer-preserving; keys store option IDs, never positions); True/False keeps canonical order and order-dependent content is never shuffled.
- Fail-closed when required configuration is missing or invalid: draft/retired/missing blueprint or policy, stale expected version, contradictory stored definition/hash, missing skill, or an infeasible pool (distinct eligible families < demand) all deny with an explicit operator reason and persist no partial state (whole-command transaction). Reuse controls: a family once exposed to a subject is never allocated to that subject again (new item IDs do not reset family history); the eligible pool shrinks site-wide as families are exposed, so a finite bank eventually makes a safe form unavailable rather than silently relaxing.
- Canonical lock order per spec 8: case row → blueprint/policy pins → allocation guard → selected-family exposure rows (canonical order, rechecked) → attempt/manifest/exposure writes; the per-key operation receipt is private to the request. One case serializes its attempt creation (ordinal). The shared HMAC idempotency receipt applies: same key + same authorized payload + same actor returns the existing result (a retry with the same operation returns the existing manifest, never a new form); changed payload or actor conflicts.
- Audit trail of allocation decisions: the operation receipt (kind, actor, input hash, result), an `allocate_attempt`/`create_case` audit event (target = attempt/case, after_hash = form hash) in the same transaction, the attempt's pinned blueprint/policy versions + hashes, the manifest (seed/pool digest/algorithm/frozen form) and the exposure ledger.
- Nothing in increment 3 scores, delivers, prints, records responses, starts clocks, or writes any native Student/Enrollment/academic/finance/payroll record. Verified Subject Access (identity increment) remains a later activation prerequisite; the synthetic subject case is the stand-in for the isolated build.

### Increment 4 — staff-supervised Digital delivery (bounded slice)

- Four native authenticated POST RPCs: `toefl_house.api.verify_attempt`, `deliver_attempt`, `save_response`, `seal_attempt`. All require `Placement Invigilator`. The allocator recorded on the attempt cannot operate the session (allocator ≠ session operator). Authors, outsiders and guests have no path; Publishers cannot deliver.
- Attempt status advances **Allocated → Verified → In Progress → Sealed** only under command context with integer version CAS. Clock fields (`verified_at`, `started_at`, `deadline_at`, `sealed_at`) and `verified_by` / `seal_reason` are one-way once set. Case, manifest, exposure and response rows stay insert-once FrozenRecords.
- Delivery records **Delivered** exposure events (Reserved rows retained) **before** the staff projection is returned. The projection contains prompts and display-ordered options only; seed, algorithm, pool digest, family, item identity and answers are stripped. Invigilator has no DocType read on the manifest.
- Server clocks: overall budget is the pinned published blueprint's `total_minutes` (engineering bound, not institutional timing). Every save checks the deadline; a reached deadline seals as `Timeout` and rejects the late payload. `Submitted` after the deadline is recorded as `Timeout`. Unanswered occurrences are sealed as explicit missing revisions.
- Physical and Hybrid modes fail closed in this increment. No candidate Website User, Subject Access, scoring, audio, printing or physical packet path exists.
- New restricted DocType `TH Placement Response`, unique `(attempt, occurrence, revision)`, readable by Invigilator / Publisher / Auditor. No generic CRUD write roles.

### Increment 5 — objective scoring of sealed Digital attempts (bounded slice)

- One native authenticated POST RPC: `toefl_house.api.score_attempt`. Requires `Placement Assessor`. Authors, outsiders, guests, Publishers and Invigilators have no scoring path. Keys and the seed-bearing manifest are not granted to Assessor; the command loads them through the database under command context.
- Attempt status advances **Sealed → Marking** under command context with integer version CAS. Scoring does not unseal or edit responses.
- Closed-registry scorer (`toefl_house.scoring`, `objective-v1`, no Frappe import): Single Choice and True False **exact match** only. Unsupported types fail closed. **Missing evidence is an explicit outcome, never a silent zero and never dropped from the denominator.** Incorrect is recorded as incorrect, never a negative mark. No composite, percent, cutoff, CEFR map, course recommendation or human rubric.
- New restricted DocType `TH Placement Score`, unique `(attempt, revision)`, FrozenRecord, self-verifying result hash. The stored projection never includes answers, option ids, item identity, family or seed. Publisher / Auditor / Assessor may read scores; Author and Invigilator may not.
- Physical/Hybrid, candidate Website User, Subject Access, audio, release, moderation sample and productive-skill rating remain unimplemented.

### Increment 6 — independent review of marked Digital attempts (bounded slice)

- One native authenticated POST RPC: `toefl_house.api.review_attempt`. Requires `Placement Reviewer`. Authors, outsiders, guests, Publishers, Invigilators and Assessors have no review path. The original scorer cannot review even if they also hold Reviewer (independent of the original scorer).
- Attempt status advances **Marking → Review** under command context with integer version CAS. Review does not edit scores or unseal responses. No Finalized state, Decision row, candidate-visible release, composite, cutoff or course recommendation.
- Reviewer reads case/attempt/response/score, not the seed-bearing manifest or keys. Author and Invigilator still do not read scores.
- Physical/Hybrid, candidate Website User, Subject Access, audio, human rubric rating, release and retention remain unimplemented.

### Increment 7 — independent finalization of reviewed Digital attempts (bounded slice)

- One native authenticated POST RPC: `toefl_house.api.finalize_attempt`. Requires `Placement Reviewer`. The original scorer and the recorded reviewer cannot finalize (independent of both). Authors, outsiders, guests, Publishers, Invigilators and Assessors have no finalize path.
- Attempt status advances **Review → Finalized** under command context with integer version CAS. Spec: Finalized is not released. No Decision row, candidate-visible release, composite, cutoff or course recommendation.
- Finalization does not edit scores or unseal responses. Reviewer reads remain case/attempt/response/score, not the seed-bearing manifest or keys.
- Physical/Hybrid, candidate Website User, Subject Access, audio, human rubric rating, Decision release and retention remain unimplemented in this increment. The later closure slice adds internal Decision release only.

### Closure slice — Finalized result → internal Decision → recommended course/level → controlled staff release

- The increment-2 config RPCs also accept `config=course_map` (`TH Placement Course Map Revision`). Blueprint and policy DTO fields are unchanged. Course-map meaning is a synthetic fixture (`algorithm=course-map-v1`, `match=any_correct`, SYN- codes only). Missing, invalid, or not-exactly-one published course map fails closed. No percent, cutoff, CEFR or official TOEFL fields.
- One native authenticated POST RPC: `toefl_house.api.release_decision`. Requires `Placement Releaser`. The recorded scorer, reviewer and finalizer cannot release. Authors, outsiders, guests, Publishers, Invigilators, Assessors and Reviewers have no release path.
- Uses a **Finalized** Digital attempt and its sealed score only. Attempt status stays **Finalized** (no new attempt transition). The case remains a FrozenRecord with no decision pointer.
- New restricted FrozenRecord `TH Placement Decision`, unique `(attempt, revision)`, self-verifying result hash. Staff-only; no candidate portal. Validity days are taken from the attempt's pinned published policy (`result_validity_days`); missing/retired/invalid policy fails closed.
- No composite, percent, cutoff, CEFR certificate or official TOEFL claim. All-missing evidence does not map to a course. Physical/Hybrid, candidate Website User, Subject Access, audio, human rubric rating and retention remain unimplemented.

No public HTML editor, candidate portal, upload, bulk import, verified candidate identity, media, learner-visible results, retention deletion or deployment feature is included yet. Those stay disabled/unimplemented rather than receiving unsafe defaults. F01–F05 remain closed; owner configuration for actual academic/privacy policies remains a later activation prerequisite.

## Qualification

`python3 -m unittest discover -s tests/placement -v` runs pure local tests, not Frappe runtime tests.

The push/manual, branch-restricted `.github/workflows/placement-content.yml` invokes the unchanged foundation runner probe, then installs exact native commits and both owned apps on two disposable sites. `tools/placement/native_checks.py` exercises real controllers, database constraints, HTTP/CSRF, independent review/publication, allocation feasibility/fail-closed, exposure reuse, deterministic re-run provenance, staff-supervised Digital delivery (verify/deliver/save/seal, server clocks, Reserved→Delivered), objective scoring of sealed Digital attempts (missing≠zero, key-free projection), independent review of marked Digital attempts (reviewer≠scorer), independent finalization of reviewed Digital attempts (finalizer≠scorer and ≠reviewer), internal Decision release of finalized Digital attempts (releaser≠scorer/reviewer/finalizer; course-map fail-closed; Finalized is not mutated), idempotency/races and rollback for increments 1–7 plus the closure slice. It does not weaken upstream tests, modify pins or expose services outside the hosted runner. Failed evidence is retained. No build/install success qualifies unexecuted acceptance scenarios.

Never uninstall this app to work around retention or remove audit evidence. Any populated schema rollback/recovery needs separate qualification; destructive uninstall is not supplied as a rollback method.

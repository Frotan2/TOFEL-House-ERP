# TOEFL House Placement — increments 1–2

**Synthetic-only, not production.** Implements the first protected content-governance
path (increment 1) and the versioned blueprint/policy configuration lifecycle
(increment 2) from the approved technical specification. This is NOT a complete
placement assessment system.

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
- Fail-closed activation: allocation (a later increment) may pin only `Published` blueprint/policy revisions; missing, draft, reviewed-only, retired or contradictory configuration therefore never enables a workflow. Nothing in this increment scores, delivers, records learner evidence, or writes any native Student/Enrollment/academic/finance/payroll record.

The record-level `code` is identity (unique `(code, revision)` constraint) and never travels inside the definition. A blueprint definition contains exactly `mode`, `sections`, `total_minutes`; a section contains exactly `id`, `skill`, `minutes`, `item_count`. A policy definition contains exactly `result_validity_days`, `retest_wait_days`, `release_working_days`, `appeal_working_days`, `retention_years`. Definitions may be sent as JSON objects or JSON strings ≤ 20 000 characters.

No public HTML editor, delivery UI, upload, bulk import, candidate identity, allocation, scoring, timing, media, results/release, retention deletion or deployment feature is included yet. Those stay disabled/unimplemented rather than receiving unsafe defaults. F01–F05 remain closed; owner configuration for actual academic/privacy policies remains a later activation prerequisite.

## Qualification

`python3 -m unittest discover -s tests/placement -v` runs pure local tests, not Frappe runtime tests.

The push/manual, branch-restricted `.github/workflows/placement-content.yml` invokes the unchanged foundation runner probe, then installs exact native commits and both owned apps on two disposable sites. `tools/placement/native_checks.py` exercises real controllers, database constraints, HTTP/CSRF, independent review/publication, idempotency/races and rollback for both increments. It does not weaken upstream tests, modify pins or expose services outside the hosted runner. Failed evidence is retained. No build/install success qualifies unexecuted acceptance scenarios.

Never uninstall this app to work around retention or remove audit evidence. Any populated schema rollback/recovery needs separate qualification; destructive uninstall is not supplied as a rollback method.

# TOEFL House Placement — increment 1

**Synthetic-only, not production.** Implements the first protected content-governance path from the approved technical specification: create a draft, revise it, and publish through an independent actor. This is NOT a complete placement assessment system.

Requires the unchanged pinned Frappe/ERPNext/Education foundation and `foundation_security`. Build backend is the same pinned setuptools used by the existing owned app; no new runtime dependencies. Install only on an explicitly authorized disposable test site through supported Bench app installation/migration.

All operations and scoped reads fail closed unless `allow_tests=1`, `toefl_house_synthetic_only=1`, and the site is `placement-test.localhost` or `placement-second.localhost`. These switches do not certify that arbitrary input is synthetic: the qualification runner creates only test users/content, and operators must not supply live data. No default activation or live-data seed is installed.

## Implemented boundary

- Three native authenticated POST RPCs: `toefl_house.api.create_draft`, `revise_draft`, `publish`.
- Exact bounded content DTO; initially Single Choice and True False authoring for vocabulary, grammar, reading and listening only. Productive-skill rubric task formats remain unimplemented and are rejected rather than misrepresented as objective speaking/writing evidence. This does not score candidate responses.
- Stable synthetic author-namespaced families, database family/revision uniqueness, optimistic revision checks under native row locks, durable actor/payload-bound idempotency receipts.
- Separate restricted answer-key versions; changing a draft appends a new key and retains the old key. Public content hashes deliberately exclude answer values; audit records reference restricted keys without containing their answers or hashes. Operation request fingerprints use HMAC with the existing native site encryption key to prevent guessing low-entropy answers from a public payload hash. Key initialization uses the native helper at install, never request-time generation. Key rotation/recovery must preserve a qualified receipt-verification strategy; mismatched fingerprints fail closed rather than re-executing the old key.
- Independent publisher, immutable published revisions and append-only audit/key history. Actor, operation, before/after public content hashes and key references recorded in the same transaction.
- No native CRUD write roles. Owned controller guards apply even when a caller supplies `ignore_permissions`; direct document setters/update/insert without a server-created context are denied. Privileged raw SQL/Python remains governed administration, not claimed tamper-proof storage.
- Equivalent role/document/query restrictions; no candidate access, guest authoring, files, attachments or learner provisioning through the app.

An author family starts `SYN-` + the first 12 uppercase hex characters of `digest(native_user_name)` + `-` + a fixture suffix. Revision is a positive integer. `content` contains only `skill`, `difficulty`, `question_type`, `prompt`, `options`, `answer`; prompts start `SYNTHETIC: `. Options use stable IDs and plain text. Requests carry 16–96-character safe idempotency keys; edit/publish require an integer `expected_version`. Do not log keys/answers as public prompt metadata. The namespace is an engineering fixture constraint, not a business policy.

No public HTML editor, delivery UI, upload, bulk import, blueprint, allocation, scoring, candidate identity, timing, media, results/release, retention deletion or deployment feature is included yet. Those stay disabled/unimplemented rather than receiving unsafe defaults. F01–F05 remain closed; owner configuration for actual academic/privacy policies remains a later activation prerequisite.

## Qualification

`python3 -m unittest discover -s tests/placement -v` runs pure local tests, not Frappe runtime tests.

The manual, branch-restricted `.github/workflows/placement-content.yml` invokes the unchanged foundation runner probe, then installs exact native commits and both owned apps on two disposable sites. `tools/placement/native_checks.py` exercises real controllers, database constraints, HTTP/CSRF, independent publication, idempotency/races and rollback. It does not weaken upstream tests, modify pins or expose services outside the hosted runner. Failed evidence is retained. No build/install success qualifies unexecuted acceptance scenarios.

Never uninstall this app to work around retention or remove audit evidence. Any populated schema rollback/recovery needs separate qualification; destructive uninstall is not supplied as a rollback method.

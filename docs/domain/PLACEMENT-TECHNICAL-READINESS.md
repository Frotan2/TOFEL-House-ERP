# Placement — implementation readiness and acceptance plan

Date: 2026-09-14 · Baseline: `63e00b2737b7bc3f70553a68ca6aee2141474af8`

## Decision

**READY FOR IMPLEMENTATION AUTHORIZATION — a bounded, isolated, synthetic-data implementation of [PLACEMENT-TECHNICAL-SPEC.md](PLACEMENT-TECHNICAL-SPEC.md).**

This is readiness to request authorization, **not authorization to start**. No code/schema/API/UI/dependency/deployment changes or runtime tests are performed in this gate. Production acceptance remains **REJECT**. Real-data collection, operational placement, live validation trials and deployment are excluded from this readiness result.

F01–F05 remain CLOSED/APPROVED. No new business decision or uncontained architectural dependency has been identified. The stock candidate audio-upload limitation has a specific owned design solution; it is not ignored or fixed by weakening core validation. File/candidate isolation and hook composition require runtime proof before acceptance. If the designed supported path fails qualification, stop the affected capability and resolve it—do not widen roles, patch core or quietly drop a required mode.

## 1. Three-way disposition

| Category | Disposition |
|---|---|
| **Engineering decisions selected now** | One owned app; native subject/User ownership; dedicated candidate scope; versioned bank/policies; immutable allocated forms; constrained fixed-blueprint selection and serialized exposure reservation; closed objective scorer registry plus human ratings; all required supervised modes; purpose-specific WAV upload; supported permission/File extensions; durable operation/dispatch record, MariaDB locks/uniqueness, fail-closed activation and reversible owned migrations. See technical specification for exact boundaries. |
| **Owner values configured later** | Actual courses/prerequisites and mappings; initial age groups; age-appropriate instruments, quotas, section timings, rubrics and exposure configuration; identity/contact/guardian evidence; accommodations; role assignments/delegation/calibration; calendar; jurisdiction, notices/licenses and lawful hold/disposal/backup procedures. They are P1–P5 artifacts, not repeat F01–F05 approval. No fabricated defaults. |
| **Runtime/empirical obligations** | Native extension/session/file/route behavior, allocation/scoring/timing correctness, concurrency/recovery, browser media, physical custody workflow, security regression, scale and retention tests. Assessment validity/mode comparability and actual course fit require separately governed trials before consequential use. None has passed for this new domain. |

Missing owner values do **not** prevent implementing the parameterized domain with synthetic fixtures. They **do** prevent publication/activation of the corresponding real policy, candidate sessions, evidence collection, recommendation or release. This precisely narrows the earlier approved-baseline wording that treated every missing policy artifact as a pre-code blocker; no policy value or learner right is changed. No source-only check substitutes for native runtime proof.

## 2. Source-based compatibility findings

Exact retained upstream identities are in [pinned-source-review.json](pinned-source-review.json); the foundation matrix remains unchanged. During this gate, all **21** recorded upstream files were fetched at their pinned commits through GitHub's contents API and SHA-256 matched the original record. **12 additional Frappe files** at `988e54f3c4c291e2077a83809663f123731abe76` were inspected and hashed below. Existing owned guards were inspected without modification.

An initial raw-GitHub retrieval failed with a TLS connection closure. It provided no usable source evidence; the authenticated GitHub contents API succeeded without disabling TLS validation. No runtime test was attempted by either retrieval.

| Ref | Inspected source and finding | Design consequence |
|---|---|---|
| **S1** | Frappe `model/base_document.py` constructs `extend_doctype_class` mixins in reverse registered order with cooperative MRO. | Compose the domain File mixin with the existing foundation extension; test actual installed order. No controller/core replacement. |
| **S2** | `permissions.py:has_controller_permissions` is deny-only; native permission must already exist. | Narrow native staff role permissions plus denials/row filters. Candidate commands explicitly broker minimal data; a hook alone cannot grant safe partial document access. |
| **S3** | File controller has public/owner/share exceptions; `is_downloadable` invokes the module permission helper; `get_content` reads content without an independent caller permission check. File utilities select downloadable URL matches. | File ACL hook alone is insufficient. Compose method guards, prevent public/retargeted aliases and qualify content/download/ZIP/metadata paths. |
| **S4** | `handler.py` checks parent write on upload; its non-Desk MIME allowlist does not include audio. It also dispatches whitelisted document methods and direct File content downloads. | Candidate cannot be given Desk or a wider core upload allowlist. Owned purpose-specific audio upload validates scope/content then persists native private Files. Generic RPC/File paths remain contained. |
| **S5** | `model/document.py:db_set` explicitly bypasses controller validations; database setters similarly bypass ordinary document flow. | Controller guards alone do not constrain arbitrary privileged code. Protect owned command routes, deny generic setters and govern privileged administration. |
| **S6** | `database/database.py` supports row-locking options, unique constraints and after-commit callbacks; callbacks run after database commit. | Use database uniqueness/locks; callback failure cannot undo committed assessment data. |
| **S7** | `utils/background_jobs.py` implements `enqueue_after_commit` by registering a callback. | Add durable dispatch intent/reconciliation in the owned Operation record, not a claim of guaranteed dispatch or exactly-once execution. |
| **S8** | Native User controller uses email as name and derives standard Website/System User from Desk-capable roles. | Require legitimate candidate account/contact configuration; use non-Desk role and reject conflicting role unions. No fake-email workaround. |
| **S9** | Pinned Education Applicant requires actual Program/year; Student creation affects User/Customer/Applicant status; enrollment mapper passes `ignore_permissions=True`; enrollment submit/cancel and attendance have native side effects/commits. | Placement references native identities but never invokes conversion/enrollment/attendance writers. Candidate route containment and negative side-effect tests remain required. |
| **S10** | Owned `foundation_security` session/auth guards constrain Student/Guardian profiles; current File mixin protects those profiles, not all new placement candidates/staff. | Keep foundation guards unchanged; add purpose-specific owned protections and run existing regressions. No inherited coverage claim. |
| **S11** | Frappe `app.py` invokes authentication before API/private-file dispatch; `auth.py` runs registered auth hooks after session/request initialization. | Supported owned candidate route containment is available; native session/CSRF and all alias/version/private-file paths must still be tested. |

Source establishes mechanisms and risks, not security completeness, vendor support guarantees or installation/runtime compatibility. Exact version pins remain those in [foundation-version-matrix.json](../engineering/foundation-version-matrix.json), including unchanged ERPNext, Education, HRMS and Payments; no frontend candidate is adopted.

## 3. Hosted acceptance matrix — all new rows NOT EXECUTED

After explicit implementation authorization, run on the existing controlled Docker/MariaDB/Redis/Python qualification environment with exact approved pins, native apps and both owned extensions. Preserve failed artifacts and report test source/candidate SHA, image/runtime identities, installed app/hook order, synthetic fixtures, commands, logs and assertions. No private learner data or credentials in evidence. Local tests aid development but only hosted reproducible evidence qualifies gates.

Use two isolated sites; two candidates with different native subjects; returning Student and conflicting-role profiles; unrelated staff; author, publisher, invigilator, assessor, independent reviewer and records officer fixtures. Include revoked/expired assignments, wrong branch, content families sharing a stimulus, inadequate pools, incomplete config, paper/hybrid cases, non-recorded/recorded speaking, holds and missing media. Fixture labels must state that curriculum/age/rubric values are not approved operational policy.

| ID | Exercise | Required evidence / pass condition |
|---|---|---|
| **T01 — Install/upgrade/reversal** | Clean install, repeated migrate, restart, compatible owned upgrade and documented rollback/restore with populated synthetic history. | Native pins/schema behavior unchanged; owned constraints exist; no duplicate fixtures; retained references and guard MRO intact; operations disabled initially. |
| **T02 — Config activation** | Missing catalog/age/identity/privacy/calendar/rubric/time/exposure settings, contradictory quotas, fixture profile copied to operational use. | Publication/affected action denied with a clear reason; no guessed cutoff or hidden production seed; explicit activation cannot bypass validation. |
| **T03 — Identity** | Unknown-program Lead, genuine Applicant, returning Student; shared contacts, duplicate claims, expired access, no usable email, candidate/staff/Student/Guardian union. | One verified subject scope; no fake Student/enrollment/User email; no automatic merge or conversion; legitimate physical path; conflicting account scope denied. |
| **T04 — Content governance** | Malformed/duplicate import, author self-publication, expired rights, quarantined item, key in prompt/media and edits to published revisions. | Staging rejects/reports errors; independent publication and frozen meaning; candidate projections contain no key, hidden notes or future form. |
| **T05 — Form correctness** | All question formats, dependency/enemy sets, difficulty/skill/time/mark quotas, option permutations, candidate look-back, empty and infeasible pools. | Every manifest satisfies exact constraints; stable option/key correspondence; deterministic replay from stored allocation; no silent shortage relaxation. |
| **T06 — Allocation races** | Concurrent attempts for the last eligible family capacity, lost allocation response, duplicate key, changed payload and revoked-user replay. | Exposure caps/unique form and operation hold; no reroll; changed/unauthorized retries reject; undelivered reclaim distinguished from printed/delivered exposure. |
| **T07 — Objective scoring** | Exact/partial choices, matching, gaps/variants, incompatible normalization, Unicode/escaping, missing/blank/invalid evidence, rescoring after key correction. | Bounded deterministic scores from sealed inputs; no arbitrary code evaluation, negative scores or invented totals; corrections versioned. |
| **T08 — Candidate routes** | Own versus other subject; guessed IDs; request body actor/state/flags; generic CRUD/list/search, `/api` variants, RPC/document methods, imports/native mapper/report/export/private download; cookie/CSRF and API-token attempts. | Only intended session-authenticated candidate commands succeed; all bypass attempts deny; no native academic/finance side effects or full person/bank metadata leak. |
| **T09 — Staff and conflicts** | Wrong assignment/branch, revoked assessor, self-release, role switching, direct submit/cancel/rename/delete/setter, report/print/notification access. | Role AND assignment/state/field/conflict predicates enforced on server; independent release; operator privileges explicitly distinguished from routine staff guarantees. |
| **T10 — Private evidence** | Owner after revocation, known URL, ZIP/content calls, public flag, reparent/copy/alias, library-file attachment, same-path alternate File, orphan and File-parent cycle. | No protected bytes or metadata disclosed through alternate bindings; both File mixins compose; native legitimate unrelated File behavior preserved. |
| **T11 — Audio** | Supported browsers/sample rates; microphone denied, wrong MIME/magic, truncated/oversize WAV, false duration, duplicate/out-of-order/missing chunks, late data and interrupted assembly. | Candidate upload works only through the owned validated path without changing core allowlists; strict bounds/private quarantine/seal; missing media holds the component; qualified live alternative. |
| **T12 — Timing/accommodations** | Client clock tamper, refresh/multi-tab, section and total deadlines, timeout worker absent, playback/navigation, rest breaks, extra time and component rescheduling. | Server controls all acceptance; no timer reset or bonus work; approved adjustments traced; earliest applicable limit enforced. |
| **T13 — Physical/hybrid** | Packet preview/print/reprint/lost packet, script transcription error, custody return, mode change and invigilator-attested interruption. | Exposure counted conservatively; script/form matches; transcription verified; mode/custody history explicit; no fictional digital timing or recording evidence. |
| **T14 — Moderation/release** | Calibrated/uncalibrated assessor, 1-in-5 routine sample across modes, consequential concern, unavailable unrecorded audio, independent release and deadline hold. | Mandatory review cannot be bypassed by sampling or service targets; unrecorded review uses real independent evidence; release includes skill/course rationale and provenance. |
| **T15 — Retest/history** | 14-day boundary, documented exception, 90-day validity, no hard attempt cap, seven-day targeted/appeal paths, stale retained components, newer invalid attempt and supersession. | Approved rights/event anchors respected in configured timezone; freshest compatible evidence only; previous decisions/attempts preserved; no highest-score merge. |
| **T16 — Failure/retry recovery** | Crash before/after DB commit, after queue callback, duplicate jobs, deadlock, save-versus-seal, release-versus-revoke, missing file and worker restart. | Atomic DB invariants, durable dispatch recovery, no double result/release or accepted partial upload; bounded retries and visible reconciliation state. |
| **T17 — Privacy/retention** | Audio/raw/summary due dates, abandoned case, access not resetting clock, appeal/legal hold racing deletion, orphan cleanup and isolated backup restore. | Exact F05 schedules/anchors and configured legal procedures; protected hold handling, deletion audit and no resurrection after restore; no claim that deleted evidence can be re-marked. |
| **T18 — Reports/realtime** | Placement versus academic grains; aggregate/drilldown/export/job retrieval after revocation; candidate subscriptions and error responses. | No score-domain mixing, key/PII leak or unauthorized stale export/event; permissions rechecked at retrieval; projections cannot authorize release. |
| **T19 — Scale/feasibility** | Synthetic 100,000 item revisions including 10,000 published eligible items; 50 concurrent allocation requests, 100 concurrent autosaves and 10 concurrent audio uploads on recorded runner resources. | All constraints/zero cross-subject leaks hold; bounded allocation failures rather than unbounded search; record p50/p95/p99, contention, memory, storage and recovery. These are engineering stress scenarios, not a promised service capacity/SLA. Operator workload/latency targets must be defined before operational acceptance. |
| **T20 — Foundation regression** | Rerun retained native/session/Student/Guardian/file/realtime/staff authorization and owned tests, including installed extension order. | No weakened guard, changed pins/test bypass or relabeled failure; report existing Phase 2 dependency/production failures separately and preserve them. |

Browser qualification must include actual recording and playback, keyboard/screen-reader/input accommodation checks and network interruption—not merely static JS compilation. Productive-task calibration and mode/course-fit studies are empirical academic obligations, not synthetic test passes. No made-up pass percentage or minimum trial size guarantees assessment validity.

## 4. Authorization boundary and sequence

1. Obtain a **separate explicit authorization** for the isolated synthetic-data build of the technical specification. No live data, public deployment, new dependencies or upstream changes are included.
2. Implement in reviewable vertical increments: protected identity/config/content → allocation/response/clock → objective/human scoring and supervised modes → independent release/history → privacy/recovery and full negative-route coverage. No incomplete increment becomes operational merely because its happy path works.
3. Execute T01–T20 and retain hosted evidence. Any unsupported mechanism, bypass, wrong result or integrity failure blocks acceptance of the affected slice. Do not bypass a failed test to preserve this readiness label.
4. Load owner-approved operational profiles only after P1–P5 artifacts, empirical validation and separately authorized real-data/use gates are met. Production deployment additionally requires unresolved Phase 2 gates to be closed; business approval does not waive them.

**No current architecture blocker requires reopening F01–F05.** Ordinary policy values and launch facts remain configurable with enforced activation gates. App availability, data/privacy approval, empirical validity, runtime security and production readiness are deliberately not conflated.

## 5. Source identity and static verification record

The following manifest records the additional inspected Frappe files (source only; not runtime proof). Existing upstream hashes remain in the unchanged 21-file pinned source review. Both new authoritative documents and the approval-record navigation update are documentation-only. All other tracked files must remain byte-identical to the baseline above.

| Frappe path | SHA-256 |
|---|---|
| [frappe/model/base_document.py](https://github.com/frappe/frappe/blob/988e54f3c4c291e2077a83809663f123731abe76/frappe/model/base_document.py) | `4362ec935db3b918463846ac3c73ffe0e7c8543c191b9aff766949a3c8e60a0e` |
| [frappe/model/document.py](https://github.com/frappe/frappe/blob/988e54f3c4c291e2077a83809663f123731abe76/frappe/model/document.py) | `902e8330128a8d541069355e9c66689c548fca749a9d05ccc69cdd952ac44937` |
| [frappe/permissions.py](https://github.com/frappe/frappe/blob/988e54f3c4c291e2077a83809663f123731abe76/frappe/permissions.py) | `2daa7a281c3976218a96d1a56796bebd68717aa2364d92d9c53d7b5130e0d415` |
| [frappe/core/doctype/file/file.py](https://github.com/frappe/frappe/blob/988e54f3c4c291e2077a83809663f123731abe76/frappe/core/doctype/file/file.py) | `76ed4581dc83b984093eca05417abac2765fd6c8c13ddc307bc369aa580a4fbc` |
| [frappe/utils/file_manager.py](https://github.com/frappe/frappe/blob/988e54f3c4c291e2077a83809663f123731abe76/frappe/utils/file_manager.py) | `0253075d88ffa6f397f065555e46e7ae9abc574c11a4c9ff6c92025baa9606bd` |
| [frappe/handler.py](https://github.com/frappe/frappe/blob/988e54f3c4c291e2077a83809663f123731abe76/frappe/handler.py) | `f8adf6b97e885f5208c0147eb4812911a1d2196276fe45d38a317f9f57a0fe99` |
| [frappe/core/doctype/user/user.py](https://github.com/frappe/frappe/blob/988e54f3c4c291e2077a83809663f123731abe76/frappe/core/doctype/user/user.py) | `cf061243103164f30e1f0a4a47a0e98a7e94df382dd0228c5392faae1ee41183` |
| [frappe/database/database.py](https://github.com/frappe/frappe/blob/988e54f3c4c291e2077a83809663f123731abe76/frappe/database/database.py) | `ce1199fe0e56f6534d4be591795c422166b7f0fdec4e423ab7060f36cdacfa00` |
| [frappe/utils/background_jobs.py](https://github.com/frappe/frappe/blob/988e54f3c4c291e2077a83809663f123731abe76/frappe/utils/background_jobs.py) | `45d721dbb4efb0b609831f2e578c219aba4d1010faa35a9672d41e4e978568bc` |
| [frappe/auth.py](https://github.com/frappe/frappe/blob/988e54f3c4c291e2077a83809663f123731abe76/frappe/auth.py) | `69e0a665d37a7ffe7b014db3d85de5443179491eea1a8e8262c8b8d6e818695b` |
| [frappe/app.py](https://github.com/frappe/frappe/blob/988e54f3c4c291e2077a83809663f123731abe76/frappe/app.py) | `1e910e76bcbf596dc708dbd4d8f682f6a6e37368971afcca5f4512efeaa845f9` |
| [frappe/core/doctype/file/utils.py](https://github.com/frappe/frappe/blob/988e54f3c4c291e2077a83809663f123731abe76/frappe/core/doctype/file/utils.py) | `17a333f87b6e509d1f8b46c1cf917ed27ad902769208c8c912dc6e432dcd88bb` |

Additional unchanged local evidence:

| Path | SHA-256 |
|---|---|
| `docs/domain/pinned-source-review.json` | `b20a13274ef8583d2306233bc2273672354edf77e1506a38aa5f1a933c2980aa` |
| `docs/engineering/foundation-version-matrix.json` | `c6447f5b046d27449521b69415854f590f8c8a5abf3a17530737e13988f9e369` |
| `apps/foundation_security/foundation_security/hooks.py` | `afb66e2a4d7541c5d14c675d554e0ee7d4eeb392d11d70220451cf9b7e432d03` |
| `apps/foundation_security/foundation_security/guards.py` | `2e7f0410b607269dd704c120e7beafbde4816eaef0543e7f8464ea1f6a9a85ce` |
| `apps/foundation_security/foundation_security/files.py` | `e85811795f776a1e74ac6e05b81f5128c8e1caeaf68dc84ef5245f79294f9f49` |

**Final gate state: READY FOR IMPLEMENTATION AUTHORIZATION. Implementation has not begun. Production acceptance remains REJECT.**

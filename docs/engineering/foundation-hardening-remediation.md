# Foundation hardening remediation — qualification, not product development

## Final targeted hardening verification — 2026-09-14

**Decision: REJECT current Phase 2 / production acceptance.** The targeted legacy-file
ownership and scheduler fixes are now hosted-verified; this is not full production approval.
GitHub access is restored. Both requested runs and the corrected follow-up were retrieved,
with lossless report SHA-256 checked against the published Check summaries, embedded commit
checked against the Check and workflow head, and embedded run ID checked against the run.
See `evidence/phase-2/final-hardening-hosted-verification.json` for all six reports and Check IDs.
Full artifact logs were not independently retrieved in this final verification.

| Run / source | Verified result |
|---|---|
| 34809817009 / 6969ab3 | **FAIL**: changing immutable File Created By during fixture setup raised CannotChangeConstantError, preventing Guardian provisioning and cascading into Guardian checks/browser. Old 180-second scheduler observer also timed out. This does not establish a file-guard failure or pass |
| 34810723925 / 22c6ad8 | **FAIL**: same fixture failure retained. Corrected observer saw actual scheduler-created **Complete at 238.19s**, native tick 240s, budget 360s |
| **34812299091 / ff39ae3883ca51b46be96235b8ecf13afbd331b6** | **Readiness 54/54, Guardian Chromium 6/6, realtime 4/4, five-app patch upgrade 33/33, frontend graph PASS.** Actual scheduler Complete at **164.14s**. Overall workflow **FAIL solely on the frontend advisory audit** |

### Legacy-owner boundary now proven in the corrected hosted fixture

Pinned Frappe both prohibits changing an existing owner and assigns the inserting user
as owner. The fixture therefore creates an unattached private File as Guardian through
normal insertion, restores Administrator, and attaches it to the unrelated Student through
normal save. Persisted owner, private flag and unrelated parent are asserted. No SQL,
ignore-permission, migration, constant-validation bypass or upstream changes are used.
The rejected insert-dictionary owner proposal is retained in commit af4baf9; its queued
run 34812019158 was superseded without executing. The source rationale is retained in
`evidence/phase-2/legacy-file-owner-source-review.json`.

For that confirmed Guardian-owned, unrelated-Student attachment, hosted results prove:

- Private-file HTTP download, File REST metadata and File RPC return **403**.
- Parent Student read is denied, native `is_downloadable()` is **false**, and native
  `get_content()` raises **PermissionError** under Guardian identity.
- Authorized private-file HTTP download remains **200**; native download/content works
  and the returned content matches the expected SHA-256.
- Missing/expanded live Guardian scopes still fail closed and recover; Guardian browser
  regressions, seven Salary Register ACLs, real-job realtime ownership and session
  revocation checks also pass.

All hosted **0.2.1 extension file hashes match the checkout**. The native content-method
check is not an end-to-end HTTP ZIP/export test. Wider lifecycle, mixed-role/multi-child,
print/export and attachment combinations still need qualification. No blanket security
approval follows from the enumerated paths.

Local validation remains **44 Python tests plus the Node adapter regression passing**;
Python compilation and JavaScript syntax checks pass. Hosted policy-test step also passed.
The final workflow failure is retained, along with all preceding failed reports. No TOEFL
implementation or main-branch changes occurred.

### Earlier evidence remains historical and available

34807848711 established 43 readiness, six Guardian browser and four realtime checks.
34808064545 established 51 readiness checks but hit the expanded upgrade smoke-site
allowlist error. 34809413852 proved the 33-stage upgrade and ES source/build graph but
retained the too-short scheduler observation failure. Those observations are not rewritten.
Pending snapshots 34807925473, 34807977896, 34808944166, 34809760788 and 34812019158 were
superseded before execution; they are neither passing nor failed runtime evidence.

## Decision and boundaries

Current production/Phase 2 acceptance remains **REJECT** until critical open gates are
closed. The minimal owned `foundation_security` extension uses Frappe hooks, a supported
v16 File class mixin, and the pinned in-process Socket.IO adapter contract. It introduces
no DocTypes, identity store, task-owner store, finance authority or TOEFL functionality.
All earlier unsafe baselines and unsuccessful harness attempts remain retained.

### Guardian scope

Canonical authority is one native Guardian with an explicit `user` link, its native
Student Guardian child rows, those Students and their Customers. Exact all-doctype
User Permissions for Guardian/Student/Customer must match that set. Missing/expanded
rules, ambiguous identity, empty membership, missing Customers, unsafe settings and
non-self-profile/global shares deny login and authenticated requests. Multiple children
are supported by the algorithm and unit-tested; broad native multi-child/mixed-role
usability and lifecycle coverage are not thereby certified.

The guard does not rely on the native email fallback for legacy Guardian invitations.
Establish explicit identity, links and scopes before permitting access. Native document
permissions remain responsible for authorized operations; these checks only deny, never
create broader permissions or parallel authorities.

A second boundary is needed for private attachments: core File ownership can otherwise
outlive permission on the attached Student. The deny-only File permission hook and v16
class mixin require parent access even for the old file owner. The mixin covers native
`is_downloadable` and `get_content` because core download/content paths can call the
File module permission helper directly, outside the ordinary controller-hook chain.
File-to-File parent cycles are denied in this restricted profile. Other native File
permissions remain in force. The synthetic adversarial fixture retains Guardian
ownership of an attachment to the unrelated Student; it must still be denied.

### Realtime resource boundary

The earlier known-ID synthetic task disclosure is preserved. The new positive control
uses a real native RQ job created as Alpha; authorization reads protected RQ `site` and
`user` metadata, not the task identifier alone. Subscription and each standard namespace
broadcast recheck the live HTTP session and resource permission. Target recipients are
explicitly checked socket IDs so a new room join cannot race into a previously checked
broadcast. Document rooms require native document read access, user rooms require the
current user, and task rooms require exact site and owner. Backend errors fail closed.

**Compatibility costs and limits:** broad site/website/doctype and combined-resource
broadcasts are denied; unchecked subscriptions and open-in-editor are disabled. This
is deliberately not transparent compatibility with every Desk realtime feature.
Delegated job supervision, clustered adapters, acknowledged/direct app-specific emits,
future handlers, proxy/origin trust, rate limits and high-fanout performance still need
qualification. A resource-delivery fix is not a public websocket deployment approval.

## Advisory reachability and remediation decisions

The per-entry record is `evidence/phase-2/frontend-advisory-triage.json`. Patched ranges
come from the public advisory API and are retained separately. Source claims about
frappe-ui 0.1.31 were checked against the exact hashes reported by the hosted module
collector, not inferred from an unrelated current package version.

- Development-server/editor findings are **not reachable through the qualified serving
  profile**, which runs Nginx/Gunicorn over built assets, not Vite/esbuild dev servers.
  This does not approve local dev-server exposure or Windows behavior.
- The two reported Vite/Rollup DOM-clobbering generator findings require cjs/iife/umd;
  the hosted production build reports **ES output only**. No universal XSS claim follows.
- linkify-it, markdown-it and ws have **no rendered package code** in this portal graph.
  Node/build/other-app use is separate, especially the actual realtime server inventory.
- Tiptap core/link, Showdown and socket.io-parser **are emitted**. They are not falsely
  labeled tree-shaken away. Source review found no TextEditor or socket initialization
  activation from the 33 pinned portal entrypoint/component/store files. FormControl
  does not instantiate an editor, and resourcesPlugin alone does not initialize sockets.
  This is a scoped dormant-code finding, not a waiver for future UI or other apps.
- Remaining tooling is **reachable during builds**; exploit-specific untrusted input
  prerequisites remain open. Browser absence cannot waive build-supply-chain risk.

Required changes before dependency acceptance:

1. Move the legacy Vite/Vue-plugin toolchain to a maintained compatible upstream line.
   Do not stop at an old patch that fixes only one of the 15 Vite findings. Published
   fixed-version branches are recorded per advisory; they are not an approved new lock.
2. Refresh compatible transitive tooling deliberately: examples of current-branch
   advisory floors include brace-expansion 2.1.4, braces 3.0.3, Browserslist 4.28.7,
   cross-spawn 7.0.5, glob 10.5.0, minimatch 9.0.7, nanoid 3.3.18, picomatch 2.3.2,
   PostCSS 8.5.23, Rollup 2.80.0 and YAML 2.8.3. These are remediation inputs, **not**
   claims of complete vulnerability absence, support lifetime or compatibility.
3. When retaining relevant paths, qualify markdown-it 14.2.0, linkify-it 5.0.2,
   socket.io-parser 4.2.7 and ws 8.21.0 against their respective runtime surfaces.
4. Tiptap core's recorded fix starts at 3.30.4, outside installed 2.x. A coherent
   editor/frappe-ui update is required; forcing core 3.x under 2.x extensions is not an
   acceptable fix. Showdown advisories list **no patched release**: remove unused parser
   exposure through maintained upstream changes or qualify a reviewed replacement.
5. Keep dev/editor endpoints inaccessible, keep build inputs controlled and preserve
   native HTML escaping. Rerun audit, production graph, affected-path tests and browser
   regressions for any changed dependency inputs. No `audit fix` or blanket waiver.

Education branch candidate `22e0910...` was reviewed but not adopted: its ten commits
include portal/API/role changes, but no frontend dependency/lockfile update in the
comparison. Newer branch source is not evidence that these dependency findings are fixed.

## Operational and upgrade interpretation

Payroll read and Salary Register report ACLs are separate from payroll posting. The
scheduler test waits for a native Scheduled Job Log status **Complete**, created by the
actual scheduler and worker, not by manually enqueueing or forcing the event. An earlier
180-second observer was shorter than the pinned default **240-second scheduler tick**;
that failed evidence is retained. The corrected observer uses the actual tick plus 120
seconds for a cron boundary/worker allowance, and reports both values. No execution
assertion is weakened and no scheduled time is forged.

The expanded upgrade changes Frappe 16.33.0 to 16.33.1 while holding the other four
upstream app revisions fixed. It uses a separate Bench/database, nine native business
fixture checks, pre-upgrade backup, requirements/migrate/build and five post-upgrade
record/file/schema checks plus replay. It does **not** establish rollback, independent
ERPNext/Education/HRMS version upgrades, security-extension upgrade/rollback, a separately
hosted restore drill or production availability.

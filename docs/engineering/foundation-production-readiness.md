# Phase 2 security and production-readiness continuation

## Current remediation checkpoint — supersedes the previous result below

**REJECT current production acceptance.** Guardian and realtime resource guard corrections
have enumerated hosted proof through run **34809413852**. Payroll report ACLs, production
build/source reachability evidence and the five-app framework patch upgrade also have
verified results. Dependency remediation and broader qualification are not complete.

The newer legacy private-file owner boundary and scheduler observer correction remain
**unverified** after GitHub access expired with HTTP 401. Runs **34809817009** and
**34810723925** must be retrieved before relying on them. See the authoritative
[hardening remediation report](foundation-hardening-remediation.md) for exact scope,
source boundaries, compatibility limitations and the current acceptance decision.

The following prior checkpoint is retained as **historical failed evidence**, not as a
claim that the corrected 0.2.0 Guardian/realtime checks still fail.

## Final recommendation — REJECT current Phase 2/production acceptance

Run **34806388937**, commit `675736e540aacdbc46635a3ec121e683d1a58801`, completed
with failure in **11m54s**. Both exact Check reports were retrieved and their compact
JSON SHA-256 verified: runtime Check **103861011181**, remaining-gate Check
**103861013308**. See `evidence/phase-2/hosted/{runtime,remaining}-34806388937.json`.
No unknown active run is relied upon. This rejects current acceptance, not the use of
canonical upstream authorities as a candidate architecture for continued qualification.

| Remaining area | Hosted result | Gate interpretation |
|---|---|---|
| Frontend dependencies | 255 package names audited; 57 advisory entries / 21 packages reconfirmed | **FAIL**. All retained entries triaged; reachability/remediation remain open |
| Native roles/payroll | 36 of 37 checks pass, including real draft payroll and all seven payroll read boundaries | **PARTIAL / FAIL**. Unscoped Guardian unrelated-Student request returned 200, not 403 |
| Guardian native scopes | Own Student 200; unrelated Student 403 after explicit Student/Customer User Permissions | Narrow remedy **PASS**; not fail-closed provisioning, multi-child/relinking, portal/file or mixed-role qualification |
| Realtime document events | Two Student sockets connect; owner event delivered; cross-student document event absent | Enumerated document-room check **PASS**, not all realtime authorization |
| Realtime task events | Second user received synthetic task marker when given its identifier | **FAIL** under the tested ownership-isolation requirement |
| Framework patch upgrade | Frappe 16.33.0→16.33.1, 19 stages, native record preservation and replay pass | Narrow framework experiment **PASS**; full bundle upgrade/rollback remains incomplete |
| Authenticated HTML cache | Both portal responses have no-store/no-cache/must-revalidate/max-age=0 | Narrow cache policy **PASS**; production TLS/proxy/session-switch/headers not qualified |

**Existing regressions also passed again:** business 9; ordinary restore 5; restricted
HTTP 10; source isolation 47; Chromium 5; hardened recovery 7; recovered isolation 47;
cache/RQ and encrypted/session recovery stages; unchanged upstream permission/sharing
modules reporting 10 and 15 tests run. **29 local helper tests pass**, including lossless
Check-transport round trips and protected-branch rejection. These are not substitutes
for full role, domain, operational or dependency acceptance.

### Blocking findings and closure requirements

1. **SEC-GUARDIAN-01:** the native Guardian role plus a canonical Guardian/Student link
   does not itself enforce the required generic REST isolation. The request to the
   unrelated Student returned 200; the negative assertion did not retain its response
   body, so no additional field-level disclosure claim is made. Explicit native scopes
   corrected the enumerated reads, but missing/expanded/revoked scopes, multi-child
   membership, shares, files, APIs and mixed roles need fail-closed lifecycle proof.
   The Student-specific generic guard was not extended to Guardian in this continuation.
2. **SEC-RT-TASK-01:** the known-identifier synthetic task event was delivered to both
   users. Pinned `frappe/realtime/handlers.js` joins task/progress rooms without the
   document permission callback used for document rooms. This is evidence about known
   identifiers and synthetic markers—not proof of task-ID guessing, real payroll-job
   disclosure, cross-site leakage or a persisted RQ job ownership check. Close with a
   supported owner/delegation authorization design and real-job, site, revocation and
   negative delivery regressions. Do not treat identifier secrecy alone as authorization.
3. **SEC-DEPS-01:** advisory triage is not remediation or proof of non-reachability.
   Require reviewed patched inputs and hosted audit/build/affected-path evidence. No
   advisory has been waived merely because it is transitive or used in build tooling.

Earlier **34804852658** and **34805581935** failures are preserved. Payroll initially
needed a native Holiday List Assignment; inserting and submitting that normal document
resolved the prerequisite without disabling a controller. Realtime initially used the
wrong login routing and then an Origin without the proxy port; native realtime uses
Origin for its backend permission callback. Correcting the test Origin to the actual
8080 proxy made the checks execute and reveal the task-room failure.

**Remaining work is not all complete.** In particular, this run does not clear the
broader operational and coverage limits below. No production or TOEFL work is authorized.

## Acceptance standard

No TOEFL-specific implementation. No upstream core edits. Only the authorized Arena
branch is changed. A successful narrow check does not authorize deployment or clear
unexecuted acceptance criteria. Historical failures remain evidence.

## Frontend advisory triage

All **57 retained advisory entries / 21 packages** are classified individually in
`evidence/phase-2/frontend-advisory-triage.json`, with original identifiers, affected
ranges, installed versions, priority and open disposition. No advisory is waived.

- **Content processing:** Tiptap core/link, markdown-it, linkify-it and Showdown merit
  priority review for XSS/DoS. The pinned portal imports frappe-ui; that alone does not
  prove every transitive editor/parser path reaches a deployed bundle or attacker input.
- **Generated output as well as tooling:** Vite, Rollup and PostCSS cannot be dismissed
  as development-only: some findings concern emitted scripts/CSS. Development-server
  exposure findings are separate; this qualification does not expose Vite publicly.
- **Transport:** socket.io-parser and ws need runtime-specific inventory/reachability.
  A Node ws finding in the frontend dependency tree does not establish that the running
  Frappe realtime server uses that exact version or vulnerable code path.
- **Build/dependency tooling:** remaining globbing, spawning, YAML and related findings
  remain open. Trusted synthetic builds are not proof of safety for untrusted source,
  package data, filenames or build configuration.

Remediation requires a maintained upstream dependency/release or narrowly reviewed
patch, fixed immutable inputs, fresh audit and affected-path regressions. Blind
`audit fix`, blanket dev-dependency exclusions and forced lockfile regeneration are
not acceptable. The remaining-gate workflow repeats the registry audit on its actual
installed Education dependency tree; failures are preserved, not converted to warnings.

## Reproducible hosted checks and scope

- Native Academics User, Instructor, Accounts User, HR User, Employee and Guardian
  accounts; actual Employee/Instructor and Guardian/Student relationships; real login
  and REST reads. Guardian must not read an unrelated Student. Staff without payroll
  duties or employee ownership must not read another employee's salary slip.
- Draft payroll through native Salary Component, Salary Structure, Assignment and
  Salary Slip controllers. Fixture failures explicitly block salary-read conclusions;
  a nonexistent document/404 is never accepted as payroll isolation proof.
- Actual authenticated Socket.IO document room delivery with positive owner control,
  cross-student denial, and an adversarial known-task-identifier subscription. The task
  probe intentionally assumes the identifier is known; it tests whether identifiers
  function as bearer capabilities, not their entropy or guessing difficulty.
- Authenticated HTML cache policy. A failing no-store assertion is an operational
  confidentiality gap; HTTP-only loopback cannot establish production TLS/Secure-cookie
  configuration and does not claim to.
- **Isolated Frappe-only** v16.33.0 `33bf510b17afcaaa857ed38b921d8e9e50dcd232` →
  v16.33.1 `988e54f3c4c291e2077a83809663f123731abe76`: separate Bench/database,
  pre-upgrade backup, native persistent record, requirements, migration, asset build,
  record preservation and migration replay. This is explicitly **not a full-bundle
  ERPNext/Education/HRMS upgrade or rollback qualification**.

Role expectations above are qualification least-privilege requirements, not a claim
that upstream promises institution-specific staff scoping. A mismatch requires policy
and native-permission review, not changing an assertion to accept the disclosure.

## Operational and coverage limits

Full mixed-role/report/export/print flows, guardian portal/relinking, payroll posting,
actual scheduled task execution, restart durability, production reverse proxy/TLS,
monitoring/alerting, secrets rotation, restore drills on separate infrastructure,
full-bundle upgrade/rollback and representative load/accessibility remain incomplete.
Previously proven cache/RQ, clean install, native backup/restore and session revocation
are not replacements for these requirements.

## Evidence transport

The workflow publishes independent `Foundation runtime evidence` and `Foundation
remaining gate evidence` Checks. Reports exceeding the Check text budget use a JSON
`encoding: gzip+base64` envelope. Decode `data`, gunzip, and verify its SHA-256 against
both `report_sha256` and the Check summary before reading the inner JSON. No observations
are removed. Full sanitized artifacts are retained for 14 days; blob downloads may be
unavailable from this sandbox. No configurations, backups or credentials are published.

## Reproduction and decision boundary

```sh
gh workflow run foundation-runtime.yml --ref arena/01a09bf3-tofel-house-erp -f profile=hardened
gh run watch RUN_ID --exit-status
```

The hardened profile still exits nonzero for the retained new Guardian baseline,
known-task event failure and positive advisory results. Do not alter assertions merely
to obtain a green run. Qualification changes must preserve their baseline reports and
publish separate remediated results. Main remains unchanged; no TOEFL app, product UI,
placement, scoring, custom finance/HR or upstream core implementation was introduced.

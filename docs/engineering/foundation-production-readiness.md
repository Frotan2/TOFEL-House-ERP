# Phase 2 security and production-readiness continuation

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

## Newly authored hosted checks (not passes until evidence is retrieved)

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

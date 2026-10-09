# Acceptance ledger

One canonical ledger for final acceptance of TOEFL House ERP as a clean,
understandable, maintainable product. Each row records a finding, severity,
required action, evidence, and status. Status changes only when evidence
exists. A passing owned suite or CI qualification is not, by itself, production
readiness. **Production authorization remains REJECT.**

**Evidence snapshot (2026-10-09; [PR #14](https://github.com/Frotan2/TOFEL-House-ERP/pull/14) merged as `13482fe285768e43ccadc0d93182a9a14eddf953`):**
The current local worktree's full Python command `python3 -m unittest discover
-s tests -t .` ran **1,207 tests, OK**, after the latest hold wording and
packaging-contract assertions; `git diff --check` passed. This local suite is
not live Frappe/Docker/Owner recovery evidence. The hosted checks on PR #15's
prior tracked head `58337b6`—before the current local-only hold clarifications—were
Owned suite [37975034446](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37975034446)
and [37975039678](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37975039678)
**PASS** (Ruff static analysis, Python test tree, Node suites), and Product image
[37975034434](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37975034434)
**PASS** in both the Windows stale-worktree/EOL and Linux image jobs. No local
Ruff, Node, or Docker build was run. No Windows Owner operation or Owner
backup/restore was run.

Hosted on merged commit `13482fe`: Product image
[37940397957](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397957),
Native lifecycle [37940397967](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397967),
and Owned suite [37940397970](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397970)
**PASS**. Foundation runtime [37940398359](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940398359)
**FAIL** in both dependency-audit gates: 160 matches across 47 packages and 8
untriaged identifier matches (7 unique advisories). The Native lifecycle run
passes and restores into a new site/database in an ephemeral Bench, but its
result artifact could not be retrieved, so this review has no per-run counts or
hashes.

Owner backup, restore, retention, Windows/Docker Desktop, Task Scheduler,
Tailscale, and key-custody evidence remain **UNVERIFIED / HOLD**. Preserve the
existing site, `product/data`, credentials, and backups; do not run the Owner
backup/retention helper, edit backup policy, restore, cleanup/deletion, or
activation. Production authorization remains **REJECTED**.

## Current gate status

| Gate | Status | Evidence boundary |
|---|---|---|
| Focused local backup/restore/native-adapter/lifecycle tests | **PASS** | Exact command in the evidence snapshot: 48 tests. This is not the full test tree or a live Frappe/Docker restore. |
| Hosted CI on merged commit `13482fe` | **PASS** (Product image, Native lifecycle, Owned suite); **FAIL** (Foundation runtime) | Runs `37940397957`, `37940397967`, `37940397970`, `37940398359`. The artifact payload from Native lifecycle was not retrievable. |
| Product image build and synthetic first-boot/recovery | **PASS in CI; Owner runtime UNVERIFIED** | `37940397957` passed the actual Linux image build, synthetic backup/restore, browser, proxy contract and upgrade/rollback. Product-image restore uses its existing disposable CI site. |
| Native Frappe restore into a separate target | **PASS in CI; scope incomplete** | `37940397967` creates `placement-restore.localhost` plus a distinct DB inside the ephemeral Bench. It checks records and one private file, but not all acceptance criteria below. |
| Foundation runtime and SEC-DEPS-01 gate | **FAIL** | `37940398359` failed both dependency audits. Annotation: 160 matches / 47 packages; 8 untriaged matches / 7 unique advisories. No advisory is waived by this entry. |
| Local Docker / Owner Docker Desktop | **UNVERIFIED** | No local Docker build or Owner Windows operation was performed in this continuation. Hosted Linux CI does not qualify Docker Desktop. |
| Owner backup / retention / restore / activation | **UNVERIFIED / HOLD** | Retention remains unresolved. No Owner helper, restore, cleanup/deletion, or activation is authorized. Existing data and backups must remain untouched. |
| Owner Task Scheduler, drive, key custody, and Tailscale | **UNVERIFIED** | No actual Owner-machine or private-tailnet evidence has been supplied. |
| Production authorization | **REJECTED** | Remains rejected until all mandatory runtime gates, actual Owner/deployment evidence, and explicit authorization are supplied and verified. |

## Findings

| # | Severity | Finding | Required action | Evidence | Status |
|---|----------|---------|-----------------|----------|--------|
| 1 | P0 | Windows restart and failure recovery must be diagnosable | Keep restart policies and plain-language service/log diagnostics; execute the Owner's Windows install/start/stop/restart/recovery checklist | `product/docker-compose.yml`; `product/windows/*.cmd`; `tests/foundation/test_product_packaging.py::RecoveryContract`; `product/windows/VALIDATION.md` (Evidence 1–10); [parent Owned suite 37940397970](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397970) | **UNVERIFIED** — recovery contracts in Owned CI `37940397970` and simulated fresh-worktree normalization in Product-image CI `37940397957` **PASS**. Actual Owner Windows lifecycle evidence is absent. |
| 2 | P0 | Real central-server + Tailscale multi-user path is unproven | Owner validates two real clients, access control, Tailscale Serve web and `/socket.io` routes, and a real WebSocket upgrade; never expose a public edge | `docs/engineering/LAUNCH-RUNBOOK.md` §6; `product/windows/VALIDATION.md` Evidence 13; Product-image workflow simulates proxy/loopback behavior only; it does **not** run Tailscale Serve or a real tailnet/WebSocket | **UNVERIFIED** — the current Product-image proxy/tailnet contract simulation `37940397957` **PASS**; no real Owner tailnet, two-client, WebSocket, or non-tailnet-denial evidence. |
| 3 | P0 | Dependency/supply-chain pin contradictions | Maintain one canonical pinned matrix, verify source commits and Node tarball hash, and keep image/probe inputs aligned; independently re-triage the current advisory and shipped frontend paths | `docs/engineering/foundation-version-matrix.json`; `product/app.Dockerfile`; `product/docker-compose.yml`; `.github/workflows/product-image.yml`; `tools/foundation/runner_probe.py`; `tests/foundation/test_product_packaging.py::DependencyPinContract`; Foundation run [37940398359](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940398359); open evidence PR [#13](https://github.com/Frotan2/TOFEL-House-ERP/pull/13) | **PASS** — static pin contracts and Product-image Compose/Node integrity checks. **FAIL** — Foundation dependency audits (160 matches / 47 packages; 8 untriaged matches / 7 unique). PR #13 is still open and is not accepted evidence. ECharts is now marked **BLOCKED** there, HRMS ProseMirror is identified as a reachable product blocker, and the oauthlib mirror is verified; its WeasyPrint SSRF dispositions and a contradictory ECharts `fix_path` remain unresolved. Public-edge exposure remains deferred, but production authorization is still **REJECTED**. |
| 4 | P0 | Product-facing administration must state live, separate site-mode and production-authorization facts | Keep the Owner cockpit and Administration control centre truthful; never let operational `PRODUCTION` mode imply release approval | `apps/toefl_house/toefl_house/desk/owner.py`; `administration.py`; `tests/foundation/test_production_state_contract.py`; `README.md`; `docs/PRODUCT.md`; this runbook; current Owned suite | **PASS in Owned CI** — static/contract implementation tests pass. **UNVERIFIED** — no live Owner-site UI check; production authorization remains **REJECTED**. |
| 5 | P1 | Branch isolation and permissions must cover all owned surfaces | Keep branch scope on native permissions, guarded commands, desk projections and REST/RPC surfaces; unscoped controls and unresolved branch identities must behave as documented | `docs/ROLE-DESKS.md`; `apps/toefl_house/toefl_house/permissions.py`; `tests/foundation/test_app_assembly.py`; `tools/native/native_checks.py`; current Owned suite [37940397970](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397970); Native lifecycle [37940397967](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397967) | **PASS in CI** — current Owned suite and Native lifecycle checks pass. **UNVERIFIED** — actual Owner branch/user setup is outstanding; the CI fixture is synthetic. |
| 6 | P1 | Teacher compensation operational readiness and daily-user desk gap | Keep the Finance Manager compensation queue actionable while projecting no rate/term/amount and retaining D12 separation of duties | `apps/toefl_house/toefl_house/desk/finance.py`; `apps/toefl_house/toefl_house/public/js/th_role_desks.js`; `tests/desk/test_desk_contract.py`; `tools/native/native_checks.py`; current Owned suite; parent Owned suite [37940397970](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397970) | **PASS in Owned CI** — source/contract tests pass in suite `37940397970`. **UNVERIFIED** — actual Owner-entered compensation values and statutory/payroll decisions remain gated. |
| 7 | P1 | Site-mode activation/deactivation must be symmetric | Restore the previous settings on any failed post-write verification and keep regression coverage | `product/activate.py`; `tests/foundation/test_product_activation.py`; current Owned suite | **PASS in CI** — activation/deactivation contract tests and Product-image synthetic mode lifecycle `37940397957` pass. **UNVERIFIED** — no Owner activation/deactivation run; backup remains on HOLD and production authorization remains REJECTED. |
| 8 | P1 | Encrypted upgrade/rollback and recovery rehearsal | Keep pinned Frappe's native backup/restore as sole authority; verify secret transport, preserve native backups, restore to a new site/database for the isolated rehearsal, and prove record/file content, integrity, metadata, CWD, restart, malformed/missing inputs, and explicit failure handling. Keep all CI evidence distinct from Owner authorization. | `product/backup.py`; `product/native_gpg.py`; `product/native_db.py`; `product/restore.py`; `tools/native/run_native.py`; `tools/native/runtime_restore.py`; focused tests in `tests/foundation/test_product_backup.py`, `test_product_restore.py`, `test_product_restore_contract.py`; `.github/workflows/native-lifecycle.yml`; `.github/workflows/product-image.yml`; `docs/engineering/LAUNCH-RUNBOOK.md` §§7–8; Product image [37940397957](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397957); Native lifecycle [37940397967](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397967) | **PARTIAL — CI PASS, verifier gaps remain.** Product-image restore into the same disposable site verifies public/private marker contents and rollback behavior. Native lifecycle creates a separate restore site/database in an ephemeral Bench; its snapshot checks 14 DocTypes by count/name digest and one private file's content hash plus selected attachment fields. It does not verify a public file on the clean target, filesystem owner/mode/UID/GID, or the restored snapshot after target restart. CWD restoration is asserted by a stubbed failure-path test, not a successful live restore. Missing/invalid inputs and sanitized explicit failures are unit-tested; malformed archive semantics are not established. Artifact values are unavailable. **UNVERIFIED / HOLD** — no Owner backup/restore, key custody, or retention authorization; do not restore over the existing site. |
| 9 | P1 | No measured performance baseline | Keep per-run measurements explicitly marked as measurements, not business policy or an Owner capacity target | `product/perf_baseline.py`; Product-image “Performance baseline” step; prior [Product image 37658914613](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37658914613); current Product-image run [37940397957](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397957) | **PASS** — Product-image CI `37940397957` captured a measured baseline and labels it as measurement, not policy. **UNVERIFIED** — no Owner capacity target is supplied; CI timings are not an Owner target. |
| 10 | P1 | Owner/GM operational visibility and recovery instructions | Preserve truthful live job/service facts and diagnosable repair; provide only non-destructive Owner recovery checks until an isolated restore workflow is qualified | GM Operations desk; `product/windows/VALIDATION.md`; `docs/engineering/LAUNCH-RUNBOOK.md` §§5–8; current Owned suite [37940397970](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397970) | **PARTIAL** — the in-place Owner restore recipe is withdrawn and replaced by read-only checks plus a separate-disposable-site requirement. **UNVERIFIED** — no Owner Windows, backup, or restore evidence. |
| 11 | P0 | Browser login previously rendered with missing JS bundles, so login did nothing | Keep WSGI static middleware in pinned Frappe order, idempotently synchronize built app assets, and prove real browser login through the current image | `product/wsgi.py`; `product/bootstrap.py`; `tests/foundation/test_product_packaging.py`; Product-image browser/login step; historical [Product image 37658914613](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37658914613); current Product-image run [37940397957](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397957) | **PASS** — Product-image CI `37940397957` passed real Chromium login against its disposable site after asset reconciliation. **UNVERIFIED** — actual Owner Windows sign-in and persisted-data smoke test have not been performed. |
| 12 | P0 | All guarded Owner-policy commands must be registered to the correct audit authority | Keep all four Owner policy command kinds mapped to `business_policy`, fail closed on missing authority, and test the complete registry | `apps/toefl_house/toefl_house/configuration/audit.py`; `tests/operations/test_owner_operations_policy.py`; static AST audit of all literal audit kinds; current Owned suite; parent [Owned suite 37940397970](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397970) | **PASS in Owned CI** — command/audit/resolver contract tests pass in `37940397970`. **UNVERIFIED** — no live Owner configuration, saved version/audit or runtime qualification. |
| 13 | P0 | Bootstrap provisions Administrator, not the daily Course Owner | When Owner configuration is authorized, use a separate native System User with Course Owner role and keep Administrator setup/recovery-only; while retention is unresolved, do not create, change, validate, or save Backup & Recovery policy | `product/windows/VALIDATION.md` Step 4; README first-run instructions | **UNVERIFIED** — Product-image CI creates a disposable synthetic Course Owner; no actual Owner account creation, role assignment, login or policy configuration evidence exists. |
| 14 | P0 | Real Owner policy, same-computer separate-drive backup and restore/key custody are not demonstrated; retention behavior requires an explicit Owner choice | Preserve the current site/backups. Until the Owner retention decision and an isolated restore procedure are approved, perform read-only inventory only; never overwrite the existing site, clean up data, or activate | `product/windows/Backup TOEFL House ERP.ps1`; `product/windows/VALIDATION.md` “Backup and restore”; `docs/engineering/LAUNCH-RUNBOOK.md` §§0–1, 7–8; Product image [37940397957](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397957); Native lifecycle [37940397967](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397967) | **UNVERIFIED / HOLD** — the retention choice is unresolved; do not run the helper, backup, restore, cleanup/deletion, or activation. CI synthetic restores are not Owner evidence. Owner drive, key custody, Task Scheduler, and recovery remain unverified. Preserve all existing runtime data and backups; production authorization remains **REJECTED**. |

## Restore verifier scope audit (2026-10-09)

| Criterion | Observed evidence | Disposition |
|---|---|---|
| Synthetic records | `tools/native/runtime_restore.py` requires at least one row in each listed DocType and compares source/target counts plus SHA-256 digests of sorted record names. It does not compare record field values or claim institutional-data completeness. | **PARTIAL** — name/count continuity only; field-level integrity is not established. |
| Public/private file bytes | Native target: one real Frappe `File` record, private only; the verifier calls `get_content()` and compares its SHA-256. Product-image CI checks synthetic public/private marker bytes after restoring the same disposable site. | **PARTIAL** — no public marker is checked on the clean Native target. |
| Clean restore target and database | `tools/native/run_native.py` creates `placement-restore.localhost`, installs apps and uses a distinct database and DB password inside the same ephemeral Bench. The product-image restore uses its existing disposable CI site. | **PASS in Native CI** for separate site/database; no separate Owner Bench was qualified. |
| Artifact/content integrity | The runner hashes and reports the source encrypted DB/public/private artifacts, then copies them to the target with `shutil.copy2` without comparing target-copy hashes to the source hashes. `product/restore.py` compares each target-side input with its own temporary staged copy before calling Frappe; the snapshot then checks record names and one private-file digest. | **PARTIAL** — source-to-target artifact integrity is not directly asserted; run-specific report values are unavailable. |
| File metadata, permissions, and ownership | Native verifier checks `is_private`, `attached_to_doctype`, a digest of `attached_to_name`, and file-content SHA-256. It does not assert the Frappe File owner, permission/share metadata, URL/size metadata, filesystem mode, UID/GID, or ACL. The adapter's mode `0600` check concerns temporary restore inputs, not restored site files. | **NOT PROVEN**. |
| CWD restoration | `product/restore.py` restores the caller CWD in `finally`. The local stub test asserts CWD equality after an injected restore failure; the successful live restore does not assert post-return CWD. | **PARTIAL** — failure-path unit evidence only. |
| Restart persistence | Product-image CI restarts/redeploys the disposable same-site stack and checks synthetic markers after restore. Native lifecycle does not restart the new target and re-verify its snapshot. | **PARTIAL** — not proven for the clean Native target. |
| Missing/malformed inputs and explicit failures | The Native snapshot verifier has no dedicated negative-case test for a malformed/missing expectation, a record mismatch, or a file mismatch; its checks raise on invalid status or mismatch, and the runner fails on non-zero/exception. Separate adapter unit tests reject invalid site/credentials/CLI input and missing required artifact roles, and inject a sanitized `SystemExit`/`FileNotFoundError`. No live test uses malformed encrypted SQL/archive payloads. | **PARTIAL** — failure behavior is partly unit-tested; Native verifier negative cases and malformed native payload behavior are not. |
| Owner-machine execution | No Windows Owner backup, restore, Task Scheduler, GPG/key-custody, or Docker Desktop operation was run. | **UNVERIFIED / HOLD**. |

The Native verifier's 14 DocTypes are `TH Placement Item Revision`, `TH
Placement Attempt`, `TH Placement Decision`, `TH Admission Decision`, `Program
Enrollment`, `Student Group`, `Course Schedule`, `Student Attendance`, `TH
Instructor Contract`, `TH Teaching Assignment`, `TH Correction Policy`, `TH
Correction Request`, `Fees`, and `Sales Invoice`. Each source/target comparison
covers only count and sorted names digest—not each record's fields or links.

The Native result artifact listed for run `37940397967` could not be retrieved
(`EOF` from the artifact results host); do not quote generated per-run counts,
hashes, or report values. The Owner restore instructions now prohibit replacing
the existing site and provide read-only checks only. Any later rehearsal must
target a new isolated disposable site/database and must not clean up or alter
existing runtime data or backups.

## Security evidence reconciliation (2026-10-09)

- **160 vs 158:** CI reported 160 identifier-level matches in 47 package
  groups. The open PR #13 replay snapshot has 96 npm + 62 PyPI records = 158;
  the two extra oauthlib matches are GHSA-hj66 and PYSEC-2026-4113. The PyPA YAML alias record
  links both to CVE-2026-49264. This reconciles the raw count; it does not turn
  160 identifiers into 160 distinct vulnerabilities. The Foundation run still
  had 8 untriaged matches (7 unique) and failed.
- **ECharts:** the pinned `frappe`, Education, HRMS frontend/roster lockfiles
  inspected in the open PR #13 branch contain no `echarts` or
  `frappe-ui@0.1.278`; its 2026-10-09 evidence changes the old `NOT_REACHABLE`
  claim to **BLOCKED**. The JSON `fix_path` still says the vulnerable component
  is not bundled/unreachable, which conflicts with that disposition and should
  be removed. The proposed PR #13 corrections are unmerged.
- **ProseMirror:** Education's `frappe-ui@0.1.31` dependency resolves
  `prosemirror-view@1.33.1`; the Education SPA has no editor construction. The
  product's pinned HRMS frontend resolves `frappe-ui@0.1.105` and
  `prosemirror-view@1.31.3` (HRMS roster: `1.33.6`), builds and serves the SPA,
  and mounts `TextEditor` for user-editable Text Editor fields. The open PR #13
  erratum correctly records the HRMS paste-XSS path as a product-level open
  blocker; it is outside the current Foundation frontend audit. This is not
  release approval or an Owner risk acceptance.
- **WeasyPrint:** the base register still marks `GHSA-jf6q-chmf-3h3v` (SSRF)
  and `GHSA-jhhc-3hcp-qhm5` (presentational-hints CSS injection), plus their
  `PYSEC-2026-3940` and `PYSEC-2026-3412` mirrors, **MITIGATED** via owned
  whitelist wrappers. Pinned Frappe directly imports/calls vendor renderers from
  `frappe/printing/doctype/print_format/print_format.py`,
  `frappe/utils/print_utils.py`, and `frappe/www/printview.py`, bypassing those
  overrides. The owned wrapper forwards `format=`, `doc=`, and
  `no_letterhead=` keywords that the pinned vendor signatures do not accept.
  Override-wiring tests do not prove direct-path coverage. Inspected Frappe
  `render()` calls omit `presentational_hints`, so CSS-injection reachability is
  unresolved, not confirmed. The Ghostscript build guard addresses only the
  separate `GHSA-r543` RCE precondition; it does not mitigate SSRF. The current
  loader nevertheless counts these unsupported dispositions as closed. Keep
  production/security approval blocked until the exact vendor paths and
  advisory preconditions are re-triaged; do not claim either finding is
  confirmed exploitable or mitigated from this evidence. Review comment
  [6086576384](https://github.com/Frotan2/TOFEL-House-ERP/pull/13#issuecomment-6086576384)
  has no direct response. Later coordination comment
  [6086997935](https://github.com/Frotan2/TOFEL-House-ERP/pull/13#issuecomment-6086997935)
  updates CI/restore evidence, but does not address the WeasyPrint or ECharts
  findings.
- **Dangling references:** the base register cites
  `tests/foundation/test_sec_deps_triage.py`, which is absent. Open PR #13 adds
  replacement references in an erratum and static tests, but those check
  override wiring/owned fixtures—not full pinned vendor call-path coverage.
  The erratum does not change the base register's `MITIGATED` statuses or gate.
- **PR #13 status (latest refresh):** head `58d20fd`. Product image
  [37969852289](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37969852289)
  on `8bca360` **PASS**; the latest `58d20fd` commit changes the README only
  and has no new Product-image check. Owned suites
  [37971951449](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37971951449)
  / [37971945002](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37971945002)
  on the current head **PASS**. Foundation run
  [37971944970](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37971944970)
  on `58d20fd` **PASS**. Earlier Foundation run
  [37969450759](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37969450759)
  on `57c73b6` **PASS**. PR #13 remains open and unmerged.

## Scope decisions (Owner)

- **Backup / recovery:** the current requirement is a verified encrypted backup
  on a separate fixed local drive on the same computer, with a tested restore
  procedure. Off-site/NAS/second-device/cloud backup is explicitly deferred and
  is not a current release gate. The CI loop-backed filesystem is only a
  synthetic separate-filesystem mechanism check; it is not the Owner's drive.
- **Multi-user access:** central server + private Tailscale tailnet (Owner
  decisions D13/D15). No public internet edge, provider, hostname, DNS, or
  public TLS is a current launch requirement. CI's HTTP proxy/foreign-host
  contract does not qualify a real tailnet, Tailscale Serve, or WebSocket.
- **Dependency advisories:** Foundation runtime [37940398359](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940398359)
  on merged commit `13482fe` failed both dependency-audit gates. Its annotation
  reports 160 identifier matches across 47 packages and 8 untriaged matches
  representing 7 unique advisories. The 158-match replay is 96 npm + 62 PyPI;
  the two additional oauthlib IDs are `GHSA-hj66-6f7g-4r5v` and
  `PYSEC-2026-4113`. The PyPA Advisory Database record for
  [PYSEC-2026-4113](https://github.com/pypa/advisory-database/blob/main/vulns/oauthlib/PYSEC-2026-4113.yaml)
  lists GHSA-hj66 and CVE-2026-49264 as aliases, so they are two identifier
  matches for one underlying advisory, not two proven unique vulnerabilities.
  Open PR [#13](https://github.com/Frotan2/TOFEL-House-ERP/pull/13) corrects
  several evidence issues but is not merged or accepted as release evidence.
  Its ECharts entry is **BLOCKED** (not NOT_REACHABLE) and it identifies the
  reachable HRMS ProseMirror path as an open product blocker. A contradictory
  ECharts fix-path claim and the base WeasyPrint SSRF `MITIGATED` claims remain
  unresolved: direct Frappe renderer imports bypass the owned whitelist
  overrides, and the wrapper's forwarded keywords do not match the pinned
  vendor signatures. The Ghostscript build guard addresses only the RCE
  prerequisite, not the SSRF paths. Do not treat current green status for those
  base IDs as verified mitigation. SEC-DEPS-01 remains relevant to public-edge
  exposure; it does not authorize production operation or supersede D15.
- **D15/SEC-DEPS clarification remains pending:** `docs/owner-decisions.json`
  D15 says production stays REJECT while SEC-DEPS-01 is REJECT, while
  `docs/PRODUCT.md` and this ledger scope the dependency gate to a future
  public-internet edge. The selected deployment is still local server +
  Tailscale; this pass does not reinterpret or supersede D15. A successful
  audit is evidence, not Owner authorization or a decision update. Keep
  production REJECT until the Owner records the intended SEC-DEPS status/scope
  and the actual Owner/deployment gates pass; do not add a public-edge
  requirement to the current launch.
- **Native authority:** ERPNext/Frappe/Education/HRMS remain authoritative; no
  parallel student, course, class, enrollment, accounting, or payroll ledger
  is introduced by this lifecycle work.
- **Site mode is not release authorization:** the guarded operational mode may
  report `PRODUCTION` only after its own checks. Product status, Owner desks,
  and this ledger must continue to report production authorization **REJECT**
  until all applicable engineering, Owner, and non-engineering gates have
  genuine evidence.

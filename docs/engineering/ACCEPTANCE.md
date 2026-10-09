# Acceptance ledger

One canonical ledger for final acceptance of TOEFL House ERP as a clean,
understandable, maintainable product. Each row records a finding, severity,
required action, evidence, and status. Status changes only when evidence
exists. A passing owned suite or CI qualification is not, by itself, production
readiness. **Production authorization remains REJECT.**

**Evidence snapshot (2026-10-10; [PR #14](https://github.com/Frotan2/TOFEL-House-ERP/pull/14) merged as `13482fe285768e43ccadc0d93182a9a14eddf953`):**
The local full Python command `python3 -m unittest discover -s tests -t .` ran
**1,207 tests in 14.769s — OK** after the Owner-hold wording, packaging-contract
assertions, and this evidence-ledger refresh; `git diff --check` passed. This
local suite is not live Frappe/Docker/Owner recovery evidence. PR #15 remains
**OPEN**, not merged. At the start of this ledger refresh, its published head
was `ea46ce67de326f10a47d12255062615379a9dd47`; the then-current Owned runs [37976713217](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37976713217)
and [37976718591](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37976718591)
**PASS** (Ruff static analysis, Python test tree, Node suites). Product image
[37976606342](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37976606342)
**PASS** in both the Windows stale-worktree/EOL and Linux image jobs on
`2109216`; all later PR #15 commits through this evidence refresh changed only
the Acceptance ledger, so no Product-image check was triggered for them.
No Foundation runtime check was present on PR #15. No local Ruff, Node, or Docker
build was run. No Windows Owner operation or Owner backup/restore was run.

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
| 3 | P0 | Dependency/supply-chain pin contradictions | Maintain one canonical pinned matrix, verify source commits and Node tarball hash, and keep image/probe inputs aligned; independently re-triage every current advisory and shipped frontend path | `docs/engineering/foundation-version-matrix.json`; `product/app.Dockerfile`; `product/docker-compose.yml`; `.github/workflows/product-image.yml`; `tools/foundation/runner_probe.py`; `tests/foundation/test_product_packaging.py::DependencyPinContract`; PR #14 Foundation run [37940398359](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940398359); current PR #13 evidence [#13](https://github.com/Frotan2/TOFEL-House-ERP/pull/13) | **PASS** — static pin contracts and Product-image Compose/Node integrity checks. **FAIL** — PR #14 Foundation audit: 160 matches / 47 packages; 8 untriaged identifier matches / 7 unique advisories. PR #13 remains open at `b07a275`; its current Foundation run [37980004394](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37980004394) fails on the expanded installed-tree audit (235 matches / 69 packages, non-empty untriaged set). The offline three-lock replay separately has 77 untriaged of 168 advisory-version entries / 73 GHSAs; these counts have different scopes, and a 76-visible-pair vs 77-replay discrepancy remains unreconciled. PR #13 Product image and Owned checks pass; Native passed on preceding code head `d0d74f7`. No advisory is waived or closed by those passes. ECharts remains **BLOCKED** with a contradictory `fix_path`; HRMS ProseMirror remediation is unqualified; WeasyPrint dispositions remain pending. Public-edge exposure remains deferred, but production authorization is **REJECTED**. |
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

## Security evidence reconciliation (refreshed 2026-10-10)

- **160 vs 158 (PR #14):** Foundation CI on merged `13482fe` reported 160
  identifier-level matches in 47 package groups; the replay has 96 npm + 62
  PyPI records = 158. The two extra oauthlib identifiers are GHSA-hj66 and
  PYSEC-2026-4113. The PyPA YAML aliases both to CVE-2026-49264: two IDs, one
  underlying advisory. PR #14 still had 8 untriaged identifier matches
  representing 7 unique advisories; the Foundation gate failed.
- **Expanded nested-tree counts (open PR #13):** its offline union of the HRMS
  frontend, HRMS roster and ERPNext banking lockfiles reports 168
  advisory-version entries: 91 matched existing dispositions (not independently
  revalidated for these newly scanned trees) and 77 untriaged, representing 73
  distinct GHSAs (3 critical, 29 high, 35 moderate, 10 low). This is not the
  installed-tree CI result. The current installed-tree audit reports 235
  advisory matches across 69 packages and fails with a non-empty untriaged set.
  PR #13's remediation note says 76 npm package/ID pairs are visible across the
  capped failure annotations; `follow-redirects` / ID 1116560 appears in the
  77-entry offline replay but not in those visible annotations. The difference
  is unreconciled: do not force the counts together or treat 77 as the installed
  audit's exact untriaged count.
- **ECharts:** the pinned `frappe`, Education, and HRMS frontend/roster
  lockfiles inspected in PR #13 contain no `echarts` or
  `frappe-ui@0.1.278`; the delta disposition is **BLOCKED**, not
  `NOT_REACHABLE`. Its JSON `fix_path` still says the component is not bundled
  and unreachable, contradicting that disposition. This remains an unresolved
  evidence defect; absence from those pinned lockfiles is not proof of general
  unreachability.
- **ProseMirror:** Education resolves `frappe-ui@0.1.31` and
  `prosemirror-view@1.33.1`; the inspected Education SPA does not construct an
  editor. The product HRMS frontend resolves `frappe-ui@0.1.105` and
  `prosemirror-view@1.31.3` (roster `1.33.6`), builds/serves the SPA, and mounts
  `TextEditor` for user-editable Text Editor fields. PR #13 still marks the
  HRMS paste-XSS path as an open product blocker. Its new install-time patch
  replaces every discovered HRMS frontend/roster copy with publisher tarballs
  for `prosemirror-view@1.42.3` and `prosemirror-model@1.25.8`, verifies tarball
  SHA-512 and installed file-tree hashes, and runs before asset build; the
  bootstrap checks the installed code before serving. Product-image run
  `37980004330` and Native run `37979725053` pass on the patched code path (the
  Native run is on prior head `d0d74f7`). However, there is no built HRMS editor
  interaction/paste-XSS regression, and Foundation still fails on the expanded
  advisory set. The lockfiles remain at the old upstream versions; this is an
  installed-code override, not a lockfile upgrade or closure of the blocker.
- **WeasyPrint aliases and paths:** `GHSA-jf6q-chmf-3h3v` (SSRF) aliases
  `PYSEC-2026-3940`; `GHSA-jhhc-3hcp-qhm5` (CSS injection) aliases
  `PYSEC-2026-3412`. The latter is **not** the SSRF alias. The base register
  still labels both findings **MITIGATED**, but that status is not established.
  Pinned Frappe directly enters vendor code from
  `frappe/printing/doctype/print_format/print_format.py`,
  `frappe/utils/print_utils.py`, and `frappe/www/printview.py`. PR #13 now
  supplies a hash-bound patch to the pinned `PrintFormatGenerator` constructor;
  its original SHA-256 matches the inspected Frappe source, and every inspected
  direct/helper route constructs that generator. The owned wrappers now match
  the vendor positional signature and enforce target print permission, a
  matching DocType, and a beta Print Format. Native and Product-image builds
  pass the patched code, but neither is a functional PDF/preview security
  regression; the new remediation note explicitly leaves this qualification
  pending, and the Foundation audit fails. The source patch gates rendering; it
  does not itself demonstrate that attacker-controlled resource fetches are
  impossible. Inspected Frappe `render()` calls omit `presentational_hints`, so
  CSS-injection reachability remains unresolved, not confirmed. The separate
  Ghostscript guard concerns `GHSA-r543` RCE and does not mitigate SSRF. Also,
  `product/app.Dockerfile` still has a top-level statement that upstream code
  is never patched, despite now patching installed Frappe during image build;
  this documentation contradiction should be corrected. Keep both WeasyPrint
  findings open for re-triage—neither is confirmed exploitable nor proven
  mitigated by this evidence.
- **Office 365 follow-up:** PR #13's new callback verifies the Microsoft ID
  token signature, audience, timestamps, tenant and issuer using a fixed JWKS
  URL. However, its subsequent `email_verified` gate is ineffective when
  `oauth.get_email(info)` returns `email`, `upn`, or `unique_name`: any such
  claim satisfies the `or` even when `email_verified` is absent or false. The
  callback test itself accepts an `email`-only fixture. Do not claim that email
  verification is enforced until this is corrected and tested.
- **Dangling references:** the base register names
  `tests/foundation/test_sec_deps_triage.py`, which is absent. PR #13 adds an
  erratum and `tests/security/test_security_remediation_2026_10_09.py`; these
  exercise a pinned-source fixture, wrapper signatures, and patch functions,
  but do not prove the complete live Frappe call graph, PDF/preview behavior, or
  built HRMS editor behavior. The erratum and remediation note do not change the
  base register's `MITIGATED` labels or close the gate.
- **PR #13 status (latest refresh):** open head
  `b07a275e7f302cdb4dc391479c971be3f11b722a`. Product image
  [37980004330](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37980004330)
  passed both Windows stale-worktree/EOL and Linux product-image jobs. The
  Linux job passed first boot/backup-restore, browser login, tailnet contract,
  upgrade/rollback, and performance checks; its failure-only log step was
  skipped as expected. Owned suites
  [37980004489](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37980004489)
  and [37980011858](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37980011858)
  **PASS** on that head. Foundation runtime
  [37980004394](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37980004394)
  **FAIL** on that head at the full-stack dependency audit (235 matches / 69
  packages; non-empty untriaged set). Native lifecycle
  [37979725053](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37979725053)
  **PASS** on preceding code head `d0d74f7`; no Native check is attached to
  `b07a275` (its changes are the remediation record and a Dockerfile comment).
  The earlier Native run [37977729383](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37977729383)
  failed the old “no tracked source changes” assertion after the intentional
  renderer patch; `d0d74f7` narrowly allows only the SHA-verified renderer file,
  and the rerun passed. PR #13 remains open and is not release approval.
  The earlier review comment
  [6086576384](https://github.com/Frotan2/TOFEL-House-ERP/pull/13#issuecomment-6086576384)
  has no direct response; later code addresses some path gaps but leaves the
  advisory, product, and email-verification findings above unresolved.

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
- **Dependency advisories:** Foundation runtime
  [37940398359](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940398359)
  on merged PR #14 commit `13482fe` failed: 160 identifier matches / 47
  packages, with 8 untriaged identifiers / 7 unique advisories. The replay's
  96 npm + 62 PyPI = 158 omits two oauthlib identifiers; `GHSA-hj66-6f7g-4r5v`
  and `PYSEC-2026-4113` alias CVE-2026-49264, so those are two IDs for one
  underlying advisory. Open PR #13 remains unmerged and not accepted as release
  evidence. Its latest expanded Foundation run
  [37980004394](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37980004394)
  failed with 235 matches / 69 packages and a non-empty untriaged set; its
  separate offline lock replay has 77 untriaged of 168 advisory-version entries
  / 73 GHSAs, with a 76-visible-pair versus 77-replay discrepancy still open.
  ECharts is **BLOCKED** but its `fix_path` still asserts no bundled/reachable
  component. HRMS ProseMirror has a new integrity-checked installed-code patch
  to fixed package versions, but its shipped editor path remains an open
  blocker pending a built-editor regression and clean audit. WeasyPrint's new
  constructor guard and corrected wrapper signatures address the earlier
  direct-path/signature gaps, but do not yet prove SSRF mitigation or CSS
  injection reachability; the base `MITIGATED` statuses remain unverified.
  The alias mapping is `GHSA-jf6q` / `PYSEC-2026-3940` for SSRF and `GHSA-jhhc`
  / `PYSEC-2026-3412` for CSS injection. Ghostscript absence remains a separate
  RCE mitigation. Do not waive or close findings on the basis of green Product
  image, Native, or Owned checks. SEC-DEPS-01 remains relevant to public-edge
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

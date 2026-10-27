# Windows delivery audit — installation, updater, repair, backup/restore (Agent 4)

Date: 2026-10-26. Author: Agent 4 (Windows Product Packaging, Installation &
Recovery Lead). Release decision: **NO-GO — this audit authorizes nothing for
production, real student data, or real money.**

Branch note: the mission asked for work on
`agents/windows-delivery-finalization`, but this Arena session is bound to its
assigned branch and must not create, switch to, or push any other branch. All
Agent 4 work below is on the session branch, limited to the Windows-delivery
scope, developed in a Linux sandbox. **The live preserved Windows acceptance
installation was not used, reset, reinstalled, or altered in any way.**

## Documents read

- PR #87 (`fix: financial reconciliation and Windows acceptance blockers`,
  base `main`, head `fix/updater-live-host-observation-20261025`) including its
  full body, evidence, and outstanding-gates section.
- `docs/engineering/WINDOWS-RESUME-2026-10-26.md` (QA-007…QA-010).
- `docs/engineering/WINDOWS-UAT-FINDINGS-2026-10-26.md` (QA-001…QA-006).
- `docs/engineering/SAFE-UPDATES.md`, `docs/CUSTOMER-UPDATES.md`,
  `docs/CUSTOMER-DELIVERY.md`.
- `product/windows/VALIDATION.md`, `OWNER HANDBOOK.txt`,
  `OWNER ACCEPTANCE GUIDE.txt`, `DAILY USE GUIDE.txt`.
- All customer lifecycle scripts: `TOEFL House ERP.ps1`,
  `Run TOEFL House ERP.ps1`, `Check This PC.ps1`,
  `Verify Package Image.ps1`, `Prepare Customer Package.ps1`,
  `Test Fresh Installation.ps1`, `Test Existing Installation.ps1`,
  `Update TOEFL House ERP.ps1`, `updater-strings.json`,
  `Install/Start/Stop/Repair TOEFL House ERP.cmd`,
  `Backup TOEFL House ERP.ps1` (developer-repo guarded script),
  `product/docker-compose.yml`, `product/updates/channel.json`.
- `tools/release/create_customer_package.py` (approved publication path) and
  `.github/workflows/windows-customer-package.yml`.

## Scope boundaries honored

- No accounting or academic business logic changed.
- No change to the release image manifest schema, release-signing
  configuration, trust store, or update-engine trust decisions.
- No merge into `main`, no published package, no production-ready claim, no
  safety gate removed. The `TEST PACKAGE - NO REAL DATA` / `REJECT` gate in
  `Verify Package Image.ps1` is pinned by a new test so it cannot be dropped
  silently.
- Local-drive backup remains the supported Owner preference; backup stays Off
  by default (D18) and the preservation/restore HOLD is restated, not lifted.

## Historical Windows defects — delivery relevance

| ID | Defect | Delivery status |
| --- | --- | --- |
| QA-001 | Fresh storage falsely reported as indeterminate | Fixed before this audit (`Check This PC.ps1` uses a successful name inventory; verified-absence vs API-failure distinguished). Re-verified by new contract `test_unknown_storage_is_never_classified_as_disposable`. |
| QA-002 | Process-wide roster accessor replacement | Academic permission internals; outside Agent 4 change scope. No delivery action. |
| QA-003 | CMD readiness never completes with real LF-only Docker output | Fixed before this audit (structured PowerShell probe: 7 running, 5 healthy, HTTP 200; Windows CI emits LF-only mocks). Re-verified via existing `test_windows_service_readiness.ps1` in CI. |
| QA-004 | Native setup first-user roles prevent login | Owned `setup_wizard_success` hook narrows the initial account; no guard bypass. Agent 4 makes no setup-logic change (business-logic boundary); first-run operator path (credentials file → private viewer → password change → separate Course Owner account) is documented and unchanged. |
| QA-005 | Same-origin realtime ingress / internal auth callback | Product ingress wiring; outside Agent 4 change scope. No delivery action. |
| QA-006 | Owner fee creation in native dependent Item writes | Business-logic boundary; no delivery action. First-plan UX gap noted for onboarding docs; no doc change needed (handbook already routes all policy through in-app pages). |
| QA-007 | Education fee root cannot save accounting defaults | Setup repair; outside Agent 4 change scope. No delivery action. |
| QA-008 | Guarded writes bypass native Branch User Permission | Security boundary; outside Agent 4 change scope. Noted: the Windows verifier-harness PowerShell module-path repair is test-process only; no package integrity check was weakened. |
| QA-009 | Saved cash-close receipt bypasses changed Company scope | Security boundary; outside Agent 4 change scope. No delivery action. |
| QA-010 | Real Android login lands in generic ERP navigation | Login/home routing; outside Agent 4 change scope. Noted for onboarding: staff-device private access remains an open gate (see dependencies). |

## Findings and corrections in this change

| ID | Finding | Severity | Action |
| --- | --- | --- | --- |
| F-01 | The GUI had no **Owner Handbook** button, although `CUSTOMER-DELIVERY.md` promises one and the approved Python packager ships `OWNER HANDBOOK.txt`. Nontechnical onboarding gap. | Medium | Added a read-only `Owner Handbook` button (same row as `Copy Safe Support Status`; opens the handbook in Notepad; disabled while busy or when the file is missing) and extended the GUI `-SmokeTest` to require the button and the file. |
| F-02 | `Prepare Customer Package.ps1` allowlist omitted `OWNER HANDBOOK.txt`, diverging from `tools/release/create_customer_package.py`. | Medium | Added the handbook to the PS1 allowlist. Both packagers still exclude Backup/Restore/Activate/Deactivate controls, secrets, site files, and backups; pinned by test. |
| F-03 | `Repair` verified the archive, then checked only bare tag existence (`docker image inspect … >nul`) after `docker load`, while `Install` binds the loaded image to the manifest labels. Exact-version compatibility gap. | Medium | `Repair` now runs `Verify Package Image.ps1 -VerifyLoadedImage` after load and refuses on mismatch, before any Compose restart. |
| F-04 | `Install`'s second (post-credential) archive verification fell through to the generic `:failed` path, which reports service state and logs for what is actually a package-integrity failure after local setup started. | Low | New dedicated `:packagechanged` label: explains the package changed or became unreadable mid-install, states the partial install was preserved, forbids re-running Install or regenerating credentials, and points to `Check This PC` + `Copy Safe Support Status`. First-verify-before-credentials ordering is unchanged and still pinned. |
| F-05 | `SAFE-UPDATES.md` failure table said `safe-abort` means “retag the previous image, start the previous version, journal `rolled-back`”, but the shipped updater never restarts automatically (even pre-migration, storage may have vanished) and always journals `recovery-required`. Doc/code mismatch. | Medium | Corrected the table and the surrounding section to the fail-closed behavior; documented the `rolled-back` journal phase and `updater.rollback_done` / `updater.rollback_blocked` catalogue entries as reserved for a future support-directed step. No behavior change; catalogue keys retained (pinned by existing tests). |
| F-06 | `OWNER HANDBOOK.txt` §10 still said “no approved automatic update path … PR #46 remains on hold. Do not install an updater”, contradicting the shipped safety-gated Check/Install Update buttons. | Medium | Rewrote §10 (English) plus the Dari summary §8 to describe the gated updater: separate buttons, signed release + verified backup + Owner recovery authorization, disabled channel behavior, bilingual messages, no automatic restart on failure, and support-directed recovery. NO-GO retained. |
| F-07 | `product/windows/VALIDATION.md` still described Install as “builds for 20–60 minutes” and a `Normalize Product Sources.ps1` build step, although the customer kit is prebuilt-only and refuses when the archive is missing. | Medium | Corrected Step 1, Step 8, and the line-endings section to the verify-then-import flow with exact-identity checks and safe-refusal wording. Holds retained. |

## Verified-correct behaviors (audited, no change needed)

- **V-01 — Unknown storage is never disposable.** `Test Fresh Installation.ps1`
  throws (no password generated) when site files exist, the named volume
  exists, or Docker storage cannot be inventoried. `Check This PC.ps1`
  reports “could not be ruled out / do NOT assume a fresh installation” when
  either inventory is unverified. Start/Repair `:nosecret` paths defer to the
  same preflight and warn the result is “NOT proof that old data cannot exist
  elsewhere”.
- **V-02 — Existing installations are preserved.** Install refuses when
  `db.env` or `site_config.json` exists (`:alreadyinstalled`, before any
  Docker/storage write). Start/Repair require `db.env` + `site_config.json` +
  exact named volume `toefl-house-erp_db-data` (presence **and** inspect
  accessibility) before Compose, so `compose up` can never silently create an
  empty replacement volume. Repair confirmation defaults to No in the GUI.
- **V-03 — No destructive commands.** No `compose down -v`, `volume rm`,
  `system prune`, `git reset --hard`, or restore-over-live path exists in any
  customer CMD/PS1, the updater, or the packagers. Repair uses `compose down`
  (containers only; named volumes preserved) followed by verified-image load.
  Pinned by new tests across all customer scripts.
- **V-04 — No source build on the customer PC.** Install/Repair refuse with a
  bilingual `:packagemissing` message when the prebuilt archive is absent;
  no `docker build` / `--build` / normalize step remains. Pinned by tests.
- **V-05 — Package integrity and exact-version binding.** SHA-256 sidecars for
  archive and manifest; manifest binds source revision, version, archive hash
  + size, config digest, and labels (`source-eol=lf-v1`, source revision,
  release version) on both the archive config bytes and the loaded image.
  Tamper and missing-sidecar cases are exercised in Windows CI.
- **V-06 — Updater failure semantics.** Documented exit codes 0/3/4/5/6;
  download-after-allow ordering; 30-minute one-use durable authorization;
  journal blocks a second update after `prepared`/`applying`; every failure
  path journals `recovery-required`, writes a safe `last-result.json` (size-
  capped, catalogue-keyed, no secrets/paths), and shows bilingual recovery
  steps. Disabled channel refuses with exit 3 in English and Dari and
  downloads nothing (proven in Windows CI).
- **V-07 — Rollback posture.** A failed update is recoverable, not automatic:
  the previous image ID is retained and best-effort retagged on `safe-abort`;
  services are never restarted automatically; the verified separate-drive
  backup plus signed Owner recovery authorization remain the recovery basis;
  support directs the recovery decision. This is now stated identically in
  code comments, `SAFE-UPDATES.md`, `CUSTOMER-UPDATES.md`, and the handbook.
- **V-08 — Read-only diagnostics.** `Check This PC.ps1` creates/changes
  nothing (no `New-Item`/`Set-Content`/`Copy-Item`/`Remove-Item`, no Compose
  or load commands); `Copy Safe Support Status` copies only allowlisted
  category/value pairs from a complete report and is invalidated by any other
  lifecycle action.
- **V-09 — Docker Desktop prerequisite handling.** Missing Docker opens the
  official download page with WSL 2 / reboot guidance; a non-running engine is
  started and awaited up to 5 minutes; no unattended single-click claim is
  made; commercial-license confirmation stays a provider duty per
  `CUSTOMER-DELIVERY.md`.
- **V-10 — Bilingual catalogue.** Every `messages`/`launcher`/`ui` entry has
  non-empty `en` + `fa` with Dari script; the GUI renders catalogue text only,
  never free text from logs or result files.
- **V-11 — Backup preference and holds.** Local fixed-drive backup remains the
  supported Owner preference; Backup defaults Off (D18) with existing files
  preserved; the customer kit intentionally exposes no Backup/Restore/
  Activate/Deactivate controls while the preservation/restore HOLD applies.

## Verification performed

Isolated Linux sandbox (no access to any Windows Owner PC; nothing outside
disposable directories and this branch was touched):

- New contracts: `python3 -m unittest
  tests.foundation.test_windows_delivery_finalization` — 14 tests pass.
- Regression neighbors: `test_customer_install_package`,
  `test_windows_update_path`, `test_customer_package_manifest`,
  `test_product_packaging`, `test_update_engine`, `test_update_bundle`,
  `test_product_backup`, `test_product_restore` — all pass (see PR checks).
- `ruff check` (0.16.8, pinned) passes on the new test file.
- CMD edits preserved CRLF line endings (verified byte-level); the linear
  single-line `IF ... GOTO` style rule is now pinned by test.
- PowerShell syntax of edited scripts cannot be parsed on this Linux host (no
  PowerShell runtime); parsing is covered by the Windows CI job below, which
  uses the real PowerShell parser on every customer script.

Windows evidence (exact, from CI on this change, PR #93):

- `Windows customer package smoke` run **40423943933** — **PASS** (all 8
  steps success, `windows-2022`): real PowerShell parse of all customer
  scripts; updater `-SmokeTest`; updater failure/recovery probe; GUI
  `-SmokeTest` (now including the Owner Handbook wiring); storage-inventory
  regressions; the new `Verify Windows delivery finalization contracts`
  step; service-readiness regressions; and the headless Install/Start/Stop/
  Repair lifecycle with fake Docker (Repair now exercises
  `-VerifyLoadedImage`), damaged-kit refusal, disabled-channel refusal
  (exit 3, bilingual, no download, safe result file), repeated/partial-
  install and missing-volume preservation blocks, tamper rejection, and the
  new handbook kit-content check.
  https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40423943933
- `Owned suite` run **40423963531** — **PASS** (all steps success,
  `ubuntu-24.04`): pinned-ruff static analysis, full Python test tree
  (including the 14 new delivery contracts), Node suites, and the update
  observer privilege probe.
  https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40423963531

## Customer instructions corrected

- `OWNER HANDBOOK.txt` §10 + Dari §8: gated updater description (above).
- `product/windows/VALIDATION.md`: prebuilt verify-then-import flow (above).
- Unchanged and still accurate: `OWNER ACCEPTANCE GUIDE.txt` (safe first
  check + disposable-PC steps), `DAILY USE GUIDE.txt` (role routines +
  NO-GO), `CUSTOMER-DELIVERY.md` (now matches the GUI after F-01),
  `CUSTOMER-UPDATES.md` (checklist + recovery steps match the shipped
  updater).

## Dependencies on the final integrated release

1. PR #87 integration: this change is based on the PR #87 head branch and is
   offered against it; it must not be merged to `main` separately and must
   not bypass the PR #87 gates (current-source CI, rebuilt customer package,
   supported in-place update/repair qualification).
2. Official rebuilt customer package: all evidence here is source/contract
   plus synthetic-Windows-CI evidence, not rebuilt-kit qualification. The
   handbook/repair/installer wording changes must be re-verified inside the
   official rebuilt kit.
3. Real-hardware gates still open (unchanged): clean Windows + Docker
   Desktop/WSL 2 install, multi-GB image import timing, graphical lifecycle,
   staff transactions, female-counter collection/handover, staff-device
   private access, separate-drive verified backup + Owner key custody +
   rehearsal restore, in-place update/repair on a real machine, Tailscale
   exposure check, and independent business/security acceptance.
4. Backup/restore: hosted isolated synthetic restore qualification
   (native-lifecycle run 39836321651) is cited, not repeated, by this audit;
   Owner-machine backup/restore remains HOLD and no Owner restore command is
   added to the customer kit.

## Remaining gates (explicitly not closed)

Final-revision CI, official rebuilt package qualification, graphical staff
transaction acceptance, Company/Branch negative acceptance, reception
collection and Finance cash handover, actual staff-device private access,
independent business/security acceptance, and Owner written production
approval. **Production authorization remains REJECT / NO-GO.**

# Owner acceptance package

Status as of 2026-10-17: **NO-GO**.

- `main`: `7c847da` (PR #20 merged). Post-merge CI on `7c847da`: all four workflows SUCCESS.
- Session branch `arena/dff19152-tofel-house-erp`: code head `f59836b`; the latest commits are evidence and documentation only. Owned is green on the newest head `b59cc12` (push `39038508246`, PR `39038511637`), which adds the F7 synthetic tests. Foundation was red on each head it ran on, for the same step and cause: `8d38d96` (run `39035649766`) and `0388edc` (run `39035673148`). It did not run on `5b0f01d`, which is outside its path filter. Open as **PR #21**. Evidence commits follow it. The current head is the PR's head: `gh pr view 21`. It is not merged, so it is not release-ready. PR #21 must not be merged while Foundation is red.
- Foundation on the session branch is **red by design** at `f59836b` (run `39034054581`), and again at `8d38d96` (run `39035649766`), `0388edc` (run `39035673148`), `5bae70a` (run `39038444492`) and `80379a1` (run `39041484781`). All failed at `Install and validate the pinned foundation`. On `80379a1` the visible annotations (145 package-and-advisory pairs) are all closed with 0 untriaged. The failing hosted audits are attributed to GHSA-VHRC by the prior reproduction on the education lock; the logs are not downloadable here, so this attribution is not directly observed in the run log. Cause reproduced 2026-10-17 (`sec-deps-01/foundation-replay-f59836b-2026-10-17/`): the frontend audit's only open entry is GHSA-VHRC-HGRQ-X75R (BLOCKED), and no untriaged finding appears in the reproduction or the visible annotations. The full artifact cannot be downloaded from the sandbox, so the full-stack audit is confirmed only for the visible annotation IDs. Earlier history: Foundation was red at `07117ea4` for the same reason (run `38904598642`).
- Final release SHA: to be recorded after PR #21 merges and the required checks pass on that exact `main` SHA.

Every item below is an owner-run or owner-decision step. Engineering has not executed any of them. No secret, token, key, password, tenant GUID, or real site data belongs in this document, in an issue, a commit, or a log. Return only the evidence listed in each row.

Reference decisions: `docs/owner-decisions.json` (D12 to D17 recorded; D14 off-site backup is DEFERRED / FUTURE; business-policy values unresolved).

## A. Owner actions

| # | Item | Owner action | Evidence to return (no secrets) | Blocks |
|---|---|---|---|---|
| A1 | Windows and Docker validation | Run `product/windows/VALIDATION.md` (steps 1 to 10) on the owner's PC, as its hold permits. Run the isolated procedure in `docs/engineering/evidence/windows-backup-readiness-2026-10-16/PROCEDURE.md` on a separate test machine with synthetic data. | Pass/fail per step (T1 to T10 and checklist steps), Windows and Docker versions, log excerpts with secrets redacted | Issue #12; NO-GO |
| A2 | Separate backup drive (same PC) | Connect a dedicated drive. Confirm the ERP validates it as a fixed secondary drive and refuses the system drive and removable media. Accept the same-PC risk (README F4). | Validation result, drive type and letter (not serials) | NO-GO |
| A3 | Keep count and nightly schedule | Set the keep count and nightly time in ERP Configuration (Backup and Recovery). D17 allows deletion of valid older sets beyond the keep count only. **Decide A9 first**, because the native staging folder is not rotated. | Configured keep count and time, one manual backup, the resulting set list | NO-GO |
| A4 | Recovery key and custody | Generate the OpenPGP recovery keypair on the owner machine. Publish only the public key. Store the private key offline with named custodians. **Name the custodian count and quorum** (README F3). Test one restore into a disposable folder. | Public-key fingerprint, custodian count and quorum policy, restore-rehearsal result (no private key material) | NO-GO |
| A5 | Tailscale multi-user acceptance | Add two synthetic test accounts on the tailnet. Verify each reaches only its permitted pages and no public exposure exists. | Account roles tested, reachability results per account | NO-GO |
| A6 | Office 365 tenant pin and live sign-in | Set `office_365_tenant_id` in site configuration to the Entra tenant GUID (non-secret). Then run `docs/engineering/evidence/microsoft-auth-review-2026-10-15/LIVE-TENANT-PROCEDURE.md` (negative cases N1 to N6, disabled-user revocation D1 to D5). Engineering has not run this. | Outcome table only (step, HTTP status, pass/fail, log-line counts) | NO-GO if Office 365 login is offered |
| A7 | Business-policy values | Record a written decision per item in `docs/engineering/evidence/business-rules-review-2026-10-16/README.md` (the nine owner decisions). Confirm which stay unconfigured and fail closed. Tax, calendar, and transfer fields are **carriers only** and are not enforced (gap G1). | Written decision per item (a decision record, not inferred) | NO-GO for affected features |
| A8 | Issue #12 closure | After A1 to A5 evidence exists, comment on #12 with the evidence list and close it. Engineering cannot comment on or close #12 (HTTP 403). | Link to this package and the evidence | Closure |
| A9 | **Native staging folder rotation (new)** | The Windows backup writes a full encrypted native set to `product\data\sites\<site>\private\backups` on every run and never rotates it (README F1). The same folder keeps partial sets left by a failed publish, with no sidecar (README F7); decide how those are handled. Decide: keep, rotate beyond the keep count (D17), or move native output off the product data volume. | Decision record | **NO-GO for backup retention** |
| A10 | Same-PC backup acceptance (new) | Acknowledge that the backup drive is on the same PC and that a PC-level loss takes the live site and backups together. Off-site backup is deferred (D14). | Written acknowledgement | NO-GO for backup |
| A11 | Microsoft authorization code in logs (new) | Decide whether the reverse proxy redacts the `code` query parameter from access logs, or accept the risk (`microsoft-auth-review-2026-10-15/README.md`, residual risk 2). | Decision record; proxy redaction evidence if chosen | Microsoft login |

## B. Repository branch decisions for the owner

Verified 2026-10-16 after `git fetch --unshallow` (ancestry checks are invalid on a shallow clone).

| # | Branch | Verified state | Recommendation |
|---|---|---|---|
| B1 | `arena/68836d1b-tofel-house-erp` (`63862fa`) | Ancestor of `main`. Zero commits not on `main`. Former PR #18 head. | Deletion is **not** in the owner's six-branch authorization. Keep unless the owner authorizes it. |
| B2 | `arena/abdece6c-tofel-house-erp` (`097193d`) | Not an ancestor of `main`. **Nine** commits not on `main` (PR #13 security evidence and hold docs and tests). | Keep unless the owner confirms each commit is superseded. Do not delete without that confirmation. |
| B3 | `arena/f99831e4-tofel-house-erp` (`4697e7d`) | Not an ancestor, but `git cherry` shows its one commit's patch is already on `main` (equivalent to PR #19). | Content is on `main`. Deletion needs owner authorization. |
| B4 | `arena/c9b97074-tofel-house-erp` (`e9b6a6c`) | Ancestor of `main`. Merged via PR #20. | Deletion needs owner authorization. |
| B5 | `arena/dff19152-tofel-house-erp` (`f6b3b46`) | Session branch, PR #21 open. | Keep until PR #21 merges. |

No branch was deleted in this round. The six earlier deletions are the only authorized ones.

## C. Release gates and evidence (as of `f6b3b46`)

| Gate | Status | Evidence |
|---|---|---|
| Local tests | PASS at `f59836b`: 1360 OK, 0 skipped; `ruff check .` clean. Earlier: 1344 OK at `f6b3b46`. | `python3 -m unittest discover -s tests -t .`; `ruff check .` |
| Owned suite (CI) | PASS at `f59836b` (`39034054544` push, `39034057519` pull_request; every step including `Install hash-pinned crypto test dependencies` and `Python test tree`). PASS at `f6b3b46`
| Foundation (CI) | **Red by design** at `f59836b` (run `39034054581`), the same cause as `07117ea4` (run `38904598642`). The only open record is GHSA-VHRC-HGRQ-X75R (BLOCKED). | `sec-deps-01/foundation-replay-f59836b-2026-10-17/`. Earlier: `sec-deps-01/gate-replay-2026-10-16/` (run history table) |
| Advisory coverage | 153 identifiers in the CI-style snapshot resolve to 144 register records; 0 untriaged. Record dispositions: NOT_REACHABLE 53, BUILD_ONLY 47, MITIGATED 18, DEV_ONLY 18, BLOCKED 1, BROWSER_SELF_DENIAL 5, INSTALL_ONLY 2 | `advisory-delta-2026-10-09/replay-snapshot.json`; `sec-deps-01/*/delta-dispositions.json` |
| Product image, Native | Passed at `61c4c42` (`38899033331`, `38899033418`). Re-run at `f6b3b46`. | Actions |

### G1. Advisories (distinct, with disposition)

- **GHSA-fgmj-fm8m-jvvx / CVE-2026-45249 (ECharts `<6.1.0`, medium):** NOT_REACHABLE. No ECharts in any pinned tree (`sec-deps-01/echarts-presence-2026-10-15/`).
- **Three-package annotation gap** (`@tiptap/extension-link`, `cookie`, `yaml`): covered by the register. The earlier "hidden" rows were writer truncation, not coverage loss (`annotation-gap-2026-10-15/`). The step-summary display on a CI run is still unconfirmed.
- **PYSEC-2026-4311 (weasyprint 68.0; alias of GHSA-r543-q48m-4c9j):** MITIGATED. The Ghostscript build guard in `product/app.Dockerfile` fails the image if `gs` is on PATH. Fix path: WeasyPrint 70.0, blocked upstream by the Frappe pin (68.0).
- **PYSEC-2026-4312 (werkzeug 3.1.6; alias of GHSA-g6x2-hccm-hh4m):** NOT_REACHABLE. The Windows NTFS precondition does not hold in Linux containers. Fix path: Werkzeug 3.1.9, blocked upstream by the Frappe pin (3.1.6).
- **GHSA-gv7w-rqvm-qjhr (esbuild, withdrawn 2026-06-17) and GHSA-8p5q-j9m2-g8wr (lodash, withdrawn 2021-10-01):** BUILD_ONLY.
- **GHSA-c8x8-7fp4-3x9w (prosemirror-view, high):** MITIGATED_CI_VERIFIED_PRE_MERGE. It must be re-verified on the release SHA.
- **GHSA-VHRC-HGRQ-X75R (`@tiptap/extension-link` `javascript:` href, XSS):** **BLOCKED**. The earlier self-denial premise was wrong: Frappe's `sanitize_html` JSON short-circuit returns stored values unchanged, so the exposure is cross-user. The Text Editor affected fields are hrms 20, education 5, erpnext 154. Containment is unit-verified only (`html_containment.py`, 11 tests). It stays BLOCKED until a live runtime containment check exists. Gate G2 below. **Owner decision (new, 2026-10-17):** the open entry is the Education frontend lock, where `@tiptap/extension-link` is `2.2.3`. The patched `2.10.4` needs `@tiptap/core` and `@tiptap/pm` at `^2.7.0`, so the fix is a coordinated TipTap upgrade with a build and editor regression pass, not a one-line overlay. Choose: (a) that upgrade, or (b) accept the server-side containment and its residuals. Details: `sec-deps-01/containment-real-sanitizer-2026-10-16/README.md`, section "Fix path for the education lock".
- **th_command_pages.js innerHTML sink:** escaped, no finding. Guarded by `tests/foundation/test_command_pages.cjs` (mutation-checked).

### G2. Other gates

| Gate | Status | Evidence |
|---|---|---|
| GHSA-VHRC runtime containment | **OPEN (blocks release)**. Unit check against the real pinned Frappe sanitizer now passes (16 tests, mutation-checked; not a hosted check). Save-path order verified in pinned Frappe: the `validate` hook runs before Frappe's own sanitizer. Two residuals are open: existing stored rows are not backfilled, and `db_set`/`set_value`/SQL bypass `validate` (`sec-deps-01/containment-real-sanitizer-2026-10-16/README.md`). Still needs a live bench check that stored `javascript:` hrefs are re-sanitized on save, reopen, import, and render. | `containment-real-sanitizer-2026-10-16/README.md`; `advisory-delta-2026-10-15/README.md` |
| HRMS editor (built component) | Lab PASS on the patched tree (Chromium 131 and 153); the controls fail on the security assertions. **Not cleared:** no logged-in full-form flow, and no server-side sanitization test for stored HTML. | `hrms-editor-2026-10-15/README.md` |
| Microsoft auth (automated) | PASS: tenant pin, linking, disabled-user refusal, per-request guard. The static wiring test pins the `auth_hooks` order. | `tests/security/test_security_remediation_2026_10_09.py` (`Office365Tests`), `test_disabled_user_paths_2026_10_15.py` |
| Microsoft auth (live tenant) | **UNVERIFIED.** Engineering has not signed in to any tenant. OAuth state lifecycle re-verified against the pinned Frappe source (2026-10-16); runtime replay is owner step N7/N8. | `LIVE-TENANT-PROCEDURE.md` (A6) |
| Business rules | Inventory complete. Enforced where tests exist. Tax, calendar, transfers, and capacity targets are not enforced (G1 in that review). Owner values are missing. | `business-rules-review-2026-10-16/README.md` (A7) |
| Backup and retention | **Blocked by F1** (native staging not rotated) and **F7** (partial native publish leaves orphans; owner decision on handling). Integrity is checked at write time only; no restore verification (F2). Key custody and quorum are owner decisions (F3). | `windows-backup-readiness-2026-10-16/README.md` (A3, A4, A9) |
| Windows lifecycle | **UNVERIFIED on a machine.** Source reviewed; tests need the owner's run. | `windows-backup-readiness-2026-10-16/PROCEDURE.md`; VALIDATION.md |
| Tailscale multi-user | UNVERIFIED (A5) | - |
| Issue #12 | OPEN, 0 comments (engineering cannot comment: HTTP 403). Item 1 (LF-only Windows checkout) has evidence on Linux: a fresh clone with `core.autocrlf=true` and `core.eol=crlf` has 0 CR files outside the required `.cmd` exception, and passes 1363 tests and `ruff`. The owner-run Windows install, Docker build, and runtime checks are still open. | `issue-12-lf-checkout-2026-10-17/README.md` |

## D. What "GO" needs

GO is allowed only when every mandatory gate above has passing evidence on the final `main` SHA, and the owner-machine checks (A1 to A5, A6, A9, A10) have passed or been decided. Until then the release stays **NO-GO**.

Mandatory engineering items still open: the GHSA-VHRC runtime containment check; the HRMS authenticated-flow and server-side sanitization tests; the state-replay test for the Microsoft callback; and the final-SHA CI on `main` after PR #21 merges.

# SEC-DEPS-01 advisory delta: 2026-10-09

Additive delta for the `STACK-ADVISORY-UNTRIAGED` gate failure. It dispositions the
eight matches the gate reported (seven unique advisories). It upgrades no dependency
and does not claim release readiness. Corrections to earlier evidence are in
`../ERRATUM-2026-10-09.md`.

Files:

| File | Purpose |
|---|---|
| `delta-dispositions.json` | Loader input: 7 advisories, dispositions, evidence with provenance, fix paths, the GHSA-c8x8 product-scope record, upgrade blockers |
| `replay-snapshot.json` | Offline replay of npm bulk and PyPI per-release data, 2026-10-09 (108 npm entries, 62 PyPI records) |
| `python-pins-replay.txt` | 153 Python pins resolved with uv 0.11.6 from the five pinned upstream manifests |

## 1. Verdict

* The gate's untriaged set is exactly 8 matches = **7 unique advisories**. PYSEC-2026-4183 mirrors GHSA-x33g-cr3x-6449. The npm numeric IDs are GHSA-g2v6, GHSA-rj75, GHSA-c8x8 and GHSA-68fv.
* Under the repository loader, the replay has **0 untriaged** npm entries (108/108 closed) and **0 untriaged** PyPI records (62/62 closed).
* The CI header's **160 matches** reconcile exactly: 96 npm + 62 PyPI + 2 oauthlib = 160 (section 3). They are identifier-level matches, not 160 vulnerabilities. The replay covers **123 unique advisories** across ecosystems.
* Dispositions: NOT_REACHABLE for GHSA-x33g, GHSA-g6x2 and GHSA-g2v6; MITIGATED for GHSA-r543 (build-time Ghostscript guard); BUILD_ONLY for GHSA-rj75 and GHSA-68fv; NOT_REACHABLE for GHSA-c8x8 **in the education tree only**.
* **Open release blocker, not closed by this PR: GHSA-c8x8 in the HRMS SPA.** `hrms/frontend` is built by `bench build` and served at `/hrms/` and `/hr/`. It mounts a Text Editor (prosemirror-view 1.31.3) for user-entered text fields, and the advisory is paste-triggered XSS. The CI gate does not scan `hrms/frontend`. The record is `product_scope` in the JSON, and section 7 lists the options. This blocks any release claim.
* Coverage gap: the CI audits do not scan `hrms/frontend`, `hrms/roster` or `erpnext/banking`. Their matches are not gated (section 7, item 2).
* The Ghostscript guard closes the GHSA-r543 precondition only where the Product image build step with the guard succeeds on the head. The guard is `product/app.Dockerfile` line 169.
* No dependency was upgraded. Every fixed version lies outside the pins that the pinned upstream stack enforces (section 4).

## 2. Advisory triage table

Reachability notes are summarized. Full evidence, line citations and provenance are in `delta-dispositions.json`.

| # | Advisory (aliases) | Package @ installed | Sev. / CVSS | Path | Fixed in | Upgrade blocked by | Disposition | Basis (short) |
|---|---|---|---|---|---|---|---|---|
| 1 | GHSA-x33g-cr3x-6449 (CVE-2026-102275, PYSEC-2026-4183) | pyjwt 2.13.0 | medium 6.5 | direct (frappe pin) | 2.15.0 | frappe `PyJWT~=2.13.0` | NOT_REACHABLE | Trigger is OKP private-JWK import through `OKPAlgorithm.from_jwk()`. Frappe's PyJWT call sites use HS256 with string secrets only: `frappe/oauth.py` 304, 307, 324, 441, 446-450, 467-471 and `frappe/utils/oauth.py` 179, 200 (verified at pin 988e54f3, 2026-10-09). |
| 2 | GHSA-r543-q48m-4c9j (CVE-2026-106443) | weasyprint 68.0 | high 8.8 | direct (frappe pin) | 70.0 | frappe `WeasyPrint==68.0` | MITIGATED | Needs a `gs` executable on PATH and attacker-influenced EPS input reaching WeasyPrint. The build guard (`product/app.Dockerfile` line 169) removes the `gs` precondition. The beta-only WeasyPrint branches are in section 7, item 3. |
| 3 | GHSA-g6x2-hccm-hh4m (CVE-2026-102598) | werkzeug 3.1.6 | medium | direct (frappe pin) | 3.1.9 | frappe `Werkzeug==3.1.6` | NOT_REACHABLE | Windows/NTFS device-name precondition. The served process is a Linux container: `product/wsgi.py:31` and `frappe/app.py:572` (verified 2026-10-09). Residual: Docker Desktop bind-mount semantics untested (availability only). |
| 4 | GHSA-g2v6-rqmx-r4w6 (1241259) | @vue/server-renderer 3.3.9 (frappe), 3.4.19 (education), 3.5.13 (HRMS, not gated) | high 7.2 | transitive via `vue` | 3.5.42 | frozen upstream lockfiles | NOT_REACHABLE | Trigger is SSR of attacker-controlled attribute names. The package is installed only as a `vue` dependency; no pinned source imports it. HRMS: lock and source evidence (2026-10-09); a built-bundle check is pending. |
| 5 | GHSA-rj75-hqrm-r3gf (CVE-2026-104844, 1241232) | postcss-selector-parser 6.0.10, 6.0.13, 6.0.15 | moderate 5.9 | transitive (tailwind, typography, component-compiler-utils) | 7.1.6 (major) | frozen lockfiles; 6.x to 7.x is a major bump | BUILD_ONLY | Trigger is synchronous parsing of attacker selectors in a request path. The consumers are build tools over repository-owned CSS. The HRMS trees are not gated (section 7, item 2). |
| 6 | GHSA-c8x8-7fp4-3x9w (CVE-2026-104847, 1241270) | prosemirror-view 1.33.1 (education), 1.31.3 (HRMS) | high | education: frappe-ui 0.1.31 → @tiptap/pm 2.2.3; HRMS: frappe-ui `TextEditor` | 1.42.3 | frozen lockfiles (education and HRMS) | NOT_REACHABLE (education tree) **and OPEN release blocker (HRMS)** | Education: no editor is constructed, so no paste sink. HRMS: `FormField.vue` mounts `TextEditor` for Text Editor fields (for example Expense Claim Detail `description`); the SPA is built and served. Paste-triggered XSS needs user interaction. Not gated. |
| 7 | GHSA-68fv-2mgg-jv7q (CVE-2026-93749, 1241209) | source-map-js 1.0.2 | high 7.5 | transitive: postcss 8.4.31 (frappe), 8.4.35 (education) | 1.2.2 | frozen lockfiles (postcss ranges resolve 1.0.2) | BUILD_ONLY | Trigger is parsing an attacker-supplied indexed source map in a process. postcss runs at build time over repository-owned sources. No runtime file imports source-map-js. |

Per-disposition upgrade detail is in `upgrade_blockers` inside the JSON.

## 3. Matches versus unique advisories (reconciled)

| Measure | Value | Source |
|---|---|---|
| Untriaged set reported by the gate (2026-10-09) | 8 matches = 7 unique advisories | run 37902411810, head a3b45abc9 |
| CI header, full set | `advisory matches=160 in 47 packages` | annotation of the Foundation runtime job, runs 37902411810 (a3b45abc9) and 37924260456 (ad7ef78) |
| npm, CI style (one GHSA per package) | 96 | `replay-snapshot.json` counts |
| PyPI per-release records, CI style (no PYSEC alias merge) | 62 | `replay-snapshot.json` counts |
| oauthlib 3.3.1, CI (OSV) only | 2: GHSA-hj66-6f7g-4r5v and PYSEC-2026-4113 | the PyPI per-release JSON omits both |
| **Reconciliation** | **96 + 62 + 2 = 160** | exact |
| Unique underlying advisories, all ecosystems | 91 npm + 32 Python = 123 | replay, alias-merged |
| Untriaged before this delta | 8 matches (= 7 unique) | replay and CI agree |
| Untriaged after this delta | 0 | replay under the current loader |

The two CI-only identifiers both belong to `py:oauthlib@3.3.1` and are NOT_REACHABLE in the loader: GHSA-hj66-6f7g-4r5v
in `advisory-delta-2026-09-29`, and PYSEC-2026-4113 in `advisory-delta-2026-10-02`,
which records it as the mirror of GHSA-hj66 with the same vulnerable range. The replay's
PyPI data for oauthlib 3.3.1 contains GHSA-xpv3-w29h-x7cv and PYSEC-2026-4114, and both
are already inside the 62.

The 160 figure counts identifier-level matches, not vulnerabilities. Most Python matches
list the same advisory under its GHSA and its PYSEC identifier, and one GHSA can match
several packages.

## 4. Upgrade and compatibility analysis

No safe, minimal, compatible upgrade exists for any untriaged item in the pinned stack.

Python (Frappe's exact or compatible-release pins are the binding constraint):

| Candidate | Frappe v16.33.1 pin (`988e54f3`) | Same pin in v16.35.0, v16.36.1, v16.49.0, v16.50.0, v16.51.0 | ERPNext / Education / HRMS / Payments | Verdict |
|---|---|---|---|---|
| PyJWT 2.13.0 → 2.15.0 | `PyJWT~=2.13.0` | yes, unchanged | none declared | Blocked: frappe pin |
| Werkzeug 3.1.6 → 3.1.9 | `Werkzeug==3.1.6` | yes, unchanged | none declared | Blocked: frappe pin |
| WeasyPrint 68.0 → 70.0 | `WeasyPrint==68.0` | yes, unchanged | none declared | Blocked: frappe pin |

These were checked against the upstream v16 tags listed above (session-1 check; the tags were
read from the remote, not from a local clone). A forced upgrade would violate a declared
requirement, which the uv resolver rejects by design.

npm: every fixed version requires moving a frozen upstream lockfile (vue, tailwind/typography,
frappe-ui, postcss, prosemirror). The repository does not patch upstream code or lockfiles, so
these are upstream refreshes, not owned changes.

The five pinned source trees match their commit pins in `docs/engineering/foundation-version-matrix.json`,
and every recorded `source_file_sha256` (pyproject, package.json, yarn.lock and frontend lockfiles)
matches. The Frappe pyproject hash is recorded in the JSON and enforced by a test.

## 5. Changes in this PR

1. `docs/engineering/evidence/sec-deps-01/advisory-delta-2026-10-09/` (new): delta, this README, the replay snapshot and the Python pins. The JSON evidence was corrected. GHSA-c8x8 gained a `product_scope` record. GHSA-x33g, GHSA-r543 and GHSA-g6x2 gained line citations. GHSA-g2v6 gained HRMS lock evidence. GHSA-rj75 gained a not-gated HRMS note. GHSA-68fv's path was corrected to `esbuild/esbuild.js`. Session-1 evidence is labelled as such.
2. `docs/engineering/evidence/sec-deps-01/ERRATUM-2026-10-09.md` (new): the dangling register references (E1), the withdrawn 2026-10-03 ECharts reasoning (E2), and corrections to this README (E3).
3. `docs/engineering/evidence/sec-deps-01/advisory-delta-2026-10-03/delta-dispositions.json`: GHSA-fgmj-fm8m-jvvx changed from NOT_REACHABLE to BLOCKED, with an erratum pointer.
4. `product/app.Dockerfile`: one final `RUN` guard at line 169. It fails the image build if a `gs` executable is on PATH. Pillow's EPS plugin runs the `gs` found on PATH (`PIL/EpsImagePlugin.py`), so the guard removes the precondition from the shipped image. The image is single-stage. The base image and the explicit apt set name no ghostscript package. Transitive absence could not be proven offline, so the guard enforces it at build time.
5. `.github/workflows/product-image.yml`: main's workflow (PR #14) plus one change to the restore rehearsal marker gate (section 8). The branch's earlier plain-restore diagnostic revision (`5bbf157`) is superseded by main's encrypted-restore path and is not carried forward.
6. `tests/foundation/test_restore_rehearsal_gate.py` (new, 12 tests): wiring checks, plus behaviour tests that execute both marker probe bodies against a stub `frappe` module.
7. `tests/security/test_advisory_delta_2026_10_09.py` (new): 16 original tests and 13 added in this revision (reconciliation, product scope, the withdrawn ECharts record, dangling references, the owned-fixture audit, and the single-stage guard).
8. Merge commit `b379c28` (main into this branch; no history rewrite, no force push).

No change to the immutable 2026-09-23 register, to other deltas (except the fgmj disposition above), to the version matrix, or to `tools/foundation/*`. `docs/engineering/ACCEPTANCE.md` is shared with the other branch and is not edited here (suggested row text in section 8).

## 6. Verification

### 6.1 Local checks on this tree

Sandbox after a reset: Python 3.11.2, Node v22.22.3 (CI pins Node 24.21.0). The commands are the owned-suite steps, run from the repository root.

| Check | Result |
|---|---|
| `ruff check .` (ruff 0.16.8, hash-pinned install as in `owned-suite.yml`) | `All checks passed!`, exit 0 |
| `python3 -m unittest discover -s tests -t . -v` | `Ran 1246 tests`, `OK`, exit 0 |
| of which `tests/security/test_advisory_delta_2026_10_09.py` | 29 of 29 pass |
| of which `tests/foundation/test_restore_rehearsal_gate.py` | 12 of 12 pass |
| Node: `test_realtime_guard.cjs`, `test_command_pages.cjs`, `test_design_system.cjs`, `test_role_desks.cjs` | all exit 0 |
| Loader after this delta | 7 advisories in `advisory-delta-2026-10-09`; GHSA-fgmj is BLOCKED and therefore not closed; GHSA-c8x8 stays NOT_REACHABLE for the education tree |
| Replay (npm 108 entries, PyPI 62 records) under the loader | 0 untriaged (session-1 replay; the snapshot is the recorded output, not re-run this session) |

### 6.2 Hosted GitHub Actions

Results are observed from the GitHub API at the time of writing. The head that will be
merged is recorded in the PR #13 body, which is updated per head.

| Head | Workflow | Run | Result |
|---|---|---|---|
| `13482fe` (main, PR #14 merge) | Product image (push) | 37940397957 | **success**: every step, including first-boot encrypted backup/restore, browser login, multi-user restart persistence, upgrade/rollback restore, performance |
| `13482fe` | Owned suite (push) | 37940397970 | success |
| `13482fe` | Native lifecycle integration (push) | 37940397967 | success |
| `13482fe` | Foundation runtime (push) | 37940398359 | **failure**: `STACK-ADVISORY-UNTRIAGED` for the same 8 matches this delta dispositions. This is the gate the delta closes on the PR branch |
| `5bbf157` (superseded) | Product image (push) | 37933917160 | failure at checkpoint "restore: pre-backup marker creation" (exit 1). The probe ran from the container WORKDIR. That is the most likely cause (section 8); the failing command's output was not captured, so this is inferred |
| `b379c28` (merge with main) | Owned suite (push / pull_request) | 37968077192 / 37968080351 | success / success |
| `b379c28` | Native lifecycle integration (push) | 37968077170 | success |
| `b379c28` | Product image (push) | 37968077218 | **success**: every step, including the build with the Ghostscript guard, the first-boot restore with the corrected marker probes, browser UI, multi-user, upgrade/rollback and performance |
| `b379c28` | Foundation runtime (push) | 37968077191 | see PR #13 body (in progress when this README was written) |

## 7. Remaining security risks and open items (not closed by this PR)

1. **GHSA-c8x8 in the HRMS SPA: open release blocker.** Owner options: (a) raise the HRMS frontend's prosemirror-view to 1.42.3 or later (blocked: the HRMS lockfile is upstream and frozen by policy); (b) unmount the Text Editor for HRMS fields (upstream code); (c) disable the `/hrms` and `/hr` website routes in the product (an application behaviour change); (d) record a risk acceptance with an expiry (needs an explicit loader rule and an owner decision). CI does not gate this tree.
2. **Coverage gap.** The CI audits do not scan `hrms/frontend`, `hrms/roster` or `erpnext/banking`. Replay matches in those trees: hrms-frontend 149 (124 unique), hrms-roster 65 (61 unique), erpnext-banking 26 (26 unique). Adding them to the gate would fail it until each is triaged. That is a follow-up decision and is not done here.
3. **WeasyPrint call paths.** The RCE precondition is removed by the build guard. The residual is authorization, not RCE: `frappe/www/printview.py` (75-76) and `frappe/utils/print_utils.py` `attach_print` (146-173) reach WeasyPrint for beta formats without the owned wrapper's gate. The owned wrapper (`toefl_house/printing.py`) also cannot succeed: it forwards `format=`, `doc=` and `no_letterhead=`, which the pinned vendor signatures at `frappe/utils/weasyprint.py` lines 11 and 22 do not accept, so every call that passes its gate raises `TypeError` (fail-closed; a static reading). Owner decision: disable beta WeasyPrint rendering, or extend the gate to the vendor paths and correct the wrapper signature.
4. **Register dangling references (2026-09-23).** Corrected by `ERRATUM-2026-10-09.md` (E1). The replacement tests exist and are checked by the test module. The register itself is immutable and still contains the dangling text.
5. **Unverified provenance from session 1.** Some checks depended on local clones and an education build that did not survive a sandbox reset: the repository-wide JWK/OKP grep, the education built-bundle markers for GHSA-g2v6, the source-map consumer grep, and the rj75 full-tree grep. The JSON labels these. They must be re-run by a job or a local clone before they are cited as fresh evidence.
6. **Social-login ID-token claims are read without signature verification** (`frappe/utils/oauth.py:200`, pinned frappe). This is not one of the seven advisories. It is recorded for owner review.
7. **2026-10-03 ECharts disposition withdrawn** (`ERRATUM-2026-10-09.md`, E2). It is BLOCKED and cannot be reproduced from any pinned lockfile.
8. **Unpatched pinned Python packages.** Werkzeug, WeasyPrint and PyJWT are not upgraded. Each is closed by reachability, not by a patch, and each reachability claim reopens when its trigger changes (`upgrade_blockers`).
9. **npm fixes depend on frozen upstream lockfiles** (vue, tailwind/typography, frappe-ui/tiptap, postcss, prosemirror). They need upstream refreshes.
10. **Werkzeug bind-mount residual.** Docker Desktop device-name handling through the `sites/` mount is untested. Impact would be availability only.
11. **Restore acceptance gaps (in scope, not security).** See section 8. The Course Owner login, the account and configuration comparison after restore/restart/repair, and a separate repair step are not yet demonstrated by CI.
12. **Release readiness is not established.** This PR claims no release gate. Open: items 1, 2 and 11, plus the other release gates not verified in this session.

## 8. Coordination with `arena/abdece6c-tofel-house-erp` (PR #14, merged)

* PR #14 (`arena/abdece6c-tofel-house-erp` → `main`, "Match native Frappe backup and restore paths") merged at `13482fe` on 2026-10-09T13:55:47Z. This branch merged `origin/main` into itself (`b379c28`, no force push). The one conflict was `.github/workflows/product-image.yml`.
* Resolution: main's workflow, plus one change to the restore rehearsal's marker gate. Marker creation and the post-restore absence check moved from `bench console` heredocs to python3 probes. Each probe runs from `bench/sites`, prints a `RESULT` line, and fails closed. Reason: a raised exception in a console cell can exit 0 with no row, which makes an absence check vacuous. The first python3 attempt (`5bbf157`) ran from the container WORKDIR and failed with exit 1. The most likely cause is Frappe's logger, which opens a CWD-relative `../logs/` file (`frappe/utils/logger.py`, pinned 988e54f3). The subsequent passing run with the directory change supports that cause, but the failing output was not captured. The corrected probes follow the pattern of main's passing verification probes, and the Product image run on `b379c28` passed with them (section 6.2).
* Please review the marker gate (`marker-create.txt`, `marker-after.txt`) and `tests/foundation/test_restore_rehearsal_gate.py`. Please avoid editing `product-image.yml` in parallel until this PR is merged or the two branches are reconciled.
* Acceptance gaps still open on main's workflow: (a) the synthetic Course Owner `backup-owner@toeflhouse.localhost` is created and its backup policy configured, but it never logs in. The browser step logs in as Administrator; (b) the Owner configuration (backup policy and recovery-key identity) and the account/profile state are checked only before the backup, and are not compared after restore, restart and repair; (c) `Repair TOEFL House ERP.cmd` is not exercised as a distinct step.
* Suggested row text for the owner of `docs/engineering/ACCEPTANCE.md` (not applied here, because the file is shared): "STACK-ADVISORY-UNTRIAGED: 8 matches = 7 unique advisories, dispositioned in advisory-delta-2026-10-09 (replay: 0 untriaged). Gate closure on a head depends on that head's Foundation runtime run. GHSA-c8x8 in the HRMS SPA is an open release blocker, not gated."

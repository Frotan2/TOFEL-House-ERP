# SEC-DEPS-01 advisory delta: 2026-10-09

Additive delta for the `STACK-ADVISORY-UNTRIAGED` gate failure. It dispositions the
eight matches the gate failed on (seven unique advisories). It does not patch
anything and does not claim release readiness.

Files:

| File | Purpose |
|---|---|
| `delta-dispositions.json` | Loader input: 7 advisories, dispositions, evidence, fix paths, upgrade blockers |
| `replay-snapshot.json` | Offline replay of npm bulk + PyPI per-release data, 2026-10-09 (108 npm entries, 62 PyPI records) |
| `python-pins-replay.txt` | 153 Python pins resolved with uv 0.11.6 from the five pinned upstream manifests |

## 1. Verdict

* The gate's untriaged set is exactly 8 matches = **7 unique advisories**. PYSEC-2026-4183 is the PyPI mirror of GHSA-x33g-cr3x-6449, and the npm numeric IDs are the same advisories as GHSA-g2v6, GHSA-rj75, GHSA-c8x8 and GHSA-68fv.
* After this delta, the replay yields **0 untriaged** npm entries (108/108 closed) and **0 untriaged** Python records (62/62 closed) under the repository loader.
* No dependency was upgraded. Every fixed version lies outside the pins that the pinned upstream stack enforces. A forced upgrade would violate upstream requirements or require patching frozen upstream lockfiles, which the repository policy forbids. See section 4.
* Closure of GHSA-r543-q48m-4c9j (WeasyPrint RCE) is conditional on the Product image build on the PR head passing with the new Ghostscript guard (section 5). If that build fails, that disposition must reopen.

## 2. Advisory triage table

Reachability notes are summarized. Full evidence is in `delta-dispositions.json`.

| # | Advisory (aliases) | Package @ installed | Sev. / CVSS | Path | Fixed in | Upgrade blocked by | Disposition | Basis (short) |
|---|---|---|---|---|---|---|---|---|
| 1 | GHSA-x33g-cr3x-6449 (CVE-2026-102275, PYSEC-2026-4183) | pyjwt 2.13.0 | medium 6.5 | direct (frappe pin) | 2.15.0 | frappe `PyJWT~=2.13.0` | NOT_REACHABLE | Trigger is OKP private-JWK import (PyJWK / from_jwk, DPoP-style). Frappe uses HS256 with string secrets only; no JWK/OKP/DPoP code in any pinned or owned tree. |
| 2 | GHSA-r543-q48m-4c9j (CVE-2026-106443) | weasyprint 68.0 | high 8.8 | direct (frappe pin) | 70.0 | frappe `WeasyPrint==68.0` | MITIGATED | RCE needs WeasyPrint to render an attacker EPS image (beta print formats only) **and** a `gs` binary. The image guard in `product/app.Dockerfile` fails the build if `gs` is on PATH. Conditional on the image build; see section 5. |
| 3 | GHSA-g6x2-hccm-hh4m (CVE-2026-102598) | werkzeug 3.1.6 | medium | direct (frappe pin) | 3.1.9 | frappe `Werkzeug==3.1.6` | NOT_REACHABLE | Windows/NTFS device-name issue. The product is a Linux container; the Windows host only runs `docker compose`. Residual: Docker Desktop bind-mount semantics not tested (availability only). |
| 4 | GHSA-g2v6-rqmx-r4w6 (1241259) | @vue/server-renderer 3.3.9 (frappe), 3.4.19 (education SPA) | high 7.2 | transitive via vue | 3.5.42 | frozen upstream lockfiles (vue ^3.3.0 / ^3.2.25) | NOT_REACHABLE | Needs SSR of attacker-controlled attribute names. No SSR entry in pinned sources; the built education bundle has zero server-renderer code markers. |
| 5 | GHSA-rj75-hqrm-r3gf (CVE-2026-104844, 1241232) | postcss-selector-parser 6.0.10, 6.0.13, 6.0.15 | moderate 5.9 | transitive (tailwind, typography, component-compiler-utils) | 7.1.6 (major) | frozen lockfiles; 6.x to 7.x is a major bump | BUILD_ONLY | Needs synchronous parsing of attacker selectors in a request path. Consumers are build tools over repo-owned CSS; nothing parses selectors at runtime. |
| 6 | GHSA-c8x8-7fp4-3x9w (CVE-2026-104847, 1241270) | prosemirror-view 1.33.1 | high | transitive: frappe-ui 0.1.31 → @tiptap/pm 2.2.3 (education SPA) | 1.42.3 | frozen education lockfile | NOT_REACHABLE | Module code is in the shipped bundle (frappe-ui chunk), but no editor is constructed: TextEditor is imported only by frappe-ui's barrel; the SPA never imports or registers it. |
| 7 | GHSA-68fv-2mgg-jv7q (CVE-2026-93749, 1241209) | source-map-js 1.0.2 | high 7.5 | transitive: postcss 8.4.31 (frappe), 8.4.35 (education) | 1.2.2 | frozen lockfiles (postcss ranges resolve 1.0.2) | BUILD_ONLY | Needs an attacker-supplied indexed source map parsed in a process. postcss runs at build time over repo-owned sources; no runtime Node file imports it. |

Per-disposition blocking detail (upgrade paths and compatibility) is in `upgrade_blockers` inside the JSON.

## 3. Matches versus unique advisories (why "160" is not 160 vulnerabilities)

| Measure | Value | Source |
|---|---|---|
| CI header (run 37902411810, head a3b45abc9) | advisory matches=160 in 47 packages | annotation, Foundation runtime |
| Replay groups (npm packages + Python package@version) | 40 + 7 = 47 (matches CI) | `replay-snapshot.json` counts |
| npm bulk entries, raw | 108 | npm bulk, against the CI-audited pinned lockfiles |
| npm matches, CI-style (unique GHSA per package) | 96 | same; 12 duplicate numeric IDs collapse to one GHSA |
| npm unique GHSA IDs | 91 (96 package-advisory pairs; a few GHSAs hit two packages) | same |
| Python PyPI records, raw | 62 across 7 packages | PyPI per-release `vulnerabilities` |
| Python unique advisories (alias-merged) | 32 (30 are GHSA/PYSEC mirror pairs) | same |
| Replay total, CI-style (no GHSA/PYSEC merge, which is how the CI annotation lists them) | 96 + 62 = 158 | CI reported 160; the 2-match difference is not explained (feed drift or OSV/PyPI differences); the untriaged set matches exactly |
| Unique underlying advisories, all ecosystems | 91 + 32 = 123 | replay |
| Untriaged matches before this delta | 8 (= 7 unique) | replay and CI agree |
| Untriaged matches after this delta | 0 | replay under current loader |

The 160 figure therefore counts identifier entries, not vulnerabilities. Most Python
matches are the same advisory listed under both its GHSA and its PYSEC identifier.

## 4. Upgrade and compatibility analysis

No safe, minimal, compatible upgrade exists for any untriaged item in the pinned stack.

Python (Frappe's exact or compatible-release pins are the binding constraint):

| Candidate | Frappe v16.33.1 pin (`988e54f3`) | Same pin in v16.35.0, v16.36.1, v16.49.0, v16.50.0, v16.51.0 | ERPNext / Education / HRMS / Payments | Verdict |
|---|---|---|---|---|
| PyJWT 2.13.0 → 2.15.0 | `PyJWT~=2.13.0` | yes, unchanged | none declared | Blocked: frappe pin |
| Werkzeug 3.1.6 → 3.1.9 | `Werkzeug==3.1.6` | yes, unchanged | none declared | Blocked: frappe pin |
| WeasyPrint 68.0 → 70.0 | `WeasyPrint==68.0` | yes, unchanged | none declared | Blocked: frappe pin |

Frappe's pins were checked against the upstream v16 tags listed above (the newest is v16.51.0). A
forced upgrade would violate a declared requirement, which the uv resolver rejects by design.

npm: every fixed version requires moving a frozen upstream lockfile (vue, tailwind/typography, frappe-ui, postcss). The repository does not patch upstream code or lockfiles. These are upstream refreshes, not owned changes.

Pinned upstream evidence was checked before writing this delta: the five commit-pinned
source trees match their commit pins in `docs/engineering/foundation-version-matrix.json`,
and every recorded `source_file_sha256` (pyproject, package.json, yarn.lock and frontend
lockfiles) matches. The Frappe pyproject hash is recorded in the JSON and enforced by a test.

## 5. Changes in this PR

1. `docs/engineering/evidence/sec-deps-01/advisory-delta-2026-10-09/` (new): delta, README, replay snapshot, Python pins.
2. `product/app.Dockerfile`: one final `RUN` guard. It fails the image build if a `gs` executable is on PATH. Pillow's EPS plugin runs `gs` found on PATH (`PIL/EpsImagePlugin.py`), so this removes the RCE precondition from the shipped image. The base image (`python:3.14.7-slim-bookworm`) and the explicit apt set name no ghostscript package. Transitive absence could not be proven here (no Debian mirror access), so it is enforced at build time rather than assumed.
3. `tests/security/test_advisory_delta_2026_10_09.py` (new, 16 tests): exact CI set coverage through the real loader, replay zero-untriaged, self-consistent counts, pins, Frappe pyproject hash binding, guard placement, guard shell behavior with and without a stub `gs`, and static WeasyPrint override wiring.

No change to the immutable 2026-09-23 register, to other deltas, to the version matrix, to
workflows, or to `tools/foundation/*`.

## 6. Verification

Commands run from the repository root on this branch (results in section 6.1).

```
/tmp/analysis/lintvenv/bin/ruff check .                          # ruff 0.16.8, hash-pinned as in owned-suite.yml
python3 -m unittest discover -s tests -t . -v                    # owned-suite Python step
node tests/foundation/test_realtime_guard.cjs                    # owned-suite Node steps
node tests/foundation/test_command_pages.cjs
node tests/foundation/test_design_system.cjs
node tests/foundation/test_role_desks.cjs
python3 -m unittest tests/security/test_advisory_delta_2026_10_09.py -v
```

Replay scripts ran from a scratch directory outside the repository. Their method and inputs are
recorded in `replay-snapshot.json` (`method`, `pinned_upstream_input_sha256`). They performed an
npm bulk POST for the CI-audited trees, PyPI per-release JSON for the 153 pins, a `semver` range
check, and the repository loader. Sandbox limits: `api.osv.dev` unreachable (PyPI JSON used as
its proxy); Debian mirrors unreachable; no Docker or MariaDB; Node v22.22.3 used locally versus
the pinned Node 24.21.0 in CI.

6.1 Results (sandbox, Python 3.11.2 and Node v22.22.3; this change tree before commit):

| Check | Result |
|---|---|
| `ruff check .` (ruff 0.16.8, hash-verified install) | `All checks passed!`, exit 0 |
| `python3 -m unittest discover -s tests -t . -v` | `Ran 1177 tests`, `OK`, exit 0 (baseline on the untouched branch: 1161, `OK`) |
| of which this delta's module `tests/security/test_advisory_delta_2026_10_09.py` | 16 of 16 pass |
| of which product packaging (`tests/foundation/test_product_packaging.py`) | 59 pass (Dockerfile ordering and content checks) |
| Node: `test_realtime_guard.cjs`, `test_command_pages.cjs`, `test_design_system.cjs`, `test_role_desks.cjs` | all exit 0 |
| Loader after delta | `advisory-delta-2026-10-09` loaded, 7 advisories, 54 delta advisories total (47 before) |
| Replay (npm 108 entries, PyPI 62 records) under loader | 0 untriaged; 108/108 npm and 62/62 PyPI closed |
| Python pin reproducibility (uv 0.11.6 re-run) | 153 pins byte-identical to `python-pins-replay.txt` |
| Frappe pyproject hash vs matrix | equal (`75a442bc…d8a6`), enforced by test |
| Ghostscript guard, shell behavior | exit 0 with no `gs` on PATH; exit 1 with a stub `gs`, with the GHSA message |
| `git diff --check` | clean |

Not run here: the Product image build (no Docker) and the hosted Foundation runtime (both
depend on the hosted runners). They are the only checks that can prove the guard and the full
gate. Their results on the PR head are recorded in the PR body.

## 7. Remaining security risks (not closed by this PR)

1. **Unpatched pinned Python packages.** Frappe pins Werkzeug and WeasyPrint exactly, PyJWT to a compatible release (`~=2.13.0`), and pypdf exactly (`==6.15.0`). pdfkit and oauthlib are compatible-release pins. All advisory records for these packages are closed by reachability, not by patching. Any future reachability change reopens them.
2. **npm fixes are frozen upstream.** Every npm advisory in this delta depends on an upstream lockfile refresh (vue, tailwind/typography, frappe-ui/tiptap, postcss).
3. **WeasyPrint call paths bypass the owned override gate.** `frappe/www/printview.py` (line 76) imports the vendor `get_html` directly. `frappe/utils/print_utils.py` `attach_print` renders beta formats via `PrintFormatGenerator` with `ignore_print_permissions` set. The 2026-09-23 register's MITIGATED dispositions for the WeasyPrint SSRF family (for example GHSA-jf6q-chmf-3h3v) cite the override gate alone. Those dispositions are over-stated for these paths. The register is immutable, so this needs an owner decision: disable beta WeasyPrint rendering, or extend the gate to these paths.
4. **Register references a missing test.** The 2026-09-23 register cites `tests/foundation/test_sec_deps_triage.py::test_weasyprint_whitelist_overrides_pin_beta_gate`. That file exists on neither `main` nor `arena/abdece6c-tofel-house-erp`. The static checks in this PR cover only the wiring, not behavior.
5. **HRMS SPA is outside the gate.** `hrms/frontend` (not built by the product build path, not in the CI audit) mounts frappe-ui `TextEditor` in `src/components/FormField.vue` with `prosemirror-view` 1.31.3 (GHSA-c8x8 applies). It also carries `@vue/server-renderer` 3.5.13, `postcss-selector-parser` 6.0.10/6.0.13/6.1.2 (including low GHSA-w9m9-85wc-3x92), and `source-map-js` 1.2.1. Those would be untriaged if that tree were scanned. Audit it before any HRMS SPA is built or served.
6. **Incorrect evidence in the 2026-10-03 delta.** Its echarts and frappe-ui@0.1.278 reasoning came from a non-lockfile resolution. The frozen trees use frappe-ui 0.1.31, and echarts is absent from all six lockfiles, including HRMS. The disposition stands, but its evidence text should be corrected by the owner. This PR does not edit the earlier delta.
7. **Ghostscript guard unverified until built.** The closure of GHSA-r543 is conditional on the Product image build on the PR head. The build could not run in this sandbox.
8. **Werkzeug bind-mount residual.** Docker Desktop mounts `sites/` from the Windows host. Device-name handling through that mount is untested. Impact would be availability only.
9. **Feed drift.** The CI-reported 160 cannot be reproduced exactly (the 2-match difference above). The untriaged set is reproduced exactly. Re-run the replay on any new gate failure.
10. **Release readiness is not established.** Other release gates (restore-with-files, native lifecycle, browser and live E2E) were not verified in this session. The other branch's Foundation run fails at restore-with-files, which is outside this PR's scope.

## 8. Coordination with `arena/abdece6c-tofel-house-erp`

* Files this PR touches: the new delta directory, one `RUN` guard in `product/app.Dockerfile` (the other branch does not change it), and the new test module. No overlap with files that differ on the other branch (`.github/workflows/foundation-runtime.yml`, `tests/foundation/test_advisory_annotations.py`, `tools/foundation/runtime_install.py`).
* Not touched: `docs/engineering/ACCEPTANCE.md` (the other agent owns the SEC-DEPS-01 row), the version matrix, the register, and all `tools/foundation/*`.
* If the other branch adds its own 2026-10-09 delta, it must use a different directory name (for example `advisory-delta-2026-10-09-2`). The loader rejects redefinition of an ID anyway.
* Suggested ACCEPTANCE row text for that owner: "STACK-ADVISORY-UNTRIAGED: 8 matches = 7 unique advisories, dispositioned in advisory-delta-2026-10-09 (replay 2026-10-09: 0 untriaged). Gate closure depends on the Product image build on this PR head proving the Ghostscript guard. Foundation runtime restore-with-files remains a separate open failure."

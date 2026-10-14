# Security finalization — 2026-10-14

## Release decision: NO-GO (qualification in progress)

Inspected remote `main`: `807d5dca324e32546d8c0b52c255be38aa7b3513`.
PR #13 was **already merged** at 2026-10-14 01:27:49 UTC. Its descriptive
"OPEN—DO NOT MERGE" text and the earlier acceptance snapshot are historical,
not current branch state. No open PR existed when this investigation began.
Work is on `arena/8d125fff-tofel-house-erp`; no other branch was checked out.

## Defect register and evidence

| ID | Reproduction / root cause | Change | Verification / remaining gate |
|---|---|---|---|
| DEP-01 | Fresh npm query of pinned HRMS frontend/roster and ERPNext banking lock union: 168 advisory matches, 77 open. Nested lockfiles retained old transitive versions; replacing only ProseMirror and Socket.IO left other families vulnerable. | Yarn Classic 1.22.22 regenerated locks within existing direct-dependency ranges; exact editor resolutions retained. Two explicit compatible-major security overrides for Firebase's Node dependencies: gRPC 1.13.7 (upstream ~1.9.0), undici 6.29.0 (upstream exact 6.19.7). | Three real installed trees: 968 package names, 12 matches, **0 open** under unchanged policy. All three ordinary Vite production builds passed locally; synthetic undici HTTP and gRPC unary round-trips pass on Node 24.21.0. Full-stack hosted audit and Firebase integration qualification still required. |
| PDF-01 | Inspected hash-pinned Frappe renderer: both HTML constructors used the default URL fetcher. Document print permission did not constrain HTML/CSS file or network resources. | Offline resource policy injected into both main/overlay constructors. Local app assets and same-document permission-checked raster attachments only; bounded raster data URIs. No HTTP, DNS, redirects, arbitrary file scheme, symlink traversal or default-fetch fallback. Failed fetches reject the final PDF instead of returning incomplete success. | Unit policy/wiring tests pass; real installed-renderer main/CSS/attachment/header/footer attacks added to Native acceptance. Local WeasyPrint import blocked by missing Pango. Native hosted execution pending. |
| AUD-01 | `osv_pypi_advisories` treated a non-object batch result (e.g. null) as an empty advisory list, creating false-clean evidence. | Reject malformed/error/paginated results instead of treating them as clean. | Negative cases for null, array, string, error object, malformed vulns and pagination pass. |
| EDIT-01 | No built HRMS editor hostile-input acceptance existed. | Compiles **actual pinned HRMS FormField.vue** and its installed Frappe UI editor, then drives Chromium paste, import and read-only rendering. No editor implementation is mocked; later Markdown extension exposed EDIT-02 below. | Initial nine hostile payloads across three paths (27 cases), plus bold/italic/list and keyboard-edit preservation pass on Node 24.21.0 / Chromium 143.0.7499.0. This is built-component acceptance, **not authenticated full-site E2E**. Foundation now executes it after its ordinary asset build. |
| EDIT-02 | Built Chromium Markdown paste reproduced executable `onerror` before ProseMirror parsing (`window.__executed = 1`) even though the final DOM contained zero event attributes. Frappe UI constructed the Markdown HTML in a disconnected element belonging to the live document. | Hash-bound patch parses Markdown into an inert DOMParser document before schema conversion, in every installed HRMS Frappe UI copy. Verified before/after builds and on product boot. | Original browser reproducer failed; patched nine-payload import/read-only/HTML paste/**Markdown paste** matrix passes (36 cases), with legitimate editing preserved. No route disabled, no editor replaced, no additional advisory waiver. |
| WIN-01 | Historical `exec /product/entrypoint.sh: no such file or directory` can be caused by CRLF in a Linux shebang even when the file exists. | Baseline already has explicit LF attributes, stale-worktree normalizer, in-image byte checks, chmod and /bin/sh. No redundant workaround added. New lock overlays are covered by Docker allowlist and LF contract. | Packaging/normalization contract tests pass locally. Main's Product image run passes; actual owner Windows/Docker Desktop lifecycle remains unexecuted. |
| WIN-02 | Installer regenerated `db.env` whenever it was missing, even if the existing named database volume remained. Start/Repair warned against this but Install did not enforce the warning. | Read-only preflight rejects existing site files/volume and Docker inventory errors before generating any password. | Contract tests pass; executable Windows PowerShell cases for fresh/existing/error/site-file paths, with sentinel preservation, pass in the hosted Windows job on final `main` (run 38581773272). |
| AUTH-01 | Reproduced uncaught provider-flow exception: token exchange/JSON parsing ran outside the callback's generic denial handler. | Include transport and response parsing in the sanitized failure boundary; raise the generic denial outside exception context. | Regression previously errored with the synthetic provider message; now passes along with cryptographic identity tests. No new identity claim requirement or email-based linking added. |
| PDF-02 | Hosted Native run 38498528739 failed at the first *authorized* `download_pdf` (`security_acceptance.py:main:56`, `pdf_resources.py:check:98`): the `--skip-assets` harness returned an empty asset manifest, so the pinned print template's `include_style()` emitted the unresolved fallback `/print_format.bundle.css`, which is not a packaged `/assets/<app>/` URL and was correctly denied, poisoning the whole PDF. The policy was right; the test fixture was invalid. | Native acceptance now maps `print_format.bundle.css` to the packaged pinned-Frappe stylesheet `/assets/frappe/css/tree.css` and additionally renders a legitimate packaged stylesheet/font/SVG PDF through the installed renderer. The policy still denies the unresolved bundle path and any unavailable asset; no allowance was added. | New unit regressions cover the unresolved-bundle denial, nested packaged bundle/font/SVG fetches, and the harness mapping. Hosted Native **SUCCESS** on corrected head `7e5186e` (run 38579194100) and again on final `main` (below). |
| WIN-03 | Hosted Product-image run 38498528731 Windows job failed with only a generic exit-code annotation and no `::error` from the synthetic preflight: every assertion had passed, but the simulated Docker failure left `$global:LASTEXITCODE=1`, which the Actions PowerShell wrapper promotes to the step exit code. | The synthetic Windows test clears the simulated native exit code after the Docker-error case and again on its success path. The production credential preflight (WIN-02) is unchanged and still fails closed. | New packaging contract regression pins the reset ordering. Hosted Windows job **SUCCESS** on `c1a9edd`. Real Windows/Docker Desktop owner acceptance remains a separate gate. |
| PDF-03 | First corrected Native rerun (`c1a9edd`) passed the authorized PDF, then failed at `security_acceptance.py:main:88` with `AttributeError` from `unittest.mock`: the hostile-case guard patched `weasyprint.urls.urlopen`, which does not exist in pinned WeasyPrint 68 (its default fetcher is the `URLFetcher` class). This defect was masked until PDF-02 was fixed. | Guard `weasyprint.urls.URLFetcher.fetch` instead; the owned policy is a plain callable and never uses that class, so any call is a default-fetch escape. No renderer or policy code changed. | Regression in `test_pdf_resources.py` pins the 68 fetcher patch target. Hosted Native rerun pending. |

`scoped-npm-audit.json` records fresh advisory IDs, severities, affected ranges,
resolved versions, baseline lock-root provenance, final installed versions and
the unchanged existing per-package dispositions. This is not a waiver, an
exploitability claim, or a final full-stack audit. Examples removed from the
three installed trees include Babel traversal GHSA-67hx-6x53-jw92, protobufjs
GHSA-xq3m-2v4x-88gg, websocket-driver GHSA-xv26-6w52-cph6, and the previously
open Axios, undici, gRPC, AJV, js-yaml, flatted and word-wrap matches.

### Reproducible dependency overlays

- Owned `tools/foundation/{hrms,banking}-locks` contain the **Yarn-generated**
  manifests/locks plus upstream/output SHA-256 hashes. No upstream version
  matrix commit is silently changed.
- Installers first verify the original source inputs, then apply these explicit
  reviewed overlays only to disposable build checkouts. Installation uses
  `yarn install --frozen-lockfile --non-interactive`, never opportunistic upgrade.
- All changed upstream tracked files are enumerated in Native's final source
  check and verified byte-for-byte. All other tracked upstream files remain
  pinned. Installed dependency trees are still audited **after** asset build.
- Existing publisher-integrity/code-tree checks on ProseMirror and Socket.IO
  remain enabled. They are additional checks, not substitutes for locks/audit.
- Direct HRMS Frappe UI stays 0.1.105; Vue/Vite/plugin major versions are not
  arbitrarily advanced. Ordinary HRMS frontend, roster and banking builds pass.
- No npm/Python advisory was added to closed triage by this change. Python
  oauthlib/pdfkit findings are not claimed fixed by frontend upgrades.

### PDF resource behavior

The resource policy is technical, not a new business-rule default. Remote
letterhead images must be replaced by trusted packaged assets or authorized
raster images attached to the document. Cross-document uploads, uploaded SVG,
HTTP resources (including same-origin endpoints), local file references and
unavailable assets deliberately fail closed. No private file is read before
checking both native File permission and attachment-to-target identity.
Trusted app assets retain CSS, fonts, SVG and raster support; nested resource
loads use the same policy. Limits: 5 MiB/resource, 20 MiB total, 128 fetches.
These limits do not prove immunity to every CPU/memory exhaustion payload or
all CSS injection findings. No existing advisory disposition is changed.

## Baseline and branch preservation

- Initial Python suite: 1,277 tests, OK, one skipped crypto-test class because
  PyJWT was absent. Installed the repository's hash-pinned crypto test wheels;
  subsequent full suite has **no skips**.
- Initial four Node suites passed (initial system Node 22; final checks use the
  supported Node 24.21.0). Ruff 0.16.8 passes.
- GitHub run logs redirect to a host not reachable from this sandbox (EOF).
  Check metadata and annotations **are** retrievable through GitHub API; no
  claim is made to have read inaccessible full hosted logs/artifacts.
- Remote `arena/e650655f-tofel-house-erp`, `fix/product-packaging-windows-bootstrap`,
  `fix/product-perf-baseline-line-ending`, and `fix/windows-permission-contract`
  have zero commits outside main. No branches were deleted.
- `arena/abdece6c-tofel-house-erp` has nine non-ancestor commits. Their affected
  acceptance/runbook/Windows validation and restore tests are already present
  in main's resulting file contents; the remaining tree differences are later
  security/product work on main. Do not merge its older tree or delete it just
  on this summary; preserve its attribution/history until closure is reviewed.

## Follow-up fixes (blocker rerun) — integrated

The PDF-02, PDF-03 and WIN-03 fixes above were made on
`arena/1f1c36da-tofel-house-erp`, which is `main` plus the three PR #16 commits
plus the corrections, and landed through superseding PR #17 (merged
2026-10-14). GitHub marks PR #16 MERGED because its commits entered `main`
through #17. Local evidence at the corrected commit: full owned suite 1,294
tests OK (one skip: PyJWT absent locally, as in the baseline), Ruff 0.16.8
clean, and all four Node suites pass.

### Final hosted evidence on exact `main` SHA `5399e20a5ea60aa6fc962fea5d99f2eba62d1c72`

| Gate | Result | Run |
|---|---|---|
| Owned suite | SUCCESS | [38581773517](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/38581773517) |
| Native lifecycle | SUCCESS | [38581773309](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/38581773309) |
| Product image (image + Windows jobs) | SUCCESS | [38581773272](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/38581773272) |
| Foundation runtime | SUCCESS | [38581773196](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/38581773196) |

Foundation annotations still record 160 advisory matches in 47 packages under
the pre-existing dispositions; those advisories are not claimed eliminated.
Product-image annotations confirm first boot (~10s), real Chromium login, the
tailnet contract and the workflow's synthetic backup/restore rehearsal on the
built image. The decision stays NO-GO until the owner-machine gates below are
done; green CI is not production authorization.

### Branch closure review (full-history, 2026-10-14)

Verified with an unshallowed fetch (the sandbox clone is depth-1 by default,
which makes ancestry checks meaningless): `arena/1f1c36da-tofel-house-erp`,
`arena/8d125fff-tofel-house-erp`, `arena/e650655f-tofel-house-erp` and the
three `fix/*` branches are git ancestors of `main` — zero unique commits, so
their work is preserved in `main` history. `arena/abdece6c-tofel-house-erp`
has nine non-ancestor docs/test commits; their substance entered `main`
through merged PRs #14/#15 and later ledgers, but the branch is retained for
attribution. No documented repository branch-deletion policy exists, so no
branch was deleted; deletion remains an owner action under that policy.

### Issue #12 (Windows line-ending / packaging audit) status

The automated parts of issue #12 are evidenced on final `main`: fresh and
stale (CRLF+BOM) Windows worktrees materialize/normalize to LF (Windows job in
run 38581773272), the in-image shebang/EOL byte checks, Compose/Dockerfile,
startup/health, backup/restore and configuration-plane contract gates all
pass in the runs above. The issue remains open solely for the real
owner-machine Windows lifecycle validation (Docker Desktop install, reboot,
Task Scheduler, owner backup drive/key custody), which CI cannot perform.

## Real-world gates (not substituted by unit tests)

Owner business values, retention authorization, key custody, recovery quorum,
actual secondary Windows drive, Docker Desktop startup/repair, Task Scheduler,
real backup recovery and private Tailscale/WebSocket operation still need their
existing runbook acceptance. No owner decision was invented or silently marked
approved. No production site, owner secret, real backup or owner data was
accessed, restored, deleted or changed. Release authorization remains REJECT.

### Advisory evidence correction: HRMS Markdown

The immutable historical Showdown disposition cited Python `frappe.markdown()`
sanitization. That is not the HRMS browser Markdown paste path. This review
reproduced execution in that browser path and fixed it; the historical prose
must not be used as proof for the unpatched HRMS editor. The current patch and
built regression, rather than the Python sanitizer, are the relevant new
mitigation evidence for this path (including GHSA-22g5-r2x5-97cx's unsafe HTML
handling family). No claim is made to eliminate every possible Showdown or
Tiptap advisory. Full-site and stored-content paths remain separate gates.

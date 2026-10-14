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
| DEP-01 | Fresh npm query of pinned HRMS frontend/roster and ERPNext banking lock union: 168 advisory matches, 77 open. Nested lockfiles retained old transitive versions; replacing only ProseMirror and Socket.IO left other families vulnerable. | Yarn Classic 1.22.22 regenerated locks within existing direct-dependency ranges; exact editor resolutions retained. Two explicit compatible-major security overrides for Firebase's Node dependencies: gRPC 1.13.7 (upstream ~1.9.0), undici 6.29.0 (upstream exact 6.19.7). | Three real installed trees: 968 package names, 12 matches, **0 open** under unchanged policy. All three ordinary Vite production builds passed locally. Full-stack hosted audit and Firebase integration qualification still required. |
| PDF-01 | Inspected hash-pinned Frappe renderer: both HTML constructors used the default URL fetcher. Document print permission did not constrain HTML/CSS file or network resources. | Offline resource policy injected into both main/overlay constructors. Local app assets and same-document permission-checked raster attachments only; bounded raster data URIs. No HTTP, DNS, redirects, arbitrary file scheme, symlink traversal or default-fetch fallback. Failed fetches reject the final PDF instead of returning incomplete success. | Unit policy/wiring tests pass; real installed-renderer main/CSS/attachment/header/footer attacks added to Native acceptance. Local WeasyPrint import blocked by missing Pango. Native hosted execution pending. |
| AUD-01 | `osv_pypi_advisories` treated a non-object batch result (e.g. null) as an empty advisory list, creating false-clean evidence. | Reject malformed/error/paginated results instead of treating them as clean. | Negative cases for null, array, string, error object, malformed vulns and pagination pass. |
| EDIT-01 | No built HRMS editor hostile-input acceptance existed. | Compiles **actual pinned HRMS FormField.vue** and its installed Frappe UI editor, then drives Chromium paste, import and read-only rendering. No editor implementation is mocked. | Nine hostile payloads across three paths (27 cases), plus bold/italic/list and keyboard-edit preservation pass on Node 24.21.0 / Chromium 143.0.7499.0. This is built-component acceptance, **not authenticated full-site E2E**. Foundation now executes it after its ordinary asset build. |
| WIN-01 | Historical `exec /product/entrypoint.sh: no such file or directory` can be caused by CRLF in a Linux shebang even when the file exists. | Baseline already has explicit LF attributes, stale-worktree normalizer, in-image byte checks, chmod and /bin/sh. No redundant workaround added. New lock overlays are covered by Docker allowlist and LF contract. | Packaging/normalization contract tests pass locally. Main's Product image run passes; actual owner Windows/Docker Desktop lifecycle remains unexecuted. |

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

## Real-world gates (not substituted by unit tests)

Owner business values, retention authorization, key custody, recovery quorum,
actual secondary Windows drive, Docker Desktop startup/repair, Task Scheduler,
real backup recovery and private Tailscale/WebSocket operation still need their
existing runbook acceptance. No owner decision was invented or silently marked
approved. No production site, owner secret, real backup or owner data was
accessed, restored, deleted or changed. Release authorization remains REJECT.

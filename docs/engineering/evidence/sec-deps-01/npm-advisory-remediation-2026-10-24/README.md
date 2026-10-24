# npm advisory remediation — 2026-10-24 (Issues #41 / #38)

## Trigger

Foundation runtime run
[40074521329](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40074521329)
failed `hosted-full-stack-dependency-audit` with
`STACK-ADVISORY-UNTRIAGED (matches=10)`. Seven of the ten matches are npm
findings (the other three — `filelock`, `setuptools` — are Python findings
remediated separately under the Python workstream and are out of scope here):

| npm id | Package / installed version | GHSA | CVE | Severity | Vulnerable range | First patched |
|---|---|---|---|---|---|---|
| 1243098 | fast-uri 3.1.8 | GHSA-w74x-v6f9-j3xg | CVE-2026-110306 | moderate | `>=3.0.0 <3.1.9` | 3.1.9 |
| 1243101 | fast-uri 3.1.8 | GHSA-xhq7-xmqj-769h | CVE-2026-110095 | low | `>=3.0.0 <3.1.9` | 3.1.9 |
| 1243104 | fast-uri 3.1.8 | GHSA-wjr9-j795-jxcr | CVE-2026-110184 | moderate | `>=3.1.3 <3.1.9` | 3.1.9 |
| 1243107 | fast-uri 3.1.8 | GHSA-333x-w4r6-6crp | CVE-2026-110725 | low | `>=3.0.0 <3.1.9` | 3.1.9 |
| 1243082 | serialize-javascript 7.1.2 | GHSA-m5mm-p8h7-m29v | CVE-2026-115897 | low | `<7.1.3` | 7.1.3 |
| 1243079 | undici 6.29.0 | GHSA-4qv8-2p9j-2685 | CVE-2026-109924 | moderate | `>=6.5.0 <6.29.1` | 6.29.1 |
| 1243114 | undici 6.29.0 | GHSA-xjj6-f33q-929c | CVE-2026-109869 | high | `>=6.23.0 <6.29.1` | 6.29.1 |

Affected/fixed ranges were confirmed against two independent sources on
2026-10-24: the live npm bulk advisory endpoint
(`/-/npm/v1/security/advisories/bulk`, captured in
`npm-advisory-bulk-vulnerable-versions.json`) and the GitHub global advisory
API for each GHSA (which additionally lists the 7.x/8.x undici and 2.x/4.x
fast-uri lines; only the installed 6.x/3.x lines are in scope here).

## Installed copies, dependency chains, and affected application

All three packages existed in exactly **one** installed tree: the HRMS
frontend (`apps/hrms/frontend`, overlay source
`tools/foundation/hrms-locks/frontend`). A full search of every reviewed lock
overlay shows no other installed copy:

- `tools/foundation/hrms-locks/roster/yarn.lock` — none of the three packages.
- `tools/foundation/education-locks/frontend/yarn.lock` — none.
- `tools/foundation/banking-locks/banking/yarn.lock` — only the separate
  `undici-types` type-definition package, which is not covered by either
  undici advisory.
- `tools/foundation/realtime-locks/yarn.lock` — only `undici-types` (~5.x),
  likewise unaffected.

Dependency chains inside the HRMS frontend lock (Yarn Classic v1):

- **fast-uri 3.1.8** — single top-level resolution `fast-uri@^3.0.1`, required
  by `ajv@8.20.0` (`ajv@^8.6.0`), the JSON Schema validator used across the
  Vite/Vue build toolchain and bundled browser code.
- **serialize-javascript 7.1.2** — single resolution
  `serialize-javascript@^7.0.3`, required by
  `@rollup/plugin-terser@1.0.0`, itself pulled in by the Workbox/PWA service
  worker build (`vite-plugin-pwa@0.20.5`). It executes at asset-build time
  when rollup terser output is serialized; it is not an application request
  path.
- **undici 6.29.0** — five Firebase packages exact-pin `undici "6.19.7"`
  (`@firebase/app-compat`, `@firebase/auth`, `@firebase/data-connect`,
  `@firebase/functions`, `@firebase/storage`). The reviewed overlay already
  force-resolved them to 6.29.0 via a Yarn `resolutions` entry (documented in
  `security-finalization-2026-10-14`); the single lock key
  `undici@6.19.7, undici@6.29.0` served every consumer. undici is the
  Node-side Firebase HTTP transport; browser Firebase builds use the platform
  fetch/XHR adapter instead. It remains an installed, audited dependency, so
  the match had to be removed rather than waived.

## Remediation

Because every one of the seven findings has a published, semver-patch fixed
release in the same minor line, the correct control is an actual upgrade — not
a disposition label. The HRMS frontend `resolutions` block now pins:

```json
"fast-uri": "3.1.9",
"serialize-javascript": "7.1.3",
"undici": "6.29.1"
```

The lockfile was regenerated with the exact pinned CLI recorded in the
manifest, **Yarn 1.22.22**, against `https://registry.npmjs.org`. The resulting
`yarn.lock` diff is exactly three resolution blocks and nothing else:

- `fast-uri@3.1.9, fast-uri@^3.0.1:` → 3.1.9
- `serialize-javascript@7.1.3, serialize-javascript@^7.0.3:` → 7.1.3
- `undici@6.19.7, undici@6.29.1:` → 6.29.1

Registry metadata confirms all three patched releases keep **identical
dependency sets and engine constraints** to their predecessors (each has zero
runtime dependencies; undici still requires node `>=18.17`,
serialize-javascript node `>=20.0.0`), which is why no other graph entry
moved. New tarball integrity hashes are published in the lockfile and were
validated by successful frozen installs (Yarn verifies `integrity` on every
extract). The overlay manifest
(`tools/foundation/hrms-locks/manifest.json`) records the new
`security_sha256` of both reviewed files; the upstream hashes are untouched
(upstream commit `a4768b441cff346def505e27f2a2229ee1e05b9b` is unchanged).

No `delta-dispositions.json` entry was added and the immutable 2026-09-23
register was not edited: the patched versions no longer match any of the seven
advisories, so there is no residual finding to disposition. This follows the
same convention as the markdown-it 14.3.3 remediation
(`test_advisory_delta_2026_10_22.py::test_markdown_it_is_fixed_not_dispositioned_here`).
No scanner warning was suppressed and no gate was weakened.

## Verification (all reproduced in this workstream)

1. **Real frozen install.** A clean directory containing only the reviewed
   `package.json` + `yarn.lock` completes
   `yarn install --frozen-lockfile --non-interactive` (Yarn 1.22.22, Node
   22.22.3) and installs exactly fast-uri 3.1.9, serialize-javascript 7.1.3
   and undici 6.29.1, each as a single copy with no nested duplicate.
2. **Live npm advisory gate, before/after.** The repository's own
   `audit_frontend.inventory` + npm bulk endpoint + `advisory_triage` pipeline
   was run against real installed trees. Baseline (vulnerable lock): the exact
   seven untriaged IDs from the CI failure, `open=7, untriaged=7`, status
   fail. Patched lock: the seven IDs are absent, **zero new advisory findings
   are introduced**, `closed=12, accepted=2, open=0, untriaged=0`, overall
   status **pass**. Captured in `before-after-audit.json` and
   `patched-tree-audit.json` (the latter retains the full 682-name installed
   inventory and raw npm response). The 14 residual matches are all
   pre-existing records already closed by the register/deltas or held as
   documented owner-accepted risks (showdown, @tiptap/core).
3. **Runtime behavior of the patched packages.**
   - `fast-uri` 3.1.9 parse/resolve round-trips succeed.
   - `serialize-javascript` 7.1.3 serializes functions and emits no raw
     `</script` terminator for a hostile function body (the GHSA-m5mm-p8h7-m29v
     regression surface).
   - `undici` 6.29.1 completes a real HTTP request round-trip against a local
     Node http server (200 + JSON body); `request` and `EventSource` exports
     resolve.
4. **Frontend compilation.** A Vite production build using the patched
   installed toolchain (vite 5.4.x from the same lock) transforms 177 modules
   and emits bundled assets successfully. The only diagnostic is the
   pre-existing browser-externalization notice for undici's Node `node:buffer`
   import, expected because undici is a server-only Firebase transport.
5. **Repository contracts.** `tests/security/test_security_locks.py` passes
   against the new manifest hashes (LF-only, v1 lock header, all `resolved`
   URLs on registry.npmjs.org, drift preflight intact), and the new
   `tests/security/test_npm_advisory_pins_2026_10_24.py` regression locks the
   pins, lock entries, affected-range exclusion and manifest evidence.

## Scope boundary and remaining blockers

- This evidence closes only the seven npm findings assigned to the JavaScript
  workstream (Issue #41). It does not close Issue #38, which also contains the
  Python `filelock`/`setuptools` matches handled by the separate Python
  workstream, and it grants no production release authorization.
- The Foundation full-stack audit, authenticated Chromium role desks, Native
  lifecycle, Product image and Windows packaging must rerun on the merged
  release revision; the local evidence here reproduces the dependency-audit
  portion and the build/runtime behavior of the three changed packages, not
  the entire hosted appliance.
- If upstream HRMS later moves its own pins, re-run the same overlay process;
  if a production process ever starts the Vite dev/preview server, re-triage
  the separate DEV_ONLY Vite/launch-editor records — none of those processes
  are started by the shipped appliance.

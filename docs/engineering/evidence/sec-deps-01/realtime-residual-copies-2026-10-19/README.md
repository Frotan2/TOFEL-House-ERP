# Realtime residual copies: Education and banking frontend locks (2026-10-19)

Scope: the residual vulnerable copies that remained after the Socket.IO root overlay
(`tools/foundation/realtime-locks`, commit `7e0f191`). The root overlay pins the Frappe realtime server.
The Education and banking frontend locks still carried older `ws` and `socket.io-parser` versions.

## Advisory data (GitHub Advisory Database, `api.github.com/advisories/...`, checked 2026-10-19)

| Advisory | Package | Vulnerable range | First patched |
|---|---|---|---|
| GHSA-3h5v-q93c-6h6q (high) | ws | >= 8.0.0, < 8.17.1 | 8.17.1 |
| GHSA-96hv-2xvq-fx4p (high) | ws | >= 8.0.0, < 8.21.0 | 8.21.0 |
| GHSA-58qx-3vcg-4xpx (medium) | ws | >= 8.0.0, < 8.20.1 | 8.20.1 |
| GHSA-2m8v-j782-fhvr (high) | socket.io-parser | >= 4.0.0, < 4.2.7 | 4.2.7 |
| GHSA-677m-j7p3-52f9 (high) | socket.io-parser | >= 4.0.0, < 4.2.6 | 4.2.6 |
| GHSA-gr94-w7qr-f4j3 (high) | engine.io | >= 6.5.0, < 6.6.7 | 6.6.7 |
| GHSA-r635-g3xr-vw7x (high) | engine.io | >= 4.1.0, < 6.6.7 | 6.6.7 |

The pins used here are at or above every first-patched version:
`ws` 8.21.3 (>= 8.21.0), `socket.io-parser` 4.2.7 (>= 4.2.7). `engine.io` 6.6.11 and `socket.io` 4.8.4 are the root overlay pins.

## Changes

- `tools/foundation/education-locks/frontend`: `resolutions` add `socket.io-parser` 4.2.7 and `ws` 8.21.3.
  Lock regenerated with Yarn 1.22.22 against `registry.npmjs.org`. Diff: `socket.io-parser` 4.2.4 to 4.2.7
  (`debug` ~4.4.1 added for it), `ws` 8.11.0 to 8.21.3. Manifest hashes refreshed.
- `tools/foundation/banking-locks/banking`: `resolutions` add `ws` 8.21.3. The lock diff is one `ws` entry.
  Manifest hashes refreshed. This is the first change to the banking `package.json` (it was byte-identical to upstream).
- Tests: `test_socket_io_parser_and_ws_are_pinned_to_patched_versions` (Education), `test_banking_ws_is_pinned_to_patched_version`.

## Reachability (source reasoning, to be confirmed by the Foundation audit)

- `ws` in the Education lock is reached only through `engine.io-client`'s Node transport. The browser bundle uses the
  browser transport, so the copy is not in browser code. It is still shipped in the frontend tree and is pinned here so that
  the audit no longer matches and the copy is not a future trap.
- `socket.io-parser` 4.2.4 in the Education lock sits in the browser bundle path through `socket.io-client`.
- The banking `ws` 8.17.1 copy is the same kind of residual. It is not on the server request path.

## Not claimed

- This is a lock-level override. It is not an upstream vendor patch.
- Compatibility of socket.io-client with socket.io-parser 4.2.7 and ws 8.21.3 is a semver-minor/patch change inside the
  same major lines. It is verified only by the Foundation runtime install and audits (the authoritative gate for this change).
- Polling, WebSocket upgrade, reconnect, and authentication through the deployed route (Tailscale Serve, port 9000) are
  not verified by this change. They are a separate live-route item.

## Foundation result on the head with these changes (`0adf145`)

- Foundation runtime run `39290652924`: **failure** (20m35s). The failing steps were the two restricted-policy
  advisory audits, `hosted-frontend-advisory-audit` and `hosted-full-stack-dependency-audit` (both exit 1). The run's last failed
  check was `hosted-frontend-advisory-audit`.
- The advisory header reports `advisory matches=148 in 40 packages`. The visible match list has no `ws`, `socket.io`,
  `socket.io-parser` or `engine.io` entries. The earlier `9754578` header reported `161 matches / 46 packages`. This note does not
  claim that the drop is caused by this change: the full artifact that would show the diff is not downloadable from the sandbox.
- The failure is not new. Foundation has failed on every head of this branch (`882ec90`, `8742b52`, `3eaf6a6`, `507e5e5`,
  `94107b7`, `0adf145`). Visible causes include open or untriaged findings in npm dev tooling (vite, esbuild, rollup, postcss,
  svgo, lodash, minimatch, nanoid and others), Python packages (pyjwt, pypdf, weasyprint, werkzeug, setuptools, oauthlib, pdfkit)
  and `@tiptap/core` GHSA-cp6q-959q-f8rh and `showdown` GHSA-rmmh-p597-ppvv.
- `advisory_triage.overall_status` returns `fail` on any untriaged or open finding. The owner's accepted risks
  (`OD-2026-10-19-A` showdown, not accepted as worded; `OD-2026-10-19-B` @tiptap/core) are still open register records, so
  the gate cannot pass until those are reviewed. This round did not weaken the gate.
- Status: the realtime/socket residual is closed at the lock level. The Foundation gate is **not** passing.

## Native gate regression found and fixed (`4d9c877`)

- Native lifecycle run `39290653297` on `0adf145` **failed** at `Native lifecycle checks on a real site`. Cause: `tools/native/run_native.py`
  asserted that the upstream ERPNext tree differs from upstream only in `banking/yarn.lock`. The banking overlay now also changes
  `banking/package.json` (the `ws` resolution), so the exact-set assertion failed. The log is not downloadable from the sandbox; the cause is
  established by reading the assertion and by reproducing the overlay locally (below).
- Fix: the expected set is now `['banking/package.json', 'banking/yarn.lock']`, which matches the reviewed manifest. The assertion stays exact.
  `secure_hrms --banking --verify` still hash-checks both files. Test `test_native_expected_banking_changes_match_reviewed_manifest` ties the two.
- Local reproduction: the real `secure_hrms.security_lock_files(..., banking=True)` on the upstream ERPNext `banking/` files at commit
  `4048fb70` (`package.json` and `yarn.lock` hashes match `upstream_sha256`). `yarn install --frozen-lockfile` passed, `verify_only` passed, and
  `git diff --name-only` was exactly the two files. The installed `ws` is 8.21.3.
- Native lifecycle run `39293858728` on `4d9c877`: **success** (native in 8m31s).
- Foundation run `39293708477` on `95394c2` (the `tools/foundation` and evidence inputs of the final head are identical to `4d9c877`):
  **failure**, same as before. `advisory matches=148 in 40 packages`. Failing checks: `hosted-frontend-advisory-audit` and
  `hosted-full-stack-dependency-audit`. The Foundation gate remains the blocker.

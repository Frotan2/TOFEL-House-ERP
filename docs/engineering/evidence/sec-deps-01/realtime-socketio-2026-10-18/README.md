# Socket.IO realtime server: dependency remediation (2026-10-18)

Status: **locally verified; hosted verification pending on the final SHA.** Release is still **NO-GO** until the gates in the owner package pass on the final SHA.

## 1. What was wrong

The Frappe realtime server (`realtime/index.js`, started by `apps/frappe/socketio.js`) is network-facing. It is reached through `/socket.io` on the central PC. The pinned Frappe root lockfile (v16.33.1, `988e54f3`) resolves:

| Package | Pinned by Frappe lock | Affected by |
|---|---|---|
| `ws` | 8.11.0 | GHSA-3h5v-q93c-6h6q, GHSA-96hv-2xvq-fx4p, GHSA-58qx-3vcg-4xpx |
| `engine.io` | 6.5.4 | GHSA-gr94-w7qr-f4j3, GHSA-r635-g3xr-vw7x |
| `socket.io-parser` | 4.2.4 | GHSA-2m8v-j782-fhvr, GHSA-677m-j7p3-52f9 |

All seven advisories were confirmed against the GitHub advisory API. Each pinned version falls inside the vulnerable range.

## 2. Correction to the earlier disposition basis

The 2026-09-23 register (`per-finding-remediation-analysis-2026-09-23.json`) records these seven advisories as MITIGATED or NOT_REACHABLE. The stated mitigations were:

- "nginx edge with 4k/1m caps" (ws GHSA-3h5v, GHSA-96hv; socket.io-parser; engine.io GHSA-r635: "nginx returns 400 for octet-stream POSTs").
- "WebTransport transport not enabled" (engine.io GHSA-gr94); "engine.io/socket.io never call ws.close(TypedArray)" (ws GHSA-58qx).

**The nginx-based mitigations do not hold for the product deployment.** Checked on this commit:

- `product/docker-compose.yml` publishes `socketio` directly as `127.0.0.1:9000:9000`. There is no nginx service.
- `docs/engineering/LAUNCH-RUNBOOK.md` (line ~271) and `product/windows/VALIDATION.md` route `/socket.io` with `tailscale serve --bg --set-path=/socket.io 9000`. Tailscale Serve has no body or header caps.
- `grep -rln nginx product/` returns nothing. nginx appears only in the Foundation/CI runtime harness (`tools/foundation/runtime_install.py`), which is not the owner's deployment.

The in-application cap is engine.io's default `maxHttpBufferSize` (1 MB). `realtime/index.js` sets only `cors` and does not override it. That cap is real in the product, but it does not address the advisory classes above (per-fragment, header-count, and transport-level DoS). The MITIGATED records are therefore not valid for the product, and this remediation replaces them with version-based resolution.

## 3. Remediation (owner decision 2026-10-18: "adopt realtime only")

Overlay: `tools/foundation/realtime-locks/` (`manifest.json`, `package.json`, `yarn.lock`), applied by `tools/foundation/secure_realtime.py`.

- `socket.io` `^4.7.1` becomes `^4.8.4`.
- `resolutions` pins `engine.io` 6.6.11, `ws` 8.21.3 and `socket.io-parser` 4.2.7. These are at or above the fixed minimums in the advisories.
- Input digests are verified before any write. The upstream blob IDs match the pinned commit (`package.json` 5a2031d0, `yarn.lock` 08976ca4). Any other input is refused.
- After a frozen install, every installed copy of `engine.io`, `ws` and `socket.io-parser` under the Frappe root must be at or above its minimum. Vendored fixtures inside other packages are excluded.

Wiring:

- `product/app.Dockerfile`: copies the script and overlay, then runs `secure_realtime.py /home/frappe/bench/apps/frappe` after `bench get-app` and the weasyprint/HRMS guards.
- `tools/foundation/runtime_install.py`: applies the overlay after the upstream source-hash guard and before `asset-build`, and verifies it again after the build.
- `.dockerignore`, `.github/workflows/native-lifecycle.yml` and `.github/workflows/product-image.yml`: allowlist and trigger paths updated.
- `tests/foundation/test_product_packaging.py`: the reviewed Dockerfile COPY-source list gained the two new sources.

The Education TipTap overlay (GHSA-VHRC) is **not** changed by this commit. The owner chose to decide that separately.

## 4. Local verification (this sandbox, 2026-10-18)

| Check | Result | Artifact |
|---|---|---|
| Upstream digests match pinned Frappe blobs | `git hash-object` = GitHub blob IDs | §3 |
| Frozen install of the exact overlay files (Yarn 1.22.22, host rewritten to npmjs for the sandbox only) | `Done`; resolved `socket.io` 4.8.4, `engine.io` 6.6.11, `ws` 8.21.3, `socket.io-parser` 4.2.7, `socket.io-client` 4.7.2 | run log only |
| Advisory bulk API, baseline versions | 7 advisories returned (ws 3, engine.io 2, socket.io-parser 2): the check detects the problem | `bulk-advisory-before-after.json` |
| Advisory bulk API, overlay versions | **0 advisories** | `bulk-advisory-before-after.json` |
| Live Socket.IO smoke (4.8.4 server, Frappe-pinned 4.7.2 client) | polling and websocket connect; echo round-trip; 1.5 MB payload refused by engine.io's cap | `realtime-smoke.js`, `bulk-advisory-before-after.json` |
| Negative control on the upstream lock | the vulnerable entries (`engine.io 6.5.4`, `socket.io-parser 4.2.4`, `ws 8.11.0`) are detected | run output |
| Regression tests | `tests/security/test_realtime_locks_2026_10_18.py`: 17 tests OK | suite |
| Packaging guard | `tests/foundation/test_product_packaging.py` OK after the allowlist update | suite |
| Full suite | **1433 tests OK** (with `/tmp/venv`, which has the bs4 dependency) | suite |
| Ruff | clean | |

Lockfile change scope: `git diff` of the overlay lock against the upstream lock touches the realtime family only (socket.io, engine.io, ws, socket.io-parser, and the transitive pins they need: cookie 0.7.2, debug 4.4.3, ms 2.1.3, base64id removed, @types/ws 8.18.2 added). Nothing else in the 3,349-line lock moved.

## 5. Hosted verification on `7e0f1915` (2026-10-18)

| Workflow | Run | Result |
|---|---|---|
| Owned suite (push) | `39106323689` | success |
| Owned suite (pull_request) | `39106326151` | success |
| Product image (`image` job, incl. Build application image, first boot, browser UI, tailnet contract, upgrade/rollback) | `39106323661` | success |
| Foundation runtime (`runtime` job; runs `runtime_install.py`, which applies the overlay before `asset-build` and verifies it after) | `39106323632` | success |
| Native lifecycle (real-site checks) | `39106323646` | success |

Foundation annotations on this SHA: 158 advisory matches in 44 packages (previously 161 in 46). The `ws` 8.11.0 and `engine.io` root entries no longer appear. The remaining `socket.io-parser` and `ws` entries are in the frontend trees listed in §6 (`browser-self-denial-review-2026-10-18/README.md` §2).

## 6. Not verified here (must be verified before any GO)

1. **Owner live test over Tailscale Serve** (`product/windows/VALIDATION.md` Evidence 13): WebSocket handshake HTTP 101 from an authorized staff PC, and a realtime desk update arriving without a refresh. Not run here. The hosted tailnet contract passed in CI, but CI does not run Tailscale Serve (per `VALIDATION.md`).
2. **Frontend bundle output.** The Frappe frontend resolves `socket.io-client` 4.7.2 with `socket.io-parser` 4.2.7 through the same resolution. No bundle was inspected.

## 7. Residual copies found in this review (not fixed by this change)

These are separate trees that the Frappe root overlay does not touch. Each needs an owner decision (see `browser-self-denial-review-2026-10-18/README.md` §3):

- **Education frontend** (`tools/foundation/education-locks/frontend/yarn.lock`): `socket.io-parser` 4.2.4 via `socket.io-client`. **This copy is in the Education browser bundle.** GHSA-2m8v and GHSA-677m apply to it. The realtime server fix does not cover it.
- **Education frontend:** `ws` 8.11.0 via `engine.io-client` (Node transport only; `browser` field excludes it from browser bundles, checked on npm for engine.io-client 6.5.1 and 6.5.3).
- **Banking frontend** (`tools/foundation/banking-locks/banking/yarn.lock`): `ws` 8.17.1 via `engine.io-client` (same Node-only reach). Its `socket.io-parser` is already 4.2.7.
- The earlier MITIGATED basis (nginx caps) is **not** valid for these client-side copies, because no nginx sits in front of a browser bundle.

## 8. Residuals and follow-ups

- The register is immutable evidence. The seven IDs keep their 2026-09-23 dispositions. The triage gate (`tools/foundation/advisory_triage.py`) does not check installed versions, so it will keep counting them as closed. The version-based fix is the real remediation, but the gate does not prove it. A follow-up should make the gate fail when a MITIGATED record's package version is below the fixed minimum. That is a strengthening, not a policy relaxation, and needs review before it is merged.
- The earlier MITIGATED basis (nginx caps) is withdrawn for the product topology. It is still correct for the Foundation/CI runtime, which does run nginx.
- `engine.io` 6.6.11 and `ws` 8.21.3 are the latest patch lines at the time of this review. A later advisory on those lines needs a new delta record.

## 9. Reproduce

```bash
# upstream verification (needs GitHub API access)
curl -s -H "Accept: application/vnd.github.raw" \
  "https://api.github.com/repos/frappe/frappe/contents/yarn.lock?ref=988e54f3" | git hash-object --stdin
# expect 08976ca46996e63c655f7a210aca7f7ad3fdc620

# unit and wiring tests
python3 -m unittest tests.security.test_realtime_locks_2026_10_18 tests.foundation.test_product_packaging -v

# advisory before/after and smoke (needs npm registry + node)
# Run realtime-smoke.js from a directory whose node_modules came from the overlay lock
# (socket.io 4.8.4, socket.io-client 4.7.2), e.g. after a frozen install of
# tools/foundation/realtime-locks/. Output is JSON on stdout.
cp docs/engineering/evidence/sec-deps-01/realtime-socketio-2026-10-18/realtime-smoke.js <overlay-install-dir>/
node <overlay-install-dir>/realtime-smoke.js
```

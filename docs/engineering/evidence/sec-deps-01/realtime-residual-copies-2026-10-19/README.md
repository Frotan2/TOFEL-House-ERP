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

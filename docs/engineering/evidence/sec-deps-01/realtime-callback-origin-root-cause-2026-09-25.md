# `actual-realtime-authorization` root cause: unreachable realtime callback URL

Date: 2026-09-25 · Branch `arena/01a0cd90-tofel-house-erp`
Scope: the `actual-realtime-authorization` gate in
`.github/workflows/foundation-runtime.yml`, which had failed identically on
every attempt regardless of the changes made to
`apps/foundation_security/realtime/handlers.js`.

Classification: **FIXABLE** (defect in our own validation harness, not in
vendor code and not an unresolved policy question).

## Symptom

The gate reported only `actual-realtime-authorization: exit 1`. Artifact
download from the hosted runner repeatedly failed (signed blob URL EOF), so
the per-check report could not be read. Every guard-side hypothesis that was
tested — adapter wrapper shape, `socket.join` wrapping, room-name prefixes,
query-string escaping — changed nothing about the failure.

## Why the failure was invariant to guard changes

Frappe's realtime server derives **every** URL it calls back into the site
with from the socket's `Origin` header. Pinned commit
`988e54f3c4c291e2077a83809663f123731abe76`, `frappe/realtime/utils.js`:

```js
function get_url(socket, path) {
	if (!path) path = "";
	let url = socket.request.headers.origin;
	if (conf.developer_mode) { /* swap port to conf.webserver_port */ }
	return url + path;
}
```

`conf.developer_mode` is unset for this lab (it is only set on
`upstream-tests.localhost`, and `get_conf()` reads `config.json` +
`sites/common_site_config.json`, not per-site config).

The lab reverse proxy rewrote that header on the public 9000 edge:

```nginx
proxy_set_header Origin $scheme://$http_host;
```

The synthetic socket client connects as `Host: foundation.localhost`, so
`$http_host` is `foundation.localhost` **without a port**, and the forwarded
`Origin` became `http://foundation.localhost`. That resolves to
`127.0.0.1:80`, and this lab serves nothing on port 80 — the desk edge is
`127.0.0.1:8080`, the Socket.IO edge `127.0.0.1:9000`, gunicorn
`127.0.0.1:8000`.

Consequence chain:

1. `realtime/middlewares/authenticate.js` calls
   `socket.frappe_request("/api/method/frappe.realtime.get_user_info")` →
   `fetch("http://foundation.localhost/api/method/…")` → ECONNREFUSED.
2. The `.catch` arm runs `next(new Error("Unauthorized: …"))`.
3. The connection is rejected **before** `on_connection()` runs, so
   `socket.installed_apps` is never consulted and
   `apps/foundation_security/realtime/handlers.js` is never invoked.

That is why no change to the guard could move the needle: the guard was never
executing. It also explains why the adjacent gates stayed green —
`runtime_http.py` only asserts an Engine.IO **handshake** (HTTP 200 + `sid`),
which node answers without any callback, and `realtime_exposure_probe.js`
exercises pre-auth advisory shapes where a rejected connection is the
expected outcome.

Secondary variable eliminated in the same change: `foundation.localhost` was
not guaranteed to resolve at all. `runtime_http.py` reaches the site as
`http://127.0.0.1:8000` with a `Host:` header and therefore never exercises
name resolution; only the realtime path does.

## Fix

1. **Pin the edge port on the forwarded Origin** (`build_proxy_conf`):

   ```nginx
   proxy_set_header Origin $scheme://$host:8080;
   ```

   `$host` is portless and `$foundation_site` has already returned `444` for
   any unknown host, so the value is derived entirely from server state. No
   client input reaches the routing decision, and the deliberate "overwrite
   client routing headers rather than trust them" posture is unchanged. The
   `Host` header forwarded to node stays `$host`, and
   `X-Frappe-Site-Name $foundation_site` continues to be what actually
   selects the site (`frappe/app.py` prefers that header over the Host
   header), so a port in `Host` cannot influence site routing either.

2. **Add `/etc/hosts` entries** for `foundation.localhost`,
   `restore.localhost`, `recovery.localhost` and `upstream-tests.localhost`,
   so the callback host resolves the way a real deployment's DNS would
   instead of depending on the runner's resolver.

3. **Diagnostic reachability.** Because artifact retrieval is unreliable,
   `surface_gate_failure()` now echoes the failed gate's result JSON,
   captured stdout, the realtime boot log and the socket.io log tails to the
   job log. `handlers.js` writes its diagnostics to **stdout** as well as
   `FOUNDATION_REALTIME_BOOT_LOG` (stdout lands in `socketio-secured.txt`),
   recording `installed_apps`, the room set on attach and after each join.
   `runtime_realtime.mjs` records every inbound event name so a failure
   message distinguishes "nothing was delivered" from "the guard filtered it".

## Validation

* `tests/foundation/test_runtime_proxy_conf.py` (new, 7 cases) pins the
  invariant on the generated configuration: the 9000 block pins
  `$scheme://$host:8080`, `$http_origin` never appears, both blocks set
  `X-Frappe-Site-Name $foundation_site` and the `444` host whitelist, both
  upstreams match the pinned lab ports, braces balance, and a local copy of
  frappe's `get_hostname()` is used to reproduce the
  `get_hostname(host) == get_hostname(origin)` guard from `authenticate.js`
  against the forwarded values.
* Negative control: the same assertions **fail** against the pre-fix
  configuration (`proxy_set_header Origin $scheme://$http_host;`), so the
  test is not vacuous.
* `handlers.js` also now falls back to its loopback `authorizeRequest()`
  (127.0.0.1:8000 with the sid cookie plus `X-Frappe-Site-Name`) **only**
  when `socket.frappe_request` could not reach the site at all (threw, or
  returned status 0) — never when the endpoint returned a real authorization
  decision, so a 403 cannot be laundered into a success.

## Status of the gate

Not yet re-run. The GitHub connection for this session returned
`HTTP 401 Bad credentials` before the fix could be pushed, so hosted
validation of this hypothesis is **pending**. Local validation is complete:
1376 Python tests pass (up from 1369, +7 new) and all four Node suites pass.

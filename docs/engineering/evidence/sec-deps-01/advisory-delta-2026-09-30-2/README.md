# Advisory delta 2026-09-30 (part 2) — PyJWT batch + brace-expansion + moment

Hosted foundation-runtime run `36668343658` (commit `4362fb2`) correctly
failed closed: `hosted-full-stack-dependency-audit: exit 1` and
`hosted-frontend-advisory-audit: exit 1` surfaced **13 advisories** published
to the GitHub Advisory Database on **2026-09-29** (after the part-1 delta was
authored the same day) that match pinned versions:

- `py:pyjwt@2.13.0` — 9 advisories (a coordinated batch; repository
  advisories dated 2026-09-11, published to the GH Advisory DB 2026-09-29;
  the audit annotation feed had not yet populated severities for them,
  shown as `(?)`; reviewed severities recorded in the JSON)
- `npm:brace-expansion@1.1.11,2.0.1` — 3 advisories (2 high, 1 moderate)
- `npm:moment@2.29.4` — 1 advisory (moderate)

Parsed from the run's own check-run annotations: **115 finding rows**; once
the mis-annotation attribution is corrected, exactly these 13 ids were
uncovered; all 13 rows below close as NOT_REACHABLE with pinned-tree
evidence. The gate behaved as designed (fail closed on unknown advisories).

---

## 1. PyJWT batch (`pyjwt@2.13.0`) — reachability trace

Pinned `frappe@988e54f3c4c291e2077a83809663f123731abe76` was searched
repository-wide. Complete JWT surface:

| Call site | Call | Input | Allow-list | Key material |
|---|---|---|---|---|
| `frappe/oauth.py:324` | `jwt.encode` (own id_token issuance) | server-generated | n/a | client_secret |
| `frappe/oauth.py:446-454` | `jwt.decode(id_token_hint, …)` inside `validate_user_match` | client-supplied `id_token_hint` on the authorize path | `["HS256"]` single-alg; `verify_signature: False` | none (unverified parse) |
| `frappe/oauth.py:467-475` | `jwt.decode(id_token_hint, key=client_secret, audience=client_id, …)` | same hint, after profile lookup | `["HS256"]` single-alg | opaque per-client HMAC `client_secret` from the DB (`oauth.py:453-458`) |
| `frappe/utils/oauth.py:200` | `jwt.decode(token, flow.client_secret, options={"verify_signature": False})` | IdP token-endpoint response body (server-to-server TLS) | none (verification off) | client_secret (unused) |

Also verified repository-wide:

- **Zero** `PyJWK`, `PyJWKSet`, `PyJWKSClient`, `jwks_client` imports or
  instantiations (three independent greps). `jwks_uri` exists only as a
  Social Login Key **type hint**, never bound
  (`frappe/integrations/utils.py:45-46`) — the identical fact recorded for
  the accepted 2026-09-29 delta (`GHSA-w6j9-cwv2-h6wq`).
- `algorithms=` grep across `frappe/`: only `["HS256"]` (446, 471) plus the
  test suite. **No mixed HMAC+asymmetric allow-list exists anywhere.**
- Both `oauth.py` decode calls sit inside
  `try: … except Exception: return False` (`frappe/oauth.py:477-478`).
- OAuth bearer tokens are opaque random strings stored as
  `OAuth Bearer Token` documents — never JWTs, never raw-token-indexed.

### Family verdicts

- **JWKS-client dependent** (`GHSA-2gx3` unknown-kid fetch amplification,
  `GHSA-9v7f` redirect-following fetch, `GHSA-9j54` empty `oct` HMAC JWK):
  the attacked classes are absent tree-wide → **NOT_REACHABLE**.
- **Mixed-allow-list + asymmetric-key-as-HMAC family** (`GHSA-ffc3`
  PEM-mutation, `GHSA-p4g4` DER, `GHSA-r6x4` BOM-JWK, `GHSA-w2cx` JWK
  containers): each advisory states the compound precondition explicitly
  (mixed allow-list + raw public key passed as `key=`); the advisory's own
  control cases show a single-alg allow-list rejects. Pinned tree has
  single `["HS256"]` allow-lists only and only ever passes opaque
  `client_secret` HMAC strings → **NOT_REACHABLE**.
- **Raw-token revocation composition** (`GHSA-hxm8`): needs the application
  to index revocation state by the raw serialized token; frappe bearer
  tokens are opaque non-JWT rows → **NOT_REACHABLE**.
- **Pre-signature recursion** (`GHSA-8wjv`): the only request-driven decode
  is wrapped by `except Exception`, converting the uncaught-500/traceback
  effect into a clean `False`; the advisory itself notes ~266 KB tokens
  exceed HTTP field limits (rejected 431 before any decode); the other
  decode input is the IdP's own response, not client bytes. Residue,
  recorded honestly: a nested-header attempt costs bounded parse time
  (~6 ms class) inside the `try` before being caught — no 500, no
  traceback, no worker state change → **NOT_REACHABLE**.

Fix path for all nine: official Frappe release carrying PyJWT ≥ 2.14.0 —
EXTERNAL/UPSTREAM BLOCKED, unchanged. Production REJECT posture unchanged.

## 2. `brace-expansion@1.1.11/2.0.1` — reachability trace

All three advisories need an **untrusted string reaching
`expand()`/`minimatch` in an executed Node process** (availability-only
advisories even in their own domain).

Executed Node surface in the pinned stack (frappe realtime/socketio server,
`socketio.js` → `realtime/`): requires exactly `socket.io`, `node:http`,
`fs`, `path`, `../node_utils`, `./middlewares/authenticate`, `./utils`,
`cookie`, `@redis/client`, `dns` (require inventory of
`realtime/index.js`, `realtime/middlewares/authenticate.js`,
`realtime/utils.js`, `node_utils.js`). **Zero** glob/minimatch/
brace-expansion imports in any executed file.

Dependency owners (lockfile-traced) are **build/lint tooling only**:

- `frappe/yarn.lock`: `stylus@^0.54.5 → glob@^7.1.6 → minimatch@^3.1.1 →
  brace-expansion@^1.1.7`
- `education@93bc7075 frontend/yarn.lock`: `sucrase@^3.32.0 → glob@^10.3.10
  → minimatch@^9.0.1 → brace-expansion@^2.0.1`
- `hrms@a4768b44 frontend/yarn.lock`: `rimraf`, `sucrase`, `workbox-build`,
  `eslint`, `jake`, `filelist` → minimatch/glob chains

All run exclusively on the builder's machine against tool-internal patterns;
no endpoint, worker, scheduler, or realtime path ever passes user input to
pattern expansion → **NOT_REACHABLE**.

## 3. `moment@2.29.4` — reachability trace

`GHSA-4p3w-j4w9-5jqw` (path traversal via non-string `moment.locale()`
input) is **explicitly server-side-npm-only** per the advisory. Pinned
frappe: moment ships only in the client-side desk bundle
(`package.json` dependency + vendored
`frappe/public/js/lib/moment.js`); the executed Node realtime server
requires no moment at all (inventory above). Browsers lack the
require/fs semantics this traversal needs, and desk locale selection passes
string language identifiers → **NOT_REACHABLE**. Fix path: official Frappe
frontend refresh carrying moment ≥ 2.31.0 — EXTERNAL/UPSTREAM BLOCKED
posture unchanged.

## Verification performed in this workspace

- Pinned clones at exact matrix commits (`frappe@988e54f3`,
  `education@93bc7075`, `hrms@a4768b44`) checked out and searched
  (JWT surface table, JWKS greps, allow-list grep, node require inventory,
  reverse lockfile dependency tracing).
- All 13 advisory pages read from the GitHub Advisory Database (mechanism,
  preconditions, advisory-reported controls).
- Simulation: the fixed triage loader over this run's full annotation set
  (115 parsed rows) leaves **0 uncovered** once this delta is merged
  (13/115 uncovered before).

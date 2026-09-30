# Advisory delta 2026-09-30 (part 3): two PyJWT advisories

Foundation runtime run `36745670524` failed closed. The dependency audit found
119 advisory matches, up from 117 in run `36715665967` three hours earlier.
The two new matches are PyJWT advisories published to the GitHub Advisory
Database on 2026-09-30. They match pinned `pyjwt 2.13.0` (Frappe pins
`PyJWT~=2.13.0`).

The source was traced in the pinned trees `frappe@988e54f3`, `erpnext@4048fb70`,
`education@93bc7075`, `payments@cca07d9f` and `hrms@a4768b44`, the owned apps,
and PyJWT tag `2.13.0`. Only Frappe uses PyJWT:

| Call site | Call | Input | Key |
|---|---|---|---|
| `frappe/oauth.py:324` | `jwt.encode` | server-generated claims | OAuth Client `client_secret` |
| `frappe/oauth.py:446` | `jwt.decode(..., verify_signature=False)` | client-supplied `id_token_hint` | none |
| `frappe/oauth.py:467` | `jwt.decode(..., key=client_secret)` | same hint | OAuth Client `client_secret` |
| `frappe/utils/oauth.py:200` | `jwt.decode(..., verify_signature=False)` | IdP token-endpoint response (TLS) | admin-configured secret, unused |

Both `oauth.py` decodes sit inside `try: ... except Exception: return False`.

## GHSA-jwrc-g2q2-pq5p: ReDoS in `is_pem_format`. NOT_REACHABLE

`is_pem_format` has one caller, `HMACAlgorithm.prepare_key(key)`
(`jwt/algorithms.py:331`). It inspects the key, never the token. No key above
is attacker-supplied.

## GHSA-42vr-xj54-vc7v: RecursionError in pre-verification parse. MITIGATED

The attacker-reachable path exists: `oauth.py:446` decodes the client-supplied
hint without verifying it. PyJWT 2.13.0 catches only `ValueError` on both the
payload and header paths, so a deeply nested token raises `RecursionError`.
Frappe's `except Exception` catches it, and the request ends as a failed hint
match. No exception escapes and no worker dies. The IdP path requires a
hostile identity provider and at worst fails that one login. `PyJWKClient`
(the JWKS variant) is absent from every pinned tree.

The fix is an official Frappe release carrying PyJWT >= 2.15.0. That is
upstream-blocked, like the rest of SEC-DEPS-01.

# SEC-DEPS-01 — advisory feed delta, 2026-09-29 (oauthlib ×2, PyJWT ×1)

**Trigger:** hosted Foundation runtime validation `36615251941` (commit
`5d5f2ce`) failed closed at `hosted-full-stack-dependency-audit` —
`triage.untriaged` reported three brand-new Python OSV findings with
`modified` stamps of 2026-09-29. The gate behaved exactly as designed:
anything not covered by the immutable 2026-09-23 register is a REGRESSION.

**Base register:** `per-finding-remediation-analysis-2026-09-23.json`
(immutable; not edited). This directory carries only the additive delta.

## The three advisories (GitHub Advisory Database, queried 2026-09-29)

| Advisory | Aliases | Package (pinned) | Range | Patched | Severity | Summary |
|---|---|---|---|---|---|---|
| GHSA-hj66-6f7g-4r5v | CVE-2026-49264 | oauthlib 3.3.1 | >= 0.6.1, <= 3.3.1 | 4.0.0 | MODERATE | Unsafe JSONP callback injection in RevocationEndpoint — arbitrary JavaScript response generation |
| GHSA-xpv3-w29h-x7cv | CVE-2026-49265 | oauthlib 3.3.1 | >= 3.0.0, < 4.0.0 | 4.0.0 | MODERATE | Timing attack in PKCE code_verifier comparison (CWE-208) |
| GHSA-w6j9-cwv2-h6wq | CVE-2026-102274 | PyJWT 2.13.0 | >= 2.9.0, <= 2.13.0 | 2.14.0 | MODERATE | Malformed RSA JWK aborts parsing of an entire JWK Set |

## Pinned-source reachability trace

Tree: `frappe@988e54f3c4c291e2077a83809663f123731abe76`
(= `foundation-version-matrix.json` commit; locally fetched `--depth 1` and
`rev-parse` verified, 2026-09-29). oauthlib appears in four frappe files;
PyJWT entry points enumerated by repository-wide search.

**GHSA-hj66-6f7g-4r5v — NOT_REACHABLE.**
`frappe/integrations/oauth2.py:189-202`: `revoke_token`
(`@frappe.whitelist(allow_guest=True, methods=["POST"])`) calls
`create_revocation_response(...)` and then **discards the response content** —
`frappe.local.response = frappe._dict({})` carrying only an
`http_status_code`. The arbitrary response body this advisory exploits is
never rendered to any client.

**GHSA-xpv3-w29h-x7cv — NOT_REACHABLE.**
The advisory's vulnerable function is oauthlib's PKCE `code_verifier`
verification. frappe never calls it: `frappe/oauth.py:87-89` stores the PKCE
challenge itself and `frappe/oauth.py:144-165` verifies it itself
(`hashlib.sha256(code_verifier)` + base64url compared with `==` against the
stored `code_challenge`). Residual honesty note (not this advisory): frappe's
own comparison is a plain string equality — a potential, separate timing
observation in upstream code; recorded here for the next upstream review
cycle, under the same Frappe-fix-path dependency.

**GHSA-w6j9-cwv2-h6wq — NOT_REACHABLE.**
The vulnerable path is `PyJWKSet` / JWKS parsing. The pinned tree has **no
import or instantiation of `PyJWKSet`/`PyJWKSClient` anywhere**; all jwt uses
are `encode`/`decode` with explicit keys (`frappe/oauth.py:304`, `:441`,
`:520`; `frappe/utils/oauth.py:179`). `jwks_uri` exists only as an unfilled
Social Login Key type hint (`frappe/integrations/utils.py:45`), and nothing in
the operator bootstrap, the product packaging layer, or the launch runbook
configures a JWKS-based social login.

## Delta mechanics (why this file exists)

`tools/foundation/advisory_triage.py` now merges dated
`advisory-delta-*/delta-dispositions.json` registers on top of the immutable
base. A delta may only add advisory ids/aliases; attempting to redefine an id
that any earlier source already covers raises immediately (no silent
re-triage). Tests: `tests/security/test_advisory_triage.py` (+ new delta
class section).

## Consequence

- The three 2026-09-29 advisories are dispositioned NOT_REACHABLE with the
  pinned-tree traces above → hosted gates regain full triage coverage.
- **SEC-DEPS-01's register-level posture is unchanged:** all three fixes
  require an official Frappe v16 release carrying oauthlib >= 4.0.0 / PyJWT
  >= 2.14.0; until then this stays EXTERNAL/UPSTREAM BLOCKED and production
  remains REJECT. No pin is overridden; the vendor tree is untouched.

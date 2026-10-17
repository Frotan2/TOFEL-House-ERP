# GHSA-VHRC-HGRQ-X75R: containment against the real pinned Frappe sanitizer (2026-10-16)

**Disposition: still BLOCKED.** This is a unit-level runtime check of the sanitizer, not the hosted runtime check that the register requires to reinstate the advisory.

## What was verified

- Frappe `sanitize_html` from `frappe/frappe@988e54f3` (pinned v16.33.1), vendored byte-for-byte at
  `tests/security/fixtures/frappe-988e54f3/html_utils.py`. SHA-256 is checked before the module loads.
  Only the `frappe` package is stubbed (`escape_html`, `as_unicode`, `is_image`), and none of them are on the sanitize path.
  nh3, bleach-allowlist and bs4 are the real libraries, hash-pinned in `tests/security/requirements-ci.txt`.
- Containment: `apps/foundation_security/foundation_security/html_containment.py`. It calls the sanitizer with
  `always_sanitize=True`, which is the flag that stops the `is_json` short-circuit.
- Test module: `tests/security/test_html_containment_real_sanitizer_2026_10_16.py` (16 tests).

## Result

- Defect confirmed on the real sanitizer: `REAL.sanitize_html('"<img src=x onerror=alert(1)>"')` returns the input unchanged.
  Without containment the payload reaches the DOM as an active `onerror`.
- With containment, the event handler and the `javascript:` scheme are removed (checked with a WHATWG-style effective-scheme parser, not a substring match), and a `<script>` in a JSON array is removed.
- Legitimate formatting survives: strong, em, u, lists, and an https link. Plain text is unchanged. Containment is idempotent. Non-JSON values are left to Frappe's own pass, which strips a plain `javascript:` href.
- Document level: a Text Editor child row and a parent body field are contained. Data fields and `ignore_xss_filter` fields are untouched.

## Mutation check (run, then restored, byte-equal)

| Mutant | Result |
|---|---|
| `always_sanitize=True` → `False` (short-circuit path returns) | exit 1; 4 failing tests (event handler, javascript scheme, script array, child row) |
| containment replaced by identity | exit 1; same 4 failing tests |

The file was restored and verified equal to the original.

## Findings from the first run (recorded so they are not repeated)

- My first payloads were not exploits: `json.dumps` escapes inner quotes, which makes the handler inert in raw HTML. The tests now assert that each payload is active in its raw form before any containment result counts.
- A quoted `href` inside a JSON-wrapped value carries literal backslashes in the raw value as well. This is not a containment effect.
- A JSON-wrapped quoted-HTML value is no longer valid JSON after containment, because nh3 keeps the wrapping quotes as text. This is cosmetic, applies only to values that are themselves quoted HTML, and is accepted.

## Not covered (remaining blockers for GHSA-VHRC)

- The hosted save path: a real Frappe bench with MariaDB and Redis. Not available in this sandbox.
- Reopen, import, and render through the actual HRMS editor and the browser.
- Effect of containment on the Text Editor fields listed in the advisory-delta README.

## Re-run

    /tmp/venv/bin/python -m unittest tests.security.test_html_containment_real_sanitizer_2026_10_16 -v

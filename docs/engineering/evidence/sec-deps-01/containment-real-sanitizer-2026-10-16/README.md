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

## Save-path order (verified in pinned Frappe, 2026-10-17)

Read from `frappe/frappe@988e54f3`:

- `frappe/model/document.py` `insert()` line 486 and `save()` line 594 call `run_before_save_methods()`, which runs the `validate` doc event (lines 1391 to 1414). Then `_validate()` runs at lines 487 and 597.
- `_validate()` (line 827) calls `_sanitize_content()` (line 837) for the parent and for each child (line 850), after the `validate` event.
- So the containment hook runs **before** Frappe's own sanitizer on every save and insert. The JSON short-circuit cannot skip it, because containment calls `sanitize_html(..., always_sanitize=True)` first.
- `frappe/model/base_document.py` `_sanitize_content()` (line 1307) uses the same skip rules that containment mirrors: `ignore_xss_filter`, `Data`, `Attach*`, `Barcode`, `Code`, and cancelled or non-`allow_on_submit` submitted documents. Containment is stricter on submitted documents, so it does not weaken Frappe's pass.
- The hook is wired as `doc_events["*"]["validate"]` (`apps/foundation_security/foundation_security/hooks.py`, line 12), so it applies to every doctype.

## Residual exposures (not closed by this record)

1. **Existing stored rows are not contained.** The hook runs only when a document is saved. A hostile value written before this hook was installed remains executable when it is reopened or rendered, until the row is re-saved. Nothing backfills it. Closing it means rewriting owner data, so it needs an owner decision and a bench run (see the owner package). A read-only check to run on a restored copy: find `tabDocField` rows of HTML fieldtypes (`Text Editor`, `Text`, `Small Text`, `Markdown Editor`) without `ignore_xss_filter`, then select rows in each table whose value starts with `"` and contains `<`.
2. **Writes that skip `validate` are not contained.** `db_set`, `db_update`, `frappe.db.set_value`, and raw SQL do not run document hooks. Frappe's own pass has the same gap. In this repository, product code writes no HTML fields through those paths (`apps/toefl_house/toefl_house/controllers.py` denies `db_set`/`db_update` on native types). The remaining call sites are tests and checks that write non-HTML fields. The gap is reachable only through Frappe's native administrative tools.

GHSA-VHRC-HGRQ-X75R stays **BLOCKED**. A hosted runtime check is still required, and residual 1 must be decided before any reinstatement.

## Fix path for the education lock (checked 2026-10-17; not applied)

The open entry is in the Frappe Education frontend lock at `frappe/education@93bc7075`, `frontend/yarn.lock`: `@tiptap/extension-link` resolves to **2.2.3**, inside the advisory's vulnerable range (`< 2.10.4`). The HRMS locks under `tools/foundation/hrms-locks/` resolve to 2.27.3 and are patched, so this entry is education-only.

- Patched version: `@tiptap/extension-link` 2.10.4 (GitHub advisory API). Its registry metadata declares peer dependencies `@tiptap/core ^2.7.0` and `@tiptap/pm ^2.7.0`.
- So the fix is not a single-package overlay. The education TipTap stack (`core`, `pm`, `extension-*`, `starter-kit`, `vue-3`) would have to move together from the 2.2.x line to 2.7 or later, and the editor would need a build and a regression pass.
- Not attempted in this round. The owner decides between (a) that coordinated upgrade with build and editor verification, or (b) accepting the server-side containment above, with residual 1 (existing rows) and residual 2 (`db_set`, `set_value`, raw SQL) recorded as accepted risk. GHSA-VHRC stays BLOCKED until one of these is decided and the hosted check passes.

# Showdown ReDoS: Desk markdown input cap (2026-10-19)

Advisory: GHSA-rmmh-p597-ppvv, showdown `<= 2.1.0`, `anchors` subparser nested regular expression (ReDoS), medium (CVSS 5.3), no patched version.
This is a denial-of-service advisory, not XSS. The Frappe sanitizer (`sanitize_markdown_html`) does not stop it.

Owner answer 2026-10-19 (`OD-2026-10-19-A`, re-confirmed in chat on 2026-10-20): "accept with a compensating control", where the control is an input cap before showdown.

## Scope

- Frappe core has exactly one showdown consumer at `988e54f3`: `frappe.markdown` in `frappe/public/js/frappe/utils/tools.js`.
  Evidence: GitHub code search `showdown repo:frappe/frappe` returned only that file plus `package.json` and `.eslintrc`.
- Education and HRMS have their own renderers and are not covered by this control. Education has no src file that imports showdown (33 files, `93bc7075`, per `OD-2026-10-19-A`).
- Not covered: the parser cost of input at or below the cap, and any other markdown path in apps that do not use `frappe.markdown`.

## Control

`tools/foundation/secure_markdown.py`: a hash-bound insertion before the single `return sanitize_markdown_html(frappe.md2html.makeHtml(txt));`.

- Input longer than 2000 characters is returned as escaped plain text (`textContent`), never parsed by showdown.
- Upstream `tools.js` sha256 `99a91f55dbdb537e3fa457fb41a83909f9f116b9a3cc8dd06b9109e14eb090e3`.
- Reviewed output sha256 `8f122bc9561836888790a5755afa10933434efae3e28ab2521ee5bbcc7f05cf7`.
- Apply is idempotent. `--verify` never writes. Any other content is refused.
- Tests: `tests/security/test_markdown_cap_2026_10_19.py`, 9 tests, including `node --check` of the patched file.

## Measurement (showdown 2.1.0, Node v22.22.3, single sandbox CPU, not a user device)

`bench.js` (first pass, input sizes to 36000 characters) and `bench2.js` (second pass, cap candidates):

| Shape (input) | 1000 ch | 1500 ch | 2000 ch | 2500 ch | 3000 ch | 4000 ch | larger (unbounded) |
|---|---|---|---|---|---|---|---|
| `[]( ` repeated | 41 ms | 71 ms | 202 ms | 331 ms | 644 ms | 1331 ms | 12000 ch: 35.8 s |
| `<a href="` repeated | 2 ms | 6 ms | 13 ms | 25 ms | 42 ms | 99 ms | 36000 ch: 70.4 s |
| `[` repeated | 4 ms | 8 ms | 12 ms | 19 ms | 26 ms | 51 ms | (linear) |

Choice: **2000 characters**. Worst observed shape is about 0.2 s at the cap, versus 35.8 s at 12000 characters. 1500 would be about 0.07 s; that was considered too restrictive for ordinary Desk text.

## Limits (say these plainly)

- A cap bounds the input the parser sees. It does not prove there is no superlinear payload below 2000 characters. The measured shapes are the ones tested; the advisory's exact published payload was not reproduced here.
- Above the cap, markdown formatting is not rendered. The text is shown as plain text. This is a visible behavior change for long Desk markdown.
- The cap is a control, not a vendor patch. showdown remains `<= 2.1.0`.
- The register record for `GHSA-rmmh-p597-ppvv` remains **BROWSER_SELF_DENIAL (open)** until a reviewed register change is approved by the owner. See below.

## Register change (proposed, not applied)

Owner decisions `OD-2026-10-18-A` and `OD-2026-10-19-C` say to keep the BROWSER_SELF_DENIAL records open and the register unchanged. Closing this record (to MITIGATED with the evidence above) would change a BROWSER_SELF_DENIAL record. That needs an explicit owner approval, so this change was not made.

Proposed: showdown `GHSA-rmmh-p597-ppvv` -> `MITIGATED`, evidence = this directory plus `secure_markdown.py` and its tests, after the Foundation Desk render run passes with the patch applied.

## Status

- Control implemented and tested locally. Foundation wiring and the Desk render run are in the same change set (see the commit that adds this file).
- Advisory disposition: still **open** until the owner approves the register change.

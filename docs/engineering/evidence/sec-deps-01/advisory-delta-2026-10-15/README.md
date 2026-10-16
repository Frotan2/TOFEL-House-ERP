# Advisory delta 2026-10-15

Actions, all recorded in `delta-dispositions.json`:

1. **Adds two undispositioned, withdrawn advisories** (review item 4):
   - GHSA-gv7w-rqvm-qjhr, esbuild, Deno-module binary integrity (withdrawn 2026-06-17). BUILD_ONLY.
   - GHSA-8p5q-j9m2-g8wr, lodash, CVE-2021-41720 (withdrawn 2021-10-01). BUILD_ONLY.
   Neither is returned by `https://registry.npmjs.org/-/npm/v1/security/advisories/bulk` for the
   installed versions (esbuild 0.21.5 and 0.14.54; lodash 4.17.21 and 4.18.1) on 2026-10-15.
2. **Withdraws GHSA-vhrc-hgrq-x75r** from BROWSER_SELF_DENIAL to BLOCKED (ERRATUM E6). See below.

## BROWSER_SELF_DENIAL review (review item 3)

Six register records use BROWSER_SELF_DENIAL. The table covers each one, with its path in the shipped trees.
Shipped trees: frappe-ui 0.1.105 (hrms) and 0.1.31 (education), taken from npm. Frappe 988e54f3.

| Record | Path in shipped trees | Actor and victim | Result |
|---|---|---|---|
| showdown ReDoS (GHSA-rmmh-p597-ppvv) | frappe-ui `markdownToHTML` runs only in the TextEditor paste handler, after `confirm()`. Frappe desk `frappe.markdown` runs on comment submit and on Markdown Editor preview. | The paster or commenter converts their own text. Frappe Markdown Editor fields (onboarding_step, package, package_release, web_page) can render another desk user's text, but only for trusted admins. | Keep BROWSER_SELF_DENIAL. The privileged-author cross-user DoS path is an owner acceptance item. |
| markdown-it / linkify-it ReDoS (GHSA-38c4-r59v-3vqw, GHSA-22p9-wv53-3rq4, GHSA-v245-v573-v5vm) | Reached only through `prosemirror-markdown`. No frappe-ui, HRMS, or education source imports it. Bundle inclusion is not proven. | No shipped path found. | Keep BROWSER_SELF_DENIAL. The evidence is weaker than stated. A bundle check is pending. |
| @tiptap/core mergeAttributes (GHSA-cp6q-959q-f8rh) | TipTap `setContent` receives HTML strings from stored values. Object-form JSON is not stored. | Requires an attacker-controlled attribute object, which string fields do not supply. | Keep BROWSER_SELF_DENIAL. It depends on the sanitizer and on no JSON-object ingestion. |
| @tiptap/extension-link XSS (GHSA-vhrc-hgrq-x75r) | Stored HTML rendered in other users' browsers, exposed through the `sanitize_html` is_json short-circuit. | An authenticated writer reaches another user's viewer, which is cross-user. | WITHDRAWN to BLOCKED (ERRATUM E6). |

Defect reproduction (pure Python):

    python3 -c "import json; v='\"<img src=x onerror=alert(1)>\"'; print(json.loads(v))"

prints the live markup. Frappe's is_json short-circuit returns the value unchanged.

## Containment for the withdrawn record

`apps/foundation_security/foundation_security/html_containment.py` runs on the `validate` doc event
for all doctypes. It re-sanitizes only HTML-capable values that are valid JSON and contain `<` or `>`.
The containment is unit-verified (`tests/security/test_html_containment_2026_10_15.py`). It has not
been run against a live bench, so runtime verification is pending. The gate stays red for GHSA-vhrc
until a hosted runtime check passes and a reinstatement is recorded.

## Review of the page-level innerHTML sink (2026-10-16)

The remaining review item was `apps/toefl_house/toefl_house/public/js/th_command_pages.js:564`. It is
the only `innerHTML` sink in the file. It rebuilds the skill `<select>` from `active_skills()` codes.

- **Input source:** `TH Skill` Active codes, returned to readers with an allowed role.
- **Escaping:** the code is interpolated only through `escapeText`, which escapes `&`, `<`, `>`, `"`, and `'`.
  It appears in both the `value` attribute and the label. `el.value` is used only for comparison.
- **Verdict:** no injection path with the current escape. The case is not self-denial. The disposition
  for this sink is "escaped, no finding". Nothing here depends on GHSA-vhrc.
- **Regression guard:** `tests/foundation/test_command_pages.cjs` runs the shipped `escapeText` against a hostile
  code, asserts the exact escaped output, asserts both interpolations are escaped, and fails if any
  new `innerHTML` sink appears. Mutation check: removing the quote escaping makes the test exit 1 (verified; file restored).

The six register records are covered by the table above. This round added the page-level sink review, which is not a register record. GHSA-vhrc remains BLOCKED. Its
containment is unit-verified only, so the withdrawal stays until a runtime containment check exists.

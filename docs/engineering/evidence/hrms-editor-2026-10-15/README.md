# HRMS editor security acceptance — 2026-10-15

**Status: lab-verified, and CI-verified on session head `d04eea7`** (Foundation
runtime run 38669251864, job 116208199819, step `built-hrms-editor-security` passed).
The first CI attempt (`b817bd3`, run 38667643650) failed at the `keyboard-formatting`
stage. Cause: Chromium 153 raced the Mod-b shortcut against the selection flush.
The harness now flushes two frames before the shortcut. The security assertions were not
changed. The GHSA-c8x8 HRMS release gate stays OPEN until the same step passes on the
exact final `main` SHA.

Scope: the **installed, built** HRMS `TextEditor` / `FormField` component
(frappe-ui 0.1.105 TextEditor, prosemirror-view, Markdown-paste path) at the
pinned source `frappe/hrms@a4768b441cff346def505e27f2a2229ee1e05b9b`. No mock
editor is used: the harness compiles the real `hrms/frontend/src/components/FormField.vue`
with vite and drives it in headless Chromium through Playwright.

## What was run (reproducible)

```
# 1. pinned source + the product's own frozen lockfile (registry host
#    rewritten only in the process environment; lockfile hashes untouched)
git clone https://github.com/frappe/hrms.git && git -C hrms checkout a4768b441cff346def505e27f2a2229ee1e05b9b
yarn config set registry https://registry.npmjs.org
(cd hrms/frontend && yarn install --frozen-lockfile --ignore-scripts)

# 2. negative control: unpatched tree
#    prosemirror-view 1.31.3 (verified), frappe-ui Markdown paste unpatched

# 3. product overlay (exact code the Foundation runtime runs before asset build)
python3 tools/foundation/secure_hrms.py hrms            # patch
python3 tools/foundation/secure_hrms.py hrms --verify   # verify
#    -> {"prosemirror-model": 2, "prosemirror-view": 2, "socket.io-parser": 2}

# 4. built-component harness (Chromium 131 from the npm package
#    @sparticuz/chromium, playwright-core 1.58.2 — the same Playwright
#    version the runtime pins; the CI runner uses its own Chromium)
node tools/foundation/hrms_editor_security.mjs hrms/frontend <playwright-core-dir> <chromium>
```

## Results

| Tree | Result | Evidence |
|---|---|---|
| Overlay-patched (prosemirror-view 1.42.3, markdown paste closed) | **PASS**, 3 consecutive runs | `{"status":"pass","payloads":9,"paths":["import","read-only rendering","paste","markdown paste","stored reload","read-only keyboard rejection"],"legitimateEditing":true,"keyboardFormatting":true}` |
| Unpatched original lock (prosemirror-view 1.31.3) | **FAIL** (control) | `actual: { executed: 0, scripts: 0, eventAttributes: 0, scriptLinks: 1 }` — a `javascript:` link survives the editor |
| Unpatched Markdown paste (frappe-ui 0.1.105 unpatched, prosemirror patched) | **FAIL** (control) | `actual: { executed: 1 ... }` on `<img src=x onerror=…>` pasted through Markdown — the pre-schema execution fixed by `secure_markdown_paste` |

The two controls show the harness detects the exact vulnerable behaviour; the
patched tree passes. The pre-existing 1.31.3 exposure is therefore
**reproduced**, and the current fix is **verified**, not assumed.

## Coverage against the requested categories

| Category | Covered by | Evidence |
|---|---|---|
| Hostile pasted HTML | ProseMirror `text/html` paste of 9 payloads | PASS patched / FAIL unpatched |
| Hostile imported HTML | `importHTML` of the same 9 payloads, editable and read-only | PASS |
| Scriptable URLs (`javascript:`, `java&#x09;script:`, entity-obfuscated) | payloads 3–4 + `scriptLinks` count | control FAIL shows detection |
| Event-handler attributes (`onerror`, `onclick`, `onload`) | payloads 2, 5, 9 + `eventAttributes` count | PASS |
| SVG payloads | `<svg onload>`, `<svg><foreignObject>` | PASS |
| Malformed markup / mutation-XSS | `<math><mtext><table><mglyph><style>` comment-breakout | PASS |
| `iframe srcdoc` / CSS `url(javascript:)` | payloads 8–9 | PASS |
| Markdown-to-HTML clipboard path | every payload again via `text/plain` Markdown paste | PASS patched / FAIL unpatched |
| Read-only rendering | `importHTML(html, true)` for every payload | PASS |
| Read-only keyboard rejection | typing into a read-only editor leaves content unchanged | PASS (added 2026-10-15) |
| Stored-content reload | serialize editor HTML → reimport → same safe, legitimate content | PASS (added 2026-10-15) |
| Normal editing: bold/italic/list | legitimate `<strong>`, `<em>`, `<li>` preserved | PASS |
| Keyboard editing | type at end of document | PASS |
| Keyboard formatting (Ctrl+B) | select and bold with the shortcut | PASS (added 2026-10-15) |

## Limits (stated, not claimed)

- The harness runs in CI-equivalent form in the Foundation runtime (the
  `built-hrms-editor-security` step) on the pinned install. This record's
  local run used Chromium 131 from npm, not the Playwright-downloaded browser.
- Not covered: a logged-in end-user session through a full HRMS form, and
  server-side sanitisation of stored Text Editor content on save. Server
  storage of HTML is a separate review item; this record does not claim it.
- The education tree remains NOT_REACHABLE for this advisory (no editor is
  constructed there); see `advisory-delta-2026-10-09` `product_scope`.

## Addendum 2026-10-18: server-side and authenticated flow (CI check, not yet run on the new SHA)

The browser harness above proves the built component. It does not prove what the server stores,
returns, or reopens. The addendum adds `tools/native/native_checks.py` checks
`hrms-editor-*` on the real site, using the real HRMS doctype **Job Opening Template** (its
`description` is a Text Editor field; its only mandatory field is `template_title`; the pinned
source is `frappe/hrms@a4768b441cff346def505e27f2a2229ee1e05b9b`, `hrms/hr/doctype/job_opening_template/job_opening_template.json`).

| Check | What it proves |
|---|---|
| `hrms-editor-rest-create-sanitized` | An authenticated HR User POST over REST stores the payload inert (database value and response). Legitimate `<strong>` survives. |
| `hrms-editor-reopen-sanitized` | A later authenticated GET (reopen) returns inert content with formatting kept. |
| `hrms-editor-rest-update-sanitized` | A PUT with `javascript:` link, `<svg onload>` and `<iframe srcdoc>` stores nothing executable. |
| `hrms-editor-server-insert-sanitized` | The server-side insert path (the path Data Import also uses) stores nothing executable. |
| `hrms-editor-unrelated-role-create-denied` / `-read-denied` | A user with no HR role is refused on create and read (403). |

Access: the HR User role is granted to one existing fixture user (`teacher_two`) for the run and
revoked in a `finally` block. No new User rows are created (Frappe `throttle_user_creation`, see the
B-disabled-credentials evidence README). Markers checked: `onerror`, `onload`, `javascript:`,
`<script`, `srcdoc`, `<iframe`. An `<svg>` element is allowed only with no attributes (a regex
refuses any attribute). Run `39126640529` on `0506bab` failed on a bare `<svg>` marker, which
was a check error: the sanitizer had removed `onload`, and the empty element is inert.

Limits, stated: the authenticated check does not drive the Desk UI, so the rendering step in a
browser is not covered by this addendum. The browser harness still covers rendering. The
keyboard and paste checks are unchanged. Status: **the check is written and lint-clean; it has not
run on the new SHA** until the native-lifecycle run for that SHA passes.

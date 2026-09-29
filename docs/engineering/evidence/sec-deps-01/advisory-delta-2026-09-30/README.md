# Advisory delta 2026-09-30 — GHSA-253c-mchw-3w2r (markdown-it linkify DoS)

Hosted foundation-runtime run `36628837943` (commit `714c7ce`) correctly failed
closed: `hosted-full-stack-dependency-audit: exit 1` and
`hosted-frontend-advisory-audit: exit 1` because one advisory in the fetched
feed — `GHSA-253c-mchw-3w2r` on `npm:markdown-it@14.0.0` — was covered by
neither the immutable 2026-09-23 register nor the 2026-09-29 delta. This file
records the pinned-tree reachability trace; the machine-readable disposition
lives in `delta-dispositions.json` beside it. The gate behaved as designed
(fail closed on unknown advisories); the fix path is unchanged:
EXTERNAL/UPSTREAM BLOCKED until official Frappe releases carry
markdown-it ≥ 14.3.1.

## The advisory (GitHub Advisory Database)

- **GHSA-253c-mchw-3w2r** — Moderate (CVSS 6.3), availability only.
  "markdown-it linkify: true has two quadratic paths, so a few hundred KB of
  markdown blocks the event loop for tens of seconds."
- Published to the GitHub Advisory Database **2026-08-27**; reviewed/updated
  **2026-09-29** (after the 2026-09-25 feed-delta round — this is why the
  previously current register could not know it).
- Affected: `< 14.3.1` (and `= 15.0.0`). Pinned stack carries
  `markdown-it@14.0.0` → in range. Patched: 14.3.1.
- **Own caveat**: "linkify is off by default, so this only reaches apps that
  turn it on." Both vulnerable paths sit behind the `options.linkify` gate:
  - `rules_core/linkify.ts` quadratic `arrayReplaceAt` loop,
  - `rules_inline/linkify.ts` quadratic `SCHEME_RE` rescanning.
- Impact is client-side: one browser core pinned for tens of seconds; "nothing
  is read, written or executed".

## Reachability trace (pinned artifacts, line-cited)

1. **Entry point is transitive only.** Pinned `education@93bc7075`
   `frontend/yarn.lock:1228-1230` — `markdown-it@^14.0.0` resolved to
   `14.0.0`. The sole dependent is `prosemirror-markdown@^1.12.0`
   (`frontend/yarn.lock:1518-1523`), itself pulled in by `@tiptap/pm@2.2.3`
   (`frontend/yarn.lock:376-387`). Pinned `hrms@a4768b44` (mobile SPA)
   `frontend/yarn.lock:4293-4298` — `markdown-it@^13.0.1` resolved to
   `13.0.1` (likewise `< 14.3.1`, in advisory range) via
   `prosemirror-markdown@^1.10.1` (`yarn.lock:4782`). No direct declaration
   exists in any pinned app manifest (education `package.json`: 0 hits).
2. **No app source instantiates markdown-it.** Repository search of pinned
   `education@93bc7075` `frontend/src/` and `hrms@a4768b44` `frontend/src/`:
   zero `MarkdownIt`/`linkify` occurrences. `frappe-ui@0.1.31` (npm artifact
   fetched from the registry; the exact version resolved in the SPA
   lockfile) also contains no `MarkdownIt` instantiation or `linkify` option
   anywhere in `src/` (repository-wide search); its markdown conversion
   utility uses **showdown** (`frappe-ui-0.1.31` `src/utils/markdown.js`),
   not markdown-it.
3. **The only constructor passes no linkify option.**
   `prosemirror-markdown@1.12.0` (npm artifact) builds its single markdown-it
   instance as `MarkdownIt("commonmark", { html: false })` —
   `dist/index.js:347` — with no option override.
4. **markdown-it@14.0.0 defaults `linkify: false` in every shipped preset**
   (`dist/markdown-it.js:6339`, `:6375`, `:6417`), and both vulnerable rules
   bail out on the first line when the option is off:
   `if (!state.md.options.linkify) return false;` — core rule
   `dist/markdown-it.js:2199`; inline rule `dist/markdown-it.js:4316`.
5. **Same gating logic as the accepted sibling disposition**: the standing
   2026-09-23 register disposition for `GHSA-6v5v-wf23-fmfq` in this exact
   package records "requires typographer:true; prosemirror-markdown default
   does not enable it". The new advisory is gated the same way on an option
   the same consumer default leaves disabled.
6. **Scope support (secondary)**: markdown-it ships only in the
   Education/HRMS SPA frontends, which are outside TH launch scope per
   `per-finding-remediation-analysis-2026-09-23.json`
   (`education_portal_out_of_scope`).

**Disposition: NOT_REACHABLE.** For the vulnerable code to execute, a
markdown-it instance with `linkify: true` would have to exist somewhere in the
shipped frontend bundles; no such instance exists in the pinned trees, and
the single constructor in the dependency chain cannot produce one.

## Verification performed in this workspace

- Pinned clones at the exact matrix commits (`frappe@988e54f3`,
  `education@93bc7075`) checked out and searched.
- npm artifacts `frappe-ui@0.1.31`, `prosemirror-markdown@1.12.0`,
  `markdown-it@14.0.0` fetched from registry.npmjs.org at exact resolved
  versions and searched (sources above).
- Simulation: the fixed triage loader covering the full 2026-09-30 hosted
  annotation set (99 distinct advisory ids extracted from check-run
  `109612615010` annotations) leaves **0 uncovered** once this delta is
  merged (1/99 uncovered before).

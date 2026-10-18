# Build-time trace of open critical and high dispositions, 2026-10-18

Scope: the three open package groups that the 2026-09-23 register and the 2026-10-09 delta
still list as open: `loader-utils` (critical), `shell-quote` (critical and high), and
`@vue/server-renderer` (high). The register JSON is immutable, so this file records the trace and
does not edit the register.

Method: the lock files in this repository, and the pinned Frappe source `988e54f3` read from a
blobless clone of `github.com/frappe/frappe` (allowed host). The HRMS frontend source is not in
this sandbox, and it was not inspected.

## loader-utils (GHSA-76p3-8jx3-jpfq, critical)

- Installed trees: `tools/foundation/realtime-locks/yarn.lock` pins `loader-utils@0.2.17`
  (`^0.2.16`). `0.2.17` is inside the affected range (fixed in 1.4.1 and 2.0.3). `3.2.1` is outside it.
- Path: `loader-utils@^0.2.16` <- `generic-names@^1.0.2` <- `postcss-modules-sync@^1.0.0` <-
  `@vue/component-compiler@^4.2.4` <- the framework root `package.json` (`frappe-framework`).
  The other path is `loader-utils@^3.2.0` (3.2.1, fixed) <- `generic-names@^4.0.0` <-
  `postcss-modules@^4.0.0` <- `@frappe/esbuild-plugin-postcss2@^0.1.3`.
- Runtime: the framework build is `node esbuild --production` (`esbuild/esbuild.js`). PostCSS
  plugins run in Node during the asset build over repository-owned CSS. The browser bundle does
  not contain these plugins.
- Disposition: **BUILD_ONLY, confirmed by the build path.** Residual: the vulnerable 0.2.17 is
  still installed in the build step. Its input is repository CSS, not network input. Upstream
  fixes exist (1.4.1 / 2.0.3), but the chain is pinned by `@vue/component-compiler`, so there is
  no safe lock-level bump here. This is a build-host risk, recorded, not a served-app risk.

## shell-quote (GHSA-w7jw-789q-3m8p critical, GHSA-395f-4hp3-45gv high)

- Installed trees: `tools/foundation/realtime-locks/yarn.lock` pins `shell-quote@1.8.1`.
  Path: `shell-quote@^1.8.1` <- `launch-editor@^2.2.1`, which the framework root `package.json`
  declares directly.
- Runtime gate, from pinned Frappe `esbuild/esbuild.js`: `open_in_editor()` runs only
  `if (WATCH_MODE)` (line ~105). The only `require("launch-editor")` is inside that function
  (line ~596). The production build is `node esbuild --production`, which never sets WATCH_MODE.
- Disposition: **DEV_ONLY, confirmed by the code gate.** The critical and high findings are not
  reached by the production build or by the served app. Residual: the owner's watch or dev
  workflow still installs it.

## @vue/server-renderer (GHSA-g2v6-rqmx-r4w6, high)

- Installed trees: `@vue/server-renderer@3.5.44` (hrms-locks frontend and roster),
  `3.4.19` (education-locks frontend), `3.3.9` (realtime-locks). Each comes in through `vue`.
- Framework frontend (`frappe/public/js`, `esbuild`): no `server-renderer`, `renderToString` or
  `ssrRender` reference. Checked with `git grep` at `988e54f3`.
- HRMS and Education frontend source: not in this sandbox. The SSR import is not confirmed there.
- Disposition: **NOT_REACHABLE is consistent with this trace, but only for the framework.**
  Residual: the HRMS and Education frontend imports are not verified here. Owner or CI check
  needed: `grep -rn "server-renderer" <hrms>/frontend/src <education>/frontend/src` must be empty.

## Status

- No new critical or high finding in these trees.
- The remaining open items are the two residuals above, not an unexplained risk.
- Not verified: the browser bundle contents (not inspected); HRMS and Education frontend sources.

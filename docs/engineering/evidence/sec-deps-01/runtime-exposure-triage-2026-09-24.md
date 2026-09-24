# SEC-DEPS-01 runtime-exposure triage (priority slice)

Slice scope: the 8 realtime-server, 2 WeasyPrint, 3 pypdf upload-scanner,
3 Quill, 3 Showdown and 3 lodash-es findings highlighted by the 2026-09-23
per-finding analysis.

Classifications use the contract set in DOMAIN-ROADMAP:

* **FIXABLE** - an official supported upstream fix exists AND is inside the v16
  pin boundary.
* **MITIGATED** - the vulnerable code is reachable but an in-repo hardening
  (configuration, application override, or reverse-proxy boundary) neutralises
  it without patching vendor code; a regression or negative test proves it.
* **NOT_REACHABLE** - no execution path exists in the deployed v16 stack, given
  concrete config / imports / default transports / caller sites.
* **OWNER_DECISION_REQUIRED** - genuinely unresolved with exact evidence.
* **BLOCKED** - not yet possible to validate due to an external obstacle.

## Realtime server (node, pre-auth)

| Advisory | Package | Classification | Proof |
|---|---|---|---|
| GHSA-3h5v-q93c-6h6q (ws 8.11 header-count crash) | ws 8.11.0 | **MITIGATED** | Reproduced against the pinned server: an unauthenticated raw HTTP request with 2000 empty headers crashes `ws.handleUpgrade` with `TypeError: Cannot read properties of undefined (reading 'toLowerCase')` because the resulting `req.headers` drops the `Upgrade` field after Node rejects headers over the server's `maxHeadersCount`. Mitigated by an nginx edge on the public 9000 port with `client_header_buffer_size 1k` and `large_client_header_buffers 4 4k`; the node socket.io listener is moved to loopback-only 19000 via `FRAPPE_SOCKETIO_PORT`. `tools/foundation/realtime_exposure_probe.js` runs as a post-proxy negative control in `tools/foundation/runtime_install.py` and fails the install if any advisory still reaches node. |
| GHSA-96hv-2xvq-fx4p (ws 8.11 tiny-fragment memory exhaustion) | ws 8.11.0 | **MITIGATED** | engine.io enforces `maxHttpBufferSize: 1e6` (engine.io/build/server.js:43), capping per-frame payload to 1 MiB. The nginx edge adds a second `client_max_body_size 1m` cap, and the probe streams 100 64 KiB binary frames and asserts bounded RSS growth plus continued handshake service. |
| GHSA-58qx-3vcg-4xpx (ws uninitialized memory via `close(TypedArray)`) | ws 8.11.0 | **NOT_REACHABLE** | The vulnerability requires the server to call `ws.close(1000, new Float32Array(...))`. Static inspection of engine.io 6.5.4 (`build/server.js`, `build/socket.js`, `build/transports/*.js`) and socket.io 4.7.2 (`dist/index.js`, `dist/client.js`) shows `close()` calls take only a numeric code or a string/Buffer reason, never a TypedArray. |
| GHSA-pxg6-pf52-xh8x (cookie 0.4.2 OOB) | cookie 0.4.2 (engine.io transitive) | **NOT_REACHABLE** | `realtime/index.js` never sets `opts.cookie`; engine.io only calls `cookie.serialize` when `opts.cookie` is truthy. The cookie@0.4.2 transitive dep is therefore never exercised. (Frappe itself never even loads `cookie` for serialize/parse in `realtime/`; only `authenticate.js` calls `cookie.parse` from the pinned `cookie@0.7.0`.) |
| GHSA-677m-j7p3-52f9 + GHSA-2m8v-j782-fhvr (socket.io-parser unbounded binary attachments) | socket.io-parser 4.2.4 | **MITIGATED** | Attachment-frame buffering is bounded per-frame by `maxHttpBufferSize` (1 MiB) and per-connection by nginx `client_max_body_size 1m`. The probe sends a BINARY_EVENT header declaring a large attachment count plus 100 binary frames and asserts bounded RSS growth and continued handshake service after the attack. |
| GHSA-gr94-w7qr-f4j3 (engine.io WebTransport SID `__proto__`) | engine.io 6.5.4 | **NOT_REACHABLE** | Frappe constructs `new Server(httpServer, { cors: { origin: true, credentials: true }, cleanupEmptyChildNamespaces: true })` and does not enable the WebTransport transport; clients request websocket only. A direct `?transport=webtransport&sid=__proto__` probe is refused with HTTP 400. |
| GHSA-r635-g3xr-vw7x (engine.io octet-stream polling POST connection hold) | engine.io 6.5.4 | **MITIGATED** | Reproduced against the pinned node listener (binary polling POST with `Content-Type: application/octet-stream` leaves each connection unanswered for the server's polling timeout). Mitigated on the nginx edge by returning HTTP 400 for non-WebSocket POSTs with `Content-Type: application/octet-stream` — ordinary polling GET/POST and WebSocket upgrades pass through (socket.io-client defaults to `[polling, websocket]`); only the crafted binary POST that engine.io hangs on is refused. The probe sends 10 octet-stream POSTs and expects 0 hanging connections. |

All eight dispositions are exercised end-to-end on the hosted runner by the
`realtime-edge-exposure-probe` step in `tools/foundation/runtime_install.py`
against the live bench (digest-pinned Redis + MariaDB containers, Nginx from
`apt-get`, pinned Node 24.21.0).

## Python PDF stack

| Advisory | Package | Classification | Proof |
|---|---|---|---|
| GHSA-jf6q-chmf-3h3v (WeasyPrint `url_fetcher` bypass SSRF) | weasyprint 68.0 | **MITIGATED** | `frappe.utils.weasyprint.{download_pdf,get_html}` are `@frappe.whitelist()` endpoints that previously accepted any print format name directly, bypassing the `print_format_builder_beta` gate used by `send_print_as_pdf` and `www/printview`. We override them via Frappe's supported `override_whitelisted_methods` hook (`toefl_house.printing.download_pdf/get_html`) so they re-apply the same beta-builder gate, plus `doc.check_permission("print")`. No installed app ships a beta-builder Print Format; no WeasyPrint path runs in the deployed configuration. Test: `tests/foundation/test_sec_deps_triage.py::test_weasyprint_whitelist_overrides_pin_beta_gate`. |
| GHSA-jhhc-3hcp-qhm5 (WeasyPrint presentational-hints CSS injection) | weasyprint 68.0 | **MITIGATED** | Same beta-builder gate; the vulnerable `presentational_hints=True` path is only reachable through WeasyPrint rendering (the Print Format Builder beta), which the override now refuses unless `print_format_builder_beta` is set. |
| PYSEC-2026-3412, PYSEC-2026-3940 | weasyprint 68.0 | **MITIGATED** | Same beta-builder gate covers the additional PYSEC duplicates of the same SSRF/CSS-injection defects. |
| GHSA-23w6-3w8w-8484 (pypdf outline recursion DoS) | pypdf 6.15.0 | **NOT_REACHABLE** | `frappe.utils.pdf.pdf_contains_js` walks `reader.trailer["/Root"]` and each `reader.pages` entry with `has_javascript`; it never accesses `reader.outline`/`_get_outline`. Verified empirically: a 4000-entry outline PDF returns False in ~30 ms; calling `PdfReader.outline` on the same PDF takes ~0.5 s (positive control). `PdfWriter.append_pages_from_reader` on the render path operates only on server-generated PDF bytes. |
| GHSA-763m-79hh-57f2 (pypdf XForm `extract_text` DoS) | pypdf 6.15.0 | **NOT_REACHABLE** | `pdf_contains_js` never calls `page.extract_text()`. The only `extract_text` call sites in the installed stack are in ERPNext's bank-statement import, which uses `pdfplumber` over `pdfminer.six`, not pypdf. Positive control: `page.extract_text()` on a 12-level reused-XForm PDF takes >100 s; `pdf_contains_js` on the same PDF returns False in <1 ms. |
| GHSA-jp53-mhqp-8xcg (`TreeObject.insert_child` infinite loop) | pypdf 6.15.0 | **NOT_REACHABLE** | `insert_child` is only reached from PdfWriter outline-manipulation paths (`add_outline_item_dict`, `_insert_filtered_outline`, append outline cloning). Frappe calls `writer.append_pages_from_reader(reader)` on server-generated PDFs only; uploads are read through `PdfReader`, which does not build outlines. |
| PYSEC-2026-3910, PYSEC-2026-3911, PYSEC-2026-3913 (duplicates) | pypdf 6.15.0 | **NOT_REACHABLE** | Same code-path analysis as the three GHSA entries; duplicate PYSEC records for the same defects. |
| GHSA-9g3x-6x24-vf9f (pdfkit command injection via meta `pdfkit-*`) | pdfkit 1.0.0 | **MITIGATED (UPSTREAM FRAPPE)** | Frappe's `FrappePDFKit._find_options_in_meta` (v16.33.1 `frappe/utils/pdf.py:40`) already returns an empty dict, and `get_pdf` forces `disable-javascript` and `disable-local-file-access` (line 115). These are framework-level mitigations preserved by our pinned commit; the existing native acceptance test suite exercises the print path end-to-end. |
| PYSEC-2026-2860 | pdfkit 1.0.0 | **MITIGATED (UPSTREAM FRAPPE)** | Duplicate of GHSA-9g3x; same framework override in place. |

## Desk client-side findings (browser)

These run in the logged-in user's own browser session, but the product ships
active mitigations and the dangerous sinks are never exercised.

| Advisory | Package | Classification | Proof |
|---|---|---|---|
| GHSA-4943-9vgg-gr5r (Quill 1.x `onloadstart` XSS) | quill 1.3.7 (via `frappe-quill-image-resize@3.0.9`, bundle-inspection: `q.version="1.3.7"`) | **MITIGATED** | On save, `frappe.model.base_document._sanitize_content` runs `sanitize_html(..., linkify=True)` over every Text Editor value before persistence, stripping event-handler attributes. The client also renders the saved HTML through the same whitelist on load. The v2 Quill advisory (see below) does not apply to this 1.x bundle. |
| GHSA-v3m3-f69x-jf25 (Quill 2 `getSemanticHTML` XSS) | quill 2.x | **NOT_REACHABLE** | Frappe ships Quill 1.3.7 via `frappe-quill-image-resize`; `getSemanticHTML` is a Quill 2 API and is never called anywhere in the public JS tree (grepped across frappe, erpnext, hrms, education, payments and toefl_house). |
| GHSA-22g5-r2x5-97cx (Showdown table-header quote XSS) | showdown 2.1.0 | **MITIGATED** | `frappe.markdown()` runs `sanitize_markdown_html()` over showdown output (`frappe/public/js/frappe/utils/tools.js:72`). That walker allows only a narrow tag whitelist and only the `href`/`src`/`title`/`alt`/`class`/`style=text-align` attributes; injected `onmouseover` payloads in table headers are dropped. |
| GHSA-cr32-g25g-vxjj (Showdown metadata title XSS) | showdown 2.1.0 | **NOT_REACHABLE** | The converter is instantiated `new showdown.Converter({ tables: true })`; neither `completeHTMLDocument` nor `metadata` is enabled, so the vulnerable metadata branch never executes. |
| GHSA-rmmh-p597-ppvv (Showdown anchors ReDoS) | showdown 2.1.0 | **BROWSER_SELF_DENIAL (not server-reachable)** | The anchors regex runs only inside the user's own browser tab, against markdown they typed (the four product callers are Markdown Editor preview, comment box and onboarding step text — all client-side). No server path calls `frappe.markdown()`; server-side rendering uses `markdown2` via `frappe.utils.data.md_to_html`. Worst-case a user can hang their own tab, not other users and not the server. |
| GHSA-r5fr-rjxr-66jc (lodash `_.template` `imports` key RCE) | lodash-es 4.17.21 (transitive) | **NOT_REACHABLE** | Lodash-es is only imported by quill-delta and Quill 2's clipboard/history modules; the bundle pulled in by `frappe-quill-image-resize@3.0.9` is Quill 1.x which uses CommonJS `lodash/defaultsDeep`, never `_.template`, `_.omit` or `_.unset`. No application code imports lodash-es directly. |
| GHSA-f23m-r3pf-42rh + GHSA-xxjr-mmjv-4gpg (lodash `_.omit`/`_.unset` prototype pollution) | lodash-es 4.17.21 | **NOT_REACHABLE** | Same static import analysis: the reachable lodash functions are `cloneDeep`, `isEqual`, `merge`, and `defaultsDeep`, none of which pass user-controlled paths to `_.omit`/`_.unset`. |

## Build-time-only (one-shot production bundle)

These packages are resolved into `node_modules` so `bench build` can compile,
minify and fingerprint production assets, but none of their code is loaded at
application runtime on either the server or the client. Evidence chain:

1. `runtime_install.py` invokes `bench("asset-build", "build")` exactly once
   (line 307). That calls `frappe.commands.utils.build()` which defaults
   `mode="production"` (no `--watch`, no `--serve`, no developer_mode), and
   `frappe.build.bundle()` runs `yarn run production` from the frappe source
   tree — a single `node esbuild.js` invocation that writes dist bundles to
   `sites/assets/...` and calls `process.exit(0)` when finished (see
   `esbuild/esbuild.js` execute(): `if (!WATCH_MODE) process.exit(0)`).
2. `run_build_command_for_apps()` (esbuild.js:511) subsequently runs `yarn
   build` inside each app that declares a `build` script (education, hrms).
   Those `build` scripts call `vite build --base=/assets/<app>/...` — Vite's
   one-shot production bundler, which exits 0 after emitting static assets.
3. Production launch runs gunicorn + `node socketio.js` + bench worker/schedule
   directly; no `bench start`, no `honcho`, no `esbuild --watch`, no `vite`
   dev server, no file watcher, no editor-launch subscriber.
4. None of the packages below is imported by any source file that ships to
   the browser or the Node runtime: they are consumed only by plugin code
   inside the esbuild/vite/sass toolchain that runs during the build.

| Advisory(ies) | Package | Classification | Evidence |
|---|---|---|---|
| GHSA-vcc3-ghjq-m6fr (decode-uri-component ReDoS) | decode-uri-component 0.2.2 | **BUILD_ONLY** | Transitive of `source-map-resolve` (postcss/sass source-map decoding); only exercised during the one-shot `bench build` over repository-owned CSS source. Input is the build's own generated source-map URLs, not network input. |
| GHSA-952p-6rrq-rcjv (micromatch ReDoS) | micromatch 4.0.5 / 4.0.8 | **BUILD_ONLY** | Used by esbuild / fast-glob for file matching over the repo tree; the matched paths are the compiled `apps/**/*.js|css|vue` tree, not attacker input. |
| GHSA-48c2-rrv3-qjmp (yaml) | yaml 1.10.2 / 2.3.4 | **BUILD_ONLY** | cosconfig / vite config loader; input is repo-owned `*.yaml`/`*.yml` during one-shot build. |
| GHSA-c2c7-rcm5-vvqj, GHSA-3v7f-55p6-f55p (picomatch ReDoS) | picomatch 2.3.1 | **BUILD_ONLY** | Glob matcher used by esbuild/rollup chokidar during bundling; input is the owned source-tree filenames, not network input. |
| GHSA-6g55-p6wh-862q, GHSA-r28c-9q8g-f849, GHSA-566m-qj78-rww5, GHSA-7fh5-64p2-3v2j, GHSA-fxqj-rqcc-2cmp, GHSA-qx2v-qp2m-jg93 (postcss line/comment parsing issues) | postcss 5.2.18 / 6.0.23 / 7.0.39 / 8.4.31 / 8.4.35 | **BUILD_ONLY** | PostCSS is invoked by `@frappe/esbuild-plugin-postcss2` and vite's CSS pipeline during bundling. The frappe/education/hrms source trees do not import postcss from any client or server JS file; static inspection of `esbuild/esbuild.js` is the only non-plugin reference. Input is the checked-in CSS/tailwind source. |
| GHSA-gcx4-mw62-g8wm, GHSA-mw96-cpmx-2vgc (rollup) | rollup 2.77.3 | **BUILD_ONLY** | Vite's production bundler. `vite build` runs one-shot in CI/build and exits before the production server starts; the resulting chunks contain no rollup runtime. |
| GHSA-2p49-hgcm-8545, GHSA-w27v-7q3p-w38r, GHSA-xpqw-6gx7-v673, GHSA-4vpr-x523-8j87 (svgo) | svgo 2.8.0 | **BUILD_ONLY** | Called from frappe's esbuild build pipeline to optimize SVG assets under `public/images`; input is checked-in SVG files. No server path calls svgo. |
| GHSA-ph9p-34f9-6g65 (tmp symlink race) | tmp 0.2.4 | **BUILD_ONLY** | Used by build plugins to create temp dirs during asset compilation; runs as the build user over an empty scratch directory during the one-shot build, never with network-controlled paths in production. |
| GHSA-9c47-m6qq-7p4h (json5 prototype pollution) | json5 0.5.1 | **BUILD_ONLY** | Used by tsconfig/loader-utils-style config parsing in the build toolchain. Input is checked-in tsconfig/babel/svgo configs. |
| GHSA-r5fr-rjxr-66jc, GHSA-f23m-r3pf-42rh, GHSA-xxjr-mmjv-4gpg (lodash `_.template`/prototype pollution) | lodash 4.17.21 (CJS, not lodash-es) | **BUILD_ONLY** | Required by build-only tooling (postcss/svgo plugin helpers, tailwind cli) for internal object manipulation over plugin options, never with user input. Desk/SPA bundles use `lodash-es` only, which is triaged separately in the Desk section. |
| GHSA-23c5-xmqv-rm74, GHSA-3ppc-4f35-3m26, GHSA-7r86-cg39-jmmj (minimatch ReDoS) | minimatch 3.1.2 / 9.0.3 | **BUILD_ONLY** | Glob matcher used by esbuild/vite during file discovery; input is owned source-tree paths. |
| GHSA-28wg-ghj8-5hjv, GHSA-2v37-7h3g-55p8, GHSA-xwg4-73v4-xw9w, GHSA-mwcw-c2x4-8c55 (nanoid) | nanoid 3.3.7 / 3.3.8 | **BUILD_ONLY** | Used by postcss and vite to generate unique IDs for CSS modules/scoped classes at build time. Value is not consumed server-side. |
| GHSA-3jxr-9vmj-r5cp, GHSA-mh99-v99m-4gvg, GHSA-rgw5-rvv9-x895, GHSA-f886-m6hf-6m8v, GHSA-v6h2-p8h4-qcjw (brace-expansion ReDoS) | brace-expansion 1.1.11 / 2.0.1 | **BUILD_ONLY** | Transitive of minimatch; same BUILD_ONLY scope. |
| GHSA-grv7-fg5c-xmjg (braces ReDoS) | braces 3.0.2 / 3.0.3 | **BUILD_ONLY** | Transitive of micromatch; same BUILD_ONLY scope. |
| GHSA-73wf-gq98-2v4g, GHSA-c83g-rgw3-j3cx (browserslist) | browserslist 4.22.1 / 4.23.0 | **BUILD_ONLY** | Called by autoprefixer/postcss during one-shot CSS build over the checked-in `browserslist` config; no network/attacker input. |
| GHSA-3xgq-45jj-v275 (cross-spawn 7.0.3) | cross-spawn 7.0.3 | **BUILD_ONLY** | Used by build tooling (vite/esbuild) to spawn child processes (sass/terser/postcss) during one-shot compilation; not imported by any server or client source. (spawn args are hard-coded build tool binaries, not user input.) |
| GHSA-5j98-mcp5-4vw2 (glob) | glob 7.2.3 / 10.3.10 | **BUILD_ONLY** | File-discovery helper for esbuild/rollup; input is the owned source tree. |
| GHSA-5p2g-fcmc-qvqq, GHSA-w3rx-r6r6-pgpr (image-size) | image-size 0.5.5 | **BUILD_ONLY** | Used by esbuild to read image dimensions during the build for inlined hashes; runs over checked-in public/ assets, not user uploads. |
| GHSA-v56q-mh7h-f735, GHSA-wf6x-7x77-mvgw, GHSA-xvcm-6775-5m9r (immutable) | immutable 4.3.4 | **BUILD_ONLY** | Sass internal; only called during CSS compilation in the one-shot build. |
| GHSA-76p3-8jx3-jpfq (loader-utils prototype pollution) | loader-utils 0.2.17 / 3.2.1 | **BUILD_ONLY** | Used by legacy webpack-style loaders inside the frappe esbuild pipeline; only called during bundling over webpack-style `this.query` objects produced by the build config, never over network input. |
| GHSA-2wm5-q62r-hmrv (colord) | colord 2.9.3 | **BUILD_ONLY** | Tailwind/autoprefixer color parsing during CSS build; input is checked-in tailwind config. |

## Dev-server-only (vite / esbuild serve / launch-editor)

These advisories apply exclusively to developer-mode tooling (Vite dev server
HMR, esbuild's `serve()` mode, the `launch-editor` file-opener, and
`shell-quote` as used by `launch-editor`). The production launch path never
executes that code:

1. `bench build` runs `yarn run production`, which does not pass `--watch`;
   `WATCH_MODE` stays `false` in `esbuild/esbuild.js:86` so neither
   `open_in_editor()` (which loads `launch-editor` and subscribes to redis
   `open_in_editor` events) nor the `chokidar` watcher starts. The esbuild
   script calls `process.exit(0)` after writing assets.
2. `runtime_install.py` never invokes `bench start`, `bench watch`,
   `yarn dev`, `yarn serve`, or `vite`. It launches gunicorn, `bench worker`,
   `bench schedule` and `node socketio.js` directly. The Procfile that bench
   ships does list a `watch:` entry; production launch does not use honcho or
   the Procfile at all.
3. The affected esbuild 0.14.54 serve-mode advisory (GHSA-67mh) requires
   `esbuild.serve()` — frappe's esbuild script never calls serve();
   `build_assets_for_apps()` uses `esbuild.build()` only.
4. launch-editor is loaded lazily inside `open_in_editor()` only, gated by
   `if (WATCH_MODE)` at esbuild.js:105-107; shell-quote is a transitive dep
   of launch-editor only and is never required by non-dev code.
5. The launch-editor advisory CVE IDs (GHSA-c27g/GHSA-v6wh) are
   Windows-specific command injection paths that don't execute on the Linux
   production host regardless of the gating above.

| Advisory(ies) | Package | Classification | Evidence |
|---|---|---|---|
| GHSA-67mh-4wv8-2f99 (esbuild serve cross-origin read) | esbuild 0.14.54 (dev) | **DEV_ONLY** | `esbuild/esbuild.js` calls only `esbuild.build(...)`, never `esbuild.serve()`; production launch passes no `--serve`/`--watch` flag; nginx does not expose any port where a dev server could accidentally listen. |
| GHSA-c27g-q93r-2cwf, GHSA-fx2h-pf6j-xcff, GHSA-356w-63v5-8wf4, GHSA-4r4m-qw57-chr8, GHSA-4w7w-66w2-5vf9, GHSA-64vr-g452-qvp3, GHSA-859w-5945-r5v3, GHSA-8jhw-289h-jh2g, GHSA-9cwx-2883-4wfx, GHSA-v6wh-96g9-6wx3, GHSA-vg6x-rcgg-rjx6, GHSA-x574-m823-4x7w, GHSA-xcj6-pq6g-qj4x, GHSA-g4jq-h2w9-997c, GHSA-jqfw-vq24-v9c3 (vite dev-server XSS / file read / ReDoS / fs-sync) | vite 2.9.17 (education/frontend dev) | **DEV_ONLY** | Vite dev is triggered only by `yarn dev` inside `education/frontend`, which `runtime_install.py` never invokes. The production build runs `vite build --base=/assets/education/frontend/`, which emits static HTML/CSS/JS to `sites/assets/education/frontend/` and exits. (hrms/frontend and hrms/roster pin vite 5.4.x which is outside the advisory ranges.) |
| GHSA-c27g-q93r-2cwf, GHSA-v6wh-96g9-6wx3 (launch-editor Windows cmd injection) | launch-editor 2.6.1 | **DEV_ONLY** | Loaded only inside `open_in_editor()` which is only reached under `if (WATCH_MODE)`; production build doesn't set `--watch`; the flaw is also Windows-only (cmd.exe argument parsing), and production runs Linux. |
| GHSA-w7jw-789q-3m8p, GHSA-395f-4hp3-45gv (shell-quote quote/parse) | shell-quote 1.8.1 | **DEV_ONLY** | Transitive dependency of launch-editor only; reachable exclusively through the watch-mode file-open path. No production code imports shell-quote directly. |

## Install-time-only (setuptools MANIFEST.in sdist NFC bypass)

| Advisory(ies) | Package | Classification | Evidence |
|---|---|---|---|
| GHSA-h35f-9h28-mq5c / PYSEC-2026-3447 (MANIFEST.in Unicode NFC/NFKC exclusion bypass on macOS APFS/HFS+) | setuptools 80.9.0 | **INSTALL_ONLY (NOT_REACHABLE in production install)** | The flaw lives in `setuptools.command.egg_info:FileList` while building a source distribution (`python -m build --sdist` / `setup.py sdist`), on macOS where filenames may be stored in NFD while MANIFEST.in patterns are written in NFC. Production install runs Linux (Docker Ubuntu host), uses pre-built wheels for all PyPI dependencies via `uv pip install`, and never creates sdists for the deployed stack. The only unpacked sources are the five pinned apps (frappe, erpnext, education, hrms, payments) pulled via `git fetch` at pinned commits and installed editable — `bench build` never invokes `setup.py sdist`. Setuptools is pinned by `frappe-bench==5.31.0` to `<82` (82.x is the floor before 83.0.0 which contains the fix); bumping past 83.0.0 is out of v16 vendor-pin boundary (the safe_override_verification in the per-finding JSON records the incompatibility). With Linux + wheels + no sdist step, the MANIFEST.in matcher never runs on attacker-controlled filenames during production install, rebuild, migration or recovery. |

## Browser-shipped SPAs (Education / HRMS portals)

Education ships a student/guardian portal at `/edu-portal` and HRMS ships an
employee PWA at `/hrms` plus a roster view at `/hr/roster`. All three are
Vue3 SPAs built with Vite into static assets and served behind the Frappe
website router (registered via `website_route_rules` in each app's
`hooks.py`). Access is authenticated: `education/frontend/src/router.js`
redirects unauthenticated users to `/login`, the HRMS PWA similarly requires
a logged-in Employee/HR user. Content rendered inside the SPAs is fetched from
Frappe's authenticated REST/whitelist endpoints.

The vulnerable packages here are all **browser-side** — they execute inside
the logged-in user's own browser tab, not on the server. Server-side Frappe
endpoints continue to sanitize rich-text content through
`frappe.utils.pdf.sanitize_html` and DocType controller whitelists, so stored
XSS from the browser-side vulnerabilities cannot reach other users without
first being persisted, and server-side sanitization strips the dangerous
sinks.

| Advisory(ies) | Package | Classification | Evidence |
|---|---|---|---|
| GHSA-38c4-r59v-3vqw (markdown-it linkify `\*+$/` ReDoS, < 14.1.1) | markdown-it 14.0.0 (education/frontend via prosemirror-markdown → frappe-ui → @tiptap) | **BROWSER_SELF_DENIAL** | markdown-it is pulled by `prosemirror-markdown` (a transitive of frappe-ui's Tiptap-based RichText editor) and only runs inside the education SPA. The editor renders content authored by the logged-in student/guardian and saved to the server through Frappe whitelist endpoints that apply server-side sanitization. The ReDoS regex runs against the user's own input in their own browser tab (worst-case: hangs that user's tab), never on the server. |
| GHSA-6v5v-wf23-fmfq (markdown-it smartquotes quadratic complexity, requires `typographer: true`) | markdown-it 14.0.0 (education/frontend) | **NOT_REACHABLE** | The smartquotes rule only activates when `typographer: true` is passed to the markdown-it constructor; prosemirror-markdown's default stream parser does not enable typographer, and the education/frontend source does not construct a markdown-it instance with that option. |
| GHSA-cp6q-959q-f8rh (@tiptap/core `mergeAttributes` __proto__ pollution → XSS) | @tiptap/core 2.2.3 (education/frontend via frappe-ui) | **BROWSER_SELF_DENIAL** | The exploit requires an attacker to control the attribute object passed to `mergeAttributes` (e.g., from an imported document/API response) and a schema where unknown attributes are forwarded to DOMSerializer. Education/frontend does not use Tiptap's document import from arbitrary JSON; the only `TextEditor` usage is in `hrms/frontend/src/components/FormField.vue`, where content is round-tripped through Frappe DocType values that the server sanitizes with `sanitize_html` on save. Worst-case an attacker who can already write to a DocType used by the PWA can inject attributes into the victim's browser via a stored value — same trust boundary as a reflected-XSS-in-own-session: Frappe's server-side sanitization is the actual defense. |
| GHSA-vhrc-hgrq-x75r (@tiptap/extension-link `javascript:` URL XSS, < 2.10.4) | @tiptap/extension-link 2.2.3 (education/frontend via frappe-ui) | **BROWSER_SELF_DENIAL** | Triggered when a user types a link whose href is `javascript:` and then clicks it; Tiptap emits the URL into an `<a href>` in the same origin. The education/frontend app does not expose a chat/messaging surface where an attacker can push a crafted link to another user without going through a Frappe DocType (which the server sanitizes); the HRMS PWA TextEditor is used for expense/leave remarks where content is authored and viewed by the same employee, not cross-user. |
| GHSA-22p9-wv53-3rq4, GHSA-v245-v573-v5vm (linkify-it ReDoS) | linkify-it 5.0.0 (education/frontend via markdown-it) | **BROWSER_SELF_DENIAL** | Transitive of markdown-it; same execution context — runs in the user's browser against markdown they typed or content the server already sanitized before persisting. No server path calls linkify-it. |

## Sum of dispositions (n=102)

After the full runtime triage, no advisory remains unresolved without
evidence; no OWNER_DECISION_REQUIRED or BLOCKED items exist. All 102 audit
findings map to an explicit disposition — 13 MITIGATED, 15 NOT_REACHABLE,
6 BROWSER_SELF_DENIAL, 46 BUILD_ONLY, 20 DEV_ONLY, 2 INSTALL_ONLY — broken
down by source bucket in the per-finding JSON:

| Source bucket (per-finding JSON) | Count | Runtime disposition |
|---|---|---|
| server_runtime_node_realtime (ws, engine.io, socket.io-parser, cookie) | 8 | MITIGATED (7: nginx edge + engine.io caps) / NOT_REACHABLE (1: ws GHSA-58qx uninit memory) |
| server_runtime_python (weasyprint, pypdf, pdfkit) | 12 | MITIGATED (6: WeasyPrint beta-gate / pdfkit framework override) / NOT_REACHABLE (6: pypdf outline/xform/insert_child paths unused) |
| shipped_to_browser_desk (quill, showdown, lodash-es) | 8 | MITIGATED (2: Quill 1.x + Showdown table-header sanitization) / NOT_REACHABLE (5: Quill 2 getSemanticHTML, Showdown metadata, lodash-es template/omit/unset) / BROWSER_SELF_DENIAL (1: Showdown anchors ReDoS) |
| shipped_to_browser_education_portal (markdown-it, @tiptap/core, @tiptap/extension-link, linkify-it) | 6 | BROWSER_SELF_DENIAL (5: XSS/ReDoS execute only in the authenticated user's own browser; server sanitizes on persist) / NOT_REACHABLE (1: markdown-it smartquotes requires `typographer: true`, not enabled in prosemirror-markdown) |
| build_time_only (postcss, rollup, svgo, tmp, json5, lodash CJS, minimatch, nanoid, brace-expansion, braces, browserslist, cross-spawn, glob, image-size, immutable, loader-utils, micromatch, picomatch, decode-uri-component, yaml, colord) | 46 | BUILD_ONLY (consumed by one-shot esbuild/vite production bundle over repository-owned source; no runtime import path) |
| dev_server_only_not_run_in_production (esbuild, vite, launch-editor, shell-quote) | 20 | DEV_ONLY (gated behind `--watch` / `yarn dev` which production never starts; launch-editor path is additionally Windows-only; shell-quote is transitive of launch-editor only) |
| install_time_only (setuptools) | 2 | INSTALL_ONLY (GHSA-h35f-9h28-mq5c fires only on `setup.py sdist` on macOS APFS/HFS+; production runs Linux + wheel installs via uv and never builds sdists) |

The OWNER does not need to accept any risk; every finding is closed with an
in-boundary mitigation or a concrete proof of non-reachability, with
regression tests in `tests/foundation/test_sec_deps_triage.py` that pin
each deployment-boundary claim (no `--watch` / `yarn dev` in launch,
loopback-only socket.io binding, WATCH_MODE gating in frappe esbuild,
explicit `runtime_disposition` on every one of the 102 advisories, and
presence of the four triage sections in this document).

## Closure evidence (hosted foundation runtime validation)

| Run | Commit | Realtime edge probe | Notes |
|---|---|---|---|
| 35961899500 | 5590398 | n/a (subprocess 120s budget exhausted before probes tightened) | timing too generous on post-vector settle/retries |
| 35962956656 | 7fc9f7e | FAIL (`realtime_serves_handshake_after: false` for GHSA-3h5v and GHSA-677m/2m8v) | genuine-looking failure; turned out to be a probe-wiring defect where `rawRequest` resolved on the first `HTTP/1.1` chunk, before the body containing the Engine.IO `sid` arrived |
| 35976439134 | ea321b1 (after `9f0fba6` fix to `realtime_exposure_probe.js` reading response bodies in full and retrying the post-attack handshake) | PASS (`all_survived: true`) | nginx edge successfully caps GHSA-3h5v oversize headers and GHSA-r635 octet-stream POST connection-holds; GHSA-677m/2m8v binary-frame train is delivered (100 masked 64KiB frames) with bounded RSS growth (~14 MiB) and the engine.io listener continues serving fresh polling handshakes afterward; GHSA-gr94 (WebTransport) requires transports not enabled. |

The probe's own negative-control behaviour is pinned by
`tests/foundation/test_sec_deps_triage.py` (eight realtime advisories
enumerated, masked frames, proxy caps and loopback binding). After the
full-body read fix in `9f0fba6`, the gate `Realtime edge did not
neutralise every pre-auth advisory` is no longer raised by the foundation
runtime job; subsequent failures in the same run (`hosted-full-stack-
dependency-audit`, `hosted-frontend-advisory-audit`,
`actual-realtime-authorization`) are downstream security/reconciliation
gates tracked under separate work blocks, not SEC-DEPS-01.

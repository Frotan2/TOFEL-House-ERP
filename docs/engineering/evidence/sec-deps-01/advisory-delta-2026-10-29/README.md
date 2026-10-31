# deepmerge source mitigation — 29 October 2026

Supplementary source overlay; production remains NO-GO. No installed customer files,
database, backup policy, keys, scheduler or update channel were changed.

Advisory: https://github.com/advisories/GHSA-gcqx-w48m-w2h4

The npm registry still publishes 4.3.1 as latest at inspection. The original
4.3.1 archive was downloaded from the public npm registry and its SHA-512
verified against the existing HRMS lockfile integrity. Its three JavaScript
entry points and MIT license are preserved as test fixtures. Exact input and
output SHA-256 values and unchanged publisher package.json are pinned in
`tools/foundation/deepmerge-hashes.json`. Both distribution fixtures are explicitly
tracked despite the repository's general dist-directory ignore rule.

`secure_deepmerge.py` changes the three destination assignments to
`Object.defineProperty` with enumerable, configurable, writable data properties.
This avoids invoking the inherited `__proto__` setter for both target copying
and source copying, preserving normal result prototypes and merge behavior.
Unknown versions/content, redirected package metadata, missing entry points,
symlinks/junctions and an empty scan fail. Required Education and HRMS frontend
roots must exist. HRMS must contain deepmerge. Education absence is accepted
only when its exact existing reviewed Tiptap overlay lock removes deepmerge;
the upstream Education graph must contain and patch it.
All discovered copies are preflighted before writes. Repeated apply is safe.

Product installs the upstream Education frontend using its frozen lock before
applying the overlay, compiles assets, then verifies and probes every installed
CJS/UMD distribution and records emitted frontend asset hashes. The final runtime
image recomputes that receipt and must match it exactly; the workflow uploads
`deepmerge-distribution-image` evidence. Foundation applies before build and
records post-build distribution/asset evidence. Native explicitly installs the
frozen Education frontend and applies/verifies/probes the same overlay; Native
does not compile frontend assets and makes no emitted-asset claim.

The 28 October scope-restricted NOT_REACHABLE disposition remains unchanged,
including the npm numeric alias. This directory adds no duplicate advisory
registration. The overlay is an additional source defense, not a replacement
triage exception or upstream version fix. Unknown advisories still fail closed.
The previous local b0e53d3 failure predates remote work@23dde16f, whose five
successful hosted gates used that 28 October scoped analysis. Those successes
do not qualify this supplementary source change.

Local regression tests reproduce the unmodified CJS exploit, then exercise
target, null-prototype source, nested and array payloads against all three
patched entry points. Ordinary nested merges, array concatenation, symbols,
merge.all and input immutability also pass. The index.js test supplies a small
mergeable-object helper; CJS/UMD exercise the actual standalone publisher code.
Metadata redirection, reinstall drift, missing consumers, linked consumers,
empty/unpatched verification and constructor/prototype payloads are covered.
One directory-symlink test requires privileges unavailable on this Windows
account; hosted Linux must execute it. Asset hashes identify compiled/shipped
bytes; they do not assert deepmerge survived tree shaking. Foundation's separate
Vite module-graph report records rendered module inclusion independently.

An independent adversarial source pass found and prompted fixes for duplicate
advisory registration, metadata redirection, hidden linked consumers, missing
Native enforcement, wrong Frappe public-asset paths and ignored dist fixtures.
The reviewer independently checked all four fixture hashes against the
integrity-verified publisher archive. This is source review, not Owner signoff.

Required next: independent source review and exact-revision Foundation/Product
image qualification, authenticated rebuilt kit, then final installed-image
acceptance. Local tests do not satisfy these release gates or authorize launch.

The first integrated candidate 4fafae3 passed Owned (2,894 tests, 23 Windows
skips) and Windows Smoke. Product then exposed native post-build public
dependency aliases; the next candidate confirmed the same pattern for Education.
Pinned [Frappe generate_assets_map](https://github.com/frappe/frappe/blob/988e54f3/frappe/build.py#L297-L327)
creates these aliases for every installed app with root node_modules.
The walker accepts only the finite seven shipped app names, each exact
`<app>/<app>/public/node_modules` alias pointing to that app's regular
`<app>/node_modules` tree it independently audits; arbitrary linked consumers
remain refused. A Linux regression checks all seven valid aliases,
tampered canonical code and redirected alias refusal. Foundation
40897652555 stopped earlier on an npm publisher HTTP 502 fetching the unchanged
Firebase archive, not an advisory waiver or overlay failure. New final-head
gates are required after the native-alias correction.

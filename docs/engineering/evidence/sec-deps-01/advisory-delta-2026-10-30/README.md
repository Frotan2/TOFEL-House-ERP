# URI decoder security backport — 30 October 2026

Foundation [40988559170](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40988559170)
failed closed on new advisory [GHSA-qr28-fpjm-wq7f](https://github.com/advisories/GHSA-qr28-fpjm-wq7f).
Upstream marks versions through 0.5.0 vulnerable and 0.5.1 fixed. The pinned
build graph still resolves CommonJS 0.2.2; upstream 0.5.1 is ESM, so simply
replacing its package version would break the existing `require()` contract.

`tools/foundation/decoder/` records immutable upstream commit
`58ed85f5adc7cfaee5e49e4d52b067f172d0bcb6`, source and payload SHA-256,
publisher 0.2.2 tarball SHA-512 integrity, original manifest/code hashes, and
the MIT license. The decoder body is unchanged from upstream 0.5.1. A separate
adapter exposes CommonJS and retains 0.2.2's plus-to-space behavior. No upstream
manifest, lock, version, accounting controller or security gate is weakened.

The installer validates **all** discovered copies before writing any, refuses
unknown bytes/manifests or hidden linked dependency roots, then replaces only
`index.js`. Verification resolves and executes each actual CommonJS entry point,
checks valid Unicode, URL/plus compatibility, type errors and no repeated
decoding of output, and runs both the repeated-malformed-byte and distinct-run
denial-of-service patterns in a child with a strict timeout.

Foundation applies before asset compilation and verifies after it. Native
applies to its real installed trees and verifies before completion. The Docker
build does the same, retaining an exact code receipt; Product Image verifies
that receipt and repeats the hostile-input probes inside the final image.
Raw advisory/version matches stay visible under the dated MITIGATED decision.
The immutable older register is retained. Unrelated packages and future
advisories receive no exception.

Local tests exercise ordinary publisher compatibility, hostile inputs,
tampered nested copies, redirected manifests, unpatched verification refusal,
and exact upstream-body reconstruction. Hosted builds, browser checks and
final downloaded image verification must still pass on the final commit.
**This source change does not authorize Production.**

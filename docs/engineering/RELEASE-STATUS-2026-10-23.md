# Release status — 2026-10-23 audit

## Decision

**NO-GO / production authorization REJECTED.** The provider-side qualification
has a locally built image and synthetic native workflow evidence,
but no externally published download, real customer-machine acceptance, or
Owner recovery ceremony is verified. Do not enter real student, payroll, or
financial data.

The initial audit snapshot was taken before Docker access was granted. The
qualification update below records the later provider-side evidence separately
so the historical findings are not silently rewritten.

## Provider qualification update (2026-10-23)

For source revision `b171902abb7bb61b31b27d54279cf72dd70d5eed`:

- The pinned Product image built successfully on the provider host. Its image
  manifest digest is
  `sha256:87d19595add86e09e9dc1e758d6b5896ce00b2b7fc60fd554d66970ea9d01524`.
- The image-inclusive package (subsequently withdrawn; see below)
  `TOEFL-House-ERP-Customer-ci-b171902abb7b.zip` passed manifest, sidecar,
  archive-integrity, allowlist, and identity checks. ZIP SHA-256:
  `47e4cec35374229ea50d68fd41418310833d10f17ee8b331d7b12c6abefe7b99`.
  The package is marked `TEST PACKAGE - NO REAL DATA` and
  `production_authorization=REJECT`.
- A disposable Frappe/MariaDB/Redis runtime booted the image; authenticated
  Administrator probes returned HTTP 200 for login, identity, home, Desk, and
  Student search.
- The native synthetic acceptance suite passed **624 checks, 0 failures** on
  the exact revision. It covered placement, admissions, enrollment, classes,
  timetables, attendance, tuition, finance, role desks, audit/access-control
  negatives, and native book stock receipt, Books-only sale, Payment Entry,
  return/credit, restocking, and GL reconciliation.
- The available computer-use environment had no browser surface, so no
  Chromium UI claim is made. The authenticated Frappe HTTP/Page-path checks
  are real runtime evidence, not a browser substitute.
- The package is not a GitHub Release asset and has no independent hosted
  artifact attestation or provider signature. Real Windows Docker Desktop/
  WSL2 hardware acceptance remains unverified.

The evidence-record commits `96f6257` and `5e2313f` are documentation-only.
The attempted replacement builds passed a mistyped Node SHA argument ending
in `d5`; the canonical matrix and downloaded file end in `d6`. The checksum
gate correctly rejected those arguments. The earlier attribution to BuildKit
was incorrect. Build inputs must be read directly from the canonical matrix.
The verified image/package above remains bound to `b171902`.

## Follow-up release audit

The earlier ZIP integrity checks did not establish installer compatibility or
release-host suitability. The `b171902` ZIP is **NOT DELIVERABLE**: its saved
Docker archive carries `toefl-house-erp-app:ci`, whereas the installer consumes
`:local`; its 2,803,979,202-byte ZIP also exceeds GitHub's under-2-GiB asset
limit. Preserve it as historical engineering evidence only.

Confirmed follow-up defects and remediation work:

- Derive and check archive identity from the embedded Docker manifest/config,
  use `:local` consistently, verify the manifest checksum, and verify the
  imported image identity before Compose starts.
- Reject oversized release assets before upload and reduce the runtime image
  by excluding build checkouts/intermediate build layers.
- Compile browser bundles on the provider and restore the provider manifest
  at startup. An isolated restart reproduced missing CSS referenced by the
  old manifest; startup must never need customer-side asset compilation.
- Add explicit HTTP `frappe.desk.desk_page.getpage` receipts for every role
  desk. The earlier 624 checks called the native Page loader in-process and
  exercised desk projections over HTTP; those scopes do not prove HTTP Page
  API delivery for all eight desks.

These fixes require the new image, packaging, native, browser and Windows
regressions to pass before their status can be marked qualified. The physical
Owner/customer acceptance and production holds remain unchanged.

The changes were pushed to canonical `main` as `eb4264f`. The Windows customer
package job [39942912709](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/39942912709)
passed, including the archive/manifest and loaded-image rejection cases. The
full owned suite on that revision ran 1,621 tests and found six lifecycle
simulations still expecting first-boot compilation plus a security contract
assuming a single-stage image. The simulations need real provider seed
fixtures; the Ghostscript exclusion is enforced in the final runtime stage
after every copy. Neither failed run is a release pass. The product image
and native jobs on that revision must be followed through to terminal state.

Native run [39942912690](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/39942912690)
finished with **634 business/security checks passing**, including all eight
authenticated `frappe.desk.desk_page.getpage` loads, delivered CSS, 12 positive
Page controls and 56 strict permission denials. Its downloaded report passed
the receipt verifier for `eb4264f6c7ada8a8f56f41c072cb593bb958bb8c`. Encrypted
isolated restore and post-restart checks also ran. The overall workflow still
failed its later source-integrity audit: native asset setup altered
`education/public/node_modules`. The setup must limit writes to the synthetic
served asset root; that source-integrity gate is retained.

The follow-up also requires all four canonical CI gates on the package's exact
revision before assembly/attestation/upload. A live read-only API probe rejected
the failed `eb4264f` revision as expected. Missing checks are dispatched only
after verifying the branch/tag still resolves to the selected SHA. This
orchestration and the revised native asset setup still require their next CI
run to finish; unit/contract results alone are not the release decision.

The canonical release blockers are GitHub issues [#12](https://github.com/Frotan2/TOFEL-House-ERP/issues/12),
[#35](https://github.com/Frotan2/TOFEL-House-ERP/issues/35), and
[#36](https://github.com/Frotan2/TOFEL-House-ERP/issues/36):

- #12 — actual Owner Windows install/lifecycle, backup/recovery, and private
  staff-device acceptance remain unverified.
- #35 — actual cashier/book-stock acceptance on a separate disposable Windows
  PC remains unverified. The hosted native code path already covers stock
  receipt, Books-only invoice, Payment Entry, return/credit, restocking,
  converted-student purchase, and negative authorization cases.
- #36 — the prior repository could prepare a package only from a local image
  and CI did not publish a customer image. This audit adds the provider/CI
  package assembly, identity manifest, image-label binding, attestation,
  artifact upload, and tag-based GitHub Release path. A provider-side local
  image-inclusive package is now verified, but issue #36 remains open until a
  permitted CI run publishes an independently downloadable artifact.

## Repository audit findings

The current `main` head at audit start was `e6776e6`. The tree contains the
native Frappe/MariaDB/Redis lifecycle, role desks, admissions, placement,
enrollment, teaching, attendance, tuition, payments, corrections, native
book commerce, audit receipts, security overlays, Windows GUI, and guarded
backup/restore code. The latest commits also corrected the eight real Frappe
Page asset directories to the names used by `Page.load_assets()`.

The main release risks are boundary evidence, not a hidden authorization
bypass: hosted CI is not a physical Windows computer; a fake-Docker Windows
smoke is not Docker Desktop/WSL2; a hosted backup is not the Owner's backup
drive/key custody; and a native synthetic book receipt is not cashier UX.

## Implemented in this audit

- `product/app.Dockerfile` now records the exact source revision and package
  version as image labels in addition to the LF-source contract.
- `tools/release/create_customer_package.py` assembles only the customer
  allowlist, refuses source/image identity mismatch, includes the dependency
  matrix hash, writes archive and manifest checksums, and produces a ZIP.
- The Windows provider packager writes and verifies the same release manifest;
  the Windows verifier checks the manifest before any image import.
- The Product image workflow builds with exact revision/version labels,
  exports a real image archive, attests the ZIP provenance, uploads the
  versioned artifact, and creates a GitHub Release asset only for an explicit
  `v*` tag.
- Windows CI synthetic packaging now exercises manifest creation and identity
  fields rather than only a bare image checksum.
- UTF-8 Windows customer-guide reads in the Python contract suite are now
  explicit, so the Dari guide is testable on a Windows host.

## Evidence run during this audit

- PowerShell parser for all customer launchers: **PASS**.
- Graphical launcher `-SmokeTest`: **PASS**.
- Package manifest and Windows installer contract tests: **19 PASS**.
- Product packaging contract suite: **101 PASS**.
- Workflow action pin suite: **9 PASS**.
- Node realtime, command-page, design-system, and role-desk suites: **PASS**.
- Docker daemon access at the initial audit snapshot: **NOT AVAILABLE**
  (named-pipe permission denied). Later provider qualification used an isolated
  temporary Compose project and did not reset existing Docker state, volumes,
  or customer data.
- Provider image build and package verification after the snapshot: **PASS**;
  see the exact revision, image digest, package hash, and synthetic-only
  status above.
- Native Frappe/MariaDB/Redis/HTTP synthetic acceptance after the snapshot:
  **624 PASS / 0 FAIL**; report retained outside the repository.
- Authenticated browser UI: **UNVERIFIED** because no browser surface was
  available in this environment; do not convert the HTTP result into a
  Chromium claim.
- Full Python tree on this Windows host: **not a release pass**. The run
  exposed platform-specific harness assumptions (POSIX `grep`, POSIX paths
  interpolated into Python heredocs, and Unix mode-bit assertions) plus tests
  requiring native Linux/Frappe fixtures. These must be separated into
  explicit POSIX-only checks or made Windows-portable before claiming a clean
  local cross-platform suite.

## Required next gates

1. Run the Product image workflow on the final permitted `main` SHA and retain
   the image ZIP, manifest, SHA-256 files, attestation, and run SHA. The local
   provider package is evidence, not the hosted customer download.
2. Download the hosted artifact independently and verify the manifest/image
   identity before a disposable Windows Docker Desktop + WSL2 test.
3. Complete the real Windows install, login, Stop/Start, reboot, Repair and
   persistence procedure with synthetic records.
4. Complete manual book cashier acceptance for #35 with synthetic books,
   stock, invoice, payment, return, restocking, and role-denial evidence.
5. Keep Owner backup/recovery, key custody, Task Scheduler, Tailscale, and
   production authorization on HOLD until the owner-approved procedures pass.

Passing CI does not close #12 or #35 and does not authorize production.

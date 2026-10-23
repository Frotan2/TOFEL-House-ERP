# Release status — 2026-10-23 audit

## Decision

**NO-GO / production authorization REJECTED.** The repository has an
engineering path for a provider-built, image-inclusive Windows customer kit,
but no exact-head downloadable artifact or real customer-machine acceptance
was available at the start of this audit. Do not enter real student, payroll,
or financial data.

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
  artifact upload, and tag-based GitHub Release path. It is **not complete
  evidence** until CI actually produces and independently downloads/verifies a
  real image-inclusive artifact.

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
- Docker daemon access from this workspace: **NOT AVAILABLE** (named-pipe
  permission denied; no containers, volumes, or customer data were changed).
- Full Python tree on this Windows host: **not a release pass**. The run
  exposed platform-specific harness assumptions (POSIX `grep`, POSIX paths
  interpolated into Python heredocs, and Unix mode-bit assertions) plus tests
  requiring native Linux/Frappe fixtures. These must be separated into
  explicit POSIX-only checks or made Windows-portable before claiming a clean
  local cross-platform suite.

## Required next gates

1. Run the Product image workflow on this exact tree and retain the image ZIP,
   manifest, SHA-256 files, attestation, and run SHA.
2. Download the artifact independently and verify the manifest/image identity
   before a disposable Windows Docker Desktop + WSL2 test.
3. Complete the real Windows install, login, Stop/Start, reboot, Repair and
   persistence procedure with synthetic records.
4. Complete manual book cashier acceptance for #35 with synthetic books,
   stock, invoice, payment, return, restocking, and role-denial evidence.
5. Keep Owner backup/recovery, key custody, Task Scheduler, Tailscale, and
   production authorization on HOLD until the owner-approved procedures pass.

Passing CI does not close #12 or #35 and does not authorize production.

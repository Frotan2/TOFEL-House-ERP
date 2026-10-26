# Windows acceptance findings — 2026-10-26

This is an in-progress engineering record, not completed staff acceptance.
Production remains **NO-GO**.

## Tested initial package

- Source: `2b29571702a75c5f0c32d89e5f2897e77246bb36`.
- Supplied inner customer ZIP SHA-256:
  `261a4f3a04090524842b04bd83a41fca3db308f9b121050a26fe2b71ed11e417`.
- GitHub build attestation verified against this repository and Product image
  workflow; the signer source SHA matches the package.
- Windows package image integrity and loaded-image identity verifiers passed.
- Windows 10 Pro build 19045; Docker Engine 29.9.2. Docker initially contained
  no containers or named volumes. Installation uses a new workspace folder
  and synthetic acceptance storage; no existing customer database is used.
- Image import completed. First installation is still downloading the pinned
  database/cache dependencies; no role/business workflow is certified yet.

## QA-001: Fresh storage falsely reported as indeterminate

The shipped read-only PC check treats every failed single-volume inspection
as an unverifiable inventory, including a genuinely absent volume. An empty
Docker engine therefore reports that existing storage cannot be ruled out.

The corrected check uses a successful name inventory to distinguish verified
absence from an API failure. Existing credentials still require a present
database volume; a successful empty inventory never permits that existing
installation to be treated as healthy. No credential or volume is written.
Four real Windows PowerShell regressions cover fresh/foreign storage,
existing-volume/missing-credential refusal, API failure and missing-volume
with existing credentials. The targeted package/preflight suite passed
22 tests on this Windows host.

## QA-002: Process-wide roster accessor replacement

Inspection confirmed that `_roster_read()` temporarily replaces Education's
module-global roster accessor while a guarded attendance command is active.
This is a concurrency-sensitive permission boundary; no external network
exploit is asserted solely from that observation.

The fix uses Frappe's owned Student Attendance controller extension. Only
membership validation inside the current actor's request-local teaching
command uses a parameterized, active-member lookup for that document's
native scheduled group. Every other caller retains native read permission
checks. Date, duplicate and holiday validation remain inherited from the
pinned Education controller; no upstream core file is edited.

The legacy lexical scope no longer replaces any global accessor. Thirty
targeted tests passed, including concurrent request isolation, inactive and
foreign student denial, scheduled-group resolution, refused-site denial and
native hook wiring. Native runtime tests and independent security approval
are still required on the corrected revision.

## Acceptance boundaries

Windows screen capture failed during the launcher attempt; a launched process
is not proof of successful graphical installation. The package's own installer
is running through its supported worker script. Browser transaction, native
accounting, restart/recovery, staff-device and independent reviewer evidence
must be recorded separately. Existing hosted results do not qualify source
changes made during this acceptance run.

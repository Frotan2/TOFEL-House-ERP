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
- Image import and pinned database/cache dependency downloads completed.
  Native initialization subsequently completed;
  all seven services are ready and the actual browser shows Sign In. No
  role/business workflow is certified yet.

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

## QA-003: CMD readiness never completes with real Docker output

The actual Windows installation reached HTTP 200, five healthy services and
running worker/scheduler processes, but its installer kept waiting. The
exact shipped `findstr /x` pipe returned 1. On this Windows host,
`healthy\n` returns 1 whereas `healthy\r\n` returns 0; the real Docker CLI
emits LF-only output. Install, Start and Repair all used the affected checks.

All three paths now invoke one read-only structured PowerShell probe. It
requires seven exact running states, five exact healthy states, successful
Docker inspection and HTTP 200. It does not accept an `unhealthy` substring
or a partial service list. Nineteen synthetic service/HTTP cases and 91
targeted packaging tests passed. The corrected probe also returned success
against the actual healthy Windows ERP. Windows CI now emits LF-only mock
Docker state output, so its package lifecycle exercise covers the real
framing that the earlier CRLF-emitting mock missed.

The corrected official package and graphical lifecycle still require retest;
this live probe result is not a completed installation/role acceptance claim.

## QA-004: Native setup first-user roles prevent successful login

The actual browser wizard created the company and set `setup_complete=1`,
then reported failure. Its trace reaches the Guardian scope guard during
`login_as_first_user`: native Frappe defaults grant the initial account every
non-automatic role, including Student and Guardian without canonical identities.
The guard correctly refuses this combination; it must not be bypassed.

An owned `setup_wizard_success` hook now narrows the separate initial account
before native login to System Manager only. It grants no business role and
refuses portal-linked identities, existing role profiles, disabled users,
reserved accounts and calls outside Administrator's native wizard. No native
core file or student/guardian permission guard changes. Ten hook regressions
and the existing guard suites passed (37 tests). Applying the same qualification
to the failed synthetic setup account allowed an actual browser login; a fresh
wizard and official rebuilt package still require acceptance on the new SHA.

Independent synthetic role accounts were created using native User records.
The company's unused incorrect initial fiscal year was disabled; the setup
account then created and saved company-scoped SYN-1405 through the browser,
with verified dates 2026-03-21 through 2027-03-20. This is setup evidence only,
not tuition, payroll or monthly-close acceptance.
## QA-005: Same-origin realtime ingress and internal authentication callback

Actual browser console errors showed Engine.IO requests reaching Gunicorn at
the browser origin; the native production client does not use port 9000 unless
the development server is enabled. There was no production ingress forwarding
`/socket.io/`. The separate realtime container also tried to authenticate via
the browser's loopback origin inside that container, rather than the web service.

The owned Node ingress now streams native HTTP traffic to private loopback
Gunicorn and forwards polling/WebSocket traffic to the configured realtime
service. A small owned realtime launcher selects the product site and pins
native authentication callbacks to the internal web service; no request origin
can choose that destination. Native authentication and room authorization remain
unchanged. As in the pinned Bench nginx template, same-origin polling receives
an Origin header when the browser omits it; explicit foreign origins remain
unchanged and rejectable. No development mode or authentication bypass is used.

Six actual HTTP/upgrade wire tests passed, including bidirectional upgrade bytes,
native refusal propagation, destination pinning and Origin handling. The 108
targeted package/setup/workflow tests passed. On the isolated source preview,
a real native Course Owner login upgraded to WebSocket and received a marker
published only to that user's native room. The actual browser reload also
authenticated to native realtime, confirmed by the installed security handler.
Hosted browser qualification now requires an authenticated realtime connection.

These are source-preview results over the earlier image, not acceptance of a
new official package. The original test web container remains preserved and
the production site remains deactivated.

## QA-006: Owner fee creation fails in native dependent Item writes

The actual Course Owner form failed because Education's Fee Category controller
inserts and saves its dependent Item without inheriting the outer document's
permission flag. The transaction rolled back: neither the category nor its
Item existed afterward. Adding Stock/Item roles to the Owner would widen access.

The correction uses a request-local scope for one newly named, non-stock sales
item in Fee Component, only inside the already authorized create-fee-type
command. An owned Item mixin rechecks the bound authority and allows only its
create/write operations. Native Education still creates the Item, maintains its
defaults and runs all native validation; no upstream function is replaced.
Existing Item-name collisions are refused before any mutation. Read, delete,
other items, other users and calls outside the command retain native permissions.

The same real browser transaction then completed. Native readback verified
`SYN Tuition` and its Item were created by the separate Course Owner. A native
permission readback confirmed that account still cannot create, read or write
Items directly. The fee scope, collision and configuration regressions passed
(110 tests); hosted native qualification now repeats the minimal-role workflow.

The browser also exposed that the first fee plan had no creation action: edit
actions existed only after a plan already existed. Active, anchored levels now
offer Define fee plan once the current academic year and an item-backed fee type
exist. Existing plans retain their existing edit path. A projection-world test
covers first-plan readiness and missing prerequisites. A real first-plan retry
then exposed an empty Components insertion: the native structure was being
inserted before its required first component was appended. New structures now
remain unsaved until that component is present; native validation still runs.
The fake lifecycle backend now enforces that native mandatory table as well.

The actual browser saved GE plan `EDU-FST-2026-00001`, one SYN Tuition component
for AFN 5,000 in SYN-1405, under the independent Owner account. Native Education
also warned that Fee Category accounting defaults still need configuration;
this remains a setup item before money workflow acceptance.

## Remaining acceptance boundaries

Windows screen capture failed during the launcher attempt; a launched process
is not proof of successful graphical installation. The package's own installer
was exercised through its supported worker script; its confirmed readiness bug
prevented completion, so only that stuck test wrapper was stopped. Browser transaction, native
accounting, restart/recovery, staff-device and independent reviewer evidence
must be recorded separately. Existing hosted results do not qualify source
changes made during this acceptance run.

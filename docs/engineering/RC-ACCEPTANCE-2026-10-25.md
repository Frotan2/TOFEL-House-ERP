# Source release candidate acceptance — 2026-10-25

**State:** engineering qualification in progress; production authorization remains
`REJECT`. This procedure uses an isolated Windows 10/11 Docker Desktop test
machine or VM, disposable Docker context and synthetic records. It must never
target an existing TOEFL House installation. The extracted
`ci-9c9ec48a6ead` customer package is a read-only reference: its manifest says
`production_authorization: REJECT`, and its `ci-*` version is outside the
date-versioned update channel. Do not change its files or use it as an update
source.

## 1. Source and package identity

1. Record `git rev-parse HEAD` and `git status --porcelain`. Require a clean
   tree and the exact SHA used by all hosted jobs, image labels, gate receipt,
   package manifest and attestation. Do not substitute an earlier green run.
2. On the disposable host, record `docker info --format
   '{{.ServerVersion}} {{.OSType}} {{.Architecture}}'`, `docker ps -a`,
   `docker volume ls`, and `docker image ls`. Require no existing TOEFL House
   containers, volume or `product/data` in the intended test location. Stop if
   an existing installation appears. Use a distinct test PC or Docker context;
   the fixed Compose names preclude sharing one daemon with a real site.
3. Verify the downloaded outer Actions artifact and its GitHub provenance,
   then the customer ZIP SHA-256, embedded manifest, image archive digest,
   image labels/config digest, four exact-SHA gate receipts, allowlist and
   TEST/REJECT labels. Record only hashes, IDs and pass/fail, no site data.

## 2. Source and runtime gates

Run these on the candidate SHA. The pinned dependency versions are in
`.github/workflows/owned-suite.yml` and `tests/security/requirements-ci.txt`;
the latter hashes cover Linux wheels. On Windows use an isolated environment
with the same versions and record platform wheel hashes separately.

```text
ruff check .
python -m unittest discover -s tests -t . -q
node tests/foundation/test_realtime_guard.cjs
node tests/foundation/test_command_pages.cjs
node tests/foundation/test_design_system.cjs
node tests/foundation/test_role_desks.cjs
powershell -NoProfile -ExecutionPolicy Bypass -File tests/foundation/windows_update_failure_probe.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "product/windows/Update TOEFL House ERP.ps1" -SmokeTest
```

The exact-SHA Native lifecycle, Foundation runtime, Product image and Windows
customer-package jobs must also pass. Native qualification must include the
synthetic teaching `Additional Salary` to submitted HRMS `Salary Slip` bridge,
while leaving payroll tax, payable account and real payment policy unclaimed.
The product image job must observe the actual synthetic Docker daemon through
the root broker and deny direct Docker access from the `frappe` account.

## 3. Disposable Windows customer journey

Use a newly verified prebuilt package for this candidate, extracted to a new
folder on the disposable machine. Follow its Owner Readiness Guide and GUI:
Check This PC, Install, Open / Start, private login, Stop, Start, Windows
reboot, and authorized Repair. Record durations, package/image IDs, and that
synthetic data persisted after every restart. Test separate staff logins for
placement, admission, enrollment, classes, attendance, tuition billing and
payment, book stock sale/payment/return/restock/cash refund, permission denials
and branch scope. Use a separate synthetic fixed backup drive and authorized
isolated restore; never restore over the test's active site. Validate private
Tailscale staff access and non-tailnet denial on real devices.

## 4. Two-version updater exercise

Use two provider-built, prebuilt images from exact source revisions in the
disposable environment: a baseline built from `9c9ec48` with synthetic dated
version `2026.10.24`, and this candidate with a later dated version. These are
**lab builds**, not the extracted customer package. Sign a lab-only update
bundle with an ephemeral RSA key using `tools/release/create_update_bundle.py
bundle`; provision only its test trust store and local HTTPS allowlist in this
VM. Use synthetic, verified backup and recovery authorization as required by
the engine. The test manifest must identify the exact image archive, source,
compatibility window and lab authorization. Never copy the lab key, trust
store, enabled channel or authorization into a real installation.

1. Confirm baseline image/site login and synthetic census. Run Check for
   Updates with baseline code; it must validate the signed manifest and
   archive without a Docker-socket mount in the old engine.
2. Run Install Update with explicit confirmation. Capture the Docker event
   order: old engine re-verifies the archive; candidate image imports while
   services run; its config digest matches the signed target; the old Compose
   tag is restored; the candidate's broker issues preflight, authorize and
   recheck against live containers, volume, site files, image and journal;
   only then do services stop, the candidate tag apply and migrations run.
3. Require two successful `bench migrate` replays, unchanged native data
   census, installed apps and role desks, successful HTTP login and persistent
   synthetic records after restart. Inspect the final journal and one-use
   transaction marker. A second apply with that transaction must refuse.
4. On separate disposable snapshots, induce missing Docker socket/broker,
   replaced volume/container, changed site credentials/config, changed image
   or journal, archive corruption, stop failure, import failure, migration
   failure and interrupted apply. Each must refuse at its intended boundary;
   no failure may start Compose automatically or recreate the database. A
   migration-started failure must keep `recovery-required` until an authorized
   isolated recovery is proved. Record redacted blocker codes and Docker
   state, not secrets or raw logs.

## Release decision

Issue #12 physical lifecycle/recovery/staff access, #35 cashier/stock, #36
independently verified package and installation, #40 updater, #71 independent
review/governance, Owner policy for actual payroll/statutory/payable terms, and
explicit Owner production approval remain separate acceptance gates. A hosted
or synthetic pass cannot resolve those by implication. Keep the channel
disabled and production `REJECT` until evidence and authority are recorded.

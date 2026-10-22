# Engineering qualification note — 2026-10-22

This note records **engineering evidence**, not production authorization.

## Qualified in hosted synthetic environments

- **Isolated restore target:** native-lifecycle run
  [39836321651](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/39836321651)
  passed on code head `1f84aee987ac77b3d93ee6202731d8489e99b912`. The source
  backup is copied into a new `placement-restore.localhost` target with a
  distinct database and a separate mini-Bench/site-data root outside the source
  Bench. The source `product/data` volume is never mounted or used.
- **Restore integrity:** the verifier compares all 14 representative DocTypes by
  count, record-name digest **and full row-value digest**; it verifies public and
  private File bytes, Frappe File metadata, file size/mode/UID/GID, encrypted
  source-artifact hashes, and restored-site HTTP/login behavior after a real
  Gunicorn restart.
- **Failure/cleanup behavior:** the same run creates a second isolated target,
  supplies a deliberately wrong backup key, requires the restore to fail,
  verifies native temporary restore staging is cleaned, verifies the source
  site configuration and preserved encrypted backup hashes did not change, and
  removes only that disposable failure target.
- **Credential boundary:** restore and site-creation credentials are supplied on
  stdin or protected option files, not child argv; retained evidence is
  redacted and the synthetic harness rejects local/production execution.
- **Owner-policy restart persistence:** the same native-lifecycle run re-read all
  eight owner-configurable policy resolvers after a real service restart and
  exercised consumer/off-switch/fail-closed behavior with rollback-confined
  synthetic fixtures.
- **Product image lifecycle:** product-image run
  [39836321829](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/39836321829)
  passed on the same code head, including the isolated-restore safety contracts
  plus the disposable product-image lifecycle and Windows source-normalization
  checks.
- **Owned quality gate:** owned-suite run
  [39836321833](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/39836321833)
  passed static analysis, the complete Python test tree, and Node suites on the
  same code head.

The explicit restore engineering release note is
[RESTORE-QUALIFICATION-RELEASE-2026-10-22.md](RESTORE-QUALIFICATION-RELEASE-2026-10-22.md).

## Explicitly not qualified by this note

The Owner's actual Windows PC, Docker Desktop/WSL lifecycle, real backup drive,
Task Scheduler, key custody, retention execution, real Tailscale devices and
production recovery are **not** qualified by hosted CI. Owner backup/restore,
activation/deactivation and production authorization remain on HOLD/REJECT
until the separate Owner-machine acceptance gates are completed.

CI qualification closes the engineering defect that an isolated restore
rehearsal was missing. It does **not** authorize any destructive or recovery
action on the operational installation.

# Engineering qualification note — 2026-10-22

This note records **engineering evidence**, not production authorization.

## Qualified in hosted synthetic environments

- **Isolated restore target:** native-lifecycle run
  [39437595961](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/39437595961)
  restored encrypted artifacts into `placement-restore.localhost` with a
  distinct database in an ephemeral Bench. Verification covered representative
  database records, public and private file bytes, Frappe File metadata,
  encrypted-artifact hashes, filesystem size/mode/UID/GID, and target behavior
  after a real Gunicorn restart.
- **Owner-policy restart persistence:** the same native-lifecycle run re-read
  all eight owner-configurable policy resolvers after service restart and
  exercised the consumer/off-switch behavior with rollback-confined synthetic
  fixtures.
- **Product image lifecycle and Windows source normalization:** product-image
  run [39597802206](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/39597802206)
  passed encrypted backup/restore, browser acceptance, restart persistence,
  upgrade/rollback, performance checks, and the Windows stale-worktree
  EOL-normalization job.

## Explicitly not qualified by this note

The Owner's actual Windows PC, Docker Desktop/WSL lifecycle, real backup drive,
Task Scheduler, key custody, retention execution, real Tailscale devices and
production recovery are **not** qualified by hosted CI. Backup/restore,
activation/deactivation and production authorization remain on HOLD/REJECT
until the separate Owner-machine acceptance gates are completed.

CI qualification therefore removes the old claim that the *engineering*
isolated-restore and policy-restart mechanisms are missing; it does not
authorize any destructive or recovery action on the operational installation.

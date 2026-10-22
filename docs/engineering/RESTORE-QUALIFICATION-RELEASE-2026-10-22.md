# Restore qualification release — 2026-10-22

**Engineering status: QUALIFIED. Owner-machine status: HOLD.**

This release closes the repository engineering gap for a safe isolated restore
rehearsal. It does not authorize restoring, replacing, cleaning or modifying the
operational Owner site.

## Accepted evidence

Native lifecycle run
[39836321651](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/39836321651)
passed on commit `1f84aee987ac77b3d93ee6202731d8489e99b912`.
Product-image run
[39836321829](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/39836321829)
and owned-suite run
[39836321833](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/39836321833)
passed on the same commit.

The accepted rehearsal:

1. uses only synthetic data on a GitHub-hosted disposable runner;
2. creates a new restore site, distinct database and a separate mini-Bench
   site-data root outside the source Bench;
3. never mounts or targets the operational `product/data` volume;
4. preflights free space before target population;
5. restores from verified disposable copies while preserving the encrypted
   source backup set byte-for-byte;
6. compares representative database data by count, record-name digest and full
   row-value digest;
7. verifies public/private file bytes, Frappe File metadata and filesystem
   size/mode/UID/GID;
8. restarts the real Gunicorn web service, authenticates to the restored target
   and re-verifies restore and policy state;
9. exercises a second isolated target with a deliberately wrong backup key and
   requires fail-closed behavior;
10. proves temporary restore staging is cleaned, source configuration/backups
    remain unchanged and cleanup is confined to the disposable failure target;
11. keeps database/admin/encryption credentials out of child argv and redacts
    retained evidence.

## Release boundary

This engineering release does **not** lift the Owner PRESERVATION / RESTORE
HOLD. The real Windows installation, separate backup drive, Task Scheduler,
key-custody ceremony, actual Owner backup, Owner recovery rehearsal and
production authorization remain separate acceptance gates. Do not run an Owner
restore until those gates are explicitly completed and authorized.

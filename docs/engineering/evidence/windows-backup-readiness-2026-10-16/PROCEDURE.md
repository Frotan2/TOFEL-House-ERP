# Isolated Windows and backup validation procedure (owner-run, UNVERIFIED)

**Status: not run.** Nothing in this procedure has been executed. Every "Expected"
line is derived from source (see README.md). Only an owner-run result on the
isolated machine counts as evidence.

## Hard rules

1. **Do not run any step on the production PC** that holds the real site, `product\data`,
   real backups, or real keys. The hold in `product/windows/VALIDATION.md` stays in force there.
2. Use a **separate Windows 10/11 Pro or Enterprise machine or VM** with Docker Desktop,
   a fresh clone of the repository at the release commit, and a **separate virtual disk
   or USB drive** labelled `SYNTHETIC-BACKUP`. Name the test site with a synthetic name only.
3. Data is **synthetic**: create test records yourself. Never import real student,
   staff, payment, or identity data.
4. Generate **test keys on the test machine only** (T9). Do not reuse production keys.
5. Return only a results table (step, PASS/FAIL, one-line observation, counts). Do not
   return keys, passphrases, passwords, the `backup_encryption_key`, the receipt contents,
   or full paths that identify a person. Record results in `RESULT-<date>.md` in this folder.

## Preconditions

| # | Check | Expected |
|---|---|---|
| P1 | `git rev-parse HEAD` in the clone | Equals the release commit under review. |
| P2 | Repository tests on the clone: `python -m unittest discover -s tests -t .` | 0 failures, 0 skipped. |
| P3 | `Test Fresh Installation.ps1` on the clean machine | `Fresh installation storage check passed.` and exit 0. |
| P4 | The `SYNTHETIC-BACKUP` drive is a separate fixed volume with free space ≥ 5 GB | Visible in File Explorer as a separate drive letter. |

## T1 Install (once)

- **Action:** double-click `Install TOEFL House ERP.cmd`; keep the window open until done.
- **Expected:** the build completes; the `Activate` route and login page are reachable.
- **Record:** PASS/FAIL, exit status, duration.

## T2 First boot, login, Course Owner account

- **Action:** open the browser, sign in as the synthetic Course Owner account.
- **Expected:** the desk loads; no error page.

## T3 Stop and start

- **Action:** `Stop TOEFL House ERP.cmd`, then `Start TOEFL House ERP.cmd`.
- **Expected:** stop says `TOEFL House ERP has stopped.`; start reports all services healthy; the
  synthetic record created in T2 is still present.

## T4 Repair

- **Action:** `Repair TOEFL House ERP.cmd`, wait several minutes.
- **Expected:** services restart; the browser opens to the login page; the desk loads;
  the synthetic record is still present.

## T5 Reboot persistence

- **Action:** restart Windows completely (not sleep). After login, run `Start TOEFL House ERP.cmd`.
- **Expected:** the site comes back with the same synthetic record and the same Course Owner
  account. No data reset, no new password prompt for the database.

## T6 Interrupted backup recovery

Run this only on the isolated machine.

- **Action A (interruption):** start `Backup TOEFL House ERP.cmd` against `SYNTHETIC-BACKUP`
  after an owner-configured policy exists (see T7 for configuration). While the copy phase
  is running, stop Docker Desktop (or disconnect the synthetic drive).
- **Expected A:** the script reports a failure. Inspect `SYNTHETIC-BACKUP\TOEFL-House-ERP-Backups`:
  no completed set folder exists for the interrupted run, and no `.staging-*` folder
  remains (the failure path removes it).
- **Action B (leftover sidecar):** if a plaintext `*-site_config_backup*.json` is left in
  `product\data\sites\toeflhouse.localhost\private\backups`, run `Backup TOEFL House ERP.cmd` again.
- **Expected B:** the run is refused with the message about pre-existing sidecars and deletes nothing.
  Move that synthetic sidecar to a quarantine folder on the test machine, then rerun.
- **Expected after rerun:** a single complete set, verified, and the receipt updated.

## T7 Retention (keep count and deletion ordering)

- **Setup:** in the **Configuration desk → Backup & Recovery** of the TEST site only, configure a
  synthetic policy: keep count `3`, behaviour `Delete valid older sets beyond keep count`,
  a test schedule time, and the test public recovery key from T9. Record the policy hash.
- **Action:** run `Backup TOEFL House ERP.cmd` five times, one after another, with distinct
  synthetic record edits in between.
- **Expected:** after the fifth run, `SYNTHETIC-BACKUP\TOEFL-House-ERP-Backups` contains exactly
  **3** set folders: the newest, and the two before it. The oldest two are removed. Each
  remaining set has a `manifest.json` that validates, and the newest set is the one named in
  the receipt. No set is deleted that is not older than the keep window.
- **Negative:** set the behaviour to `Preserve all valid backup sets` on a second test
  site copy and run twice. **Expected:** no set is deleted.
- **Known gap (F1):** the native folder `product\data\sites\toeflhouse.localhost\private\backups`
  is **not** rotated by this procedure. Record how many native sets exist after T7 (count
  only). **Expected:** it grows by one per run. This is the defect the owner must decide before
  release. A PASS here confirms F1, it does not clear it.

## T8 Integrity and restore rehearsal (synthetic only; no production restore)

- **Action:** on the isolated machine only, copy one committed set to a scratch folder. Verify each
  artifact's SHA-256 against `manifest.json`. Then decrypt the set's site-config artifact with the
  **test** private key (T9) into the scratch folder and confirm it parses as JSON.
- **Expected:** every hash matches; decryption with the test key succeeds; decryption with a
  wrong key fails. Do not restore into `toeflhouse.localhost`. A full restore is **not** claimed by
  this procedure, because no qualified isolated restore runner exists (F2).

## T9 Key custody and quorum (test keys only)

- **Action:** generate an OpenPGP test keypair on the test machine (a test identity, no real names).
  Publish only the public key to the test ERP. Export the private key to a file on a separate
  USB stick. Remove the private key from the PC after the test.
- **Expected:** `SYNTHETIC-BACKUP` contains no private key and no plaintext `backup_encryption_key`
  outside the native folder. Search the drive for `PRIVATE KEY` and for the test passphrase by name
  only. Expected: 0 hits.
- **Quorum:** with the custodian count the owner sets under owner action A4 (README F3), a test with one
  custodian's key must fail to recover and two keys must succeed. Record the custodian count
  you actually used. Do not use real custodians' keys.

## T10 Same-PC drive boundary (documented risk, F4)

- **Action:** with the synthetic drive attached to the same test PC, note that the drive and the
  live site share a machine. Record the result of T7 and T8 in one line. Do not claim off-site protection.
- **Expected:** a single-machine failure is recorded as lost data in the owner package until off-site
  backup (D14, deferred) exists.

## Result record

For each step: PASS, FAIL, or NOT RUN, with the date, the commit SHA, the Windows version,
and one-line observations. A single FAIL in T1–T9 blocks the Windows and backup gate. A
NOT RUN is not a pass. Do not mark any step PASS from this document alone.

## Owner decisions this procedure depends on

These are new decisions that are not yet in `docs/owner-decisions.json`. They must be recorded there by the owner before release.

- **Native staging rotation (README F1):** keep native sets, rotate them beyond the keep count, or move native output off the product data volume.
- **Recovery custodians and quorum (README F3):** owner action A4 in `OWNER-ACCEPTANCE-PACKAGE.md`.
- **Same-PC local-only backup until off-site exists (README F4):** owner acceptance, with off-site backup (D14) deferred.
- **Business values (retention count, schedule time):** owner action A3. This procedure uses test values only.

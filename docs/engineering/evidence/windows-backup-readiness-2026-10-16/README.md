# Windows and backup readiness review — 2026-10-16

Status: **source review complete; machine validation UNVERIFIED.** No Windows,
Docker, or backup-drive test ran in this sandbox. Nothing here touches the
owner's site, data, backups, keys, or credentials. Every claim below was read
from the repository source at the reviewed commit. The owner-run isolated
procedure is in [PROCEDURE.md](PROCEDURE.md).

Reviewed sources: `product/windows/Backup TOEFL House ERP.ps1` (lines cited),
`product/backup.py`, `product/windows/VALIDATION.md`, `Test Fresh Installation.ps1`.

## What the code does (verified in source)

| Stage | Behaviour | Where |
|---|---|---|
| Preflight | Refuses if a plaintext `*-site_config_backup*.json` sidecar is already in the native folder, and asks for secure review. Never deletes it. | ps1 ~line 468 |
| Native backup | Enables `encrypt_backup`, runs `product/backup.py` in the web container. Frappe's own cleanup is disabled so the adapter does not delete native sets. | backup.py `_native_backup` |
| Staging verification | Each native artifact must carry a GPG symmetric packet (`:symkey enc packet:`) and the expected name. | backup.py `_assert_gpg_encrypted`, `_verify_and_publish` |
| Drive copy | Copies to `<drive>\TOEFL-House-ERP-Backups\.staging-<guid>`. Each copy is SHA-256 and size checked against its source. The site config is wrapped under the **public** recovery key (`*-site-config.gpg`). Any plaintext sidecar in the set refuses the backup. | ps1 ~lines 527–670 |
| Commit | Writes `manifest.json` (schema 2, per-artifact SHA-256 and bytes), then `Move-Item` staging → set root. Refuses to overwrite an existing set. Failure removes only the staging folder. | ps1 ~lines 640–676 |
| Post-commit | Re-hashes every committed artifact against the manifest. Removes the native plaintext sidecar of this run only. | ps1 ~lines 676–688 |
| Task | Registers and verifies the daily task (action, time, interactive user, one trigger). | ps1 ~lines 690–715 |
| Retention | Only when `retention_behavior = Delete valid older sets beyond keep count` (D17). Sorts valid manifests newest first, keeps the new set and the protected receipt set, deletes the rest. A new set not in the keep window aborts before any delete. Manifests that are not valid are never deleted. | ps1 lines 204–221, 722–725 |
| Receipt | Written to `product\data\activation\backup-receipt.json` only after the above. | ps1 lines 226–233 |

Deletion ordering is therefore: **verify new set → commit → verify committed hashes → remove this run's plaintext sidecar → verify task → rotate older sets → write receipt**. The new set is never deleted by its own run, and rotation never runs before the new set is committed and hash-verified. Confirmed by reading the code order; not run.

## Findings

| # | Finding | Severity | Status | Owner action or fix |
|---|---|---|---|---|
| F1 | **Native staging folder is never rotated.** Every run leaves a full encrypted native set in `product\data\sites\<site>\private\backups` (database, public files, private files, site config). The script removes only the plaintext sidecar (ps1 line 688). Retention (lines 722–723) rotates only the drive set. The folder therefore grows by one full set per run on the same PC's data volume. | High (disk exhaustion; more encrypted copies than the keep count the owner chose under D17). | **OPEN. Blocker for the retention gate.** Not fixed here: deleting from the owner's data folder needs owner authority and a Windows run to validate. | Owner decision required (new; not yet in owner-decisions.json), D17 applied to the native folder. Proposed fix: after the drive set is committed and rotated, delete native sets of this site older than the newest committed set, using the same keep count and the same verified-manifest rule. Needs a Windows regression run before any release. |
| F2 | **Integrity is checked at write time, not at restore.** Drive sets record SHA-256 per artifact and are re-hashed after commit. Native artifacts are checked only for the GPG packet, not decrypted. No restore verification exists, and the restore path is unqualified (VALIDATION.md "Future restore target"). | Medium | OPEN. Restore is not a current release capability. | Synthetic decrypt-and-hash rehearsal in PROCEDURE.md T8. Restore must not be claimed until a qualified isolated restore runner exists. |
| F3 | **Key custody.** Native backups are GPG symmetric under `backup_encryption_key`, which lives in the site config on the same PC. The drive set wraps the site config under the owner's public recovery key, so the private recovery key must sit outside the PC with named custodians. The custodians and quorum are not defined in the repo (LAUNCH-RUNBOOK §67, §104). | High (decides whether a stolen drive is recoverable only with custodians) | OPEN. Owner decision. | Name custodians and quorum (owner decision). Store the private recovery key offline. Test recovery with synthetic keys only (PROCEDURE.md T9). |
| F4 | **Same-PC backup drive.** The drive is on the same PC as the product. A fire, theft, or ransomware event on the PC can take both the live site and every backup drive set. | High (resilience; accepted per D14/D17 only as local backup) | ACCEPTED LOCAL-ONLY RISK, to be restated by the owner. D14 defers off-site backup. | Owner acknowledges in the package (owner action A2). Off-site destination is deferred future scope and not a gate. |
| F5 | **Interrupted runs fail closed.** A failure during copy removes `.staging-<guid>`. A leftover sidecar blocks the next run until the owner secures it. Duplicate set names are refused. | Positive | VERIFIED in source; machine test UNVERIFIED (PROCEDURE.md T6). | None. |
| F6 | **Receipt and policy.** A run refuses without an Owner-configured policy, retention count, explicit behaviour, public key, and schedule (`OWNER_POLICY_REQUIRED`, ps1 line 406). No defaults. | Positive | VERIFIED in source. | Owner must configure values (deferred business input). |
| F7 | **Partial native publish is not rolled back** (`product/backup.py`, `_verify_and_publish` and `_publish_without_overwrite`, found in review 2026-10-17). Artifacts are published one at a time with no-overwrite links. If a later copy fails, the earlier encrypted artifacts stay in `private\backups` with no site-config sidecar, so the set is never complete. The sidecar, which holds the plaintext key, is published last and is therefore not written. Nothing removes or reports the orphans. No overwrite and no key exposure occur. `tests/foundation/test_product_backup_publish_2026_10_17.py` pins the current orphan behaviour with synthetic files (the gpg packet check is stubbed; no real gpg here). A mutation that publishes the sidecar first fails it. Update that test together with any F7 fix. | Medium (unrestorable orphan files that grow the F1 folder; no data loss) | **OPEN.** Found in review. Not fixed: deleting even files this process created needs an owner decision. | Owner decision: quarantine, report, or remove partial sets. Proposed: remove only names this process created in this run (verified absent before publish), and fail with a clear message. Needs a synthetic regression test that injects a failure on the second copy. |

## Gates affected

- Retention and deletion: **blocked by F1 and F7** until the owner decides native-folder rotation and orphan handling, and a Windows test covers both.
- Integrity and restore: **not claimable** (F2).
- Key custody and quorum: **owner decision** (F3; owner action A4).
- Same-PC drive: **accepted local-only risk** pending owner restatement (F4).
- Windows lifecycle (install, repair, reboot, interrupted recovery): **UNVERIFIED** until the owner runs PROCEDURE.md on an isolated machine.

## Owner decision options for F2, F1, and F7 (recorded 2026-10-17; nothing applied)

Checked against `product/backup.py` and `product/restore.py` at `ed4f7cd`:

- **F2 (restore integrity).** Publish never persists a digest. `_publish_without_overwrite` compares the temporary copy with the source only at copy time and then discards the hash. Restore (`_stage_restore_artifacts`) hashes the source and its staged copy against each other, not against any recorded digest. So a corrupted or substituted encrypted artifact cannot be detected at restore.
  - Option A: keep restore out of the release (status quo, "not claimable"). The owner acknowledges that restore is untested.
  - Option B: publish a per-set digest manifest and make restore fail closed on a missing or mismatched digest. Consequence: backup sets created before the change have no manifest and cannot be restored automatically. The owner must choose refusal or a documented manual path for them. Retention and the PowerShell rotation must also delete the manifest with its set.
- **F1 (native staging never rotated).** Options: (A) rotate native sets with the same keep count as D17; (B) keep every native set until the owner clears them by hand. Neither can be verified on this sandbox (no PowerShell).
- **F7 (partial native publish).** Options: (A) on failure, remove the artifacts this run published (never pre-existing ones) and report the failure; (B) leave them and rely on an owner-run orphan cleanup, with the set marked incomplete; (C) keep the current behaviour pinned by `tests/foundation/test_product_backup_publish_2026_10_17.py`, which is not a release-quality choice.

## Owner decisions applied (2026-10-17)

- **F7, owner cleanup (applied).** `product/backup.py` `_verify_and_publish`: if an encrypted artifact was published and a later copy fails, the run raises `native-publish-incomplete` and names the set. The artifacts stay in place, the site-config sidecar (the completion marker, which holds the backup key) is never written, and nothing is deleted. Tests: `tests/foundation/test_product_backup_publish_2026_10_17.py` (4 tests, updated from the old pin).
- **F1, rotation to the D17 keep count (applied, Python side).** After a verified publish, `_apply_native_retention` reads the validated Owner policy (`current_backup_policy()`). Only an explicit "Delete valid older sets beyond keep count" with a keep count of at least 2 deletes anything. Preserve-all, unconfigured, unrecognised, or invalid values delete nothing. `rotate_native_sets` keeps the newest complete sets, refuses if the current set would be dropped, never counts or deletes incomplete, symlinked, or non-timestamped sets, and removes each set's sidecar first, so an interrupted deletion leaves an incomplete set that is never deleted automatically. The keep count is not in code. Tests: `tests/foundation/test_native_retention_2026_10_17.py` (14 tests, with mutation checks: sidecar-last and no-protect-guard both fail the suite).
  - The PowerShell drive-side rotation (D17 for drive sets) is unchanged. It remains owner-run and UNVERIFIED on Windows (`PROCEDURE.md`).
  - Retention is inactive until the owner enters the keep count and retention behaviour in Owner Configuration.
- **F2, restore integrity (not a release capability).** Status unchanged: "not claimable". Restore is not part of the release claim.

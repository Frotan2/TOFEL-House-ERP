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
| F1 | **Native staging folder is never rotated.** Every run leaves a full encrypted native set in `product\data\sites\<site>\private\backups` (database, public files, private files, site config). The script removes only the plaintext sidecar (ps1 line 688). Retention (line 722) rotates only the drive set. The folder therefore grows by one full set per run on the same PC's data volume. | High (disk exhaustion; more encrypted copies than the keep count the owner chose under D17). | **OPEN. Blocker for the retention gate.** Not fixed here: deleting from the owner's data folder needs owner authority and a Windows run to validate. | Owner decision required (new; not yet in owner-decisions.json), D17 applied to the native folder. Proposed fix: after the drive set is committed and rotated, delete native sets of this site older than the newest committed set, using the same keep count and the same verified-manifest rule. Needs a Windows regression run before any release. |
| F2 | **Integrity is checked at write time, not at restore.** Drive sets record SHA-256 per artifact and are re-hashed after commit. Native artifacts are checked only for the GPG packet, not decrypted. No restore verification exists, and the restore path is unqualified (VALIDATION.md "Future restore target"). | Medium | OPEN. Restore is not a current release capability. | Synthetic decrypt-and-hash rehearsal in PROCEDURE.md T8. Restore must not be claimed until a qualified isolated restore runner exists. |
| F3 | **Key custody.** Native backups are GPG symmetric under `backup_encryption_key`, which lives in the site config on the same PC. The drive set wraps the site config under the owner's public recovery key, so the private recovery key must sit outside the PC with named custodians. The custodians and quorum are not defined in the repo (LAUNCH-RUNBOOK §67, §104). | High (decides whether a stolen drive is recoverable only with custodians) | OPEN. Owner decision. | Name custodians and quorum (owner decision). Store the private recovery key offline. Test recovery with synthetic keys only (PROCEDURE.md T9). |
| F4 | **Same-PC backup drive.** The drive is on the same PC as the product. A fire, theft, or ransomware event on the PC can take both the live site and every backup drive set. | High (resilience; accepted per D14/D17 only as local backup) | ACCEPTED LOCAL-ONLY RISK, to be restated by the owner. D14 defers off-site backup. | Owner acknowledges in the package (owner action A2). Off-site destination is deferred future scope and not a gate. |
| F5 | **Interrupted runs fail closed.** A failure during copy removes `.staging-<guid>`. A leftover sidecar blocks the next run until the owner secures it. Duplicate set names are refused. | Positive | VERIFIED in source; machine test UNVERIFIED (PROCEDURE.md T6). | None. |
| F6 | **Receipt and policy.** A run refuses without an Owner-configured policy, retention count, explicit behaviour, public key, and schedule (`OWNER_POLICY_REQUIRED`, ps1 line 406). No defaults. | Positive | VERIFIED in source. | Owner must configure values (deferred business input). |

## Gates affected

- Retention and deletion: **blocked by F1** until the owner decides native-folder rotation and a Windows test covers it.
- Integrity and restore: **not claimable** (F2).
- Key custody and quorum: **owner decision** (F3; owner action A4).
- Same-PC drive: **accepted local-only risk** pending owner restatement (F4).
- Windows lifecycle (install, repair, reboot, interrupted recovery): **UNVERIFIED** until the owner runs PROCEDURE.md on an isolated machine.

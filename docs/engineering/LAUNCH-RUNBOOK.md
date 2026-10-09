# Launch runbook — site-mode lifecycle (not production authorization)

Owner-run procedure that switches the product site's **operational mode**
from REFUSED to PRODUCTION and back. It does not authorize production release
or go-live. Production authorization remains REJECT until every applicable
evidence gate in [ACCEPTANCE.md](ACCEPTANCE.md), plus Owner and
non-engineering gates, actually passes. Native ERPNext/Education/HRMS work
without this mode switch. Do not expose the service to the public internet
while SEC-DEPS-01 is open; the selected local-server + Tailscale deployment
is not a public-edge release gate (see [../PRODUCT.md](../PRODUCT.md) §6).

**Desktop product (Owner) — PRESERVATION HOLD:** the Owner must explicitly
choose whether to preserve all valid backup sets or authorize deletion of
valid older external backup-set directories beyond the keep count (the current
cleanup protects the current set and prior receipt set). The policy has no
default: if the choice is unset, backup and activation remain fail-closed.
**Do not run `Backup TOEFL House ERP.cmd` or invoke the Windows
backup/retention helper, and do not proceed through activation, until the Owner
resolves this choice and the implementation/docs agree.** No Windows
backup/retention run has been performed in this review. The procedure below
documents the guarded implementation, not authorization to run it. Any later
Owner decision must be recorded in the effective-dated policy before execution.

The Owner-configured local nightly backup time, retention count (at least two),
explicit retention behavior, ASCII-armored OpenPGP public recovery key, and
key-custody requirement are entered through the ERP Configuration desk; no
schedule or count is supplied by product code. Keep the matching private key
outside Frappe and the backup drive.
When the preservation hold is formally resolved, the helper is intended to
create three native encrypted database/files artifacts plus a separately
public-key-encrypted site-config recovery artifact. It verifies actual GPG
packets, copy hashes/sizes, Owner policy, Task Scheduler and retention, and
never copies the misleading plaintext `*-site_config_backup-enc.json` sidecar.
It refuses to start if any pre-existing plaintext sidecar is found and removes
only the exact sidecar created by the current run after the separate-drive set
has been committed and verified. On a failed run it preserves and warns about
that run's plaintext sidecar for Owner review. Before any later site-mode
change, the host re-verifies the external drive, four payloads, manifest, live
Owner policy/key identity and scheduled task;
`product/activate.py` then checks the same-site source artifact hashes and the
app's own resolver. Any failed mode verification restores the saved
`site_config.json`. `Deactivate TOEFL House ERP.cmd` returns operational mode
to REFUSED. Neither operation changes production authorization.

## 0. Preconditions (do not proceed unless all hold)

1. The supported Windows product is running the current image and the native
   site has completed its migrations.
2. The ERP site uses MariaDB; non-MariaDB and qualification sites refuse.
3. The Course Owner has created/validated an effective-dated Owner policy
   through the ERP Configuration desk using approved values for every required
   field: reporting review, class capacity, tax, transfers/withdrawals,
   calendar, backup schedule/retention count and behavior/public key, custody
   and recovery quorum.
   No defaults or placeholders are supplied; unresolved choices remain fail-closed.
4. A dedicated OpenPGP key pair exists under an approved custody procedure.
   Provide only its ASCII-armored **public** key in the ERP desk. GPG/Gpg4win
   is not installed by the desktop product; use it on a trusted Owner host to
   create/export or recover the key, and test private-key availability before
   relying on it.
5. The matching private recovery key and its custody/recovery procedure are
   held outside Frappe and outside the separate backup drive. Never paste or
   copy private-key material into ERPNext, the Docker image/container, or the
   backup set. Changing the public key requires a new backup before activation.
6. The backup drive is a separate fixed local drive on this same computer.
   Off-site/NAS/second-device/cloud backup remains deferred future scope, not a
   current gate. The site is not `placement-test.localhost` or
   `placement-second.localhost`; those qualification sites can never be the
   operational production site. Production authorization remains REJECT until
   the acceptance evidence and Owner/non-engineering gates pass.
7. **Retention behavior is unresolved and currently fails this
   precondition.** The Owner policy requires an explicit choice: preserve all
   valid sets, or authorize deleting valid older sets beyond the keep count.
   The choice has no default; an unset value blocks backup and activation. Do
   not proceed until the Owner resolves it and the preservation requirement is
   reconciled with the implementation. This review has not run the Windows
   script.

## 1. Create and verify the Owner-configured backup

1. In the Configuration desk's **Backup & Recovery** section, create the
   Owner policy if absent, then use **Set policy version** and **Validate
   policy**. Supply approved values for every required Owner field (including
   reporting, capacity, tax, transfers/withdrawals, calendar, backup time,
   retention count/behavior, public key, custody, and quorum); do not invent
   defaults or use
   placeholders. Generate/obtain the dedicated OpenPGP key pair under the
   approved custody procedure and enter only its ASCII-armored public key.
   The Windows backup task runs as the interactive Windows user who registers
   it; that user session and Docker Desktop/server must be available for the
   scheduled run. Verify this operational dependency on the actual Owner PC;
   CI does not qualify it.
2. **Do not double-click `Backup TOEFL House ERP.cmd` while precondition 7 is
   unresolved.** After the Owner's retention decision is recorded and the code
   and documentation agree with it, the product adapter calls pinned Frappe's
   `scheduled_backup`/`BackupGenerator`; it does not define a parallel backup
   format or authority. It enables Frappe's
   native encryption, creates database/public-files/private-files artifacts,
   reads the current public key from the guarded Owner policy, and separately
   OpenPGP-encrypts the Frappe site-config recovery sidecar (which otherwise
   contains credentials and the native backup key). The adapter routes
   Frappe's native `backup_encryption_key` to GPG over stdin using GPG's
   `--passphrase-fd 0` option, and routes the native MariaDB dump/import
   password through a temporary mode-0600 option file; neither secret is
   inserted into the respective child command arguments. Restore similarly
   calls pinned Frappe `_restore` and uses those same GPG and MariaDB
   credential transports. **Do not bypass these adapters with direct
   credential-bearing Bench commands.** Source review of matrix-pinned Frappe
   commit `988e54f3c4c291e2077a83809663f123731abe76` found that `bench new-site`
   and `bench restore` expose credential options (including database/admin
   passwords and the restore encryption key) through CLI options; Frappe's
   native backup/restore GPG helper interpolates the key into a
   `--passphrase` command, and `frappe.database.get_command()` puts MariaDB
   passwords in `--password=...` arguments (PostgreSQL passwords in connection
   URIs). The product adapters retain Frappe's native implementation while
   replacing only those transports. This is pinned-source review, not runtime
   qualification. Automated tests inspect mocked GPG child argv, check the dump
   password is absent from native dump arguments/command text, verify sanitized
   failure output, preserve older source backups, and ensure restore mutations
   stay on disposable copies. These tests are not a Docker, Windows,
   Owner-machine, or actual restore rehearsal. The misleading
   `*-site_config_backup-enc.json` plaintext sidecar is never copied to the
   backup drive. Any pre-existing plaintext sidecar makes the command refuse
   before a new backup starts; those files are preserved for Owner review. The
   exact sidecar created by this run is removed only after the separate-drive
   set has been committed and its payload hashes/sizes have been reverified.
   If the run fails before that point, the script warns that the new plaintext
   sidecar remains; do not activate or delete it without the Owner's secure
   handling procedure.
3. The completed set has exactly four encrypted payloads:
   `*-database-enc.sql.gz`, `*-files-enc.tar`, `*-private-files-enc.tar`, and
   `*-site-config.gpg`, plus `manifest.json`. The first three must contain
   actual native symmetric-encryption packets; the config artifact must be
   a public-key packet for the configured Owner key. The script verifies
   SHA-256 and byte size after copy to
   `\<backup-drive>\TOEFL-House-ERP-Backups\<backup-set>`, verifies the
   Owner policy identity and daily Task Scheduler action. If—and only if—the
   Owner explicitly chose deletion in the effective policy, the helper removes
   valid older external backup-set directories outside the keep count (while
   protecting the current and prior receipt sets) before writing the activation
   receipt. If the Owner chose preservation, no pre-existing external backup
   set is removed; only the exact plaintext sidecar generated by the current
   run is handled after its encrypted copy verifies. An unset/unknown behavior
   fails closed before backup generation or cleanup.
   This review has not run the helper; the Owner's actual retention choice is
   still unresolved, so do not run it or activate yet.
4. Stop if the script reports a missing policy, unavailable drive, key/GPG
   mismatch, failed hash, missing task, insufficient drive capacity, selected
   retention-verification error, or a pre-existing plaintext sidecar. Do not
   hand-edit a receipt or treat a filename as proof
   of encryption. The backup script never removes pre-existing sidecars or
   sidecars from older backup sets. Do not activate while any plaintext
   Frappe site-config sidecar remains in the native source folder; preserve it
   and ask the Owner/engineering to handle it using an approved secure
   procedure. A failed run may leave only that run's newly generated sidecar
   for review, and the script explicitly warns about it.

The backup script also leaves the four encrypted native/recovery artifacts in
Frappe's source backup folder so the guarded site-mode command can recheck the
same-site artifact hashes. The required separate-drive copy is independently
checked by the Windows host wrapper immediately before activation. Neither
copy contains the plaintext site-config sidecar or a private recovery key.

## 2. Switch operational site mode through the guarded Windows flow

1. **Do not run the activation wrapper while precondition 7's retention/
   preservation hold is unresolved, even if an older receipt exists.** Only
   after the Owner's explicit decision is recorded and the implementation and
   documentation agree, double-click `Activate TOEFL House ERP.cmd` and type
   `ACTIVATE` after reviewing its warning. The wrapper first runs
   `Backup TOEFL House ERP.ps1 -VerifyExisting` on the Windows host, which
   rechecks the current secondary
   drive, exact backup-set path, manifest digest, all four file hashes/sizes,
   live Owner policy/public-key identity, and the scheduled task.
2. The product then runs `product/activate.py` inside the container. It checks
   the current receipt, source artifact hashes, live app policy and the app's
   own site-mode resolver. It saves a private-mode `site_config.json`
   snapshot; if a mode gate fails, the previous file is restored.
3. Do not edit `site_config.json` by hand or run the in-container activation
   script directly as a substitute for the Windows wrapper: that would skip
   the host-side check of the separate local backup drive.

Expected status after success:

- `Site operational mode: PRODUCTION`;
- `Production authorization: REJECT`.

This is an operational mode change only. It is not a release/launch approval,
not a green CI claim, and not a GO decision. Production authorization remains
REJECT until the current [ACCEPTANCE.md](ACCEPTANCE.md) evidence ledger and
all Owner/non-engineering gates are satisfied.

## 3. Hard gates exercised by the guarded command

The current same-site backup must be no older than 24 hours, complete, marked
encrypted/verified, hash/size unchanged, and match the effective Owner
schedule, retention count/behavior, public-key hash, and policy identity. The
host wrapper also verifies the external fixed drive and task. The app then
checks MariaDB,
rejects both synthetic site names and the *presence* of stale test flags,
requires the baseline mode to be REFUSED, probes the app's production mirror,
tests mixed production/test flags are refused, and confirms production mode
is restored before reporting success. Any failed post-write check restores
the saved `site_config.json`.

The Owner Cockpit, Administration control centre, and product status must
continue to show `Production authorization: REJECT`. A PRODUCTION site-mode
result cannot authorize production release.

## 4. Native placement-fee item (before first billing)

On synthetic sites the placement fee uses `SYN-PLACEMENT-FEE`, which is
forbidden on the operational site. Finance must create a native ERPNext Item
with a positive selling rate on the `TOEFL House Standard` price list. The
Owner can then use the optional prompt in `Activate TOEFL House ERP.cmd` to
set that existing Item through `product/activate.py fee-item`; no parallel
Item or price ledger is introduced. A missing, fixture-marked, or unpriced
Item remains refused. This setting does not change production authorization.

## 5. Rollback (deactivation)

Double-click `Deactivate TOEFL House ERP.cmd`. It removes only the operational
mode keys through `product/activate.py`, saves a private-mode snapshot, and
verifies that the app resolves to `REFUSED`. A failed verification restores
the prior configuration. No database migration or ledger is changed, and
production authorization remains REJECT before and after rollback.

## 6. Multi-user access (central server + Tailscale)

The current deployment (owner decision D15) is one central computer
running the product, with authorized staff computers accessing it through the
owner's Tailscale tailnet. The product does not change for this: it keeps
listening on `127.0.0.1` only, and the tailnet reach comes from **Tailscale
Serve**, which is external to the product and stays under the owner's
Tailscale account (identity, ACLs, device list).

Setup (once per central PC; every staff PC only needs Tailscale joined to
the tailnet):

1. Start the ERP on the central PC (`Start TOEFL House ERP.cmd`).
2. Operator step on the central PC (a terminal is fine; it is not part of
   the double-click flow):

   ```
   tailscale serve --bg 8000
   tailscale serve --bg --set-path=/socket.io 9000
   tailscale serve status
   ```

   The root route forwards normal ERP requests to the loopback web service;
   `/socket.io` must forward to the loopback Socket.IO service on port 9000 for
   same-origin realtime refresh. This publishes HTTPS only to the tailnet on
   the central PC's Tailscale hostname. It opens no public port: without
   Funnel (never enable it for this product), only tailnet members can reach it.
3. On each staff PC, open
   `https://<central-PC-name>.<your-tailnet-name>.ts.net/` in the browser.
   The Tailscale certificate is trusted on all tailnet machines (MagicDNS is
   on by default).
4. Each staff member logs in with their own native User (User and Role are
   the identity authority; branch-scoped staff additionally carry a native
   User Permission for their Branch — `docs/ROLE-DESKS.md`, "Branch
   scope").

Properties and limits:

- Access control is Tailscale identity plus the ERP's own users and roles;
  no public address, no firewall rule, no open host port is involved.
- The product resolves its single site independently of the hostname in the
  URL (`product/wsgi.py` pins the site), so the tailnet hostname needs no
  site configuration.
- The owned CI qualification proves a second non-administrator client can
  authenticate through an arbitrary forwarded-host proxy, checks loopback-only
  publication and restart persistence, and health-checks the Socket.IO service.
  It does **not** run Tailscale Serve, prove the `/socket.io` path/WebSocket
  upgrade through an actual tailnet, or use the Owner's devices. Record that
  real Windows/Tailscale path and realtime check in
  [ACCEPTANCE.md](ACCEPTANCE.md) before changing its evidence status. Do not
  publish the raw Socket.IO port or enable Funnel; any topology change requires
  a new qualification.
- Removing the tailnet exposure at any time: run
  `tailscale serve --delete` on the central PC. The ERP remains
  loopback-only; nothing else is affected.

## 7. Restore from backup (operator)

A restore overwrites site data and is deliberately an operator task. Use the
chosen set on the separate fixed local drive; keep the ERP idle and ensure no
staff member is issuing commands. The private key is never imported into
Frappe or the web container.

1. Confirm the chosen backup's `manifest.json` belongs to that set and verify
   each of its four artifact SHA-256 digests and byte sizes against the
   manifest. Refuse a set with any plaintext `*-site_config_backup*.json`
   sidecar. Record the set name and the outcome.
2. Gpg4win is not installed by the desktop product. On a trusted Windows
   host, install/use GPG (for example, Gpg4win) and make the Owner-held private
   recovery key available through its separate custody procedure. If the key
   is in an armored key file, import it into the current Windows user's GPG
   keyring with `gpg --import "<Owner-private-key-file>"`; do not copy the key
   into the product, Frappe, container, or backup drive. In PowerShell, set
   the chosen backup path/set name and decrypt into a unique protected temp
   file (GPG may prompt for the private-key passphrase):

   ```powershell
   $backupRoot = "D:\TOEFL-House-ERP-Backups"
   $backupSet = "<backup-set>"
   $configArtifact = Join-Path $backupRoot $backupSet
   $configArtifact += "-site-config.gpg"
   $recoveredConfig = Join-Path $env:TEMP ("toefl-house-site-config-" + [Guid]::NewGuid().ToString("N") + ".json")
   gpg --output $recoveredConfig --decrypt $configArtifact
   if ($LASTEXITCODE -ne 0) { throw "Owner recovery-key decryption failed; stop." }
   $siteConfig = Get-Content -LiteralPath $recoveredConfig -Raw -Encoding UTF8 | ConvertFrom-Json
   $backupEncryptionKey = [string]$siteConfig.backup_encryption_key
   if ([string]::IsNullOrWhiteSpace($backupEncryptionKey)) { throw "Recovered config has no native backup_encryption_key; stop." }
   ```

   Keep the recovered JSON/key private; do not print them, paste them into
   chat, or leave plaintext in the backup set, Frappe site directory, Docker
   container, or a shared folder. If the private key is unavailable or
   decryption fails, stop. Delete `$recoveredConfig` only after the restore checks succeed.
3. Copy the three native encrypted database/files artifacts (not the config
   artifact) into
   `product\data\sites\toeflhouse.localhost\private\backups`. From the
   `product` directory, quiesce the app and run the restore in a one-off web
   container so no staff request can write during the restore. Keep MariaDB
   and Redis running. **Frappe extracts its public/private tar archives into
   the existing `files` directories; it does not remove files absent from the
   backup.** To restore an exact file snapshot rather than merge/overlay it,
   move the existing trees aside on the same filesystem and create empty
   targets before invoking Frappe. Keep enough free space for the restored
   files while the old trees are staged, and do not delete the stage until
   database and file checks pass. The pinned product restore adapter calls
   Frappe's native restore implementation. Since native Frappe decrypts each
   encrypted input in place, the adapter first copies the three encrypted
   artifacts to mode-0600 files under a private disposable `/tmp` directory in
   the one-off container; it never hands the Owner's original backup files to
   the mutating restore routine. Normal completion or failure cleanup removes
   those copies, while the Owner's source encrypted set remains unchanged. It
   accepts the Frappe key, MariaDB root password, and Administrator
   password as a JSON document on stdin; none of those values is placed in a
   Docker/Bench command argument, transcript, or failure diagnostic:

   ```powershell
   docker compose stop web worker scheduler socketio
   $restoreStageName = ".restore-files-" + [Guid]::NewGuid().ToString("N")
   $stageFiles = @'
   set -eu
   umask 077
   site=sites/toeflhouse.localhost
   stage="$site/private/$RESTORE_STAGE_NAME"
   mkdir -p "$stage"
   for scope in public private; do
       files="$site/$scope/files"
       if [ -d "$files" ]; then mv "$files" "$stage/$scope-files"; fi
       mkdir -p "$files"
   done
   '@
   docker compose run --rm --no-deps -e "RESTORE_STAGE_NAME=$restoreStageName" --entrypoint /bin/sh web -eu -c "$stageFiles"

   $dbRootLine = Get-Content -LiteralPath "data\secrets\db.env" |
       Where-Object { $_.StartsWith("MARIADB_ROOT_PASSWORD=") } |
       Select-Object -First 1
   if (-not $dbRootLine) { throw "MariaDB root password is missing; stop." }
   $dbRootPassword = $dbRootLine.Substring("MARIADB_ROOT_PASSWORD=".Length)
   $adminSecure = Read-Host "Enter the Owner-controlled Administrator password for this restore" -AsSecureString
   $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($adminSecure)
   try { $adminPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer) }
   finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer) }
   $restorePayload = [ordered]@{
       site = "toeflhouse.localhost"
       backup_set = $backupSet
       encryption_key = $backupEncryptionKey
       db_root_password = $dbRootPassword
       admin_password = $adminPassword
   } | ConvertTo-Json -Compress
   $restoreStartInfo = New-Object System.Diagnostics.ProcessStartInfo
   $restoreStartInfo.FileName = "docker"
   $restoreStartInfo.Arguments = "compose run --rm --no-deps --interactive --no-TTY --entrypoint /home/frappe/bench/env/bin/python web /product/restore.py"
   $restoreStartInfo.UseShellExecute = $false
   $restoreStartInfo.RedirectStandardInput = $true
   $restoreProcess = New-Object System.Diagnostics.Process
   $restoreProcess.StartInfo = $restoreStartInfo
   $restoreStream = $null
   $restoreStarted = $false
   try {
       if (-not $restoreProcess.Start()) { throw "Docker Compose restore adapter did not start." }
       $restoreStarted = $true
       $restoreStream = $restoreProcess.StandardInput.BaseStream
       $restoreBytes = [Text.Encoding]::UTF8.GetBytes($restorePayload + "`n")
       $restoreStream.Write($restoreBytes, 0, $restoreBytes.Length)
       $restoreStream.Flush()
       $restoreProcess.StandardInput.Close()
       $restoreProcess.WaitForExit()
       $restoreExitCode = $restoreProcess.ExitCode
   }
   finally {
       if ($restoreStream) { $restoreStream.Dispose() }
       if ($restoreStarted -and -not $restoreProcess.HasExited) {
           $restoreProcess.Kill()
           $restoreProcess.WaitForExit()
       }
       $restoreProcess.Dispose()
       $restoreBytes = $null
       $restorePayload = $null
       $dbRootPassword = $null
       $adminPassword = $null
       $adminSecure.Dispose()
       $backupEncryptionKey = $null
   }
   if ($restoreExitCode -ne 0) { throw "Native Frappe restore failed; sensitive diagnostics were withheld." }
   ```

   Do not enable shell tracing or record this PowerShell session in a
   transcript. The product restore adapter reads credentials only from stdin
   and withholds native restore diagnostics on failure. No application writer
   is running during the restore.
4. Start the full stack again with `docker compose up -d`, log in, verify
   expected native ERPNext/Education/HRMS records plus representative public
   and private files from the selected set, and confirm files created after
   that set are absent. Only after all checks pass, delete the staged old
   trees and protected temporary config:

   ```powershell
   docker compose exec -T web sh -eu -c 'rm -rf -- "sites/toeflhouse.localhost/private/$1"' sh $restoreStageName
   Remove-Item -LiteralPath $recoveredConfig -Force
   ```

   The native Frappe restore is destructive and must not be interrupted. If the restore
   command fails, leave the services stopped. If a post-start verification
   fails, stop the full stack again. In either case retain the staged trees
   and escalate rather than allowing staff to use a partially restored
   database/filesystem.
5. Create a new encrypted backup and re-verify the Owner policy/task/receipt
   before any site-mode activation. Restoring data does not restore or
   authorize a site mode; the current `site_config.json` operational-mode
   state remains under the guarded activation/rollback flow. Record the date,
   set name, manifest/artifact verification, key recovery outcome, elapsed
   restore time, data checks, and result in the Owner's acceptance evidence.
   The actual Owner key-custody/recovery ceremony is a non-engineering gate;
   CI cannot qualify it.

## 8. Record the rehearsal

The Owner runs the backup and restore rehearsal on the actual local server and
records each run. Current backup scope is an encrypted, verified set on a
separate local drive on the same computer. Off-site/NAS/second-device/cloud
backup is deferred future scope and is not a current release gate:

| Date | Site | Backup set | Artifact hashes / config decrypt | Restore checks | Elapsed | Outcome |
| ---- | ---- | ---------- | --------------------------------- | -------------- | ------- | ------- |
|      |      |            |                                   |                |         |         |

Activation is a mechanism, not a GO decision. SEC-DEPS-01 (known upstream
advisories in the pinned stack) gates **internet exposure** of the product;
it is not a stop for the selected loopback / local-Tailscale deployment
(owner decisions D13/D15). The current evidence state of the acceptance
items (backup, branch isolation, rollback, monitoring, capacity) is recorded
in `docs/engineering/ACCEPTANCE.md`.

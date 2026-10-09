# First-run validation checklist (Windows) — one pass, ten steps

**Who this is for:** the TOEFL House owner. You do **not** need any PowerShell,
WSL, Git, Python, Bench, database, or command-line knowledge. Every action
below is a **double-click**, a **browser click**, or **taking a screenshot**
(`Win + Shift + S`, drag, then paste — or simply take a photo with your phone).

**What its result means:** this checklist is the exact release-gate evidence
set (`Install → first boot → login → Start → Stop → Start → Backup → Repair →
browser access → persistence`). The Desktop release gate stays **OPEN** until
all ten evidence items exist and engineering confirms them. If anything
differs from the "Expected" lines, that is a defect — stop and report it
(see "If something fails").

**Validation status:** this document describes expected results; it is not
proof that a Windows installation or Owner lifecycle has passed. The
`product-image.yml` workflow checks a fresh Windows-style Git worktree and
simulates a stale CRLF/BOM worktree, but that CI check does not validate Docker
Desktop, the Owner's real data, Task Scheduler, login, backup recovery,
Tailscale, or a real Windows lifecycle. Record those results from the Owner PC
and keep the Desktop release gate open until engineering verifies them.

---

## Before you start (once)

1. A 64-bit **Windows 10 or 11** PC with internet and ~30 GB free disk.
2. **Docker Desktop** installed: https://www.docker.com/products/docker-desktop/
   Its own installer is click-through and sets up WSL2 automatically if the PC
   asks. Restart the PC if it tells you to.
3. GPG/Gpg4win on a trusted Owner/custodian host is needed to create/export
   or recover the dedicated OpenPGP key pair. Only the ASCII-armored public
   key enters ERPNext; the private key and its recovery procedure stay under
   Owner custody outside Frappe/the container and outside the backup drive.
   The normal product backup encrypts inside the product container.
4. This repository unzipped anywhere (e.g. Desktop): on GitHub use
   **Code → Download ZIP**, then right-click the ZIP → **Extract All…**.

Then open the folder `product → windows` and do the steps below **in order**.
Do not skip or reorder steps — later steps prove earlier ones survived.

### Source line endings (automatic; no manual cleanup)

- Fresh Git checkouts pin product build inputs to UTF-8/LF; the Windows
  `.cmd` launchers intentionally stay CRLF for `cmd.exe`.
- `Install` and `Repair` run `Normalize Product Sources.ps1` before building.
  It scans the Dockerfile's `COPY` sources and build-control files, removes
  UTF-8 BOMs and normalizes CRLF/CR to LF only for recognized text sources.
  It does **not** traverse `product/data`, credentials, or backups. Unknown
  binary inputs with CR/BOM bytes fail safely instead of being rewritten.
- If source bytes were changed, `Install` builds the image and `Repair`
  rebuilds it before restarting services. `Repair` also rebuilds an old image
  that lacks the verified `source-eol=lf-v1` marker, even if the worktree is
  already LF. Allow the image-build time on that first recovery run.
- If the source check reports an error, stop and contact engineering; do not
  run a broad line-ending converter or edit the runtime-data directory.

---

## Step 1 — Install (once)

- **Action:** double-click `Install TOEFL House ERP.cmd`. Keep the window open.
- **Expected:** it checks Docker Desktop, asks nothing, builds for 20–60
  minutes the first time, then says it is finishing inside the app
  ("site setup can take 15-40 minutes on first run"). Finally it prints a box
  with **Username: Administrator** and a **Password**, opens your browser at
  `http://127.0.0.1:8000`, and ends with "Install finished".
- **Evidence 1:** screenshot/photo of the printed login box **and** of the
  browser page (a TOEFL House ERP login page).
- *The password is also saved in `data\sites\toeflhouse.localhost\private\
  first-run-credentials.txt`. Move a copy somewhere private.
  **Never email or photograph the password text to anyone** — the evidence is
  the box on screen with the password covered or blurred, plus the file's
  existence.*

## Step 2 — First boot completed

- **Action:** none — this step is already done when the browser opened and the
  login page loaded in Step 1. If the page showed an error instead of a login
  form, wait 10 minutes, refresh once; only if it still errors, treat as failure.
- **Expected:** the login page (not an error page, not "site unavailable").
- **Evidence 2:** screenshot/photo of the login page, address bar showing
  `http://127.0.0.1:8000`.

## Step 3 — Login

- **Action:** type `Administrator` and the password from Step 1, click **Login**.
- **First login only:** frappe's one-time setup wizard appears (organization
  details, currency, fiscal year). Complete it with your institute's own
  values — it is a native frappe step, once only; afterwards you land on the
  desk.
- **Expected:** the TOEFL House ERP desk (the work screen with menus/icons),
  not an error.
- **Evidence 3:** screenshot of the desk after login.

## Step 4 — Create and use the Course Owner account

- **Action:** while signed in as the one-time `Administrator`, use the native
  **User** list to create a separate enabled **System User** for the real
  Course Owner, assign the native **Course Owner** role, and set that user's
  own password with ERPNext's normal account flow. Do not use or rename the
  built-in Administrator as the Course Owner: guarded Owner commands
  deliberately reject Administrator. Keep the Administrator credential
  private for setup/recovery. Sign out, sign in as the new Course Owner, open
  **My Profile**, set **Full Name** to `Owner`, and save.
- **Expected:** the dedicated Course Owner login reaches the desk and the
  profile save succeeds. This is the account that will configure backup and
  other Owner policies through the ERP Configuration desk.
- **Evidence 4:** screenshot of the Course Owner account's native role
  assignment and its profile showing **Full Name: Owner**. Do not include a
  password or recovery key. If a separate Course Owner account cannot be
  created/authenticated, stop; do not proceed using Administrator.

## Step 5 — Stop

- **Action:** double-click `Stop TOEFL House ERP.cmd`.
- **Expected:** it says "TOEFL House ERP has stopped." and the window closes
  by itself. The browser page will no longer load (that is correct).
- **Evidence 5:** screenshot of the stopped message (or a photo of the
  refreshed browser showing the page no longer loads).

## Step 6 — Start

- **Action:** double-click `Start TOEFL House ERP.cmd`, wait (usually 1–5
  min; it first checks a few seconds whether the app has been updated).
- **Expected:** it waits, then opens the browser at `http://127.0.0.1:8000`
  and closes its window by itself.
- **Evidence 6:** login as the Course Owner created in Step 4; screenshot of
  the desk **and** My Profile still showing **Full Name: Owner** (the mark
  survived a stop).

## Step 7 — Backup

- **Before backup:** sign in as the dedicated Course Owner from Step 4 (not
  Administrator). In **Configuration desk → Backup & Recovery**, create the
  Owner policy if it does not exist, then choose **Set policy version** and
  **Validate policy**. The version form requires actual Owner-approved values
  for reporting review days, class capacity, tax choices/rate, transfer and
  withdrawal rules, calendar notice, local nightly backup time, retention
  count (at least two) and explicit preserve/delete behavior, ASCII-armored
  OpenPGP **public** recovery key, custody
  requirement, and recovery quorum, plus effective date and reason. No
  defaults or placeholders are supplied: obtain any unresolved business
  decision from the Owner rather than guessing. Generate/obtain the dedicated
  key pair under the approved custody procedure using GPG/Gpg4win on a trusted
  host; enter only its public key. Keep the matching private key and recovery
  procedure outside Frappe and the backup drive. Never paste or copy private
  key material into ERPNext, the container, or the backup set. If the effective
  policy is incomplete or invalid, the backup launcher refuses and does not
  create an activation receipt.
- **Preservation hold:** do **not** invoke `Backup TOEFL House ERP.cmd`, its
  Windows backup/retention helper, or activation while the Owner's explicit
  retention behavior is unresolved. The effective-dated Owner policy must
  choose either to preserve all valid backup sets or to authorize deletion of
  valid older sets beyond the keep count (the current cleanup protects the
  current and previous receipt sets). There is no default; an unset choice
  keeps backup/activation fail-closed. This review has not run the Windows
  backup/retention helper.
- **Action (only after the Owner resolves the preservation hold):** double-click
  `Backup TOEFL House ERP.cmd` and wait for the success message and the printed
  backup-set folder on a separate fixed local drive on this same PC. Press any
  key to close.
- **Expected:** the set contains `manifest.json` and exactly four encrypted
  payloads: `*-database-enc.sql.gz`, `*-files-enc.tar`,
  `*-private-files-enc.tar`, and `*-site-config.gpg`. The last artifact is
  public-key encrypted for Owner recovery of Frappe's site config/native backup
  key. The misleading plaintext `*-site_config_backup-enc.json` sidecar must
  **not** be present after a successful run. Before starting, the script refuses
  and preserves any pre-existing plaintext sidecars for Owner review; it removes
  only the exact sidecar created by this run, and only after the separate-drive
  set and its hashes/sizes verify. If the run fails before that point, it warns
  that the newly created plaintext sidecar remains; do not activate or delete it
  without the approved secure-handling procedure. **Important preservation
  hold:** after verifying a new backup, the helper deletes valid older external
  sets beyond the configured keep count only when the Owner explicitly selects
  that behavior; the alternate choice preserves all valid sets. An unset choice
  fails closed before backup generation or cleanup. This review has not run the
  helper on Windows. Do not run `Backup TOEFL House ERP.cmd` or activate until
  the Owner resolves the retention choice and the implementation/docs agree.
  The script prints an error
  rather than success if GPG packet checks, copy hashes/sizes, the Owner policy,
  Task Scheduler identity, or retention verification fail.
- **Implementation/evidence note:** `product/backup.py` delegates artifact
  creation to pinned Frappe `scheduled_backup`/`BackupGenerator`; it does not
  introduce another backup format. The native GPG key is written to GPG stdin
  through `--passphrase-fd 0`; native MariaDB dump/import passwords are moved
  from Frappe's upstream `--password` argument into a temporary mode-0600
  option file. `product/restore.py` calls pinned Frappe `_restore` with the
  same GPG and MariaDB credential transports. Because native Frappe decrypts
  its input artifacts in place, the adapter gives it mode-0600 copies in a
  private disposable `/tmp` directory; the Owner's encrypted source set is not
  passed to the mutating restore implementation. Focused synthetic source tests
  inspect mocked GPG child argv, check database passwords are absent from
  native arguments/command text, and verify both that backup publication leaves
  existing artifacts unchanged and that restore mutations remain on disposable
  copies. Those
  unit/static checks do not execute Docker, Windows, GPG against real backup
  data, Task Scheduler, Owner key custody, or a real backup/restore.
- **Schedule dependency:** the daily Windows task runs as the interactive
  user who registered it; that user session and Docker Desktop/server must be
  available for the task to run. Confirm this on the Owner PC; CI does not
  qualify Windows Task Scheduler.
- **Evidence 7:** screenshot of the printed separate-drive path and the
  four-artifact set/manifest in File Explorer. Do not send the backup, private
  key, decrypted site config, or any passwords as evidence. A separate local
  drive on the same PC is the current requirement; off-site/NAS/second-device/
  cloud copies are deferred future scope.

## Step 8 — Repair

- **Action:** double-click `Repair TOEFL House ERP.cmd`, wait (a few minutes).
- **Expected:** it restarts services, waits, then opens the browser and says
  "Repair complete". It never deletes data.
- **Also true after a PC or Docker Desktop restart:** the ERP comes back by
  itself the next time Docker Desktop runs; if anything still misbehaves after
  a restart, this same Repair script is the one recovery path. If it cannot
  finish, it now shows which service is not up (a short service list plus the
  last log lines) so the problem can be reported without guessing.
- **Evidence 8:** screenshot of the Repair window's "Repair complete" message
  (take it before pressing a key to close).

## Step 9 — Browser access after repair

- **Action:** in the browser it opened, log in as the dedicated Course Owner
  created in Step 4.
- **Expected:** the desk loads normally.
- **Evidence 9:** screenshot of the desk after login.

## Step 10 — Persistence

- **Action:** open the Course Owner's **My Profile** again.
- **Expected:** **Full Name: Owner** is still there after the Stop → Start →
  Repair cycle. The backup step remains intentionally unrun while the
  preservation hold is active; after the Owner resolves the hold and the
  implementation/docs agree, repeat this persistence check after the
  separately authorized backup run.
- **Evidence 10:** screenshot of My Profile showing **Owner**. Backup/restore
  and downstream activation evidence remain UNVERIFIED while the hold is open.

---

## Finishing

Send engineering: one message/email containing **Evidence 1–10** (password
and recovery key covered/omitted wherever they appear), plus your Windows version and the date
you ran this. Engineering maps the ten items onto the release-gate steps and
closes the **Desktop release gate**, which is OPEN until exactly this evidence
set is confirmed.

## Later: switching on real operation (once, not part of this checklist)

Do **not** perform this switch while the preservation hold is unresolved,
even if an older receipt exists. Only after the Owner explicitly resolves the
retention behavior and the implementation/docs agree may the Owner run
`Backup TOEFL House ERP.cmd`, verify its result, then run
`Activate TOEFL House ERP.cmd` and type `ACTIVATE` when asked. Activation
changes only the site's operational mode; it is **not** production release
authorization, which stays REJECT until all acceptance evidence and
Owner/non-engineering gates pass. The wrapper also refuses without a current,
verified four-artifact backup on the separate local drive.
`Deactivate TOEFL House ERP.cmd` returns the site to REFUSED without changing
native ERP data. Restore/key custody steps are in the canonical launch runbook.

## Later: letting authorized staff access it from their computers

The ERP always listens only on the central PC (nothing is opened on the
public internet). Authorized staff PCs that are in your Tailscale network
reach it over that private network: Tailscale is installed on the central PC
and staff PCs. The supported Tailscale Serve setup has separate web and
`/socket.io` routes on the central PC (written out in the launch runbook
section "Multi-user access (central server + Tailscale)") so realtime requests
use the same HTTPS origin. Access is limited to your Tailscale network
members only; no firewall rule or public address is involved. CI does not run
Tailscale Serve or prove the actual tailnet/WebSocket path; record that
real Owner-PC check separately.

## If something fails

1. **Exactly one retry path exists:** double-click `Repair TOEFL House ERP.cmd`
   and wait. It is safe and never deletes data.
2. If the same step still fails, **stop**. Do not look for terminal commands.
3. Send: a photo of the failing window, the step number, plus the `data\logs`
   folder (right-click it → **Send to → Compressed (zipped) folder**, attach
   the ZIP). Engineering treats first-run discrepancies as product defects.

*This checklist mirrors the shipped scripts exactly. None of these steps is a
deployment approval: production approval remains a separate, owner-signed
decision; this list only proves the Windows daily-use flow on a real PC.*

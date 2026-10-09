# First-run validation checklist (Windows) — ten lifecycle steps plus backup/restore gates

**Who this is for:** the TOEFL House owner. You do **not** need any PowerShell,
WSL, Git, Python, Bench, database, or command-line knowledge. Every action
below is a **double-click**, a **browser click**, or **taking a screenshot**
(`Win + Shift + S`, drag, then paste — or simply take a photo with your phone).

**What its result means:** the ten-step on-machine lifecycle sequence is
`Install → first boot → login → Start → Stop → Start again → Repair → browser
login → persistence`. Backup and restore are additional mandatory Owner gates
(Evidence 11–12 below); the later private-network/Tailscale check is
Evidence 13. None may be inferred from the ten-step lifecycle.
The Desktop release gate stays **OPEN** until the lifecycle, backup/restore,
Task Scheduler, and other applicable Owner evidence is recorded and engineering
confirms it. If anything differs from the "Expected" lines, stop and report it
(see "If something fails").

**Validation status (2026-10-09):** **UNVERIFIED** — no actual Windows Owner
installation/lifecycle, browser login, backup/readability/restore rehearsal,
Task Scheduler, key-custody ceremony, or Tailscale/private-exposure evidence
has been supplied. Backup/restore is under a **PRESERVATION / RESTORE HOLD**:
the Owner's retention choice remains unresolved and the Owner package has no
qualified isolated restore workflow. Do not run the backup/retention helper,
restore, cleanup/deletion, or activation; never replace the existing site or
clean up `product/data`. The backup/restore section below contains read-only
checks only. Production authorization remains **REJECTED**.

**Hosted CI snapshot (2026-10-09; merged head `13482fe285768e43ccadc0d93182a9a14eddf953`):**

- Product-image run
  [37940397957](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397957)
  **PASS** — Compose validation, pinned image build, synthetic first boot,
  encrypted backup/restore and mode checks, Chromium login, multi-user proxy
  contract, upgrade/rollback, and measured performance. The restore is into the
  same disposable CI site; it is not an Owner restore.
- Native lifecycle run
  [37940397967](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397967)
  **PASS** — the runner creates a new `placement-restore.localhost` site and a
  separate database in its ephemeral Bench. The verifier checks 14 synthetic
  DocTypes by count/name digest (not field values) and one private `File`'s
  content hash, `is_private`, attached DocType, and attached-name digest. It does
  not check a public file, File owner/share metadata, filesystem mode/UID/GID,
  CWD restoration, or a post-restore restart. Its happy-path run has no negative
  snapshot-mismatch test. The retained result artifact could not be retrieved in
  this review; per-run counts and hashes are unavailable.
- Owned suite
  [37940397970](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397970)
  **PASS**.
- Foundation runtime
  [37940398359](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940398359)
  **FAIL** — both dependency-audit gates failed. The annotation reports 160
  matches across 47 packages and 8 untriaged matches (7 unique advisories).
  This is not a restore failure and is not a security pass.

CI evidence is synthetic Linux evidence only. It does not validate Docker
Desktop, the Owner's existing data, Windows operations, Task Scheduler, real
backup/restore, key custody, Tailscale, or release readiness. Production
authorization remains **REJECTED**.

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

## Step 5 — Start

- **Action:** after the first login, double-click `Start TOEFL House ERP.cmd`
  while the installation is already running. This verifies the daily Start
  launcher is idempotent on a healthy stack; do not run a shell command.
- **Expected:** it checks all service health, opens
  `http://127.0.0.1:8000`, and closes its window.
- **Evidence 5:** screenshot of the Course Owner desk opened by Start.

## Step 6 — Stop

- **Action:** double-click `Stop TOEFL House ERP.cmd`.
- **Expected:** it says "TOEFL House ERP has stopped." and the window closes
  by itself. The browser page will no longer load (that is correct).
- **Evidence 6:** screenshot of the stopped message (or a photo of the
  refreshed browser showing the page no longer loads).

## Step 7 — Start again

- **Action:** double-click `Start TOEFL House ERP.cmd` again after Step 6;
  wait while it checks services and opens the browser.
- **Expected:** the Course Owner can sign in and the profile mark from Step 4
  remains saved across Stop → Start.
- **Evidence 7:** screenshot of the desk and My Profile still showing
  **Full Name: Owner** (the mark survived the restart).

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

## Backup and restore — Owner PRESERVATION / RESTORE HOLD

**No backup or restore action is authorized.** The Owner's retention choice is
unresolved. Do not create or change an effective policy, run `Backup TOEFL House
ERP.cmd` or its retention helper, trigger cleanup/deletion, decrypt a backup,
restore, activate/deactivate, or change the existing site. Preserve the current
site, `product/data`, all runtime data, credentials, and every existing backup.
The former in-place restore procedure in
[`docs/engineering/LAUNCH-RUNBOOK.md` §7](../../docs/engineering/LAUNCH-RUNBOOK.md)
has been withdrawn; do not follow saved copies of it.

### Read-only checks allowed while the hold remains

1. In the normal browser, note whether the existing site responds. Do not
   create or edit records. If it is unavailable, stop and contact engineering;
   do not attempt restore or replacement.
2. In Windows File Explorer, observe whether a separate fixed local drive on
   this PC is present and note its free-space figure. If an existing backup
   folder is visible, inspect only directory names and file metadata (names,
   sizes, timestamps). Do not open, copy, move, decrypt, or delete any file.
   Keep complete paths and backup-set names in Owner-controlled records; share
   only redacted status evidence.
3. In **Configuration desk → Backup & Recovery**, view—without editing or
   saving—whether an effective policy exists and whether the retention choice
   is unset. Do not create a policy version, validate/save changes, or start a
   backup.
4. If `TOEFL House ERP Backup` already appears in Task Scheduler, view its
   enabled state and last result only. Do not run, edit, enable, disable, or
   delete the task.

These checks use no command line and do not inspect backup contents. Never send
private keys, passwords, decrypted site configuration, raw backups, or
unredacted screenshots.

### Future restore target (not currently available on the Owner PC)

Any later engineering-approved rehearsal must target a **new unique Frappe site
and distinct database in an isolated disposable Bench/site-data root**, after a
disk-capacity preflight. It must not use `toeflhouse.localhost`, its database or
file trees, or the existing `product/data` volume. Use synthetic data only and
verify actual public/private file contents, record integrity, Frappe File
metadata, filesystem ownership/permissions, CWD restoration, failure paths, and
snapshot persistence after restarting the target. Do not clean up or alter the
existing site or any existing backup. The current Owner package has no qualified
isolated restore runner; do not improvise a restore command or treat CI as
Owner evidence.

### CI evidence boundary

- Product-image run
  [37940397957](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397957)
  passed its synthetic encrypted restore into the same disposable CI site and
  checked public/private markers after redeploy/restore. It does not restore to
  a separate target site.
- Native lifecycle run
  [37940397967](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/37940397967)
  passed after creating a separate restore site and database in an ephemeral
  Bench. It checks 14 DocTypes by count/name digest and a private File's content
  hash and selected attachment metadata. Public-file integrity, filesystem
  owner/mode/UID/GID, and a post-restore target restart are not established.
  The result artifact was not retrievable in this review, so exact per-run
  counts/hashes are unavailable.
- Neither run qualifies Windows, Docker Desktop, Task Scheduler, the Owner's
  same-computer backup drive, retention choice, key custody, or production
  recovery.

**Evidence 11–12:** do not report backup or restore as passed and do not send a
backup, private key, decrypted configuration, or password. Record only the
read-only checks above until an isolated Owner procedure is independently
approved.

---

## Finishing

Send engineering Evidence 1–10 for the non-destructive Windows lifecycle, plus
your Windows version and the date. Do not perform or submit backup/restore
Evidence 11–12 while the preservation/restore hold is open. Evidence 13 is
separate and remains unverified until the actual Tailscale/private-exposure
check is authorized and performed. Cover passwords and omit recovery keys,
backups, and decrypted configuration from all evidence. The Desktop release
gate remains **OPEN**; CI cannot close the Owner-machine gate.

## Later: switching on real operation (HOLD; not an instruction)

Do not run `Backup TOEFL House ERP.cmd`, `Activate TOEFL House ERP.cmd`, or
`Deactivate TOEFL House ERP.cmd` under the current hold. A future explicit Owner
retention decision alone is not authorization: the isolated restore procedure,
verified same-computer backup, actual Owner/deployment evidence, and every
applicable acceptance gate must be reviewed first, followed by separate
production authorization. Operational site mode is not release authorization;
production authorization remains **REJECTED**.

## Later: letting authorized staff access it from their computers

The ERP always listens only on the central PC (nothing is opened on the
public internet). Authorized staff PCs that are in your Tailscale network
reach it over that private network: Tailscale is installed on the central PC
and staff PCs. The supported Tailscale Serve setup has separate web and
`/socket.io` routes on the central PC (written out in the launch runbook
section "Multi-user access (central server + Tailscale)") so realtime requests
use the same HTTPS origin. Access is intended to be limited to your Tailscale
network members only; no firewall rule or public address is involved. CI does
not run Tailscale Serve or prove the actual tailnet/WebSocket path.

### Evidence 13 — private network and exposure (UNVERIFIED until actually checked)

1. On the central PC, follow
   [`docs/engineering/LAUNCH-RUNBOOK.md` §6](../../docs/engineering/LAUNCH-RUNBOOK.md)
   to configure Serve for the web port and `/socket.io`. Do not enable Funnel,
   router port forwarding, or a public firewall rule.
2. From a separate authorized staff PC that is joined to the Owner's tailnet,
   open the central PC's HTTPS tailnet name and sign in with that staff
   member's own ERPNext User. In the browser's developer tools, confirm the
   Socket.IO WebSocket handshake succeeds (HTTP `101`) and that an ordinary
   realtime desk update arrives without refreshing the page.
3. On a device not joined to the tailnet (for example, a phone with Wi-Fi and
   Tailscale both off), confirm the same address does not load. On the central
   PC, confirm `tailscale serve status` lists only the intended web and
   `/socket.io` routes, and `tailscale funnel status` reports that Funnel is
   not enabled.
4. **Evidence 13:** redacted Serve status plus screenshots/notes of the
   authorized-client sign-in, successful WebSocket/realtime check, and
   non-tailnet failure. Do not expose passwords, private keys, or public
   tunnels. If this topology is not deployed, leave the gate **UNVERIFIED**;
   CI proxy tests are not a substitute.

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

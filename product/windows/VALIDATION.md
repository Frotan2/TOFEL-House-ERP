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

---

## Before you start (once)

1. A 64-bit **Windows 10 or 11** PC with internet and ~30 GB free disk.
2. **Docker Desktop** installed: https://www.docker.com/products/docker-desktop/
   Its own installer is click-through and sets up WSL2 automatically if the PC
   asks. Restart the PC if it tells you to.
3. This repository unzipped anywhere (e.g. Desktop): on GitHub use
   **Code → Download ZIP**, then right-click the ZIP → **Extract All…**.

Then open the folder `product → windows` and do the steps below **in order**.
Do not skip or reorder steps — later steps prove earlier ones survived.

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
- **Expected:** the TOEFL House ERP desk (the work screen with menus/icons),
  not an error.
- **Evidence 3:** screenshot of the desk after login.

## Step 4 — Make a tiny mark (needed to prove persistence later)

- **Action:** click your name/avatar (top-right) → **My Profile** → set
  **Full Name** to `Owner` → **Save**.
- **Expected:** a saved confirmation, no error.
- **Evidence 4:** screenshot showing **Full Name: Owner**.

## Step 5 — Stop

- **Action:** double-click `Stop TOEFL House ERP.cmd`.
- **Expected:** it says "TOEFL House ERP has stopped." and the window closes
  by itself. The browser page will no longer load (that is correct).
- **Evidence 5:** screenshot of the stopped message (or a photo of the
  refreshed browser showing the page no longer loads).

## Step 6 — Start

- **Action:** double-click `Start TOEFL House ERP.cmd`, wait (usually 1–5 min).
- **Expected:** it waits, then opens the browser at `http://127.0.0.1:8000`
  and closes its window by itself.
- **Evidence 6:** login as in Step 3; screenshot of the desk **and** of
  My Profile still showing **Full Name: Owner** (your mark survived a stop).

## Step 7 — Backup

- **Action:** double-click `Backup TOEFL House ERP.cmd`, wait until it prints
  "Backup finished" and a folder path ending in
  `data\sites\toeflhouse.localhost\private\backups`. Press any key to close.
- **Expected:** that folder now contains **new files with today's date**
  (at least one file ending in `-database.sql.gz` and one ending in
  `files.tar`).
- **Evidence 7:** screenshot of that folder in File Explorer showing the new
  files with today's date. (Good habit: copy the whole folder to a USB drive.)

## Step 8 — Repair

- **Action:** double-click `Repair TOEFL House ERP.cmd`, wait (a few minutes).
- **Expected:** it restarts services, waits, then opens the browser and says
  "Repair complete". It never deletes data.
- **Evidence 8:** screenshot of the Repair window's "Repair complete" message
  (take it before pressing a key to close).

## Step 9 — Browser access after repair

- **Action:** in the browser it opened, log in as in Step 3.
- **Expected:** the desk loads normally.
- **Evidence 9:** screenshot of the desk after login.

## Step 10 — Persistence

- **Action:** open **My Profile** again.
- **Expected:** **Full Name: Owner** is still there — your mark survived the
  full Stop → Start → Backup → Repair cycle.
- **Evidence 10:** screenshot of My Profile showing **Owner**.

---

## Finishing

Send engineering: one message/email containing **Evidence 1–10** (password
covered/blurred wherever it appears), plus your Windows version and the date
you ran this. Engineering maps the ten items onto the release-gate steps and
closes the **Desktop release gate**, which is OPEN until exactly this evidence
set is confirmed.

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

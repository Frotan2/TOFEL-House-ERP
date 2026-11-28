# Install TOEFL House ERP on the institute computer (new installation)

This is the only guide you need for a **new** computer that has never had
TOEFL House ERP. It contains no update or migration steps. The program checks
itself at each stage. If a screen shows a red error, stop and use
**Check This PC → Copy Safe Support Status** (see "Help" at the end).

**Do not enter real students, payments or salaries until Part F says that
activation succeeded.** Before that, the ERP refuses real operation by design.

## The one file you need

| Item | Value |
| --- | --- |
| Release | `ci-fbe4ec8f4280` (source revision `fbe4ec8f4280e240bb4e34daa26506186a54acf7`) |
| Download (sign in to GitHub first) | [TOEFL-House-ERP-Offline-Setup-TEST-fbe4ec8…](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/46160509937/artifacts/15270638125) (1.19 GB ZIP, available until 26 Feb 2027) |
| File inside the ZIP | `TOEFL-House-ERP-Setup-TEST.exe` |
| Correct SHA-256 of the EXE | `df35bca8c70ba64f440d63606b33da176c3e70c862bb09b85a1ebeaf6da765d9` |
| Independent confirmation of that SHA-256 | [GitHub build attestation](https://github.com/Frotan2/TOFEL-House-ERP/attestations/73481776) |

The EXE already contains the application, its database programs and all the
tools in this guide. You do **not** need the 3.6 GB "Customer" package, the
"Offline runtime" download, or a source ZIP. Keep a copy of the EXE on a USB
drive. You will need it again only if a repair is ever required.

## What to have ready

- **ERP computer:** Windows 10 or 11 (64-bit), at least 8 GB RAM, at least 30 GB
  free on drive C:, and a Windows account with administrator rights.
  Virtualization must be on. To check, open **Task Manager → Performance → CPU**:
  it must show "Virtualization: Enabled". If it does not, turn it on in the BIOS.
- **Internet on the ERP computer during installation.** Setup downloads Microsoft
  WSL and Docker Desktop and checks their fingerprints before using them.
- **A backup disk:** a second internal disk, or an external USB hard disk or SSD,
  that stays connected. A USB flash stick is not accepted, and neither is
  another partition of the same disk.
- **Two people with signing authority,** each with their own computer (not the
  ERP computer): the **Course Owner** and the **General Manager**.
- **For staff access from other computers:** someone who can manage the
  institute router and firewall (Part D).

---

## Part A: Install (IT person, about 1–2 hours)

1. **Check the file.** Unzip the download. Install 7-Zip if needed, right-click
   `TOEFL-House-ERP-Setup-TEST.exe` and choose **7-Zip → CRC SHA → SHA-256**.
   The result must equal the SHA-256 in the table above, character for
   character. If it is different, **stop** and do not run the file.
2. **Allow this internal build to run.** It is verified by SHA-256, not by a
   paid code-signing certificate, so Windows needs two settings:
   - Right-click the EXE → **Properties** → tick **Unblock** → **OK**.
   - Open the developer settings page:
     - Windows 10: **Settings → Update & Security → For developers**.
     - Windows 11: **Settings → System → For developers** (called **Advanced**
       in newer versions).

     Under **PowerShell**, switch on "Change execution policy to allow local
     PowerShell scripts to run without signing".
3. **Double-click the EXE.** Then:
   - Approve the Windows administrator prompt.
   - Accept the Docker Desktop licence when it appears. Skip any Docker sign-in.
   - If Windows asks to restart, restart. Setup continues by itself after you
     sign in again.
   - The installation is finished when the **TOEFL House ERP** window says
     "TOEFL House ERP is ready. Opening in your browser." and a **TOEFL House
     ERP** desktop shortcut exists.

   Opening the same EXE again only opens the program. It never creates a
   second database.
4. In the TOEFL House ERP window, click **Check This PC**. Keep the result as
   your installation record.

## Part B: First sign-in and the Owner's account (about 30 minutes)

1. In the ERP window, click **View Administrator Login** and note the password
   privately. Click **Open / Start**. The browser opens
   `http://127.0.0.1:8000/`. Sign in as `Administrator`.
2. Complete the setup wizard:
   - Language: English. Country: Afghanistan. Time zone: Asia/Kabul. Currency: AFN.
   - Your own name, email and a strong password (this becomes the setup account).
   - The institute's company name.
3. Change the Administrator password: **User list → Administrator →
   Change Password**. Keep it sealed. Nobody uses Administrator for daily work.
4. Create the Owner's account:
   - **User list → Add User**: enter the Owner's email and name, then **Save**.
   - Under **Roles**, tick **Course Owner**, then **Save**.

## Part C: Encrypted backup (Course Owner, about 30 minutes)

1. **Create the recovery key** on the Owner's own computer, not the ERP computer:
   - Install **Gpg4win** and open **Kleopatra**.
   - Choose **File → New OpenPGP Key Pair**. Enter the Owner's name and email
     and protect the key with a passphrase.
   - Right-click the key → **Export** to save the public key (`.asc`).
   - Use **Backup Secret Keys** to copy the private key to two USB sticks.
     Store them in two different safe places, away from the ERP computer and the
     backup disk. **Without this private key, backups cannot be restored.**
2. **Save the backup settings.** Sign in to the ERP as the Owner, then go to
   **Configuration → Backup & Recovery → Save and validate backup settings**.
   Enter these values (they match the approved policy):

   | Field | Enter |
   | --- | --- |
   | Change reason | Initial backup setup |
   | Nightly backup time | 02:30 |
   | Backup keep count | 3 |
   | Backup retention behavior | Delete valid older sets beyond keep count |
   | Recovery public key | Open the `.asc` file in Notepad and paste all of its text |
   | Key custody requirement | One sentence on where the private key copies are kept |
   | Recovery quorum | 2 |

   Then click **Turn backup On**.
3. In the ERP window, click **Back Up Now** and choose the backup disk. When it
   finishes, click **Verify Backup**. It must report a verified backup.
   - The nightly backup runs automatically at 02:30. For it to run, the computer
     must be **on or asleep** (not shut down), signed in (it can be locked), and
     the backup disk must be connected.
   - If a night is missed, the backup runs as soon as the computer is available.

## Part D: Private access for staff computers (IT person, about 1 hour)

Click **Private HTTPS** in the ERP window. The full instructions are in
`%LOCALAPPDATA%\TOEFL House ERP\Customer\product\windows\Private HTTPS Setup.md`.
In short, the IT person:
- reserves an IP address and a private name for the ERP computer;
- prepares the HTTPS files with the form;
- allows only the staff network in the Windows firewall;
- installs the certificate on staff devices.

Then two staff devices must open the private `https://` address without a
warning. A guest network must **not** be able to reach it. Activation requires
this check. Do not sign staff in yet.

## Part E: Signing keys (once; Course Owner and General Manager, each separately)

Each signer does this on **their own** computer. Never on the ERP computer.

1. Install **Python 3** (python.org, default options) and **Git for Windows**,
   which includes OpenSSL.
2. Open **Git Bash** and run this single line:

   `openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -aes-256-cbc -out toefl-signing-key.pem`

   Type a passphrase twice. Keep `toefl-signing-key.pem` on your own USB stick.
   Never send it to anyone.
3. Copy the **Approval Signing** folder from the ERP computer to your computer
   by USB. It is at `%LOCALAPPDATA%\TOEFL House ERP\Customer\Approval Signing`.
4. Open `tools\release\Sign Internal Activation.pyw` and fill in:
   - **Your role.**
   - **Choose your private RSA key:** your `.pem` file.
   - **Choose approved OpenSSL:** `C:\Program Files\Git\usr\bin\openssl.exe`.
   - **Choose output folder.**
   - **Key passphrase.**
5. Click **Export my public key**, then enter your full name and a key ID, for
   example `owner-2026` or `gm-2026`. Use exactly the same name and key ID
   everywhere later.
6. Give the IT person the public `.json` file by USB. Read the SHA-256 that the
   tool shows to the IT person by phone.

On the ERP computer, the IT person registers the keys (first time only):
**Apply Approvals → Register public keys**. Choose both public files, type each
SHA-256 exactly as the signer read it out, then click **Review and register**.

## Part F: Activation day (Owner, General Manager and IT person, within 8 hours)

1. **Make a fresh backup.** In the ERP window, click **Back Up Now**, then
   **Verify Backup**. Activation accepts only a backup made in the last 24 hours.
2. **Create the request.** Click **Activation Request** and enter:
   - **Host evidence reference:** for example "Institute PC installation record,
     date, Check This PC passed".
   - **Source revision:** `fbe4ec8f4280e240bb4e34daa26506186a54acf7`.
   - **Installer SHA-256:** `df35bca8c70ba64f440d63606b33da176c3e70c862bb09b85a1ebeaf6da765d9`.
   - **Names and key IDs** of the Course Owner and the General Manager, exactly
     as in Part E.

   Tick each box only when it is true:
   - **Windows host acceptance:** Part A finished, Check This PC passed, and the
     ERP opens again after a Windows restart.
   - **Two staff devices and excluded access:** Part D.
   - **Separate key custody:** Part E. Each signer holds only their own key.
   - **Isolated recovery evidence reviewed:** existing evidence is reused, so
     **no restore is done on this computer**. The evidence is the Windows
     separate-database recovery
     ([readiness record](engineering/RELEASE-READINESS-2026-11-11.md)) and the
     isolated restore test on this exact release
     ([native lifecycle run](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/46160529864)).
   - **Backup disk is physically separate:** Part C.

   Click **Save unsigned request** and choose a USB folder. Write down the
   request SHA-256 that it shows.
3. **Sign.** The Owner and the General Manager each, on their own computer:
   - Open the signing tool and click **Choose activation request**.
   - Type the request SHA-256 that the IT person reads out by phone.
   - Choose your role, key, OpenSSL and output folder, and enter your passphrase.
   - Click **Sign my approval**.
   - Bring the signature file back by USB.
4. **Apply.** On the ERP computer:
   - Click **Apply Approvals** and choose the request and both signature files.
   - Tick the confirmation and click **Verify and apply**.

   A success message means the ERP is activated for real work. If the request
   expires (after 8 hours) or anything is refused, nothing is changed: start
   again from step 1.

## Part G: Start daily work

1. **Set up the courses.** The Owner opens **Academic Setup**, checks programs,
   levels, fees and classes, and clicks **Initialize new course catalog**.
2. **Create staff accounts.** For each person: **User list → Add User** → email
   and name → **Save** → tick their role(s) → **Save**. Then give them their
   branch: **User Permission → Add**, with User = the person, Allow = Branch, and
   Value = their branch. Reception accounts must have a branch.

   | Job | Role to tick |
   | --- | --- |
   | Owner | Course Owner |
   | General Manager | General Manager |
   | Academic manager | Academic Manager |
   | Finance manager / cashier | Finance Manager |
   | Reception | Reception |
   | Teacher | Instructor |

   Give the specialist roles only when the Owner assigns those duties. These
   are the Placement, Admission and Enrollment roles, Teaching Scheduler,
   Attendance Recorder, Finance Officer and the Auditor roles. Never give one
   person both the "prepare" and the "approve" role in the same process.
3. **Daily use:**
   - On the ERP computer, open the **TOEFL House ERP** shortcut → **Open / Start**.
   - Staff open the private `https://` address and sign in with their own account.
   - Each person sees only their own desk.
   - The **How to Use** button opens the daily guide.
   - Each morning, click **Verify Backup**.

## Not needed for this new installation (update-only)

These apply only when updating an existing installation, such as the old
HP ENVY test computer. Skip them all:
- the 3.6 GB Customer/update package and the Offline runtime download;
- **Check for Updates**, **Install Update**, `Service Existing TOEFL House ERP`,
  update bundles and their provider signature;
- the owner-update policy and approval, and the two-person *recovery
  authorization* for updates;
- any migration, data import, or restore on this computer;
- `OWNER ACCEPTANCE GUIDE.txt` and the preservation hold in `VALIDATION.md`.
  Both describe the old test computer.

## Never

- Never run a second installer over this installation, and never reset Docker
  or delete its data.
- Never put a private signing key or recovery key on the ERP computer, and never
  send keys or passwords by email or chat.
- Never use the Administrator account, or someone else's account, for daily work.

## Help

Click **Check This PC**, then **Copy Safe Support Status**, and send only that
text to trusted support. It contains no passwords or personal data.

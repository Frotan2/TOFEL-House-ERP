# Customer delivery: Windows graphical setup and offline application image

**Release status: engineering candidate only — DO NOT SHIP TO A CUSTOMER YET.**
The current production authorization is **REJECT**. The Owner preservation,
backup/restore and real-machine qualification holds take precedence over
this packaging guide. This document describes the installation capability,
not permission to operate real student, payroll or financial data.

## The customer experience

The customer receives a dedicated **TOEFL-House-ERP-Customer-...** folder
prepared by the provider. The provider has already built the application
image and included it in the delivery, so the customer does not use Git,
clone a repository, type commands or build Frappe from source.

1. Use a compatible 64-bit Windows 10/11 computer with enough free disk space
   for Docker Desktop, the application image, the database and backups.
   Install **Docker Desktop** using its official Windows installer. On some
   computers it must also install or enable WSL 2, request administrator
   approval, change virtualization settings, or restart Windows. This is a
   third-party prerequisite, **not** an unattended single-click install.
   Confirm that the customer's organization meets Docker Desktop's current
   commercial license terms before supplying it.
2. Copy or extract the entire customer folder onto the local main computer,
   not a removable drive, cloud-synchronized folder or network share.
   Double-click **TOEFL House ERP.vbs**. This opens the Windows GUI without
   a terminal or PowerShell commands.
3. Select **Install**. The launcher verifies the image checksum, imports the
   prebuilt application, generates a private local database password on the
   first installation, initializes the site and waits for health checks.
   It then opens the ERP in the browser.
4. Select **View Administrator Login** to open the local, private first-run
   credentials file. Change the initial password and create a separate
   native **Course Owner** account for normal administration. Do not email
   or photograph the credentials. Owner policies and real-operation mode
   remain subject to the documented release hold.
5. Select **Check This PC** for a read-only technical report. The report
   checks Windows, Docker availability, local disk space and loopback login
   reachability without touching the existing site, backup, secrets or Docker
   volumes. It does not qualify backup/recovery, Tailscale or production use.
6. On later days, open the same GUI and click **Open / Start**. Use **Stop**
   to shut down services safely, or **Repair** for an interrupted installation.
   The window stays open during active operations. Logs are kept under the
   current Windows user's LocalAppData; sharing them requires care because
   diagnostics may contain private technical information.

**Important:** The customer cannot move an installed ERP merely by copying
the delivery folder. The database lives in a Docker named volume while site
files and local secrets live in product/data. Transfer and recovery require
a separately verified backup/restore process, which is currently on HOLD.
Do not erase volumes, delete product/data, or replace an existing database
password just to repeat installation.

## How the provider prepares the folder

From a verified source checkout with a built local image tagged
toefl-house-erp-app:local, open
product/windows/Prepare Customer Package.ps1 in Windows PowerShell, or run
it with a chosen Destination path. The provider-side utility:

- Confirms Docker is running and the image includes the Linux LF-source
  contract label.
- Copies only the explicitly allowed Windows GUI, lifecycle scripts and
  Compose configuration. It never copies source repositories, Docker data,
  administrator credentials, active site files, activation receipts or backups.
- Uses docker save to write product/release/toefl-house-erp-app.tar, and writes
  a SHA-256 checksum next to it. It verifies the archive again after export.
- Creates a new, timestamped customer folder and an English quick-start
  readme. It does not overwrite an existing package. An interrupted/failed
  package must be discarded by the provider after inspection, not delivered.

The SHA-256 file catches corruption and casual package damage. It does **not**
authenticate the author: a malicious party able to replace both tar and hash
can replace the image. Before commercial distribution, introduce a signed
release manifest, controlled versioning and publisher identity verification.
The packaged image must also be bound to an independently checked, approved
source revision; the current LF label alone does not prove that.

The customer GUI intentionally offers **no** Backup, Restore, Activate,
Deactivate or production bypass controls while the relevant holds apply.
The older specialized guarded scripts remain in the developer repository for
future authorized workflows but are excluded from customer packages.

## Verification: what has and has not been shown

| Capability | Verification boundary |
| --- | --- |
| Docker app image startup in disposable Linux CI | Product image workflow; not equivalent to customer Windows |
| Windows script syntax, synthetic image packaging and tamper rejection | Windows customer package workflow |
| Source installation, existing-site checks, no-discard lifecycle | Owned tests and source contract checks |
| Isolated synthetic restore to a new site/database/site-data root + wrong-key failure + post-restart verification | **QUALIFIED IN HOSTED CI — run 39836321651; NOT OWNER-MACHINE AUTHORIZATION** |
| Owner-policy persistence across a real hosted service restart | **QUALIFIED IN HOSTED CI FOR ALL EIGHT POLICIES** |
| Real clean Windows installation with Docker Desktop and WSL 2 | **NOT YET QUALIFIED** |
| Prebuilt multi-GB image import on a real customer PC | **NOT YET QUALIFIED** |
| Administrator GUI interaction and login | **NOT YET QUALIFIED ON REAL WINDOWS** |
| Local backup, encrypted restore and data persistence through device failure | **HOLD / NOT YET QUALIFIED** |
| Multi-user Tailscale access on real devices | **NOT YET QUALIFIED** |
| Production authorization for real student/financial data | **REJECT** |

### Required customer acceptance before any release

On a disposable clean Windows PC, use **only synthetic data** and complete
the following as one continuous test: obtain the prepared package, install
Docker Desktop from the GUI link, complete WSL/reboot if requested, launch the
ERP without a terminal, authenticate as Administrator, restart Windows and
start again, create a synthetic course/student/enrollment/fee/attendance,
verify persistent records, exercise stop/start and non-destructive repair,
test separate backup and isolated restore after its hold is resolved,
and verify access on an authorized Tailscale staff PC.

Record version, image identity, Windows edition, Docker version, elapsed
time, screenshots, permission prompts, failure recovery and network boundary
evidence. Only then consider releasing the package to real customers.

### Common installer support issues

- If Docker is missing, the GUI opens Docker's official download site.
  Completing the vendor installation or WSL/reboot may need the customer's
  authorized Windows administrator.
- If a password file is missing but a database already exists, the product
  **refuses to generate a replacement password**. Recover the original,
  do not reinstall or delete data.
- If the archive checksum fails, the installer **must not** import or start it.
  Obtain an intact, trusted package from the provider.
- If the user has a repository checkout rather than a package, the GUI can
  explicitly offer a source build. This slow developer fallback is **not**
  the intended customer experience.
- If Windows Script Host is disabled by policy, the Windows launcher may
  not run. A signed Windows executable/installer and enterprise packaging
  support are future distribution requirements; do not disable customer
  security controls to bypass that restriction.

For current policy/activation and recovery limitations see
[PRODUCT.md](PRODUCT.md) and
[engineering/LAUNCH-RUNBOOK.md](engineering/LAUNCH-RUNBOOK.md).

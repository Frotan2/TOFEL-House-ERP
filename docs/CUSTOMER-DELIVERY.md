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
The provider also compiles the browser bundles. Startup restores the compiled
manifest and assets from the image; first boot still installs native database
records and runs migrations, which must be timed during customer acceptance.

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
3. Select **Install**. The launcher verifies the image checksum **before**
   creating any local database credentials or application data. It generates a
   private local database password for a genuinely fresh installation, imports
   the verified prebuilt image, initializes the site and waits for health
   checks. If previous Frappe site files exist under another site name, it
   preserves them and refuses to create a replacement database password.
   It then opens the ERP in the browser.
4. Select **View Administrator Login** to open the local, private first-run
   credentials file. Change the initial password and create a separate
   native **Course Owner** account for normal administration. Do not email
   or photograph the credentials. Owner policies and real-operation mode
   remain subject to the documented release hold.
5. Select **Owner Readiness Guide** to read a no-command, read-only first-check
   and a separate synthetic Windows test checklist directly from the GUI.
   This does not lift the backup/restore hold or authorize production.
   Select **Check This PC** for a read-only technical report. The report
   checks Windows, Docker availability, local disk space, possible fixed local
   backup volumes, the presence (never contents) of database storage and its
   credential file, and localhost reachability. It warns if a database/site
   exists without its credential file. It never changes the existing site,
   backup, secrets or Docker volumes. It does not qualify backup/recovery,
   Tailscale, publisher trust or production use.
6. On later days, open the same GUI and click **Open / Start**. Use **Stop**
   to shut down services safely. **Do not use Install again** on an existing
   site; the launcher now refuses a repeated installation. **Repair** is only
   for a provider-authorized recovery attempt on an intact existing site, not
   a data restore or a fix for a missing database. The window stays open
   during active operations.

**Preservation gate for existing installations:** Start and Repair now check
that `db.env`, the Frappe site's `site_config.json`, and the exact named
Docker database volume are present and accessible **before** running Compose.
If anything is missing or unverifiable, they refuse to run rather than risk
creating a new empty database volume. This is an existence check, **not**
proof that records or backups are healthy. Do not replace credentials,
reinstall, recreate a volume, or bypass the refusal. Use the GUI's
**Check This PC → Copy Safe Support Status** to share only the fixed, safe
summary with trusted support. Logs are kept locally under LocalAppData; do
**not** email or zip entire raw logs, student records, secrets or backups.

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

- Confirms Docker is running and the image includes the Linux LF-source,
  exact source-revision, and exact release-version labels.
- Copies only the explicitly allowed Windows GUI, Owner readiness guide,
  lifecycle scripts and Compose configuration. It never copies source repositories, Docker data,
  administrator credentials, active site files, activation receipts or backups.
- Uses docker save to write product/release/toefl-house-erp-app.tar, and writes
  an archive checksum, release manifest, dependency-matrix hash, and manifest
  checksum. It verifies the bound archive before delivery.
- Creates a new, versioned customer folder and an English quick-start readme.
  It does not overwrite an existing package. An interrupted/failed package
  must be discarded by the provider after inspection, not delivered.

The provider/CI implementation is also available as
`tools/release/create_customer_package.py`. The Product image workflow uses
it after the real image and all hosted qualification steps pass, creates a ZIP,
attests that ZIP with GitHub's build-provenance service, uploads the versioned
artifact, and publishes a GitHub Release asset only for an explicit `v*` tag.
The ZIP is the customer download; the included manifest binds the exact source
revision, image labels, image hash, and dependency matrix. Verify the
attestation separately. A package that has only a bare tar/hash pair is not a
verified customer release.

Both packagers require the selected checkout HEAD and clean customer inputs
to match the requested revision. The saved archive, manifest, imported tag,
and Compose image all use `toefl-house-erp-app:local`. Verification reads the
actual archive config before import and checks the loaded image's identity
before startup. The manifest checksum is mandatory. CI refuses a ZIP at or
above GitHub's 2 GiB per-file release limit; the runtime image excludes build
checkouts and intermediate build layers to keep the single download viable.

The SHA-256 and manifest sidecars catch corruption and bind the package
contents. They do **not** replace the provider/GitHub attestation: a malicious
party able to replace both an archive and its local hash could otherwise
replace the image. The Windows verifier checks the manifest and image hash
before import; it never treats those checks alone as production approval.

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

## No-code staff help in the customer launcher

The installed Windows GUI now includes **How to Use**, which opens an offline
plain-English **DAILY USE GUIDE.txt** supplied in the allowlisted customer kit.
It explains the Owner, Reception, Academic, Teacher and Finance routines and
how the native ERPNext stock-book workflow works without developer commands.
It does **not** grant access, activate production, or replace the separate
Owner Readiness Guide and real Windows/customer recovery approval.

### Safe support status for nontechnical users

After the read-only **Check This PC** succeeds, the Windows launcher enables
**Copy Safe Support Status**. This copies only whitelisted machine readiness
status lines, not raw Docker/PowerShell logs, secrets or student records.
It does not approve live use, authorize backup/restore or connect to a
support service without the owner's direct action.

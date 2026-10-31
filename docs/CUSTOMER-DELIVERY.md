# Customer delivery — one offline Windows Setup EXE

**Current release decision:** **REJECT / NO-GO — TEST PACKAGE, NO REAL DATA.**
This is the target delivery contract and engineering integration path, not a
claim that a completed, signed, independently accepted customer installer
exists. Do not install over the preserved Owner installation.

## Accepted customer experience

The authorized provider supplies **one publisher-signed offline Windows Setup
EXE** for a supported 64-bit Windows 10/11 computer. The Owner double-clicks
the installer, follows graphical Windows administrator/license/restart prompts
when necessary, and completes institute setup in **English**, left to right.

The customer must not:
- Download Docker Desktop, WSL, Linux images or application dependencies;
- Open a terminal or run PowerShell, Git, Python or database commands;
- Extract a repository ZIP, nested ZIPs or source files, or compile anything;
- Supply JSON policy values, invent staff email addresses, or initialize a
  practice database that later becomes the institute's real database.

The signed installer bundles a prebuilt TOEFL House Linux/amd64 image,
digest-pinned MariaDB and Redis images, compatible provider-verified Windows
prerequisite installers, the graphical launcher, operating instructions,
a release manifest and exact-source gate evidence. Its internal ZIP64 payload
is extracted automatically; **there is no customer-managed nested archive**.

A Windows feature source or firmware virtualization configuration that
cannot be satisfied offline must trigger a clear refusal and provider remedy,
not send the customer to a website. The user must accept any applicable
third-party license themselves; the provider verifies Docker Desktop
distribution and commercial licensing before release.

## First installation and safe re-opening

1. Check the publisher's Authenticode signature, release identity, installer
   digest and the full Git revision through the trusted provider.
2. In an **approved disposable Windows acceptance environment**, double-click the EXE. It
   verifies its embedded payload before extraction and publishes the
   extracted kit only after validation. The Windows setup step verifies
   bundled prerequisite SHA-256 hashes and trusted Microsoft/Docker
   publisher signatures.
3. If Windows requests an authorized restart, perform it normally and reopen
   the same Setup EXE. A repeated launch must **never** create a replacement
   site, user or database. On a verified existing installation it opens the
   normal GUI without attempting fresh installation.
4. On a genuinely empty site, initialize native application services, then
   authenticate locally (normally `http://127.0.0.1:8000/`). Protect the
   initial Administrator credentials and configure the existing Course Owner
   account without duplicating it.
5. Complete the Owner's approved catalog, calendar, rooms, tuition and
   role-specific staff setup with guarded forms. **No historical or synthetic
   business data is shipped**: students, enrollments, attendance, assessment,
   payroll, invoices, payment entries and demo records all start at zero.
6. On later days, use the normal graphical **Open / Start**, **Stop** and
   authorized support workflows. Ordinary customer actions must never
   require developer tooling.

The current repository also has an image-inclusive **folder/VBS engineering
fallback**. It can be used under provider supervision with an isolated test
site on the existing Windows PC, preserving the Owner installation. This does
not substitute for the clean offline first-install gate below. It is **not** the accepted final customer delivery,
and an old GitHub Actions ZIP is not proof of an approved EXE.

## Provider-only building and verification

The provider first qualifies the exact source revision through the required
Owned, Native, Foundation, Product-image and Windows package gates.
The source image and native runtime images are exported from the pinned
Linux/amd64 identities. The Windows packaging workstation then uses:

`tools/release/Build Customer Installer.ps1`

It takes a verified image-inclusive kit, the vetted WSL MSI and Docker
Desktop EXE, a distinct output path, and optionally an exact-source
`RuntimeBundle`. It independently checks the package image, prerequisite
publishers, runtime manifest, hashes, native image identities and forbidden
customer data/links; the resulting offline Compose override has
`pull_policy: never`.

For an actual publisher-signed artifact the provider additionally supplies
`SigningCertificateThumbprint` and a Windows-compatible HTTP
`TimestampServer`. The signer must hold a valid code-signing private key.
The final EXE's signature, signer identity and timestamp must all verify
**before** the artifact is published. An output created without these
parameters is conspicuously an **UNSIGNED TEST INSTALLER ONLY**; it cannot
satisfy the customer contract. The currently supported provider builder
accepts only **REJECT**-classified test manifests; production packaging
requires a separately reviewed, authorized release process.

The signing path is not yet independently Windows-qualified. A conventional
PE Authenticode certificate-table offset is bounded; the provider must
make the image bundle small enough to be signed and verified, rather than
pretending that an oversized executable can be safely issued. A GitHub
Release file-size limit is **not** waived by assembling an EXE. If a single
signed file cannot fit the distribution/signing limits, customer handover
remains blocked until a reviewed delivery architecture resolves this
without extra customer downloads or manual archive extraction.

## Preserve previous installations and recovery material

Before any customer lifecycle operation, preserve the installed site,
`product/data`, local credentials, named MariaDB volume, key custody and
encrypted backup sets. The launcher and worker must **refuse** replacement
database creation when existing site or credential/volume markers are
missing or inconsistent. No one may use reinstall, Docker reset, volume
deletion, update replay or live-site overwrite to bypass a failed check.

Only **Check This PC** and **Copy Safe Support Status** are supported
read-only diagnosis paths during the existing Owner preservation hold.
The safe support text must exclude student records, passwords, raw logs,
invoices, keys and backup content. The update channel remains disabled
pending independent authorization and two-person recovery acceptance.
See [Customer updates](CUSTOMER-UPDATES.md) and
[Windows validation](../product/windows/VALIDATION.md).

## Independent release acceptance — mandatory evidence

| Gate | Required evidence | Present acceptance |
| --- | --- | --- |
| Exact source and supply chain | Same full SHA, five successful CI gates, verified provenance and pinned dependencies | Recheck latest `work` head |
| Final customer artifact | One publisher-signed EXE; trusted timestamp, validated SHA-256, safe single-file extraction and size | **NOT QUALIFIED** |
| Clean offline Windows | Fresh Windows installation without network/tool downloads, accurate UAC/license/reboot, local login, Stop/Start/repair and persistent state | **NOT QUALIFIED** |
| Staff and native workflows | Six segregated roles; admissions, placement, scheduling, fees, cashier, books, refunds, grading and payroll with negative permission/replay tests | **NOT QUALIFIED ON FINAL INSTALLED IMAGE** |
| Recovery and updates | External encrypted drive, distinct recovery approvers, isolated restore with matching records and guarded update/rollback | **HOLD / NOT QUALIFIED** |
| Final approval | Independent security review, protected release branch, explicit written Owner production authorization | **REJECT** |

Use synthetic data **only** in isolated acceptance, never on the Owner's
preserved system. Record image and Windows versions, source SHA, installed
config, privacy-safe test evidence, crash/restart recovery, package signature,
role isolation and native ledger reconciliation. No individual green test,
downloadable ZIP, successful local browser login or reported EXE build can
override the final NO-GO decision.

For authoritative documentation precedence, see
[Documentation and release authority](DOCUMENTATION.md). For provider
technical details and retained earlier engineering evidence, see
[Single-file delivery](engineering/SINGLE-FILE-CUSTOMER-DELIVERY.md).

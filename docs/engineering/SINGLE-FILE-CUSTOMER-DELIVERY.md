# Single-file Windows customer delivery

The customer requirement is one Setup EXE, no typed commands, installation
websites, manual downloads, developer checkout or manually nested ZIP extraction.
Windows UAC, Docker's license dialog and a Windows restart can still require a
normal graphical response. Firmware virtualization cannot be enabled by this app.

## Confirmed original defects at c2216b7

- `Install TOEFL House ERP.cmd` opened Docker's website if Docker was missing.
- The GUI blocked Install before a prerequisite installer could run.
- Product-image's Actions upload included an already-compressed customer ZIP and
  a second directory containing only manifest/gate files. GitHub wraps this upload
  in another ZIP. That produces nested archives and a confusing partial directory;
  it does not establish that two complete application copies were downloaded.
- The application TAR did not include the digest-pinned MariaDB and Redis images.
  Compose could fetch those from a registry on the customer computer.

The Actions customer artifact now uploads one complete directory directly. One
extraction exposes the launcher and product directory. Tagged ZIP releases remain
single ZIP downloads. This fixes nesting; it does not turn a CI artifact into the
final one-file customer installer.

## Provider assembly

`tools/release/Build Customer Installer.ps1` accepts a newly qualified customer kit,
a publisher-signed x64 WSL MSI, a publisher-signed Docker Desktop offline installer,
and a new EXE output path. Only the provider uses this script. Do not ask the
customer to run it or obtain these inputs.

The Product image workflow now exports the runtime inputs on Linux, then runs
`offline-windows-installer` on Windows after the exact-source app gates pass.
For the ordinary work/main engineering pipeline it uses the verified
`create_customer_package.py --no-zip` folder output: a multi-gigabyte
customer EXE no longer depends on first producing a duplicate ZIP below the
legacy GitHub Release 2 GiB limit. Tagged legacy releases still request
the ZIP separately and correctly refuse to publish when it exceeds that
limit. The provider obtains the allowlisted folder automatically through
the trusted CI artifact; the customer only receives the final EXE.
That job downloads the original qualified kit and runtime exports from its own
run, retrieves official WSL/Docker binaries using the committed version/URL/hash
catalog, checks their publisher signatures, builds the actual offline TEST EXE,
and publishes it with GitHub artifact provenance. None of these downloads run on
the customer computer. This still does not replace clean-machine acceptance or a
publisher-signed production release. The Windows builder accepts `RuntimeBundle`
so it does not need nested Linux virtualization on a hosted Windows runner.

The provider script verifies the application kit, rejects customer data and links,
copies the offline Windows installers, fetches the exact digest-pinned Linux/amd64
MariaDB/Redis images, and exports them with local tags. The offline Compose override
sets `pull_policy: never`. A manifest records archive hashes, full image Config and
RootFS identities; the customer importer verifies both archives before the first
import, and verifies each loaded image before starting ERP services.

The builder compiles the small C# GUI extractor, then appends a ZIP64 payload and
an integrity footer. This avoids embedding multi-gigabyte resources in the PE
compiler and avoids requiring another archiver on the customer's computer. The
extractor validates paths before writing, refuses traversal and duplicate names,
uses an atomic move after extraction, and refuses to overwrite an existing kit.
Its footer reader supports the PE certificate table appended by Authenticode.
Integrity checks are not a publisher signature. The provider-only builder
now accepts `SigningCertificateThumbprint` and `TimestampServer` (a Windows
Authenticode-compatible HTTP endpoint), signs the fully assembled temporary
EXE and verifies the signer identity and timestamp before publication. An
unsigned build is explicitly labelled **UNSIGNED TEST INSTALLER ONLY**. The
actual temporary executable is run with `--verify-payload` after signing and
before it is moved to the published output path. Traditional PE certificate
table offsets are 32-bit; an assembled EXE that is too large for signing is
rejected rather than passed off as signed. Real trusted certificate/signing
and offline clean-Windows acceptance remain outstanding.

The customer opens Setup, which extracts to the current user's local application
folder and opens the GUI with Install selected. The worker verifies the app image
before prerequisite installation. Windows preparation uses only the supplied
installers, validates SHA-256 and publisher signatures, requests normal UAC
approval, enables local Windows components without Windows Update downloads,
and returns a restart request rather than rebooting the customer's open work.
Reopen Setup after the restart and select Install. Existing/partial ERP site
markers refuse fresh installation before prerequisite changes.

## Release limits and required evidence

This is a new delivery path, not evidence of a completed customer installation.
The original kit's app and CI provenance remain intact; added prerequisite/runtime
assets are bound by the final EXE artifact and must be included in its signed
provenance. Do not describe the earlier CI receipts as qualification of these
additional binary assets or a real Windows installation.

Before handing the EXE to a customer:

1. Build the app and original kit from the exact revised source with all required
   engineering gates passing. Do not patch an old customer's folder or re-label
   an older image as the new source revision.
2. Supply reviewed, licensed-for-distribution Windows prerequisite binaries and
   produce the offline EXE on a provider Windows machine. The tool does not
   automatically download or silently accept Docker's license on behalf of a user.
3. Verify the final executable's signature and provenance. Choose a delivery
   channel that accepts the actual EXE size; GitHub's 2 GiB release-asset limit
   still applies and this EXE may exceed it.
4. Test a clean supported Windows x64 PC with network disconnected: UAC, license,
   feature enablement, reboot, reopen, actual engine readiness, all services,
   initial Owner login, approved staff/setup workflows and normal later launches.
   WSL must be at least 2.1.5; the supplied binary must satisfy the selected Docker
   version's requirements. Missing Windows component source and disabled firmware
   virtualization require provider preparation, not customer command instructions.
5. Test interruption, corrupt binaries, wrong publishers, corrupt runtime images,
   concurrent setup launches, existing/partial data refusal and signed EXE reading.
   Source smoke tests are not substitutes for these clean-machine journeys.

Until this evidence exists, keep **TEST PACKAGE - NO REAL DATA** and production
**REJECT**. No customer-ready EXE is claimed merely because its source compiles.

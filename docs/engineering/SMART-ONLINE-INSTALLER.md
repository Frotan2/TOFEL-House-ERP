# TOEFL House ERP — Smart Online Installer (engineering candidate)

**Production: REJECT / NO-GO. No real student, payroll or financial data.**
This is a second **distribution route**; it does not change any ERP feature,
database authority, backup procedure, signed update channel or customer policy.
The existing fully offline Setup and its qualified release image remain intact.

## Customer experience

One small \`TOEFL-House-ERP-Online-Setup.exe\`. A signed Windows GUI displays
**Download & Install**, downloads one immutable, **already publisher-signed**
\`TOEFL-House-ERP-Setup.exe\` from the TOEFL House GitHub Releases page,
verifies the published size, exact SHA-256 and Authenticode signer, then opens
that existing offline setup. That setup already includes signed WSL and Docker
Desktop prerequisites, pinned database/cache/application images and a protected
first-install flow. The initial total download remains approximately 2 GB;
this approach reduces **initial EXE size**, not total bytes or installed disk.

The online GUI cannot install Windows virtualization silently or accept
Windows/Docker licence prompts for the customer. Restarts and UAC may be needed.

## Immutable download and security model

- The official URL is compiled into a signed EXE resource, not fetched from
  a mutable remote channel. It is restricted to a tagged asset at
  \`github.com/Frotan2/TOFEL-House-ERP/releases/download/<tag>/TOEFL-House-ERP-Setup.exe\`.
  No arbitrary source links, JSON policy, API key or URL parameter are allowed.
- The pinned published SHA-256, exact byte length and signer **certificate
  thumbprint** are also embedded. Redirects must end on HTTPS. The downloaded
  executable is validated by both SHA-256 and Windows WinVerifyTrust
  Authenticode plus the exact publisher certificate, before any launch.
  A changed, unsigned, expired/untrusted or wrong-publisher payload cannot
  be installed. The bootstrap itself must be publisher-signed and timestamped.
- Downloaded bytes are saved in a uniquely digest-named \`.part\` file under
  the user's local application data. Subsequent launches use HTTP Range only
  when the server proves the correct offset and total length; otherwise the
  response is restarted from byte zero. A finished verified cache is reused.
  Reparse points and overwrites of existing published paths are refused.
  Partial downloads are never executed. HTTPS is required in production.
- An existing \`%LOCALAPPDATA%\TOEFL House ERP\Customer\` directory causes
  refusal **before network/download**; the user is directed to the installed
  launcher. The offline setup retains its own site/volume/secret fail-closed
  checks. No Docker, data, credential, finance or Owner records are touched
  by the online downloader.
- Deliberate version pinning means an online bootstrap is **not an updater**:
  a future release gets a newly approved, signed bootstrap. The held
  signed-update feature cannot be bypassed with an online installer.

## Provider-only release assembly

Prerequisites: a **real, independently accepted** release commit; a valid
trusted code-signing certificate/private key and RFC3161/Authenticode-compatible
timestamp server; an **already signed and timestamped** offline
\`TOEFL-House-ERP-Setup.exe\` built from that same release; and permission to
publish a GitHub Release asset smaller than 2 GiB.

The provider performs these steps, **not the customer**:

1. Verify that the offline installer and every exact-head/physical Windows,
   Owner/recovery, protected-main and independent-release gate is approved.
2. Sign and timestamp the qualified offline Setup with the release publisher
   certificate. Verify the EXE bytes and certificate on the provider PC.
3. Upload that exact signed EXE to a reviewed immutable tag on the official
   GitHub Release as \`TOEFL-House-ERP-Setup.exe\`. Public tagged releases are
   versioned; GitHub per-asset size limits still apply. Do not replace assets
   silently after distributing a bootstrap.
4. On the provider Windows PC, run the protected builder:

   \`powershell.exe -NoProfile -File "tools/release/Build Online Installer.ps1" -SignedOfflineSetup "<provider signed offline EXE>" -ReleaseTag "<approved tag>" -OutputExe "<new provider output path>.exe" -SigningCertificateThumbprint "<approved signer thumbprint>" -TimestampServer "<approved code-signing timestamp server>"\`

   The builder refuses unsigned/untimestamped input, wrong-publisher payload,
   missing signing key, oversized release asset and existing output files.
   It compiles and signs the small bootstrap and writes a SHA-256 sidecar.
5. Independently verify the signed bootstrap and official published bytes.
   On a disposable clean Windows PC, exercise full online download, resume,
   offline-Setup launch, prerequisite UX, restart, actual ERP first boot,
   failed/tampered/unavailable source, and all required Owner/role/recovery gates.
6. Publish **only after** separate Owner authorization and release approval.
   No GitHub Actions TEST EXE or unsigned fixture qualifies as a production
   download target, and no customer should be sent a TEST bootstrap.

## Current automated tests and limitations

\`tests/foundation/test_online_installer.ps1\` compiles the **real C# source**
with the explicit \`TEST_BUILD\` conditional on a hosted Windows runner,
uses synthetic local HTTP bytes and checks valid full download, cached reuse,
partial download using HTTP Range, and wrong SHA rejection without ever
launching a file. The production provider builder cannot enable TEST_BUILD.
The current CI cannot exercise the actual trusted publisher identity because
no legitimate release signing certificate is provided; a real signed launch,
2-GB download and clean-machine experience still require independent
acceptance. Production stays REJECT.

**Release precedence:** \`docs/engineering/RELEASE-CANDIDATE.md\`, exact-head CI
and separate Owner acceptance always override this engineering design note.

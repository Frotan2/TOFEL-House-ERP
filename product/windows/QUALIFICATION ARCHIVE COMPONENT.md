# Isolated archive component

`Qualification Archive.ps1` is a dot-source library for a future isolated Windows qualification installer. It performs no Docker commands, installer launch, prerequisite update, site creation or credential operation. It is not a one-click installer or production acceptance result.

`Get-QualificationArchiveInspection` verifies an explicitly supplied archive SHA-256, image config digest and sole tag. Only the reviewed uncompressed USTAR Docker/OCI schema is accepted. Paths, entry types, header checksums, file padding, end blocks, duplicate names, JSON keys, metadata shape, entry counts and expansion bounds are checked before staging. Every content-addressed blob is hashed, including compatibility blobs not referenced by the current image manifest.

`New-QualifiedDockerArchive` accepts only the three standard product tags as input and a new `th-qual-*` tag as output. It requires a new destination outside the source archive directory, refuses linked paths and Windows aliases, holds the source file against writes, and derives a new archive with the absolute stock Windows `tar.exe`. Its named mutex prevents cooperating derivations from sharing a destination. Any failure preserves the new staging tree and refuses reuse on a subsequent call.

The component creates three rewritten files from exact UTF-8 bytes. They hold the Docker `manifest.json` tag, OCI `index.json` tag annotations, and legacy `repositories` binding. The derived archive must match the generated digest for each of those files before its final filename and receipt are published. Verification also preserves the original config bytes, all blobs, ordered layers (including repeated layers), `LayerSources`, and `oci-layout` bytes.

The wrapper must provide a private staging root controlled by the qualification owner. Before any import, it must verify the receipt against the authorized source and rehash the exact derived archive identified by that receipt. Keep the archive protected against writes and replacement from verification through import.

Run the tiny-fixture suite using Windows PowerShell 5.1:

```powershell
powershell.exe -NoProfile -NonInteractive -File "tests\foundation\test_qualification_archive.ps1"
```

The suite creates a new `.foundation/qa-*` evidence directory and retains all fixtures and failed cases. It uses stock Windows tar for positive app/database/cache schemas and checks refusal of malformed headers, unsafe paths/types, duplicate metadata, hidden tag bindings, changed blobs, bounds and occupied destinations. No existing archive, Docker image tag, container or volume is used.

Still required before installer delivery: independent review, real archive qualification, current-engine tiny-image import tests with tag sentinels, an isolated installation state machine, exact resource/nonce/secret guards, packaged EXE integration, actual first boot/restart/recovery and release acceptance. Hash verification is not a publisher signature; production stays `REJECT`.

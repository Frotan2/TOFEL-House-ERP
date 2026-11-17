# Factory Windows release authorization

The single-owner route is separate from internal acceptance. A Windows publisher
signature verifies downloaded software provenance. The developer release grant
is what permits a clean, verified factory installation to enter production.
An unsigned or test installer never enrolls a first Course Owner or activates
through this route. Existing sites, independent restore approval, accounting
permissions, and signed updates keep their existing controls.

Release engineering must provision an approved public key in
`product/customer-release-trust.json` with the sole
`customer-installation-release` purpose before building the qualified image. The
default repository trust store is deliberately empty. After independent review
and exact-image Windows acceptance, sign an exact UTF-8 JSON file with these
fields:

- `schema_version` is `1`.
- `document_type` is `toefl-house-erp-customer-release` and `product` is
  `toefl-house-erp`.
- `release_id` identifies the approved release. `source_revision` and
  `image_id` are the exact factory Git commit and Docker image ID.
- `windows_acceptance_sha256` is the digest of the independent Windows
  acceptance record for that image. `production_authorization` is
  `AUTHORIZED`.

The signature envelope has the same exact field layout as update signatures
but uses document type `toefl-house-erp-customer-release-signature`. Pass both
documents to the existing Windows builder using `-CustomerReleaseGrant` and
`-CustomerReleaseSignature`, along with the approved Authenticode publisher
certificate and timestamp service. Keep the exact approved image loaded in the
local provider Docker Desktop engine. The builder verifies the grant against
that image in a network-disabled container before signing the delivered
PowerShell scripts or executable.

Validate the resulting signed executable on Windows with its download marker
intact. The native wizard enrolls the named first Course Owner only after
verifying the grant. The Owner saves a passphrase-protected recovery kit from
the local browser. Setup validates the exported decryption subkey in a fresh
keyring and preserves the established key when routine settings are edited.
The first Owner-authorized backup must verify on a separate physical drive
before factory activation. The provider must verify real first-run, recovery
and secure staff access before distribution. The portable recovery kit must be
kept outside both the system and backup disks.

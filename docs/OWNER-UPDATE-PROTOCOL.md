# Explicit Owner update policy

This additive protocol leaves the existing two-person recovery validator and
all migrating-update rules unchanged. A separately enrolled, signed Owner policy
may authorize only its exact nonmigrating, reversible legacy transition. There
is no caller-controlled bypass flag. Missing or invalid policy refuses that
transition. All signed document types below use the `toefl-house-erp-` prefix.

The fixed policy files are `data/updates/owner-policy.json` and
`data/updates/owner-policy.json.sig`. Detached signature envelopes retain the
existing schema/algorithm/key_id/signature_b64 fields and exact raw-byte RSA
PKCS1v1.5/SHA256 verification. The policy envelope document type is
`toefl-house-erp-owner-update-policy-signature`; the approval envelope type is
`toefl-house-erp-owner-update-approval-signature`.

Trust entries retain `approver_identity` and `approver_role`; the additive
`approver_windows_sid` is required for this policy. The key needs explicit
`update-policy`, `owner-update-authorization`, and `update-manifest` purposes.
Factory installation keys remain purpose-restricted and cannot authorize this.
The same trust entry also binds `publisher_thumbprint`; its uppercase value must
equal the policy's publisher. The fixed decision file is
`data/updates/owner-policy-decision.json`, copied byte-for-byte from the actual
Owner approval record. Its digest must match `approval_record_sha256`, with
`status=EXPLICIT_OWNER_POLICY_CHANGE_APPROVED`, matching `owner_email` and
`windows_sid`, and `existing_recovery_key_must_be_preserved=true`.

Policy exact top-level fields:

```text
schema_version: 1
document_type: toefl-house-erp-owner-update-policy
product: TOEFL House ERP
site: toeflhouse.localhost
mode: single-owner-nonmigrating
policy_id: 32 lowercase hex characters
key_id: enrolled signer key identifier
owner_identity: actual verified Owner identity
owner_role: course-owner
owner_windows_sid: actual enrolled Windows SID
publisher_thumbprint: 40 uppercase hexadecimal characters
issued_utc, expires_utc: UTC timestamps
approval_record_sha256: actual explicit Owner policy decision document digest
installation: {storage_sha256, credentials_sha256, site_config_sha256}
transition: {
  source_version, source_revision, source_image_id, source_sequence,
  target_version, target_revision, target_image_config_digest,
  target_image_id, target_archive_sha256, target_sequence
}
```

The Owner approval is supplied through the existing `recovery_authorization`
and `recovery_signature` request paths. `recovery_signature_2` is absent. Its
exact fields are:

```text
schema_version: 1
document_type: toefl-house-erp-owner-update-approval
product, site
operation: site-update
scope: exact-legacy-nonmigrating-update
policy_id, policy_sha256
request_id: single-use 32 lowercase hex characters
key_id, owner_identity, owner_role: course-owner, owner_windows_sid
issued_utc, expires_utc: maximum 30-minute validity
manifest_sha256
backup_receipt_sha256
existing_recovery_key_access_verified: true
separate_key_custody_verified: actual boolean, never silently promoted
restore_rehearsal: {
  report: product-relative existing evidence file path,
  report_sha256, backup_set, verified_utc, source_revision,
  source_image_id, verified: true
}
```

The rehearsal may describe the honestly recorded earlier restored set; it does
not claim the new backup was restored. The report bytes must match its digest,
the rehearsal must precede approval and match the unchanged source image/revision,
and fresh backup receipt/artifact authentication remains mandatory. Pending
separate custody is retained as a warning, not replaced by a false attestation.
The policy validity is at most 31 days. Approval validity is at most 30 minutes
and must lie inside the policy's validity window. The prior rehearsal evidence
may be at most 168 hours old. A normalized evidence JSON has `status=PASS`,
`verified=true` and the exact `backup_set`, `verified_utc`, `source_revision`
and `source_image_id` declared in the approval. Additional provenance fields
should identify the original genuine evidence; normalization does not turn a
failed or unperformed restore into a successful one.

The signed update manifest optionally adds:

```text
legacy_bridge: {
  source_version, source_revision, source_image_id, source_sequence,
  target_sequence
}
image.runtime_id: signed actual OCI Engine ID, distinct from archive config_digest
host_service: {
  archive: toefl-house-erp-host.zip,
  sha256, size_bytes,
  files: [{path, old_sha256: hex or null, new_sha256, size_bytes}]
}
```

Only these host paths are allowed: `docker-compose.yml`,
`windows/Backup TOEFL House ERP.ps1`, `windows/Update TOEFL House ERP.ps1`,
`windows/Owner Host Servicing.ps1`, `windows/updater-strings.json`,
`updates/servicing/update_engine.py`, `updates/servicing/update_host.py`, and
`updates/servicing/update_entrypoint.sh`, `updates/servicing/bootstrap.json`,
and `updates/servicing/bootstrap.sig.json`. Null old_sha256 requires absence. The
host verifies every old/new file and archive hash and retains rollback bytes.
The manifest phase may bind the signed host plan before its ZIP is downloaded;
it still checks the old host files. Authorize, recheck and apply require the
actual ZIP, its exact signed file set, all hashes and the bounded expanded size.
The response exposes the normalized plan in `target.host_service` for the
launcher to retrieve this small asset before image authorization.
Source/target sequence values come only from the signed exact transition;
image labels and original factory identity are never rewritten.

The persisted transaction binds authorization mode, policy/approval/signature
hashes, restore report digest and host-service plan digest. Apply revalidates
them, then consumes the existing durable request/transaction markers before
mutation. New authenticated engine bytes must run; an unchanged engine inside
the installed/candidate image cannot interpret this new policy.

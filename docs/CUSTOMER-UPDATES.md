# Customer updates — controlled Windows release process

**Availability:** The update mechanism is implemented but its release channel is
disabled. Production authorization remains **REJECT / NO-GO**. It cannot be
used with real institute records until the exact installed release, independent
acceptance, verified backup, two-person recovery authorization and signed
release channel have all been approved.

This guide describes the **English-language** customer workflow and the
separate provider-only procedure. It is not permission to activate updates.

## Customer workflow

The Windows launcher offers two distinct actions:

| Action | Customer-visible behavior |
| --- | --- |
| **Check for Updates** | Checks trusted, signed provider metadata when the channel is enabled. Does not install or change the site. While disabled, explains that updates are unavailable. |
| **Install Update** | Requires confirmation, repeats every safety check and refuses an unsafe or unapproved update. |

A normal customer must never need Git, Python, PowerShell, Docker commands,
manual JSON editing, or database administration to update the application.
The version number and any safe refusal explanation appear in English.

## Safety checks before changing an installed application

An approved update must independently verify all of these conditions:

1. The provider's cryptographic release signature against a **separately
   installed** trusted key. A checksum alone is not proof of publisher identity.
2. The source revision, release sequence, version, pinned prebuilt image and
   supported upgrade path. The customer machine never builds source code.
3. The existing site configuration, credentials, named database volume and
   sufficient disk space; an incomplete or unexpected installation fails closed.
4. A verified, encrypted backup on the separate approved drive, with matching
   artifacts and backup receipt.
5. A recovery authorization signed by **two distinct authorized people**:
   Course Owner and General Manager (or designated recovery authority), using
   separate approved keys and the same single-use request identifier.
6. No unfinished or unreconciled previous update transaction.
7. The downloaded image's exact size, SHA-256 digest and signed identity,
   checked again immediately before application.
8. Complete, readable baseline record counts and relationships for existing
   students, payments, invoices, books, classes, attendance and payroll.
   Refuse before changing the installation if an expected baseline cannot be
   read; never assume absent verification means zero records.

The image is downloaded only after release metadata passes validation. An
approved installation decision expires after 30 minutes; stale, replayed or
reused permissions are refused. An update manifest cannot waive the backup
or recovery authorization requirements.

## If an update fails

- **Refused before installation:** No installation change was started. Follow
  the explanation shown in the launcher.
- **Import or apply failure:** Do not assume services or storage are healthy.
  The launcher must not silently restart or overwrite anything. Save the
  support status and contact trusted support.
- **Recovery decision required:** Do not reinstall, reset Docker, delete
  application data or restore over the live site. Keep the installation intact.
  The update journal blocks another attempt until an authorized recovery
  decision resolves the previous attempt.

**Never** delete a Docker volume, run `docker system prune`, reset Docker,
rebuild the image on the customer machine or proceed without signed release,
backup and recovery evidence.

## Provider-only release channel procedure

These steps belong on the release provider's controlled workstation, **not**
on a customer machine. The channel must remain disabled until all release
gates have been independently accepted.

1. Build and qualify the exact source revision and complete customer package.
   Sign the release using the provider-controlled offline signing key:

   ```bash
   python3 tools/release/create_update_bundle.py bundle \
     --release-dir <package>/product/release \
     --private-key <offline-key>.pem --key-id <key-id> \
     --out <channel>/stable --trust-store-out <secure>/trust-store.json \
     --target-schema-version frappe-v16-<release> --copy-archive
   ```

   The tool copies release state and authorization from the verified
   `release-manifest.json`; it cannot promote a **TEST PACKAGE - NO REAL
   DATA / REJECT** candidate to an approved production release. The shipped
   verifier must reject that candidate.

2. Publish `index.json`, `update.json`, `update.json.sig` and the exact
   image archive on the provider's allowlisted metadata host.
3. Provision `product/data/updates/trust-store.json` separately on the
   customer computer. **Never** trust an update-server-supplied trust anchor.
4. Configure `product/updates/channel.json` only after approving the
   actual provider host and release channel; then rebuild and independently
   qualify the distributable.
5. Before a migrating update, create one schema-2 recovery authorization
   naming the Course Owner and General Manager or designated authority with
   a single-use `request_id`. Each signs the identical document using their
   own offline key and produces a distinct signature file:

   ```bash
   python3 tools/release/create_update_bundle.py sign \
     --document recovery-authorization.json --private-key <owner-key>.pem \
     --key-id <owner-key-id> --document-type recovery \
     --out recovery-authorization.sig
   python3 tools/release/create_update_bundle.py sign \
     --document recovery-authorization.json --private-key <manager-key>.pem \
     --key-id <manager-key-id> --document-type recovery \
     --out recovery-authorization-2.sig
   ```

   The trust store must bind each signing key to the correct distinct
   identity and role. A missing signature, reused request identifier,
   interrupted update or single-person approval is a hard refusal.

**Release boundary:** This document is a specification for secure updates.
It does not prove that the current Windows installer, updater, recovery
ceremony or any release is production-qualified. Refer to
[Release and documentation authority](DOCUMENTATION.md) for the current
acceptance requirements.

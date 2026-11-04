# Isolated Oracle ARM64 staging target

**TEST / synthetic records only. Not approved for production.**

This stack uses its own Compose project, named database volume and
`product/oracle/data/` directory. It does not mount the Windows product data.
Only the Caddy reverse proxy publishes ports 80 and 443; the app, database,
Redis, workers, scheduler and Socket.IO have no host-published ports. The
Compose file fixes every service to Linux/ARM64 and pins third-party images by
digest. App containers must use the config ID of the attested image.

Before preparing an Oracle VM, verify in the OCI Console that the instance,
storage, home region, public address, object storage and all other selected
resources are Always Free eligible. Keep the tenancy out of any paid upgrade
and do not use free trial credits. Never start this stack with real institute
data. Do not use this staging path as a production backup solution: encrypted
off-host backup, retention, restore rehearsal, key custody and quota checks
are separate mandatory gates and are not implemented by this Compose target.

## Prepare and start a fresh synthetic staging site

On a new OCI Linux ARM64 VM, make a private `product/oracle/.env` based on
`.env.example`. Set `PUBLIC_ADDRESS` to the real public IPv4 address or an
approved DNS name. Download the `oracle-arm64-test-<commit>` artifact from the
successful Oracle workflow for the reviewed commit. On the VM, use
`bash import-image.sh /path/to/oracle-arm64-test.tar.zst <commit>` with
GitHub CLI, zstd and Docker installed. Set `ERP_APP_IMAGE` to the value it prints
after checking GitHub provenance, architecture and the source label. Keep the file readable by the VM administrator only
(mode `600`). Never place credentials in the `.env`; the first-run script
creates a separate random MariaDB root secret with mode `600`.

Run `bash prepare-stage.sh` from an otherwise empty cloud checkout. It refuses
to overwrite/reuse unmarked data or to regenerate credentials over an existing
database volume. It starts the stack only after validating the address and
image digest format. The script does not provision OCI resources; the Oracle
VM must already exist within the Owner-approved Always Free quota.

Caddy requests the ACME `shortlived` profile for the public address and
persists its certificate state in its own volumes. A successful config parse
is not proof of public issuance or renewal. Verify real HTTPS, automatic
renewal, alerting, and a deploy/reload failure rehearsal before calling the
staging edge verified.

## Stop and preserve staging

Use `docker compose -f docker-compose.yml --project-name toefl-house-cloud-staging stop`
to stop services without deleting data. Never run `down -v`, remove the named
volume, regenerate `data/secrets/db.env`, or restore over an existing site as
a troubleshooting step. Recovery belongs to the separately tested, encrypted
backup procedure.

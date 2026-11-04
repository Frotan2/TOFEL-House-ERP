# Oracle Cloud ARM64 readiness

**Status at 2026-11-04: ARM64 source work started; no Oracle staging environment exists; production is REJECT / NO-GO.**

This is the isolated cloud workstream requested by the Owner. It must not
reuse the Windows installation, its Docker volumes, credentials, backup keys,
or real records. Deploy synthetic acceptance data only until the release
decision and data-custody rules are separately satisfied.

## Audit baseline

- Source of truth before this workstream: `main` at
  `415d0145f09b546d474853bafb33c235593441db` (2026-11-04).
- The app build was Linux/amd64 only. `product/app.Dockerfile` downloaded the
  x64 Node.js binary unconditionally, and the offline exporter rejects any
  non-amd64 app image. The Windows installer remains explicitly amd64-only.
- The pinned MariaDB 11.8.9 and Redis 8.6.6 OCI indexes both contain Linux
  ARM64 manifests. This was checked against their exact matrix digests on
  2026-11-04; the OCI image index digests remain the source of truth.
- Python 3.14.7 uses the official Debian Bookworm multi-architecture base tag.
  A native ARM build must still verify the resolved manifest and execute all
  shipped Python/native dependencies; a tag name is not proof of runtime
  compatibility.
- The staging reverse proxy is pinned to the official Caddy 2.11.8 Alpine OCI
  index, which includes ARM64. Public ACME issuance and renewal require a real address.
- The current product web ingress already proxies HTTP and Socket.IO through
  one origin. The site identity and several Windows lifecycle helpers are
  fixed to `toeflhouse.localhost`; this must be kept behind the cloud reverse
  proxy and must not be treated as an internet hostname.
- TOEFL Preparation's approved duration is four months. The setup preset
  already enforces it; the cloud path must preserve the canonical Owner
  decision ledger and must not seed synthetic business records into a live
  site.

## Free-tier envelope to validate in the tenancy

OCI currently documents the Always Free Ampere A1 allowance as 1,500 OCPU
hours and 9,000 GB-hours per month (equivalent to 2 OCPUs and 12 GB RAM),
available only in the tenancy's home region. It also lists 200 GB total
combined boot/block storage, five volume backups, 20 GB combined Object
Storage after trial expiry, 50,000 Object Storage API requests/month, 10 TB
monthly outbound transfer, and shape-dependent A1 networking. Regional A1 capacity can be unavailable. The console's current
Always Free eligibility and quota view must be checked before any resource is
created; never switch account tiers or consume promotional credits.

Source: [OCI Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

The 20 GB Object Storage allowance may not accommodate the required encrypted
multi-version backups once real database and private-file sizes are measured.
The retention policy, usable size, restore time, key recovery, and free-quota
headroom must be tested together. Stop before a backup or resource could incur
a charge. The existing Windows backup scope remains unchanged.

OCI can reclaim an Always Free A1 instance if its CPU, network, and memory
utilization all remain below the documented thresholds for seven days. A
small institution's real usage and memory footprint must be measured; no
artificial traffic should be generated to evade reclamation.

## Safe access target

The requested target is an ordinary browser at a stable public HTTPS address,
with Cloudflare optional and Tailscale unnecessary for staff. Only HTTP for
ACME validation/redirect and HTTPS should be public. MariaDB, Redis, app
workers, scheduler, and Socket.IO must stay on a private container network;
SSH must be key-based and source-restricted.

If no domain is supplied, Let's Encrypt now offers short-lived IP certificates
valid for 160 hours. Certbot 5.4+ supports IP issuance with the `shortlived`
profile and webroot validation, but its server installation is not yet
automatic: an explicit deploy hook and renewal/failure monitoring are
required. Renewal, proxy reload, firewall validation, and browser trust must
be tested against staging before public issuance.

Sources: [Let's Encrypt IP and 6-day certificate GA](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability/),
[Certbot IP-certificate support and deploy-hook requirement](https://letsencrypt.org/2026/03/11/shorter-certs-certbot/).

## Current environment and blockers

- The home region, capacity and remaining quotas require an authenticated tenancy check.
- The owner-approved launch policy originally selected local server plus
  Tailscale and deferred off-host storage. The new 2026-11-04 Owner request
  explicitly selects an isolated Oracle direction and encrypted off-host
  backups for the cloud workstream; it does not authorize migrating real data
  or change the protected Windows backup destination.
- No ARM64 build has passed yet. The new build workflow provides the first
  native build gate; its result will not by itself prove the full business,
  backup/recovery, public-edge, or operational acceptance required below.
- The isolated staging Compose and Caddy configuration pass local syntax
  validation. It has not been booted against an ARM64 image. Its provisional
  memory caps have not been measured against the 12 GB OCI limit.
- No production image, credentials, domain, public endpoint, OCI resources, or
  cloud backups exist. Production authorization stays **REJECT / NO-GO**.

## Required gates before staging can be called verified

1. Native ARM64 build with the architecture-specific official Node.js hash;
   verify the app image, MariaDB, Redis, Python, Node, PDF libraries and every
   runtime binary report ARM64. Keep the Windows/amd64 workflow green.
2. Disposable ARM64 Frappe site: boot, login, users/roles, all required
   services, realtime, core workflows, PDF/printing, encrypted backup and
   isolated recovery. Repeat restart, interruption, disk-pressure and
   rollback checks on the actual ARM runtime.
3. Reproducible, digest-bound deployment files and restricted OCI network
   rules; test HTTPS acquisition and renewal/failure notification. Keep all
   internal ports private.
4. Measure actual peak CPU, memory, disk, backup size, concurrent response
   times, RPO/RTO and Object Storage retention against the exact home-region
   Always Free quota. Record regional capacity and account billing guardrails.
5. Independent security review, finance-ledger reconciliation, role
   acceptance, encrypted off-host recovery, Windows preservation evidence,
   and a separate explicit Owner production authorization.

Until those gates pass, status terms must remain precise: source-ready,
build-verified, staging-deployed, infrastructure-verified,
production-approved, production-deployed, and operationally accepted are
separate states.

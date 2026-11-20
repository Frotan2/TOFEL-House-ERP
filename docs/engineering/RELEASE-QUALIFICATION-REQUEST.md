# Exact-main release qualification request — 2026-11-11

**Status: ENGINEERING QUALIFICATION REQUEST — NOT PRODUCTION AUTHORIZATION.**

## Reason for this request

GitHub `main@1eb25e27a500a80adb0cabf1d88ad6e10036a381` contains the safely merged and archived cleanup work through PR #165. The Owned Suite and Windows Customer Package Smoke workflows passed at that SHA, but GitHub's path filters correctly did not schedule Native Lifecycle, Foundation Runtime, or Product Image for a maintenance-only merge. The HP ENVY qualification handover reported that its connected Work agent could not manually dispatch the missing workflows (HTTP 403). The previous fully qualified installer refers to an **older** code revision and must not be misrepresented as an exact-current-main installer.

## Authorized engineering-only action

Merging this request and its workflow-trigger contract into `main` creates a **new SHA**. The three long-running paths in `native-lifecycle.yml`, `foundation-runtime.yml`, and `product-image.yml` explicitly monitor this request. Owned Suite and Windows Customer Package Smoke already run on every `main` push. This triggers **five** fresh workflows on the new merge SHA without requiring Work to invoke a privileged workflow-dispatch endpoint.

The Product Image job must still demand its exact-SHA upstream gate receipts, construct its own TEST-only artifact, and fail closed if a prerequisite cannot be verified. A green result is only source/CI qualification, not independent signed Windows acceptance.

## Non-negotiable evidence and release limits

- Confirm the new `main` SHA, all five workflow run IDs, run conclusions, product-image embedded source SHA, and GitHub provenance. Never reuse receipt IDs from the predecessor revision.
- Keep the institute and HP ENVY preserved installations, MariaDB data, named Docker volumes, credentials and encrypted backups untouched. This request does **not** operate any Windows host.
- A TEST-only offline installer is not an institute-ready signed artifact. Publisher Authenticode signing, trusted timestamp, Docker/WSL redistribution clearance, independent clean Windows host testing, authorized tailnet/staff access, off-device recovery, and explicit Owner go-live authorization **remain release blockers**.
- `Production authorization: REJECT / NO-GO`. No database migration or live-user activation is approved.
- If the CI contract fails or product image cannot be produced, retain the failure and resolve its actual cause; do not downgrade or bypass any required gate.

Reference: [dated release-readiness checkpoint](RELEASE-READINESS-2026-11-11.md).

## Turnkey Windows candidate — 2026-11-16

Collect exact-revision receipts for the guarded Owner catalog and timetable setup, Windows package and public key enrollment in [PR #173](https://github.com/Frotan2/TOFEL-House-ERP/pull/173). The Windows smoke passed on `aab374c`, but its Owned suite found a stale first-run navigation assertion. This follow-up corrects that fixture and the institute's private HTTPS directions. The linked candidate must receive fresh receipts under the rule above; `aab374c` receipts do not establish a later build's identity.

Keep the previous graphical installation and isolated recovery evidence for `f8a851b`. No live host, database or backups are part of this request. The artifact remains a qualification build until the exact Windows installer passes separate clean-client acceptance and the required independent reviews. It neither authorizes a data migration nor supplies the institute's two installation-bound signatures.

All five workflows passed on `baebb2d` and assembled its checksum-bearing Windows qualification installer. The subsequent graphical proxy preparation and certificate export change requires its own five receipts. The packaging job checks the staging feature using the same pinned Caddy archive bundled into that executable.

The backup-only Owner setup passed its disposable-site lifecycle test on `e5b5d14`. Qualify the complete revision again after wiring the new record into the standard permission, validation and audit registries. The new settings leave unrelated business policies unset and keep backup enablement and activation under their existing controls.

## Existing HP ENVY corrected-release request — 2026-11-20

The Owner authorized a targeted corrected release in the existing source checkout,
without reinstalling over the preserved institute site. This candidate fixes the
native wizard's transient first-Owner role exclusion, makes one-off backup
producers run as the same unprivileged identity as their consumers, requests wake
for the AC-protected Windows backup task, and requires an auditable reason for
new backdated bills while preserving completed-request replay and native finance
authorization. Placement chargeability and normal installment defaults are
unchanged. Existing Windows acceptance and backups remain preserved evidence for
their original image and scope.

The first combined follow-up revision's hosted Owned Suite found a stale guided
tuition signature expectation. The contract now includes the optional reason
and also checks the installment endpoint. Qualify the complete revision containing
this request on all five workflows; earlier successful receipts do not qualify
this revision. This is an engineering build request, not a production GO, an
authorization to replace the live installation, or a substitute for recovery-key
custody, verified staff identities/scopes, and permitted staff-device HTTPS
acceptance.

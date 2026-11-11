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

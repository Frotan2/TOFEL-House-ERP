# Security remediation follow-up — 2026-10-09

**Authorization: REJECT. PR #13 must not be merged or represented as release-ready.**
This record supersedes the *open HRMS / WeasyPrint wrapper / OAuth* descriptions
in the preceding delta README insofar as implementation is concerned; it does
not close any finding without a successful installed-image and audit run.

## Implemented on the PR branch (qualification pending)

* HRMS: retain the audited upstream commit and frozen lock, then replace **all**
  installed `prosemirror-view` copies in the frontend and roster (including
  nested copies) with 1.42.3 and `prosemirror-model` with 1.25.8, using the npm
  publisher tarballs with exact SHA-512 integrity. No Text Editor or HRMS route
  is disabled. The image, Foundation and Native installers apply the change
  before asset build; the web/bootstrap path verifies installed versions before
  serving, and the Foundation runner verifies again after build. A package
  manifest/version check alone is not a built-bundle exploit regression test;
  the built HRMS asset and editor UI still require hosted confirmation.
* Office 365: override only Frappe's Office 365 whitelisted callback. Validate
  the Microsoft-signed ID token with a fixed JWKS location, RS256 only, audience
  equal to the configured client ID, required timestamp claims and tenant-bound
  Microsoft v1 issuer before calling Frappe's existing state/login routine.
  Fail closed on malformed tokens, network errors or key errors; never log token
  or error content. Frappe's shipped `/common/oauth2/token` uses v1. Other
  providers retain the native user-info path.
* WeasyPrint: the owned helper wrappers now match the pinned vendor signatures.
  A SHA-256-bound installation patch inserts an authorization check at the
  **single** pinned `PrintFormatGenerator` constructor, reached by the whitelisted
  helpers, `printview`, Print Format methods and `attach_print`, including jobs.
  It requires target document print permission (including an independent
  role/record check not bypassed by `doc.flags.ignore_permissions`), a beta
  format and matching DocType before rendering. Scheduled jobs or guest/key
  printing that lack print permission may now fail; compatibility must be
  exercised on a synthetic site before calling this functionality preserved.
  A source mismatch fails the build. The existing
  final-stage `gs` absence check remains a separate RCE mitigation. This
  deliberately refuses unsafe rendering rather than disabling printing.
* Audit: Foundation supplies root, education/frontend, HRMS frontend/roster
  and ERPNext banking installed trees to the **same** npm triage. Missing/empty
  nested trees fail closed; untriaged/new findings fail the existing gate. The
  audit still does not scan operating-system/container CVEs or every library's
  exploit path; do not call it a full release security approval.

## Unfinished release gates

1. Observe hosted Foundation, Native, and Product image on the final head,
   including built HRMS editor behavior and printed PDF/preview behavior on a
   synthetic site. The existing static/in-memory regression tests are not an
   end-to-end proof of these paths.
2. Independently disposition/remediate **every** additional advisory in the
   newly included HRMS frontend/roster and ERPNext banking trees. Do not
   relabel matches BUILD_ONLY or NOT_REACHABLE without pinned callsite or build
   evidence. Expect the Foundation gate to fail until this is done.
3. Real Windows installation, encrypted backup, restore (DB plus uploaded
   public/private files), restart and repair on a disposable Windows machine
   with Docker Desktop, including Course Owner login and policy/account
   persistence. Ubuntu Actions, line-ending emulation and mocks do **not**
   meet this gate. No Windows host is available in this sandbox. Do not run
   destructive acceptance against a real site or the operator's backup drive.
4. Required review and other release criteria remain independent. Keep
   `docs/owner-decisions.json:production_state` at `REJECT`.

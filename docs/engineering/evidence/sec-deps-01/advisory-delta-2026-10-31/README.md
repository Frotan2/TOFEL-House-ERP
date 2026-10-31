# Security delta — 31 October 2026

Production remains REJECT. Historical registers and accepted-risk decisions are unchanged.
Foundation run [41151189301](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/41151189301)
failed closed for 11 newly indexed findings. This change never suppresses an unknown advisory.

## Actual fixes

- **pypdf 6.21.4**, replacing 6.21.2, carries the seven newly reported parser,
  page-label and resource fixes. [Upstream release](https://github.com/py-pdf/pypdf/releases/tag/6.21.4).
- **OAuthlib 4.0.0**, replacing 3.3.1, fixes authenticated-client identity confusion.
  Frappe really permits the password grant, so declaring the new finding unreachable
  would be incorrect. [Upstream advisory](https://github.com/oauthlib/oauthlib/security/advisories/GHSA-7984-qgvg-3j9c).
- **follow-redirects 1.16.2**, replacing 1.16.1 in the frozen banking lock,
  fixes cross-realm sensitiveHeaders handling. The official npm tarball SHA-1 and
  SHA-512 integrity were independently verified before updating the lock digest.
  [Upstream advisory](https://github.com/advisories/GHSA-mrwp-f3q8-3g9p).

All three Python installation paths install the same exact security releases,
refresh Frappe metadata and run pip check. The original Frappe commit and original
pyproject hash remain mandatory; source drift still refuses the overlay.

A disposable container on this Windows PC, without any Owner site mounts,
installed the six reviewed Python security dependencies against the actual pinned
Frappe checkout. Metadata pip check passed, exact versions verified, and a real
PDF write/read passed. The new OAuth authenticated-client regression **fails on
3.3.1** and **passes on 4.0.0**: a foreign client ID receives no token or persistence,
while the matching-client control succeeds. The existing device-grant refusal also
passes. These are dependency/validator checks, not final customer acceptance.
The same checks now run in hosted Native acceptance. A real frozen Yarn install
against the pinned ERPNext banking checkout also passed and installed
follow-redirects 1.16.2. No Owner sites were mounted in either qualification.

## Scoped build-only findings

[Glob cancellation](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4) and
[minimatch amplification](https://github.com/advisories/GHSA-g3hv-75wg-m249)
remain present in build tools. They are **not fixed** or removed. Their triggers
require a glob traversal/pattern preprocessing invocation. The server ingress uses
Node builtins; the pinned realtime source and actual transitive runtime graph of
28 packages contain neither library. A new Native check resolves the installed
production dependency graph and refuses either library entering it. Asset builders
consume trusted pinned source/patterns; there is no staff/student pattern endpoint.

Only these two advisory IDs and their verified aliases receive BUILD_ONLY
records. Their patched versions require different major build-tool APIs; changing
all pinned asset tooling is unnecessary for the demonstrated runtime boundary.
New consumers or changed build-input trust require reassessment. This disposition
does not authorize deployment or close unrelated residual browser risks.

## Remaining qualification

The complete Owned, Native, Foundation, Windows and Product workflows must rerun
on the resulting same commit. Earlier green gates and disposable-container checks
cannot certify the new final image, installer, five-role Windows journeys, update,
rollback or Owner acceptance. No Owner runtime or customer data was modified.

# Advisory delta 2026-10-22

Foundation runtime **39597802134** surfaced new npm advisory records after the previous triage snapshot.

This delta closes eight **launch-editor / Vite development-path** records as `DEV_ONLY`.
It does **not** waive Pillow or markdown-it:

- Pillow, GitPython, PyJWT and pypdf are upgraded by the reviewed, hash-bound `secure_frappe_python.py` overlay.
- HRMS frontend and roster are pinned to markdown-it 14.3.3, the patched release.
- launch-editor/Vite remain pinned upstream build/development dependencies, but TOEFL House does not start Vite dev/preview or editor-launch middleware in production.

## Evidence

`production-bundle-evidence.json` now records the production graph from run 39829102419; the downloaded workflow artifact independently maps npm IDs 1242724 and 1242730 to GHSA-9jrq-w75r-8gcw and GHSA-rq7h-c2jc-7f22.
The graph is explicitly not a vulnerability waiver; it is one supporting fact. The decisive boundary is that the shipped appliance serves the application from Linux containers and does not run the vulnerable editor-launch development path.

The launch-editor advisories have the same runtime boundary as the older launch-editor/Vite findings already classified DEV_ONLY in the SEC-DEPS-01 register. GHSA-698v and GHSA-587h name Windows-specific preconditions; GHSA-r825 requires an editor-launch invocation. The two later Vite records are also development-server-only: GHSA-9jrq requires Vite custom/middleware HTML transformation, while GHSA-rq7h requires a network-exposed Vite dev server. None of those processes run in the shipped appliance.

If a production Vite development server, preview/editor middleware, or Windows Node application process is introduced, these records must be re-triaged.

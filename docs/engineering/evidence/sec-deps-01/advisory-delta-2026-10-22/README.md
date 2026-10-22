# Advisory delta 2026-10-22

Foundation runtime **39597802134** surfaced new npm advisory records after the previous triage snapshot.

This delta closes only the six **launch-editor / Vite editor-launch** records as `DEV_ONLY`.
It does **not** waive Pillow or markdown-it:

- Pillow is upgraded to 13.0.0 by the reviewed, hash-bound `secure_pillow.py` overlay.
- HRMS frontend and roster are pinned to markdown-it 14.3.3, the patched release.
- launch-editor/Vite remain pinned upstream build/development dependencies, but TOEFL House does not start Vite dev/preview or editor-launch middleware in production.

## Evidence

`production-bundle-evidence.json` transcribes the production graph from run 39597802134.
The graph is explicitly not a vulnerability waiver; it is one supporting fact. The decisive boundary is that the shipped appliance serves the application from Linux containers and does not run the vulnerable editor-launch development path.

The new launch-editor advisories have the same runtime boundary as the older launch-editor/Vite findings already classified DEV_ONLY in the SEC-DEPS-01 register. GHSA-698v and GHSA-587h also name Windows-specific preconditions; GHSA-r825 requires an editor-launch invocation that the production runtime never performs.

If a production Vite development server, preview/editor middleware, or Windows Node application process is introduced, these records must be re-triaged.

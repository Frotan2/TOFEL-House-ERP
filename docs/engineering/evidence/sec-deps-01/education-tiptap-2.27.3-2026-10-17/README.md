# GHSA-VHRC-HGRQ-X75R: Education frontend TipTap upgrade (2026-10-17)

Owner decision (2026-10-17): coordinated TipTap upgrade, not an accepted exception.

## What changed

- `tools/foundation/education-locks/`: reviewed overlay for the Education frontend. Every `@tiptap/*` package is pinned to **2.27.3** through `resolutions`, with a regenerated `yarn.lock` (38 `@tiptap/*` names, all 2.27.3, `registry.npmjs.org` URLs only). `manifest.json` records the upstream SHA-256 of `frappe/education@93bc7075` `frontend/package.json` and `frontend/yarn.lock`, and the overlay SHA-256.
- `tools/foundation/secure_education.py`: applies the overlay to the disposable Education checkout. It validates every overlay source before touching the target, refuses drifted or missing targets, installs with `yarn install --frozen-lockfile`, and verifies that every installed `@tiptap/extension-link` is at least 2.10.4.
- `tools/foundation/runtime_install.py`: applies the overlay after the upstream source-hash check and before `asset-build`, verifies it again after `asset-build`, and adds the regression module to the hosted security unittest run.
- `tests/security/test_education_locks_2026_10_17.py`: 47 combined tests with the existing lock and remediation suites, all OK. Covers the pinned upstream hashes, the TipTap pins, npmjs-only URLs, the overlay differing from upstream only by `resolutions`, drift and tamper refusal before any write, the frozen-install apply path, fail-closed installed-version checks, and the install-path ordering.

## Why the upgrade is coordinated

`frappe-ui` 0.1.31, which the Education frontend uses, pins `@tiptap/*` at `^2.0.3` and `^2.2.3`. The patched `@tiptap/extension-link` 2.10.4 requires `@tiptap/core` and `@tiptap/pm` `^2.7.0`. Changing one package alone is not possible, so the whole set moves together.

## Verification run here

| Check | Result |
|---|---|
| Yarn 1.22.22 frozen install of the overlay on the upstream tree | OK (`secure_education.py` apply, then `--verify`) |
| Education Vite build (`vite build --base=/assets/education/frontend/`) on the overlay tree | exit 0, no missing-export errors |
| Post-build `secure_education.py --verify` | `frontend/node_modules/@tiptap/extension-link` = 2.27.3 |
| `repro_frontend.py` against the overlay lock (`repro-overlay-lock.txt`) | 65 advisory entries, 65 closed, 0 open, 0 untriaged. Before the upgrade the same script reported 66 entries, 65 closed, 1 open (GHSA-VHRC). |
| Behavioural differential (`link_command_probe.mjs`, jsdom, TipTap core and starter-kit at each version) | see below |

### Behavioural differential

The advisory's vulnerable path is "setting or toggling links" with a `javascript:` URL. The probe calls `setLink` and `toggleLink` on a text selection, with a control that uses `https://`:

| Case | 2.2.3 (vulnerable) | 2.27.3 (patched) |
|---|---|---|
| `setLink({href:"javascript:alert(1)"})` | command returns true; link mark stored with `javascript:alert(1)` | command returns false; no link mark |
| `toggleLink({href:"javascript:alert(1)"})` | command returns true; link mark stored with `javascript:alert(1)` | command returns false; no link mark |
| `setLink({href:"https://example.com/x"})` (control) | link mark kept | link mark kept, `rel`/`target` as before |

Raw outputs: `probe-2.2.3.json` and `probe-2.27.3.json`.

A first version of the probe that only used `setContent` with a hostile `<a href>` gave identical output on both versions. That path was not the advisory's vulnerable path, so it was not used as evidence.

## Not verified here (remaining)

- The Education runtime in a bench (MariaDB, Redis, Frappe). The hosted Foundation run is the first real check of `secure_education.py` inside the install order and of the hosted frontend audit on the patched tree.
- The Education editor in a real browser session. The probe is a jsdom check of the TipTap command path, not a UI test. Compile-level import checks passed through the Vite build.
- The post-upgrade behaviour of other Education editor features beyond links (tables, mentions, images). Only the link path was run.

## Register record

The `GHSA-vhrc-hgrq-x75r` record in the advisory register is **left unchanged** (BLOCKED). The triage gate closes an entry only when the advisory is absent or the disposition is closed, so the record is not edited here. The owner should decide whether to retire the BLOCKED record after the hosted Foundation run on the final SHA confirms that the advisory no longer appears.

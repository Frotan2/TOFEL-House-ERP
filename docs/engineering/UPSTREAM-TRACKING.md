# TOEFL House ERP — Upstream Tracking Evidence (R5)

Date: 2026-09-16 · Branch: `arena/01a0a9f7-tofel-house-erp`
Scope: evidence that upstream/external risk items are precisely
tracked, with the product-side boundary verified here and the upstream
remainder stated exactly. **Production remains REJECT.**

## 1. Realtime non-exposure (SEC-RT-TASK-01, product side)

**Grep evidence (2026-09-16, this branch):**

```
$ grep -rn "publish_realtime" apps/toefl_house/ | wc -l
0
$ grep -rn "publish_realtime\|realtime_subscribe\|frappe.realtime\|socketio" \
    apps/ --include="*.py" --include="*.js" --include="*.json" --include="*.html"
(only match: none — zero emit sites in owned code)
```

- Product code (`apps/toefl_house`) contains **zero** realtime emit
  sites — no task/progress/business-payload events are ever enqueued
  by this product.
- The only realtime-related owned file is
  `apps/foundation_security/foundation_security/realtime.py`: a
  **subscription-side** whitelist authorizer (`@frappe.whitelist()
  authorize(kind, resource, name)`) that emits nothing and is
  deny-by-default — `user` rooms match the session user, `document`
  rooms require fresh `has_permission(..., ptype="read")`, `task`
  rooms require site+user match on the RQ job, and **site/website/
  doctype/broad rooms return False unconditionally** ("Do not infer
  one from a role or ID").
- Conclusion: the upstream frappe realtime task-room behavior
  (SEC-RT-TASK-01) has **no product-side exposure path**; the upstream
  fix remains tracked out-of-repo. Patching upstream in-repo would
  create a fork and is prohibited.

## 2. Dependency advisory triage (SEC-DEPS-01)

- **Owned Python surface:** `apps/toefl_house/pyproject.toml` declares
  **no runtime dependencies** (build-system only, `setuptools==80.9.0`).
  No `package.json` exists under `apps/` — the product ships no
  frontend dependency of its own. There is nothing in-repo to patch.
- **Dependabot:** alerts are **disabled** for this repository
  (`GET /repos/Frotan2/TOFEL-House-ERP/dependabot/alerts` → HTTP 403
  "Dependabot alerts are disabled", observed 2026-09-16). Recorded as
  fact, not as a pass.
- **Upstream bundle (the actual SEC-DEPS-01 substance):** at pinned
  education `v16.1.0` (`93bc7075`), the recorded npm advisory lookup on
  255 resolved package names returned **57 advisory entries across 21
  packages** (foundation-version-matrix.json `risk` field); runtime
  exploitability **not tested**; resolved frontend versions recorded
  (vue 3.4.19, vite 2.9.17, frappe-ui 0.1.31, pinia 2.1.7, vue-router
  4.3.0, tailwindcss 3.4.1). Remediation requires a coherent upstream
  toolchain migration — upstream scope; not patchable in-repo without
  inventing a fork. Tracked here with the exact pin so the triage can
  be re-run against any future upstream release.
- **Dated Education re-scan (2026-09-16, this branch):** the pinned lockfile
  (`frappe/education@93bc7075` `frontend/yarn.lock`, fetched via GitHub
  contents API) parses to **279 unique resolved packages**; all six
  recorded top-level pins match it exactly. Full scan via the GitHub
  global advisory API (`GET /advisories?affects=name@version&
  ecosystem=npm`, 279 queries, 0 failures): **57 advisory entries
  across 21 packages** — exactly reproducing the historical record.
  Severity split: **27 high / 26 medium / 4 low / 0 critical**. Top
  carriers: `vite@2.9.17` (15), `brace-expansion@2.0.1` (5),
  `nanoid@3.3.7` (4), `postcss@8.4.35` (4), `minimatch@9.0.3` (3),
  `showdown@2.1.0` (3), `ws@8.11.0` (3). Most carriers sit in the
  build/dev toolchain; runtime exploitability remains **not tested**.
  Full machine-readable result:
  `docs/engineering/evidence/phase-2/education-frontend-advisory-rescan-2026-09-16.json`.
- **Current resolved-stack audit (2026-09-16, this branch):** hosted Foundation
  run `35084695840` at `955e4cd5eedc34b90f4fbfce047339e18558f1f2` ran the
  collector after the actual Bench asset build. It used the Bench interpreter's
  installed distributions (161 package names, queried against OSV/PyPI) and
  supplied installed Frappe/ERPNext/Education/Payments/HRMS Node roots plus
  Education frontend (572 package names, queried against npm bulk advisories).
  It recorded **14 PyPI/OSV finding records across four packages** and **97 npm
  advisory entries across 36 packages** (2 critical / 49 high / 39 moderate /
  7 low), so its diagnostic check failed as intended. Exact advisory IDs,
  queried versions, provider ranges, and the validated report provenance are
  retained in
  [`evidence/phase-2/resolved-stack-advisory-2026-09-16.json`](evidence/phase-2/resolved-stack-advisory-2026-09-16.json).
  The entire runtime report is `Foundation runtime evidence` check
  `104762158723`, SHA-256
  `f004c4893e80fa6e4477c816bc67019280e54d06b9121fc0f06642a6b1f651fc`;
  the detailed `stack-dependency-audit.json` was retained as restricted
  workflow evidence. The checker records MariaDB and Redis digest references
  only as inventory; it is not an OS-package or container-image CVE scanner,
  full SBOM, exploit/reachability assessment, remediation, or production
  approval. These findings make `SEC-DEPS-01` a whole-resolved-stack REJECT
  gate, not merely an Education frontend observation.

### Current official-remediation candidate decision

**Rejected before build — no credible official input exists.** The retained
assessment ([`dependency-remediation-candidate-assessment-2026-09-16.json`](evidence/phase-2/dependency-remediation-candidate-assessment-2026-09-16.json))
compares every currently newer official v16 input that could change this
resolved tree. It is a verified *rejection*, not a candidate pass:

- Frappe `v16.34.0` and ERPNext `v16.35.0` are newer official releases, but
  their reviewed `pyproject.toml`, `package.json`, and `yarn.lock` SHA-256
  values are identical to the current pins. Frappe continues to require
  `pdfkit~=1.0.0`, `pypdf==6.15.0`, and `WeasyPrint==68.0`.
- Education has no later v16 release. Its official `version-16` branch head is
  ten commits ahead, but the reviewed root/frontend manifests and frozen locks
  are byte-identical to the release; a moving branch must not replace a
  released input merely to create candidate activity.
- The recorded `pdfkit` advisory has no provider-listed patched version;
  current Frappe retains it. Frappe retains `pypdf==6.15.0` where the listed
  fixes start at 6.16.0/6.16.1, and `WeasyPrint==68.0` where listed affected
  ranges include `<70.0` and `<=68.1`.
- Bench `v5.31.0` constrains `setuptools` to `<82.0.0`; the provider-listed
  fixed version for the recorded finding is 83.0.0. An override would violate
  the reviewed upstream constraint. The unchanged Node locks leave all 97
  current npm entries in place.

Consequently, no disposable Bench was built and no full-stack/security/native
lifecycle/recovery/realtime/upgrade/browser result is claimed for a candidate.
A forced lock or resolver override would be an unsupported fork, fail the
clean-audit requirement, and constitute evidence theater. The smallest viable
input is an officially released compatible bundle that changes those direct
Python and frozen Node inputs; only then should an isolated immutable matrix be
built and subjected to every unchanged required gate.

## 3. Upgrade-path note

Pinned bundle (foundation-version-matrix.json, reviewed 2026-09-13,
source SHAs + file hashes recorded there): frappe `v16.33.1`
(`988e54f3c4c2`), erpnext `v16.34.2` (`4048fb70e14d`), education
`v16.1.0` (`93bc7075`), hrms `v16.18.1` (`a4768b44`), bench `v5.31.0`,
python 3.14.7, node 24.21.0, mariadb 11.8.9, redis 8.6.6.

**Newer-release observation, not a selected candidate (2026-09-16):** GitHub
release metadata lists Frappe `v16.34.0` (`c1f1e8ec3708750d7254f7f99d869ffb9886f19f`;
published 2026-09-15) and ERPNext `v16.35.0`
(`12cd563fb9a79731f75ae2a45b1446a0a2dd9e74`; published 2026-09-15).
Education and HRMS have no newer non-prerelease v16 release than their current
pins. The dependency-bearing source inputs checked for those new Frappe/ERPNext
tags (`pyproject.toml`, `package.json`, and `yarn.lock`) have the same SHA-256
values already pinned in the current matrix. They therefore are not a credible
clean-audit remediation candidate for the observed dependency findings by
inspection alone. Neither release is adopted: no five-app compatibility,
dependency, migration, native lifecycle, or production qualification has been
performed on that combination.

**Upgrade procedure (when authorized):**
1. Bump one app at a time to the newest non-prerelease tag in the same
   major line (`bench update --app <app>`), run migrations.
2. Gate: the full hosted suite (currently **542 checks**, run
   35073376790 @ `3587700`) must pass green before the bump is
   accepted — this suite directly exercises pinned framework behavior
   (permission model, workspace visibility, File/print paths), so it
   is the regression gate for framework upgrades by construction.
3. Re-run the advisory scan (section 2) against the new pin and update
   this file.

**Known upgrade hazards (pinned-evidence based):**
- Education version-string mismatch: tag says `16.1.0`, source
  `__version__` says `16.0.1` — **the pinned SHA is authoritative**.
- Education `version-16` branch head `22e0910d` is newer than the
  pinned `v16.1.0` release; adopting it requires separate
  qualification (not a drop-in).
- Education `after_install` creates Custom DocPerms on Sales Invoice
  that **void all standard SI permission rows site-wide** (proven via
  run 35048606232 diagnostics; mechanism in pinned
  `frappe.permissions.get_valid_perms`). Any education upgrade must
  re-verify this behavior before surfaces relying on native SI reads
  ship.
- No v17/develop jump without full re-qualification; MariaDB/Redis
  stay aligned to the frappe_docker recipe line (11.8 / 8.6), not the
  newest observed majors.

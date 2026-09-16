# TOEFL House ERP — Upstream Tracking Evidence (R5)

Date: 2026-09-16 · Branch: `arena/01a0a496-tofel-house-erp`
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
- **Dated re-scan (2026-09-16, this branch):** the pinned lockfile
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

## 3. Upgrade-path note

Pinned bundle (foundation-version-matrix.json, reviewed 2026-09-13,
source SHAs + file hashes recorded there): frappe `v16.33.1`
(`988e54f3c4c2`), erpnext `v16.34.2` (`4048fb70e14d`), education
`v16.1.0` (`93bc7075`), hrms `v16.18.1` (`a4768b44`), bench `v5.31.0`,
python 3.14.7, node 24.21.0, mariadb 11.8.9, redis 8.6.6.

**Upgrade procedure (when authorized):**
1. Bump one app at a time to the newest non-prerelease tag in the same
   major line (`bench update --app <app>`), run migrations.
2. Gate: the full hosted suite (currently **533 checks**, run
   35053305607 @ `46e5040`) must pass green before the bump is
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

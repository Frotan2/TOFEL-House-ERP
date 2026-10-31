# SEC-DEPS-01 deepmerge advisory delta — 2026-10-28

**Disposition: NOT_REACHABLE for the inspected pinned application dependency paths only.**
This is an engineering reachability assessment, not a claim that deepmerge is patched,
a blanket exemption for every consumer, Owner production authorization or clearance of
the unrelated Windows/financial/recovery release gates.

## Advisory and failure evidence

- GitHub-reviewed [GHSA-gcqx-w48m-w2h4](https://github.com/advisories/GHSA-gcqx-w48m-w2h4) /
  CVE-2026-93753: prototype poisoning in deepmerge `mergeObject()` for versions
  4.2.0 through 4.3.1. Severity: low in the reviewed npm advisory (2026-10-27
  update); no patched release listed at review time.
- GitHub Foundation runtime
  [40621526161](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40621526161)
  on `4f52eaa538a5f74e6789f99057a92ba8a420bdb9` correctly failed
  closed: `STACK-ADVISORY-UNTRIAGED npm:deepmerge 1243505`.
- The Product image run 40621526149 then failed its **release-check dependency**
  (`Require release checks on the same source revision`), not an independent
  deepmerge runtime exploit demonstration.
- The advisory ID, CVE alias and npm numeric ID are indexed only for the
  **deepmerge** package. Unknown advisories and other packages still fail closed.
  The immutable 2026-09-23 remediation register is not changed.

## Pinned dependency reachability

The assessment applies to these immutable upstream commits:

- Education `93bc7075753369457919720690f80c6d2207b5f2`:
  `frontend/yarn.lock` resolves `deepmerge@4.3.1` via
  `@tiptap/pm@2.2.3 -> prosemirror-trailing-node@2.0.7 ->
  @remirror/core-helpers@3.0.0`. In the reviewed trailing-node
  implementation, only `includes` and `uniqueArray` are imported
  from core-helpers; its `deepMerge` export is not imported.
- HRMS `a4768b441cff346def505e27f2a2229ee1e05b9b`:
  `frontend/yarn.lock` resolves `deepmerge@4.3.1` via
  `prosemirror-trailing-node@2.0.4 ->
  @remirror/core-helpers@2.0.3`, and separately via
  `workbox-build@7.3.0 -> @rollup/plugin-node-resolve@15.3.1`.
  The latter invokes `deepMerge({}, defaults)` only in the build process,
  using internally constructed source data, not attacker-supplied keys.
- The independent reviewer reported a production Vite output of about 71 KB
  without deepmerge in the emitted bundle. This build-output observation was
  **reported, not independently reproduced in this commit**; the definitive
  hosted artifact is still the next exact-head CI.

Dependency presence alone is not a vulnerability demonstration. The advisory
requires malicious source-object keys to reach vulnerable `mergeObject()`.
Neither a consumer importing only unrelated helpers nor the inspected internal
build-time defaults call establishes that path. No reviewed TOEFL House
browser/server input path using this vulnerable merge was identified.

## Scope, limitations, re-review triggers

- **This is not a patched package.** New vulnerability information, changed
  upstream lockfiles, new code importing `deepMerge`, arbitrary object
  merging in build tools, new SPA entrypoints or exposure of untrusted config
  must trigger a new reachability review; withdraw this delta when premises
  fail.
- The reviewer worked locally and did not push their draft. This separate
  committed delta re-records the supplied reasoning and independently
  checks the pinned yarn.lock edges. It does not claim to possess or reproduce
  the reviewer's uncommitted source files.
- No runtime bypass, weakened audit filter, dependency override or removal of
  existing triage failures is introduced. The official Foundation and Product
  image workflows must be rerun against the **exact combined head**.
- Other release gates, including independent two-person recovery controls and
  real installed Windows acceptance, remain **HOLD**.

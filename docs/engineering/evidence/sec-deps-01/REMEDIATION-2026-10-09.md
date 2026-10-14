# Security remediation follow-up — 2026-10-09

**Authorization: REJECT. PR #13 must not be merged or represented as release-ready.**
This record supersedes the *open HRMS / WeasyPrint wrapper / OAuth* descriptions
in the preceding delta README insofar as implementation is concerned; it does
not close any finding without a successful installed-image and audit run.

## Implemented on the PR branch (qualification pending)

* HRMS: retain the audited upstream commit and frozen lock, then replace **all**
  installed `prosemirror-view` copies in the frontend and roster (including
  nested copies) with 1.42.3 and `prosemirror-model` with 1.25.8, using the npm
  publisher tarballs with exact SHA-512 integrity. The same fail-closed helper
  now replaces both HRMS `socket.io-parser` copies with 4.2.7
  (GHSA-cqmj-92xf-r6r9, GHSA-677m-j7p3-52f9, GHSA-2m8v-j782-fhvr),
  plus nested, independently integrity-checked
  `debug` 4.4.1 and `ms` 2.1.3 required by the fixed parser, without changing
  other consumers. It verifies each patched file tree again after build.
  A synthetic Node regression rejects zero/oversized binary attachment counts
  and invalid event payloads while accepting a valid packet. Disposable HRMS
  frontend and roster asset builds succeeded after this change; the frontend
  sourcemap's parser sources match the patched installed package byte-for-byte.
  This does **not** remediate other apps' parser copies or establish a live
  Socket.IO/HRMS UI acceptance run. No Text Editor or HRMS route is disabled.
  The image, Foundation and Native installers apply the change before asset
  build; the web/bootstrap path verifies installed versions before
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
  exploit path; do not call it a full release security approval. Dispositions
  are now matched by **package and advisory ID**, including scoped npm names:
  a closed advisory for one library cannot lend its evidence to a different
  library sharing the same GHSA or CVE alias. On a disposable three-tree npm
  inventory after the HRMS parser fix (165 npm bulk advisory entries, each
  potentially covering multiple installed versions), this corrected one
  misattributed evidence record (`vite` / 1120784 previously
  borrowed `launch-editor` evidence); both recorded dispositions were
  DEV_ONLY, so this comparison changed **no** pass/fail verdict and left 75
  untriaged package/ID pairs in that scratch scope. This is not a hosted
  installed-tree count or independent revalidation of the other dispositions.

## Unfinished release gates

1. Observe hosted Foundation, Native, and Product image on the final head,
   including built HRMS editor behavior and printed PDF/preview behavior on a
   synthetic site. The existing static/in-memory regression tests are not an
   end-to-end proof of these paths.
2. Independently disposition/remediate **every** additional advisory in the
   newly included HRMS frontend/roster and ERPNext banking trees. The offline
   union-lock replay in `audit-expansion-replay-2026-10-09.json` found 168 npm
   advisory-version entries: 91 matched existing closed dispositions (**not**
   independently revalidated for these newly scanned trees), **77 untriaged**
   (73 distinct GHSA identifiers; 3 critical, 29 high, 35 moderate, 10 low).
   This is a public lockfile replay, not the installed-tree result. Several
   criticals are code-generation/RCE matches; none is dismissed as build-only
   without callsite analysis. Do not relabel matches BUILD_ONLY or
   NOT_REACHABLE without pinned callsite or build evidence. The Foundation gate
   must fail until this is done; a passing earlier head did not scan these
   trees. Hosted Foundation run `37977729365` on `492019a` failed at
   `hosted-full-stack-dependency-audit` (exit 1), with header `advisory
   matches=235 in 69 packages`; 76 npm package/ID pairs are visible across
   its error annotations, and the lock replay lists 77. After the HRMS parser
   fix, hosted Foundation `38149432929` on `679161e` **failed** at that same
   audit command: **234 matches in 69 packages; 75 untriaged npm package/ID
   pairs**. A set-diff of the two check-run annotation sets shows exactly one
   removed pair, `socket.io-parser` / 1100541; there are no new untriaged
   pairs in this comparison. This confirms the narrow fix in the installed
   audit, **not** a passing security gate.
   A follow-up emits every untriaged public package/ID pair in bounded
   failure annotations instead of hiding the tail; the gate still fails.
   Hosted check `114493843583` (Foundation run `38147507770` on `14d4508`)
   completed with **76 untriaged installed npm package/ID pairs**, all visible
   in three `STACK-ADVISORY-UNTRIAGED` error annotations. Comparing their
   exact package/ID pairs to the 77 replay pairs yields only one difference:
   `follow-redirects` / 1116560 occurs **only in the lockfile replay**.
   The banking lock pins `follow-redirects@1.15.11` for `^1.15.11`, but its
   installed `axios@1.18.1` requests `^1.16.0`, for which that lock has no
   resolution. In a disposable frozen-Yarn scratch install, `yarn why` reports
   an installed **1.16.1** hoisted from axios; the installed-tree npm query
   returns no advisory for it. This explains the scratch lock/install delta
   without claiming that the hosted version was observed; the missing frozen
   resolution is a separate reproducibility concern to fix, not a waiver.
   The hosted Foundation command `hosted-full-stack-dependency-audit` still
   fails with exit 1 on the 76 open pairs. This is distinct from the total
   **235 advisory-version matches in 69 packages** in the hosted warning.

   Pinned HRMS frontend/roster and ERPNext banking were also installed from
   frozen locks in a **local disposable source checkout**, with registry URLs
   rewritten to the npm host without altering package integrity. HRMS's editor
   patch and all three asset builds succeeded. Production-build JavaScript
   sourcemaps (87 frontend, 2 roster, 34 banking) show `@firebase/app` in
   frontend and `socket.io-parser` in frontend **and** roster. These are
   bundled module-presence observations, not exploit proofs or dispositions.
   No other replay-open package name was found as a bundled JavaScript module
   in these three sourcemap sets. This does **not** prove other installed
   packages safe: build tools can execute at build time, sourcemaps can omit
   inputs (banking's Tailwind plugin warned of an incomplete map), and the
   audit must still assess the installed trees. The local banking build used
   a synthetic throwaway `common_site_config.json`; no site or runtime data
   was accessed. None of these scratch builds is hosted or Windows acceptance.

   Native run `37977729383` on `492019a` reached its final source check and
   failed at `tools/native/run_native.py:246`: `assert not run('unchanged-'+name,
   ['git','-C',d,'diff','--name-only'])`. The owned installer intentionally
   patches pinned Frappe's WeasyPrint file; the old invariant allowed *no*
   tracked modification. Commit `d0d74f7` narrows that invariant to exactly
   `frappe/utils/weasyprint.py` with a verified post-patch SHA-256, and still
   rejects every other tracked change. Native rerun `37979725053` on
   `d0d74f7` **passed**; final-head Foundation `37980004394` still **failed**
   at `hosted-full-stack-dependency-audit`. Product image `37980004330` and
   Owned suite `37980004489`/`37980011858` passed on `b07a275`. These runs
   predate the annotation and cryptographic-test CI follow-up. After the
   HRMS parser patch, Product image `38149503915` (on `6fa8747`) passed
   application-image build, synthetic first boot/backup/restore, and browser
   UI acceptance. Native lifecycle `38149651905` (on `757e8e5`) passed its
   synthetic real-site lifecycle. Both Owned suite runs on `757e8e5`
   (`38149651777`, `38149656124`) passed. None of these is real Windows
   acceptance or an audit pass; Foundation `38149432929` failed as described
   above. A later Native run `38151418984` on `7d85379` failed at the new
   `security-site-acceptance` command on the **first authorized PDF preview**:
   Jinja's `print_format.html:10` invokes `include_style`, whose pinned
   `bundled_asset` calls `.get()` on the missing assets manifest. The Native
   bench deliberately uses `--skip-assets`; this is a test-fixture omission,
   not evidence that print authorization was bypassed. The correction supplies
   an empty, process-local manifest only in that disposable Native acceptance
   script, while the Product image separately builds and checks actual assets.
   A regression asserts the fixture precedes preview rendering. The corrected
   hosted run must pass before claiming site-backed WeasyPrint or Office 365
   acceptance; no such pass was observed on `7d85379`.
3. Real Windows installation, encrypted backup, restore (DB plus uploaded
   public/private files), restart and repair on a disposable Windows machine
   with Docker Desktop, including Course Owner login and policy/account
   persistence. Ubuntu Actions, line-ending emulation and mocks do **not**
   meet this gate. No Windows host is available in this sandbox. Do not run
   destructive acceptance against a real site or the operator's backup drive.
4. Required review and other release criteria remain independent. Keep
   `docs/owner-decisions.json:production_state` at `REJECT`.

## Review follow-up — 2026-10-14

The ECharts record in `advisory-delta-2026-10-03/delta-dispositions.json` remains `BLOCKED`. Its fix-path text previously contradicted that disposition by asserting the component was not bundled and therefore unreachable. That unsupported reachability assertion has been removed; the regression suite now checks that it cannot return. This is an evidence-quality correction only: it does not close the ECharts finding or authorize merge.

The remaining release gates above still apply. In particular, package-specific evidence for the untriaged installed npm advisory pairs, end-to-end WeasyPrint resource-fetch/SSRF controls, built HRMS editor paste-XSS acceptance, and real Windows Owner-machine lifecycle acceptance are not established by this documentation change.

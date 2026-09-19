# SEC-DEPS-01 readable finding register — 2026-09-19

Owner standing decision (2026-09-19, kept 2026-09-19): **keep REJECT until the
dependency-audit findings can actually be read.** This register is the
readability input for that decision. It changes no gate.

## What this is

- **Finding set:** exactly the retained resolved-stack evidence
  (`../phase-2/resolved-stack-advisory-2026-09-16.json`, SHA-256-verified
  transport of hosted run `35084695840`, check `104762158723`): **14 PyPI/OSV
  records + 97 npm advisory records.** Nothing added, nothing removed —
  `tests/foundation/test_sec_deps_register.py` enforces exact set equality.
- **What's new:** the 14 PyPI/OSV records had null summaries and severities;
  each was resolved against the public OSV API on 2026-09-19 and the returned
  summary, severity, CWE, aliases and fixed-version range were transcribed.
  The 97 npm records were already readable and are rolled up per package
  unchanged.
- **Machine form:** `readable-register-2026-09-19.json`, built by
  `tools/foundation/sec_deps_register.py` (`--check` verifies the committed
  file equals a fresh build, so it cannot drift by hand-edit).

## What this is NOT

Not a fresh audit of the current pins. Not exploitability or reachability
proof. Not a full SBOM. Not OS/container coverage. Not remediation. Not a gate
change: **SEC-DEPS-01 stays UPSTREAM-BLOCKED / REJECT, D8 stays BLOCKED,
production stays REJECT.** Per-finding reachability for the 7 Python
vulnerabilities is traced in
[pdf-reachability-trace-2026-09-19.md](pdf-reachability-trace-2026-09-19.md);
npm reachability is explicitly NOT established for any finding here.

## PyPI: 7 unique vulnerabilities, 4 packages (14 records)

| # | Package @ installed | Severity | Finding | Fix |
|---|---|---|---|---|
| 1 | pdfkit @ 1.0.0 | **HIGH** | Path traversal in `from_string`: server-side JS execution + local file exfiltration. GHSA-9g3x-6x24-vf9f / PYSEC-2026-2860 / CVE-2025-26240 | **NO FIX LISTED** (1.0.0 is last_affected) |
| 2 | pypdf @ 6.15.0 | MODERATE | Long runtimes / large memory on outlines (crafted-PDF DoS). GHSA-23w6-3w8w-8484 / PYSEC-2026-3910 / CVE-2026-84310 | fixed in **6.16.1** |
| 3 | pypdf @ 6.15.0 | MODERATE | Long runtimes / large memory on XForm extraction (crafted-PDF DoS). GHSA-763m-79hh-57f2 / PYSEC-2026-3911 / CVE-2026-84311 | fixed in **6.16.1** |
| 4 | pypdf @ 6.15.0 | MODERATE | Infinite loop in `TreeObject.insert_child` (crafted-PDF DoS). GHSA-jp53-mhqp-8xcg / PYSEC-2026-3913 / CVE-2026-84309 | fixed in **6.16.0** |
| 5 | setuptools @ 80.9.0 | MODERATE | MANIFEST.in exclusion bypass via NFC/NFD collision — **build-time, macOS APFS/HFS+ only** (sdist publishing, not Linux runtime). GHSA-h35f-9h28-mq5c / PYSEC-2026-3447 / CVE-2026-59890 | fixed in **83.0.0**, but Bench constrains setuptools below it |
| 6 | weasyprint @ 68.0 | MODERATE | CSS injection via presentational hints (needs `presentational_hints=True` + untrusted HTML). GHSA-jhhc-3hcp-qhm5 / PYSEC-2026-3412 / CVE-2026-49452 | **no fixed version listed** (last_affected 68.1) |
| 7 | weasyprint @ 68.0 | MODERATE | SSRF / `url_fetcher` bypass: local file read via `xmp_metadata`, resource loading via `stylesheets` (needs attacker-influenced params). GHSA-jf6q-chmf-3h3v / PYSEC-2026-3940 / CVE-2026-55073 | fixed in **70.0** |

Full per-record detail (CVSS vectors, CWE, deployment notes, OSV URLs) is in
the JSON register. Details: https://osv.dev/vulnerability/\<id\> for any id above.

## npm: 97 entries, 36 packages (2 critical / 49 high / 39 moderate / 7 low)

Titles, CWEs and vulnerable ranges per advisory are in the JSON register
(`npm_rollup_by_package`) and in the retained evidence. Package rollup:

| Package | Installed | Entries | Worst |
|---|---|---|---|
| @tiptap/core | 2.2.3 | 1 | moderate |
| @tiptap/extension-link | 2.2.3 | 1 | low |
| brace-expansion | 1.1.11, 2.0.1 | 10 | high |
| braces | 3.0.2, 3.0.3 | 1 | high |
| browserslist | 4.22.1, 4.23.0 | 2 | high |
| colord | 2.9.3 | 1 | moderate |
| cookie | 0.4.2, 0.7.0 | 1 | low |
| cross-spawn | 7.0.3 | 1 | high |
| decode-uri-component | 0.2.2 | 1 | moderate |
| engine.io | 6.5.4 | 2 | high |
| esbuild | 0.14.54 | 1 | moderate |
| glob | 10.3.10, 7.2.3 | 1 | high |
| image-size | 0.5.5 | 2 | high |
| immutable | 4.3.4 | 3 | high |
| json5 | 0.5.1 | 1 | high |
| launch-editor | 2.6.1 | 2 | high |
| linkify-it | 5.0.0 | 2 | high |
| loader-utils | 0.2.17, 3.2.1 | 1 | critical |
| lodash | 4.17.21 | 3 | high |
| lodash-es | 4.17.21 | 3 | high |
| markdown-it | 14.0.0 | 2 | moderate |
| micromatch | 4.0.5, 4.0.8 | 1 | moderate |
| minimatch | 3.1.2, 9.0.3 | 6 | high |
| nanoid | 3.3.7, 3.3.8 | 4 | high |
| picomatch | 2.3.1 | 2 | high |
| postcss | 5.2.18, 6.0.23, 7.0.39, 8.4.31, 8.4.35 | 6 | high |
| quill | 1.3.7, 2.0.3 | 2 | moderate |
| rollup | 2.77.3 | 2 | high |
| shell-quote | 1.8.1 | 2 | critical |
| showdown | 2.1.0 | 3 | moderate |
| socket.io-parser | 4.2.4 | 2 | high |
| svgo | 2.8.0 | 4 | high |
| tmp | 0.2.4 | 1 | high |
| vite | 2.9.17 | 15 | high |
| ws | 8.11.0 | 3 | high |
| yaml | 1.10.2, 2.3.4 | 2 | moderate |

## Honest consequences for the local launch decision

1. **pdfkit HIGH with no patch**: path traversal in `from_string` with
   server-side JS execution and local file exfiltration; 1.0.0 is the last
   affected version. Traced: both halves are disabled by forced
   `disable-javascript`/`disable-local-file-access` at the single Frappe call
   site, but HTML reaches `from_string` by design — disposition OPEN, not
   NOT-REACHABLE. Any risk acceptance must name this finding explicitly.
2. **Two weasyprint MODERATEs**, gated on beta-builder Print Formats (the
   product ships none). SSRF fixed in 70.0 (Frappe pins 68.0); CSS injection
   has no listed fix (68.1 last affected).
3. **pypdf MODERATEs** are crafted-PDF denial of service, **reachable via
   native PDF upload**, with patch releases available (6.16.0/6.16.1) that
   Frappe does not pin — an upstream-release plus re-qualification decision,
   not taken here.
4. **setuptools MODERATE** is build-time macOS-only; negligible Linux-server
   runtime relevance, but it still fails the audit while pinned below 83.0.0.
5. **npm: 2 critical + 49 high**, dominated by build/dev-transitive packages
   (vite 15, brace-expansion 10, postcss/minimatch 6 each). Whether any survives
   into served assets or accepts attacker input is NOT established by this
   register; the 2026-09-14 triage began that per-advisory separation and its
   gate stayed closed.

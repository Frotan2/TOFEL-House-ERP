# Stored-HTML audit (GHSA-VHRC-hgrq-x75r, residual 1) — owner-run procedure

Status: **tool written and unit-tested; the bench run is OWNER-RUN and UNVERIFIED here.**
No live site, real backup, or real credential was touched. The sandbox has no Frappe bench.

## Why this exists

GHSA-VHRC-hgrq-x75r (`@tiptap/extension-link` `javascript:` links) is fixed for code written
after the upgrade: the Education frontend is pinned to 2.27.3 and the containment hook
(`apps/foundation_security/foundation_security/html_containment.py`) sanitizes JSON-shaped values
that Frappe's `is_json` short-circuit would otherwise store unsanitized.

**Residual 1:** rows saved *before* the upgrade and containment are not rewritten by the fix.
This audit tells the owner how many such rows exist and in which records. It does not change
any row. What to do with the rows is an owner decision (see "Decisions" below).

## What it does

`tools/foundation/audit_stored_html.py <site>` runs inside the bench and:

1. Lists every HTML-capable field (`Text Editor`, `Text`, `Small Text`, `Markdown Editor`) from
   `DocField` **and** `Custom Field`.
2. For each field, issues one `SELECT name, <field> FROM tab<Doctype> WHERE <field> IS NOT NULL AND <field> != ''`.
   There is no `LIKE` pre-filter, because a JSON-escaped payload (`\u003c`) contains no literal `<`.
3. Classifies each value with the **same functions the containment hook uses**:
   - `would_change`: containment would store a different value (the real hazard set);
   - `json_shaped`: the value takes Frappe's JSON short-circuit (the exposure path);
   - `scheme_or_handler`: contains a `javascript:` scheme or an inline `on<event>=` handler.
4. Prints JSON with counts and **record names only**. Stored content is never printed.

Fields with `ignore_xss_filter` are **scanned and flagged** (`"ignore_xss_filter": true`), not
skipped. Frappe does not sanitize them, so they are the highest-risk rows.

Unsafe identifiers (anything that is not `[A-Za-z0-9 ]` for doctype or `[a-z0-9_]` for fieldname)
are reported under `skipped` and never queried.

## Read-only guarantees (enforced by tests)

- Static test: the script contains no `db.commit(`, `db_set(`, `set_value(`, `.save(`, `.delete(`,
  `delete from`, `update <table>`, `insert into`, or `.set(` in code (docstring excluded).
- Static test: exactly one `frappe.db.sql(` call, which is a `select`.
- Behavioural test: a fake `frappe` records every query; a mutation that injects `db.commit()` fails.
- The audit never calls `contain_document`, which writes. It calls only the pure `contain_value`.

Mutation check (2026-10-18, sandbox): disabling the `would_change` branch, injecting `db.commit()`,
and re-adding a literal `LIKE '%<%'` each failed the suite; the file was restored byte-for-byte.

## Automated evidence on the commit (sandbox, not the owner's site)

| Check | Result |
|---|---|
| `tests/security/test_stored_html_audit_2026_10_17.py` | 15 tests OK |
| Full Python tree (`unittest discover -s tests -t .`) | 1411 tests OK |
| `ruff check .` (pinned `ruff==0.16.8`, hash-checked) | All checks passed |
| Real pinned Frappe `sanitize_html` (hash-checked fixture) | JSON-wrapped `onerror` payload: active raw, inert after containment; legitimate formatting untouched |

These tests use **synthetic rows only**. They do not show what the owner's site contains.

## Owner-run procedure

Run on a **restored copy** of the site first. Only then run against a live site if you choose.
Use a read-only database account if you have one. The tool does not need write privileges.

```bash
# 1. Restore the latest backup to a SEPARATE test site (never the production site name).
#    Use the product restore procedure in docs/engineering/evidence/windows-backup-readiness-2026-10-16/PROCEDURE.md.

# 2. From the bench, run the read-only audit against that copy:
cd <bench>/sites
<bench>/env/bin/python <repo>/tools/foundation/audit_stored_html.py <restored-site-name> > stored-html-audit.json

# 3. Review the summary without reading record content:
python3 -c "import json,sys; d=json.load(open('stored-html-audit.json')); print(d['totals']); print([ (f['doctype'],f['fieldname'],f['ignore_xss_filter'],f['counts']) for f in d['fields'] if f['counts'].get('would_change') or f['counts'].get('scheme_or_handler')]); print(d['skipped'])"
```

Expected output shape (keys always present; values depend on your data):

```json
{
  "site": "<restored-site-name>",
  "totals": {"scanned": 0, "would_change": 0, "json_shaped": 0, "scheme_or_handler": 0},
  "fields": [{"doctype": "...", "fieldname": "...", "fieldtype": "...", "ignore_xss_filter": false,
              "counts": {...}, "record_names": {"would_change": [], "json_shaped": [], "scheme_or_handler": []}}],
  "skipped": []
}
```

Interpretation:

- `would_change == 0` on the restored copy: no pre-upgrade row is currently a containment-changing
  value in HTML fields. This is evidence for the owner, not a release gate on its own.
- `would_change > 0`: the record names in `record_names.would_change` are the rows that need a
  decision (below). Do not edit them by hand from the audit output.
- Any `ignore_xss_filter: true` field with `would_change` or `scheme_or_handler`: highest priority.
- `skipped` non-empty: investigate; these fields were not checked.

`record_names` may identify private records. Treat the JSON as confidential and keep it out of Git
and out of issues.

## Decisions this feeds (owner)

1. **Residual 1 disposition**, one of:
   - (a) owner-run backfill migration that re-saves flagged rows through the containment hook (needs
     its own review, backup first, and a dry-run report);
   - (b) accept the residual with the audit result attached as the record;
   - (c) audit first, then choose (a) or (b).
   No option is chosen here. The sandbox made no production change.
2. **Retire the GHSA-VHRC BLOCKED register record** once residual 1 is decided. The Education
   overlay (2.27.3) and the containment hook are verified in CI; the register record is still
   BLOCKED pending that decision.

## What this does NOT prove

- It does not prove the owner's real site is clean. It has not been run against any live data.
- It does not cover writes made by `db_set`, `set_value`, or raw SQL. Those bypass `validate`, and
  they are not reachable from product code (see the residual-2 note in the containment README).
- It does not cover non-`tab` storage, attachments, or files on disk.
- It does not verify the bench itself. Running it inside a bench is an owner step, UNVERIFIED here.

# Frappe Python dependency security uplift — 2026-10-22

This release keeps the reviewed Frappe source commit pinned and applies a
hash-bound dependency-only overlay before the application is built.

The exact runtime replacements are:

- `GitPython 3.2.1` — includes the validate-before-mutation fix for
  GHSA-83vg-56qc-22m7.
- `Pillow 13.0.0` — the reviewed October 2026 Pillow security uplift; upstream
  Frappe PR #44814 makes the same dependency-family change.
- `PyJWT 2.15.1` — includes the 2.14.0 fix for GHSA-pxh4-856f-4h89 and stays
  on the current upstream Frappe-compatible 2.x line.
- `pypdf 6.21.2` — includes the October parser/resource fixes through 6.21.2,
  including the 6.21.1 DCT/JPEG validation hardening.

`tools/foundation/secure_frappe_python.py` refuses any Frappe commit or
`pyproject.toml` bytes other than the pinned source, changes exactly four
reviewed requirement lines, and verifies all four installed versions after the
editable Frappe metadata refresh. The product-image, native-lifecycle and
foundation-runtime paths all use the same helper.

This is a dependency security remediation, not a change to business policy or
production authorization. Hosted gates must still pass after the uplift.

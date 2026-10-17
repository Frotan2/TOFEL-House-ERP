# Vendored Frappe sanitizer source (test fixture only)

- Source: `frappe/frappe` at commit `988e54f3c4c291e2077a83809663f123731abe76` (the pinned Frappe v16.33.1).
- File: `frappe/utils/html_utils.py`, copied byte-for-byte. SHA-256 `9997c4d8f2782ca3a5ad08ecf047a4bce798ba67cea1092a861826702545fd15`.
- The test verifies this SHA-256 before loading the file, and fails if it differs.
- Licence: MIT (`LICENSE.txt`, copied from the same commit).
- Used only by `tests/security/test_html_containment_real_sanitizer_2026_10_16.py`. Not shipped in the product.
- The only stubbed dependency is the `frappe` package itself (`frappe.utils.data.escape_html`, `frappe.as_unicode`), which the `sanitize_html` path does not call. The sanitizer code and its `nh3` / `bleach_allowlist` / `bs4` dependencies are real.

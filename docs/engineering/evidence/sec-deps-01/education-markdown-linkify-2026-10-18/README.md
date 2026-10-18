# Education frontend: markdown-it and linkify-it remediation (2026-10-18)

Scope: two of the five `BROWSER_SELF_DENIAL` records that the owner decision OD-2026-10-18-A keeps open
(`docs/owner-decisions.json`). The remediation is a pinned overlay for the Education frontend lock, applied by
`tools/foundation/secure_education.py`, the same mechanism as the GHSA-VHRC `@tiptap/*` overlay.

## Advisories and fixed versions (GitHub Advisory Database, `api.github.com/advisories/...`, 2026-10-18)

| Advisory | Package in tree | Vulnerable range | First patched | Overlay pin |
|---|---|---|---|---|
| GHSA-38c4-r59v-3vqw (ReDoS) | `markdown-it@14.0.0` | `>= 13.0.0, < 14.1.1` | 14.1.1 | `resolutions.markdown-it = 14.1.1` |
| GHSA-22p9-wv53-3rq4 (quadratic `match`) | `linkify-it@5.0.0` | `<= 5.0.0` | 5.0.1 | `resolutions.linkify-it = 5.0.2` |
| GHSA-v245-v573-v5vm (quadratic `mailto:`) | `linkify-it@5.0.0` | `<= 5.0.1` | 5.0.2 | `resolutions.linkify-it = 5.0.2` |

## Lock change (`tools/foundation/education-locks/frontend/yarn.lock`, Yarn 1.22.22, registry.npmjs.org)

- `markdown-it` 14.0.0 to 14.1.1 (`integrity sha512-BuU2qnTti9YKgK5N+IeMubp14ZUKUUw7yeJbkjtosvHiP0AZ5c8IAgEMk79D0eC8F23r4Ac/q8cAIFdm2FtyoA==`).
- `linkify-it` 5.0.0 to 5.0.2 (`integrity sha512-ONTm2jCMAVZjgQa/Fy1kScXsuOoF5NPTsoFBdE1KVIZ2vAh/r9+Bqo+0jINCBYnavTPQZz38QzFTme79ENoN3Q==`).
- `uc.micro` 2.0.x to 2.1.0, the new dependency required by markdown-it 14.1.1 (`^2.1.0`).
- No other lock entry changed (`diff` of the lock: 23 lines).

## Why this closes the findings

The Foundation audits match installed versions against advisory ranges. A tree at a patched version
produces no finding for the advisory. The register records stay immutable; they are not edited.

## What is NOT closed (still BROWSER_SELF_DENIAL, still open)

- `showdown@2.1.0` (GHSA-rmmh-p597-ppvv): the advisory lists no patched version. It is in the Education lock and in
  `tools/foundation/realtime-locks`. It needs removal, replacement or runtime proof. Not addressed here.
- `@tiptap/core` (GHSA-cp6q-959q-f8rh): the first patched version is 3.30.4. The Education overlay pins 2.27.3, which is
  still in the vulnerable range. Moving to 3.x is a major migration of the Education editor. Not addressed here.

## Verification

- `tests/security/test_education_locks_2026_10_17.py` (19 tests) passes; new test
  `test_markdown_it_and_linkify_it_are_pinned_to_patched_versions` pins the two versions and the lock entries.
- Full local suite passes. CI verification: the Foundation run on the head that carries this change (see the owner package).

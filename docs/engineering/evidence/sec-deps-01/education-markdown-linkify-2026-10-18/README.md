# Education frontend: markdown-it and linkify-it remediation (2026-10-18)

Scope: two of the five `BROWSER_SELF_DENIAL` records that owner decision OD-2026-10-18-A keeps open
(`docs/owner-decisions.json`). The remediation is a pinned overlay for the Education frontend lock, applied by
`tools/foundation/secure_education.py`, the same mechanism as the GHSA-VHRC `@tiptap/*` overlay.

## Advisories and fixed versions (GitHub Advisory Database, `api.github.com/advisories`, 2026-10-18)

| Advisory | Package in tree | Vulnerable range | First patched | Overlay pin |
|---|---|---|---|---|
| GHSA-38c4-r59v-3vqw (ReDoS) | `markdown-it@14.0.0` | `>= 13.0.0, < 14.1.1` | 14.1.1 | `resolutions.markdown-it = 14.3.3` |
| GHSA-6v5v-wf23-fmfq (quadratic smartquotes, medium) | `markdown-it@14.1.1` after the first pin | `<= 14.1.1` | 14.2.0 | `resolutions.markdown-it = 14.3.3` |
| GHSA-253c-mchw-3w2r (quadratic linkify paths, medium) | `markdown-it@14.1.1` after the first pin | `< 14.3.1` | 14.3.1 | `resolutions.markdown-it = 14.3.3` |
| GHSA-22p9-wv53-3rq4 | `linkify-it@5.0.0` | `<= 5.0.0` | 5.0.1 | `resolutions.linkify-it = 5.0.2` |
| GHSA-v245-v573-v5vm | `linkify-it@5.0.0` | `<= 5.0.1` | 5.0.2 | `resolutions.linkify-it = 5.0.2` |

The first pin (14.1.1) was tried and rejected: run `e0c22ca` surfaced GHSA-6v5v and GHSA-253c as
new untriaged findings against `markdown-it@14.1.1`. The pin was moved to 14.3.3, the newest 14.x release.
`GET api.github.com/advisories?affects=markdown-it@14.3.3` returns no advisories. The same filter returns the two
advisories for 14.1.1, so the filter is a valid check.

## Lock change (`tools/foundation/education-locks/frontend/yarn.lock`, Yarn 1.22.22, `--registry https://registry.npmjs.org/`)

- `markdown-it` 14.0.0 to 14.3.3 (`integrity sha512-L//tDAkjTjJCU6pBUSBTgs3Kg4InVaZuUZog/b6V12UKhcDQ7S78877ibbCanRExwPuYP1CZD7Gd2dxSy1GXRg==`).
- `linkify-it` 5.0.0 to 5.0.2 (`integrity sha512-ONTm2jCMAVZjgQa/Fy1kScXsuOoF5NPTsoFBdE1KVIZ2vAh/r9+Bqo+0jINCBYnavTPQZz38QzFTme79ENoN3Q==`).
  markdown-it 14.3.3 requires `linkify-it ^5.0.2`.
- `entities` deduplicated to the existing `^4.5.0` entry (markdown-it 14.3.3 requires `^4.5.0`).
- `uc.micro` entries are unchanged.

## Why this closes the findings

The Foundation audits match installed versions against advisory ranges. A tree at a patched version produces no
finding for the advisory. The register records stay immutable and are not edited. Register deltas can only target
BLOCKED, so the fix has to remove the match by upgrading the package.

## What is NOT closed (still BROWSER_SELF_DENIAL, still open)

- `showdown@2.1.0` (GHSA-rmmh-p597-ppvv): the advisory lists no patched version. It is in the Education lock and in
  `tools/foundation/realtime-locks`. It needs removal, replacement or runtime proof. Not addressed here.
- `@tiptap/core` (GHSA-cp6q-959q-f8rh): the first patched version is 3.30.4. The Education overlay pins 2.27.3, which is
  still in the vulnerable range. Moving to 3.x is a major migration of the Education editor. Not addressed here.

## Verification

- `tests/security/test_education_locks_2026_10_17.py` (19 tests) passes. The test
  `test_markdown_it_and_linkify_it_are_pinned_to_patched_versions` pins the two versions and the lock entries.
- Full local suite and ruff: see the commit message and the owner package for the final head.
- Foundation runtime evidence: run `39150998353` (head `e0c22ca`, markdown-it 14.1.1) showed linkify-it absent and
  markdown-it 14.1.1 with two new advisories. It is superseded by the 14.3.3 head; the run for that head is recorded in
  the owner package.

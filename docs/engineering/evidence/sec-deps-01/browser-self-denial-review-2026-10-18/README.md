# BROWSER_SELF_DENIAL review (2026-10-18)

Scope: every record whose `runtime_disposition` is `BROWSER_SELF_DENIAL` in the 2026-09-23 register (`per-finding-remediation-analysis-2026-09-23.json`) and its dated deltas. The review tests each premise against the stored-content evidence that overturned the GHSA-VHRC self-denial premise on 2026-10-17.

Result: **no `BROWSER_SELF_DENIAL` record is upheld as written.** The register's records are immutable evidence, so no disposition is changed here. Each record below is marked **NOT SUSTAINED** (the premise is contradicted by the record's own reach evidence) or **UNVERIFIED** (the premise depends on a field-audience fact nobody has checked). Owner decisions are listed in section 3.

## 1. Records reviewed (6)

| # | Package | Advisory | Severity | Record's premise | Reach evidence in the record | Verdict |
|---|---|---|---|---|---|---|
| 1 | markdown-it@14.0.0 | GHSA-38c4-r59v-3vqw | moderate | ReDoS runs "in authenticated student/employee browser only; server sanitizes persisted content" | Education/HRMS bundles; the TH launch scope excludes the student/guardian portal | **UNVERIFIED.** A ReDoS payload is a long string, which a sanitizer does not remove. The premise also needs every surface that renders the markdown to be single-user. Not verified. |
| 2 | showdown@2.1.0 | GHSA-rmmh-p597-ppvv | moderate | "runs in the user's browser against markdown they typed" | Desk `frappe.markdown` rendering of "authenticated-user-authored markdown" | **NOT SUSTAINED.** The record's own reach text describes content authored by authenticated users, which other users can read. The premise "markdown they typed" only holds for self-only content. |
| 3 | @tiptap/extension-link@2.2.3 | GHSA-vhrc-hgrq-x75r | low (register) | "javascript: URL link injection ... cross-user exploitation requires server persistence which sanitize_html strips" | Education editor; portal outside launch scope | **NOT SUSTAINED and already superseded.** On 2026-10-17 the owner-approved disposition is **BLOCKED** and the chosen fix is the coordinated TipTap upgrade. The "sanitize_html strips" premise was shown to be wrong: Frappe's JSON short-circuit returns stored values unchanged. Rows saved before the upgrade are residual 1 (owner audit pending). |
| 4 | @tiptap/core@2.2.3 | GHSA-cp6q-959q-f8rh | moderate | "requires an attacker-controlled attribute object; FormField content is server-sanitized" | Education editor; the same stored-content path as #3 | **NOT SUSTAINED as written.** It relies on the same "server-sanitized" premise that did not hold for stored rows. The Education overlay pins 2.27.3 (fixed), but that overlay is **not** in the product image (owner decision: separate). |
| 5 | linkify-it@5.0.0 | GHSA-22p9-wv53-3rq4 | high | "same browser-only execution context" (transitive of markdown-it) | markdown-it dependency in Education/HRMS | **UNVERIFIED.** Same premise as #1. A ReDoS in a shared-content renderer is cross-user availability impact, not self-denial. |
| 6 | linkify-it@5.0.0 | GHSA-v245-v573-v5vm | high | duplicate of #5 | same | **UNVERIFIED.** Same as #5. |

Summary of the review: the classification "self-denial" assumes that a user's own browser is the only consumer of the content. The register's reach evidence contradicts that for showdown and tiptap (shared, authored content), and it is not verified for markdown-it and linkify-it. Exposure is **client-side availability** (ReDoS and memory), not server compromise. It is still cross-user for shared content.

## 2. Related facts found in this review

- The product image (`product/app.Dockerfile`) does **not** apply the Education TipTap overlay. The native path does. So `@tiptap/*` 2.2.3 is still shipped in the product image's Education frontend. This is an owner decision (separate from the realtime overlay).
- Two copies of `socket.io-parser` 4.2.4 and `ws` 8.11.0 remain in the Education frontend lock, and `ws` 8.17.1 in the banking frontend lock. The `ws` copies are reached only through `engine.io-client`'s Node transport. The `browser` field of `engine.io-client` (6.5.1 and 6.5.3, checked on the npm registry) maps the WebSocket constructor to the browser version, so `ws` is not expected in browser bundles. Bundle output has not been inspected. The `socket.io-parser` 4.2.4 copy **is** in the Education browser client bundle. It is not covered by the realtime fix (see `realtime-socketio-2026-10-18/README.md` §6).
- The Foundation annotation (run `39106323632`, `7e0f1915`) lists `npm:socket.io-parser@4.2.4,4.2.7` and `npm:ws@8.11.0,8.17.1,8.21.3`. The version lists are the installed versions across the whole stack (`tools/foundation/audit_stack.py` `installed_versions`), not the matching versions. The matches are the 4.2.4, 8.11.0 and 8.17.1 copies.

## 3. Owner decisions required

1. **Shared-content renderers (#1, #2, #5, #6):** accept as client-side availability residuals with a stated audience, or require a field audit (which Desk, Education and HRMS fields render markdown, and who can read them). Until decided, these are **not** self-denial.
2. **Education frontend (`socket.io-parser` 4.2.4, `ws` 8.11.0) and the Education TipTap pin in the product image:** extend the Education overlay (same mechanism as the TipTap pin) to these packages, or accept.
3. **Banking frontend (`ws` 8.17.1):** extend the banking overlay, or accept as Node-transport-only with bundle evidence.

Release impact: each item above keeps the release at **NO-GO** until decided. None of them is a server compromise on the production realtime path, which is handled by the realtime overlay.

## 4. Not done here

- No bundle output was inspected (no build was run here).
- No field audit of markdown renderers was run. Nothing was run against the owner's real site.
- No disposition was changed, and the immutable register was not edited.

## Addendum 2026-10-18: owner decision and what the Desk rendering check does not close

Owner decision (2026-10-18): **keep all six records open** (UNVERIFIED or BLOCKED until a runtime
check proves each premise). Nothing is closed on paper review. Recorded in `docs/owner-decisions.json`
as `OD-2026-10-18-A`.

The new Desk rendering step `browser-desk-hrms-stored-html` (passed on `5431053`, run `39136491032`;
see `hrms-editor-2026-10-15/README.md` addendum 2026-10-18b) covers a stored HRMS Text Editor value in
Desk. It does **not** exercise the six records' premises: `markdown-it`, `showdown`, `@tiptap/extension-link`,
`@tiptap/core`, and `linkify-it` in the Education and HRMS bundles, nor the student or guardian portal.
Therefore no `BROWSER_SELF_DENIAL` record changes state because of it. Each of the six records
remains open until a runtime check that drives its own content path is added and passes.

**Gate change (same day, implements OD-2026-10-18-A).** `BROWSER_SELF_DENIAL` was a member of
`CLOSED_DISPOSITIONS` in `tools/foundation/advisory_triage.py`, so its matches passed the audit. It is
now an owner-open disposition: `OWNER_OPEN_DISPOSITIONS`, not closed. Each match fails the stack and
frontend audits until a runtime check proves its premise and the owner records that proof. Pinned by
`tests/security/test_browser_self_denial_open_2026_10_18.py`. The earlier gate-replay note
("BROWSER_SELF_DENIAL is a closed disposition in the current policy") describes the 2026-10-16 state only.

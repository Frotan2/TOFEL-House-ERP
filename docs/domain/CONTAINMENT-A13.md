# A13 Containment Evidence — native bypass-route proofs for the implemented slices

Date: 2026-09-15 · Session branch: `arena/01a0a496-tofel-house-erp`
· Qualifying commit: `5b5a044` · Hosted run `35008705885`: **523/523 checks
pass**, native report SHA-256
`a66a1b5d5dd2793a1e43bf6b90610a79f3afeda4d789c7d7b562e1fce3176f89`.
· Decision basis: [ARCHITECTURE-DECISIONS.md](ARCHITECTURE-DECISIONS.md) A13
(recommendation H: server invariant coverage).

**Status: A13 remains CONDITIONAL overall.** What this document proves is
the *implemented-slice* coverage half of A13: hosted negative tests across
the native write routes for the seven command-only doctypes of the five
closed slices. The full native writer/side-effect inventory for not-yet-
implemented domains (B10/B11/B13) remains open. **Production remains
REJECT. Do not deploy.**

## 1. The gap that was closed

All five closed slices enforce "commands are the only writer" through
`validate` doc_event guards on: Program Enrollment, Course Enrollment,
Sales Invoice, Fees, Student Group, Course Schedule, Student Attendance.

Pinned frappe (`988e54f3c4c2`, `frappe/model/document.py`,
`run_before_save_methods`) shows `validate` fires **only** for save and
submit actions:

- **cancel** runs `before_cancel` — no `validate`;
- **post-submit edits** run `before_update_after_submit` — no `validate`.

A validate-only guard therefore had cancel and post-submit-edit bypass
routes. `hooks.py` now pins the same command-only guard on all three
seams for all seven doctypes (static test:
`tests/finance/test_containment_hooks.py`).

Native facts verified at the pinned commits (not assumed):

- Delete of a submitted document is denied unconditionally, even for
  `Administrator` (`frappe/model/delete_doc.py`,
  `check_permission_and_not_submitted`).
- Cancel of a draft of a non-submittable doctype is denied by frappe's
  docstatus transition validator *before* `before_cancel` fires
  (`Cannot change docstatus from 0 (Draft) to 2 (Cancelled)`).
- `frappe.client.set_value` / REST resource PUT resolve to
  `get_doc → update → save` — the same guarded lifecycle
  (`frappe/client.py`, `frappe/resource.py`).
- `runserverobj` is a deprecated alias of `run_doc_method`
  (`frappe/handler.py`).
- Education Fees permissions grant `Accounts User`
  read/write/create/submit/delete (`93bc7075`, `fees.json`) — the web-seam
  probe user therefore reaches the guard, not a role denial.

## 2. Hosted evidence (actual runner output; nothing relabeled)

- Run `35004695315` (commit `3374216`): **FAIL** — 517/517 prior checks
  stayed green; first cancel probe iteration failed honestly on Course
  Enrollment: non-submittable draft, native transition denial fires before
  the guard. Probe fixed in `2caf3da` to classify the denial layer.
- Run `35005981914` (commit `2caf3da`): **PASS 523/523** — but every REST
  probe returned 403 PermissionError: the re-granted post-revocation
  finance_officer session did not carry effective Fees permissions at
  request time, so the *guard* layer at the web seam was not demonstrated.
  Fixed in `514a061` with a dedicated `containment_probe` user (native
  Accounts User, never revoked); `5b5a044` added its missing users-map
  entry (run `35007663815` KeyError).
- Run `35008705885` (commit `5b5a044`): **PASS — 523/523**, SHA-256 above.
  The six `containment-*` checks, with their recorded observations:

| Check | Result |
|---|---|
| `containment-admin-cancel-denied` | Fees / Sales Invoice / Program Enrollment / Student Attendance: **command-only guard (`before_cancel`)**, docstatus intact. Course Enrollment / Student Group / Course Schedule: **native docstatus transition** (draft, non-submittable), docstatus intact. |
| `containment-edit-seam-denied` | Guard denial, value unpersisted: Fees `student_name`, Sales Invoice `company_tax_id` (submitted → `before_update_after_submit`); Course Enrollment `program`, Student Group `student_group_name`, Course Schedule `title` (draft → `validate`). Program Enrollment / Student Attendance carry no plain-text field — **reported not probed**, covered by the pinned hooks and identical guard path. |
| `containment-rpc-routes-denied` | `frappe.client.insert` (full valid Fees payload) and `frappe.client.set_value` as `Administrator`: guard denial, nothing persisted. `frappe.client.delete`: native submitted-record denial, document intact. |
| `containment-rest-routes-denied` | As `containment_probe` (native Accounts User, permission layer satisfied): `POST /api/resource/Fees` → **417 ValidationError (guard)**; `PUT /api/resource/Fees/<name>` → **417 (guard)**, value unpersisted; `DELETE` → 417 native submitted-record denial; `runserverobj` Desk cancel route → 403 permission layer (Accounts User has no Fees cancel; guard on the cancel seam proven server-side where permissions are bypassed). |
| `containment-amend-copy-denied` | `frappe.copy_doc` + insert of Fees and Sales Invoice as `Administrator`: guard denial. Amend is unreachable while cancel is denied. |
| `containment-no-side-effects-from-probes` | GL Entry / Fees / Sales Invoice / receipt / audit counts unchanged by all probes; all seven target documents intact. |

## 3. Boundary — what is *not* claimed

- **`db_set` / direct SQL / privileged operator access** bypass document
  hooks by design. A13 itself scopes this as governed/audited access, not
  something app code can prevent; no code claim is made.
- **Queue-worker seam**: a background job executes the same document
  lifecycle (the runner runs no worker; no check is faked). The lifecycle
  seam it shares is the proven one (`client.insert` ≡ job `insert()`).
- **Data Import** was not exercised end-to-end; it routes through the same
  `get_doc(...).insert()` lifecycle proven via `frappe.client.insert`.
- Cancel/post-submit guards deny **absolutely** outside commands,
  including for `Administrator`. Legitimate correction paths (refunds via
  native Credit Note etc.) remain owner deliverables
  ([FINANCE-POLICY-APPROVAL.md](FINANCE-POLICY-APPROVAL.md)); enabling any
  of them must extend the command surface, never loosen the hooks.
- Closed domains were not reopened: no command behavior changed; the
  guards are the same functions, additionally pinned on two seams, and
  the full prior suite (517 checks) re-passed unchanged in every run
  above.

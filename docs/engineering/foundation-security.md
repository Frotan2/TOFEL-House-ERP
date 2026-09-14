# Foundation security qualification

## Status and scope

**Security gate: NOT PASSED. Product implementation: NOT AUTHORIZED.**

### Latest checkpoint — final integration outcome unavailable

Run **34781717183** at `956fd31` was last observed running. GitHub then returned
**HTTP 401 Bad credentials**, so its final outcome has not been retrieved. Reconnect
GitHub in Arena and retrieve the sanitized Check before relying on this candidate.
The generic guard is **not runtime-approved**. There are **26 passing local helper tests**.

The last confirmed extension run, **34781217903**, installed the app and passed a fresh
post-install cache/RQ job, but failed all four login controls: Administrator HTTP 400,
Students HTTP 403. Source tracing identified two extension defects, not new upstream
permission disclosures: generating CSRF inside session creation preceded Frappe's login
request CSRF validation; rejecting every DocShare also rejected core's legitimate User
self-profile share. The candidate now generates the token in the post-validation auth hook,
rejects tokenless unsafe legacy-session requests, and preserves only native self-profile
shares while rejecting other inherited/global shares. These corrections have unit coverage,
but their hosted verification is the unavailable run above.

Earlier packaging failures (`34780307591`, `34780667272`) are retained: Bench required a
standalone local Git app root and its empty `patches.txt` discovery manifest. The runner
exports exact owned app files into a disposable same-branch Git snapshot and uses supported
Bench registration; it does not hand-edit apps.txt or bypass installation checks. Superseded
pending runs `34780366068` and `34780432921` were cancelled by GitHub concurrency before
execution; they are neither passing nor failing qualification evidence.


This is a synthetic-data qualification of the pinned upstream bundle, not a production
hardening guarantee. GitHub access has recovered. Run `34778602344` is now retrieved and
verified against commit `43d4287bc63b47a2000cdb44a38f83fa322b9dc6`.

No TOEFL-specific app, schema or workflow was introduced. The remediation currently uses
native configuration and User Permission records, with no upstream core edits. The browser
harness runs unchanged Education assets in real Chromium behind a loopback-only Nginx proxy.

## Confirmed failure and cause

Runs `34778224918` and `34778602344` show that the tested Student role plus Student/user
link alone permits another student's generic REST document and private attachment to be read.
The target name and attachment SHA-256 were verified, not inferred from an HTTP status alone.
The Education `get_student_context` RPC rejected the same cross-student request.

Pinned-source call paths explain the difference:

1. Education's `student.json` gives the Student role read/export/print/share rights, without
   an owner restriction. The `user` field is not automatically a generic document ACL.
2. Frappe `permissions.has_user_permission` returns true when no User Permission rules exist.
   When explicit Student rules exist, it checks the document name; Customer restrictions also
   constrain relevant linked financial records.
3. Frappe `core/doctype/file/file.py:has_permission` allows a private attachment when its
   referenced document is readable (with separate owner/share exceptions). Thus a Student
   document scope error also exposes its private attachment. A private URL is not a separate ACL.
4. Education `api.check_permission` explicitly compares Student/user or guardian linkage.
   That protects the portal RPC but does not replace generic REST/File permission checks.
5. `Student.validate_user` can automatically create a Website User with the Student role.
   It does not create the Student/Customer User Permission records required by this policy.

These findings apply to the pinned revisions in `foundation-version-matrix.json`. They are
not a claim that all Frappe deployments, or every Education endpoint, have the same exposure.

## Verified narrow remediation

Run `34778602344` retains the failing baseline and then creates native User Permission records
for each synthetic user:

- `allow=Student`, `for_value=<that user's linked Student>`;
- `allow=Customer`, `for_value=<that Student's canonical Customer>`;
- `apply_to_all_doctypes=1` for both.

All ten restricted HTTP checks passed: both users authenticate, own Student and private file
remain accessible, cross-student REST and private files return 403, and the portal RPC remains
403. Administrator checks on source/restore and the transport handshake also pass.
The run remains **failed**, deliberately, because its original baseline failed.

This is a verified configuration remedy for those two paths, **not complete security acceptance**.
It must not be represented as an automatic provisioning fix or a full role/tenant matrix.

## Additional hardening under qualification

The next policy revision uses native settings to close alternate activation/sharing paths:

| Setting | Intended protection |
|---|---|
| Website Settings `disable_signup=1` | Disable public account signup while controlled provisioning is required. |
| Education Settings `user_creation_skip=1` | Do not silently activate an unscoped Student account during Student creation. |
| System Settings `apply_strict_user_permissions=1` | Avoid permissive empty-link behavior for applicable User Permissions. |
| System Settings `disable_document_sharing=1` | Prevent peer document shares from overriding the intended student boundary. |

These settings change operational capabilities. Public signup, automatic portal activation and
ad-hoc sharing are intentionally unavailable; guardians/staff collaboration still require their
own qualification. Administrator is a trusted configuration authority, not an untrusted tenant user.
Do not grant extra staff roles to Student accounts. A Company/Branch is **not** a tenant boundary;
independent sites/databases are the boundary tested here.

Before any real deployment, provision accounts disabled or without the Student role, establish
and verify canonical links and exact User Permission scopes, and only then activate the role.
Audit every enabled Student account for missing, stale, extra or cross-student rules. Administrator
removal of all User Permission records reintroduces the framework's permissive fallback; native
configuration is not an immutable fail-closed policy against a malicious administrator. No production
provisioning implementation is being claimed or built in this phase.

## Expanded regression coverage

`runtime_isolation.py` exercises real REST v1/v2, lists, generic and Education RPCs, related
attendance/results/invoices, unauthorized writes (requiring PermissionError rather than a CSRF
rejection), unchanged target data, guest/private-file access, cross-site SID replay and a source-only
record absent from the restored database. It also probes signup/sharing and unprovisioned users.

`runtime_browser.mjs` uses native login forms, the actual Education fee page, desktop/mobile
viewports, tampered URL/local-storage student selection, authenticated browser REST/RPC/file
requests, and deliberate cross-site cookie replay. No UI interception or mocked ERP authorization
is used. Playwright 1.58.2 is integrity-checked; its Chromium version is recorded in evidence.

Nginx permits only the two synthetic Host names, overwrites client `X-Frappe-Site-Name`, serves
only public `/assets/` statically, and routes private files through Frappe. No production TLS,
public-host deployment, proxy trust chain or multi-company tenancy guarantee is implied.

Run `34779173567` exposed harness/browser prerequisites: the login locator matched two buttons,
and the portal document did not supply the CSRF token expected by the HTTP harness. The locator
and dangling browser promises were corrected. Token absence remains an explicit failing check;
independent authorization probes now continue without inventing a token or disabling CSRF checks.
The cause and impact of the portal token result require the follow-up report, not assumption.

## Remaining critical gates

- Final outcomes of the broadened browser/API/hardening probes and any required remediation.
- Student/guardian/staff/HR/payroll role combinations; list/report/export/print and realtime events.
- Provisioning, account relinking, permission drift/revocation, and hardened-policy backup/restore.
  The original successful restore preceded permission hardening; it does not prove ACL recovery.
- CSRF/session baseline, production proxy/TLS/cookie configuration and frontend advisories.
- Existing upstream suites, payroll/refunds/legacy Fees experiments and controlled version upgrade.

Passing the restricted ten-check experiment does not clear these gates. The 57 recorded frontend
advisory entries remain unresolved. All failed evidence is retained under `evidence/phase-2/hosted/`.

## Architecture decision: generic guard extension (under runtime qualification)

Run `34779652716` confirmed four authenticated portal documents with an assigned but empty
CSRF token. It also passed the source-site native policy's read/write/file/sharing/signup and
HTTP tenant-boundary checks. API v2 returned 403 but uses `errors[].type`, not v1 `exc_type`;
the assertion is corrected to verify the native v2 error shape, not relaxed to accept any error.
Alpha's real portal and browser API/file checks passed; Beta encountered a harness navigation
race after login. The runner now waits for the native login redirect.

Native configuration cannot initialize website session CSRF tokens or make the framework's
missing-User-Permission fallback fail closed. Therefore `apps/foundation_security` is a minimal
**generic security extension**, not a TOEFL product app. Supported `on_session_creation` and
`auth_hooks` initialize the native token and validate exact native Student/Customer rules on
login and authenticated requests. It adds no schema or parallel identity/finance authority.
Its version and source hashes are recorded by the runner. Per-user document shares also cause
a denial pending review. Administrator remains explicitly trusted.

The extension requires disabling website HTML caching because Education embeds the session
token directly in HTML; Redis application caching/workers remain enabled and tested. Both
synthetic sites receive the native settings and extension. Regression probes remove a real User
Permission as Administrator, require the existing Student session and fresh login to fail closed,
restore it through the normal API and require access to recover. Missing/invalid CSRF tokens
must be rejected while a valid-token self-profile control succeeds. This is not yet a passed
remediation until a hosted report verifies it; historical failures remain immutable evidence.

# Foundation security qualification

## Subsequent dependency and operations qualification — 2026-09-14

**REJECT remains current.** See [final qualification review](foundation-final-qualification.md)
and [acceptance ledger](foundation-production-acceptance-ledger.json). Hosted frontend
comparison **34823793929** reduces 57 baseline matches to 23 in an isolated candidate
(35 removed, one newly applicable); the candidate is **not adopted** and both audits fail.
Native run **34823345078** passes controlled Gunicorn/RQ restart and **47 post-restart
isolation checks**, plus 54 readiness / 6 Guardian browser / 4 realtime / 33 upgrade checks.
Actual scheduler Complete is observed at 234.2s. Full public deployment, data-store/host
recovery, broader business/security coverage and dependency acceptance remain open.
The detailed checkpoints below remain retained evidence, not newer production approvals.


## Status and scope

**Security gate: NOT PASSED. Product implementation: NOT AUTHORIZED.**

### Final targeted hardening evidence — 2026-09-14

**34812299091 / ff39ae3883ca51b46be96235b8ecf13afbd331b6** verifies the **0.2.1** extension,
with all installed source hashes matching the checkout. **54 readiness checks, six Guardian
browser checks and four realtime checks pass.** A Guardian-owned private File attached to
the unrelated Student is denied through HTTP download, REST metadata, RPC and native
download/content methods; authorized controls still work and content hashes match.
Live Guardian scope drift/recovery, native payroll read and seven Salary Register ACLs pass.
Real RQ task ownership and native session revocation continue to deny unauthorized delivery.

Both requested prior runs **34809817009** and **34810723925** are preserved failures of
immutable-owner fixture setup, not accepted ownership-boundary evidence. The corrected
fixture uses normal actor-owned insertion and Administrator attachment, without validation
bypasses. Scheduler-driven Complete is proven in 34810723925 and the final follow-up.
GitHub access is restored; exact report/commit/run verification is retained.

**Full security and production acceptance remain REJECT / NOT PASSED.** The final workflow
still fails on 57 advisory entries; scoped source/build classifications are not waivers.
End-to-end ZIP/export/print combinations, broad mixed-role usability and public realtime
proxy/origin/cluster/direct-emit compatibility remain outside current approval. See
[hardening remediation](foundation-hardening-remediation.md) for reproducible evidence
and explicit boundaries. Local 44 Python tests and Node regression also pass.

### Previous verified Student guard checkpoint — 2026-09-14

GitHub access is restored. The exact sanitized Check for **34781717183** at `956fd31`
has been retrieved and retained in `evidence/phase-2/hosted/runtime-34781717183.json`.
The corrected generic guard passed **10 restricted HTTP checks, 47 expanded isolation
checks, 5 Chromium checks, and the post-install cache/RQ probe**. The overall run failed
solely because the deliberately retained unsafe baseline failed. This is scoped runtime
proof for the enumerated controls, **not full security approval**. All 26 local helper tests pass.

The earlier **34781217903** login failures (Administrator 400, Students 403) were genuine
extension defects. Moving token generation after native HTTP CSRF validation and allowing
only native User self-profile shares corrected them; the later hosted checks verify those
corrections. Tokenless unsafe legacy writes and other inherited/global shares remain denied.

### Hardened recovery and upstream suites — verified

Run **34803138631** at `35aed363e4da79fca4f483e8d53866918547ed03` completed successfully
in 10m5s. Check **103851249930** was retrieved, its exact compact-text SHA-256 verified,
and all **57,156 bytes** retained in `evidence/phase-2/hosted/runtime-34803138631.json`.

- Source: restricted HTTP **10/10**, expanded isolation **47/47**, Chromium **5/5**,
  and cache/RQ probes passed.
- A fresh hardened SQL/files backup restored to a third distinct database/site. Native
  encrypted Password-field decryption passed after explicit site-key recovery. No source
  database credentials were copied into destination configuration.
- **7/7 recovery invariants** passed: relationships, submitted records, public/private
  file hashes, app/settings/native User Permissions, referenced-Student deletion denial,
  and presence then native revocation of the copied live session.
- Separate HTTP proof confirmed that captured SID still authenticates on the source and
  is denied on recovery. **47/47 isolation checks** then passed on recovery, without
  re-provisioning its native permissions or singleton security settings.
- Unchanged upstream `test_user_permission` and `test_docshare` suites passed on their
  own fourth, Frappe-only site, reporting **10 and 15 tests run**. Declared upstream test
  dependencies installed and `uv pip check` passed. Detailed skip accounting is not in the
  compact report; the full artifact download still fails at its blob host in this sandbox.
  No claim is made that these two modules cover all upstream security.

Earlier recovery failures remain retained. **34801558069** and **34801702600** assumed
an encryption key already existed. **34802126407** proved encrypted recovery but used
`db.exists` against `Sessions`, a framework SQL table with no `name` column. The pinned
`frappe/database/mariadb/framework_mariadb.sql` defines its native `sid` index; the corrected
probe uses a bound-parameter SQL count on `sid`. The later successful run verifies the
correction and actual copied-session revocation, rather than removing that assertion.

The hardened profile explicitly does not execute the unsafe baseline and references its
historical failed evidence. The forensic profile retains it. Neither profile can turn the
baseline failure into a pass or automatically clear the broader security/Phase 2 gates.

Earlier packaging failures (`34780307591`, `34780667272`) are retained: Bench required a
standalone local Git app root and its empty `patches.txt` discovery manifest. The runner
exports exact owned app files into a disposable same-branch Git snapshot and uses supported
Bench registration; it does not hand-edit apps.txt or bypass installation checks. Superseded
pending runs `34780366068` and `34780432921` were cancelled by GitHub concurrency before
execution; they are neither passing nor failing qualification evidence.


This is a synthetic-data qualification of the pinned upstream bundle, not a production
hardening guarantee. GitHub access has recovered. Run `34778602344` is now retrieved and
verified against commit `43d4287bc63b47a2000cdb44a38f83fa322b9dc6`.

No TOEFL-specific app, schema or workflow was introduced. The remediation uses native configuration, User Permission records and the generic
qualification extension, with no upstream core edits. The browser
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
The later 34781717183 report verifies the corrected token behavior; this earlier failure remains historical evidence.

## Remaining critical gates

- Full Student/guardian/staff/HR/payroll role combinations and list/report/export/print paths.
- Full provisioning/account relinking and legitimate mixed-role sharing behavior beyond the
  enumerated fail-closed scope/revocation tests. Guardian flows remain unqualified.
- Realtime event authorization, client/proxy cache and session-switch behavior, production
  proxy/TLS/cookie/security-header configuration, and frontend dependency remediation.
- Other high-value upstream suites, payroll/refunds/legacy Fees experiments, accessibility,
  representative performance, scheduled task execution and controlled version upgrade.

The **57 frontend advisory entries remain unresolved**. The successful hardened profile
explicitly reports security, Phase 2 and product gates **false**. All failures are retained.
It is not a production approval or a full-role authorization certification.

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
Its version and source hashes are recorded by the runner. Non-self-profile per-user document shares cause
a denial pending review. Administrator remains explicitly trusted.

The extension requires disabling website HTML caching because Education embeds the session
token directly in HTML; Redis application caching/workers remain enabled and tested. Both
synthetic sites receive the native settings and extension. Regression probes remove a real User
Permission as Administrator, require the existing Student session and fresh login to fail closed,
restore it through the normal API and require access to recover. Missing/invalid CSRF tokens
must be rejected while a valid-token self-profile control succeeds. This is not yet a passed
remediation until a hosted report verifies it; historical failures remain immutable evidence.

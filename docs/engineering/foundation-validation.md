# Foundation validation — Phase 2 checkpoint

## Current hosted-runner checkpoint — 2026-09-14

**ACCEPT WITH CONDITIONS — retain the architecture for further qualification only.**
Phase 2 has **not** passed. Product implementation and deployment remain unauthorized.
This section supersedes the local-environment runtime status in the historical assessment below;
its source analysis, unresolved frontend advisories and unexecuted acceptance requirements remain relevant.

### Proven on the controlled runner

- Branch-only GitHub-hosted Ubuntu 24.04 runner, image `20260907.300.1`, with working
  checksummed Python downloads and digest-pinned Docker MariaDB/Redis services.
- Run [34776186463](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/34776186463)
  at `b3dc8c2e92e8284d594239adf88e834c501f08f3`: clean site creation, all five app installs,
  dependency consistency, migrations twice, and full asset build passed (59 recorded stages).
  This was an **installation-only** success, not an accepted ERP foundation.
- Observed runtime: Python 3.14.7, Node 24.21.0, Yarn 1.22.22, MariaDB 11.8.9,
  Redis 8.6.6, Bench 5.31.0, Docker 28.0.4 and Compose 2.38.2.
  Imported app versions subsequently confirmed Frappe 16.33.1, ERPNext 16.34.2,
  Education **16.0.1** from release tag **16.1.0**, Payments 0.0.1 and HRMS 16.18.1.
  Exact source revisions and hashes remain in the version matrix.
- Run [34777832562](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/34777832562)
  completed native setup-wizard stages, created a company with 97 accounts and a branch,
  academic year/term/program/course/group/admission, and an Instructor linked to an Employee.
  Two Applicants became Students, each with Customer and enrollment relationships and group membership.
  Existing portal Users were **not automatically linked** to the Students; the probe explicitly
  configured the upstream Student `user` field as an operator would.
- A course/group Assessment Plan was created with zero Students. A Result without a Student
  was rejected (`StudentNotInGroupError`); an Applicant identifier in its Student link was rejected
  (`LinkValidationError`). These are limited runtime boundary observations, **not placement implementation**
  or proof of versioned/pre-enrollment attempts.

### Historical baseline: lifecycle/recovery passed, isolation failed

Run [34778224918](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/34778224918)
at `ff29395` completed all nine business checks. Attendance and Assessment Result were submitted
(score 75, grade B); a 100 USD fee with 10% discount produced a 90 USD invoice, settled by
Payment Entry, with zero outstanding and four balanced GL rows (180 debit / 180 credit across
invoice and payment). Public/private attachments were created and hashed.

A real database/files backup was restored into a **distinct clean database/site**, migrated,
and verified for Student/Applicant/Customer/enrollment links, submitted records and both file hashes.
Administrator login and Student HTTP reads worked on both sites. Ten canonical tables were
inspected for columns/indexes/audit fields; referenced Student deletion was rejected with
`LinkExistsError`. MariaDB reported `utf8mb4` / `utf8mb4_unicode_ci`.
Cache round-trip and a real RQ job passed (1.004 seconds observed); Engine.IO 4 handshake passed.
Scheduler process liveness is **not** proof of scheduled-task execution or realtime event isolation.

**Blocking server-side isolation finding:** with the tested native Student role and explicit
Student/user links, but without additional User Permission records:

- Alpha could read Beta's Student document through generic REST (HTTP 200, target name verified).
- Beta could download Alpha's private attachment (HTTP 200, exact file hash verified).
- The Education portal context RPC correctly denied the other Student (HTTP 403).

These were synthetic owned records on loopback, not production data. The overall run correctly
failed. Portal-specific checking does not secure other server entry points. The baseline is retained;
a separate native Student/Customer User Permission configuration experiment subsequently passed
identical HTTP assertions. It cannot erase the baseline failure or establish a full role matrix.

### Failures preserved, not bypassed

| Run | Failure / interpretation |
|---|---|
| 34776065793 | Bench expected a host Redis executable during config generation. Supported external-Redis options corrected the harness; real Redis remained required. |
| 34777102178 | Direct probe ran from Bench root rather than `sites`, so Frappe logging resolved the wrong directory. Harness context corrected; no controller ran. |
| 34777452072 | Company creation before onboarding lacked standard `Transit` Warehouse Type. Corrected by running upstream setup completion, not a placeholder or ignored link validation. |
| 34777832562 | Attendance rejected the missing Company default Holiday List. Earlier six business checks passed. A normal institution calendar corrected this in run 34778224918; no holiday validation was disabled. |

Sanitized reports, including failures, are retained in `evidence/phase-2/hosted/`.
Later harness revisions are not evidence until their own hosted report is recorded.

### Latest verified integration checkpoint

GitHub access is restored. **34781717183** (`956fd31`) passed the corrected generic guard's
**10 restricted HTTP, 47 expanded isolation, 5 Chromium and secured cache/RQ checks**.
Its overall failure preserves the unsafe baseline; it does not indicate failure of those
corrected checks. The exact hosted report is retained. **26 local helper tests pass**.
See the [security report](foundation-security.md) for scope and earlier failures.

Run **34801558069** (`3f927a5`) repeated the guarded passes and restored hardened SQL/files,
then failed on a harness assumption that an encryption key already existed. The retained
failure does not prove policy/session recovery. **34802126407** (`eb09b39`) corrects this by
creating a native encrypted Password fixture before backup and verifying decryption afterward;
it also includes unchanged upstream User Permission/DocShare suites on a dedicated test site.
The corrected result is **not yet verified**. Security and Phase 2 gates remain false.

### Security continuation: connection restored, native remedy verified

GitHub access recovered. Run **34778602344** at `43d4287` was retrieved and its
native User Permission experiment verified: all ten restricted checks passed while the
original two isolation failures remained recorded and the run remained failed.

See [foundation security qualification](foundation-security.md) for the root cause,
exact native controls, threat-model limits and new regression matrix. Run **34779652716**
passed the expanded source-site Student/result/attendance/invoice read controls, lists,
write denials, private files, signup/sharing restrictions and HTTP cross-site checks.
It found missing portal CSRF tokens; API v2 error-shape and browser redirect-race harness
issues were also retained and corrected, not mistaken for permission disclosures.
Alpha's actual Chromium portal/fees and browser API/file isolation checks passed.

A minimal generic `foundation_security` Frappe extension is now under qualification.
It initializes native session CSRF tokens and denies Student requests with missing,
expanded or ambiguous native identity/permission scopes. It adds no domain schema,
TOEFL-specific app, product UI or scoring. Supported hooks are used; upstream core
remains untouched. **26 helper tests pass**, including guard tests; these are not a
substitute for hosted integration results. Security and Phase 2 gates remain false.

### Qualification method and reproduction

Use `.github/workflows/foundation-runtime.yml` on `arena/01a09bf3-tofel-house-erp`:

```sh
gh workflow run foundation-runtime.yml --ref arena/01a09bf3-tofel-house-erp -f profile=hardened
# Historical unsafe-baseline reproduction: use -f profile=forensic instead.
gh run list --workflow foundation-runtime.yml --branch arena/01a09bf3-tofel-house-erp
# Substitute the returned run ID:
gh run watch RUN_ID --exit-status
```

The workflow qualifies services, checks exact source/input hashes, installs the pinned native
Bench environment and containerized MariaDB/Redis, and creates disposable synthetic sites.
Native Bench plus container services is the **proven CI qualification method**; a full application
Docker image and interactive OS/WSL development experience remain unqualified. Do not run the
restricted synthetic harness against an existing institution site.

MariaDB/Redis ports are loopback-only; HTTP and realtime probes also use runner loopback.
Passwords are generated per run, masked and redacted; no site configs, backup databases,
private files or credentials are uploaded. Sanitized JSON is published through a Checks API
entry and sanitized evidence artifacts are retained for 14 days. Child processes, containers
and temporary site storage are cleaned up at job end. A new workflow run is the clean reset.
The scripts' connection context is the normal Bench `sites` working directory, not a custom
installed application or an upstream core modification.

### Remaining gates / interpretation

The authored harness includes fee/invoice/payment/ledger, files, real backup/restore,
DB inspection, cache/job, HTTP login/Student isolation and transport-handshake probes.
**An authored test is not a passed test.** Only the explicitly enumerated lifecycle/recovery/cache/HTTP checks above have now passed;
the two baseline isolation denials failed. Full staff/HR/payroll authorization, refunds/legacy Fees overlap,
upstream regression suites, controlled version upgrade, browser UI/accessibility/performance,
scheduler task execution and realtime event authorization still need evidence.
The 57 frontend advisory entries (27 high, 26 moderate, 4 low) remain unresolved.
Repeated same-version migrations are not version-upgrade proof. Company/Branch is not a tenant boundary.

No TOEFL-specific app, schema, scoring, placement, lifecycle, finance, HR or UI was implemented.
Main remains `9eccff957cadf036a3ac6f8208540a110148e67b` (remote reconfirmed during this continuation).
The detailed 23-category analysis below is retained as the **historical local checkpoint**,
not a claim that the now-proven hosted installation is still blocked.

---

## Historical local-environment assessment (before hosted qualification)

Date: 2026-09-13 UTC · Baseline: `d77085b` · Branch: `arena/01a09bf3-tofel-house-erp`

## 1. Decision and limits

**FOUNDATION STATUS: ACCEPT WITH CONDITIONS**

This means **retain the candidate architecture for continued qualification**, not approve the bundle for product implementation or deployment. **Phase 2 is incomplete; its runtime gate has NOT passed. No backend application bundle has been validated.** Environment failures are not evidence that the architecture is unsuitable, but neither source compatibility nor the successful frontend build establishes a working ERP.

**The hard stop remains in force:** no placement, scoring, custom lifecycle, billing, HR, branding or UI redesign work may begin. English is the canonical product, code, API and documentation language. This supersedes Phase 1's proposed Persian/RTL qualification direction; no RTL changes were made.

What actually succeeded:

- Refreshed upstream releases and verified six clean source checkouts at exact release commits, including Education's **release** rather than its previously reviewed branch head.
- Installed Bench **5.31.0**, uv **0.11.6**, Node **24.21.0**, and Yarn **1.22.22** in an isolated lab. Bench's tool environment passes `pip check`; this says nothing about Frappe's dependencies.
- Installed Education's frozen frontend dependency tree and built its production assets on Node 24.21.0. Repeated from removed `node_modules` and a fresh Yarn cache with the original lockfile unchanged.
- Verified all **286 tarballs** against upstream lock integrity values when using npm as transport for a Yarn offline mirror.
- Queried npm advisories for **255 installed package names**; **57 advisory entries across 21 packages** were returned (27 high, 26 moderate, 4 low). This security gate **fails pending triage/remediation**, not “passed with warnings.”

What did not succeed:

- Debian repositories could not be reached over HTTP or HTTPS, preventing MariaDB, Redis, native libraries and Docker package installation.
- The selected CPython **3.14.7** runtime asset could not be downloaded: GitHub's signed release-asset redirect ended in EOF, producing zero bytes. The earlier uv attempt at 3.14.4 also failed. Certificate verification was never disabled.
- Docker is absent; its static download and registry endpoints also fail TLS connection establishment. No container was built or run.
- **Zero Frappe sites, companies, applicants, students, employees, invoices, payments, assessment results or payroll records were created.** No DB, backend login, portal/API authorization, workflow, worker, scheduler, realtime, backup, restore or migration test was run. These are blocked, not passed or silently skipped.

Machine-readable records: [version matrix](foundation-version-matrix.json), [test results](foundation-test-results.json). Evidence is under [evidence/phase-2](evidence/phase-2/). The final status is conditional because qualification can continue; the precise success standard in the Phase 2 request has **not** yet been achieved.

## 2. Reconfirmed repository and release provenance (2A–2B)

The working tree was clean at `d77085b`. README, `initial-assessment.md` and `upstream-review.json` were re-read. No upstream apps or infrastructure had been installed into the project. The requested branch spelling included `toefl`; the session is fixed to the existing **`tofel`** branch listed above. No product branch was created/switched, no `main` edits and no history rewriting occurred.

| Component | Exact candidate | Exact source commit | Actual validation |
|---|---|---|---|
| Frappe | v16.33.1 | `988e54f3c4c291e2077a83809663f123731abe76` | Source verified; not installed |
| ERPNext | v16.34.2 | `4048fb70e14d1843956fcdabb7c3cca75a1cbcdd` | Source verified; not installed |
| Education | v16.1.0; source reports 16.0.1 | `93bc7075753369457919720690f80c6d2207b5f2` | Source and standalone frontend build verified; backend not installed |
| HRMS | v16.18.1 | `a4768b441cff346def505e27f2a2229ee1e05b9b` | Source verified; not installed |
| Payments | Source version 0.0.1; no published release returned | `cca07d9f9392e2ea0e521c5975151db9e4b6c321` | Required-path investigation only; not installed |
| Bench | v5.31.0 | `f21f11793872705560e710b2bda69934c9c34011` | Released source verified; PyPI CLI runs |
| frappe_docker | v3.2.2 | `3061850feface8fbbad15b5dc08a110c596107cb` | Released recipes inspected; no Docker runtime |
| Python | 3.14.7 | Peeled CPython tag in matrix | Selected artifact fetch failed; host remains 3.11.2 |
| Node.js | 24.21.0 | Peeled Node tag in matrix | CLI + Education frontend install/build verified |
| MariaDB | 11.8.9 | Peeled MariaDB tag in matrix | Candidate only; no engine installed |
| Redis | 8.6.6 | Redis tag commit in matrix | Candidate only; no server installed |
| Yarn Classic | 1.22.22 | npm integrity in matrix | CLI + frozen offline installation verified |

The JSON matrix includes source URLs, full runtime-source SHAs, manifest/lock hashes, selection reasons, unresolved image/dependency pins, and a null `approved_runtime_bundle`. **It is not an application environment lock or a production image manifest.**

### Why these candidates, and what is not proven

- These were the newest non-prerelease **v16** Frappe/ERPNext/Education/HRMS releases returned in the refreshed release lists. The v15 entries returned by “latest release” do not define a compatible v16 bundle. No arbitrary develop branches were chosen for the apps.
- ERPNext declares Frappe `>=16.21,<17`; Education declares Frappe `>=16,<17` and requires ERPNext in hooks; HRMS declares Frappe/ERPNext `>=16,<17`. The source versions satisfy these ranges. **The declarations are not installation proof.**
- Education's release commit differs from Phase 1 branch head `22e0910...`. Both report 16.0.1 in Python despite release tag v16.1.0. SHA, not the application version string, identifies the candidate. Any newer branch fix requires separate review and qualification.
- Effective Python requirement is Frappe `>=3.14,<3.15`; Node must be >=24. Selected Python 3.14.7 and Node 24.21.0 stay on these lines. Initial experiments with uv's automatically selected Python 3.14.4 and Node 24.14.0 are recorded as superseded, not quietly treated as the final bundle.
- The pinned Docker recipe defaults to Python 3.14.2 and Node 24.13.0 build arguments; a future image must explicitly select the matrix's candidate versions rather than silently keep those defaults. It uses MariaDB 11.8 and Redis 8.6 moving image tags. Latest observed patches **11.8.9 / 8.6.6** are candidates; image digests have **not** been fetched. MariaDB 12.3.3, Redis 8.10.1/8.8.2 and Node 26.8.2 were not selected merely for being newer lines. Education CI's MariaDB 10.6 differs from this recipe; compatibility must still be tested.
- Education's release billing module imports Razorpay and a helper in ERPNext's payment-entry **test module**. Its CI installs Payments, whose manifest supplies Razorpay. Whether all intended non-gateway paths can run without Payments is **not runtime-established**; do not mislabel it either definitely optional or fully validated. Pin its explicit source revision for the dependency experiment. No real payment provider is configured.
- “Supported” here means release/tag and manifest/deployment evidence, not an upstream support contract, EOL assurance or guarantee for this combination. Full Python dependency resolution, system-library pins, OCI digests, full-stack SBOM and license/advisory review remain outstanding. Redis distribution licensing and GPL-covered application distribution need owner/legal review.

Source provenance and unchanged input hashes: [source-verification.json](evidence/phase-2/source-verification.json).

## 3. Installation strategy and clean environment (2C–2E)

### Evidence-based comparison

| Path | What was attempted | Result | Decision |
|---|---|---|---|
| Native Bench | Fresh Python tools venv; pinned Bench; attempted OS dependencies and compatible Python bootstrap | Bench CLI and standalone Node frontend work. Apt/Python downloads block the app/site prerequisites | Keep as diagnostic/local alternative; **not a verified full-stack development environment** |
| Docker-based | Reviewed stable upstream recipe; attempted to install Docker through apt; probed official static download and registry | Docker CLI/daemon/Compose unavailable; download endpoints fail TLS | **Conditional canonical target:** upstream pinned development/custom-image environment with Bench inside; not yet runnable or qualified |

A containerized canonical target is recommended because this attempt demonstrated real host/toolchain drift (Debian's host Python/Node differ from Frappe requirements), and the upstream recipe supplies separated app processes and persistent storage that can be reused in CI/deployment. That is a design recommendation, **not a measured runtime comparison**. No claim is made that Docker would repair this sandbox's network. If the approved developer environment cannot provide Docker, rerun native qualification rather than add a custom source-built database/Python toolchain merely to evade the lab's constraints.

**There is intentionally no untested compose file, pretend one-command ERP installer, placeholder application or green compatibility CI job in this commit.** Engine/Compose versions, images and native package snapshot must be pinned when a full environment can actually be exercised.

### Host and operational requirements

Observed lab: Debian GNU/Linux 12, x86_64, approximately 4 GiB RAM and 19 GiB free disk at start; sudo available; no pre-existing Bench site, MariaDB, Redis or Docker. Work stayed under `/home/user/foundation-lab`, outside the product Git checkout. OS package installation failed without creating services. The temporary HTTP→HTTPS apt-source change was reverted after diagnosis.

Proposed onboarding budget, **not benchmarked**: Linux x86_64 or WSL2 with Linux containers, 4 vCPU, 8 GiB memory and 30 GiB free disk for all apps/assets/test sites. Other architectures need independent validation. WSL users should keep the bench on the Linux filesystem, not a Windows-mounted source path. macOS/ARM and Windows-native Bench are not validated here.

Target topology (not running): Nginx frontend → Gunicorn/Frappe backend; Node Socket.IO; short/default/long workers; scheduler; MariaDB; Redis cache/queue; persistent site public/private files and DB storage. Proposed local HTTP 8080 for container frontend or 8000 for native Bench; backend 8000, realtime 9000, database 3306 and cache/queue remain internal. Do not expose MariaDB or Redis to the browser/public host. Exact compose port mapping is still unqualified.

For an Arena preview, the public frontend must bind `0.0.0.0`, accept the assigned preview hostname and proxy same-origin API/websocket traffic. No browser-side localhost backend calls. No preview was started because no functioning site exists; a static portal disconnected from its backend would be misleading.

Target DB settings: MariaDB, utf8mb4/utf8mb4_unicode_ci, separate site database/user, config and encryption key. No actual DB schema, credentials, volumes or site configuration exist. Future `db_host`, `db_port`, database credentials, Redis endpoints and site routing must be set through protected site/common config or container secrets. Use unique synthetic-site credentials, keep them out of logs/Git, and separate admin provisioning from regular role tests. No default production passwords, ignored CSRF or permission bypasses.

Reset currently means choosing a **new dedicated lab directory**, leaving the product checkout/history intact. Preserve evidence before clearing lab-only caches/artifacts. There are no database/container volumes to reset yet. Once provisioned, use explicitly named validation sites/volumes and rehearse their reset; do not use global Docker pruning or delete production sites to make a test pass.

### Reproduce the checks that actually ran

These commands reproduce the **tooling/frontend experiment**, not a runnable ERP. Set `REPO` to this repository and `LAB` to a fresh directory **outside** it. Required: Python 3.11 for these utilities, Git, npm and HTTPS access to GitHub source/PyPI/npm. Bootstrap npm was 10.9.8 on host Node 22.22.3; all Education install/build commands subsequently used Node 24.21.0.

```bash
mkdir -p "$LAB/sources"
python3 -m venv "$LAB/tools"
"$LAB/tools/bin/pip" install -r "$REPO/docs/engineering/evidence/phase-2/bootstrap-tool-versions.txt"
npm install --prefix "$LAB/node" --no-audit --no-fund node@24.21.0 yarn@1.22.22
export PATH="$LAB/tools/bin:$LAB/node/node_modules/.bin:$PATH"
bench --version
node --version
yarn --version
"$LAB/tools/bin/pip" check

git clone --depth 1 --branch v16.1.0 https://github.com/frappe/education.git "$LAB/sources/education"
test "$(git -C "$LAB/sources/education" rev-parse HEAD)" = 93bc7075753369457919720690f80c6d2207b5f2

# Direct frozen install was attempted first and failed on registry.yarnpkg.com.
# --registry alone did not replace the resolved tarball URLs in the upstream lock.
python3 "$REPO/tools/foundation/seed_yarn_mirror.py" \
  "$LAB/sources/education/frontend/yarn.lock" "$LAB/yarn-mirror"
printf 'yarn-offline-mirror "%s"\n' "$LAB/yarn-mirror" > "$LAB/yarnrc"
cd "$LAB/sources/education/frontend"
yarn install --offline --frozen-lockfile --non-interactive \
  --cache-folder "$LAB/yarn-cache" --use-yarnrc "$LAB/yarnrc"
yarn build

# This command exits 1 when advisories exist; record and investigate that result.
python3 "$REPO/tools/foundation/audit_frontend.py" node_modules \
  --output "$LAB/frontend-advisories.json"
```

`--no-audit` above only prevents an implicit npm bootstrap audit; the separate explicit Education dependency advisory check was executed and **failed**. It is not a security gate exemption. The freeze is a record of tooling versions, not a hash-locked full-stack dependency supply chain.

The mirror helper downloads only matching npm tarball paths, validates lockfile integrity **before writing**, and fails on unsupported entries or mismatches. It does not rewrite the lock, skip package scripts, use `--ignore-engines`, change dependency versions or disable TLS. A fresh-cache repeat succeeded. The build regenerated one tracked upstream generated `education/public/frontend/index.html`; its hash was recorded and that generated tracked file restored afterward. Source/lock/controller inputs remain unchanged.

Read-only preflight and collector tests:

```bash
python3 "$REPO/tools/foundation/preflight.py" --method native --output "$LAB/native-preflight.json"
python3 "$REPO/tools/foundation/preflight.py" --method docker --output "$LAB/docker-preflight.json"
python3 -m unittest discover -s "$REPO/tests/foundation" -v
```

Both preflights currently exit **1**. Collector/mirror unit tests pass; these are tests of validation utilities, **not ERP tests**. Bootstrap command failures and remediation are recorded in [test results](foundation-test-results.json) and the selected logs. Signed GitHub download query parameters were redacted rather than persisted as credentials.

## 4. Functional, lifecycle and placement gates (2F–2H)

**Status: BLOCKED — no site/database.** No capability in this section is claimed working. Existing source relationships remain hypotheses to exercise, not runtime findings. The minimal fixture set must include an institution/company, branch, program, course, academic year/term, cohort/group, Employee-linked Instructor, approved Applicant, Student, enrollment, fee schedule/invoice/payment, attendance and assessment/result.

The next controlled lifecycle must capture actual document IDs and before/after states at every step:

1. Create Student Admission/intake and Student Applicant for a real program/year; approve through the supported path. Record whether source or workflow enforces status, not just whether a button is visible.
2. Call the supported applicant enrollment operation, recording **exactly when Student and Program Enrollment are created**. Verify Applicant → Student → Customer links and ensure retry cannot produce a second identity. Do not create a Student to accommodate placement testing.
3. Submit canonical Program Enrollment and verify Course Enrollment side effects, fee behavior and membership in a Student Group/Batch. Confirm Instructor → Employee and Room/schedule relationships.
4. Create and submit Attendance, Assessment Plan and Assessment Result in the proper course/group context; verify grades and membership validation server-side. Duplicate and cancelled/amended result cases need separate observations.
5. Generate the selected invoice path, receive/allocate payment and reconcile receivable/ledger balances. Verify submitted/cancelled statuses and academic history after corrections.

### Placement boundary: recommendation, not a completed experiment

| Question | Source indication at selected Education release | Required runtime proof |
|---|---|---|
| Can an assessment exist before Student creation? | A Plan can describe a course/group assessment; Result requires Student. “Assessment” must distinguish Plan from Result | Create Plan independently, then attempt Result without Student; record actual validation response |
| Can Applicant own normal Assessment Result? | Result's student Link targets Student, not Applicant | Attempt Applicant identity in that Link; verify rejection without bypassing validations |
| Independent of Course enrollment? | Plan requires Course/Student Group; Result validates membership | Probe absent Plan/course/group and membership without Course Enrollment; do not assume a formal enrollment invariant beyond actual controller behavior |
| Versioned attempts? | Document amendment/submission and duplicate plan/student checks are not a versioned placement/rubric/retake model | Test repeat results, amended results, changed grading rules and history; distinguish attempts from document versions |
| Remain attached to Applicant, later link Student? | No native Applicant-owned result shown by selected schema; a future separate Link can preserve provenance without replacing academic authority | Verify actual Link metadata/permissions and migration in an approved future extension; **no placement DocType built now** |

**KEEP** enrolled academic Assessment Plan/Result authority. **EXTEND** canonical admissions/enrollment handoff only after runtime tests. **BUILD** a separate applicant placement aggregate if these runtime boundary tests confirm the model mismatch. This preserves the Phase 1 direction but does not turn its unexecuted tests into proof. No scoring, level, CEFR or recommendation implementation exists.

## 5. Finance authority (2I)

**Status: BLOCKED — no invoices, payments or GL entries created. No definitive experimentally validated billing decision is possible yet.**

Provisional choice remains **Education Fee Schedule → ERPNext Sales Invoice → Payment Entry → ERPNext ledgers**, using ERPNext Customer linked from Student. ERPNext owns financial truth; an educational fee schedule is not a second general ledger. Selected-source evidence: Education `fee_schedule.py`, `program_enrollment.py`, legacy `fees.py`, and ERPNext invoice/payment/GL controllers.

The legacy Fees controller and invoice generation both still exist. This is a reason to test duplicate obligations, not a claim that a duplicate has already been observed. Keep legacy code upstream but do not adopt both paths for the same obligation.

Required experiments before a definitive recommendation:

- Generate an invoice from a fee obligation; verify Customer, Company, receivable account, posting date/currency, outstanding balance and balanced GL entries.
- Generate legacy Fees for the same logical obligation on an isolated fixture; determine whether upstream prevents double billing and record both ledgers. Roll back/reset only that synthetic experiment after preserving evidence.
- Partial/full payments, allocation, overpayment, cancellation and retry: match Payment Entry references, invoice outstanding and GL/payment-ledger balances; do not rely on a displayed “paid” flag.
- Discounts through supported invoice pricing/discount fields: verify net obligation and taxes; no parallel discount ledger.
- Refund through supported return/credit-note and payment-out flow: verify balances, references and reversals; do not model refunds merely by editing an invoice total or Student balance.

No real gateway secrets, provider requests, custom receipts or billing workflows were added. The billing module's test-helper import and privileged operations need runtime/import and security qualification before enabling online payments.

## 6. HR/payroll decision (2J)

**Status: source ownership established; execution BLOCKED.** HRMS is technically justified for the requested full attendance/leave/payroll scope, not because of its feature count. It is not required just to hold Employee/Department or link a teacher.

| Scope | Source owner at selected releases | Recommendation | Runtime state |
|---|---|---|---|
| Employee, Department | ERPNext setup DocTypes | KEEP existing master | Not installed |
| Instructor/teacher link | Education Instructor.employee | EXTEND only institute-specific teaching data later | Not executed |
| Employment Type, employee Attendance, Leave Application | HRMS HR DocTypes | REQUIRE HRMS for these requested workflows | Not executed |
| Salary Structure, Salary Slip, Payroll Entry | HRMS payroll DocTypes | REQUIRE HRMS for payroll | Not executed |
| Salary Component/deductions; Additional Salary/bonuses | HRMS payroll DocTypes | KEEP upstream engine; validate local policy later | Not executed |
| Payroll accounting | HRMS Payroll Entry integrates ERPNext Journal Entry | KEEP one accounting authority | No journal created |
| Duplicate employee, payroll or salary ledger | Would compete with existing authority | DO NOT USE / AVOID | Not built |

Before installing HRMS, record which relevant DocTypes/controllers exist in an ERPNext+Education test site; then install pinned HRMS, migrate and exercise attendance, leave, salary structure/assignment, slip with deduction/additional salary, payroll posting and reversal. Verify Employee/Payment Entry override composition and accountant-vs-HR segregation. If the immediate academic pilot explicitly excludes HR/payroll, HRMS can be deferred; it cannot be called unnecessary for the complete scope requested here.

## 7. Portal, authorization and security (2K, 2O)

**Portal/API authorization: BLOCKED.** No users or site-local Administrator were provisioned; no server-side allow/deny result was obtained. Source-level permission checks and an asset build are not isolation evidence. No access-control check was disabled and no Administrator-only test was substituted for least-privilege testing.

Required role fixtures: Administrator, academic manager (map deliberately to upstream Education Manager/Academics User), Instructor/teacher, accountant, HR user, and at least **two** student users with separate records. Add a second site for site isolation. Capture each user/role assignment and server response.

- Student own profile/grade/attendance/invoice reads must work; a changed document ID must not disclose another student's data through REST, RPC, reports, prints, exports or files.
- Teacher access must be scoped to assigned academic work; direct finance/payroll writes must be denied.
- Accountant must not gain unrestricted employee/payroll operations; HR access must not grant general financial authority by accident.
- Verify field-level sensitive data, shares, attachments, submitted record edits, Guest access, admin-only actions, session/CSRF behavior, password handling and site-header routing. Menu hiding is not evidence.

### Actual dependency/security observation

[education-frontend-advisories.json](evidence/phase-2/education-frontend-advisories.json) records the queried installed versions and npm's advisory responses on 2026-09-13. **57 returned advisory entries / 21 packages** include Vite, esbuild, Rollup, markdown/rendering/editor dependencies, socket.io-parser/ws and build-tool dependencies. Counts are advisory entries, not 57 proven vulnerabilities reachable in this application. Some concern dev servers, platform-specific cases or build-time inputs; browser/runtime reachability and exact remediation must be assessed separately.

Do not expose this old Vite dev server publicly or suppress advisory results. Upgrade to a supported upstream fix/release or document narrowly reviewed remediation with regression tests before adoption; do not blindly regenerate lockfiles with “audit fix.” This is an additional gate beyond restoring network access. No live exploit probes were run.

Other unresolved production safeguards: unique credentials/MFA/session policy, private evidence/payroll file defaults, trusted proxy site selection, private DB/Redis ports, disabled production developer configuration, safe backup/key storage, retention, least-privilege API/service accounts and payment provider verification. No runtime defaults can be declared secure because no site was initialized. No real student/employee/payment data or credentials are committed.

## 8. Database, transactions, backup and migration (2L–2N)

**All actual database and recovery gates: BLOCKED.** There is no live schema to inspect and no backup file or restored site. No migration command was run. Repeating `migrate` on an absent database or claiming a documented restore command is a proof would be misleading.

Required MariaDB evidence after provisioning:

- Capture engine/version, charset/collation, selected table definitions/indexes and metadata for Student, Applicant, Program/Course Enrollment, Course, Group/Batch, Assessment Plan/Result, Invoice/Fees, Payment Entry, Employee and Salary/Payroll records. Verify primary `name` keys, parent links, audit fields and framework vs SQL constraints.
- Exercise duplicate/concurrent enrollment, assessment uniqueness, submit/cancel/delete, referenced-document deletion, child history and rollback of a failing transaction. Record actual behavior; no schema redesign now.
- Record a full `backup --with-files` for populated synthetic data and an attachment with known hash. Preserve required config/encryption keys securely.
- Restore into a **different clean site/environment** with the same app revisions; verify login, counts, links, file hashes, result usability and financial balances. Disable real outbound integrations during drills. Record elapsed time and RPO/RTO observations, not only CLI exit codes.
- Controlled migration scenario: baseline backup → run all app migrations → verify schema/patch state → rerun unchanged migration and compare stable business data/invariants. This proves idempotent migration replay only; a cross-release upgrade needs a separately pinned before/after bundle and restore fallback. No cross-release upgrade is claimed.

## 9. Frontend and performance observations (2P–2Q)

**Standalone frontend install/build: PASS. Browser workflows and full asset pipeline: BLOCKED.**

Actual installed Education versions: Vue **3.4.19**, Vite **2.9.17**, frappe-ui **0.1.31**, Pinia **2.1.7**, Vue Router **4.3.0**, Tailwind CSS **3.4.1**. The command `yarn build` executes the upstream Vite production build with base `/assets/education/frontend/` and copies the HTML entry to `education/www/edu-portal.html`. Build transformed **1,587 modules**. The compiler emits bundles including Grades, Attendance, Fees, Schedule and Students; that proves assets were generated, not that those screens or APIs work.

| Observation | Measured result | Interpretation |
|---|---|---|
| Integrity-checked offline mirror seed (repeat) | 286 tarballs, 8.015 s | Package transport timing only |
| Fresh cache + removed node_modules install | 12.817 s wall | Yarn install; frozen lock unchanged |
| Production frontend build (repeat) | 7.460 s wall | Compile only; first successful build was 7.512 s |
| Large generated shared JS chunk | frappe-ui ~785.70 KiB / gzip ~245.24 KiB | Upstream >500 KiB warning; not a page-load benchmark |
| Generated HTML SHA-256 | `539df07366386b23db122e462fd049d96d617be0d744c52b1baf05bcecf0afae` | Artifact evidence, not deploy approval |
| ERP startup/migration/page/list/report/job latency | Not measured | No backend or sample DB |

Warnings retained: duplicate cache-destination patterns, peer dependencies, deprecated `url.parse`, outdated Browserslist data and chunk-size warning. They were not hidden by upgrading dependencies or increasing thresholds. The known advisory findings are tracked separately as a failed security gate.

Forms, tables, dashboards, routing against a live site, responsiveness, keyboard/focus/accessibility, English terminology and extension behavior require real browser tests with the configured backend. No screenshot/mock SPA, fake API or fabricated sample-data benchmark is offered as evidence. Frappe Desk/ERPNext/HRMS frontend builds remain unexecuted; do not extrapolate from Education's standalone build.

## 10. Testing strategy and gate coverage (2R)

Executed project tests cover the **validation helpers only**: missing/wrong-version/nonzero/timeout preflight behavior, never conflating tools with ERP success, strict mirror-origin parsing and strongest-hash/integrity rejection. Upstream test files were not rewritten. The explicit dependency audit exits 1 on findings; both unavailable-environment preflights exit 1.

Highest-value next existing suites: Education applicant/student/enrollment, attendance, Assessment Result, Fee Schedule/Fees; ERPNext Sales Invoice/Payment Entry/general ledger and Employee; HRMS attendance/leave/payroll/slips. First run these against a dedicated test site with development/test dependencies from the same pinned bundle. Use `bench --site <test-site> run-tests --app <app>` (or its supported narrowed DocType/module filters); record actual command, exit code, duration and failures. They **cannot currently execute because Python 3.14, DB/Redis and an installed test site are absent**. No selected upstream test is claimed passed by source inspection.

Add only small cross-app fixture/regression tests when that runtime exists: lifecycle handoff, double-fee prevention, permissions, file access and recovery. Do not create hundreds of unexecuted “tests” with invented API contracts now. `foundation-test-results.json` explicitly records planned scenarios as blocked and separates static/source, tool, build and runtime evidence.

## 11. Ownership matrix after this checkpoint

| Capability | Decision | Confidence / remaining gate |
|---|---|---|
| Framework/auth/ORM/jobs/storage | KEEP upstream | Source fit; runtime unproven |
| Student, Applicant, Employee, Customer | KEEP canonical authorities | Source relationships; zero live records |
| Education enrollments/classes/attendance/results | EXTEND only where institute rules require | Existing workflow not yet executed |
| Applicant placement/level/recommendation | BUILD boundary provisionally | No implementation; boundary experiments blocked |
| Academic/financial/HR integration links | EXTEND via owned app later | Must first prove upstream integration |
| Invoice/payment/ledger | KEEP ERPNext; prefer invoice path | Billing choice remains provisional until duplicate/refund/reconciliation tests |
| HR/payroll | REQUIRE HRMS for full requested scope | Source ownership proven; installation and payroll posting blocked |
| Frontend | KEEP/EXTEND upstream, English | Education builds, but dependency remediation and live UX checks required |
| Whole ERP/framework replacement | REPLACE: none justified by evidence | Transport failure is not an architectural rejection |
| Parallel student/employee/ledger; simultaneous duplicate fee paths | AVOID | No competing authorities added |
| Unreviewed direct upstream core edits | AVOID | No controller/schema/lock input modifications |

The extension-first architecture remains a **candidate**, not a runtime-certified decision. No owned Frappe product app was scaffolded in Phase 2.

## 12. Blocking conditions and next action (2S)

| Blocker | Required resolution before product work |
|---|---|
| B1 — dependency transport / missing runtime | Provide a controlled runner with working trusted Debian/container/Python-asset downloads, or approved digest-verified prebuilt artifacts. Do not disable TLS or use untrusted repackaged DB binaries |
| B2 — no qualified complete bundle | Pin container/runtime tooling, image digests and resolved app dependencies; execute clean app/site install and migrations, including Payments optionality and HRMS composition |
| B3 — frontend advisory findings | Triage the 57 entries, identify reachable risks, adopt reviewed fixes/upstream releases and rerun frozen build/security/UX regression; preserve all failures |
| B4 — cross-domain and permission proof absent | Complete lifecycle, finance, HR/payroll, Student/Teacher/Accountant/HR negative access tests and schema/transaction checks with synthetic records |
| B5 — recoverability/upgrade proof absent | Backup and restore populated data/files into a clean site; migration replay and a separately scoped release-upgrade rehearsal where required |
| B6 — no operational/browser performance baseline | Run workers/scheduler/cache/realtime, login and browser UI/accessibility checks; populate realistic samples and capture real timings |

**Next implementation phase is still foundation validation**, not TOEFL House domain engineering. Resume with an environment that can install the missing runtime, preserve the present successful frontend evidence, and resolve dependency findings. Once all required gates actually pass, replace the null approved bundle and blocked scenarios with reproducible runtime artifacts and revisit this conditional verdict. Do not convert this checkpoint into an acceptance declaration merely because the documentation and asset build are complete.

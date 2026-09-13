# TOEFL House ERP — initial engineering assessment

Date: 2026-09-13 UTC · Status: reconnaissance; **not production-qualified**

## 1. Executive decision and scope

**Use upstream dependencies plus an owned Frappe application, provisionally targeting the v16 family. Do not fork or copy ERP core.** Qualify a reproducible release bundle before creating business code. This is an architectural recommendation, not a claim that a foundation was previously selected or installed.

The connected repository is empty of application code. Accordingly, there is no existing local ERP to trace, run, migrate, or certify. We inspected candidate upstream source separately, including DocType JSON, controllers, portal APIs, billing, framework infrastructure, manifests and workflows. Findings below distinguish **observed local state**, **observed candidate behavior**, and **proposed policy**. This is a targeted source assessment, not an exhaustive security audit, dependency advisory scan, performance assessment, or runtime compatibility certification.

Frappe is a strong candidate because the code already provides integrated academic, accounting and employee authorities plus application hooks. A controlled fork would add merge/security maintenance without demonstrated need. A hybrid is justified only for a blocking upstream defect that cannot be fixed through supported extension: upstream the fix, record a narrowly scoped temporary patch, owner, tests and removal deadline. No evidence currently justifies replacing the framework or introducing microservices, another frontend framework, another CRM, or another ledger. This review does not claim a comparative evaluation of every education ERP.

## 2. Current repository and Git state

| Item | Observed result |
|---|---|
| Connected repository | `Frotan2/TOFEL-House-ERP`, https://github.com/Frotan2/TOFEL-House-ERP |
| Authoritative base | `main`, initial commit `9eccff957cadf036a3ac6f8208540a110148e67b` |
| Working branch | `arena/01a09bf3-tofel-house-erp`; session-fixed, already branched from base |
| GitHub default branch | `main` |
| Origin | Connected owned repository; no upstream remote |
| Fork/derivative status | GitHub `isFork=false`, parent absent; one initial commit and README only. No evidence of copied upstream code or mirror history |
| Initial tracked content | `README.md` containing only `# TOFEL-House-ERP` |
| Initial working tree | Clean |
| License | No local LICENSE; GitHub license metadata null |
| Branch protection | API returned HTTP 403 `Resource not accessible by integration`; **unknown**, not evidence of unprotected `main` |

No manifests, submodules, database, backend, frontend, authentication, tenancy, migrations, tests, CI/CD or production configuration exist locally. Exact **installed** framework/app/dependency versions are therefore **none**. Local Python is 3.11.2 and Node is 22.22.3; Docker and Bench were not found on PATH. No application server was started.

Evidence: `git status --short`, `git branch --show-current`, `git log`, `git ls-tree -r HEAD`, `git remote -v`; GitHub repository, branches and branch-protection APIs. Repository creation date in GitHub metadata: 2026-09-13.

## 3. Candidate upstream relationships and version integrity

Source checkouts were kept outside the product repository; they are not vendored or installed. [upstream-review.json](upstream-review.json) records full inspected commit SHAs, source versions, Python dependency declarations, Bench compatibility declarations, JavaScript manifests and discovered lockfile paths. It is **evidence, not a deployment lockfile**. Immutable source roots:

| ID | Repository/ref inspected | Source-declared version | License evidence |
|---|---|---|---|
| F | [Frappe/version-16](https://github.com/frappe/frappe/tree/988e54f3c4c291e2077a83809663f123731abe76) | 16.33.1 | MIT |
| E | [ERPNext/version-16](https://github.com/frappe/erpnext/tree/4048fb70e14d1843956fcdabb7c3cca75a1cbcdd) | 16.34.2 | GPL-3.0 |
| A | [Education/version-16](https://github.com/frappe/education/tree/22e0910d8b4188f17b76e58d7b434354ce5a0e58) | 16.0.1 | `license.txt`: GNU GPL V3; hooks agree |
| H | [HRMS/version-16](https://github.com/frappe/hrms/tree/a4768b441cff346def505e27f2a2229ee1e05b9b) | 16.18.1 | GPL-3.0 |
| P | [Payments/version-16](https://github.com/frappe/payments/tree/cca07d9f9392e2ea0e521c5975151db9e4b6c321) | 0.0.1 | MIT |
| D | [frappe_docker/main](https://github.com/frappe/frappe_docker/tree/a0c52135d4d41c4b8acf7adfdfc5bbcba46dd4d0) | No app version asserted | MIT |
| B | [Bench/develop](https://github.com/frappe/bench/tree/c9d12503d9d7fbfd94086c3de3cd4ac23dd44823) | 5.0.0-dev | GPL-3.0-only in manifest |

Paths prefixed F/E/A/H/P/D/B below are relative to these immutable roots. DocType shorthand `A:<name>` means `education/education/doctype/<name>/<name>.json` and its Python controller. This convention permits verification without relying on moving branches.

**Dependency graph:** Frappe → ERPNext → Education and HRMS. Education `hooks.py` requires ERPNext but its `pyproject.toml` only declares Frappe `>=16,<17`. HRMS declares both Frappe and ERPNext `>=16,<17`. ERPNext requires Frappe `>=16.21,<17`. Education CI additionally installs Payments; its billing module imports Razorpay, provided by Payments' declared dependencies. Treat payment installation/import requirements as a qualification gate, not an optional toggle proven safe to omit.

**Version traps:** GitHub's latest-release endpoint returned Frappe v15.120.1 and ERPNext v15.121.2 despite v16 branches existing. Education's latest release tag was v16.1.0, but both its inspected v16 branch and that tag's `education/__init__.py` declare 16.0.1. Bench's inspected default branch is development code; its latest release endpoint returned v5.31.0. Never assemble production by independently resolving `latest`, default branches, or app version strings.

The inspected Frappe requires Python `>=3.14,<3.15` and Node `>=24`; ERPNext and Payments require Python >=3.14. Education/HRMS lower Python declarations do not lower the effective stack requirement. Examples of exact direct pins are Frappe `rq==2.6.1`, `mysqlclient==2.2.7`, `PyMySQL==1.1.2`; many other dependencies are ranges or Git references. No resolved Python environment or transitive dependency inventory exists. Inspect lockfiles, resolve and hash the entire bundle and produce an SBOM in phase 2; do not label declaration ranges “exact installed versions.”

## 4. Architecture and extension assessment

**Backend:** Python metadata-driven modular monolith. DocType JSON defines fields, Link/Table relationships, permissions and submission support; Python Document controllers enforce behavior. Frappe exposes document REST APIs and whitelisted methods (`F:frappe/api/`, `handler.py`, `model/document.py`). Whitelisting is an exposure mechanism, not sufficient business authorization. ERPNext and HRMS are applications in the same site/process environment, not isolated services.

**Frontend:** Desk uses generated forms, JavaScript controllers, workspaces, reports and esbuild assets; Frappe includes Vue as well as existing jQuery/Bootstrap components. Education adds a Vue 3/Pinia/frappe-ui/Vite student/guardian portal (`A:frontend/package.json`, `frontend/src/stores/portal.js`, `education/hooks.py`). Its manifest still declares Vite ^2.7.2: investigate maintenance/advisories and Node 24 build behavior before adoption, not a vulnerability assertion. ERPNext has a banking frontend; HRMS has PWA/roster frontends. Do not introduce a parallel SPA for initial reception/teacher workflows.

**Jobs/cache/realtime:** Frappe Redis caching, Redis/RQ short/default/long jobs, scheduler and Node Socket.IO (`F:frappe/utils/background_jobs.py`, `F:frappe/utils/scheduler.py`, `F:realtime/`; D compose). Site and user context must be preserved in custom jobs; use after-commit enqueue and idempotent processing for payment/enrollment side effects. Retries are not exactly-once delivery.

**Extensions:** custom apps, DocTypes, exported Custom Fields/Property Setters, fixtures, document events, permission hooks, reports, workspaces, translation catalogs and v16 `extend_doctype_class` (`F:frappe/model/base_document.py`). Prefer these over class replacement. HRMS already overrides Employee, Timesheet and Payment Entry (`H:hrms/hooks.py`); another override can silently compete. Review hook order with all apps installed. Client scripts are UX only; rules must run in controllers/services for REST, imports and jobs too.

**UX/localization:** retain upstream Desk and portal until workflows are proven. Frappe's `is_rtl` recognizes `fa` (`F:frappe/public/js/frappe/utils/utils.js`); this does not certify Persian usability. Education's inspected translations directory contains Arabic, not a complete Persian catalog. Qualify RTL forms/tables, mixed English text, fonts, mobile, keyboard navigation, printing/PDF, Persian search and date/number input. Decide Gregorian/Jalali presentation, timezone and currency with operations; do not silently convert canonical stored dates or hard-code rial/toman assumptions.

## 5. Database, data authority and lifecycle

**Engine recommendation:** MariaDB for the combined stack. Frappe includes MariaDB, PostgreSQL and SQLite adapters, but that is not evidence that ERPNext/Education work on each. Education contains MariaDB-specific SQL. D's MariaDB override uses `mariadb:11.8`, utf8mb4/utf8mb4_unicode_ci, while Education CI uses MariaDB 10.6. Qualify and pin an exact MariaDB 11.8 patch/image digest; do not infer supported production combinations from these divergent examples. D's Redis override uses `redis:8.6-alpine`, also a moving tag to qualify.

**Schema/tenant model:** one database and configuration per Frappe site; apps installed on that site share its database. Most document tables are `tab<DocType>` with document `name` identity, plus metadata and child tables; Singles use framework single-value storage. Child rows carry parent/parenttype/parentfield. Link/Dynamic Link validation is framework-level, not a universal SQL foreign-key constraint guarantee (`F:frappe/database/`, `model/document.py`, `model/delete_doc.py`). Direct SQL writes can bypass validation, permissions and audit hooks.

A site is the candidate institution tenant. Company is an accounting boundary; Branch is an organizational dimension, **neither is a security tenant by itself**. Shared bench workers/apps and database hosts mean separate site databases are not separate infrastructure trust zones. Use separate deployments for stronger isolation requirements. Host/site selection must be controlled by a trusted proxy (`F:frappe/app.py:init_request`; D frontend site header).

| Canonical authority | Relationships and policy |
|---|---|
| ERPNext Lead | Prospect/contact lifecycle. Add a controlled link to Student Applicant; no second CRM identity store |
| Education Student Applicant | Requires Program and Academic Year. Retain applicant authority; reconcile placement-before-program choice with a meaningful admissions program policy, not fake enrollment |
| Education Student | Links Applicant, User, Customer and Guardians. Student controller creates/updates linked ERPNext Customer; Student is academic identity, Customer is accounting party, not competing student masters |
| Education Program/Course Enrollment | Program Enrollment submission creates Course Enrollments and can initiate fee documents. Do not independently insert competing enrollment records |
| Education Student Group | Actual group membership, instructors, maximum strength; Student Batch Name is a label/cohort dimension, not the entire class aggregate |
| Education academic results/attendance | Submitted results and attendance remain canonical for enrolled learning |
| ERPNext accounting | Sales Invoice/Payment Entry/Journal Entry and GL/payment ledgers own money. Custom payment records are reconciliation evidence, never another ledger |
| ERPNext Employee, extended by HRMS | Employee schema lives in `E:erpnext/setup/doctype/employee/`; HRMS overrides/extends behavior. Instructor links Employee. No second teacher-payroll master |
| TOEFL House placement (proposed) | Applicant-linked attempts and versioned decisions; links to Student after conversion, without copying academic or financial authority |

**Transactions:** Frappe commits successful state-changing requests and rolls back errors (`F:frappe/app.py:sync_database`); background jobs have their own transaction lifecycle. Explicit commits exist in Education's attendance API. Program Enrollment has synchronous academic and billing side effects; Fee Schedule may enqueue generation. Do not assume an end-to-end lead/payment/enrollment transaction or distributed atomicity. Test duplicate submissions, retries, concurrent enrollment/capacity and financial reconciliation. Use unique/idempotency constraints where the invariant requires them, not only lookup-before-insert checks.

**Audit/deletion/archive:** Frappe supports Version records when tracking is enabled, activity/access-related records and document timestamps. Several inspected Education masters/results lack `track_changes`; this is not a complete immutable audit trail. Submittable documents use draft/submitted/cancelled states. Framework deletion checks static/dynamic links and can retain Deleted Document records, with force/permanent paths; these are not legal retention guarantees. Program Enrollment cancellation deletes its Course Enrollments. Student has enabled/leaving fields and Group has disabled, but there is no demonstrated institute-wide archival policy. Define retention, restricted deletion, correction/amendment reasons, financial preservation and PII erasure policy before real data. Backups must follow the same retention policy.

## 6. Education coverage and TOEFL House fit

Source-traced paths:

1. **Applicant → Student → enrollment:** `A:education/education/doctype/student_applicant/student_applicant.js` invokes the enrollment API; `A:education/education/api.py:enroll_student` maps Applicant to Student and creates Program Enrollment. Student controller links Customer and updates applicant status. Program Enrollment submission creates Course Enrollments and fee records. Applicant status values alone are not an approved TOEFL House transition policy; implement/check server-side approval and placement prerequisites.
2. **Assessment:** Assessment Plan requires Student Group, Course, Grading Scale and criteria; Result requires Student/Plan. Result validation checks group membership, maximum scores, calculates grades and detects duplicate plan/student results. Criteria and percentage thresholds already exist; they can represent skill labels. They do not establish a pre-admission, multi-attempt placement decision system. Question currently supports single/multiple-correct options, not a complete human-rated speaking/writing examination.
3. **Class operations:** Course Schedule validates date/time and overlaps for groups, instructors and rooms, including assessment schedules. Attendance saves/submits Student Attendance documents. Assessments, Course/Quiz Activity and reports cover some progress, not yet a demonstrated institute progression policy.
4. **Portal:** frontend portal store requests server context; profile/program/invoice/attendance APIs use student/guardian relationship checks in `A:education/education/api.py`. This positive control does not prove every helper, generic document API, report, file or write route has identical scope.
5. **Billing:** Fee Schedule creates Sales Orders or Sales Invoices; legacy Fees still posts GL entries on submit/reverses on cancel. Select Sales Invoice + Payment Entry as intended billing authority, subject to migration/reconciliation tests. Do not bill one obligation through both flows.

### KEEP / EXTEND / BUILD / REPLACE / AVOID matrix

KEEP means preserve upstream ownership and qualify/configure, **not already approved for production**. Names below resolve to the source DocType directories described in §3.

| Capability | Decision | Evidence / boundary |
|---|---|---|
| Authentication, document framework, jobs, files | KEEP | F framework mechanisms; harden configuration and test permissions |
| Leads/prospects | EXTEND | E CRM Lead controller/schema; link to Applicant, deduplicate conversion, capture contact consent |
| Applicants/admissions | EXTEND | A Student Applicant/Student Admission; Program/year required before placement outcome, approval rules need qualification |
| Students/guardians | KEEP + EXTEND | A Student/Guardian links; qualify guardian scope, shared-email/minor requirements and audit settings |
| Programs/courses | EXTEND | A Program, Program Course, Course; language levels, prerequisites and recommendation mapping are not equivalent to a school academic year |
| Placement attempts and skill scoring | BUILD | Existing academic Result requires Student and class/course Plan; build applicant attempt and human rubric workflow, reuse criteria concepts where semantics match |
| English levels and recommendations | BUILD | Grading Scale percentage intervals are useful but not a versioned skill-based recommendation policy |
| Enrollment | EXTEND | A Program Enrollment/Course Enrollment; preserve submission ownership, add approval/placement/idempotency checks |
| Batches/classes | EXTEND | A Student Group and Student Batch Name; validate rolling intakes, capacity and transfers |
| Teachers/instructors | EXTEND | A Instructor.employee → E Employee → H HR behavior; teacher workload/qualification data only |
| Scheduling/rooms/resources | EXTEND | A Course Schedule/Room and overlap validations; branch scope, calendars and conflict concurrency require tests |
| Student attendance/leave | EXTEND | A Student Attendance/Student Leave Application; teacher scope, correction and business attendance policy |
| Academic assessments/exams | EXTEND | A Assessment Plan/Criteria/Result/Grading Scale; avoid replacing enrolled academic records |
| Progress/completion/next course | EXTEND + BUILD | A Course/Quiz Activity and reports support progress; build explicit completion eligibility and audited next-course decisions |
| Student/guardian portal | EXTEND | A frontend and portal API; permission qualification and Persian/mobile workflow gaps |
| Fees/payments/refunds | EXTEND | A Fee Structure/Schedule → E Sales Invoice/Payment Entry; one receivable flow, local gateway adapter only after reconciliation design |
| Accounting/reporting/expenses | KEEP + EXTEND | E accounts controllers, GL, purchase invoices; H Expense Claim. Configure chart, taxes, dimensions, approvals; no custom ledger |
| HR/leave/time/payroll | KEEP + EXTEND | H attendance/leave, Salary Structure/Slip/Payroll Entry; payroll creates E Journal Entry. Local labor/tax rules and teaching-hour calculation require validation |
| Branch operations/analytics | EXTEND + BUILD | E Company/Branch/Cost Center plus A Room and reports; controlled academic branch scope and cross-domain dashboards |
| Entire framework/UI/assessment core | REPLACE: none justified | No evidence supports wholesale replacement; do not turn a placement gap into an academic rewrite |
| Legacy Fees for new billing | AVOID | Remains upstream, but do not activate alongside invoice billing for the same fee |
| Parallel student/employee/ledger/CRM | AVOID | Duplicates established authority; no second education app owning the same entities |

### Proposed placement boundary (design constraints, not schema commitment)

Lead → Applicant → Placement Attempt → reviewed scoring → Level Decision → Course Recommendation → approved canonical enrollment → group/attendance/assessment → completion → next-course decision.

Use configurable dimensions (reading, listening, speaking, writing, grammar, vocabulary, interview), rubric versions, weights, thresholds, missing-score policy and manual-review rules. Do not assume CEFR bands, exam equivalence or cutoffs without the academic team's signoff. Preserve raw scores, evaluator, evidence, rule version, calculated result, overrides/reasons and timestamps. Submitted decisions must remain reproducible after rules change. Define retakes, expiry, supersession, partial tests, accommodations, scorer permissions and appeal/correction policy. Validate score ranges, zero denominators, missing/duplicate dimensions and threshold boundaries server-side.

Recommendation references upstream Course/Program and records rationale; it is not enrollment. Conversion links the attempt to the existing/new canonical Student once. Academic Assessment Result remains post-enrollment authority; do not create a fake student, group or enrollment just to take a placement test.

## 7. Security and technical-risk register

Static findings below identify qualification/hardening work, not confirmed exploitable vulnerabilities. No offensive tests or third-party runtime probing were performed.

| Priority | Observation and evidence | Required disposition / owner |
|---|---|---|
| Blocker | No runnable, pinned or tested local foundation | Platform lead: qualify install/build/migration and release bundle before business implementation |
| High | Education role JSON grants broad academic operations and Student/Guardian read/report/share on several records; selected portal APIs explicitly check relationships, but there is no demonstrated equivalent coverage across all access surfaces | Security + academic lead: least-privilege matrix and negative tests for generic APIs, exports, reports, prints, shares, files and jobs; instructor restricted to assigned groups |
| High | Education billing uses privileged writes and imports a helper from ERPNext's test module; Razorpay dependency supplied through CI Payments installation | Finance + security: keep online payments disabled pending dependency, payer/invoice binding, provider-verification, amount/currency, duplicate callback and reconciliation review. Prefer supported upstream payment integration; no custom ledger |
| High | Academic results compute grades server-side but inspected validator is not a complete placement-rule validator; duplicate checks are application lookups | Academic + QA: boundary/concurrency tests; immutable versioned placement decisions and explicit approval policy |
| High | Legacy Fees and invoice billing both remain available; enrollment also initiates fees | Finance: select one flow, test duplicate prevention, cancellation, refunds and trial-balance reconciliation |
| High | Site routing depends on host/site-header; shared runtime is not adversarial tenant containment | DevOps + security: trusted routing, isolated internal ports, per-site credentials, two-site isolation tests and deployment separation where needed |
| High | No backup/restore drill, audit retention or local privacy policy exists | Operations: approve RPO/RTO, encrypted offsite backups, key escrow, restore/recovery evidence; decide legal retention |
| High | v16 requirements exceed current sandbox; branch/release labels and Education source version differ; CI and container DB versions differ | Platform: approved immutable bundle and real compatibility matrix; scheduled dependency/advisory review |
| Medium | HRMS already overrides several ERPNext controllers | Architecture: extension composition tests and no competing class overrides |
| Medium | Portal's older frontend declarations and CI helper's unpinned tooling/older PDF download | Platform + QA: dependency scan, reproducible build, PDF/RTL qualification; do not copy CI helper as production installer |
| Medium | Audit tracking inconsistent; cancellation may delete derived enrollments | Data lead: preserve required history, verify links/correction semantics and tested retention policy |
| Unknown | GitHub branch-protection read denied; license absent locally | Maintainer: verify protection/rulesets in GitHub with sufficient rights; owner/legal select licensing policy |

Frappe provides session authentication, API keys/OAuth, CSRF checks, login attempt tracking and two-factor integration (`F:frappe/auth.py`, `twofactor.py`). Configure staff MFA, least-privilege service accounts, session policy, TLS, secure secret delivery and separate admin access; do not disable CSRF to make a portal work. Disable unnecessary Guest operations and production developer/server-script capabilities. App-menu visibility is not authorization.

File attachments use Frappe File records and site public/private storage. Private file serving delegates permission checks (`F:frappe/utils/response.py`, `core/doctype/file/file.py`); public files are public. Student evidence, exams, IDs and payroll documents must default to private and have parent-document permissions. Qualify upload limits/type handling, malware scanning policy, retention and backups. Do not assume object storage is configured; introduce a supported storage integration only if deployment requirements justify it.

## 8. Development, deployment, migrations and recovery

### Local development model — proposed, not runnable from this repository yet

Phase 2 must add a tested runbook and reproducible environment using upstream Bench/development containers. Install release-qualified Python 3.14, Node 24, MariaDB and Redis, a **released pinned Bench** (not the inspected develop head), and the native build/PDF requirements of the selected bundle. Keep the bench/sites outside the source checkout. Fetch each upstream app at its approved immutable revision; resolve the Payments requirement explicitly. Create a synthetic-data site with `bench new-site`, install ERPNext, dependency-qualified Payments, Education and HRMS in verified order, then the owned app. Build assets and start the complete Bench development process, including workers/scheduler/realtime.

Do not publish guessed one-command installers or moving-branch installs as qualified setup. A future preview must bind its frontend to `0.0.0.0`, accept the preview hostname and use same-origin `/api` requests with backend/websocket proxying. Site routing must match the synthetic site without trusting arbitrary browser-supplied site selection. No browser-side localhost backend URLs.

Site database configuration belongs in secret-managed per-site config (`db_type=mariadb`, `db_name`, `db_password`, and approved DB host/port/user configuration); Redis endpoints/shared settings belong in Bench common config. Never commit actual site config or credentials. `developer_mode` is local-only. A sanitized template must be added with the tested environment, not copied from an actual site.

### Production model — proposed

Use upstream `frappe_docker` custom-image build mechanisms, pinned to a reviewed revision, with Frappe/ERPNext/Education/HRMS and the owned app included. The default ERPNext image contains only Frappe/ERPNext, not the whole product. D `compose.yaml` splits Nginx frontend, Gunicorn backend, websocket, short/long workers, scheduler and configurator; database/cache are composed separately. Start with this model rather than Kubernetes or custom service orchestration.

Use immutable image digests shared across process roles; persistent sites/files and DB volumes; private DB/Redis networking; trusted TLS reverse proxy; no example/default passwords. D's example MariaDB override has a fallback password and must not be deployed unchanged. Supply secrets through controlled infrastructure, not Git or image build arguments. Add health/readiness checks, queue lag/scheduler monitoring, error monitoring, capacity planning, backup alarms and staging. Do not use `bench start` as production supervision. No production infrastructure is provisioned by this phase.

### Migrations and upgrades

Frappe `bench --site <site> migrate` runs patches, DocType schema synchronization, fixtures/customizations and hooks (`F:frappe/migrate.py`, `modules/patch_handler.py`; A/H/E patches). Commit owned schema and ordered idempotent patches; no manual production SQL or untracked Customize Form changes. Do not edit released historical patches, skip failing patches or assume DDL is globally transactional. Migration phases can commit independently.

For every release: back up → restore into isolated staging → install new immutable app bundle → migrate all intended sites → run regression/reconciliation → controlled production maintenance window with queues drained/paused as needed → migrate → smoke checks → re-enable processing. Test interrupted migrations and reruns. Rollback means restoring the matching database/files/config plus prior application image when schema/data is incompatible, not simply checking out old Python code. Record cross-app install/migration order and app versions for each site.

### Backup and restore

Upstream supports `bench --site <site> backup --with-files`, including database, public/private files and configuration, plus backup encryption support (`F:frappe/utils/backups.py`, `commands/site.py`). Site data-encryption keys and backup decryption keys must be recoverable through separate secure escrow; never put them in this repository. Backups retained on the same host/volume are insufficient.

Schedule monitored, encrypted, offsite backups with access/retention controls and approved RPO/RTO. Establish consistent recovery points for DB and attachments; assess whether point-in-time DB recovery is needed. Restore into an isolated site with the same approved application bundle using `bench --site <site> restore <database-backup> --with-public-files <archive> --with-private-files <archive>` and securely restore required configuration/keys. Confirm exact options against the pinned Bench/Frappe command help. Do not overwrite live data for a drill. Verify login, permissions, attachments, enrollment counts, ledger totals and decrypted integration settings without sending real notifications/payments. Only a timed successful drill proves recovery.

## 9. Licensing and distribution

The owned repository currently grants no explicit license. Do not assume public visibility permits unrestricted downstream use. Frappe/Payments/Docker tooling use MIT licenses; ERPNext/HRMS use GPLv3; Education's license file and hooks say GNU GPL V3 although GitHub's detector returned NOASSERTION. Preserve applicable copyright, license and attribution notices, including transitive dependencies and bundled assets. Audit Redis image licensing separately for the selected release.

For distributed GPL-covered combined/derivative software, plan corresponding-source and license compliance; separate Python packages are not automatically a copyleft exemption. GPLv3 is not AGPL's network-use provision, but hosting, customer deployment and downloadable images have different distribution implications. Have counsel/owner approve the owned app's license and distribution model before publishing a product. No upstream code or license text has been copied into the owned repository by this phase. TOEFL naming/trademark and any claimed exam affiliation also require owner/legal review.

## 10. Repository, branch and application policy

- Keep this repository as owned product source/integration documentation; upstream repositories remain dependencies. Do not fork merely because GitHub allows it, nor place upstream app copies inside this checkout.
- This session works only on `arena/01a09bf3-tofel-house-erp`; submit a PR to `main` after review. No branch switch, history rewrite or direct default-branch change. Future sessions should use their authorized feature branches, with protected PR-only integration, required checks and architecture/security/finance review for relevant changes. Branch/ruleset configuration needs an authorized maintainer to verify.
- Initially create **one owned Frappe app**, proposed package `toefl_house`, rather than one app per department. Proposed internal modules: Admissions & Placement; Academic Operations (links/orchestration only); Institute Configuration & Localization; Reporting. Small payment/notification adapters may live in the app when approved. Split reusable language-institute logic from TOEFL House branding/configuration logically; extract a reusable app only after real reuse warrants it.
- Upstream owns authentication, DocType engine, canonical students/enrollments/academic records, CRM, accounting and employee/payroll. Owned code owns placement policies/attempts/decisions, language-level progression rules, institute-specific approvals, controlled links, translations and workflow UX.
- Never modify `apps/frappe`, `apps/erpnext`, `apps/education` or `apps/hrms` in production; never edit generated assets, vendor dependencies or upstream DocType JSON in-place. For required fixes use reviewed upstream contributions or explicitly tracked temporary patch exceptions. No blind monkeypatching.
- Export scoped custom fields/property setters/workflows and fixtures through the owned app; avoid dumping users, credentials or live business records. Prefix owned fields/entities where appropriate. Centralize business transitions server-side and test them across UI/API/import/job entry points.

## 11. Validation performed and next implementation gate

| Validation | This phase result |
|---|---|
| Repository identity/history/tree/default branch | Inspected; README-only starting point confirmed |
| Branch protection | Blocked by GitHub integration's 403; requires maintainer verification |
| Candidate source/manifests and domain relationships | Inspected at recorded SHAs; static only |
| Dependency integrity | Declarations captured; complete resolution, advisory scan and SBOM **not run** |
| Installation/startup/database initialization | **Not run**; no app installed, Bench/Docker unavailable on PATH, host runtimes below candidate requirements |
| Migrations/backup/restore | Mechanisms inspected; execution and recovery **not run** |
| Backend/frontend/API/authorization/regression tests | Upstream tests/workflows inspected, **not executed**; no local test suite |
| Lint/type/static/build/smoke gates | No application gates executed; documentation/JSON/diff checks only |

Education contains 49 `test_*.py` files at the inspected snapshot and a Bench-based Python CI workflow plus build/lint workflows. Frappe includes server, UI, migration and type-check workflows; ERPNext/HRMS have their own suites. Existence or file count proves neither passing status nor TOEFL House coverage. Education CI ignores JavaScript-only PRs for its Python test job and uses moving dependency installs; do not copy it as the product's entire quality gate.

### Recommended phase 2: qualify the foundation, then a narrow placement slice

1. **Release/platform qualification:** resolve reviewed release tags to immutable commits, explain Education version mismatch, select released Bench, lock dependencies/image digests and record licenses/SBOM. Install all required apps in a reproducible dev/CI environment; prove cold startup, schema initialization, migrations and assets/PDF build. Resolve payment imports before enabling portal billing.
2. **Security and operational baseline:** approve role matrix (receptionist, teacher, academic reviewer, accountant, HR/payroll, manager, student/guardian, integration user); exercise allow/deny behavior across two students, teachers, branches and sites. Verify files/exports/prints/realtime/job scope and privileged operations. Complete backup/restore drill and migration rollback rehearsal.
3. **Canonical workflow/finance qualification:** use synthetic Applicant → Student → Enrollment → Group → Schedule → Attendance → Result fixtures. Prove Student–Customer and Instructor–Employee links; invoice/payment/partial payment/refund/cancel flow, payroll journals and reconciliation. Cover retry/duplicate/concurrent enrollment and cancellation history. Record unsupported localization/business requirements rather than silently bypassing them.
4. **Business-rule signoff:** academic operations approves level taxonomy, dimensions/rubrics, thresholds, retakes, expiry, progression and pre-placement Program handling. Finance/HR approve jurisdiction, currencies, fee policy and payroll rules. Operations approves tenant/branch topology, privacy, retention and RPO/RTO. These choices cannot be established from Git source alone.
5. **Owned app vertical slice:** only after gates 1–4, scaffold the app; build applicant-linked placement policy/attempt/review/decision and recommendation with a narrow receptionist/reviewer UI. Tests must show score-boundary correctness, reproducibility under changed rules, permissions, invalid transition rejection and idempotent canonical enrollment handoff. Do not start a second ledger, student master or wholesale portal redesign.

CI acceptance must include locked dependency install/integrity, fresh site and upgrade migration tests, upstream-relevant backend regression, custom unit/integration/API/business/authorization tests, UI/RTL smoke tests, configured lint/type checks, secret/dependency/static scanning, asset build and full-stack smoke checks. Persist real results and failures; do not use skip-failing migration flags, disabled validations or placeholder green jobs. Production approval is a later gate, not the outcome of this report.

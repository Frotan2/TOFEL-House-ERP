# Foundation architecture decision — maintenance and production risk

**Decision date:** 2026-09-14  
**Status:** Recommended architecture direction; production release remains blocked  
**Production / Phase 2 recommendation:** **REJECT current acceptance**  
**Selected strategy:** **Controlled upstream-aligned frontend upgrade path (option 2)**

## 1. Decision

Retain **Frappe → ERPNext → Education** as the target foundation for continued qualification, with **MariaDB** as the database default. Retain HRMS for the already-justified native HR/payroll scope, and Payments where the qualified dependency bundle requires it. Do not create parallel student, employee, academic or accounting authorities. Keep owned security safeguards in the small extension app, with explicit compatibility tests and reversible boundaries.

Choose a **coordinated upstream-aligned maintenance path**, not an accumulation of dependency overrides. Keep the existing immutable pins as the reference qualification baseline until a replacement bundle is proven. The experimental frontend lock is **not adopted**. No new framework, frontend, database, app version or vendor is selected by this decision.

Use option 1 only as a **temporary qualification bridge**, not an indefinite production strategy. If option 2 is infeasible, evaluate option 3 as **contracted upstream-aligned maintenance with a bounded patch queue**. Do not default to a permanent private fork, parallel portal or ERP replacement.

This selects the architectural direction; it does **not** approve production, grant risk acceptance, pass Phase 2 or authorize TOEFL-specific development. No dependency upgrades or runtime changes are made by this decision.

## 2. Evidence and uncertainty

| Evidence | Consequence for the decision |
|---|---|
| Hosted frontend comparison **34823793929**, source `45568015dc98c9f5b4b0d0483ff8837fac5970e1`, Check **103911386257**: 57 baseline advisory entries; 23 in the isolated candidate; 35 original matches removed and one newly applicable match | Bounded updates can reduce the problem, but the tested candidate is not a clean or integrated replacement |
| Both frontend builds and eight basic API checks per profile pass; candidate has zero detected dependency/peer range conflicts; application and reviewed frappe-ui source hashes are unchanged | Useful feasibility evidence, not native browser/backend compatibility, exploit regression or production approval |
| Vite 2.9.x caps Rollup below 2.78.0 and requires esbuild 0.14.x; recorded fixes exceed those bounds | Do not force individual toolchain versions outside declared contracts |
| Tiptap fixes require coordinated peers; Showdown has no patched release in the reviewed advisory records | A coherent editor/parser/UI solution is needed, not core-only overrides or an assumption that dormant code is removed |
| Reviewed frappe-ui **0.1.278** requires Vue ≥3.5 and does not export Education's existing deep Tailwind require path | It is not a drop-in replacement for the locked Vue 3.4.19 frontend; a newer library alone is not an approved target |
| Native run **34823345078**, source `4fa3192880a05ec5ba67899ecfff64679821ec74`: 54 readiness, six Guardian browser, four realtime, 33 upgrade and 47 post-restart isolation checks pass | The native foundation has substantial reusable evidence; wholesale replacement is not justified solely by Education's frontend findings |
| The native workflow still fails on its advisory audit; independent deployment, recovery and wider operational/security requirements remain incomplete | Production stays rejected regardless of the maintenance strategy selected |

The **58-entry review** covers the union of 57 baseline findings and one additional candidate finding. Counts are advisory matches, not counts of demonstrated remotely exploitable production defects. Serving-profile absence, ES-only output, absent browser code, dormant emitted code and build-input risks are distinct. The Education frontend comparison is not an audit of every Frappe/ERPNext/HRMS/Payments, server, Python or container dependency.

This decision uses the retained hosted reports and source/manifest review. It does **not** assert a newly verified vendor support window, available support contract, remediation delivery date or upstream commitment. A release tag and successful build are not an SLA. No vendor outreach or new runtime experiment was performed for this architecture-only decision.

## 3. Comparison of long-term strategies

Relative effort assessments below are architectural judgments, not priced estimates or delivery commitments.

| Strategy | Benefits | Production and compatibility risks | Ownership / reversibility | Decision |
|---|---|---|---|---|
| **1. Stay pinned with documented risk acceptance and monitoring** | Lowest immediate change; reproducible known baseline; retains existing scoped native evidence | Known findings remain; dormant paths can become active; old tooling accumulates migration debt; monitoring cannot prevent all XSS, disclosure or resource exhaustion; support horizon unverified | Low short-term engineering effort, increasing security/operational ownership; freezing is reversible but deferred migrations become harder | **Qualification bridge only. Not recommended as the indefinite production policy. No exception granted** |
| **2. Controlled upstream-aligned upgrade** | Preserves canonical ERP/academic models; reduces long-term divergence; makes compatibility and maintenance an explicit release discipline | Joint Vite/plugin/Vue/compiler/frappe-ui/editor/parser changes can affect asset generation, styling, serialized content and runtime APIs; upstream timing uncertain; a newer lock can introduce new advisories | Moderate-to-high bounded qualification work, then ongoing planned upgrades; reversible through versioned artifacts and rehearsed recovery, not assumed downgrade support | **Recommended strategic path** |
| **3a. Contracted upstream-aligned maintenance / bounded backports** | Can provide accountable patch ownership when upstream timing is insufficient; may retain stable APIs while addressing specific defects | Coverage may exclude Education's portal, transitive packages or the owned security extension; backports require provenance, compatibility and exploit tests; provider dependency and fees | Ongoing funded engineering/procurement responsibility; exit requires complete source, reproducible builds, documentation and a transition plan | **Conditional fallback; provider capability and terms unverified** |
| **3b. Reduce or retire the affected portal surface** | May reduce exposed functionality and future maintenance scope if business requirements permit | Disabling a page does not remove packages or protect REST/RPC/files/realtime; staff/guardian usability may become unacceptable; backend Education remains an authority | Potentially smaller footprint, but requires an explicitly approved service scope and separate qualification | **Feasibility option only, not a dependency waiver or authorized implementation** |
| **3c. Permanent fork, replacement portal or platform replacement** | Maximum control over implementation choices | Highest recurring ownership; duplicates or reimplements UI/auth contracts; resets substantial integration/security/migration evidence; a new dependency tree brings its own risks | High-to-very-high lifecycle burden; difficult exit if data or APIs diverge | **Not recommended now. Reopen architecture only if options 2 and 3a fail the feasibility gates** |

### Option 1: what risk acceptance would—and would not—mean

A pin prevents unintended version drift; it does not make a vulnerable package safe. Similarly, a WAF, CSP or alert is not a general cure for vulnerable parsers or build tooling. Network controls and observed dormancy support narrow exposure arguments, not blanket immunity.

If a future accountable owner requests an exception, it must identify:

- Exact versions/artifact hashes, affected advisories, environment, reachable paths, data sensitivity, users and business necessity.
- A named business risk owner, security reviewer and operational owner; their approvals are **not supplied by this document**.
- Verified preventive controls, residual impact, monitoring signals, response and service-withdrawal procedures.
- An expiry, review cadence, remediation owner and concrete exit criteria. Renewal must be explicit, not automatic.
- Which acceptance criteria, if any, are being proposed for change. Preserve raw failed audits and report an exception separately; never relabel them as passing tests.

**Proposed governance defaults—not implemented controls or accepted SLAs:** daily advisory/release intake, human triage at least weekly, and immediate reassessment after a relevant exploit report, newly reachable path, asset/dependency change or control failure. A proposed exception should expire within **30 days**, with review before expiry. Urgency must follow actual exposure and impact; a numerical cadence is not a guarantee of protection.

No exception is currently granted. Continued synthetic, isolated qualification is not authorization to process real student/payroll data or start a production pilot. Even a duly approved dependency exception would not close missing TLS, recovery, capacity, business or authorization evidence. A future exception requires a separately reviewed release decision; the existing failed gates remain unchanged here.

### Option 2: what upstream alignment requires

Alignment means a maintained, provenance-traceable change set compatible with the native bundle—not “install latest.” Obtain evidence for the relevant release/support policy and a coherent combination of build toolchain, Vue/compiler, frappe-ui, Tiptap/ProseMirror and parser/sanitation behavior. Do not assume independently current releases compose correctly.

Keep the backend bundle fixed during initial frontend experiments where feasible to isolate failures. If a frontend upgrade requires backend/API changes, qualify the whole proposed bundle explicitly; do not silently broaden the scope. Do not infer a new client's realtime authorization or reconnect behavior from the baseline client's passes.

Prefer changes accepted into a maintained upstream release. If a temporary backport is necessary, it needs explicit approval, an exact source base, patch hashes, upstream references, named ownership, tests and retirement criteria. No upstream core modification is authorized by this ADR. The experimental 18-resolution candidate remains a diagnostic artifact, not the target architecture.

The owned security extension is also a maintenance liability: File extension composition and the pinned realtime adapter behavior must be requalified when native contracts change. Its deliberate denial of broad traffic is an availability/compatibility trade-off, not universal support for Desk, clustered adapters or app-specific emitters. Do not remove protections to accommodate a frontend upgrade.

### Option 3: acceptable fallback boundaries

Before selecting a support provider, require explicit coverage of the **actual** Frappe/ERPNext/Education/HRMS/Payments bundle, frontend transitives and owned security integration—not a generic “ERP support” claim. Require patch provenance, reproducible artifacts, licensing/redistribution review, disclosure handling, security response commitments, regression responsibility and access to source/build documentation upon exit. No provider or contract has been evaluated or approved.

A bounded maintenance line must not create new Student, Employee, ledger or academic authorities. Keep patches separate from product features, rebase regularly against an identified supported base, and retire patches when upstream incorporates or supersedes them. Do not relabel vulnerable versions to suppress scanners. For genuine backports, retain the scanner result and a reviewed mapping from advisory to patch and tests under an explicitly approved exception policy.

Portal retirement is only viable if stakeholders accept the reduced service and tests prove the intended boundary. Merely hiding links leaves endpoints and installed dependencies present. Removing assets/build dependencies, restricting routes and validating all remaining native access paths are different tasks. Do not uninstall Education or invent a replacement authority as a shortcut. No portal redesign or replacement is started now.

## 4. Recommended execution and decision gates

These are proposed next steps, not evidence of completion. Accountable people, funding, support terms, deployment targets and recovery/performance objectives remain to be assigned or agreed.

| Stage | Required deliverable | Exit / stop condition |
|---|---|---|
| **A. Baseline and ownership** | Preserve exact pins, evidence and unadopted candidate; appoint platform, security and operations owners; define intended deployment/data exposure | No production or product work. No automatic dependency update merge |
| **B. Upstream feasibility** | Confirm support policy and a coherent upgrade proposal; inspect API/export/peer/engine changes, parser semantics, licensing and upstream acceptance path; obtain an effort/maintenance estimate | **Proposed checkpoint: within four weeks of funded kickoff**, not four weeks of unapproved work. If no credible maintained path exists, evaluate 3a or pause—not indefinite silent freezing |
| **C. Isolated qualification** | Exact immutable candidate; integrity-verified frozen build; whole relevant dependency inventory; per-advisory affected-path tests; retained baseline and failed attempts | Reject incompatible forced resolutions, regressions, unresolved critical exposure or unowned patches. Build/API smoke alone cannot promote a candidate |
| **D. Native and operational validation** | Hosted browser/API/CSRF/role/Guardian/file/realtime tests; assets and supported browsers; editor/content compatibility where used; migration and rollback/recovery; deployed TLS/origin/session boundary; durability, monitoring and capacity evidence | All critical criteria must meet documented targets. Upgrading dependencies cannot waive independent operational gates |
| **E. Release decision** | Evidence-linked acceptance review, approved residual-risk register, immutable artifacts, release/rollback runbooks and assigned operators | ACCEPT only when required gates pass; ACCEPT WITH CONDITIONS only for explicitly bounded, approved noncritical residuals. Otherwise REJECT |

Reopen architecture if there is no funded owner, no credible supported/backported path, repeated incompatible security fixes, inability to preserve native authorities/authorization, or no viable recovery/deployment design. Any replacement-platform investigation must compare migration and lifecycle costs against retained native evidence; it is a new decision, not an implied next implementation step.

## 5. Production risk and acceptance position

The selected strategy does not eliminate these current blockers:

1. **Dependencies:** baseline still has 57 Education advisory entries; experimental candidate has 23 and is not natively integrated or adopted. Whole-stack coverage is incomplete.
2. **Exposure and authorization:** demonstrated Guardian/File/realtime protections are scoped. Broader mixed-role, multi-child, lifecycle, export/print/attachment and app-specific realtime paths remain unqualified.
3. **Deployment and durability:** controlled web/worker replacement is not database/Redis/host-loss durability, HA, exactly-once processing or an approved public TLS/proxy/origin boundary.
4. **Recovery and change safety:** same-runner recovery and a framework patch upgrade do not establish independent-host recovery, approved key/backup handling, rollback or independent app upgrades.
5. **Operational and business completeness:** representative capacity, alert delivery, audit/retention processes, full payroll posting and wider business-role coverage remain open.
6. **Sustained maintenance:** accountable staffing, support coverage, response expectations and licensing/distribution decisions need resolution before depending on them in production.

**Final foundation decision:** proceed with option 2 as the architecture and maintenance direction; preserve option 1 as a time-bounded qualification bridge; reserve option 3a as a gated fallback. **REJECT current production/Phase 2 acceptance.** Neither risk acceptance nor monitoring has been approved or implemented by this decision. No TOEFL-specific implementation begins.

## References

- [Final dependency and operations qualification](foundation-final-qualification.md)
- [Production acceptance ledger](foundation-production-acceptance-ledger.json)
- [Advisory-by-advisory review](evidence/phase-2/frontend-advisory-compatibility-review.md)
- [Exact hosted report verification](evidence/phase-2/dependency-operations-hosted-verification.json)
- [Pinned candidate matrix—not an approved production lock](foundation-version-matrix.json)
- [Owned security boundaries and historical hardening evidence](foundation-hardening-remediation.md)

All prior failed evidence is retained. This architecture-only decision introduces no new runtime pass, waiver, dependency version, deployment, vendor commitment or product feature.

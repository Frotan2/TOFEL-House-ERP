# Engineering review — 2026-09-17

Date: 2026-09-17 UTC · Active branch: `arena/01a0aef4-tofel-house-erp`
Reviewer scope: the whole repository as checked out, not a single domain.
**Production remains REJECT. D8 remains BLOCKED. No qualified domain was
reopened. No business rule, price, grading policy, tax, refund term or
operational target was invented, and no license was selected.**

This review answers three questions with evidence rather than narrative: is the
working tree sound, what did the review actually find and fix, and what genuinely
remains and why.

---

## 1. Method — what was actually executed

Nothing below is asserted from reading alone. Every command was run against this
checkout:

| Command | Result at review start | Result now |
|---|---|---|
| `python3 -m unittest discover -s tests -t .` | **629 tests, 2 FAILED** | **665 tests, OK** |
| `node tests/foundation/test_realtime_guard.cjs` | PASS | PASS |
| `node tests/foundation/test_command_pages.cjs` | PASS (14 pages) | PASS (14 pages) |
| `python3 tools/foundation/d8_validate.py --contract …template.json` | exit 1 — `checkout_branch_matches_active` false | exit 0 — BLOCKED / REJECT |
| `ruff check .` (pyflakes + syntax) | **11 findings** | **All checks passed** |
| All five `owned-suite.yml` step scripts, executed locally | — | all exit 0 |

Structural checks also run: 22 DocType JSONs parse; 20 command-only DocTypes have
matching `has_permission`, `permission_query_conditions`, `permissions.query_*`
and `policy.can_read` coverage with no gaps; the 2 child tables correctly carry
no `has_permission`; all 23 role fixtures referenced by `KIND_ROLES` and the
14 command Pages exist; every `_COMMAND_PAGES` entry has a Page file. **No
assembly drift was found** — that surface is genuinely consistent. It was,
however, only consistent by luck: nothing enforced it, so it is now enforced by
`tests/foundation/test_app_assembly.py` (F8).

---

## 2. Findings

### F1 — CRITICAL: the working tree was red; the branch boundary had drifted

`tools/session_branch.ACTIVE_BRANCH` pinned `arena/01a0aafe-tofel-house-erp`
while the checkout is on `arena/01a0aef4-tofel-house-erp`. Two qualification
tests failed as a direct result:

```
FAIL: tests.d8.test_contract.D8ContractTests.test_template_is_explicitly_blocked_and_production_disabled
  AssertionError: False is not true          # checkout_branch_matches_active
FAIL: tests.foundation.test_current_branch_qualification.CurrentBranchQualificationTests.test_checkout_is_the_active_session_branch
  AssertionError: 'arena/01a0aef4-…' != 'arena/01a0aafe-…'
```

By this repository's own rule (`BRANCH-RECONCILIATION.md`, "Required review
rule") an unclassified old branch in an active workflow, hosted guard,
current-status header or qualification test *is* release-control drift and must
be corrected. It was not corrected; it had been sitting there.

**Fixed** by rotating the boundary per the documented procedure, in one change:
`tools/session_branch.py`; all 10 workflow filters (22 references); 16
current-status document headers; `active_branch` in 4 governance JSON files
(5 occurrences — D8 matrix ×2, contract template, canonical owner record,
architecture gate review); and the acceptance ledger.

### F1a — The rotation procedure could not be followed honestly (design defect)

This is the more serious half of F1, and it was invisible until the rotation was
attempted. `d8_validate.validate_ledger()` required:

```python
runtime.get("run") != ACTIVE_RUNTIME_RUN  →  ContractError
```

i.e. the *active* branch's ledger block had to name a specific run id. After a
rotation no hosted run exists on the new branch, so the only way to satisfy the
old validator was to record run `35122242581` — which executed on the *previous*
branch — as an execution on the new one. The validator structurally forced
either a red tree or falsified evidence.

**Fixed** by making the absence an explicit, validated state:
`hosted_execution_state: NOT_EXECUTED_ON_THIS_BRANCH`. `validate_ledger()` now
- rejects **any** execution identity (run, check, commit, SHA-256) inside such a block, at any nesting depth;
- rejects populated `foundation_runtime` / `foundation_runner` / `placement` / `frontend_candidate` / `d8_contract` sub-blocks;
- rejects a relaxed production posture in that block;
- rejects an `EXECUTED` claim the session boundary does not record;
- pins each previous branch's run separately (`PRIOR_ACTIVE_RUNTIME_RUN = 35122242581` on `01a0aafe`, `EARLIER_ACTIVE_RUNTIME_RUN = 35090904508` on `01a0a9f7`), each required to stay `historical_provenance`.

The D8 report now discloses the state as `active_branch_hosted_execution` and
says so in its `warning`. **No gate changed state**: production stays REJECT,
D8 stays BLOCKED, SEC-DEPS-01 stays UPSTREAM-BLOCKED / REJECT.

Verified by 8 new tests in `tests/d8/test_contract.py` (`ActiveBranchEvidenceTests`),
each mutating the ledger and asserting `ContractError`.

### F1b — Branch strings were duplicated in tests, so drift was guaranteed

`tests/foundation/test_durability_contract.py` and
`tests/foundation/test_independent_recovery_contract.py` each hardcoded
`arena/01a0aafe-tofel-house-erp` twice instead of importing the canonical pin,
so the next rotation would have stranded them exactly as this one did.
**Fixed**: both now read `ACTIVE_BRANCH` / `ACTIVE_REF` from `session_branch`.

### F2 — CRITICAL: latent `NameError` in the evidence-recovery path

`tools/placement/recover_evidence.py:48` called

```python
subprocess.run(["python3", str(root/"tools/foundation/publish_evidence.py"), …])
```

but the module constant is `ROOT`. The name `root` is undefined, so the publish
step raised `NameError` unconditionally. It survived because that line has never
been reached: `BRANCH-RECONCILIATION.md` records that the migration push's
recovery run `35090760612` *failed before publication* while retrieving the
historical artifact. A dead code path in a recovery tool is exactly where a
defect should not be allowed to live.

**Fixed** (`root` → `ROOT`). Caught by enabling pyflakes (F821), which is why
F4 below matters more than the one-line fix.

### F3 — SECURITY: `tarfile.extractall()` without a filter on a decrypted archive

`tools/foundation/release_readiness_evidence.py` extracted a decrypted backup
archive with a bare `extractall`, which writes through absolute and `..` member
paths. The HMAC in that path proves the archive was not tampered with by someone
*without the key*; it says nothing about the member names inside it.

**Fixed** with `extract_safely()`: `filter="data"` where the interpreter supports
it (default from Python 3.14), plus an explicit fallback that refuses links,
device nodes and any member resolving outside the destination. Verified by 4 new
tests asserting the invariant rather than an exception type, because the two
paths differ (the `data` filter sanitizes an absolute member into the
destination and raises on traversal; the fallback raises on both).

> **Honest limit:** this sandbox runs Python 3.11.2, whose `TarFile.extractall`
> has no `filter` parameter — confirmed by `inspect.signature`. Only the
> fallback branch was executed here. The `filter="data"` branch is pinned by a
> source-contract test but was **not executed** in this environment.

### F4 — No static-analysis gate existed

25,653 lines of Python across `apps/`, `tools/` and `tests/` with no linter
configured and no CI job running one. That is why F2 reached the repository.
**Fixed**: root `pyproject.toml` with a
narrow, zero-false-positive ruleset (`E9`, `F`) and **no per-file suppressions**;
11 findings fixed rather than silenced — 1 undefined name (F2), 6 unused
imports, 4 unused variables. Two of those unused variables were computed evidence
that was being thrown away: the per-version ciphertext digests in the
release-readiness harness are now recorded in its manifest, and the fixture
member list is now asserted to survive the encrypted round trip path-by-path.

**Wider rule families still report findings and are deliberately not suppressed
or enabled** — they are staged follow-ups (§4), not clean bills of health:
`TRY003` 768, `S101` 730 (asserts — legitimate in a harness), `C408` 236 (a
Frappe idiom), `PLR2004` 233, `I001` 123, `BLE001` 32 blind excepts, `B023` 6,
`B905` 7, `S608` 10 hardcoded SQL fragments.

### F5 — No single run exercised the whole owned suite

Every workflow is path-filtered to the tooling it qualifies, so:
- a change under `apps/**` never ran `tests/d8`;
- a change under `tools/**` never ran the domain suites;
- **no workflow triggered on `pull_request` at all** (verified: 0 occurrences
  across all 10 workflows at `HEAD`), despite the README requiring "reviewed
  pull requests".

**Fixed** with `.github/workflows/owned-suite.yml`: whole-tree discovery
(`-s tests -t .`, so a new `tests/<area>` is covered automatically), both Node
suites, hash-pinned ruff in an isolated venv, and an assertion that the D8 gate
is still BLOCKED / production still REJECT. Runs on push to the active branch
*and* on every pull request. `permissions: contents: read` only. All five step
scripts were executed locally: 654 tests OK, both Node suites OK, ruff clean,
D8 validator exit 0.

### F6 — OWNER DECISION REQUIRED: the product license is declared three ways

Not fixed, because it is not engineering's to fix:

| Surface | States |
|---|---|
| `apps/toefl_house/toefl_house/hooks.py`, `apps/foundation_security/…/hooks.py` | `app_license = "MIT"` |
| `README.md` | "No product license has been selected yet." |
| Repository `LICENSE` file | **absent** |
| GitHub `repos/Frotan2/TOFEL-House-ERP` `license` field | `null` (queried) |

A license is a legal grant, effectively irreversible once published, and it
constrains how the pinned upstream Frappe/ERPNext/Education/HRMS apps may be
combined and distributed. **Recorded as D11** in the canonical owner-decision
record and `OWNER-DECISIONS.md` with four options and an explicit consistency
requirement. No license was selected and no `app_license` value was changed.

### F7 — The documented branch-boundary rule was prose only

`BRANCH-RECONCILIATION.md` states that an unclassified old branch in an active
surface "must be corrected", but nothing enforced it — which is precisely how F1
persisted. **Fixed** with `tests/foundation/test_branch_boundary.py` (7 tests):
workflows may name only the active branch; any historical branch in
`tools/`, `tests/` or `apps/` must be declared in
`session_branch.HISTORICAL_BRANCHES` and labelled as provenance on its own line;
current-status headers must name the active branch; and recorded evidence under
`docs/engineering/evidence/` must **never** be rewritten to the active branch.

Proved load-bearing rather than vacuous: temporarily reverting one workflow
filter to the previous branch makes the suite fail with
*"a stale branch in an active workflow filter is release-control drift"*;
restoring it passes.

---

### F8 — App-assembly consistency was verified by hand and enforced by nothing

`hooks.py` (`has_permission`, `permission_query_conditions`, `page_js`,
`doc_events`, fixtures) has to agree with `permissions.KINDS`/`TABLES`, every
`permissions.query_*` definition, `policy.can_read`, `security.DOCTYPES`/
`KIND_ROLES`, the DocType JSON files, `modules.txt` and `fixtures/role.json`.
Frappe resolves those tables at import/migrate time and fails late and
obscurely, so a new guarded DocType added without a matching `query_*` function
or `can_read` branch would ship silently and only surface on a live site.

The review audited the whole surface and found it **consistent** — 22 DocTypes,
20 guarded, 2 child tables correctly unguarded, 20 kinds each with a row and a
`can_read` branch, 23 roles, 14 pages. But no test held any of it.

**Fixed** with `tests/foundation/test_app_assembly.py` (11 tests): pure file
parsing, no Frappe import. Proved load-bearing — injecting one kind into
`permissions.KINDS` without extending `policy.can_read` produces 3 failures;
reverting passes. It also pins the A13 invariant that every natively guarded
DocType carries the *same* guard on all three lifecycle seams.

### F9 — CRITICAL: the TLS edge could not decide the protocol-policy check, and lost the evidence that explained why

**Pre-existing and undocumented.** `foundation-operational-boundaries.yml` failed
at the same step with the same traceback on two consecutive session branches —
run `35197870620` on `arena/01a0aafe-tofel-house-erp` and run `35214660151` on
this one — so it is not caused by the F1 branch rotation, and no review, gap-map
row or ledger note recorded it before this one.

Both runs failed one check:

```
AssertionError: TLS protocol policy not enforced:
{"reason": "no parseable evidence for: TLSv1, TLSv1.1",
 "outcomes": {"TLSv1.2": "ACCEPTED", "TLSv1.3": "ACCEPTED", "SSLv3": "REFUSED",
              "TLSv1": "NOT OBSERVABLE", "TLSv1.1": "NOT OBSERVABLE"}}
```

The assertion itself was **correct** and was left fail-closed. Two separate
defects sat behind it.

**Defect 1 — the evidence that explained the failure was never published.**
In `tools/foundation/runtime_tls_edge.py` the client-verification step runs
`probe.run("verify-tls-edge-as-a-real-client", …)`, which raises on a non-zero
exit *before* the next line reads the inner `tls-checks-result.json`. The inner
result was written and retained in the artifact zip, but never ingested. Both
published reports therefore carried `verdicts keys: ['tailscale_boundary']`,
`tls_protocol_policy: null` and `has client_checks: False` — precisely the
per-protocol transcripts and `required_refusals_observed` structure built to
separate "refused by the listener" from "rejected by the client, therefore not
evidence" were the thing thrown away. The gate went red with no retrievable
explanation, and diagnosing it required a runner we could not get.

*Fix:* the call is wrapped, the inner result is ingested and
`required_refusals_observed` populated **before** the exception is re-raised, so
fail-closed behaviour is unchanged and the evidence survives the failure.
`summarize_refusals()` tolerates a half-finished result and publishes
`complete: false`, `protocols_with_no_evidence_at_all` and
`client_side_refusal_reasons` instead of a quietly empty report.

**Defect 2 — the observation was undecidable on the runner's OpenSSL.** The
distribution crypto policy stops `openssl s_client` from offering TLS 1.0/1.1 at
all, so the "refusal" was the client's own. `protocol_flag` correctly declined to
count it as evidence about the server — a refusal that never reached the server
says nothing about it — and the claim stayed unproven forever on that image.

*Fix:* a policy-independent instrument. `tls_edge.build_legacy_client_hello()`
and `tls_edge.parse_tls_record()` are pure (the module's docstring promises no
network dependency and that contract is honoured); `legacy_protocol_outcome()`
in `runtime_tls_edge_checks.py` does the socket I/O and offers one legacy
protocol on a raw socket. `merge_legacy_observations()` folds the result back in
and only ever upgrades an entry already `NOT OBSERVABLE` — it cannot manufacture
an outcome. Alert 70 (`protocol_version`), 71 (`insufficient_security`) and 40
(`handshake_failure`) count as server-attributable refusals; a `SERVER_HELLO`
counts as a policy violation.

**Verified against real TLS servers on loopback** — not mocked, and the negative
control was run:

| Listener under test | Probe result |
| --- | --- |
| `minimum_version=TLSv1_2` | TLS 1.0 / 1.1 → `ALERT / protocol_version / attributable_to_server=True`; SSLv3 → `ALERT / handshake_failure / True` |
| `minimum_version=TLSv1` + `DEFAULT@SECLEVEL=0` | TLS 1.0 → `SERVER_HELLO / negotiated 0x030x01`; TLS 1.1 → `SERVER_HELLO / 0x030x02` |
| closed port | `NO EVIDENCE / ConnectionRefusedError / attributable=False` — never a refusal |

Replaying the exact outcomes run `35214660151` published, plus those raw
observations, yields `POLICY ENFORCED` with `protocols_with_no_evidence == []`.
A listener that genuinely accepts TLS 1.0 still resolves to `NOT PROVEN` with
`policy_violations == ["TLSv1"]`.

10 tests added in `tests/foundation/test_tls_edge_contract.py`
(`LegacyProtocolObservabilityTests`, `ClientEvidencePublicationTests`), 665 → 675.
**Limit:** the runner's own crypto policy could not be reproduced in the sandbox
(OpenSSL 3.0.20 offers TLS 1.0/1.1 fine, and `-cipher DEFAULT@SECLEVEL=2` or
`@SECLEVEL=0` does not change it), so the *client-capability* half of defect 2 is
reasoned about, not reproduced. The raw-ClientHello path is verified end to end.

**Then verified on the runner.** Run `35216709160` @ `37e4bff` — the same
workflow that failed on two consecutive session branches — completed `pass` with
38 checks and no failures. Its published report:

| Field | Before (runs 35197870620 / 35214660151) | After (run 35216709160) |
| --- | --- | --- |
| `verdicts` keys | `['tailscale_boundary']` | `['tailscale_boundary', 'tls_protocol_policy', 'certificate_verification']` |
| `client_checks` | absent | present |
| `tls_protocol_policy.verdict` | `null` (check never reached a verdict) | `POLICY ENFORCED` |
| `protocols_with_no_evidence` | `["TLSv1", "TLSv1.1"]` | `[]` |
| TLSv1 / TLSv1.1 | `NOT OBSERVABLE` | `REFUSED`, `resolved_by: "raw ClientHello (policy-independent)"`, `alert_description: "protocol_version"` |
| `required_refusals_observed` | never published | `protocols_rejected_by_the_listener: ["SSLv3","TLSv1","TLSv1.1"]`, `…not_evidence: []`, `complete: true` |

The alert the runner's listener returned to the raw ClientHello —
`protocol_version` — is the same alert observed locally, so the instrument
behaved identically in both places.

**A third defect surfaced from that report and is fixed here.** The published
verdicts carried no `tls_protocol_raw_client_hello`, even though the probe wrote
it: `runtime_tls_edge.py` ingested a *hardcoded pair* of verdict keys, so the new
instrument's own record was silently discarded — the same evidence-loss failure
mode as defect 1, one layer above it. The key is now published, and
`test_the_raw_client_hello_evidence_is_published_and_not_whitelisted_away` fails
if any verdict key the probe writes is neither published nor deliberately
withheld. The full `s_client` transcripts (`tls_protocol_attempts`) remain in the
retained artifact only: they embed certificate PEM and would dominate the
published summary without changing any verdict. 675 → 685 tests.

### F10 — Every workflow ran on deprecated action runtimes, and nothing in the suite noticed

GitHub deprecated the Node.js 20 action runtime on 2025-09-19. Every run in this
repository carries the warning as an *annotation*, which no gate reads:

```
Node.js 20 is deprecated. The following actions target Node.js 20 but are being
forced to run on Node.js 24: actions/checkout@11d5960a326750d5838078e36cf38b85af677262,
actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
```

Three of the four pinned actions declared `runs.using: node20` and were being
force-run on a runtime their authors never tested — in a repository whose entire
posture is "pin it, hash it, prove it". The pins were correct; the *runtime* they
pinned was not. Because the warning is an annotation rather than a failure, the
whole suite stayed green and nothing recorded it.

**Fixed.** Each action was resolved against the GitHub API (tag each SHA carries,
and the `runs.using` declared by that tag's `action.yml`) and rotated to the
**lowest major that runs on Node 24** — chosen to remove the deprecation with the
smallest behavioural delta rather than to chase the newest major:

| Action | Was | Now | `runs.using` |
| --- | --- | --- | --- |
| `actions/checkout` | `11d5960a…` v4.4.0 | `fbc6f399…` **v5.1.0** | node24 |
| `actions/upload-artifact` | `ea165f8d…` v4.6.2 | `b7c566a7…` **v6.0.0** | node24 |
| `actions/download-artifact` | `d3f86a10…` v4.3.0 | `37930b1c…` **v7.0.0** | node24 |
| `actions/setup-node` | `249970729…` v6.5.0 | unchanged | node24 already |

Breaking changes were checked rather than assumed. All three new majors require
runner ≥ 2.327.1; `download-artifact` v5's one real breaking change is scoped to
single-artifact downloads **by ID**, and `grep` confirms no workflow passes
`artifact-id` — all eight downloads are by `name`, so it does not apply.

Two defects in the pinning discipline itself surfaced while doing this and are
also fixed:

- **Comments disagreed with the SHAs they annotated.** The refs carried four
  different comment styles — `# v4`, `# v4.4.0`, `# v4 reference resolved
  2026-09-13`, and none at all. Rotating the SHA alone would have left 21 refs
  asserting a version they no longer were. All 48 are now normalized to the
  resolved tag.
- **The same literals were duplicated into three contract tests** — exactly the
  F1b failure mode. They were rotated in the same change and a test now fails if
  a retired pin reappears anywhere under `tests/`.

`tests/foundation/test_workflow_action_pins.py` (9 tests) makes the property
executable: every `uses:` reference is a full 40-char SHA, is in a table of pins
this repository has resolved to a Node 24 release, carries a comment agreeing
with that SHA, and every `uses:` line is parsed so a malformed one cannot vanish
from the audit. Proved load-bearing by mutation — reverting one checkout pin to
the retired SHA, annotating a v5.1.0 SHA as v4.4.0, and substituting the mutable
tag `actions/checkout@v5` each produce failures; restoring passes.

**Verified on the runner by controlled comparison.** The identical annotation
query was run against both commits:

| Commit | Runs sampled | Node 20 deprecation annotation |
| --- | --- | --- |
| `f813a5c` (old pins) | 35214660202, 35214660234, 35214660271 | **present in all 3**, naming `actions/checkout@11d5960a…` and `actions/upload-artifact@ea165f8d…` |
| `e8da889` (new pins) | 35218007896, 35218008053, 35218007835, 35218007901 | **absent in all 4** |

The new pins also did not disturb the workflows that depend on them most: the
key-custody and independent-recovery runs, which pass artifacts between jobs
through `upload-artifact`/`download-artifact`, both passed
(35218007872, 35218007835).

---

## 3. What remains

### 3.1 Engineer-executable — but it must be executed, not asserted

**The active branch has no hosted evidence.** This is the single largest open
item and it is stated plainly rather than papered over: every hosted run in this
repository executed on an earlier session branch. Nothing here is a run on
`arena/01a0aef4-tofel-house-erp`.

To close it: re-run `foundation-runtime.yml`, `foundation-runner.yml`,
`placement-content.yml`, `foundation-frontend-review.yml` and
`d8-operations-contract.yml` on the active branch, then set
`ACTIVE_RUNTIME_STATE = "EXECUTED"`, pin the real run id in
`ACTIVE_RUNTIME_RUN`, and replace the active ledger block with the observed
results in the same change. Expected outcome on current pins: Foundation runtime
still **fails** SEC-DEPS-01. Re-running will not turn it green and must not be
presented as if it might.

### 3.2 Owner-gated — engineering cannot start these without inventing policy

Unchanged from the existing decision packet, now including D11:

| Gate | Decision required | Blocks |
|---|---|---|
| D1 | Level vocabulary, sections/components, rubrics, cutoffs, grading scales | A06 academic assessment |
| D2 | Remaining payroll posting scope (framework already shipped) | A09 full payroll |
| D3 | Partial-refund terms, Fees-side correction scope | Finance correction v2 |
| D4 | Identity/merge/activation, guardian delegation | A02/A03, SEC-GUARDIAN-01 |
| D5 | Intake calendars, repeat/transfer/withdrawal semantics | A05/A11 |
| D6 | Tax configuration; payment gateway (currently "none") | Tax, payments |
| D7 | Metric stewards, denominators, disclosure, retention | A12 metrics layer |
| D8 | Provider/edge, off-site destination, numeric capacity/availability, numeric RPO/RTO | Production operations |
| **D11** | **Product license (new)** | **Distribution of the owned app** |

### 3.3 Deployment-gated — cannot be closed from a repository

Measured restart downtime, HA, cross-provider/region recovery, key custody in a
real trust boundary (KMS/HSM/owner secret store), session revocation on recovery,
measured RPO/RTO against a selected objective, full-bundle upgrade and rollback,
public TLS/proxy qualification, capacity, and deployed monitoring operation.
Running these "somewhere else" would be evidence theater; they stay BLOCKED until
an authorized deployment target exists.

### 3.4 Upstream-blocked

**SEC-DEPS-01** remains UPSTREAM-BLOCKED / REJECT. It was not weakened, waived
or reinterpreted by this review, and no dependency was forced, overridden,
forked or suppressed. No credible official upstream candidate passes the gate
yet.

---

## 4. Staged follow-ups (not done, and why)

1. **Wider lint rules.** `B023` (6 closures capturing loop variables in
   `tools/placement/native_checks.py`) is a real bug class, but every instance is
   currently called within its own iteration, and that 3,432-line file is the
   primary hosted qualification harness. Changing its lambda signatures is
   mechanical but **cannot be verified in this environment**, so it was left
   alone rather than shipped unverified. Do it as its own change with a hosted
   placement run behind it.
2. **`BLE001` blind excepts (32)** — mostly in tooling; each needs a decision
   about what should propagate, not a blanket `# noqa`.
3. **`S608` SQL fragments (10)** — all in the hosted runtime probes
   (`runtime_durability.py` 4, `runtime_independent_source.py` 2,
   `runtime_key_custody_operator.py` 2, `runtime_independent_target.py` 1,
   `runtime_key_custody_recovery.py` 1), where the interpolated table/database
   name is a module-level constant and no request input reaches the string.
   `apps/toefl_house/toefl_house/permissions.py` builds
   `permission_query_conditions` SQL too and is **not** flagged — its only
   interpolated value goes through `frappe.db.escape`. Reviewed and considered
   safe as written; a narrow rule exemption carrying that reasoning is the right
   follow-up, not a rewrite.
4. **Import ordering (`I001`, 123)** — cosmetic; enable after the correctness
   rules have bedded in so the diff stays reviewable.

---

## 5. Diff summary

- `tools/session_branch.py` — boundary rotated; explicit execution-state model;
  declared historical-branch list.
- `tools/foundation/d8_validate.py` — `validate_ledger` split into
  `validate_active_branch_qualification` + `validate_provenance_block`; identity
  rejection; report discloses the active-branch execution state.
- `docs/engineering/foundation-production-acceptance-ledger.json` — ordered
  provenance chain (`active` / `prior` / `earlier`); every run, check, commit and
  SHA-256 identity preserved byte-for-byte; nothing re-executed or re-labelled.
- 10 workflows rotated; `owned-suite.yml` added.
- `tools/placement/recover_evidence.py` — undefined name fixed.
- `tools/foundation/release_readiness_evidence.py` — safe extraction; computed
  evidence now recorded instead of discarded.
- 7 unused imports / variables removed across 5 files.
- New tests: `test_branch_boundary.py` (7), `test_app_assembly.py` (11),
  `test_owned_suite_gate.py` (6), `ActiveBranchEvidenceTests` (8),
  `SafeExtractionTests` (4) — 629 → **665**.
- Docs: `BRANCH-RECONCILIATION.md` rotation record, D11 in the canonical record
  and `OWNER-DECISIONS.md`, current-status headers rotated.

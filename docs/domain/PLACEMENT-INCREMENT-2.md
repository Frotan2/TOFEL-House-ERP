# Placement — increment 2 implementation record (blueprint/policy configuration)

Date: 2026-09-14 · Session branch: `arena/01a0a055-tofel-house-erp` · Baseline: `857352e4afa74f6eb300b75fb8e50a8e8e036fdd`

**Status: IN PROGRESS — see the Evidence section for executed results. Synthetic-data
implementation only, authorized for the bounded isolated build. Production remains
REJECT. F01–F05 remain CLOSED/APPROVED; no policy value is invented or reopened.**

This records increment 2 of the vertical-increment sequence in
[PLACEMENT-TECHNICAL-SPEC.md](PLACEMENT-TECHNICAL-SPEC.md) §1/§4.2 and
[PLACEMENT-TECHNICAL-READINESS.md](PLACEMENT-TECHNICAL-READINESS.md) §4.2:
`protected identity/config/content → allocation/response/clock → …`. Increment 1
(content governance) is unchanged except for the shared audit/permission/operation
machinery extensions below.

## 1. What was implemented

The **Blueprint / Policy Revision** aggregate from spec §3, using the same security
architecture as increment 1 (server-created command context, HMAC-bound idempotency
receipts, append-only audit, deny-by-default permissions, bounded whole-command
retry, two-site synthetic isolation gate):

- **Records:** `TH Placement Blueprint Revision` and `TH Placement Policy Revision`
  (hash-named, `synthetic=1` read-only flag, unique `(code, revision)`,
  `Draft → Reviewed → Published → Retired`, immutable `review_actor`,
  `content_hash` over the canonical definition). `TH Placement Audit Event` gains an
  optional `target` field; an event references exactly one of
  `item_revision` / `target` (controller invariant). `item_revision`/`after_key`
  become optional DocType fields with per-action requirements enforced in the
  owned controller.
- **Commands (authenticated POST, native session + CSRF):**
  `create_draft_config`, `revise_draft_config`, `review_config`, `publish_config`,
  `retire_config` — each with `config` ∈ {`blueprint`, `policy`} (any other value
  denied). Author = document owner for create/revise (Draft only); review,
  publish and retire require `Placement Publisher`, a different actor from the
  owner; publish additionally requires a different actor from the recorded
  `review_actor` and re-validates the stored definition and hash before freezing
  meaning. Expected-version CAS on every transition.
- **Validation (pure, `policy.py`):** exact-field bounded definitions; blueprint
  sections (1–12) with unique ids, six-skill/mode enums, bounded minutes/item
  counts, and `total_minutes == Σ section minutes` (contradictory quotas fail
  closed); policy parameters as bounded integers (structural ranges only — no
  institutional value is encoded, and no withdrawn 70%/16+/hard-attempt-cap
  default can be represented). Fixture values are explicitly non-operational.
- **Fail-closed activation:** only `Published` revisions are ever eligible for a
  later allocation increment to pin; draft/reviewed/retired/missing/contradictory
  configuration enables nothing. No candidate, scoring, timing, media, result or
  retention capability exists in this increment.
- **Harness:** the branch-restricted hosted qualification runner
  (`.github/workflows/placement-content.yml`, `tools/placement/run_native.py`) is
  re-scoped from the previous session branch to `arena/01a0a055-tofel-house-erp`
  (identical lock discipline: hosted runner, exact pinned native commits, two
  disposable synthetic sites, no local/production execution).
  `tools/placement/native_checks.py` retains every increment-1 scenario verbatim
  and adds increment-2 native and HTTP scenarios.

## 2. Files changed (increment 2)

| File | Change |
|---|---|
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_blueprint_revision/*` | new DocType (json/py/init) |
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_policy_revision/*` | new DocType (json/py/init) |
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_audit_event/th_placement_audit_event.json` | optional `item_revision`/`after_key`, new `target` |
| `apps/toefl_house/toefl_house/api.py` | five config commands over the shared `_execute` engine; kind→role generalization |
| `apps/toefl_house/toefl_house/security.py` | `KIND_ROLES` map; new kinds/DocTypes; `require_command` uses the map |
| `apps/toefl_house/toefl_house/policy.py` | `validate_blueprint`, `validate_policy`, `validate_config_code`, state-machine data, `can_read` extension |
| `apps/toefl_house/toefl_house/controllers.py` | config lifecycle invariants; audit target XOR invariant |
| `apps/toefl_house/toefl_house/permissions.py` | blueprint/policy kinds, tables, query conditions |
| `apps/toefl_house/toefl_house/hooks.py` | hook registrations for the two new DocTypes |
| `apps/toefl_house/toefl_house/install.py` | unique `(code, revision)` constraints; status/creation and audit-target indexes |
| `apps/toefl_house/README.md` | increment-2 boundary documentation |
| `tests/placement/test_config_policy.py` | new pure local unit tests |
| `tools/placement/native_checks.py` | increment-2 hosted acceptance scenarios (+ increment-1 regression) |
| `.github/workflows/placement-content.yml` | branch lock re-scoped to this session branch |
| `tools/placement/run_native.py` | branch lock re-scoped to this session branch |

## 3. Evidence

<!-- Filled from actual execution output only; no inferred or relabeled results. -->

- Local pure unit tests, executed in the session workspace on 2026-09-14:
  - `python3 -m unittest discover -s tests/placement -v`: **47/47 OK**
    (18 increment-1 content policy, 7 transactions, 22 increment-2 config
    policy/state/read-boundary tests).
  - `python3 -m unittest discover -s tests/foundation`: **OK** (unchanged).
  - `node tests/foundation/test_realtime_guard.cjs`: **PASS** (unchanged).
- Hosted qualification (`.github/workflows/placement-content.yml` on
  `arena/01a0a055-tofel-house-erp`):
  - Run `34859456825` (commit `1fbf2a474f7b87896fa73f17e4553a2d1c83e36e`):
    **FAILED at the "Pinned runner dependencies" step before any Frappe
    installation** — the shared foundation probe/evidence gates
    (`tools/foundation/runner_probe.py`, `tools/foundation/publish_evidence.py`)
    still matched only the previous session branch and exited before any
    download/service check. The "Owned local tests" step passed on the
    runner. Harness-gate fix in `1c53918`.
  - Run `34861078186` (commit `1c5391826a972335438f379ce92e168c63d9fe70`):
    probe passed; pinned installs, both site installations and migrations
    **succeeded**; the native acceptance step then ran **57 of 58 checks to
    completion, all earlier checks pass**, and failed at
    `config-ignore-permissions-does-not-bypass-controller` with
    `AttributeError: module 'toefl_house.api' has no attribute 'BP'` —
    `tools/placement/native_checks.py` referenced `api.BP` while
    `toefl_house/api.py` exports `BLUEPRINT` (14 occurrences). Fixed by
    renaming the references to `api.BLUEPRINT` and adding a local AST guard
    test (`tests/placement/test_native_check_names.py`) that fails locally if
    any `api.*` name used by the hosted native checks is missing from
    `api.py`. Re-qualification triggered by that fix commit.
- Baseline for increment 1: hosted run `34851805904` (success, parent branch
  `arena/01a09bf3-tofel-house-erp`, head `092a06d2b3d597f42ccd858f2e99d2732f32cd19`).

## 4. Known limitations (unchanged boundary)

- Hosted runner evidence is the only runtime qualification; local unit tests do not
  qualify native Frappe/MariaDB/Redis/HTTP behavior.
- Controller invariants constrain generic CRUD/RPC/`ignore_permissions` writes;
  privileged raw SQL/Python (trusted operator shell) remains governed
  administration, not tamper-proof storage (spec S5).
- All fixture content is synthetic and non-operational; owner artifacts P1–P5,
  empirical validation and the real-data gate remain prerequisites before any
  operational use. Browser qualification, allocation, scoring, delivery, release
  and retention capabilities are not implemented and remain disabled.

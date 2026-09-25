# Active-branch runtime state: the transition criterion can no longer be met

Date: 2026-09-25. Dated finding record; no verdict was changed by this work.

## 1. What was observed

Two independent push-triggered Foundation runtime runs on the active
validation branch have now run to completion, with the same shape both times.
This is no longer a single observation.

| | run `36114770663` | run `36119457187` |
|---|---|---|
| commit | `8918403` | `2f67140` |
| conclusion | success | success |
| executed checks | 123, all `pass` | 123, all `pass` |
| report `status` | `"pass"` | `"pass"` |
| `security_gate_passed` | `False` | `False` |
| `phase2_gate_passed` | `False` | `False` |
| `product_implementation_authorized` | `False` | `False` |
| `hardened_profile_passed` | `True` | `True` |
| `stack_dependency_audit.status` | `"pass"` | `"pass"` |
| OSV findings listed | 14 | 14 |

Both evidence reports were verified against their recorded
`report_sha256` before being read. The stack audit in each lists real OSV
findings (GHSA/PYSEC records against `pdfkit` 1.0.0, `pypdf` 6.15.0 and
others); see
[`sec-deps-01/triage-integrity-verification-2026-09-25.md`](sec-deps-01/triage-integrity-verification-2026-09-25.md)
for why reporting `pass` alongside findings is the triage mechanism working as
designed and not a dead gate.

Nothing here is a weakening. The gate verdicts are unchanged:
`runtime_install.py` sets `security_gate_passed = False` unconditionally, with
the comment "broader roles, advisories and remaining security gates still
required", and `d8_validate.py` still reports D8 `BLOCKED`, production
`REJECT` and `sec_deps` `UPSTREAM-BLOCKED / REJECT`.

## 2. Why the pin did not advance

`tools/session_branch.py` carries two statements of the transition criterion
and they disagree.

The 2026-09-24 rotation note says the state is
`NOT_EXECUTED_ON_THIS_BRANCH` "until the first post-rotation push runs the
runtime to completion". Read literally, that condition is now satisfied.

The enforced criterion is in `d8_validate.validate_active_branch_qualification`:

```python
if runtime.get("status") != "fail_reject" or runtime.get("run") != ACTIVE_RUNTIME_RUN:
    raise ContractError("acceptance ledger latest runtime evidence drifted")
```

So the pinned run must be a `fail_reject` run. Both runs report `pass`.
Advancing the pin on completion alone would make the validator raise, and
would also require populating the acceptance ledger's
`active_branch_qualification` block with a run whose recorded status does not
match the rule.

The pin was therefore left as `NOT_EXECUTED_ON_THIS_BRANCH` with
`ACTIVE_RUNTIME_RUN = None`, and the ledger was left untouched.

## 3. The underlying problem

No tool ever writes `fail_reject`. It appears only as a value `d8_validate.py`
asserts and as a classification recorded by hand in the acceptance ledger from
an observed rejection — which is how the two prior branches' runs
(`35984767187`, `35451785714`) were recorded.

The runtime used to *reject*: `BRANCH-RECONCILIATION.md` records those runs
failing at the "Install and validate the pinned stack" step because of
SEC-DEPS-01, and that rejection was classified `fail_reject`.

Since the advisory-triage work, the runtime completes and reports `status:
"pass"` while keeping `security_gate_passed: False`. The rejection is now
expressed as a flag rather than as the run's status. The observed outcome no
longer has the shape the transition rule expects, so the state machine's input
changed shape and its transition became unreachable: every future push will
host a runtime execution while the baseline continues to assert that this
branch has no hosted execution.

## 4. Disposition

**OWNER DECISION REQUIRED — not actioned here.**

Two defensible readings, and choosing between them changes what counts as
active-branch qualification evidence, which is a release-contract question
rather than a bookkeeping one:

1. **Update the criterion.** Accept the current evidence shape as qualifying
   (runtime `status: "pass"` together with `security_gate_passed: False`), so
   `ACTIVE_RUNTIME_STATE` becomes `EXECUTED` with run `36114770663`. This
   requires changing `d8_validate.validate_active_branch_qualification`, the
   ledger's `active_branch_qualification` block, and the
   `NOT_EXECUTED_ON_THIS_BRANCH` assertions in `tests/d8/test_contract.py`
   (lines 181 and 345).
2. **Keep the criterion, record the non-qualifying execution.** Leave the pin
   as-is and record run `36114770663` as a completed execution that does not
   satisfy the rule, so the baseline stops implying no execution has happened.

Option 2 was partly applied here: the mismatch is now documented in
`tools/session_branch.py` so a future reader following the 2026-09-24 note
does not advance the pin and break the validator. Option 1 was deliberately
**not** applied, because it reinterprets what the release contract accepts and
would weaken a gate assertion without an owner decision.

No RPO/RTO, retention, capacity or acceptance threshold is asserted here, and
no value in `session_branch.py` or the acceptance ledger was changed.

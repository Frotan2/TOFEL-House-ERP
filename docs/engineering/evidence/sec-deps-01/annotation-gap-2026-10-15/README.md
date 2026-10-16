# Advisory annotation gap: 47 reported, 44 visible (resolved 2026-10-15)

## Question

The Foundation runtime header reports `advisory matches=160 in 47 packages`. The
annotations visible through the check-run API named 44 groups. Were three
advisory-bearing packages left untriaged?

## Finding

No. The three groups are not hidden from the gate. They are hidden from the
annotation text by the annotation budget, and the writer says so.

- `runtime_install.advisory_finding_annotations` emits at most `ANNOTATION_MAX_LINES = 9`
  lines of `ANNOTATION_TEXT_LIMIT = 700` characters, because GitHub keeps at most 10
  warning annotations per step.
- When the budget is exceeded the last line ends `... +N packages not shown`. The
  live annotation set for run `38672481320` (head `7c847da`) ends
  `... +3 packages not shown`.
- The three hidden groups are `npm:@tiptap/extension-link`, `npm:cookie`, and
  `npm:yaml`. Each is covered by a register entry (see the table below).

An earlier parse also reported 42 visible groups because its regex could not match
scoped names (`npm:@scope/name`). That was a parser bug, not a coverage gap. The
corrected parse (`reconcile_annotations.py`) shows 44 visible groups plus 3 hidden,
which equals the 47 expected groups.

## Reconciliation (exact)

| Measure | Value | Source |
|---|---|---|
| CI header groups | 47 (`in 47 packages`) | annotation, run 38672481320 |
| Replay groups | 40 npm packages + 7 Python name@version = 47 | `replay-snapshot.json` counts |
| Visible in annotations | 44 | `fnd_annotations_7c847da.json`, `reconcile_annotations.py` |
| Hidden by budget | 3 (`+3 packages not shown`) | same annotation |
| Replay groups with no register/delta entry | 0 | `tests/foundation/test_advisory_annotations.py` |

## The three hidden groups

| Package | Advisory (matched version) | Register disposition | Source |
|---|---|---|---|
| `@tiptap/extension-link` | GHSA-VHRC-HGRQ-X75R (low, 2.2.3) | BLOCKED (withdrawn from BROWSER_SELF_DENIAL by ERRATUM E6, 2026-10-15) | register, with delta `advisory-delta-2026-10-15` |
| `cookie` | GHSA-PXG6-PF52-XH8X (low, 0.4.2) | NOT_REACHABLE | register (2026-09-23) |
| `yaml` | GHSA-48C2-RRV3-QJMP (moderate, 1.10.2 and 2.3.4) | BUILD_ONLY | register (2026-09-23) |

`@tiptap/extension-link` was one of the BROWSER_SELF_DENIAL records. Review on 2026-10-15 found
its self-only premise false (ERRATUM E6), so it is now BLOCKED. The hidden group is therefore
open, and the gate stays red for it until containment is verified at runtime.

## Change made

- `runtime_install.py`: the group logic moved into `advisory_group_entries()`. The
  annotation writer still uses it, so annotation output is unchanged. New
  `advisory_summary_markdown()` and `write_advisory_step_summary()` append the full
  group list to `$GITHUB_STEP_SUMMARY` when the job runs in Actions. The summary has
  no annotation cap, and the owner can read it in the run UI.
- `tests/foundation/test_advisory_annotations.py`: `AdvisoryCompleteListTests` adds
  invariants (visible + hidden == total, summary has every group, replay reconciles to
  47, every replay group covered, the three named groups covered).

## Not yet verified

The step-summary output has not been observed on a hosted run. It is verified on the
next Foundation run of the PR branch. The summary is only readable in the run UI, so
the owner or a hosted-run check must confirm it.

## Reproduce

```
cd docs/engineering/evidence/sec-deps-01/annotation-gap-2026-10-15
python3 reconcile_annotations.py    # expects RECONCILED, exit 0
```

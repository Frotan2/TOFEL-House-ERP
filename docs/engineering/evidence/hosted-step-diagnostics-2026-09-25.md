# Hosted step diagnostics: a red step was not a diagnosis

Date: 2026-09-25
Scope: how a failing hosted Foundation step was made readable again, and what
the first readable results showed. No gate verdict was changed by this work.

## 1. The defect

Five hosted workflows were red, and every failing step annotated itself with
nothing more than:

```
Process completed with exit code 1.
```

A `run:` step's stdout and stderr exist only in the job log, which is a zip
served from `results-receiver.actions.githubusercontent.com`. Artifact
download, signed blob URLs and `gh run view --log` all EOF from the review
environment. Retrieving check-run annotations for the durability job
(`107625292471`) returned exactly two annotations: the downstream
`No files were found with the provided path:` symptom emitted by an
`if-no-files-found: error` upload step, and the exit-code line itself.

So the failing assertion did not exist anywhere reachable. A red step was an
**evidence loss**, not a diagnosis — it could not be triaged, only re-run.

## 2. The remedy

Two changes, both verdict-neutral.

`tools/foundation/annotated_step.py` wraps a step command. It streams output
to the job log unchanged, propagates the command's own exit code, and only
when the command fails replays the tail of its output as `::error` workflow
commands, which GitHub records as check-run annotations readable through the
plain REST API. Values registered with `::add-mask::` are redacted first.
Wired into every `python3` step of the seven D8 evidence and qualification
workflows. `placement-content` is deliberately excluded: it already pipes
every suite through `tee` into retained evidence under `set -o pipefail`, so
its failures are already readable from the artifact.

`tools/foundation/frontend_experiment.py` previously wrote its only diagnosis
to `result.json`, inside the undownloadable artifact, and printed nothing at
all. It now logs one line per check as it runs, logs the tail of a failing
check's own output, and emits `::error` annotations naming the last failed
check — following the existing `runtime_install.hosted_failure_annotations`
convention, so the cause survives even the job log.

Two bugs were found and fixed while building the wrapper, both caught by its
own streaming test: iterating a pipe uses a read-ahead buffer, and writing to
a piped stdout without flushing holds a whole step's output back until it
exits. Either alone would have left a twenty-minute step's log blank.

## 3. What became readable

### Foundation frontend candidate review — run `36114770675` @ `8918403`

The step had failed on twelve consecutive runs with no recorded cause. With
the instrumentation it reports:

```
comparison gate rejected the candidate:
  baseline:  advisories=57 constraint_issues=3
  candidate: advisories=23 constraint_issues=0
```

See [`frontend-candidate-review-2026-09-25.md`](frontend-candidate-review-2026-09-25.md)
for the full verdict and its disposition.

### Foundation datastore durability — historical failure at `2deba87`

The durability gate's step 3 failure is now explained without needing the lost
log. Commit `2deba87` re-pointed eleven workflows at the new active branch
while `tools/session_branch.py` still pinned the previous one, so
`test_workflow_is_restricted_to_the_active_branch` compared a new literal in
the workflow against an old literal in the canonical pin and failed on a pure
bookkeeping mismatch. No durability code or probe changed between the failing
run and the current tip.

The gate is green again at `8918403` with real container evidence (run
`36113793485`): MariaDB 11.8.9 and Redis 8.6.6 started from pinned image
digests on named volumes, graceful restart, SIGKILL crash recovery and
container destruction each preserved 25 committed rows with an identical
`payload_crc32_sum`, and the negative control — volume removed, container
recreated — found the table absent, confirming the data had lived in the
volume rather than the image.

The exposure is that a rotation lands as two commits, and every gate whose
contract asserts the branch literal is red in between. That is a real
recurrence risk for the next rotation; the durable fix is to make the rotation
atomic, not to relax the assertion.

## 4. Not changed

No verdict was weakened, waived or reinterpreted. The wrapper propagates exit
codes unchanged and adds nothing to a passing step. The frontend candidate's
`status` remains `fail`, and `publish_evidence.py` still publishes a failing
check run for it.

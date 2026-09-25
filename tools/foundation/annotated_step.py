#!/usr/bin/env python3
"""Run a hosted step and surface its real output when it fails.

GitHub Actions annotates a failed ``run:`` step with nothing more than
``Process completed with exit code 1``.  The step's own stdout/stderr only
ever exists in the job log, and that log is a large zip served from
``results-receiver.actions.githubusercontent.com`` — a host that is not
always reachable from every review environment.  When it is not, a red
step is an evidence loss rather than a diagnosis: nobody can tell which
guard broke.

This wrapper is the fix for that specific failure mode.  It runs the step
command, streams its output to the job log exactly as before, and — only
when the command fails — replays the tail of that output as ``::error::``
workflow commands, which GitHub records as check-run annotations and which
are readable through the plain REST API.

It is deliberately *not* a gate change:

* the exit code of the command is propagated unchanged, so a failing step
  still fails the job;
* a passing command produces no annotations at all;
* output is redacted before it is annotated, so masked values cannot leak
  into a check-run message.

Usage::

    python3 tools/foundation/annotated_step.py <label> -- <command> [args...]
"""
from __future__ import annotations

import subprocess
import sys

# GitHub keeps at most ten annotations per step, and when a step emits more it
# keeps an arbitrary subset. Replaying the whole tail therefore loses the very
# lines that matter: on a unittest failure the forty trailing lines were mostly
# "... ok" and the FAILED summary was dropped. Emit few lines, chosen for
# being diagnostic rather than merely recent, and emit them best-first so the
# cap discards the least useful.
MAX_ANNOTATION_LINES = 8
MAX_LINE_CHARS = 480

# Ordered most specific first. A failing test names itself with FAIL:/ERROR:,
# states the assertion, and finishes with a FAILED (...) or Ran N tests line.
DIAGNOSTIC_PATTERNS = (
    r"^\s*(FAIL|ERROR):\s",
    r"^\s*E\s+\S",
    r"^\s*\w*(Error|Exception|Failure):",
    r"^\s*(FAILED|OK)\b",
    r"^\s*Ran \d+ tests?",
    r"\bAssertionError\b",
)


def escape(value: str) -> str:
    """Escape a value for a GitHub workflow command message."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def masked_values(output: str) -> list[str]:
    """Collect values the step asked GitHub to mask.

    Steps such as ``runtime_key_custody_custodian.py`` print
    ``::add-mask::<value>``.  Anything registered there must not be replayed
    into an annotation, so it is redacted before the output is republished.
    """
    values = []
    for line in output.splitlines():
        marker = "::add-mask::"
        if line.startswith(marker):
            value = line[len(marker):].strip()
            # A mask line with no value masks nothing; ignore it.
            if value:
                values.append(value)
    return values


def redact(output: str) -> str:
    for value in masked_values(output):
        output = output.replace(value, "[REDACTED]")
    return output


# Lines that are already workflow commands. Several hosted tools emit their
# own ``::error::`` lines (see runtime_install.hosted_failure_annotations),
# because that convention predates this wrapper. Replaying one inside a
# ::error message would nest two commands on a line and produce a garbled
# annotation, so such lines are left to stand on their own.
WORKFLOW_COMMAND_PREFIXES = ("::error", "::warning", "::notice", "::debug", "::group::", "::endgroup::")


def select_diagnostic_lines(output: str, limit: int = MAX_ANNOTATION_LINES) -> list[str]:
    """Choose the lines that explain the failure, best first.

    A passing unittest run prints thousands of "... ok" lines; the tail of a
    failed run is mostly those too. Blindly replaying the tail therefore
    annotates noise and, once the ten-annotation cap drops some, can omit the
    failure entirely. Lines that name a failure are chosen over lines that
    merely precede it.
    """
    import re

    lines = output.splitlines()
    chosen: list[str] = []
    for pattern in DIAGNOSTIC_PATTERNS:
        for line in lines:
            if re.search(pattern, line) and line not in chosen:
                chosen.append(line)
    if not chosen:
        # Nothing looked like a failure report; the end of the output is then
        # the only signal available.
        chosen = lines[-limit:]
    return [line[:MAX_LINE_CHARS] for line in chosen[:limit]]


def run(argv: list[str]) -> int:
    """Run the command, stream it, annotate on failure, return its exit code."""
    if "--" not in argv:
        print("usage: annotated_step.py <label> -- <command> [args...]", file=sys.stderr)
        return 2
    split = argv.index("--")
    label = " ".join(argv[:split]).strip() or "step"
    command = argv[split + 1:]
    if not command:
        print("annotated_step: no command given after --", file=sys.stderr)
        return 2

    print(f"::group::{label}", flush=True)
    # Stream line by line rather than buffering. Some wrapped steps run for
    # twenty minutes; capturing their output would leave the job log blank
    # for the duration and hide the progress the log exists to show.
    process = subprocess.Popen(command, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    chunks = []
    assert process.stdout is not None
    # readline(), never `for line in process.stdout`: iterating a pipe uses a
    # read-ahead buffer that withholds output until the buffer fills or the
    # child exits, which would reintroduce exactly the blank-log problem this
    # streaming exists to prevent.
    while True:
        line = process.stdout.readline()
        if not line:
            break
        sys.stdout.write(line)
        # Flush per line: when this tool's own stdout is a pipe, Python
        # block-buffers it, so writing without flushing would hold the whole
        # step's output back until it exits.
        sys.stdout.flush()
        chunks.append(line)
    sys.stdout.flush()
    returncode = process.wait()
    print("::endgroup::", flush=True)
    sys.stdout.flush()

    if returncode == 0:
        return 0

    combined = redact("".join(chunks))
    title = escape(label)
    lines = [line for line in select_diagnostic_lines(combined)
             if not line.startswith(WORKFLOW_COMMAND_PREFIXES)]
    # The summary goes first: when the ten-annotation cap discards something,
    # it must be a detail rather than the fact of the failure.
    print(f"::error title={title}::{escape(f'step failed with exit code {returncode}')}",
          flush=True)
    if not lines:
        # Nothing plain to replay. Say so plainly rather than emitting an
        # empty annotation, which would look like a tooling error.
        lines = ["(the step produced no plain output before failing; if it "
                 "emitted annotations of its own, they are recorded above)"]
    for line in lines:
        print(f"::error title={title}::{escape(line)}", flush=True)
    return returncode


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())

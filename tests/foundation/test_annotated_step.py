"""Contract for tools/foundation/annotated_step.py.

A red hosted step that reports only "Process completed with exit code 1" is an
evidence loss, not a diagnosis, because the job log lives in a zip on a host
that is not always reachable. This wrapper is the remedy, so its own behaviour
is pinned: it must not change any verdict, must not invent annotations for a
passing step, and must never republish a value the step asked to be masked.
"""
import subprocess
import time
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools"))

import annotated_step  # noqa: E402

TOOL = ROOT / "tools" / "foundation" / "annotated_step.py"


def run_tool(*args):
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, cwd=str(ROOT))


class ExitCodePropagationTests(unittest.TestCase):
    """The wrapper must never change the verdict of the step it wraps."""

    def test_a_passing_command_propagates_zero_and_emits_no_annotation(self):
        completed = run_tool("passing", "--", sys.executable, "-c", "print('hello')")
        self.assertEqual(completed.returncode, 0)
        self.assertIn("hello", completed.stdout)
        self.assertNotIn("::error::", completed.stdout)

    def test_a_failing_command_propagates_its_own_exit_code(self):
        completed = run_tool("failing", "--", sys.executable, "-c", "import sys;sys.exit(3)")
        self.assertEqual(completed.returncode, 3)

    def test_a_failing_command_still_prints_its_output_to_the_job_log(self):
        """The job log must not get worse by wrapping the step."""
        completed = run_tool("failing", "--", sys.executable, "-c",
                             "import sys;print('the real cause');sys.exit(1)")
        self.assertIn("the real cause", completed.stdout)

    def test_a_missing_separator_is_rejected(self):
        self.assertEqual(run_tool("no-separator").returncode, 2)
        self.assertEqual(run_tool("empty", "--").returncode, 2)


class AnnotationContentTests(unittest.TestCase):
    def test_the_failure_reason_reaches_the_annotations(self):
        completed = run_tool("failing", "--", sys.executable, "-c",
                             "import sys;print('AssertionError: guard X broke');sys.exit(1)")
        self.assertIn("::error", completed.stdout)
        self.assertIn("AssertionError: guard X broke", completed.stdout)

    def test_stderr_is_annotated_not_only_stdout(self):
        """A traceback lands on stderr and is exactly what must be visible."""
        completed = run_tool("failing", "--", sys.executable, "-c",
                             "import sys;sys.stderr.write('Traceback: boom\\n');sys.exit(1)")
        self.assertIn("Traceback: boom", completed.stdout)

    def test_annotation_text_is_escaped_for_workflow_commands(self):
        """A literal newline or % in output would corrupt the annotation."""
        completed = run_tool("failing", "--", sys.executable, "-c",
                             "import sys;print('50% done\\nsecond line');sys.exit(1)")
        self.assertIn("50%25 done", completed.stdout)
        self.assertNotIn("50% done", completed.stdout.split("::error")[-1])

    def test_empty_failure_output_is_stated_not_silently_dropped(self):
        completed = run_tool("failing", "--", sys.executable, "-c", "import sys;sys.exit(1)")
        self.assertIn("no plain output before failing", completed.stdout)

    def test_the_label_appears_in_every_annotation(self):
        completed = run_tool("durability guards", "--", sys.executable, "-c",
                             "import sys;print('boom');sys.exit(1)")
        lines = [line for line in completed.stdout.splitlines() if line.startswith("::error")]
        self.assertTrue(lines, "no annotation was produced")
        for line in lines:
            self.assertIn("durability guards", line)

    def test_a_label_containing_reserved_characters_is_escaped(self):
        completed = run_tool("step 100%", "--", sys.executable, "-c",
                             "import sys;print('boom');sys.exit(1)")
        for line in completed.stdout.splitlines():
            if line.startswith("::error"):
                self.assertIn("100%25", line)


class StreamingTests(unittest.TestCase):
    """Some wrapped steps run for twenty minutes.

    Buffering their output would leave the job log blank for the whole run,
    which is the opposite of what the log is for, so output must be streamed
    as it is produced and still be available to annotate afterwards.
    """

    def test_output_is_streamed_before_the_step_finishes(self):
        script = ("import sys,time\n"
                  "print('early', flush=True)\n"
                  "time.sleep(3)\n"
                  "print('late', flush=True)\n"
                  "sys.exit(1)\n")
        started = time.monotonic()
        process = subprocess.Popen(
            [sys.executable, str(TOOL), "streaming", "--", sys.executable, "-c", script],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(ROOT))
        assert process.stdout is not None
        # The first line must arrive well before the step completes.
        # Skip the ::group:: marker the wrapper opens the step with.
        seen = []
        while True:
            line = process.stdout.readline()
            if not line:
                break
            if "early" in line:
                seen.append(line)
                break
        elapsed = time.monotonic() - started
        self.assertTrue(seen, "the step never streamed its first line")
        self.assertLess(elapsed, 2.5,
                        "output was buffered rather than streamed; a long step "
                        "would show an empty log for its whole duration")
        rest = process.communicate()[0]
        self.assertIn("late", rest)
        self.assertNotEqual(process.returncode, 0)

    def test_stderr_is_merged_into_the_streamed_output(self):
        completed = run_tool("merging", "--", sys.executable, "-c",
                             "import sys;sys.stderr.write('on stderr\\n');sys.exit(1)")
        self.assertIn("on stderr", completed.stdout)


class ExistingAnnotationTests(unittest.TestCase):
    """Some tools emit their own ::error:: lines; that convention predates
    this wrapper. Replaying one inside a ::error message would nest two
    commands on a line and produce a garbled annotation."""

    def test_lines_that_are_already_annotations_are_not_replayed(self):
        script = ("print('::error file=x.py::last failed check: clone')\n"
                  "print('plain context line')\n"
                  "sys.exit(1)\n")
        completed = run_tool("nesting", "--", sys.executable, "-c",
                             "import sys;" + script)
        self.assertIn("plain context line", completed.stdout)
        self.assertNotIn("::error title=nesting::::error", completed.stdout)

    def test_a_step_whose_only_output_was_annotations_still_says_so(self):
        completed = run_tool("only-annotations", "--", sys.executable, "-c",
                             "import sys;print('::error file=x.py::boom');sys.exit(1)")
        self.assertIn("no plain output", completed.stdout)


class RedactionTests(unittest.TestCase):
    """A value the step masked must never be republished in a check run."""

    def test_a_masked_value_is_not_annotated(self):
        script = "\n".join([
            "import sys",
            "print('::add-mask::supersecret')",
            "for index in range(200):",
            "    print('test_%d ... ok' % index)",
            "print('FAIL: test_the_gate (tests.x.Y)')",
            "print('AssertionError: expected supersecret but got other')",
            "print('FAILED (failures=1)')",
            "sys.exit(1)",
        ])
        completed = run_tool("failing", "--", sys.executable, "-c", script)
        annotations = completed.stdout[completed.stdout.index("::error"):]
        self.assertNotIn("supersecret", annotations)
        self.assertIn("[REDACTED]", annotations)

    def test_masking_does_not_hide_the_structure_of_the_failure(self):
        script = ("import sys;"
                  "print('::add-mask::supersecret');"
                  "print('AssertionError: expected supersecret but got other');"
                  "sys.exit(1)")
        completed = run_tool("failing", "--", sys.executable, "-c", script)
        annotations = completed.stdout[completed.stdout.index("::error"):]
        self.assertIn("AssertionError", annotations)

    def test_an_empty_mask_marker_is_ignored(self):
        self.assertEqual(annotated_step.masked_values("::add-mask::\n"), [])
        self.assertEqual(annotated_step.masked_values("::add-mask::value\n"), ["value"])


class DiagnosticSelectionTests(unittest.TestCase):
    """GitHub keeps at most ten annotations per step and discards the rest
    arbitrarily, so a blind replay of the tail loses the failure itself:
    a unittest run ends in hundreds of "... ok" lines. The lines that name a
    failure must be chosen over the lines that merely precede it."""

    def test_a_failure_is_chosen_over_surrounding_passing_noise(self):
        output = "\n".join(
            [f"test_{i} ... ok" for i in range(300)]
            + ["FAIL: test_the_gate (tests.x.Y)",
               "AssertionError: expected 1 but got 2",
               "FAILED (failures=1)"])
        chosen = annotated_step.select_diagnostic_lines(output)
        self.assertIn("FAIL: test_the_gate (tests.x.Y)", chosen)
        self.assertIn("AssertionError: expected 1 but got 2", chosen)
        self.assertIn("FAILED (failures=1)", chosen)
        self.assertTrue(all("... ok" not in line for line in chosen))

    def test_the_annotation_count_stays_inside_the_github_cap(self):
        output = "\n".join([f"FAIL: test_{i}" for i in range(100)])
        self.assertLessEqual(len(annotated_step.select_diagnostic_lines(output)),
                             annotated_step.MAX_ANNOTATION_LINES)
        self.assertLessEqual(annotated_step.MAX_ANNOTATION_LINES, 10)

    def test_without_a_recognised_failure_the_tail_is_used(self):
        output = "\n".join(f"line {i}" for i in range(500))
        chosen = annotated_step.select_diagnostic_lines(output)
        self.assertIn("line 499", chosen)
        self.assertNotIn("line 0", chosen)

    def test_overlong_lines_are_clipped(self):
        chosen = annotated_step.select_diagnostic_lines("x" * 5000)
        self.assertLessEqual(max(len(line) for line in chosen),
                             annotated_step.MAX_LINE_CHARS)

    def test_the_end_to_end_annotation_names_the_failed_test(self):
        script = "\n".join([
            "import sys",
            "for index in range(200):",
            "    print('test_%d ... ok' % index)",
            "print('FAIL: test_the_gate (tests.x.Y)')",
            "print('AssertionError: expected 1 but got 2')",
            "print('FAILED (failures=1)')",
            "sys.exit(1)",
        ])
        completed = run_tool("suite", "--", sys.executable, "-c", script)
        annotations = completed.stdout[completed.stdout.index("::error"):]
        self.assertIn("FAIL: test_the_gate", annotations)
        self.assertIn("FAILED (failures=1)", annotations)
        self.assertIn("AssertionError: expected 1 but got 2", annotations)
        self.assertNotIn("... ok", annotations)
        # Inside the cap, so nothing important can be discarded.
        self.assertLessEqual(annotations.count("::error"), 10)


class WiringTests(unittest.TestCase):
    """Every hosted step that can fail must be wrapped, or the wrapper is inert."""

    # Every workflow whose python steps can fail and take their only copy of
    # the explanation into an unretrievable job log.
    #
    # Steps piped into `tee` are exempt: their output is retained as evidence
    # under .foundation/, so a failure is already readable from the artifact.
    # That exemption was once claimed for all of placement-content, but only
    # its unit-test block is tee'd; its runner_probe, run_native and publish
    # steps were not, and are now wrapped. The exemption is therefore matched
    # on the `tee` itself rather than on the workflow, so it cannot be claimed
    # for a step that does not have one.
    WORKFLOWS = ("foundation-durability", "foundation-key-custody",
                 "foundation-independent-recovery", "foundation-operational-boundaries",
                 "foundation-frontend-review", "foundation-runner",
                 "foundation-runtime", "owned-suite", "placement-content",
                 "d8-operations-contract", "placement-evidence")

    def test_no_workflow_with_python_steps_is_silently_dropped(self):
        """The list above is the coverage boundary, so dropping an entry from
        it would silently disable the check for that whole workflow.

        There is deliberately no exemption mechanism. Two exemptions were
        claimed in this file at earlier points and both were false: the
        placement-content claim ("every suite is tee'd") covered only its
        unit-test block, and the d8-operations-contract claim ("steps call
        runtime_install.py") named a script it never runs. A workflow that
        runs python is wrapped, or the list is changed in a reviewable diff.
        """
        python_workflows = {
            path.stem for path in (ROOT / ".github" / "workflows").glob("*.yml")
            if "python3" in path.read_text(encoding="utf-8")
        }
        self.assertEqual(sorted(python_workflows - set(self.WORKFLOWS)), [],
                         "a workflow runs python but is not in the wrapped "
                         "list: " + ", ".join(sorted(python_workflows - set(self.WORKFLOWS))))

    def test_every_hosted_python_step_is_wrapped(self):
        unwrapped = []
        for name in self.WORKFLOWS:
            path = ROOT / ".github/workflows" / (name + ".yml")
            self.assertTrue(path.exists(), f"{name} is missing")
            lines = path.read_text(encoding="utf-8").splitlines()
            index = 0
            while index < len(lines):
                line = lines[index]
                stripped = line.strip()
                indent = len(line) - len(line.lstrip())
                # A `run: >-` folded scalar continues on following, more
                # deeply indented lines. Treat the whole block as one step.
                if stripped == "run:" or stripped.startswith("run: >"):
                    block, cursor = [], index + 1
                    while cursor < len(lines):
                        candidate = lines[cursor]
                        if not candidate.strip():
                            break
                        if len(candidate) - len(candidate.lstrip()) <= indent:
                            break
                        block.append(candidate)
                        cursor += 1
                    joined = " ".join(part.strip() for part in block)
                    if joined.startswith("python3 ") and "annotated_step.py" not in joined:
                        unwrapped.append(f"{name}: {joined[:90]}")
                    index = cursor
                    continue
                if not stripped.startswith("python3 ") or "annotated_step.py" in line:
                    index += 1
                    continue
                # A `python3 - <<'PY'` step reads its script from stdin.
                # Its assertions already name the offending value, and
                # wrapping it would risk the heredoc reaching the wrong
                # process, so it is a documented exception.
                if "<<" in stripped:
                    index += 1
                    continue
                # Output retained by `tee` is readable from the artifact even
                # when the job log is not, so the wrapper adds nothing.
                if "| tee" in stripped or "|tee" in stripped:
                    index += 1
                    continue
                unwrapped.append(f"{name}: {stripped[:90]}")
                index += 1
                continue
                index += 1
        self.assertEqual(unwrapped, [],
                         "an unwrapped python step can fail with no readable cause: "
                         + "; ".join(unwrapped))

    def test_the_tool_itself_is_present_and_executable(self):
        self.assertTrue(TOOL.exists())
        completed = run_tool("self check", "--", sys.executable, "-c", "pass")
        self.assertEqual(completed.returncode, 0)


if __name__ == "__main__":
    unittest.main()

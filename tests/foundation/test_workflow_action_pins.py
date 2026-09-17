"""Every workflow action must be pinned to a commit that GitHub will still run.

GitHub deprecated the Node.js 20 runtime on 2025-09-19. Actions that declare
``runs.using: node20`` are now *forced* onto Node 24, and every run in this
repository carried the warning:

    Node.js 20 is deprecated. The following actions target Node.js 20 but are
    being forced to run on Node.js 24: actions/checkout@11d5960a...,
    actions/upload-artifact@ea165f8d...

Forcing an action onto a runtime its author never tested against is a silent
supply-chain risk in a repository whose whole posture is "pin it, hash it, prove
it". The warning was also invisible to this suite: nothing failed, so nothing
recorded it. These tests make the property executable - every action reference is
a full commit SHA, that SHA is one this repository has resolved to a Node 24
release, and the trailing comment agrees with the SHA it annotates.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

# sha -> (repository, tag). Resolved against the GitHub API on 2026-09-17: the tag
# each SHA carries, and the ``runs.using`` declared by that tag's action.yml.
# Lowest major that runs on Node 24, chosen to remove the deprecation with the
# smallest behavioural delta rather than to chase the newest major.
NODE24_PINS = {
    "fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09": ("actions/checkout", "v5.1.0"),
    "b7c566a772e6b6bfb58ed0dc250532a479d7789f": ("actions/upload-artifact", "v6.0.0"),
    "37930b1c2abaa49bbe596cd826c3c89aef350131": ("actions/download-artifact", "v7.0.0"),
    "249970729cb0ef3589644e2896645e5dc5ba9c38": ("actions/setup-node", "v6.5.0"),
}

# Pins that declare node20 and must never come back. Kept as literals on purpose:
# the test has to be able to fail on a value that is no longer in the table above.
RETIRED_NODE20_PINS = {
    "11d5960a326750d5838078e36cf38b85af677262": "actions/checkout v4.4.0",
    "ea165f8d65b6e75b540449e92b4886f43607fa02": "actions/upload-artifact v4.6.2",
    "d3f86a106a0bac45b974a628896c90dbdf5c8093": "actions/download-artifact v4.3.0",
}

# `uses: owner/name@ref`, on one line, with any trailing comment
ACTION_REF = re.compile(r"^\s*(?:-\s+)?uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@(\S+)"
                        r"(?:\s*#\s*(.*))?$")


def references():
    """Every ``uses:`` reference in every workflow, as (file, line, owner/name, ref, comment)."""
    for path in WORKFLOWS:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = ACTION_REF.match(line)
            if match:
                yield (path.name, number, match.group(1), match.group(2),
                       (match.group(3) or "").strip())


class ActionPinTests(unittest.TestCase):
    def test_the_workflow_directory_is_the_one_being_checked(self):
        self.assertGreaterEqual(len(WORKFLOWS), 11, "workflow discovery found no workflows")
        found = list(references())
        self.assertGreater(len(found), 40, "action-reference parsing silently found nothing")

    def test_every_uses_line_is_parsed_and_none_can_vanish(self):
        """A malformed `uses:` must fail loudly, not disappear from the audit."""
        unparsed = []
        for path in WORKFLOWS:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if re.match(r"^\s*(?:-\s+)?uses:\s*", line) and not ACTION_REF.match(line):
                    unparsed.append(f"{path.name}:{number} {line.strip()}")
        self.assertEqual(unparsed, [],
                         "a `uses:` line does not match the audit's own pattern, so it is "
                         "excluded from every check below")

    def test_every_action_reference_is_pinned_to_a_full_commit_sha(self):
        loose = [f"{name}:{line} uses {owner}/{action}@{ref}"
                 for name, line, owner, action, ref, _comment in
                 ((f, ln, *o.split("/"), r, c) for f, ln, o, r, c in references())
                 if not re.fullmatch(r"[a-f0-9]{40}", ref)]
        self.assertEqual(loose, [], "a mutable tag or branch is used instead of a commit SHA")

    def test_no_reference_uses_a_retired_node20_pin(self):
        offenders = []
        for name, line, _owner, ref, _comment in references():
            if ref in RETIRED_NODE20_PINS:
                offenders.append(f"{name}:{line} pins {RETIRED_NODE20_PINS[ref]} ({ref[:12]}), "
                                 "which declares runs.using: node20")
        self.assertEqual(offenders, [])

    def test_every_pin_is_one_this_repository_resolved_to_a_node24_release(self):
        unknown = sorted({ref for _n, _l, _o, ref, _c in references()
                          if ref not in NODE24_PINS})
        self.assertEqual(unknown, [],
                         "an action pin is not in NODE24_PINS: resolve its tag and confirm "
                         "its action.yml declares runs.using: node24 before adding it")

    def test_the_repository_uses_no_action_outside_the_resolved_set(self):
        actions = {owner for _n, _l, owner, _r, _c in references()}
        expected = {repository for repository, _tag in NODE24_PINS.values()}
        self.assertEqual(actions, expected,
                         "an action is referenced that has no resolved Node 24 pin recorded")

    def test_every_trailing_comment_agrees_with_the_sha_it_annotates(self):
        """A pin whose comment names a different version is worse than no comment."""
        mismatched = []
        for name, line, owner, ref, comment in references():
            expected_tag = NODE24_PINS[ref][1]
            if not comment:
                mismatched.append(f"{name}:{line} {owner}@{ref[:12]} has no version comment")
            elif expected_tag not in comment:
                mismatched.append(f"{name}:{line} {owner}@{ref[:12]} is {expected_tag} "
                                  f"but the comment says {comment!r}")
        self.assertEqual(mismatched, [])

    def test_the_pin_table_has_no_duplicate_or_stale_entries(self):
        repositories = [repository for repository, _tag in NODE24_PINS.values()]
        self.assertEqual(len(repositories), len(set(repositories)),
                         "NODE24_PINS records two versions of the same action; keep only the "
                         "one the workflows actually use")
        for sha, (repository, tag) in NODE24_PINS.items():
            self.assertRegex(tag, r"^v\d+\.\d+\.\d+$",
                             f"{repository} is pinned with a non-specific tag {tag!r}")
            self.assertEqual(len(sha), 40, f"{repository} pin is not a full commit SHA")

    def test_the_contract_tests_pin_the_same_shas_the_workflows_do(self):
        """F1b's lesson: a literal duplicated in a test is a drift waiting to happen."""
        for path in sorted((ROOT / "tests").rglob("test_*.py")):
            if path.name == Path(__file__).name:
                continue  # this file is the register of retired pins; it must name them
            body = path.read_text(encoding="utf-8")
            for sha, label in RETIRED_NODE20_PINS.items():
                self.assertNotIn(sha, body,
                                 f"{path.name} still asserts the retired {label} pin")


if __name__ == "__main__":
    unittest.main()

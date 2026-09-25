"""Executable enforcement of the branch-boundary review rule.

`docs/engineering/BRANCH-RECONCILIATION.md` states the rule: a branch reference
must be classified as **active**, **historical provenance**, or **example/text
fixture**, and "an unclassified old branch in an active workflow, hosted guard,
current status header, or qualification test is documentation or release-control
drift and must be corrected".

Until now that rule was prose only. The 2026-09-17 rotation was needed precisely
because the checkout had moved to a new Arena session branch while the canonical
pin still named the previous one — two qualification tests were failing on the
working tree as a result. These checks make the rule mechanical so the next
rotation cannot silently strand a stale branch in an active surface.
"""
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from session_branch import ACTIVE_BRANCH, ACTIVE_REF, HISTORICAL_BRANCHES, PRIOR_ACTIVE_BRANCH  # noqa: E402

BRANCH_PATTERN = re.compile(r"arena/[0-9a-f]{8}-tofel-house-erp")
PROVENANCE_MARKERS = ("historical", "provenance", "previous", "prior", "earlier", "rotated")
# An absence check ("this stale branch must NOT appear") is a guard, not a
# reference, so it is exempt from the provenance-labelling requirement.
ABSENCE_CHECKS = ("assertnotin", "not in", "!=", "!= ", "assertnotcontains")
# The file that declares the boundary is where historical branches legitimately
# live; everything else must import from it.
DECLARING_FILE = "tools/session_branch.py"

# Current-status headers must name the active branch. These are the documents
# whose opening line declares which branch the work is on.
CURRENT_STATUS_HEADERS = {
    "README.md": "Active engineering branch:",
    "docs/engineering/RELEASE-GAP-MAP.md": "Active branch:",
    "docs/engineering/OWNER-DECISIONS.md": "Active branch:",
    "docs/engineering/BRANCH-RECONCILIATION.md": "The Arena session branch",
    "docs/engineering/RELEASE-CANDIDATE-DOSSIER.md": "Active branch:",
    "docs/engineering/PRODUCTION-OPERATIONS-IMPLEMENTATION-CONTRACT.md": "Active branch:",
    "docs/domain/ARCHITECTURE-DECISIONS.md": "Active branch:",
    "docs/domain/DOMAIN-CONTRACT.md": "Active branch:",
    "docs/domain/ERP-CAPABILITY-MAP.md": "Active branch:",
    "docs/domain/README.md": "Active branch:",
}

# Immutable evidence: run/check/commit identities recorded against the branch
# they were produced on. Never rewritten by a rotation.
EVIDENCE_ROOTS = ("docs/engineering/evidence/",)


def tracked_files():
    """Tracked files plus untracked ones that are not gitignored.

    Tracked files alone are not enough to make a local run mean anything. A
    newly written file is untracked until it is committed, so scanning only
    the index lets a brand new file carry an unlabelled historical branch
    past a local run and fail in CI instead -- which is precisely what
    happened when tests/foundation/test_branch_boundary_checker.py was added.
    `--exclude-standard` keeps ignored build output out of the scan.
    """
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, text=True, capture_output=True, check=True)
    return sorted({line for line in result.stdout.splitlines() if line})


class BranchBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = tracked_files()
        cls.sources = {path: (ROOT / path).read_text(encoding="utf-8")
                       for path in cls.files if path.endswith((".py", ".yml", ".md", ".json", ".js", ".cjs", ".mjs"))}

    def test_the_scan_sees_a_file_that_has_not_been_committed_yet(self):
        """A local run must mean the same thing as a hosted one.

        Scanning only the index would let a newly written file carry an
        unlabelled historical branch past a local run and fail in CI
        instead, which is what happened when
        tests/foundation/test_branch_boundary_checker.py was first added.
        """
        probe = ROOT / "tests" / "foundation" / "_boundary_scan_probe.py"
        self.assertFalse(probe.exists())
        probe.write_text(
            "# provenance marker on the same line keeps the fixture valid\n"
            f'PRIOR = "{PRIOR_ACTIVE_BRANCH}"  # previous branch, provenance\n',
            encoding="utf-8")
        self.addCleanup(probe.unlink)
        self.assertIn("tests/foundation/_boundary_scan_probe.py", tracked_files())

    def test_checkout_matches_the_canonical_pin(self):
        result = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT,
                                text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), ACTIVE_BRANCH,
                         "the checkout drifted from tools/session_branch.ACTIVE_BRANCH; "
                         "rotate the boundary per BRANCH-RECONCILIATION.md")

    def test_active_ref_is_derived_from_the_active_branch(self):
        self.assertEqual(ACTIVE_REF, "refs/heads/" + ACTIVE_BRANCH)
        self.assertNotIn(ACTIVE_BRANCH, HISTORICAL_BRANCHES)

    def test_every_workflow_names_only_the_active_branch(self):
        workflows = [p for p in self.files if p.startswith(".github/workflows/")]
        self.assertTrue(workflows, "no workflows found")
        for path in workflows:
            for found in set(BRANCH_PATTERN.findall(self.sources[path])):
                self.assertEqual(found, ACTIVE_BRANCH,
                                 f"{path} filters on {found}; a stale branch in an active "
                                 "workflow filter is release-control drift")

    def test_tools_and_tests_classify_every_non_active_branch_as_provenance(self):
        offenders = []
        for path, source in self.sources.items():
            if not path.startswith(("tools/", "tests/", "apps/")) or path == DECLARING_FILE:
                continue
            for lineno, line in enumerate(source.splitlines(), start=1):
                for found in BRANCH_PATTERN.findall(line):
                    if found == ACTIVE_BRANCH:
                        continue
                    self.assertIn(found, HISTORICAL_BRANCHES,
                                  f"{path}:{lineno} references undeclared branch {found}")
                    low = line.lower()
                    if any(check in low for check in ABSENCE_CHECKS):
                        continue  # an absence assertion guards against the stale branch
                    if not any(marker in low for marker in PROVENANCE_MARKERS):
                        offenders.append(f"{path}:{lineno}")
        self.assertEqual(offenders, [],
                         "a historical branch in an active surface must be labelled as "
                         "provenance on the same line: " + ", ".join(offenders))

    def test_every_historical_branch_is_importable_from_the_pin(self):
        """The executable provenance list must cover every branch the docs cite."""
        reconciliation = self.sources["docs/engineering/BRANCH-RECONCILIATION.md"]
        cited = {b for b in BRANCH_PATTERN.findall(reconciliation) if b != ACTIVE_BRANCH}
        self.assertTrue(cited, "BRANCH-RECONCILIATION.md cites no historical branch")
        self.assertEqual(sorted(cited - set(HISTORICAL_BRANCHES)), [],
                         "a branch cited as provenance is missing from HISTORICAL_BRANCHES")

    def test_current_status_headers_name_the_active_branch(self):
        for path, marker in CURRENT_STATUS_HEADERS.items():
            self.assertIn(path, self.sources, f"{path} is missing")
            document = self.sources[path]
            self.assertIn(marker, document, f"{path} no longer declares its active branch")
            window = document[document.index(marker):document.index(marker) + 300]
            self.assertIn(ACTIVE_BRANCH, window,
                          f"{path} current-status header names a stale branch")

    def test_immutable_evidence_is_never_rewritten_to_the_active_branch(self):
        """The rotation must not relabel provenance to look like current execution."""
        stale = [path for path in self.sources
                 if path.startswith(EVIDENCE_ROOTS) and ACTIVE_BRANCH in self.sources[path]]
        self.assertEqual(stale, [],
                         "recorded evidence was rewritten to the active branch; runs keep "
                         "the branch they executed on: " + ", ".join(stale))


if __name__ == "__main__":
    unittest.main()

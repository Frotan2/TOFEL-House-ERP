"""Local guards so increment-3 actor mistakes fail before a hosted run.

The `author` fixture is dual-role (Placement Author + Placement Publisher) so
increment 1/2 can prove self-publication/self-review denied despite role union.
create_case / allocate_attempt are Publisher commands with no extra SoD, so
Author-only denials and non-staff read denials must use `second_author`/`other`.
Using `author` there is accepted (correct product behavior) and aborts the
hosted suite — run 34880406771.
"""
import ast
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "tools/placement/native_checks.py"
SECURITY = ROOT / "apps/toefl_house/toefl_house/security.py"

SESSION_BRANCH = "arena/01a0a13b-tofel-house-erp"
SESSION_REF = "refs/heads/" + SESSION_BRANCH

AUTHOR_ONLY = frozenset({"second_author", "other"})
DUAL_ROLE = "author"

# Hosted increment-3 checks that mean "Placement Author, not Publisher".
INC3_AUTHOR_ONLY_CHECKS = (
    "alloc-case-author-denied",
    "http-alloc-wrong-role-denied",
    "http-alloc-other-role-read-denied",
    "http-alloc-case-wrong-role-denied",
)


def _kind_roles():
    tree = ast.parse(SECURITY.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "KIND_ROLES":
                    return ast.literal_eval(node.value)
    raise AssertionError("KIND_ROLES not found in security.py")


def _check_call_source(src, name):
    needle = "check('%s'" % name
    start = src.find(needle)
    if start < 0:
        raise AssertionError("native check %r not found" % name)
    # Capture through the matching close-paren of this check(...) call.
    depth = 0
    for i, ch in enumerate(src[start:]):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return src[start:start + i + 1]
    raise AssertionError("unbalanced check() for %r" % name)


def _function_source(src, name):
    needle = "def %s(" % name
    start = src.find(needle)
    if start < 0:
        raise AssertionError("function %r not found" % name)
    next_def = src.find("\n        def ", start + 1)
    next_check = src.find("\n        check(", start + 1)
    ends = [i for i in (next_def, next_check) if i > start]
    end = min(ends) if ends else len(src)
    return src[start:end]


class Increment3ActorGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = NATIVE.read_text(encoding="utf-8")
        cls.inc3 = cls.src[cls.src.index("# --- Increment 3:"):]

    def test_author_fixture_remains_dual_role_for_sod(self):
        self.assertRegex(
            self.src,
            r"'author'\s*:\s*\[\s*'Placement Author'\s*,\s*'Placement Publisher'\s*\]",
        )
        self.assertRegex(self.src, r"'second_author'\s*:\s*\[\s*'Placement Author'\s*\]")
        self.assertRegex(self.src, r"'other'\s*:\s*\[\s*'Placement Author'\s*\]")

    def test_operational_commands_are_publisher_without_extra_sod(self):
        roles = _kind_roles()
        self.assertEqual(roles["create_case"], "Placement Publisher")
        self.assertEqual(roles["allocate_attempt"], "Placement Publisher")

    def test_inc3_author_denials_use_author_only_fixtures(self):
        for name in INC3_AUTHOR_ONLY_CHECKS:
            with self.subTest(check=name):
                body = _check_call_source(self.src, name)
                self.assertNotIn("'%s'" % DUAL_ROLE, body.replace("check('%s'" % name, ""))
                self.assertTrue(
                    any("'%s'" % label in body for label in AUTHOR_ONLY),
                    "%s must use an Author-only fixture, got: %s" % (name, body),
                )

    def test_alloc_read_parity_does_not_treat_dual_role_as_non_staff(self):
        body = _function_source(self.src, "alloc_reads")
        # The non-staff denial loop must not include the dual-role author.
        loop = re.search(r"for label in \(([^)]+)\)", body)
        self.assertIsNotNone(loop, body)
        labels = {part.strip().strip("'\"") for part in loop.group(1).split(",") if part.strip()}
        self.assertNotIn(DUAL_ROLE, labels)
        self.assertTrue(labels & AUTHOR_ONLY)
        self.assertIn("outsider", labels)
        # Dual-role author is asserted as a Publisher reader (positive control).
        self.assertIn("users['author']", body)
        self.assertIn("has_permission('read')", body)
        self.assertIn("dual_role_author_reads_as_publisher", body)

    def test_self_publication_sod_still_uses_dual_role_author(self):
        # Do not "fix" increment 3 by stripping Publisher off the author fixture.
        body = _check_call_source(self.src, "self-publication-denied-despite-role-union")
        self.assertIn("as_user('author'", body)


class SessionBranchLockTests(unittest.TestCase):
    def test_workflow_triggers_on_this_session_branch(self):
        yml = (ROOT / ".github/workflows/placement-content.yml").read_text(encoding="utf-8")
        self.assertIn("branches: [%s]" % SESSION_BRANCH, yml)
        self.assertIn("github.ref == 'refs/heads/%s'" % SESSION_BRANCH, yml)
        self.assertNotIn("branches: [arena/01a0a055-tofel-house-erp]", yml)

    def test_run_native_locked_to_this_session_branch(self):
        src = (ROOT / "tools/placement/run_native.py").read_text(encoding="utf-8")
        self.assertIn("BRANCH = '%s'" % SESSION_REF, src)
        self.assertIn("'%s'" % SESSION_BRANCH, src)

    def test_probe_and_evidence_authorize_this_session_branch(self):
        probe = (ROOT / "tools/foundation/runner_probe.py").read_text(encoding="utf-8")
        evidence = (ROOT / "tools/foundation/publish_evidence.py").read_text(encoding="utf-8")
        self.assertIn('"%s"' % SESSION_REF, probe)
        self.assertIn('"%s"' % SESSION_REF, evidence)


if __name__ == "__main__":
    unittest.main()

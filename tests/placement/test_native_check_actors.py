"""Local guards so increment-3 actor mistakes fail before a hosted run.

The `author` fixture is dual-role (Placement Author + Placement Publisher) so
increment 1/2 can prove self-publication/self-review denied despite role union.
create_case / allocate_attempt are Publisher commands with no extra SoD, so
Author-only denials and non-staff read denials must use `second_author`/`other`.
Using `author` there is accepted (correct product behavior) and aborts the
hosted suite — run 34880406771.
"""
import ast
import json
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
INC4_AUTHOR_ONLY_CHECKS = (
    "deliver-verify-author-denied",
    "http-deliver-wrong-role-denied",
    "http-deliver-other-role-response-read-denied",
)
INC5_AUTHOR_ONLY_CHECKS = (
    "score-author-denied",
    "http-score-wrong-role-denied",
    "http-score-other-role-read-denied",
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
        self.assertRegex(
            self.src,
            r"'invigilator'\s*:\s*\[\s*'Placement Invigilator'\s*\]",
        )
        self.assertRegex(
            self.src,
            r"'assessor'\s*:\s*\[\s*'Placement Assessor'\s*\]",
        )

    def test_operational_commands_are_publisher_without_extra_sod(self):
        roles = _kind_roles()
        self.assertEqual(roles["create_case"], "Placement Publisher")
        self.assertEqual(roles["allocate_attempt"], "Placement Publisher")
        self.assertEqual(roles["verify_attempt"], "Placement Invigilator")
        self.assertEqual(roles["deliver_attempt"], "Placement Invigilator")
        self.assertEqual(roles["save_response"], "Placement Invigilator")
        self.assertEqual(roles["seal_attempt"], "Placement Invigilator")
        self.assertEqual(roles["score_attempt"], "Placement Assessor")

    def test_inc3_author_denials_use_author_only_fixtures(self):
        for name in INC3_AUTHOR_ONLY_CHECKS + INC4_AUTHOR_ONLY_CHECKS + INC5_AUTHOR_ONLY_CHECKS:
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

    def test_increment3_reconnects_to_primary_site_before_allocation(self):
        start = self.src.index("# --- Increment 3:")
        bank = self.src.index("alloc-bank-fixture-published", start)
        self.assertIn("connect('placement-test.localhost')", self.src[start:bank])

    def test_allocation_doctypes_do_not_grant_author(self):
        # Do not "fix" Insufficient Permission by adding Author read grants.
        root = ROOT / "apps/toefl_house/toefl_house/placement/doctype"
        for folder in ("th_placement_case", "th_placement_attempt",
                       "th_placement_form_manifest", "th_placement_exposure",
                       "th_placement_response", "th_placement_score"):
            data = json.loads((root / folder / (folder + ".json")).read_text(encoding="utf-8"))
            roles = {row["role"] for row in data["permissions"]}
            self.assertNotIn("Placement Author", roles, folder)
            self.assertIn("Placement Publisher", roles, folder)
            self.assertIn("Placement Auditor", roles, folder)
        guard = json.loads((root / "th_placement_allocation_guard" /
                            "th_placement_allocation_guard.json").read_text(encoding="utf-8"))
        self.assertEqual(guard["permissions"], [])
        manifest = json.loads((root / "th_placement_form_manifest" /
                               "th_placement_form_manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("Placement Invigilator",
                         {row["role"] for row in manifest["permissions"]})
        score = json.loads((root / "th_placement_score" / "th_placement_score.json").read_text(
            encoding="utf-8"))
        score_roles = {row["role"] for row in score["permissions"]}
        self.assertIn("Placement Assessor", score_roles)
        self.assertNotIn("Placement Author", score_roles)
        self.assertNotIn("Placement Invigilator", score_roles)
        for folder in ("th_placement_case", "th_placement_attempt",
                       "th_placement_exposure", "th_placement_response"):
            data = json.loads((root / folder / (folder + ".json")).read_text(encoding="utf-8"))
            self.assertIn("Placement Invigilator",
                          {row["role"] for row in data["permissions"]}, folder)
        # Assessor reads the operational rows needed to mark; not the seed
        # or the unused exposure ledger. Do not grant Manifest/Key/Guard.
        for folder in ("th_placement_case", "th_placement_attempt",
                       "th_placement_response"):
            data = json.loads((root / folder / (folder + ".json")).read_text(encoding="utf-8"))
            self.assertIn("Placement Assessor",
                          {row["role"] for row in data["permissions"]}, folder)
        for folder in ("th_placement_form_manifest", "th_placement_exposure",
                       "th_placement_key_revision"):
            data = json.loads((root / folder / (folder + ".json")).read_text(encoding="utf-8"))
            self.assertNotIn("Placement Assessor",
                             {row["role"] for row in data["permissions"]}, folder)

    def test_alloc_read_parity_treats_permissionerror_as_denial(self):
        body = _function_source(self.src, "cannot_list") + _function_source(self.src, "cannot_read_doc")
        self.assertIn("PermissionError", body)

    def test_post_helper_is_not_called_with_timeout(self):
        # Run 34887457604: alloc_revoke passed timeout= into post(), which only
        # takes (label, method, payload). Coverage of revocation stays.
        tree = ast.parse(self.src)

        class Visitor(ast.NodeVisitor):
            def visit_Call(self, node):
                if isinstance(node.func, ast.Name) and node.func.id == "post":
                    for kw in node.keywords:
                        if kw.arg == "timeout":
                            raise AssertionError("post() does not accept timeout")
                self.generic_visit(node)

        Visitor().visit(tree)

    def test_allocate_insert_records_allocator_and_version_one(self):
        # Run 34923079666: AttemptRecord requires Allocated/version=1/allocated_by
        # on insert; omitting them aborted the suite at alloc-happy-path.
        api_src = (ROOT / "apps/toefl_house/toefl_house/api.py").read_text(encoding="utf-8")
        start = api_src.index("def allocate_attempt")
        end = api_src.index("\ndef _now(")
        blob = api_src[start:end]
        self.assertIn("allocated_by=actor", blob)
        self.assertIn("version=1", blob)
        self.assertIn('status="Allocated"', blob)

    def test_http_allocate_keys_match_whitelist_signature(self):
        # Run 34886485679: HTTP JSON used case/blueprint/policy while the
        # whitelist still required case_name/blueprint_name/policy_name → 500.
        api_src = (ROOT / "apps/toefl_house/toefl_house/api.py").read_text(encoding="utf-8")
        tree = ast.parse(api_src)
        args = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "allocate_attempt":
                args = [a.arg for a in node.args.args]
        self.assertEqual(
            args,
            ["request_key", "case", "blueprint", "blueprint_version", "policy", "policy_version"],
        )
        start = self.src.index("http_alloc_payload=dict(")
        blob = self.src[start:start + 400]
        for key in ("request_key", "case", "blueprint", "blueprint_version", "policy", "policy_version"):
            self.assertIn("%s=" % key, blob)
        self.assertNotIn("case_name=", blob)
        self.assertNotIn("blueprint_name=", blob)
        self.assertNotIn("policy_name=", blob)

    def test_http_sessions_include_invigilator(self):
        start = self.src.index("sessions={label:login")
        blob = self.src[start:start + 360]
        self.assertIn("'invigilator'", blob)
        self.assertIn("'assessor'", blob)

    def test_http_session_keys_match_whitelist_signature(self):
        api_src = (ROOT / "apps/toefl_house/toefl_house/api.py").read_text(encoding="utf-8")
        tree = ast.parse(api_src)
        expected = {
            "verify_attempt": ["request_key", "attempt", "expected_version"],
            "deliver_attempt": ["request_key", "attempt", "expected_version"],
            "save_response": ["request_key", "attempt", "expected_version",
                              "occurrence", "expected_revision", "option_id", "missing"],
            "seal_attempt": ["request_key", "attempt", "expected_version", "reason"],
            "score_attempt": ["request_key", "attempt", "expected_version"],
        }
        found = {}
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in expected:
                found[node.name] = [a.arg for a in node.args.args]
        self.assertEqual(found, expected)
        self.assertIn("http_deliver_payload=dict(", self.src)
        blob = self.src[self.src.index("http_deliver_payload=dict("):
                        self.src.index("http_deliver_payload=dict(") + 500]
        for key in ("request_key", "attempt", "expected_version"):
            self.assertIn("%s=" % key, blob)

    def test_increment3_pins_its_own_published_policy(self):
        # Do not capture increment-2's `pol` across the second-site hop.
        self.assertNotIn("pol_name=pol['name']", self.inc3)
        self.assertIn("pol_name=cfgx['main_pol']", self.inc3)
        self.assertIn("publish_config_flow('SYN-POL-ALLOC-1',good_pol,'policy')", self.inc3)


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

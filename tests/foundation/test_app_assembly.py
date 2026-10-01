"""App-assembly consistency for the owned Frappe application.

Frappe resolves these wiring tables at import/migrate time and fails late and
obscurely when they disagree, so a mismatch between `hooks.py`,
`permissions.py`, `policy.can_read` and the DocType JSON files would ship
silently and only surface on a live site. The 2026-09-17 review verified this
surface by hand and found it consistent; these checks make that a permanent
invariant instead of a one-off audit.

Pure file parsing: no Frappe import, no site, no database.
"""
import ast
from pathlib import Path
import json
import re
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
SECURITY = APP / "security.py"
PERMISSIONS = APP / "permissions.py"
POLICY = APP / "policy.py"


def load_hooks():
    """hooks.py is declarative data with no imports, so it can be executed safely."""
    namespace = {}
    exec(compile((APP / "hooks.py").read_text(encoding="utf-8"), "hooks.py", "exec"), namespace)
    return namespace


def load_security_constants():
    """Execute only the constant block of security.py, with frappe stubbed out."""
    source = SECURITY.read_text(encoding="utf-8").split("def require_synthetic")[0]
    frappe_stub = types.ModuleType("frappe")
    frappe_stub.PermissionError = type("PermissionError", (Exception,), {})
    previous = sys.modules.get("frappe")
    sys.modules["frappe"] = frappe_stub
    try:
        namespace = {}
        exec(compile(source, "security.py", "exec"), namespace)
        return namespace
    finally:
        if previous is None:
            del sys.modules["frappe"]
        else:
            sys.modules["frappe"] = previous


class AppAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hooks = load_hooks()
        cls.security = load_security_constants()
        cls.doctypes = {}
        for path in APP.glob("*/doctype/*/*.json"):
            definition = json.loads(path.read_text(encoding="utf-8"))
            cls.doctypes[definition["name"]] = definition
        cls.roles = {row["name"] for row in
                     json.loads((APP / "fixtures/role.json").read_text(encoding="utf-8"))}
        cls.modules = {line.strip() for line in
                       (APP / "modules.txt").read_text(encoding="utf-8").splitlines() if line.strip()}
        cls.permissions_source = PERMISSIONS.read_text(encoding="utf-8")
        cls.policy_source = POLICY.read_text(encoding="utf-8")

    # --- DocType files -------------------------------------------------
    def test_every_doctype_directory_is_complete(self):
        directories = [p for p in APP.glob("*/doctype/*/") if p.is_dir()]
        self.assertTrue(directories, "no DocType directories found")
        for directory in directories:
            slug = directory.name
            for expected in (directory / f"{slug}.json", directory / f"{slug}.py",
                             directory / "__init__.py"):
                self.assertTrue(expected.exists(), f"missing {expected}")

    def test_every_doctype_lives_in_a_declared_module(self):
        for name, definition in self.doctypes.items():
            self.assertIn(definition["module"], self.modules,
                          f"{name} declares module {definition['module']} which is not in modules.txt")

    # --- hooks <-> permissions wiring ---------------------------------
    def test_permission_hooks_and_query_conditions_cover_exactly_the_command_doctypes(self):
        has_permission = set(self.hooks["has_permission"])
        query_conditions = set(self.hooks["permission_query_conditions"])
        guarded = (set(self.security["DOCTYPES"]) | self.governance_doctypes()
                   | self.branch_native_doctypes())
        self.assertEqual(has_permission, query_conditions,
                         "has_permission and permission_query_conditions disagree")
        self.assertEqual(has_permission, guarded,
                         "hooks must cover exactly the synthetic-guarded doctypes, "
                         "the declared governance configuration, and the documented "
                         "branch-isolation native set")

    def branch_native_doctypes(self):
        """The documented branch-isolation set: native doctypes that gain their
        own branch hooks (not synthetic-gated, not governance)."""
        match = re.search(r"^BRANCH_NATIVE_DOCTYPES = \((.*?)\)", self.permissions_source,
                          re.S | re.M)
        self.assertTrue(match, "permissions.py must declare BRANCH_NATIVE_DOCTYPES")
        native = set(ast.literal_eval("(" + match.group(1) + ")"))
        self.assertTrue(native.isdisjoint(self.security["DOCTYPES"]),
                        "branch-native doctypes must stay disjoint from the "
                        "synthetic-guarded doctypes")
        self.assertTrue(native.isdisjoint(self.governance_doctypes()),
                        "branch-native doctypes must stay disjoint from governance")
        return native

    def branch_kinds(self):
        match = re.search(r"^BRANCH_KINDS = (\{.*?^\})", self.permissions_source, re.S | re.M)
        self.assertTrue(match, "permissions.py must declare BRANCH_KINDS")
        return ast.literal_eval(match.group(1))

    def governance_doctypes(self):
        import ast as _ast
        match = re.search(r"^GOVERNANCE_DOCTYPES = (\{.*?\})", self.permissions_source,
                          re.S | re.M)
        self.assertTrue(match, "permissions.py must declare GOVERNANCE_DOCTYPES")
        governance = _ast.literal_eval(match.group(1))
        self.assertTrue(governance.isdisjoint(self.security["DOCTYPES"]),
                        "governance configuration must stay disjoint from the "
                        "synthetic-guarded doctypes")
        return governance

    def test_child_tables_are_deliberately_unguarded(self):
        children = {name for name, definition in self.doctypes.items()
                    if definition.get("istable")}
        self.assertTrue(children, "expected child tables in the app")
        self.assertEqual(children, set(self.doctypes) - set(self.hooks["has_permission"]),
                         "exactly the child tables may be absent from the permission hooks")

    def test_every_query_condition_target_exists(self):
        governance = self.governance_doctypes()
        native = self.branch_native_doctypes()
        branch_kinds = self.branch_kinds()
        for doctype, target in self.hooks["permission_query_conditions"].items():
            if doctype in governance:
                self.assertEqual(target, "toefl_house.permissions.configuration_query",
                                 f"{doctype} must use the non-synthetic governance query")
                self.assertIn("def configuration_query(", self.permissions_source,
                              "the governance query seam has no definition")
                self.assertIn("def configuration_has_permission(", self.permissions_source,
                              "the governance row seam has no definition")
                continue
            if doctype in native:
                self.assertEqual(target,
                                 f"toefl_house.permissions.branch_query_{branch_kinds[doctype]}",
                                 f"{doctype} must use its documented branch query")
                self.assertIn(f"def branch_query_{branch_kinds[doctype]}(",
                              self.permissions_source,
                              f"{target} has no definition in permissions.py")
                self.assertEqual(self.hooks["has_permission"][doctype],
                                 "toefl_house.permissions.branch_has_permission",
                                 f"{doctype} must use the branch document gate")
                continue
            self.assertEqual(target, f"toefl_house.permissions.query_{self.kind_of(doctype)}",
                             f"{doctype} points at an unexpected query function")
            suffix = target.rsplit("query_", 1)[1]
            self.assertIn(f"def query_{suffix}(", self.permissions_source,
                          f"{target} has no definition in permissions.py")

    def kind_of(self, doctype):
        kinds = ast.literal_eval(
            re.search(r"^KINDS = (\{.*?^\})", self.permissions_source, re.S | re.M).group(1))
        return kinds[doctype]

    def test_every_kind_has_a_row_and_query_condition_function(self):
        kinds = ast.literal_eval(
            re.search(r"^KINDS = (\{.*?^\})", self.permissions_source, re.S | re.M).group(1))
        tables = ast.literal_eval(
            re.search(r"^TABLES = (\{.*?^\})", self.permissions_source, re.S | re.M).group(1))
        self.assertEqual(set(kinds), set(self.security["DOCTYPES"]))
        for doctype, kind in kinds.items():
            expected_table = f"`tab{doctype}`"
            if kind in ("audit", "operation"):
                continue  # audit/operation are row-level only, no query surface
            self.assertEqual(tables.get(kind), expected_table,
                             f"kind {kind} has no TABLES row for {doctype}")

    def test_can_read_covers_every_kind(self):
        """A new kind with no can_read branch would silently deny or leak."""
        kinds = set(ast.literal_eval(
            re.search(r"^KINDS = (\{.*?^\})", self.permissions_source, re.S | re.M).group(1)).values())
        body = self.policy_source.split("def can_read(")[1].split("\ndef ")[0]
        for kind in kinds:
            self.assertIn(f'"{kind}"', body,
                          f"policy.can_read has no branch for kind '{kind}'")

    def test_branch_scope_doctypes_are_deterministic(self):
        """Every branch-scoped doctype is either synthetic-guarded (reusing its
        existing kind and query seam) or in the documented native set (with its
        own branch query seam). A branch-scoped kind with no condition path
        would either silently leak or silently deny."""
        branch_kinds = self.branch_kinds()
        native = self.branch_native_doctypes()
        kind_map = ast.literal_eval(
            re.search(r"^KINDS = (\{.*?^\})", self.permissions_source, re.S | re.M).group(1))
        for doctype, kind in branch_kinds.items():
            if doctype in kind_map:
                # A guarded doctype must reuse its existing kind, so the
                # synthetic guard and the branch rule compose in one place.
                self.assertEqual(kind_map[doctype], kind,
                                 f"{doctype} must reuse its existing kind for branch scope")
                self.assertIn(f"def query_{kind}(", self.permissions_source)
            else:
                self.assertIn(doctype, native,
                              f"{doctype} is branch-scoped but neither guarded nor "
                              "in the documented native set")
                self.assertIn(f"def branch_query_{kind}(", self.permissions_source)

    # --- roles and pages ----------------------------------------------
    def test_every_command_role_is_a_shipped_fixture(self):
        for command, role in self.security["KIND_ROLES"].items():
            self.assertIn(role, self.roles, f"command {command} requires unfixed role {role}")

    def test_command_pages_exist_and_are_role_gated(self):
        pages = self.hooks["page_js"]
        self.assertTrue(pages, "no command pages are wired")
        slugs = {p.parent.name.replace("_", "-") for p in APP.glob("*/page/*/*.json")}
        for slug in pages:
            self.assertIn(slug, slugs, f"page_js references {slug} which has no Page file")
        for path in APP.glob("*/page/*/*.json"):
            page = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(page["doctype"], "Page", path.name)
            self.assertTrue(page.get("roles"), f"{path.name} has no Has Role rows")
            for row in page["roles"]:
                self.assertIn(row["role"], self.roles,
                              f"{path.name} grants Page access to unfixed role {row['role']}")

    def test_page_assets_exist(self):
        for slug, asset in self.hooks["page_js"].items():
            self.assertTrue((APP / asset).exists(), f"{slug} references missing asset {asset}")

    # --- guard seams ---------------------------------------------------
    def test_every_guarded_doctype_pins_all_three_lifecycle_seams(self):
        """A13 containment: pinned frappe fires `validate` only on save/submit."""
        events = self.hooks["doc_events"]
        seams = ("validate", "before_cancel", "before_update_after_submit")
        guarded_native = {dt for dt, handlers in events.items()
                          if any(handler.startswith("toefl_house.") for handler in handlers.values())}
        self.assertTrue(guarded_native, "no native DocType carries an owned guard")
        governance = self.governance_doctypes()
        for doctype, handlers in events.items():
            if doctype not in guarded_native:
                continue
            if doctype in governance:
                # Governance configuration is non-cancelable and non-submittable;
                # its hooks are unconditional integrity checks (validate family).
                self.assertIn("validate", handlers, f"{doctype} is missing the validate seam")
                continue
            for seam in seams:
                self.assertIn(seam, handlers, f"{doctype} is missing the {seam} seam")
            self.assertEqual(len({handlers[s] for s in seams}), 1,
                             f"{doctype} pins a different guard per seam")


class ChildRowConversionTests(unittest.TestCase):
    """Child-table rows from doc.get() convert via row.as_dict(), never dict().

    The first hosted version write (S7) proved pinned Frappe child
    Documents are not dict-convertible: dict(row) raises TypeError on a
    live site while passing against dict-based local stubs. dict() stays
    legal only over get_all/project_rows results, which are real dicts.
    """

    def test_no_dict_conversion_over_document_child_rows(self):
        offenders = []
        for path in sorted(APP.rglob("*.py")):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "dict(row) for row in" in line and ".get(\"" in line:
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()


class BranchIsolationContract(unittest.TestCase):
    """The branch rule on the real permissions.py, against a scripted frappe.

    Proves the operating rule end-to-end at the seam: no Branch User
    Permission = unrestricted (HQ); a Branch User Permission = scoped to
    exactly those branches, fail closed wherever the branch is
    unresolvable; Administrator is never scoped.
    """

    PERM = APP / "permissions.py"

    def setUp(self):
        from types import ModuleType, SimpleNamespace
        import importlib.util
        self.up_rows = []            # Branch User Permission rows for the user
        self.up_filters = []         # every User Permission filter the module issued
        self.roster = {}             # student -> [branch, ...] active roster branches
        self.group_branches = {}     # student group name -> branch
        self.applicant_branches = {} # applicant name -> branch
        self.errored = []
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))

        frappe_stub = ModuleType("frappe")
        frappe_stub.PermissionError = type("PermissionError", (Exception,), {})
        frappe_stub.session = SimpleNamespace(user="staff@toeflhouse.test")

        def escape(value):
            return "'" + str(value).replace("'", "''") + "'"

        def sql(query, values=(), as_dict=False, **kwargs):
            # The roster resolution is the only raw SQL the module runs.
            if "tabStudent Group Student" in query and "sg.th_branch" in query:
                student = values[0]
                branches = self.roster.get(student, [])
                rows = [SimpleNamespace(th_branch=b) for b in branches]
                return rows if as_dict else [(b,) for b in branches]
            self.errored.append(query[:60])
            raise AssertionError(f"unexpected SQL: {query[:60]}")

        def get_value(doctype, name, fieldname=None):
            if doctype == "Student Group":
                return self.group_branches.get(name)
            if doctype == "Student Applicant":
                return self.applicant_branches.get(name)
            self.errored.append(doctype)
            raise AssertionError(f"unexpected get_value {doctype}")

        frappe_stub.db = SimpleNamespace(escape=escape, sql=sql, get_value=get_value)

        def get_all(doctype, filters=None, pluck=None, limit_page_length=None, **kwargs):
            if doctype == "User Permission":
                self.up_filters.append(dict(filters or {}))
                return list(self.up_rows)
            raise AssertionError(f"unexpected get_all {doctype}")

        frappe_stub.get_all = get_all
        frappe_stub.get_roles = lambda user: {"Admission Officer"}

        policy = ModuleType("toefl_house.policy")
        policy.can_read = lambda kind, roles, user, owner, status: True
        security = ModuleType("toefl_house.security")
        security.require_operational = lambda: None
        package = ModuleType("toefl_house")
        package.__path__ = []
        sys.modules.update({"frappe": frappe_stub, "toefl_house": package,
                            "toefl_house.policy": policy, "toefl_house.security": security})
        spec = importlib.util.spec_from_file_location("toefl_house.permissions", self.PERM)
        self.perm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.perm)

    def test_no_branch_permission_is_unrestricted(self):
        self.perm = self.perm  # sanity
        self.assertEqual(self.perm.branch_query_student(), "1=1")
        doc = SimpleNamespace_doctype("Student", "STU-1")
        self.assertTrue(self.perm.branch_has_permission(doc, "read"))
        self.assertEqual(self.perm.branch_query_student_group(), "1=1")

    def test_scoped_user_query_conditions_carry_the_branch(self):
        self.up_rows = ["Branch Alpha"]
        condition = self.perm.branch_query_student()
        self.assertIn("'Branch Alpha'", condition)
        self.assertIn("tabStudent Group Student", condition)
        self.assertIn("th_branch IN", condition)
        self.assertEqual(self.perm.branch_query_student_group(),
                         "`tabStudent Group`.th_branch IN ('Branch Alpha')")
        self.assertIn("`tabStudent Applicant`.th_branch IN ('Branch Alpha')",
                      self.perm.branch_query_student_applicant())

    def test_scoped_user_document_gate_follows_the_roster(self):
        self.up_rows = ["Branch Alpha"]
        self.roster["STU-A"] = ["Branch Alpha"]
        self.roster["STU-B"] = ["Branch Beta"]
        allowed = SimpleNamespace_doctype("Student", "STU-A")
        foreign = SimpleNamespace_doctype("Student", "STU-B")
        unrostered = SimpleNamespace_doctype("Student", "STU-NONE")
        self.assertTrue(self.perm.branch_has_permission(allowed, "read"))
        self.assertFalse(self.perm.branch_has_permission(foreign, "read"))
        self.assertFalse(self.perm.branch_has_permission(unrostered, "read"),
                         "unresolvable branch must fail closed")

    def test_group_and_applicant_gate_on_their_branch_field(self):
        self.up_rows = ["Branch Alpha"]
        own = SimpleNamespace_doctype("Student Group", "GRP-A", th_branch="Branch Alpha")
        foreign = SimpleNamespace_doctype("Student Group", "GRP-B", th_branch="Branch Beta")
        unbranched = SimpleNamespace_doctype("Student Group", "GRP-N", th_branch=None)
        self.assertTrue(self.perm.branch_has_permission(own, "read"))
        self.assertFalse(self.perm.branch_has_permission(foreign, "read"))
        self.assertFalse(self.perm.branch_has_permission(unbranched, "read"))
        applicant = SimpleNamespace_doctype("Student Applicant", "APP-A", th_branch="Branch Alpha")
        self.assertTrue(self.perm.branch_has_permission(applicant, "read"))

    def test_scoped_to_no_branch_sees_nothing(self):
        # A User Permission row with an empty value: scoped, to nothing.
        self.up_rows = [""]
        self.assertEqual(self.perm.branch_query_student(), "1=0")
        self.assertFalse(self.perm.branch_has_permission(
            SimpleNamespace_doctype("Student", "STU-A"), "read"))

    def test_administrator_is_never_branch_scoped(self):
        import frappe as _unused  # noqa: F401  (stub is in sys.modules)
        original = sys.modules["frappe"].session.user
        sys.modules["frappe"].session.user = "Administrator"
        try:
            self.up_rows = ["Branch Alpha"]
            self.assertEqual(self.perm.branch_query_student(), "1=1")
            self.assertTrue(self.perm.branch_has_permission(
                SimpleNamespace_doctype("Student", "STU-ANY"), "read"))
        finally:
            sys.modules["frappe"].session.user = original

    def test_guarded_kind_composes_role_and_branch(self):
        self.up_rows = ["Branch Alpha"]
        condition = self.perm.query("admission_decision")
        # The role base condition for Admission Officer plus the branch rule.
        self.assertIn("student_applicant", condition)
        self.assertIn("'Branch Alpha'", condition)
        self.assertTrue(condition.startswith("("), "base condition must be preserved")
        # A kind without a branch path is untouched.
        self.assertEqual(self.perm.query("attempt"), self.perm._query_role("attempt"))

    def test_user_permission_filters_use_pinned_columns_only(self):
        # D2-class guard: the scripted world answers any filter key, which is
        # exactly what let a nonexistent column (User Permission.block at
        # pinned frappe 988e54f) reach a real MariaDB. Every filter key the
        # module issues against User Permission must exist on the pinned
        # schema ledger.
        self.up_rows = ["Branch Alpha"]
        self.perm.branch_query_student()
        self.perm.branch_has_permission(SimpleNamespace_doctype("Student", "STU-A"))
        self.assertTrue(self.up_filters, "the branch rule must read User Permission")
        ledger = json.loads(
            (ROOT / "tests" / "desk" / "pinned_schema.json").read_text(encoding="utf-8"))
        real = set(ledger["doctypes"]["User Permission"]["fields"])
        for filters in self.up_filters:
            bad = sorted(set(filters) - real)
            self.assertEqual(bad, [],
                             f"User Permission filter references unpinned columns: {bad}")


def SimpleNamespace_doctype(doctype, name, **extra):
    from types import SimpleNamespace
    payload = dict(extra)

    class _Doc(SimpleNamespace):
        pass

    doc = _Doc(doctype=doctype, name=name, **payload)

    def get(field, default=None):
        if hasattr(doc, field):
            return getattr(doc, field)
        return default

    doc.get = get
    return doc


if __name__ == "__main__":
    unittest.main()

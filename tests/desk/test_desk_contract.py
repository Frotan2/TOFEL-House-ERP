"""Role-desk product layer contract (docs/product/ROLE-DESKS.md).

The desks are separately authorized read projections. These checks pin the
security-relevant shape of that layer offline:

- every whitelisted desk endpoint gates on its desk audience before anything
  else, and that gate is the desk's own audience (mutation-visible: deleting
  the gate call fails these tests);
- every database read in the desk package flows through the sanctioned
  projection helpers with an explicit allow-listed field list and an explicit
  limit; no desk module touches frappe.get_all / get_list / db directly;
- no desk module writes: no insert/save/delete/submit, no frappe.get_doc;
- the projected field allow-lists never contain sensitive internals;
- the lifecycle stage machine produces the documented stages and next roles;
- the finance vocabulary never invents a money status.

No Frappe site is required: frappe is stubbed at import time, exactly like the
app-assembly suite stubs it for security.py constants.
"""
import ast
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
DESK = APP / "desk"

DESK_MODULES = ("__init__", "lifecycle", "reception", "academic", "finance",
                "operations", "owner", "setup")

SENSITIVE_FIELDS = {
    "answer", "content_hash", "result_json", "seed", "pool_digest",
    "key_version", "form_hash", "net_pay", "salary", "base",
    "encryption_key", "password", "secret",
}


def _load_pinned_schema():
    spec = importlib.util.spec_from_file_location(
        "th_pinned_schema", Path(__file__).with_name("pinned_schema.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pinned_schema = _load_pinned_schema()


def assert_columns_real(caller, doctype, columns):
    """Every projected/filtered column must exist on the pinned authority.

    The stub world answers any field name a test asks for — that neutrality
    is what hid the D2 class (desk code querying Student Group.active, a
    column no pinned doctype has). This guard makes the fake world schema-
    strict: unknown doctype or unknown column fails, in every live-run
    smoke, world test and static scan below.
    """
    real = pinned_schema.real_fields(doctype)
    if real is None:
        raise AssertionError(f"{caller}: {doctype!r} is not in the pinned schema "
                             "ledger — a new doctype entered a desk projection "
                             "without pinning its real fields")
    bad = sorted({column for column in columns if column and column not in real})
    if bad:
        raise AssertionError(f"{caller}: {doctype} has no column(s) {bad} "
                             "(schema fiction — D2 class)")


def _frappe_stub(roles=()):
    stub = types.ModuleType("frappe")

    class PermissionError(Exception):
        pass

    class ValidationError(Exception):
        pass

    stub.PermissionError = PermissionError
    stub.ValidationError = ValidationError

    def throw(msg, exc=None):
        raise (exc or Exception)(msg)

    stub.throw = staticmethod(throw)

    def whitelist(**kwargs):
        """Marks the function exactly where the real frappe decorator would.

        A neutralized pass-through stub hid the Academic Setup defect (D1):
        the desk ran in-process whether or not it was exposed. Marking here
        keeps imports callable while making the MISSING decorator observable
        to the tie-out tests below — the closest offline mirror of the real
        request pipeline's whitelist enforcement.
        """
        def decorator(func):
            func.__frappe_whitelisted__ = True
            func.__frappe_whitelist_methods__ = tuple(kwargs.get("methods") or ())
            return func
        return decorator

    stub.whitelist = whitelist
    stub.session = types.SimpleNamespace(user="desk-user@example.com")
    stub.get_roles = lambda user: set(roles)
    def _db_get_all(doctype, filters=None, fields=None, order_by=None,
                    limit_start=None, limit_page_length=None, **kwargs):
        assert_columns_real("stub get_all", doctype,
                            list(fields or []) + list((filters or {}).keys())
                            + ([kwargs["pluck"]] if kwargs.get("pluck") else []))
        return []

    def _db_count(doctype, filters=None):
        assert_columns_real("stub count", doctype, list((filters or {}).keys()))
        return 0

    stub.db = types.SimpleNamespace(
        count=_db_count,
        get_value=lambda *args, **kwargs: 1,
        get_all=_db_get_all,
        get_list=_db_get_all,
    )
    stub.get_all = _db_get_all
    import datetime as _datetime
    _NOW = _datetime.datetime(2026, 9, 17, 9, 0, 0)

    def _get_datetime(value):
        if isinstance(value, _datetime.datetime):
            return value
        return _datetime.datetime.fromisoformat(str(value))

    utils = types.ModuleType("frappe.utils")
    utils.get_datetime = _get_datetime
    utils.now_datetime = lambda: _NOW
    utils.today = lambda: "2026-09-17"
    stub.utils = utils
    return stub


def _import_desk(name, roles=()):
    """Import toefl_house.desk.<name> with frappe stubbed and the real desk
    package executed, so `from toefl_house.desk import ...` resolves."""
    stub = _frappe_stub(roles)
    previous = {key: sys.modules.get(key)
                for key in ("frappe", "frappe.utils", "toefl_house", "toefl_house.desk")}
    sys.modules["frappe"] = stub
    sys.modules["frappe.utils"] = stub.utils
    package = types.ModuleType("toefl_house")
    package.__path__ = [str(APP)]
    sys.modules["toefl_house"] = package
    package_spec = importlib.util.spec_from_file_location("toefl_house.desk", DESK / "__init__.py")
    package_desk = importlib.util.module_from_spec(package_spec)
    package_desk.__path__ = [str(DESK)]
    sys.modules["toefl_house.desk"] = package_desk
    try:
        package_spec.loader.exec_module(package_desk)
        if name == "__init__":
            return package_desk
        spec = importlib.util.spec_from_file_location(f"toefl_house.desk.{name}", DESK / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"toefl_house.desk.{name}"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for key, value in previous.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value


def desk_sources():
    return {name: (DESK / f"{name}.py").read_text(encoding="utf-8")
            for name in DESK_MODULES}


def desk_trees():
    return {name: ast.parse(source) for name, source in desk_sources().items()}


def _literal_block(source, header):
    """Extract a dict literal that follows `header` and closes with a lone }."""
    block = source.split(header)[1].split("\n}\n")[0]
    return ast.literal_eval("{" + block + "}")


class DeskGateTests(unittest.TestCase):
    """Every whitelisted endpoint gates on its audience, first."""

    @classmethod
    def setUpClass(cls):
        cls.trees = desk_trees()

    def whitelisted(self, tree):
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    if "whitelist" in ast.unparse(decorator):
                        found.append(node)
        return found

    def test_every_whitelisted_desk_endpoint_gates_on_its_audience_first(self):
        for module in ("reception", "academic", "finance", "operations", "owner",
                       "setup"):
            endpoints = self.whitelisted(self.trees[module])
            self.assertTrue(endpoints, f"{module} ships no whitelisted endpoint")
            for func in endpoints:
                statements = [ast.unparse(node) for node in func.body]
                self.assertTrue(
                    any(statement.startswith("require_desk_audience(")
                        for statement in statements[:2]),
                    f"{module}.{func.name} does not gate on the desk audience first")
                self.assertIn("require_desk_audience(SLUG)", " ".join(statements[:2]),
                              f"{module}.{func.name} gates on the wrong audience expression")

    def test_registry_endpoint_guards_protected_identities(self):
        for node in ast.walk(self.trees["__init__"]):
            if isinstance(node, ast.FunctionDef) and node.name == "available":
                statements = [ast.unparse(child) for child in node.body]
                joined = " ".join(statements)
                self.assertIn("Guest", joined)
                self.assertIn("Administrator", joined)
                self.assertIn("enabled", joined)
                first_return = next(index for index, statement in enumerate(statements)
                                    if statement.startswith("return"))
                guards = [index for index, statement in enumerate(statements)
                          if "Guest" in statement or "Administrator" in statement
                          or "enabled" in statement]
                self.assertTrue(guards and min(guards) < first_return,
                                "available() must refuse protected identities before answering")
                return
        self.fail("available() endpoint is missing from the desk registry")


class DeskReadBoundaryTests(unittest.TestCase):
    """All desk reads flow through the sanctioned, allow-listed helpers."""

    @classmethod
    def setUpClass(cls):
        cls.sources = desk_sources()
        cls.trees = desk_trees()

    def test_desk_modules_never_query_or_write_directly(self):
        forbidden_calls = ("frappe.get_all", "frappe.get_list", "frappe.db.get_list",
                           "frappe.db.get_all", "frappe.db.sql", "frappe.get_doc",
                           "frappe.db.insert", "frappe.db.delete", "frappe.db.count")
        for name in ("reception", "academic", "finance", "operations", "owner",
                     "setup"):
            for node in ast.walk(self.trees[name]):
                if isinstance(node, ast.Call):
                    rendered = ast.unparse(node.func)
                    self.assertNotIn(rendered, forbidden_calls,
                                     f"{name} performs an unsanctioned {rendered} read/write")

    def test_desk_modules_never_mutate_documents(self):
        forbidden_names = (".insert(", ".save(", ".delete(", ".submit(", ".cancel(")
        for name, source in self.sources.items():
            if name == "__init__":
                continue
            for line in source.splitlines():
                if line.strip().startswith("#"):
                    continue
                for token in forbidden_names:
                    self.assertNotIn(token, line,
                                     f"{name} looks like it mutates a document: {line.strip()}")

    def test_every_projection_call_names_explicit_fields_and_a_limit(self):
        for name in ("reception", "academic", "finance", "operations", "owner",
                     "setup"):
            for node in ast.walk(self.trees[name]):
                if not (isinstance(node, ast.Call) and ast.unparse(node.func) in (
                        "project_rows", "project_count")):
                    continue
                keywords = {keyword.arg for keyword in node.keywords}
                positional = len(node.args)
                if ast.unparse(node.func) == "project_rows":
                    # fields is the third declared parameter, limit the sixth
                    self.assertTrue("fields" in keywords or positional >= 3,
                                    f"{name} project_rows without explicit fields")
                    self.assertTrue("limit" in keywords or positional >= 6,
                                    f"{name} project_rows without an explicit limit")
                else:
                    # filters is the third declared parameter of project_count
                    self.assertTrue("filters" in keywords or positional >= 3,
                                    f"{name} project_count without filters")

    def test_projection_allow_lists_are_declared_and_clean(self):
        allow = _literal_block(self.sources["__init__"], "PROJECTION_FIELDS = {")
        self.assertTrue(allow)
        for (desk, doctype), fields in allow.items():
            self.assertIn("name", fields, f"{desk}/{doctype} cannot be identified")
            for field in fields:
                self.assertNotIn(field.lower(), SENSITIVE_FIELDS,
                                 f"{desk}/{doctype} projects sensitive field {field}")
        covered_desks = {key[0] for key in allow}
        self.assertLessEqual(
            {"reception", "academic", "finance", "management"}, covered_desks,
            "a desk has no projection allow-list")

    def test_desk_limits_stay_within_the_declared_bounds(self):
        source = self.sources["__init__"]
        for constant, bound in (("LIMIT_QUEUES", 100), ("LIMIT_TODAY", 100),
                                ("LIMIT_LOOKUP", 50), ("BOUNCE_WINDOW", 1000)):
            found = [line for line in source.splitlines()
                     if line.startswith(constant + " =")]
            self.assertTrue(found, f"{constant} is not declared")
            value = int(found[0].split("=")[1].strip())
            self.assertLessEqual(value, bound, f"{constant}={value} exceeds the desk bound")


class DeskAudienceTieTests(unittest.TestCase):
    """Page JSON, Python DESKS registry and the client SURFACES agree."""

    @classmethod
    def setUpClass(cls):
        cls.source = desk_sources()["__init__"]
        cls.desks = _literal_block(cls.source, "DESKS = {")
        cls.hooks = (APP / "hooks.py").read_text(encoding="utf-8")
        cls.client = (APP / "public/js/th_role_desks.js").read_text(encoding="utf-8")

    def test_desk_registry_is_complete(self):
        self.assertEqual(set(self.desks), {
            "th-reception-desk", "th-academic-desk", "th-finance-desk",
            "th-operations-desk", "th-owner-cockpit", "th-academic-setup"})
        roles = {row["name"] for row in json.loads(
            (APP / "fixtures/role.json").read_text(encoding="utf-8"))}
        for slug, spec in self.desks.items():
            self.assertTrue(set(spec["roles"]) <= roles, f"{slug} uses an unshipped role")

    def test_desk_pages_exist_with_matching_audience_and_module(self):
        for slug, spec in self.desks.items():
            path = APP / "operations" / "page" / slug / f"{slug}.json"
            self.assertTrue(path.exists(), f"missing Page JSON for {slug}")
            page = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(page["doctype"], "Page", slug)
            self.assertEqual(page["module"], spec["module"], slug)
            self.assertEqual(page["title"], spec["title"], slug)
            self.assertEqual([row["role"] for row in page["roles"]], spec["roles"], slug)
            self.assertEqual(page.get("standard"), "Yes", slug)

    def test_client_surfaces_match_the_desk_registry(self):
        for slug, spec in self.desks.items():
            self.assertIn(f'"{slug}"', self.client, f"{slug} missing from the desk client")
            self.assertIn(spec["title"], self.client, f"{slug} title drift in the client")

    def test_hooks_wire_every_desk_page_to_the_desk_client(self):
        for slug in self.desks:
            self.assertIn(f'"{slug}"', self.hooks, f"{slug} not wired in hooks")
        self.assertIn('"public/js/th_role_desks.js"', self.hooks)
        self.assertIn("_DESK_PAGES", self.hooks)

    def test_client_endpoints_match_the_whitelisted_desk_modules(self):
        module_of = {
            "th-reception-desk": "reception.work",
            "th-academic-desk": "academic.work",
            "th-finance-desk": "finance.work",
            "th-operations-desk": "operations.work",
            "th-owner-cockpit": "owner.cockpit",
            "th-academic-setup": "setup.work",
        }
        for slug, dotted in module_of.items():
            self.assertIn(f'"toefl_house.desk.{dotted}"', self.client,
                          f"{slug} client endpoint drift")
            module, func = dotted.split(".")
            self.assertIn(f"def {func}(", desk_sources()[module],
                          f"{module}.{func} missing")


class DeskReadEndpointExposureTests(unittest.TestCase):
    """Every desk read endpoint the client actually names must EXIST at that
    dotted path and be whitelisted (D1 recurrence guard).

    The stub's whitelist marks decorated functions exactly where real frappe
    would expose them, so this mirrors the HTTP request path: the client's
    own strings are resolved (a phantom module path like
    ``toefl_house.desk.registry.available`` fails resolution) and the
    resolved function must carry the whitelist mark with GET/POST methods.
    Deleting a decorator, renaming a module or moving a function off the
    path the browser calls now fails the owned suite.
    """

    CLIENT = (APP / "public" / "js" / "th_role_desks.js").read_text(encoding="utf-8")

    def _client_named_desk_methods(self):
        import re
        named = set(re.findall(r'"(toefl_house\.desk\.[A-Za-z_.]+)"', self.CLIENT))
        self.assertIn("toefl_house.desk.available", named,
                      "the client must resolve the desk registry via the real module path")
        return named

    def test_every_named_desk_method_resolves_to_a_marked_endpoint(self):
        for dotted in sorted(self._client_named_desk_methods()):
            with self.subTest(endpoint=dotted):
                parts = dotted.split(".")
                self.assertIn(parts[1], ("desk",), dotted)
                if len(parts) == 4:
                    module_name, func = parts[2], parts[3]
                elif len(parts) == 3:
                    module_name, func = "__init__", parts[2]
                else:
                    self.fail(f"unexpected desk method depth: {dotted}")
                self.assertIn(module_name, DESK_MODULES, f"{dotted} has no desk module file")
                module = _import_desk(module_name)
                target = getattr(module, func, None)
                self.assertIsNotNone(target, f"{dotted} does not resolve to a callable")
                self.assertTrue(getattr(target, "__frappe_whitelisted__", False),
                                f"{dotted} is callable but NOT whitelisted — the browser "
                                "will be refused at the API layer (D1 class)")
                self.assertTrue({"GET", "POST"} <= set(
                    getattr(target, "__frappe_whitelist_methods__", ())),
                    f"{dotted} must accept GET and POST like every desk read")


class DeskSchemaFidelityTests(unittest.TestCase):
    """No desk may ever query a column the pinned authority does not have.

    D2 class prevention, in two layers: the PROJECTION_FIELDS allow-lists
    are diffed against the frozen native ledgers (pinned_schema.json), and
    every project_rows/project_count CALL SITE in every desk module is
    scanned (doctype, projected fields, filter keys and order-by columns all
    resolved through module constants) against the same ledgers. A future
    upstream revision that drops a column fails here the moment the ledger
    is regenerated — and a desk reaching for a nicer-sounding field that was
    never real (active, currency, applicant_name) fails immediately.
    """

    @classmethod
    def setUpClass(cls):
        cls.sources = desk_sources()
        cls.trees = desk_trees()

    def test_projection_allow_lists_are_schema_real(self):
        block = _literal_block(self.sources["__init__"], "PROJECTION_FIELDS = {")
        self.assertTrue(block)
        for (desk, doctype), fields in block.items():
            assert_columns_real(f"PROJECTION_FIELDS[{desk},{doctype}]", doctype, fields)

    def test_every_desk_query_site_uses_real_columns(self):
        for name in ("reception", "academic", "finance", "operations", "owner",
                     "setup"):
            tree = self.trees[name]
            strings, lists = {}, {}
            for node in tree.body:
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                    try:
                        value = ast.literal_eval(node.value)
                    except Exception:
                        continue
                    if isinstance(value, str):
                        strings[node.targets[0].id] = value
                    elif isinstance(value, list):
                        lists[node.targets[0].id] = value

            def resolve(node):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    return node.value
                if isinstance(node, ast.Name):
                    return strings.get(node.id)
                return None

            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in ("project_rows", "project_count")):
                    continue
                args = node.args
                self.assertTrue(len(args) >= 2, f"{name}: query without a doctype")
                doctype = resolve(args[1])
                self.assertIsNotNone(
                    doctype, f"{name}:{node.lineno} doctype argument must be a "
                             "module-level literal (keeps the ledger honest)")
                fields, filter_node = [], None
                if node.func.id == "project_rows":
                    if len(args) > 2:
                        third = args[2]
                        if isinstance(third, ast.Name) and third.id in lists:
                            fields = lists[third.id]
                        else:
                            try:
                                fields = ast.literal_eval(third)
                            except Exception:
                                fields = []
                    filter_node = args[3] if len(args) > 3 else next(
                        (k.value for k in node.keywords if k.arg == "filters"), None)
                else:
                    fields = ["name"]
                    filter_node = args[2] if len(args) > 2 else next(
                        (k.value for k in node.keywords if k.arg == "filters"), None)
                filter_keys = []
                if isinstance(filter_node, ast.Dict):
                    for key in filter_node.keys:
                        try:
                            filter_keys.append(ast.literal_eval(key))
                        except Exception:
                            filter_keys.append(None)
                order_by = next((k for k in node.keywords if k.arg == "order_by"), None)
                columns = list(fields) + [k for k in filter_keys if k]
                if order_by is not None:
                    try:
                        clause = ast.literal_eval(order_by.value) or ""
                    except Exception:
                        clause = ""
                    for part in str(clause).split(","):
                        part = part.strip().split()
                        if part and part[0].replace("_", "").isalnum():
                            columns.append(part[0])
                assert_columns_real(f"{name}:{node.lineno}", doctype, columns)


class LifecycleStageTests(unittest.TestCase):
    """The stage machine is the shared vocabulary of the five desks."""

    @classmethod
    def setUpClass(cls):
        cls.lifecycle = _import_desk("lifecycle")

    def test_placement_attempt_states_map_to_a_stage(self):
        for state in self.lifecycle.PLACEMENT_ATTEMPT_ORDER[:-1]:
            stage = self.lifecycle.placement_session_stage(state)
            self.assertTrue(stage["label"], state)
            self.assertTrue(stage["next"], state)
            self.assertTrue(stage["role"], state)
        self.assertIsNone(self.lifecycle.placement_session_stage("Finalized"))
        self.assertIsNone(self.lifecycle.placement_session_stage("Nonsense"))

    def test_admission_stage_matrix(self):
        cases = [
            ("Draft", False, False, "Admission drafted", "Admission Reviewer"),
            ("Review", False, False, "Admission review", "Admission Approver"),
            ("Approved", False, False, "Admission decided", "Admission Officer"),
            ("Conditional", False, False, "Conditional admission", "Admission Officer"),
            ("Approved", True, False, "Offer accepted", "Admission Approver"),
            ("Approved", True, True, "Student created", "Enrollment Officer"),
            ("Deferred", False, False, "Deferred", "Admission Officer"),
            ("Rejected", False, False, "Rejected", None),
            ("Withdrawn", False, False, "Withdrawn", None),
            ("Revoked", False, False, "Revoked", None),
            ("Expired", False, False, "Expired", None),
        ]
        for status, accepted, converted, label, role in cases:
            stage = self.lifecycle.admission_stage(status, accepted, converted)
            self.assertEqual(stage["label"], label, status)
            self.assertEqual(stage["role"], role, status)
            self.assertTrue(stage["definition"], status)
            self.assertTrue(stage["next"], status)

    def test_unknown_admission_status_fails_into_an_explicit_stage(self):
        stage = self.lifecycle.admission_stage("Mystery", False, False)
        self.assertIsNone(stage["role"])
        self.assertIn("not one of the defined states", stage["definition"])

    def test_enrollment_stage_matrix(self):
        self.assertEqual(self.lifecycle.enrollment_stage(False, False)["label"],
                         "Awaiting enrollment")
        self.assertEqual(self.lifecycle.enrollment_stage(True, False)["label"],
                         "Enrolled, no class")
        self.assertEqual(self.lifecycle.enrollment_stage(True, True)["label"], "Enrolled")

    def test_every_stage_label_appears_in_the_funnel_order(self):
        produced = {"Placement session", "Marking", "Independent review",
                    "Awaiting release", "Admission drafted", "Admission review",
                    "Admission decided", "Conditional admission", "Offer accepted",
                    "Student created", "Awaiting enrollment", "Enrolled, no class",
                    "Enrolled", "Deferred"}
        for label in produced:
            self.assertIn(label, self.lifecycle.funnel_order(),
                          f"funnel order is missing stage {label}")


class FinanceVocabularyTests(unittest.TestCase):
    """The finance desk never invents a money status."""

    @classmethod
    def setUpClass(cls):
        cls.finance = _import_desk("finance")

    def test_cancelled_wins_over_everything(self):
        row = {"docstatus": 2, "outstanding_amount": 5, "status": "Unpaid"}
        self.assertEqual(self.finance._money_state(row), "Cancelled")
        self.assertEqual(self.finance._invoice_display_state(row), "Cancelled")

    def test_native_invoice_status_wins(self):
        for status in ("Overdue", "Paid", "Unpaid", "Return", "Credit Note Issued"):
            row = {"docstatus": 1, "outstanding_amount": 10, "status": status,
                   "due_date": "2026-01-01"}
            self.assertEqual(self.finance._invoice_display_state(row), status)

    def test_fee_states_come_from_the_native_numbers(self):
        settled = {"docstatus": 1, "outstanding_amount": 0, "grand_total": 100,
                   "due_date": "2026-01-01"}
        outstanding = {"docstatus": 1, "outstanding_amount": 40, "grand_total": 100,
                       "due_date": "2999-01-01"}
        overdue = {"docstatus": 1, "outstanding_amount": 40, "grand_total": 100,
                   "due_date": "2026-01-01"}
        self.assertEqual(self.finance._money_state(settled), "Settled")
        self.assertEqual(self.finance._money_state(outstanding), "Outstanding")
        self.assertEqual(self.finance._money_state(overdue), "Overdue")

    def test_correction_items_never_offer_an_action_without_a_policy(self):
        """Without an active policy the approval command would deny everyone,
        so the queue item must say so instead of rendering a failing button."""
        module = self.finance
        original_rows = module.project_rows
        module.project_rows = lambda *args, **kwargs: []
        try:
            items = module._correction_items([
                {"name": "CR-1", "sales_invoice": "INV-1", "reason": "wrong amount",
                 "requested_amount": 100, "status": "Requested", "modified": "2026-09-17"},
            ])
        finally:
            module.project_rows = original_rows
        self.assertEqual(len(items), 1)
        self.assertNotIn("action", items[0])
        self.assertIn("No active correction policy", items[0]["next"])

    def test_correction_items_offer_the_policy_approver_action(self):
        module = self.finance
        original_rows = module.project_rows
        original_guided = module.guided_action
        module.project_rows = lambda *args, **kwargs: [
            {"approver_role": "Admission Approver"}]
        module.guided_action = lambda role, endpoint, label, args: {
            "role": role, "endpoint": endpoint, "label": label, "args": args}
        try:
            items = module._correction_items([
                {"name": "CR-1", "sales_invoice": "INV-1", "reason": "wrong amount",
                 "requested_amount": 100, "status": "Requested", "modified": "2026-09-17"},
            ])
        finally:
            module.project_rows = original_rows
            module.guided_action = original_guided
        self.assertEqual(items[0]["action"]["role"], "Admission Approver")
        self.assertEqual(items[0]["action"]["endpoint"],
                         "toefl_house.finance.corrections.approve_invoice_correction")

    def test_money_totals_summarize_per_currency(self):
        rows = [
            {"currency": "USD", "paid_amount": 100},
            {"currency": "USD", "paid_amount": 50.5},
            {"currency": "EUR", "paid_amount": 20},
        ]
        rendered = self.finance._summarize(rows, "paid_amount")
        self.assertIn("150.50 USD", rendered)
        self.assertIn("20.00 EUR", rendered)
        self.assertEqual(self.finance._summarize([], "paid_amount"), "0")


class GuidedActionTests(unittest.TestCase):
    """Guided actions exist only for viewers who hold the acting role."""

    def test_action_requires_the_acting_role(self):
        desk = _import_desk("__init__")
        original = desk.viewer_roles
        desk.viewer_roles = lambda: {"Reception"}
        try:
            action = desk.guided_action(
                "Admission Officer", "toefl_house.admission.review_admission",
                "Send for review", {"name": "X"})
        finally:
            desk.viewer_roles = original
        self.assertIsNone(action)
        desk.viewer_roles = lambda: {"Admission Reviewer"}
        try:
            action = desk.guided_action(
                "Admission Reviewer", "toefl_house.admission.review_admission",
                "Send for review", {"name": "X"})
        finally:
            desk.viewer_roles = original
        self.assertEqual(action["role"], "Admission Reviewer")
        self.assertEqual(action["endpoint"], "toefl_house.admission.review_admission")
        self.assertEqual(action["args"], {"name": "X"})


class ReceptionLookupTests(unittest.TestCase):
    """Lookup bounds and the audience gate are enforced server-side."""

    def test_short_query_is_refused(self):
        reception = _import_desk("reception", roles={"Reception"})
        with self.assertRaises(Exception) as ctx:
            reception.lookup("a")
        self.assertIn("two characters", str(ctx.exception))

    def test_long_query_is_truncated(self):
        reception = _import_desk("reception", roles={"Reception"})
        calls = []

        def fake_project_rows(desk, doctype, fields, filters=None, order_by=None, limit=0):
            calls.append((desk, doctype, filters))
            return []

        original = reception.project_rows
        reception.project_rows = fake_project_rows
        try:
            reception.lookup("x" * 300)
        finally:
            reception.project_rows = original
        self.assertTrue(calls, "a truncated query must still search")
        for _desk, _doctype, filters in calls:
            self.assertNotIn("x" * 121, str(filters),
                             "the lookup searched with untruncated text")


class GuidedEndpointRegistryTests(unittest.TestCase):
    """Every guided action endpoint is a real owned whitelisted command."""

    ENDPOINTS = {
        "toefl_house.admission.review_admission": ("admission/__init__.py",
                                                   ["request_key", "name", "expected_version"]),
        "toefl_house.admission.decide_admission": ("admission/__init__.py",
                                                   ["request_key", "name", "expected_version", "outcome", "reason", "conditions"]),
        "toefl_house.admission.accept_offer": ("admission/__init__.py",
                                               ["request_key", "name", "expected_version"]),
        "toefl_house.admission.convert_applicant": ("admission/__init__.py",
                                                    ["request_key", "name", "expected_version"]),
        "toefl_house.admission.create_admission": ("admission/__init__.py",
                                                   ["request_key", "student_applicant", "placement_decision", "existing_student"]),
        "toefl_house.admission.record_applicant": ("admission/__init__.py",
                                                   ["request_key", "placement_decision", "first_name", "program", "academic_year"]),
        "toefl_house.enrollment.enroll_in_program": ("enrollment/__init__.py",
                                                     ["request_key", "admission_decision"]),
        "toefl_house.api.release_decision": ("api.py",
                                             ["request_key", "attempt", "expected_version"]),
        "toefl_house.finance.issue_tuition_fees": ("finance/__init__.py",
                                                   ["request_key", "program_enrollment", "fee_structure", "posting_date", "due_date"]),
        "toefl_house.finance.corrections.approve_invoice_correction": ("finance/corrections.py",
                                                                       ["request_key", "request"]),
    }

    def test_every_guided_endpoint_is_whitelisted_with_the_expected_signature(self):
        client = (APP / "public/js/th_role_desks.js").read_text(encoding="utf-8")
        for endpoint, (module_path, signature) in self.ENDPOINTS.items():
            source = (APP / module_path).read_text(encoding="utf-8")
            func = endpoint.rsplit(".", 1)[1]
            found = __import__("re").search(
                rf"^def\s+{func}\(([^)]*)\):", source, __import__("re").M)
            self.assertTrue(found, f"{endpoint} is missing")
            position = found.start()
            self.assertIn("@frappe.whitelist", source[max(0, position - 500):position],
                          f"{endpoint} must stay whitelisted")
            parameters = [part.strip().split("=")[0] for part in found.group(1).split(",")]
            self.assertEqual(parameters, signature, endpoint)
            # the client dialog mirrors exactly this signature
            self.assertIn(f'"{endpoint}"', client, f"{endpoint} missing from the desk client")


class DeskWorkSmokeTests(unittest.TestCase):
    """Every desk endpoint must EXECUTE against the stub, not merely import.

    Source scans prove nothing about runtime: a missing import (the today()
    bug) only explodes when work() actually runs. This is the test that
    failure class can never pass again."""

    CASES = (
        ("reception", "work", {"Reception"}),
        ("academic", "work", {"Academic Manager"}),
        ("finance", "work", {"Finance Manager"}),
        ("operations", "work", {"General Manager"}),
        ("owner", "cockpit", {"Course Owner"}),
        ("setup", "work", {"Course Owner"}),
    )

    def test_every_desk_endpoint_runs_and_returns_sections(self):
        for module_name, entry, roles in self.CASES:
            with self.subTest(desk=module_name):
                module = _import_desk(module_name, roles=roles)
                payload = getattr(module, entry)()
                self.assertTrue(payload["desk"])
                self.assertIsInstance(payload["sections"], list)
                self.assertTrue(payload["sections"],
                                "a desk with no sections is an empty dashboard")
                for sect in payload["sections"]:
                    self.assertTrue(sect["title"])
                    self.assertIn(sect["kind"], ("facts", "queue", "links"))
                    self.assertTrue(sect["empty"], "every section needs an empty state")

    def test_desk_endpoints_refuse_the_wrong_role_at_runtime(self):
        module = _import_desk("finance", roles={"Reception"})
        with self.assertRaises(Exception) as ctx:
            module.work()
        self.assertIn("Finance", str(ctx.exception))


class SetupDeskWorldTests(unittest.TestCase):
    """The setup desk against a small configured world.

    Source pins prove the code exists; this proves the OWNER'S ANSWERS come
    out the other end: the progression chain reads in level order, a
    progression/sequence mismatch is named (§32 configuration validation as
    a visible fact), progression targets display their title (next_level
    stores the level CODE), and each active level states its billing
    readiness for the current academic year.
    """

    def _run(self, *, mismatch=False):
        world = {
            "TH Academic Program": [{
                "name": "PROG-GEN", "code": "GEN-ENG", "title": "General English",
                "status": "Active", "modified": "2026-09-01 10:00:00",
            }],
            "TH Program Level": [
                {"name": "LVL-A1", "family": "PROG-GEN", "code": "GEN-A1",
                 "title": "Pre-Starter", "sequence": 1, "status": "Active",
                 "native_program": "NATIVE-A1",
                 "next_level": "GEN-A3" if mismatch else "GEN-A2",
                 "modified": "2026-09-01 10:00:00"},
                {"name": "LVL-A2", "family": "PROG-GEN", "code": "GEN-A2",
                 "title": "Starter", "sequence": 2, "status": "Active",
                 "native_program": "NATIVE-A2", "next_level": "GEN-A3",
                 "modified": "2026-09-01 10:00:00"},
                {"name": "LVL-A3", "family": "PROG-GEN", "code": "GEN-A3",
                 "title": "Prep One", "sequence": 3, "status": "Active",
                 "native_program": "NATIVE-A3", "next_level": None,
                 "modified": "2026-09-01 10:00:00"},
            ],
            "TH Level Duration": [{
                "name": "DUR-1", "parent": "LVL-A1", "parenttype": "TH Program Level",
                "duration_value": 2, "duration_unit": "Month",
                "effective_from": "2026-01-01", "superseded_on": None,
                "reason": "initial", "set_by": "owner@example.com",
            }],
            "Program Enrollment": [{
                "name": "ENR-1", "program": "NATIVE-A1", "docstatus": 1,
            }],
            "Academic Year": [{
                "name": "2026-2027", "year_start_date": "2026-07-01",
                "year_end_date": "2027-06-30",
            }],
            "Fee Category": [{
                "name": "FT-TUITION", "category_name": "Tuition Fee",
                "description": "Term tuition", "item": "Tuition Fee",
            }],
            "Fee Structure": [{
                "name": "FS-A1", "program": "NATIVE-A1",
                "academic_year": "2026-2027", "company": "TOEFL House",
                "receivable_account": "Debtors - TH", "docstatus": 0,
                "total_amount": 5000,
            }],
            "Fee Component": [{
                "name": "FC-1", "parent": "FS-A1", "parenttype": "Fee Structure",
                "fees_category": "Tuition Fee", "amount": 5000, "idx": 1,
            }],
            "Program": [
                {"name": "NATIVE-A1", "program_name": "General English — Pre-Starter"},
                {"name": "NATIVE-A2", "program_name": "General English — Starter"},
                {"name": "NATIVE-A3", "program_name": "General English — Prep One"},
                {"name": "NATIVE-ORPHAN", "program_name": "Orphan Native Program"},
            ],
            "TH Discount Rule": [{
                "name": "SCHOLARSHIP-10", "code": "SCHOLARSHIP-10",
                "title": "10% Merit Scholarship", "discount_percentage": 10.0,
                "precedence": 10, "status": "Active", "fee_category": "Tuition Fee",
                "program": "PROG-GEN", "description": "Scholarship",
                "modified": "2026-09-01 10:00:00",
            }],
        }

        def world_get_all(doctype, filters=None, fields=None, order_by=None,
                          limit_start=None, limit_page_length=None, **kwargs):
            assert_columns_real("setup world", doctype,
                                list(fields or []) + list((filters or {}).keys()))
            rows = world.get(doctype, [])
            filters = filters or {}
            return [dict(row) for row in rows
                    if all(row.get(key) == value
                           for key, value in filters.items()
                           if key in row or value is not None)]

        module = _import_desk("setup", roles={"Course Owner"})
        module.frappe.get_all = world_get_all
        module.frappe.db.get_all = world_get_all
        return module.work()

    @staticmethod
    def _section(payload, sid):
        return next(sect for sect in payload["sections"] if sect["id"] == sid)

    @staticmethod
    def _item(payload, sid, item_id):
        items = SetupDeskWorldTests._section(payload, sid)["items"]
        return next(item for item in items if item["id"] == item_id)

    def test_progression_chain_reads_in_level_order(self):
        payload = self._run()
        facts = self._section(payload, "progression")["facts"]
        chain = next(fact for fact in facts if fact["label"] == "General English")
        self.assertEqual(
            chain["value"], "Pre-Starter → Starter → Prep One",
            "a consistent chain must read as the plain ordered chain")

    def test_progression_sequence_mismatch_is_named(self):
        payload = self._run(mismatch=True)
        facts = self._section(payload, "progression")["facts"]
        chain = next(fact for fact in facts if fact["label"] == "General English")
        self.assertIn("Pre-Starter progresses to Prep One", chain["value"])
        self.assertIn("not to the next position (Starter)", chain["value"])

    def test_progression_target_displays_the_title_not_the_code(self):
        payload = self._run()
        level = self._item(payload, "levels", "GEN-A1")
        self.assertIn("Progression: Starter.", level["next"],
                      "next_level stores the code; the desk must show the title")
        self.assertNotIn("GEN-A2", level["next"])

    def test_active_levels_state_their_billing_readiness(self):
        payload = self._run()
        ready = self._item(payload, "levels", "GEN-A1")
        self.assertIn("Fee plan ready for 2026-2027.", ready["next"])
        unready = self._item(payload, "levels", "GEN-A2")
        self.assertIn("No complete fee plan for 2026-2027 yet.", unready["next"])

    def test_the_orphan_native_program_is_audited(self):
        payload = self._run()
        facts = self._section(payload, "health")["facts"]
        orphan = next(fact for fact in facts
                      if "outside the control plane" in fact["label"])
        self.assertEqual(orphan["value"], 1,
                         "exactly one of the four native programs is unanchored")

    def test_discounts_section_and_health_fact(self):
        payload = self._run()
        facts = self._section(payload, "health")["facts"]
        disc_fact = next(fact for fact in facts if fact["label"] == "Active discount rules")
        self.assertEqual(disc_fact["value"], 1)

        disc_item = self._item(payload, "discounts", "SCHOLARSHIP-10")
        self.assertEqual(disc_item["status"], "Active")
        self.assertIn("10.0% discount", disc_item["detail"])
        self.assertEqual(disc_item["action"]["label"], "Retire discount rule")

        setup_act = self._item(payload, "setup", "new-discount-rule")
        self.assertEqual(setup_act["action"]["label"], "Define discount rule")


class FinanceBillingGuidanceWorldTests(unittest.TestCase):
    """U9: the awaiting-billing promise is the issuance command's own rule.

    A plan counts when it is non-cancelled and carries components — draft or
    submitted alike; empty drafts wait for the Owner, duplicates pause, and a
    null academic year on both sides still matches (the old rule keyed plans
    on a raw None and looked up "", so those enrollments were declared
    unconfigured while the command would have billed them).
    """

    def _payload(self):
        world = {
            "Program Enrollment": [
                {"name": "ENR-DRAFT", "student": "STU-1", "student_name": "One",
                 "program": "SYN-P1", "academic_year": "2026", "enrollment_date":
                 "2026-09-01", "docstatus": 1},
                {"name": "ENR-SUB", "student": "STU-2", "student_name": "Two",
                 "program": "SYN-P2", "academic_year": "2026", "enrollment_date":
                 "2026-09-02", "docstatus": 1},
                {"name": "ENR-NONE", "student": "STU-3", "student_name": "Three",
                 "program": "SYN-P3", "academic_year": "2026", "enrollment_date":
                 "2026-09-03", "docstatus": 1},
                {"name": "ENR-EMPTY", "student": "STU-4", "student_name": "Four",
                 "program": "SYN-P4", "academic_year": "2026", "enrollment_date":
                 "2026-09-04", "docstatus": 1},
                {"name": "ENR-TWO", "student": "STU-5", "student_name": "Five",
                 "program": "SYN-P5", "academic_year": "2026", "enrollment_date":
                 "2026-09-05", "docstatus": 1},
                {"name": "ENR-NULLYEAR", "student": "STU-6", "student_name": "Six",
                 "program": "SYN-P6", "academic_year": None, "enrollment_date":
                 "2026-09-06", "docstatus": 1},
                {"name": "ENR-CANCELLED", "student": "STU-7", "student_name": "Seven",
                 "program": "SYN-P7", "academic_year": "2026", "enrollment_date":
                 "2026-09-07", "docstatus": 1},
            ],
            "Fee Structure": [
                {"name": "FS-D", "program": "SYN-P1", "academic_year": "2026",
                 "company": "TH", "docstatus": 0},
                {"name": "FS-S", "program": "SYN-P2", "academic_year": "2026",
                 "company": "TH", "docstatus": 1},
                {"name": "FS-E", "program": "SYN-P4", "academic_year": "2026",
                 "company": "TH", "docstatus": 0},
                {"name": "FS-G1", "program": "SYN-P5", "academic_year": "2026",
                 "company": "TH", "docstatus": 0},
                {"name": "FS-G2", "program": "SYN-P5", "academic_year": "2026",
                 "company": "TH", "docstatus": 1},
                {"name": "FS-H", "program": "SYN-P6", "academic_year": None,
                 "company": "TH", "docstatus": 0},
                {"name": "FS-C", "program": "SYN-P7", "academic_year": "2026",
                 "company": "TH", "docstatus": 2},
            ],
            "Fee Component": [
                {"name": "FC-1", "parent": "FS-D", "parenttype": "Fee Structure",
                 "fees_category": "Tuition", "amount": 1000, "idx": 1},
                {"name": "FC-2", "parent": "FS-S", "parenttype": "Fee Structure",
                 "fees_category": "Tuition", "amount": 2000, "idx": 1},
                {"name": "FC-3", "parent": "FS-G1", "parenttype": "Fee Structure",
                 "fees_category": "Tuition", "amount": 500, "idx": 1},
                {"name": "FC-4", "parent": "FS-G2", "parenttype": "Fee Structure",
                 "fees_category": "Tuition", "amount": 600, "idx": 1},
                {"name": "FC-5", "parent": "FS-H", "parenttype": "Fee Structure",
                 "fees_category": "Tuition", "amount": 700, "idx": 1},
                {"name": "FC-6", "parent": "FS-C", "parenttype": "Fee Structure",
                 "fees_category": "Tuition", "amount": 800, "idx": 1},
            ],
        }

        def world_get_all(doctype, filters=None, fields=None, order_by=None,
                          limit_start=None, limit_page_length=None, **kwargs):
            assert_columns_real("billing world", doctype,
                                list(fields or []) + list((filters or {}).keys()))
            rows = world.get(doctype, [])
            filters = filters or {}
            kept = []
            for row in rows:
                ok = True
                for key, value in filters.items():
                    cell = row.get(key)
                    if isinstance(value, (tuple, list)) and len(value) == 2 \
                            and isinstance(value[0], str) and value[0] in ("in", "!=", ">"):
                        op, bound = value
                        if op == "in" and cell not in bound:
                            ok = False
                        elif op == "!=" and cell == bound:
                            ok = False
                        elif op == ">" and not (cell is not None and cell > bound):
                            ok = False
                    elif cell != value:
                        ok = False
                if ok:
                    kept.append(dict(row))
            return kept

        module = _import_desk("finance", roles={"Finance Manager", "Finance Officer"})
        module.frappe.get_all = world_get_all
        module.frappe.db.get_all = world_get_all
        return module.work()

    @staticmethod
    def _billing(payload):
        return next(sect for sect in payload["sections"] if sect["id"] == "billing")

    def _item(self, payload, enrollment):
        return next(item for item in self._billing(payload)["items"]
                    if item["id"] == enrollment)

    def test_submitted_plan_is_billed_not_blamed(self):
        payload = self._payload()
        item = self._item(payload, "ENR-SUB")
        self.assertEqual(item["action"]["endpoint"],
                         "toefl_house.finance.issue_tuition_fees")
        self.assertEqual(item["action"]["args"]["fee_structure"], "FS-S",
                         "a submitted plan with components is exactly what the "
                         "issuance command accepts; the desk must prefill it (U9)")
        self.assertNotIn("No fee plan", item["next"])

    def test_draft_plan_still_prefills(self):
        payload = self._payload()
        item = self._item(payload, "ENR-DRAFT")
        self.assertEqual(item["action"]["args"]["fee_structure"], "FS-D")

    def test_empty_draft_names_the_owner_completion(self):
        payload = self._payload()
        item = self._item(payload, "ENR-EMPTY")
        self.assertIn("has no components yet", item["next"])
        self.assertEqual(item["next_role"], "Course Owner")
        self.assertNotIn("action", item)

    def test_no_plan_says_so(self):
        payload = self._payload()
        item = self._item(payload, "ENR-NONE")
        self.assertIn("No fee plan is configured", item["next"])

    def test_two_complete_plans_pause_billing(self):
        payload = self._payload()
        item = self._item(payload, "ENR-TWO")
        self.assertIn("More than one complete fee plan", item["next"])
        self.assertNotIn("action", item)

    def test_null_academic_year_matches(self):
        payload = self._payload()
        item = self._item(payload, "ENR-NULLYEAR")
        self.assertEqual(item["action"]["args"]["fee_structure"], "FS-H",
                         "plan key normalization must not strand a null year")

    def test_cancelled_plan_is_not_usable(self):
        payload = self._payload()
        item = self._item(payload, "ENR-CANCELLED")
        self.assertIn("No fee plan is configured", item["next"],
                      "a cancelled plan is not a configured one")


class ManagementCorrectionsWorldTests(unittest.TestCase):
    """D6: a correction row on the GM desk names its real target."""

    def _payload(self):
        world = {
            "TH Correction Request": [
                {"name": "COR-1", "sales_invoice": None, "fees": "FEE-77",
                 "reason": "wrong amount", "requested_amount": 25000,
                 "status": "Requested", "modified": "2026-09-15 09:00:00"},
                {"name": "COR-2", "sales_invoice": "ACC-SINV-9", "fees": None,
                 "reason": "duplicate charge", "requested_amount": 3000,
                 "status": "Requested", "modified": "2026-09-16 09:00:00"},
                {"name": "COR-3", "sales_invoice": "ACC-SINV-10", "fees": None,
                 "reason": "already decided", "requested_amount": 10,
                 "status": "Posted", "modified": "2026-09-10 09:00:00"},
            ],
        }

        def world_get_all(doctype, filters=None, fields=None, order_by=None,
                          limit_start=None, limit_page_length=None, **kwargs):
            assert_columns_real("management world", doctype,
                                list(fields or []) + list((filters or {}).keys()))
            rows = world.get(doctype, [])
            filters = filters or {}
            kept = []
            for row in rows:
                ok = True
                for key, value in filters.items():
                    if isinstance(value, (tuple, list)) and len(value) == 2 \
                            and isinstance(value[0], str):
                        op, bound = value
                        if op == "in" and row.get(key) not in bound:
                            ok = False
                    elif row.get(key) != value:
                        ok = False
                if ok:
                    kept.append(dict(row))
            return kept

        module = _import_desk("operations", roles={"General Manager"})
        module.frappe.get_all = world_get_all
        module.frappe.db.get_all = world_get_all
        return module.work()

    def test_fees_correction_is_not_anonymous(self):
        payload = self._payload()
        items = {item["id"]: item for item in
                 next(sect for sect in payload["sections"] if sect["id"] == "exceptions")["items"]}
        self.assertIn("COR-1", items)
        self.assertEqual(items["COR-1"]["person"], "FEE-77",
                         "a fees correction must name the fee it targets (D6)")
        self.assertIn("Tuition-fee correction", items["COR-1"]["detail"])
        self.assertEqual(items["COR-2"]["person"], "ACC-SINV-9")
        self.assertIn("Invoice correction", items["COR-2"]["detail"])
        self.assertNotIn("COR-3", items, "only pending requests are exceptions")


if __name__ == "__main__":
    unittest.main()

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
                "operations", "owner")

SENSITIVE_FIELDS = {
    "answer", "content_hash", "result_json", "seed", "pool_digest",
    "key_version", "form_hash", "net_pay", "salary", "base",
    "encryption_key", "password", "secret",
}


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
    stub.whitelist = lambda **kwargs: (lambda func: func)
    stub.session = types.SimpleNamespace(user="desk-user@example.com")
    stub.get_roles = lambda user: set(roles)
    def _db_get_all(doctype, filters=None, fields=None, order_by=None,
                    limit_start=None, limit_page_length=None, **kwargs):
        return []

    stub.db = types.SimpleNamespace(
        get_value=lambda *args, **kwargs: 1,
        get_all=_db_get_all,
        get_list=_db_get_all,
        count=lambda doctype, filters=None: 0,
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
        for module in ("reception", "academic", "finance", "operations", "owner"):
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
        for name in ("reception", "academic", "finance", "operations", "owner"):
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
        for name in ("reception", "academic", "finance", "operations", "owner"):
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
            "th-operations-desk", "th-owner-cockpit"})
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
        }
        for slug, dotted in module_of.items():
            self.assertIn(f'"toefl_house.desk.{dotted}"', self.client,
                          f"{slug} client endpoint drift")
            module, func = dotted.split(".")
            self.assertIn(f"def {func}(", desk_sources()[module],
                          f"{module}.{func} missing")


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


if __name__ == "__main__":
    unittest.main()

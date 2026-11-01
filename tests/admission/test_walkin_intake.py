"""Real preliminary intake implementation against a guarded Frappe test double."""
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"
ACTOR = "reception@example.test"


class ValidationError(Exception):
    pass


class PermissionError(Exception):
    pass


class DuplicateEntryError(Exception):
    pass


class Row(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None


class Inquiry:
    def __init__(self, fixture, facts, new=False):
        self.fixture = fixture
        self.data = dict(facts)
        self.new = new
        self.name = self.data.get("name") or f"INQ-{len(fixture.saved) + 1:03d}"
        self.data["name"] = self.name

    def __getattr__(self, key):
        try:
            return self.data[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        if key in {"fixture", "data", "new", "name"}:
            object.__setattr__(self, key, value)
        else:
            self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)

    def is_new(self):
        return self.new

    def insert(self, ignore_permissions=False):
        assert ignore_permissions
        self.fixture.module.protect_inquiry(self)
        active_key = self.data.get("open_identity_key")
        if active_key and any(
                row.get("open_identity_key") == active_key
                for row in self.fixture.saved.values()):
            raise DuplicateEntryError("Duplicate open inquiry key")
        self.fixture.saved[self.name] = dict(self.data)
        self.new = False
        return self

    def save(self, ignore_permissions=False):
        assert ignore_permissions
        self.fixture.module.protect_inquiry(self)
        self.fixture.saved[self.name] = dict(self.data)
        return self


class ReceptionWalkinTests(unittest.TestCase):
    def setUp(self):
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
        self.saved = {}
        self.placement_attached = False
        self.kind = None
        self.audit = []
        f = self

        frappe = ModuleType("frappe")
        frappe.ValidationError = ValidationError
        frappe.PermissionError = PermissionError
        frappe.DuplicateEntryError = DuplicateEntryError
        frappe.session = SimpleNamespace(user=ACTOR)
        frappe.whitelist = lambda **_kwargs: lambda fn: fn

        def get_value(doctype, name, fields=None, as_dict=False, **kwargs):
            assert doctype == "TH Reception Inquiry"
            doc = f.saved.get(name)
            if doc is None:
                return None
            return Row({key: doc.get(key) for key in fields}) if as_dict else doc.get(fields)

        def get_doc(doctype, name=None, for_update=False):
            if isinstance(doctype, dict):
                assert doctype["doctype"] == "TH Reception Inquiry"
                return Inquiry(f, doctype, new=True)
            assert doctype == "TH Reception Inquiry" and for_update
            if name not in f.saved:
                raise ValidationError("Not found")
            return Inquiry(f, f.saved[name])

        frappe.db = SimpleNamespace(
            exists=lambda doctype, value: (
                doctype == "Branch" and value == "Branch Alpha"
                or doctype == "TH Placement Case" and f.placement_attached
                and value == {"reception_inquiry": "INQ-001"}),
            get_value=get_value)
        frappe.get_doc = get_doc
        def get_all(doctype, filters=None, fields=None, limit_page_length=None):
            assert doctype == "TH Reception Inquiry"
            assert set(filters) == {"th_branch", "phone", "person_name", "status"}
            statuses = set(filters["status"][1])
            return [{"name": name} for name, value in f.saved.items()
                    if value.get("th_branch") == filters["th_branch"]
                    and value.get("phone") == filters["phone"]
                    and value.get("person_name") == filters["person_name"]
                    and value.get("status") in statuses][:limit_page_length]
        frappe.get_all = get_all
        sys.modules["frappe"] = frappe

        package = ModuleType("toefl_house")
        package.__path__ = [str(APP)]
        sys.modules["toefl_house"] = package

        api = ModuleType("toefl_house.api")
        def execute(kind, request_key, payload, work):
            assert isinstance(request_key, str)
            f.audit.append((kind, dict(payload)))
            f.kind = kind
            try:
                return work(ACTOR)[0]
            finally:
                f.kind = None
        api._execute = execute
        sys.modules["toefl_house.api"] = api

        scope = ModuleType("toefl_house.command_scope")
        def resolve(branch, _actor):
            if branch and branch != "Branch Alpha":
                raise PermissionError("Out of branch")
            return branch or "Branch Alpha"
        scope.resolve_creation_branch = resolve
        sys.modules["toefl_house.command_scope"] = scope

        policy = ModuleType("toefl_house.policy")
        policy.digest = lambda value: "digest-" + str(len(repr(value)))
        sys.modules["toefl_house.policy"] = policy

        security = ModuleType("toefl_house.security")
        def require(doctype):
            if doctype != "TH Reception Inquiry" or f.kind not in {
                "create_walkin_inquiry", "update_walkin_inquiry"}:
                raise PermissionError("Guarded command required")
            return f.kind, ACTOR
        security.require_command = require
        security.record_synthetic_flag = lambda: 1
        sys.modules["toefl_house.security"] = security

        spec = importlib.util.spec_from_file_location(
            "toefl_house.reception_intake", APP / "reception_intake.py")
        self.module = importlib.util.module_from_spec(spec)
        sys.modules["toefl_house.reception_intake"] = self.module
        spec.loader.exec_module(self.module)

    def test_first_contact_needs_no_email_user_or_placement(self):
        result = self.module.create_walkin_inquiry(
            "key-new-001", "  Arefa Visitor  ", phone="+93 700 000 001",
            program_interest="English", notes="Call tomorrow")
        self.assertEqual(result["status"], "New")
        self.assertEqual(result["th_branch"], "Branch Alpha")
        self.assertEqual(self.saved["INQ-001"]["person_name"], "Arefa Visitor")
        self.assertNotIn("student_email_id", self.saved["INQ-001"])
        self.assertEqual([kind for kind, _ in self.audit], ["create_walkin_inquiry"])

    def test_same_open_visitor_and_phone_is_not_accidentally_registered_twice(self):
        self.module.create_walkin_inquiry("one", "Visitor",
                                          phone="۰۷۹۴۳۵۷۵۰۹")
        with self.assertRaisesRegex(ValidationError, "open inquiry already exists"):
            self.module.create_walkin_inquiry("two", "Visitor",
                                              phone="0794357509")
        self.assertEqual(len(self.saved), 1)

    def test_phone_separators_are_normalized_before_duplicate_warning(self):
        result = self.module.create_walkin_inquiry(
            "new", "Visitor", phone="۰۷۹-۴۳۵ ۷۵۰۹")
        self.assertEqual(result["status"], "New")
        self.assertEqual(self.saved["INQ-001"]["phone"], "0794357509")
        with self.assertRaisesRegex(ValidationError, "open inquiry already exists"):
            self.module.create_walkin_inquiry(
                "repeated", "Visitor", phone="0794357509")
        self.assertEqual(len(self.saved), 1)

    def test_shared_household_phone_does_not_merge_different_people(self):
        self.module.create_walkin_inquiry("one", "Visitor A", phone="0794357509")
        self.module.create_walkin_inquiry("two", "Visitor B", phone="0794357509")
        self.assertEqual(len(self.saved), 2)

    def test_unique_index_rejects_simultaneous_same_open_intake(self):
        # Simulate two requests both reading an empty pre-insert duplicate
        # list. The database uniqueness seam must reject the second write.
        self.module.frappe.get_all = lambda *_args, **_kwargs: []
        self.module.create_walkin_inquiry(
            "first", "Visitor", phone="0794357509")
        with self.assertRaisesRegex(ValidationError, "open inquiry already exists"):
            self.module.create_walkin_inquiry(
                "second", "Visitor", phone="079-435-7509")
        self.assertEqual(len(self.saved), 1)

    def test_closed_visit_permits_a_new_visit(self):
        self.module.create_walkin_inquiry("one", "Visitor", phone="0794357509")
        self.module.update_walkin_inquiry("done", "INQ-001", 1, "Closed", notes="Finished")
        self.assertIsNone(self.saved["INQ-001"]["open_identity_key"])
        self.module.create_walkin_inquiry("two", "Visitor", phone="0794357509")
        self.assertEqual(len(self.saved), 2)

    def test_phone_optional_but_untrusted_contact_is_rejected(self):
        self.module.create_walkin_inquiry("k", "Visitor", phone="")
        for phone in ("hello<script>", "100", "+9300000\nother"):
            with self.subTest(phone=phone), self.assertRaises(ValidationError):
                self.module.create_walkin_inquiry("k", "Visitor", phone=phone)

    def test_afghan_dari_decimal_phone_digits_are_normalized(self):
        self.module.create_walkin_inquiry(
            "key-dari-phone-0000000001", "Visitor",
            phone="۰۷۹۴۳۵۷۵۰۹")
        self.assertEqual(self.saved["INQ-001"]["phone"], "0794357509")

    def test_contact_cannot_be_only_punctuation(self):
        for phone in ("(((()", "+-----", "0" * 16):
            with self.subTest(phone=phone), self.assertRaises(ValidationError):
                self.module.create_walkin_inquiry("key-invalid-number-01", "Visitor", phone=phone)

    def test_missing_branch_resolution_is_rejected_before_write(self):
        self.module.resolve_creation_branch = lambda _branch, _actor: ""
        with self.assertRaises(ValidationError):
            self.module.create_walkin_inquiry("k", "Visitor")
        self.assertEqual(self.saved, {})

    def test_branch_refused_before_any_document_is_written(self):
        with self.assertRaises(PermissionError):
            self.module.create_walkin_inquiry("k", "Visitor", branch="Other Branch")
        self.assertEqual(self.saved, {})

    def test_normal_follow_up_checks_locked_revision(self):
        self.module.create_walkin_inquiry("new", "Visitor")
        record = self.module.update_walkin_inquiry(
            "update", "INQ-001", 1, "Awaiting Placement", notes="Booked for Thursday")
        self.assertEqual(record["version"], 2)
        self.assertEqual(record["status"], "Awaiting Placement")
        with self.assertRaises(ValidationError):
            self.module.update_walkin_inquiry("retry", "INQ-001", 1, "Closed")
        self.module.update_walkin_inquiry("close", "INQ-001", 2, "Closed")
        with self.assertRaises(ValidationError):
            self.module.update_walkin_inquiry("reopen", "INQ-001", 3, "Contacted")

    def test_cannot_downgrade_referred_visitor_after_placement_case_created(self):
        self.module.create_walkin_inquiry("new", "Visitor")
        self.module.update_walkin_inquiry(
            "sent", "INQ-001", 1, "Awaiting Placement")
        self.placement_attached = True
        with self.assertRaisesRegex(PermissionError, "linked to Placement"):
            self.module.update_walkin_inquiry(
                "reverse", "INQ-001", 2, "Contacted")
        self.assertEqual(self.saved["INQ-001"]["version"], 2)
        self.module.update_walkin_inquiry(
            "close", "INQ-001", 2, "Closed")
        self.assertEqual(self.saved["INQ-001"]["status"], "Closed")

    def test_unchanged_followup_does_not_create_an_audit_revision(self):
        self.module.create_walkin_inquiry("new", "Visitor")
        self.module.update_walkin_inquiry("call", "INQ-001", 1, "Contacted", notes="Call made")
        with self.assertRaises(ValidationError):
            self.module.update_walkin_inquiry("no-op", "INQ-001", 2, "Contacted", notes="Call made")
        self.assertEqual(self.saved["INQ-001"]["version"], 2)

    def test_http_int_version_is_canonical_and_concurrent_safe(self):
        self.module.create_walkin_inquiry("new", "Visitor")
        result = self.module.update_walkin_inquiry(
            "follow-up", "INQ-001", "1", "Contacted")
        self.assertEqual(result["version"], 2)
        for version in (True, "01", "1.0", "-1", 1.5, "9999999999"):
            with self.subTest(version=version), self.assertRaises(ValidationError):
                self.module.update_walkin_inquiry(
                    "bad-version", "INQ-001", version, "Closed")

    def test_identity_cannot_be_mutated_by_follow_up(self):
        self.module.create_walkin_inquiry("new", "Visitor")
        doc = Inquiry(self, self.saved["INQ-001"])
        doc.person_name = "Another Person"
        doc.version += 1
        self.kind = "update_walkin_inquiry"
        with self.assertRaises(PermissionError):
            self.module.protect_inquiry(doc)
        with self.assertRaises(PermissionError):
            self.module.protect_inquiry(doc, "on_trash")

    def test_rejects_blank_control_names_and_note_overflow(self):
        for person, note in ((" ", ""), ("A\nB", ""), ("Visitor", "n" * 1001)):
            with self.subTest(person=person), self.assertRaises(ValidationError):
                self.module.create_walkin_inquiry("k", person, notes=note)


if __name__ == "__main__":
    unittest.main()

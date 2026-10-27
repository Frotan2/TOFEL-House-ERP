"""Mission 5 — End-to-end notification & portal verification (synthetic).

Covers:
- Dispatch rule configuration per event type (recipients, severity, timing, channel, retries, escalation, disabling)
- Durable notification lifecycle: queued → delivered → failed → acknowledged (no fake delivered)
- Provider-independent external interfaces (Dashboard/Email succeed, SMS/WhatsApp stub fails until bound)
- All 7 operational event generators
- Student portal isolation + IDOR/adversarial tests
- Guardian portal verified relationship + consent + revocation + age-privacy + record-level auth
- Portal/channel enable-disable controls (disabled by default)
- Failed-delivery handling and retry/escalation

Loads the REAL notification/portal modules against a stub frappe harness,
exactly like the existing alerting/guardian tests. No frappe site needed.
"""
import importlib.util
import sys
import types
import unittest
from types import SimpleNamespace
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "apps/toefl_house/toefl_house"

# ---------------------------------------------------------------------------
# Helpers to load real modules under stub frappe
# ---------------------------------------------------------------------------

def _load_real(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module

class _FakeDoc(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc
    def __setattr__(self, name, value):
        if name.startswith("_") or name in ("insert", "save", "is_new"):
            object.__setattr__(self, name, value)
        else:
            self[name] = value
    def get(self, k, d=None):
        return super().get(k, d)
    def append(self, field, row):
        self.setdefault(field, []).append(dict(row))
    def set(self, field, val):
        self[field] = val
    def as_dict(self):
        return dict(self)
    def save(self, ignore_permissions=False):
        self["_saved"] = True
        return self
    def insert(self, ignore_permissions=False):
        self["_inserted"] = True
        return self

# ---------------------------------------------------------------------------
# Test base
# ---------------------------------------------------------------------------

class BaseHarness(unittest.TestCase):
    def setUp(self):
        # Reset sys.modules snapshot like the real tests do
        self._prev = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(self._prev)))

        # In-memory stores for stub DB
        self.students = {}       # name -> {name, student_name, student_email_id, customer, date_of_birth}
        self.guardians = {}      # name -> {name, user}
        self.student_guardians = []  # list of {parent, guardian, parenttype, parentfield}
        self.users = {}          # user -> {name, email, enabled, roles}
        self.user_permissions = []   # list of {user, allow, for_value, apply_to_all_doctypes}
        self.guardian_consents = []  # TH Guardian Consent rows
        self.notifications = {}  # name -> notification dict/doc
        self.dispatch_rules = {}  # durable stub rows for policy dispatch rules
        self.fees = []
        self.course_schedules = []
        self.attendances = []
        self.assessment_results = []
        self.roster = []         # Student Group Student rows
        self.announcements = []

        # Control today/now
        self.today = "2026-10-24"
        self.now = "2026-10-24 12:00:00"

        fake = self

        def get_all(doctype, filters=None, fields=None, order_by=None, limit=None, limit_page_length=None, pluck=None, **kw):
            filters = filters or {}
            # Handle various doctypes
            def match(row, f):
                for k, v in (f or {}).items():
                    if isinstance(v, (list, tuple)) and len(v) == 2 and v[0] == "in":
                        if row.get(k) not in v[1]:
                            return False
                    elif isinstance(v, (list, tuple)) and len(v) == 2 and v[0] == ">":
                        if not (row.get(k) is not None and row.get(k) > v[1]):
                            return False
                    elif isinstance(v, (list, tuple)) and len(v) == 2 and v[0] == "<=":
                        if not (str(row.get(k) or "") <= str(v[1])):
                            return False
                    else:
                        if row.get(k) != v:
                            return False
                return True

            # Pluck helper
            def apply(rows):
                if pluck:
                    return [r.get(pluck) for r in rows]
                if fields:
                    out = []
                    for r in rows:
                        d = {}
                        for f in fields:
                            d[f] = r.get(f)
                        out.append(d)
                    return out
                return rows

            # Route
            if doctype == "Student":
                rows = [v for v in fake.students.values() if match(v, filters)]
                return apply(rows)[: (limit or limit_page_length or 9999) ]
            if doctype == "Guardian":
                rows = [v for v in fake.guardians.values() if match(v, filters)]
                return apply(rows)[: (limit or limit_page_length or 9999) ]
            if doctype == "Student Guardian":
                rows = [r for r in fake.student_guardians if match(r, filters)]
                return apply(rows)
            if doctype == "TH Guardian Consent":
                rows = [r for r in fake.guardian_consents if match(r, filters)]
                # order_by consent_date desc
                if order_by and "consent_date desc" in order_by:
                    rows = sorted(rows, key=lambda x: str(x.get("consent_date") or ""), reverse=True)
                lim = limit or limit_page_length
                if lim:
                    rows = rows[:lim]
                return apply(rows)
            if doctype == "User Permission":
                rows = [r for r in fake.user_permissions if match(r, filters)]
                return apply(rows)
            if doctype == "Student Group Student":
                rows = [r for r in fake.roster if match(r, filters)]
                return apply(rows)
            if doctype == "Course Schedule":
                rows = [r for r in fake.course_schedules if match(r, filters)]
                return apply(rows)
            if doctype == "Student Attendance":
                rows = [r for r in fake.attendances if match(r, filters)]
                return apply(rows)
            if doctype == "Assessment Result":
                rows = [r for r in fake.assessment_results if match(r, filters)]
                return apply(rows)
            if doctype == "Fees":
                rows = [r for r in fake.fees if match(r, filters)]
                return apply(rows)
            if doctype == "TH Portal Announcement":
                rows = [r for r in fake.announcements if match(r, filters)]
                return apply(rows)
            if doctype == "TH Portal Configuration":
                return []
            if doctype == "TH Notification":
                rows = [v for v in fake.notifications.values() if match(v, filters)]
                return apply(rows)
            if doctype == "TH Notification Dispatch Rule":
                rows = [r for r in fake.dispatch_rules.values() if match(r, filters)]
                return apply(rows)[:(limit or limit_page_length or 9999)]
            if doctype in ("TH Notification Recipient", "TH Notification Escalation Recipient"):
                field = ("recipients" if doctype == "TH Notification Recipient"
                         else "escalation_recipients")
                rows = [{"parent": r["name"], "recipient": address}
                        for r in fake.dispatch_rules.values()
                        for child in r.get(field, [])
                        for address in [child.get("recipient") if isinstance(child, dict) else child]
                        if match({"parent": r["name"], "recipient": address}, filters)]
                return apply(rows)[:(limit or limit_page_length or 9999)]
            # Default: empty
            return []

        def get_value(doctype, name_or_filters, fieldname=None, **kw):
            # name_or_filters can be a name string or dict filters
            if isinstance(name_or_filters, dict):
                rows = get_all(doctype, filters=name_or_filters, fields=[fieldname] if isinstance(fieldname, str) else fieldname, limit=1)
                if not rows:
                    return None
                row = rows[0]
                if isinstance(fieldname, list):
                    return {f: row.get(f) for f in fieldname}
                if fieldname:
                    return row.get(fieldname)
                return row
            # name string
            name = name_or_filters
            if doctype == "Student":
                s = fake.students.get(name)
                if not s:
                    return None
                if fieldname is None:
                    return s
                if isinstance(fieldname, list):
                    return {f: s.get(f) for f in fieldname}
                if isinstance(fieldname, str):
                    return s.get(fieldname)
                # as_dict case
                if kw.get("as_dict"):
                    return s
                return s.get(fieldname)
            if doctype == "Guardian":
                g = fake.guardians.get(name)
                if not g:
                    return None
                if isinstance(fieldname, str):
                    return g.get(fieldname)
                return g
            if doctype == "User":
                u = fake.users.get(name)
                if not u:
                    return None
                if isinstance(fieldname, str):
                    return u.get(fieldname)
                if isinstance(fieldname, list):
                    return {f: u.get(f) for f in fieldname}
                return u
            if doctype == "TH Guardian Consent":
                row = next((r for r in fake.guardian_consents if r.get("name") == name), None)
                if row is None:
                    return None
                if isinstance(fieldname, list):
                    fields = _FakeDoc({key: row.get(key) for key in fieldname})
                    return fields if kw.get("as_dict") else dict(fields)
                if isinstance(fieldname, str):
                    return row.get(fieldname)
                return _FakeDoc(dict(row)) if kw.get("as_dict") else dict(row)
            # fallback
            return None

        def get_doc(doctype, name=None, for_update=False, **kw):
            if isinstance(doctype, dict):
                d = dict(doctype)
                dt = d.get("doctype")
                if dt == "TH Notification":
                    # Generate a name if not provided
                    if "name" not in d:
                        import hashlib
                        h = hashlib.sha256((fake.now + d.get("title","")).encode()).hexdigest()[:8].upper()
                        d["name"] = f"NOTIF-{h}"
                    doc = _FakeDoc(d)
                    doc["_is_new"] = True
                    # Provide is_new helper
                    doc.is_new = lambda: getattr(doc, "_is_new", False)
                    orig_save = doc.save
                    orig_insert = doc.insert
                    def save_wrap(ignore_permissions=False):
                        fake.notifications[doc["name"]] = doc
                        return orig_save(ignore_permissions=ignore_permissions)
                    def insert_wrap(ignore_permissions=False):
                        fake.notifications[doc["name"]] = doc
                        doc["_is_new"] = False
                        return orig_insert(ignore_permissions=ignore_permissions)
                    doc.save = save_wrap
                    doc.insert = insert_wrap
                    return doc
                if dt == "TH Notification Dispatch Rule":
                    if "name" not in d:
                        d["name"] = "SYN-RULE-" + d["event_type"]
                    doc = _FakeDoc(d)
                    orig_save, orig_insert = doc.save, doc.insert
                    def persist(ignore_permissions=False):
                        fake.dispatch_rules[doc["name"]] = dict(doc)
                    def save_wrap(ignore_permissions=False):
                        persist(ignore_permissions)
                        return orig_save(ignore_permissions=ignore_permissions)
                    def insert_wrap(ignore_permissions=False):
                        persist(ignore_permissions)
                        return orig_insert(ignore_permissions=ignore_permissions)
                    doc.save, doc.insert = save_wrap, insert_wrap
                    return doc
                # TH Guardian Consent
                if dt == "TH Guardian Consent":
                    if "name" not in d:
                        import hashlib
                        h = hashlib.sha256((d.get("guardian","")+d.get("student","")+fake.now).encode()).hexdigest()[:8].upper()
                        d["name"] = f"CONSENT-{h}"
                    doc = _FakeDoc(d)
                    doc.is_new = lambda: True
                    orig_insert = doc.insert
                    def insert_wrap(ignore_permissions=False):
                        fake.guardian_consents.append(dict(doc))
                        doc["_is_new"] = False
                        return orig_insert(ignore_permissions=ignore_permissions)
                    doc.insert = insert_wrap
                    return doc
                # Generic fallback
                doc = _FakeDoc(d)
                doc.is_new = lambda: True
                return doc
            # doctype is string, name is identifier
            if doctype == "TH Notification":
                doc = fake.notifications.get(name)
                if doc is None:
                    raise Exception(f"Notification not found: {name}")
                # wrap as doc-like with save
                fd = _FakeDoc(dict(doc))
                fd.is_new = lambda: False
                orig_save = fd.save
                def save_wrap(ignore_permissions=False):
                    fake.notifications[fd["name"]] = dict(fd)
                    return orig_save(ignore_permissions=ignore_permissions)
                fd.save = save_wrap
                return fd
            if doctype == "TH Notification Dispatch Rule":
                row = fake.dispatch_rules.get(name)
                if not row:
                    raise Exception("Dispatch rule not found")
                doc = _FakeDoc(dict(row))
                orig_save = doc.save
                def save_wrap(ignore_permissions=False):
                    fake.dispatch_rules[name] = dict(doc)
                    return orig_save(ignore_permissions=ignore_permissions)
                doc.save = save_wrap
                return doc
            if doctype == "TH Guardian Consent":
                for c in fake.guardian_consents:
                    if c.get("name") == name:
                        fd = _FakeDoc(dict(c))
                        fd.is_new = lambda: False
                        orig_save = fd.save
                        def save_wrap(ignore_permissions=False):
                            for i, cc in enumerate(fake.guardian_consents):
                                if cc.get("name") == fd["name"]:
                                    fake.guardian_consents[i] = dict(fd)
                                    break
                            return orig_save(ignore_permissions=ignore_permissions)
                        fd.save = save_wrap
                        return fd
                raise Exception(f"Consent not found: {name}")
            if doctype == "Student":
                s = fake.students.get(name)
                if s:
                    return _FakeDoc(s)
                raise Exception(f"Student not found: {name}")
            # Generic
            raise Exception(f"get_doc unhandled: {doctype} {name}")

        def has_permission(*a, **kw):
            return True

        def throw(msg, *a, **kw):
            raise Exception(msg)

        stub = types.ModuleType("frappe")
        stub.PermissionError = PermissionError
        stub.ValidationError = ValueError
        stub.AuthenticationError = PermissionError
        stub.CSRFTokenError = PermissionError
        stub.DuplicateEntryError = Exception
        stub.throw = throw
        stub._ = lambda m: m
        stub.utils = SimpleNamespace(today=lambda: fake.today, now_datetime=lambda: fake.now)
        stub.db = SimpleNamespace(get_all=get_all, get_value=get_value, get_doc=get_doc, exists=lambda dt, n: False, sql=lambda *a, **kw: [], count=lambda dt, filters=None: 0, escape=lambda x: f"'{x}'")
        stub.get_doc = get_doc
        stub.get_all = get_all
        stub.get_value = get_value
        stub.has_permission = has_permission
        stub.get_roles = lambda user: fake.users.get(user, {}).get("roles", [])
        stub.session = SimpleNamespace(user="Guest", data=SimpleNamespace(csrf_token="tok"), sid="test")
        stub.flags = SimpleNamespace(in_test=True)
        stub.conf = {}
        stub.request = SimpleNamespace(path="/", method="GET")
        stub.form_dict = {}
        stub.local = SimpleNamespace(site="test.localhost")
        stub.whitelist = lambda **kw: (lambda f: f)
        stub.get_meta = lambda dt: SimpleNamespace(has_field=lambda f: True)
        # Expose test stores for portal helpers
        stub._test_consents = fake.guardian_consents

        model = types.ModuleType("frappe.model")
        document = types.ModuleType("frappe.model.document")
        document.Document = type("Document", (), {})
        model.document = document
        stub.model = model
        sys.modules["frappe"] = stub
        sys.modules["frappe.utils"] = stub.utils
        sys.modules["frappe.model"] = model
        sys.modules["frappe.model.document"] = document

        # Install package shims
        for pkg in ["toefl_house", "toefl_house.operations", "toefl_house.configuration", "toefl_house.academic", "foundation_security"]:
            if pkg not in sys.modules:
                m = types.ModuleType(pkg)
                m.__path__ = [str(APP)] if "toefl_house" in pkg else []
                sys.modules[pkg] = m
        # Load the pure approved Afghan calendar without the finance package's
        # operational dependencies in this isolated portal harness.
        finance = types.ModuleType("toefl_house.finance")
        finance.__path__ = [str(APP / "finance")]
        sys.modules["toefl_house.finance"] = finance
        _load_real("toefl_house.finance.shamsi", APP / "finance/shamsi.py")
        # The real foundation guardian hook is separately tested against
        # Frappe. This isolated harness provides the same fail-closed
        # membership/customer precondition using its synthetic records.
        guards = types.ModuleType("foundation_security.guards")
        def validate_guardian_scope():
            actor = stub.session.user
            if actor in (None, "Guest", "Administrator"):
                raise PermissionError("Guardian scope requires a signed-in guardian")
            if "Guardian" not in stub.get_roles(actor):
                raise PermissionError("Guardian role required")
            identities = [g for g in fake.guardians.values() if g.get("user") == actor]
            if len(identities) != 1:
                raise PermissionError("Exactly one canonical Guardian required")
            children = [x["parent"] for x in fake.student_guardians
                        if x.get("guardian") == identities[0]["name"]]
            if not children or any(
                    not fake.students.get(name, {}).get("customer")
                    for name in children):
                raise PermissionError("Guardian requires valid child/customer links")
        guards.validate_guardian_scope = validate_guardian_scope
        sys.modules["foundation_security.guards"] = guards

        # Real foundation rules (needed for some imports)
        def try_load(mod, rel):
            p = APP / rel
            if p.exists():
                _load_real(mod, p)
        try_load("toefl_house.configuration.rules", APP / "configuration/rules.py")
        try_load("toefl_house.policy", APP / "policy.py")
        # Load configuration audit stub
        audit = types.ModuleType("toefl_house.configuration.audit")
        def require_authority(authority):
            # No-op for tests — consider Course Owner always present for business_policy
            return "course.owner@example.com"
        def execute(kind, key, payload, work):
            return work("course.owner@example.com")[0]
        audit.require_authority = require_authority
        audit.execute = execute
        audit.latest_after_hash = lambda t: ""
        sys.modules["toefl_house.configuration.audit"] = audit
        # Load observable if exists
        try_load("toefl_house.observability", APP / "observability.py")
        # Load target modules under test
        self.portal_policy = _load_real("toefl_house.operations.portal_policy", APP / "operations/portal_policy.py")
        self.provider = _load_real("toefl_house.operations.external_provider", APP / "operations/external_provider.py")
        self.notifications_mod = _load_real("toefl_house.operations.notifications", APP / "operations/notifications.py")
        _load_real("toefl_house.operations.portal_dates", APP / "operations/portal_dates.py")
        self.student_portal = _load_real("toefl_house.operations.student_portal", APP / "operations/student_portal.py")
        self.guardian_portal = _load_real("toefl_house.operations.guardian_portal", APP / "operations/guardian_portal.py")
        # Reset memory flags/rules
        self.portal_policy.reset_memory_flags()
        self.provider.reset_registry()
        try:
            self.notifications_mod.reset_memory_rules()
        except Exception:
            pass
        # Ensure frappe session helper
        self.frappe = stub

    def _add_user(self, name, email=None, roles=None, enabled=True):
        self.users[name] = {"name": name, "email": email or name, "enabled": 1 if enabled else 0, "roles": list(roles or [])}

    def _add_student(self, name, email, customer="CUST-1", dob="2010-01-01"):
        self.students[name] = {"name": name, "student_name": name, "student_email_id": email, "customer": customer, "date_of_birth": dob}

    def _add_guardian(self, gname, user):
        self.guardians[gname] = {"name": gname, "user": user}

    def _link_guardian(self, student, guardian):
        self.student_guardians.append({"parent": student, "guardian": guardian, "parenttype": "Student", "parentfield": "guardians"})

    def _set_session(self, user):
        self.frappe.session.user = user


# ===========================================================================
# 1. Dispatch rule configurability
# ===========================================================================
class PortalFailClosedAuthorizationTests(BaseHarness):
    def test_process_memory_cannot_enable_production_portals(self):
        self.portal_policy.set_portal_flags(
            guardian_portal=True, student_portal=True,
            email=True, whatsapp=True)
        self.assertTrue(self.portal_policy.is_portal_enabled("guardian_portal"))
        self.frappe.flags.in_test = False
        self.assertFalse(self.portal_policy.is_portal_enabled("guardian_portal"))
        self.assertFalse(self.portal_policy.is_portal_enabled("student_portal"))
        self.assertFalse(self.portal_policy.is_channel_enabled("email"))
        self.assertFalse(self.portal_policy.is_channel_enabled("whatsapp"))

    def test_direct_doc_writes_cannot_activate_guardian_consents(self):
        path = APP / "operations/doctype/th_guardian_consent/th_guardian_consent.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn('foundation.active_command() != "approve_guardian_consent"', source)
        self.assertIn("recorded_by", source)


class DispatchRuleTests(BaseHarness):
    def test_all_event_types_have_disabled_default(self):
        for et in self.notifications_mod.EVENT_TYPES:
            rule = self.notifications_mod.get_dispatch_rule(et)
            self.assertFalse(rule["enabled"], et)

    def test_create_notification_when_disabled_returns_none(self):
        result = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="T", message="M"
        )
        self.assertIsNone(result)

    def test_enabled_rule_allows_notification_creation(self):
        self.notifications_mod.set_dispatch_rule({
            "event_type": "overdue_tuition", "enabled": True,
            "recipients": ["finance@example.com"], "severity": "critical",
            "channel": "Email", "max_retries": 3, "retry_delay_minutes": 15,
            "escalate_after_minutes": 60, "escalation_recipients": ["ops@example.com"],
            "timing_delay_minutes": 0
        })
        notif = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="Overdue fee", message="Fee overdue"
        )
        self.assertIsNotNone(notif)
        self.assertEqual(notif["status"], "queued")
        self.assertEqual(notif["severity"], "critical")
        self.assertEqual(notif["channel"], "Email")
        self.assertEqual(notif["max_retries"], 3)

    def test_severity_timing_channel_retries_escalation_configurable(self):
        self.notifications_mod.set_dispatch_rule({
            "event_type": "low_book_stock", "enabled": True,
            "recipients": ["ops@example.com"], "severity": "warning",
            "channel": "Dashboard", "timing_delay_minutes": 5,
            "max_retries": 5, "retry_delay_minutes": 10,
            "escalate_after_minutes": 120,
            "escalation_recipients": ["manager@example.com"]
        })
        rule = self.notifications_mod.get_dispatch_rule("low_book_stock")
        self.assertEqual(rule["severity"], "warning")
        self.assertEqual(rule["timing_delay_minutes"], 5)
        self.assertEqual(rule["channel"], "Dashboard")
        self.assertEqual(rule["max_retries"], 5)
        self.assertEqual(rule["escalate_after_minutes"], 120)

    def test_disabling_rule_stops_future_notifications(self):
        self.notifications_mod.set_dispatch_rule({
            "event_type": "class_change", "enabled": True,
            "recipients": ["a@example.com"], "severity": "info",
            "channel": "Dashboard", "max_retries": 1
        })
        n1 = self.notifications_mod.create_notification(event_type="class_change", title="T1", message="M1")
        self.assertIsNotNone(n1)
        # Disable
        self.notifications_mod.set_dispatch_rule({
            "event_type": "class_change", "enabled": False,
            "recipients": [], "severity": "info", "channel": "Dashboard"
        })
        n2 = self.notifications_mod.create_notification(event_type="class_change", title="T2", message="M2")
        self.assertIsNone(n2)

    def test_invalid_recipients_refused(self):
        with self.assertRaises(ValueError):
            self.notifications_mod.set_dispatch_rule({
                "event_type": "system_alert", "enabled": True,
                "recipients": [], "severity": "info", "channel": "Dashboard"
            })

    def test_seven_event_types_exist(self):
        self.assertEqual(len(self.notifications_mod.EVENT_TYPES), 7)
        self.assertIn("overdue_tuition", self.notifications_mod.EVENT_TYPES)
        self.assertIn("pending_academic_approval", self.notifications_mod.EVENT_TYPES)
        self.assertIn("incomplete_attendance", self.notifications_mod.EVENT_TYPES)
        self.assertIn("class_change", self.notifications_mod.EVENT_TYPES)
        self.assertIn("low_book_stock", self.notifications_mod.EVENT_TYPES)
        self.assertIn("scheduling_conflict", self.notifications_mod.EVENT_TYPES)
        self.assertIn("system_alert", self.notifications_mod.EVENT_TYPES)


# ===========================================================================
# 2. Durable notification lifecycle
# ===========================================================================
class NotificationLifecycleTests(BaseHarness):
    def _enable(self, et, channel="Dashboard"):
        self.notifications_mod.set_dispatch_rule({
            "event_type": et, "enabled": True, "recipients": ["a@example.com"],
            "severity": "warning", "channel": channel, "max_retries": 2, "retry_delay_minutes": 1
        })

    def test_queued_initially_never_fake_delivered(self):
        self._enable("overdue_tuition")
        n = self.notifications_mod.create_notification(event_type="overdue_tuition", title="T", message="M")
        self.assertEqual(n["status"], "queued")
        # Must not be delivered until attempt_delivery is called
        self.frappe.db.get_all("TH Notification", fields=["status"])[0] if self.frappe.db.get_all("TH Notification", fields=["status"]) else n
        self.assertNotEqual(n["status"], "delivered")

    def test_delivered_on_success(self):
        self._enable("overdue_tuition", channel="Dashboard")
        n = self.notifications_mod.create_notification(event_type="overdue_tuition", title="T", message="M")
        status, _ = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(status, "delivered")

    def test_failed_on_disabled_channel(self):
        self._enable("overdue_tuition", channel="SMS")  # SMS disabled by default
        n = self.notifications_mod.create_notification(event_type="overdue_tuition", title="T", message="M")
        status, detail = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(status, "failed")
        self.assertIn("disabled", detail.lower())

    def test_failed_then_retry_until_max(self):
        self._enable("overdue_tuition", channel="SMS")
        n = self.notifications_mod.create_notification(event_type="overdue_tuition", title="T", message="M")
        # First fail
        s1, _ = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(s1, "failed")
        # Retry — still fails (stub)
        s2, _ = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(s2, "failed")
        # After max_retries exhausted, stays failed
        s3, detail = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(s3, "failed")
        self.assertIn("max retries", detail.lower())

    def test_acknowledged_only_from_delivered(self):
        self._enable("overdue_tuition")
        n = self.notifications_mod.create_notification(event_type="overdue_tuition", title="T", message="M")
        # Cannot acknowledge queued
        with self.assertRaises(ValueError):
            self.notifications_mod.acknowledge_notification(n["name"])
        # Deliver then acknowledge
        self.notifications_mod.attempt_delivery(n["name"])
        status, _ = self.notifications_mod.acknowledge_notification(n["name"], actor="a@example.com")
        self.assertEqual(status, "acknowledged")

    def test_escalation_after_timeout(self):
        self.notifications_mod.set_dispatch_rule({
            "event_type": "overdue_tuition", "enabled": True, "recipients": ["a@example.com"],
            "severity": "critical", "channel": "Dashboard",
            "escalate_after_minutes": 60, "escalation_recipients": ["boss@example.com"],
            "max_retries": 1
        })
        n = self.notifications_mod.create_notification(event_type="overdue_tuition", title="T", message="M")
        self.notifications_mod.attempt_delivery(n["name"])
        # Not yet escalatable (created 0 min ago, needs 60)
        ok, _ = self.notifications_mod.escalate_if_needed(n["name"])
        self.assertFalse(ok)
        # Fast-forward time 2 hours
        self.notifications_mod._now = lambda: "2026-10-24 14:30:00"  # type: ignore
        # Actually we patch frappe.utils.now_datetime
        self.frappe.utils.now_datetime = lambda: "2026-10-24 14:30:00"
        ok2, detail2 = self.notifications_mod.escalate_if_needed(n["name"])
        self.assertTrue(ok2)
        self.assertIn("boss@example.com", detail2)


# ===========================================================================
# 3. Provider independence
# ===========================================================================
class ProviderTests(BaseHarness):
    def test_dashboard_and_email_providers_succeed_when_enabled(self):
        self.portal_policy.set_portal_flags(dashboard=True, email=True)
        self.notifications_mod.set_dispatch_rule({
            "event_type": "system_alert", "enabled": True, "recipients": ["a@example.com"],
            "severity": "info", "channel": "Dashboard"
        })
        n = self.notifications_mod.create_notification(event_type="system_alert", title="Sys", message="Hello")
        s, _ = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(s, "delivered")

    def test_sms_whatsapp_stub_fails_until_bound(self):
        self.portal_policy.set_portal_flags(sms=True, whatsapp=True)
        for ch in ("SMS", "WhatsApp"):
            payload = {"channel": ch, "recipient": "+123", "title": "T", "message": "M", "notification_id": "X"}
            ok, _, detail = self.provider.deliver(payload, check_enabled=False)
            # Stub always fails
            self.assertFalse(ok)

    def test_custom_provider_can_be_registered(self):
        class MockSms:
            name = "Mock SMS"
            def send(self, notification):
                return True
        self.provider.register_provider("sms", MockSms())
        self.portal_policy.set_portal_flags(sms=True)
        self.notifications_mod.set_dispatch_rule({
            "event_type": "overdue_tuition", "enabled": True, "recipients": ["+123"],
            "severity": "warning", "channel": "SMS", "max_retries": 1
        })
        n = self.notifications_mod.create_notification(event_type="overdue_tuition", title="T", message="M")
        s, _ = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(s, "delivered")


# ===========================================================================
# 4. Event generators for 7 types
# ===========================================================================
class EventGeneratorTests(BaseHarness):
    def setUp(self):
        super().setUp()
        # Enable all generators
        for et in self.notifications_mod.EVENT_TYPES:
            self.notifications_mod.set_dispatch_rule({
                "event_type": et, "enabled": True, "recipients": ["a@example.com"],
                "severity": "info", "channel": "Dashboard", "max_retries": 1
            })

    def test_overdue_tuition_generator(self):
        snap = {"fees": [{"name": "F-1", "student": "STU-1", "student_name": "Ali", "due_date": "2026-10-20", "outstanding_amount": 500, "docstatus": 1}]}
        specs = list(self.notifications_mod.generate_overdue_tuition(snap))
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["event_type"], "overdue_tuition")
        self.assertIn("Overdue", specs[0]["title"])

    def test_pending_academic_approval_generator(self):
        snap = {"admission_decisions": [{"name": "ADM-1", "student_applicant": "APP-1", "program": "TOEFL", "status": "Draft", "modified": "2026-10-24"}]}
        specs = list(self.notifications_mod.generate_pending_academic_approvals(snap))
        self.assertEqual(len(specs), 1)

    def test_incomplete_attendance_generator(self):
        snap = {"course_schedules": [{"name": "CS-1", "student_group": "G1", "schedule_date": "2026-10-23"}], "attendance_keys": set()}
        specs = list(self.notifications_mod.generate_incomplete_attendance(snap))
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["event_type"], "incomplete_attendance")

    def test_class_change_generator(self):
        snap = {"class_changes": [{"name": "G1", "change": "room changed", "modified": "2026-10-24"}]}
        specs = list(self.notifications_mod.generate_class_changes(snap))
        self.assertEqual(specs[0]["event_type"], "class_change")

    def test_low_book_stock_generator(self):
        snap = {"book_bins": [{"item_code": "BOOK-1", "item_name": "Oxford 101", "actual_qty": 2, "reorder_level": 5, "warehouse": "Main"}]}
        specs = list(self.notifications_mod.generate_low_book_stock(snap))
        self.assertEqual(len(specs), 1)
        snap_ok = {"book_bins": [{"item_code": "BOOK-1", "actual_qty": 10, "reorder_level": 5}]}
        self.assertEqual(len(list(self.notifications_mod.generate_low_book_stock(snap_ok))), 0)

    def test_scheduling_conflict_generator(self):
        snap = {"course_schedules": [
            {"name": "CS-1", "student_group": "G1", "schedule_date": "2026-10-24", "from_time": "09:00:00", "to_time": "10:00:00"},
            {"name": "CS-2", "student_group": "G1", "schedule_date": "2026-10-24", "from_time": "09:30:00", "to_time": "10:30:00"},
        ]}
        specs = list(self.notifications_mod.generate_scheduling_conflicts(snap))
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["event_type"], "scheduling_conflict")

    def test_system_alert_generator(self):
        snap = {"system_conditions": [{"condition": "unseen_error_logs", "detail": "3 errors", "observed": True}]}
        specs = list(self.notifications_mod.generate_system_alerts(snap))
        self.assertEqual(len(specs), 1)

    def test_generate_all_respects_enabled_flag(self):
        # Disable one
        self.notifications_mod.set_dispatch_rule({
            "event_type": "low_book_stock", "enabled": False, "recipients": [], "severity": "info", "channel": "Dashboard"
        })
        snap = {"book_bins": [{"item_code": "B", "actual_qty": 0, "reorder_level": 5}], "fees": []}
        specs = self.notifications_mod.generate_all_notifications(snap)
        ets = {s["event_type"] for s in specs}
        self.assertNotIn("low_book_stock", ets)


# ===========================================================================
# 5. Student portal — isolation and IDOR
# ===========================================================================
class StudentPortalTests(BaseHarness):
    def setUp(self):
        super().setUp()
        self.portal_policy.set_portal_flags(student_portal=True)
        self._add_user("alice@example.com", email="alice@example.com", roles=["Student"])
        self._add_user("bob@example.com", email="bob@example.com", roles=["Student"])
        self._add_student("STU-ALICE", "alice@example.com", customer="CUST-A", dob="2010-05-01")
        self._add_student("STU-BOB", "bob@example.com", customer="CUST-B", dob="2009-03-15")
        # Email on its own cannot establish a student identity. These
        # administrator-provisioned native User Permissions are the binding.
        self.user_permissions.extend([
            {"name": "UP-ALICE", "user": "alice@example.com",
             "allow": "Student", "for_value": "STU-ALICE"},
            {"name": "UP-BOB", "user": "bob@example.com",
             "allow": "Student", "for_value": "STU-BOB"},
        ])
        # Roster + schedules
        self.roster.append({"parent": "GRP-10A", "student": "STU-ALICE", "active": 1})
        self.course_schedules.append({"name": "CS-1", "student_group": "GRP-10A", "course": "TOEFL-A", "room": "R1", "schedule_date": "2026-10-24", "from_time": "09:00", "to_time": "10:00", "instructor": "T1"})
        self.attendances.append({"name": "ATT-1", "student": "STU-ALICE", "student_group": "GRP-10A", "course_schedule": "CS-1", "date": "2026-10-24", "status": "Present", "docstatus": 1})
        self.attendances.append({"name": "ATT-2", "student": "STU-BOB", "student_group": "GRP-10B", "course_schedule": "CS-2", "date": "2026-10-24", "status": "Present", "docstatus": 1})
        self.fees.append({"name": "FEE-ALICE", "student": "STU-ALICE", "program": "TOEFL", "academic_year": "2026", "grand_total": 1000, "outstanding_amount": 200, "due_date": "2026-10-20", "docstatus": 1})
        self.fees.append({"name": "FEE-BOB", "student": "STU-BOB", "program": "TOEFL", "academic_year": "2026", "grand_total": 1000, "outstanding_amount": 0, "due_date": "2026-10-20", "docstatus": 1})
        self.assessment_results.append({"name": "AR-1", "student": "STU-ALICE", "assessment_plan": "AP-1", "grade": "A", "docstatus": 1, "posting_date": "2026-10-24"})
        self.assessment_results.append({"name": "AR-2", "student": "STU-BOB", "assessment_plan": "AP-1", "grade": "C", "docstatus": 0, "posting_date": "2026-10-24"})  # draft — not visible
        self.announcements.append({"name": "ANN-1", "title": "Welcome", "message": "Hello students", "publish_date": "2026-10-24", "audience": "All", "status": "Published"})

    def test_portal_disabled_by_default(self):
        self.portal_policy.reset_memory_flags()
        self._set_session("alice@example.com")
        with self.assertRaises(PermissionError):
            self.student_portal.get_my_schedule()

    def test_student_sees_own_schedule_only(self):
        self._set_session("alice@example.com")
        sched = self.student_portal.get_my_schedule()
        self.assertEqual(len(sched), 1)
        self.assertEqual(sched[0]["name"], "CS-1")

    def test_schedule_shows_status_and_afghan_date_only_for_active_roster(self):
        self._set_session("alice@example.com")
        self.course_schedules[0]["th_session_status"] = "Postponed"
        self.roster.append({"parent": "OLD", "student": "STU-ALICE", "active": 0})
        self.course_schedules.append({"name": "OLD-SESSION", "student_group": "OLD", "schedule_date": "2026-10-24"})
        schedule = self.student_portal.get_my_schedule()
        self.assertEqual(len(schedule), 1)
        self.assertEqual(schedule[0]["th_session_status"], "Postponed")
        self.assertEqual(schedule[0]["schedule_date_shamsi"], "02 عقرب 1405")
        self.assertEqual(schedule[0]["schedule_date"], "2026-10-24")
        attendance = self.student_portal.get_my_attendance()
        self.assertEqual(attendance[0]["date_shamsi"], "02 عقرب 1405")

    def test_student_sees_own_attendance_only(self):
        self._set_session("alice@example.com")
        rows = self.student_portal.get_my_attendance()
        self.assertTrue(all(r["student"] == "STU-ALICE" for r in rows))
        self.assertEqual(len(rows), 1)

    def test_student_sees_only_approved_grades(self):
        self._set_session("alice@example.com")
        grades = self.student_portal.get_my_grades()
        self.assertEqual(len(grades), 1)
        self.assertEqual(grades[0]["grade"], "A")

    def test_student_sees_own_fees_only(self):
        self._set_session("alice@example.com")
        data = self.student_portal.get_my_fees()
        self.assertEqual(len(data["fees"]), 1)
        self.assertEqual(data["fees"][0]["name"], "FEE-ALICE")

    def test_email_match_without_native_student_binding_cannot_access_records(self):
        self._set_session("alice@example.com")
        self.user_permissions = [
            p for p in self.user_permissions if p.get("user") != "alice@example.com"
        ]
        with self.assertRaises(PermissionError):
            self.student_portal.get_my_attendance()

    def test_disabled_student_account_cannot_read_grades(self):
        self._set_session("alice@example.com")
        self.users["alice@example.com"]["enabled"] = 0
        with self.assertRaises(PermissionError):
            self.student_portal.get_my_grades()

    def test_idor_via_explicit_student_param_blocked(self):
        self._set_session("alice@example.com")
        # Attempt to fetch Bob's attendance via manipulated ID
        with self.assertRaises(PermissionError):
            self.student_portal.get_attendance_for_student(student="STU-BOB")

    def test_idor_predictable_ids_blocked(self):
        self._set_session("alice@example.com")
        with self.assertRaises(PermissionError):
            self.student_portal.get_fees_for_student(student="STU-BOB")

    def test_unauthenticated_denied(self):
        self._set_session("Guest")
        with self.assertRaises(PermissionError):
            self.student_portal.get_my_schedule()

    def test_announcements_visible(self):
        self._set_session("alice@example.com")
        anns = self.student_portal.get_announcements()
        self.assertEqual(len(anns), 1)
        self.assertEqual(anns[0]["title"], "Welcome")

    def _set_session(self, user):
        self.frappe.session.user = user
        # ensure roles
        if user not in self.users:
            self._add_user(user, email=user, roles=[])


# ===========================================================================
# 6. Guardian portal — verified relationship, consent, revocation, privacy
# ===========================================================================
class GuardianPortalTests(BaseHarness):
    def setUp(self):
        super().setUp()
        self.portal_policy.set_portal_flags(guardian_portal=True)
        # Guardian user + two children (one minor, one adult)
        self._add_user("guardian@example.com", email="guardian@example.com", roles=["Guardian"])
        self._add_user("other.guardian@example.com", email="other.guardian@example.com", roles=["Guardian"])
        self._add_student("STU-CHILD1", "child1@example.com", customer="CUST-1", dob="2015-06-01")  # 11y
        self._add_student("STU-CHILD2", "child2@example.com", customer="CUST-2", dob="2000-01-01")  # 26y adult
        self._add_student("STU-OTHER", "other@example.com", customer="CUST-3", dob="2012-01-01")
        self._add_guardian("GUARD-1", "guardian@example.com")
        self._add_guardian("GUARD-2", "other.guardian@example.com")
        self._link_guardian("STU-CHILD1", "GUARD-1")
        self._link_guardian("STU-CHILD2", "GUARD-1")
        self._link_guardian("STU-OTHER", "GUARD-2")
        # Roster + attendance for child1
        self.roster.append({"parent": "GRP-1", "student": "STU-CHILD1", "active": 1})
        self.course_schedules.append({"name": "CS-G1", "student_group": "GRP-1", "course": "TOEFL", "room": "R1", "schedule_date": "2026-10-24", "from_time": "09:00", "to_time": "10:00", "instructor": "T1"})
        self.attendances.append({"name": "ATT-C1", "student": "STU-CHILD1", "student_group": "GRP-1", "course_schedule": "CS-G1", "date": "2026-10-24", "status": "Present", "docstatus": 1})
        self.fees.append({"name": "FEE-C1", "student": "STU-CHILD1", "program": "TOEFL", "academic_year": "2026", "grand_total": 500, "outstanding_amount": 100, "due_date": "2026-10-20", "docstatus": 1})
        self.fees.append({"name": "FEE-OTHER", "student": "STU-OTHER", "program": "TOEFL", "academic_year": "2026", "grand_total": 500, "outstanding_amount": 200, "due_date": "2026-10-20", "docstatus": 1})
        self.assessment_results.append({"name": "AR-C1", "student": "STU-CHILD1", "assessment_plan": "AP-1", "grade": "B", "docstatus": 1, "posting_date": "2026-10-24"})
        self.announcements.append({"name": "ANN-G1", "title": "Parent meeting", "message": "On Friday", "publish_date": "2026-10-24", "audience": "Guardians", "status": "Published"})
        # Also need guardian lifecycle policy governing terms for consent
        # Mock governing_guardian_lifecycle to return active policy
        import types as _t
        gl = _t.ModuleType("toefl_house.operations.guardian_lifecycle")
        gl.governing_guardian_lifecycle = lambda on_date=None: {
            "effective_from": "2026-10-20", "delegation_window_days": 90,
            "pre_admission_proxy": "Allowed", "consent_evidence": "Link",
            "consent_expiry_days": 365,
            "records_recording_rights": "Test rights text"
        }
        sys.modules["toefl_house.operations.guardian_lifecycle"] = gl

    def _approve_independently(self, student):
        """Guardian evidence alone is insufficient: staff must approve it."""
        self._set_session("guardian@example.com")
        pending = self.guardian_portal.record_consent(
            student=student, evidence_type="Link",
            link_reference="https://example.com/consent")
        with self.assertRaises(PermissionError):
            self.guardian_portal.get_child_attendance(student=student)
        return self.guardian_portal.approve_guardian_consent(
            "synthetic-guardian-approval-" + student, pending["name"])

    def test_pending_evidence_does_not_authorize_private_student_data(self):
        self._set_session("guardian@example.com")
        pending = self.guardian_portal.record_consent(
            student="STU-CHILD1", evidence_type="Link",
            link_reference="https://example.com/evidence")
        self.assertEqual(pending["status"], "Pending")
        with self.assertRaises(PermissionError):
            self.guardian_portal.get_child_fees(student="STU-CHILD1")

    def test_portal_disabled_by_default(self):
        self.portal_policy.reset_memory_flags()
        self._set_session("guardian@example.com")
        with self.assertRaises(PermissionError):
            self.guardian_portal.get_my_children()

    def test_verified_children_only(self):
        self._set_session("guardian@example.com")
        children = self.guardian_portal.get_my_children()
        names = {c["name"] for c in children}
        self.assertIn("STU-CHILD1", names)
        self.assertIn("STU-CHILD2", names)
        self.assertNotIn("STU-OTHER", names)

    def test_consent_required_then_access_granted(self):
        self._set_session("guardian@example.com")
        # Without consent, access denied
        with self.assertRaises(PermissionError):
            self.guardian_portal.get_child_attendance(student="STU-CHILD1")
        # Record consent
        self._approve_independently("STU-CHILD1")
        rows = self.guardian_portal.get_child_attendance(student="STU-CHILD1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "ATT-C1")

    def test_child_endpoint_requires_nonempty_scalar_and_normalizes_scope(self):
        self._set_session("guardian@example.com")
        self._approve_independently("STU-CHILD1")
        methods = (self.guardian_portal.get_child_schedule, self.guardian_portal.get_child_attendance,
                   self.guardian_portal.get_child_grades, self.guardian_portal.get_child_fees)
        for method in methods:
            for student in (None, "", "  ", [], {"name": "STU-CHILD1"}):
                with self.subTest(method=method.__name__, student=student), self.assertRaises(ValueError):
                    method(student=student)
        rows = self.guardian_portal.get_child_attendance(student="  STU-CHILD1  ")
        self.assertEqual([row["name"] for row in rows], ["ATT-C1"])
        self.assertEqual(rows[0]["date_shamsi"], "02 عقرب 1405")

    def test_child_schedule_shows_status_and_never_an_inactive_group(self):
        self._set_session("guardian@example.com")
        self._approve_independently("STU-CHILD1")
        self.course_schedules[0]["th_session_status"] = "Cancelled"
        self.roster.append({"parent": "OLD", "student": "STU-CHILD1", "active": 0})
        self.course_schedules.append({"name": "OLD-SESSION", "student_group": "OLD", "schedule_date": "2026-10-24"})
        rows = self.guardian_portal.get_child_schedule(student="STU-CHILD1")
        self.assertEqual([row["name"] for row in rows], ["CS-G1"])
        self.assertEqual(rows[0]["th_session_status"], "Cancelled")
        self.assertEqual(rows[0]["schedule_date_shamsi"], "02 عقرب 1405")
        self.assertEqual(rows[0]["schedule_date"], "2026-10-24")

    def test_revocation_immediately_denies(self):
        self._set_session("guardian@example.com")
        self._approve_independently("STU-CHILD1")
        # Access works
        self.guardian_portal.get_child_attendance(student="STU-CHILD1")
        # Revoke
        self.guardian_portal.revoke_consent(student="STU-CHILD1", reason="No longer need")
        with self.assertRaises(PermissionError):
            self.guardian_portal.get_child_attendance(student="STU-CHILD1")

    def test_idor_other_guardians_child_blocked(self):
        self._set_session("guardian@example.com")
        # GUARD-1 trying to access STU-OTHER (belongs to GUARD-2)
        with self.assertRaises(PermissionError):
            self.guardian_portal.get_child_fees(student="STU-OTHER")

    def test_adult_student_requires_consent(self):
        self._set_session("guardian@example.com")
        # STU-CHILD2 is adult (26) — even with verified relationship, consent required
        with self.assertRaises(PermissionError):
            self.guardian_portal.get_child_grades(student="STU-CHILD2")
        # After consent, allowed
        self._approve_independently("STU-CHILD2")
        rows = self.guardian_portal.get_child_grades(student="STU-CHILD2")
        # No grades for child2, but call succeeds (empty list) rather than PermissionError
        self.assertIsInstance(rows, list)

    def test_record_level_authorization(self):
        self._set_session("guardian@example.com")
        self._approve_independently("STU-CHILD1")
        # Guardian can see child1 fees but not other
        data = self.guardian_portal.get_child_fees(student="STU-CHILD1")
        self.assertEqual(len(data["fees"]), 1)
        self.assertEqual(data["fees"][0]["name"], "FEE-C1")
        with self.assertRaises(PermissionError):
            self.guardian_portal.get_child_fees(student="STU-OTHER")

    def test_announcements_for_guardian(self):
        self._set_session("guardian@example.com")
        anns = self.guardian_portal.get_announcements_for_guardian()
        self.assertEqual(len(anns), 1)

    def _set_session(self, user):
        self.frappe.session.user = user
        if user not in self.users:
            self._add_user(user, email=user, roles=[])


# ===========================================================================
# 7. Administrative enable/disable controls independently
# ===========================================================================
class AdminControlsTests(BaseHarness):
    def test_portals_disabled_by_default(self):
        self.portal_policy.reset_memory_flags()
        self.assertFalse(self.portal_policy.is_portal_enabled("student_portal"))
        self.assertFalse(self.portal_policy.is_portal_enabled("guardian_portal"))

    def test_channels_disabled_by_default_except_dashboard(self):
        self.portal_policy.reset_memory_flags()
        self.assertFalse(self.portal_policy.is_channel_enabled("sms"))
        self.assertFalse(self.portal_policy.is_channel_enabled("whatsapp"))
        self.assertFalse(self.portal_policy.is_channel_enabled("email"))
        self.assertTrue(self.portal_policy.is_channel_enabled("dashboard"))

    def test_each_portal_toggle_independent(self):
        self.portal_policy.set_portal_flags(student_portal=True)
        self.assertTrue(self.portal_policy.is_portal_enabled("student_portal"))
        self.assertFalse(self.portal_policy.is_portal_enabled("guardian_portal"))
        self.portal_policy.set_portal_flags(guardian_portal=True)
        self.assertTrue(self.portal_policy.is_portal_enabled("guardian_portal"))
        self.assertTrue(self.portal_policy.is_portal_enabled("student_portal"))
        self.portal_policy.set_portal_flags(student_portal=False)
        self.assertFalse(self.portal_policy.is_portal_enabled("student_portal"))
        self.assertTrue(self.portal_policy.is_portal_enabled("guardian_portal"))

    def test_each_channel_toggle_independent(self):
        self.portal_policy.set_portal_flags(email=True)
        self.assertTrue(self.portal_policy.is_channel_enabled("email"))
        self.assertFalse(self.portal_policy.is_channel_enabled("sms"))
        self.portal_policy.set_portal_flags(sms=True)
        self.assertTrue(self.portal_policy.is_channel_enabled("sms"))
        self.assertTrue(self.portal_policy.is_channel_enabled("email"))


# ===========================================================================
# 8. Privacy adversarial — never leak other student's data
# ===========================================================================
class PrivacyAdversarialTests(BaseHarness):
    def setUp(self):
        super().setUp()
        self.portal_policy.set_portal_flags(student_portal=True)
        self._add_user("alice@example.com", email="alice@example.com", roles=["Student"])
        self._add_user("mallory@example.com", email="mallory@example.com", roles=["Student"])
        self._add_student("STU-ALICE", "alice@example.com", customer="CUST-A")
        self._add_student("STU-MALLORY", "mallory@example.com", customer="CUST-B")
        self.user_permissions.extend([
            {"name": "UP-PRIV-ALICE", "user": "alice@example.com",
             "allow": "Student", "for_value": "STU-ALICE"},
            {"name": "UP-PRIV-MALLORY", "user": "mallory@example.com",
             "allow": "Student", "for_value": "STU-MALLORY"},
        ])
        self.fees.append({"name": "FEE-ALICE", "student": "STU-ALICE", "grand_total": 1000, "outstanding_amount": 500, "docstatus": 1})
        self.fees.append({"name": "FEE-MALLORY", "student": "STU-MALLORY", "grand_total": 1000, "outstanding_amount": 0, "docstatus": 1})

    def test_query_manipulation_with_filter_injection_blocked(self):
        self.frappe.session.user = "mallory@example.com"
        # Even if attacker tries to inject a filter like {"student": ["in", ["STU-ALICE", "STU-MALLORY"]]}
        # the portal ignores caller filters and scopes by own student.
        # We test via the explicit method that takes student param.
        with self.assertRaises(PermissionError):
            self.student_portal.get_fees_for_student(student="STU-ALICE")

    def test_predictable_id_enumeration_blocked(self):
        self.frappe.session.user = "mallory@example.com"
        for fake_id in ("STU-001", "STU-ALICE", "1", "2", "STU-MALLORY' OR 1=1 --"):
            with self.subTest(fid=fake_id):
                with self.assertRaises(PermissionError):
                    self.student_portal.get_attendance_for_student(student=fake_id)

    def test_api_endpoint_without_student_param_still_scoped(self):
        self.frappe.session.user = "mallory@example.com"
        fees = self.student_portal.get_my_fees()
        self.assertTrue(all(f["student"] == "STU-MALLORY" for f in fees["fees"]))


if __name__ == "__main__":
    unittest.main()

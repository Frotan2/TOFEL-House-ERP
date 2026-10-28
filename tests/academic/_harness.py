"""Scripted Frappe harness for the academic assessment suite.

The owned suite runs without a site, database or Docker, so these tests load
the REAL academic assessment modules (`toefl_house.academic.grading`,
`.assessment`, `.progression`, `toefl_house.security`, `toefl_house.policy`)
against a small in-memory document store that implements exactly the Frappe
surface those modules use: ``db.get_value``/``get_all``/``exists``/``count``/
``sql``, ``get_doc`` with child tables, ``get_roles``/``session``, and the
command gate from ``toefl_house.api._execute``.

It is deliberately a *store*, not a Frappe clone: filters support only the
comparisons the academic code uses, and reading an unknown doctype raises
instead of returning an empty result, so a typo in the modules fails the test
rather than passing quietly.
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house"
SITE = "placement-test.localhost"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


_PURE = {}


def load_pure_modules(name):
    """Import one frappe-free owned module without running the package init.

    ``toefl_house.academic.__init__`` registers the whitelisted command
    surface and imports Frappe, so a pure rule module cannot be imported by
    its dotted name in the offline suite. Registering the package stubs with
    their real ``__path__`` lets Python resolve the submodule while skipping
    ``__init__``; ``sys.modules`` is restored afterwards so no other suite
    inherits these stubs.
    """
    if name in _PURE:
        return _PURE[name]
    previous = dict(sys.modules)
    try:
        for package in ("toefl_house", "toefl_house.academic",
                        "toefl_house.configuration"):
            module = types.ModuleType(package)
            module.__path__ = [str(APP / package.replace(".", "/"))]
            sys.modules[package] = module
        import importlib
        _PURE[name] = importlib.import_module(f"toefl_house.{name}")
        return _PURE[name]
    finally:
        sys.modules.clear()
        sys.modules.update(previous)


class ValidationError(Exception):
    pass


class FrappePermissionError(Exception):
    pass


class DuplicateEntryError(Exception):
    pass


def _matches(value, condition):
    if isinstance(condition, (list, tuple)):
        operator, operand = condition[0], condition[1]
        if operator == "<":
            return value is not None and str(value) != "" and str(value) < str(operand)
        if operator == "<=":
            return value is not None and str(value) != "" and str(value) <= str(operand)
        if operator == ">":
            return value is not None and str(value) != "" and str(value) > str(operand)
        if operator == "in":
            return value in operand
        if operator == "not in":
            return value not in operand
        if operator == "!=":
            return value != operand
        raise AssertionError(f"unsupported filter operator {operator!r}")
    return value == condition


class Child(dict):
    """A child row: dict storage plus Frappe's attribute/.get/as_dict surface."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value

    def get(self, field, default=None):
        return dict.get(self, field, default)

    def as_dict(self):
        return dict(self)


class Doc:
    """A document backed by the store, with the subset of Frappe's methods used."""

    def __init__(self, store, doctype, values=None, name=None, stored=False):
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "_doctype", doctype)
        object.__setattr__(self, "_values", {
            key: ([Child(row) if isinstance(row, dict) else row for row in value]
                  if isinstance(value, list) else value)
            for key, value in (values or {}).items()})
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_stored", stored)
        object.__setattr__(self, "_before",
                           store.snapshot(doctype, name) if stored else None)

    def __getattr__(self, field):
        if field.startswith("_"):
            raise AttributeError(field)
        return self._values.get(field)

    def __setattr__(self, field, value):
        if field.startswith("_"):
            object.__setattr__(self, field, value)
        else:
            self._values[field] = value

    def get(self, field, default=None):
        return self._values.get(field, default)

    def set(self, field, value):
        self._values[field] = value

    @property
    def name(self):
        return self._name

    @property
    def doctype(self):
        return self._doctype

    @property
    def docstatus(self):
        return int(self._values.get("docstatus") or 0)

    @property
    def flags(self):
        return self._values.setdefault("_flags", types.SimpleNamespace())

    def as_dict(self):
        out = {}
        for key, value in self._values.items():
            if key.startswith("_"):
                continue
            out[key] = ([Child(row) for row in value] if isinstance(value, list)
                        else value)
        return out

    def append(self, field, row):
        rows = self._values.setdefault(field, [])
        rows.append(Child(row))
        return rows[-1]

    def get_doc_before_save(self):
        return self._before

    def insert(self, ignore_permissions=False):
        if self._stored:
            raise AssertionError("insert called twice")
        self._store.insert(self)
        return self

    def save(self, ignore_permissions=False):
        if not self._stored:
            raise AssertionError("save called on an unsaved document")
        self._store.save(self)
        return self

    def submit(self):
        self._values["docstatus"] = 1
        self._store.save(self)
        return self

    def cancel(self):
        self._values["docstatus"] = 2
        self._store.save(self)
        return self

    def db_set(self, field, value):
        self._values[field] = value
        self._store.save(self, update_snapshot=False)
        return self


class Store:
    """In-memory documents keyed by doctype, with Frappe query semantics."""

    def __init__(self):
        self.docs = {}
        self.counters = {}
        self.calls = []

    def allow(self, doctype):
        """Declare a doctype this store may answer reads for (possibly empty)."""
        self.docs.setdefault(doctype, {})

    def seed(self, doctype, values, name=None):
        name = name or values.get("name") or values.get("code")
        doc = Doc(self, doctype, values, name=name)
        self.insert(doc, name=name)
        return name

    def _next_name(self, doctype):
        self.counters[doctype] = self.counters.get(doctype, 0) + 1
        prefix = "".join(word[0] for word in doctype.split())[:4].upper()
        return f"{prefix}-{self.counters[doctype]:05d}"

    def insert(self, doc, name=None):
        table = self.docs.setdefault(doc.doctype, {})
        name = name or doc.get("name") or self._next_name(doc.doctype)
        if name in table:
            raise DuplicateEntryError(f"{doc.doctype} {name} already exists")
        object.__setattr__(doc, "_name", name)
        doc._values["name"] = name
        doc._values.setdefault("docstatus", 0)
        table[name] = self._dump(doc)
        object.__setattr__(doc, "_stored", True)
        object.__setattr__(doc, "_before", self.snapshot(doc.doctype, name))
        return name

    def save(self, doc, update_snapshot=True):
        table = self.docs.setdefault(doc.doctype, {})
        if doc.name not in table:
            raise AssertionError(f"{doc.doctype} {doc.name} is not stored")
        table[doc.name] = self._dump(doc)
        if update_snapshot:
            object.__setattr__(doc, "_before", self.snapshot(doc.doctype, doc.name))

    def _dump(self, doc):
        out = {}
        for key, value in doc._values.items():
            if key.startswith("_") or key == "name":
                continue
            out[key] = [dict(row) for row in value] if isinstance(value, list) else value
        return out

    def snapshot(self, doctype, name):
        if not name:
            return None
        stored = self.docs.get(doctype, {}).get(name)
        if stored is None:
            return None
        return Doc(self, doctype, dict(stored), name=name, stored=False)

    def load(self, doctype, name):
        stored = self.docs.get(doctype, {}).get(name)
        if stored is None:
            return None
        return Doc(self, doctype, dict(stored), name=name, stored=True)

    def rows(self, doctype):
        table = self.docs.get(doctype)
        if table is None:
            raise AssertionError(f"unexpected doctype read: {doctype}")
        return [dict(values, name=name) for name, values in table.items()]

    def find(self, doctype, filters=None, order_by=None, limit=None):
        rows = self.rows(doctype)
        if filters:
            rows = [row for row in rows
                    if all(_matches(row.get(field), condition)
                           for field, condition in filters.items())]
        if order_by:
            field, _, direction = order_by.partition(" ")
            rows.sort(key=lambda row: ((row.get(field) is None),
                                       str(row.get(field) or "")),
                      reverse=direction.strip().lower() == "desc")
        if limit:
            rows = rows[:limit]
        return rows


class Harness:
    """Install the stub frappe plus the real owned modules on a test case."""

    def __init__(self, test=None):
        self.store = Store()
        self.users = {}
        self.today = "2026-10-24"
        self.receipts = []
        self._install()

    # --- identity -------------------------------------------------------
    def grant(self, user, roles):
        self.users[user] = list(roles)

    def acting_as(self, user):
        self.frappe.session.user = user

    def roles_of(self, user=None):
        user = user or self.frappe.session.user
        return list(self.users.get(user, []))

    # --- frappe surface -------------------------------------------------
    def _install(self):
        # Each test gets a fresh stub: drop any modules imported against the
        # previous stub so the real owned modules rebind to this store.
        for name in [name for name in sys.modules
                     if name == "frappe" or name.startswith(("frappe.", "toefl_house"))]:
            del sys.modules[name]
        store = self.store
        harness = self

        frappe = types.ModuleType("frappe")
        frappe.ValidationError = ValidationError
        frappe.PermissionError = FrappePermissionError
        frappe.DuplicateEntryError = DuplicateEntryError
        frappe.whitelist = lambda **kwargs: (lambda func: func)
        frappe.session = types.SimpleNamespace(user="Administrator")
        frappe.local = types.SimpleNamespace(site=SITE, conf={})
        frappe.conf = {"toefl_house_synthetic_only": 1, "allow_tests": 1,
                       "encryption_key": "harness-key"}

        def get_doc(*args, **kwargs):
            if args and isinstance(args[0], dict):
                payload = dict(args[0])
                doctype = payload.pop("doctype")
                values = {key: ([Child(row) for row in value]
                                if isinstance(value, list) else value)
                          for key, value in payload.items()}
                return Doc(store, doctype, values, stored=False)
            doctype, name = args[0], args[1]
            doc = store.load(doctype, name)
            if doc is None:
                raise ValidationError(f"{doctype} {name} not found")
            return doc

        def get_value(doctype, name_or_filters, fieldname=None, as_dict=False, **kwargs):
            if isinstance(name_or_filters, str):
                row = store.docs.get(doctype, {}).get(name_or_filters)
                if row is None:
                    return None
                row = dict(row, name=name_or_filters)
            else:
                rows = store.find(doctype, filters=name_or_filters, limit=1)
                if not rows:
                    return None
                row = rows[0]
            if fieldname in (None, "*"):
                return row
            if isinstance(fieldname, str):
                value = row.get(fieldname)
                return types.SimpleNamespace(**{fieldname: value}) if as_dict else value
            if as_dict:
                return types.SimpleNamespace(
                    **{field: row.get(field) for field in fieldname})
            return tuple(row.get(field) for field in fieldname)

        def get_all(doctype, filters=None, fields=None, order_by=None, limit=None,
                    **kwargs):
            rows = store.find(doctype, filters=filters, order_by=order_by,
                              limit=limit or kwargs.get("limit_page_length"))
            if kwargs.get("pluck"):
                return [row.get(kwargs["pluck"]) for row in rows]
            # Frappe returns attribute-accessible dicts (frappe._dict); the
            # harness mirrors that so product code reads rows the same way it
            # does on a hosted site.
            if fields and fields != ["*"]:
                return [Child({field: row.get(field) for field in fields})
                        for row in rows]
            return [Child(row) for row in rows]

        def exists(doctype, name=None):
            table = store.docs.get(doctype)
            if table is None:
                raise AssertionError(f"unexpected exists read: {doctype}")
            if isinstance(name, str):
                return name in table
            if name is None:
                return bool(table)
            return bool(store.find(doctype, filters=name, limit=1))

        def count(doctype, filters=None):
            return len(store.find(doctype, filters=filters))

        def sql(query, values=None, **kwargs):
            """Answer only the identity-chain query the read scope issues."""
            if "TH Teaching Assignment" in query and "emp.user_id" in query:
                return harness.instructor_groups(query)
            return []

        frappe.db = types.SimpleNamespace(get_value=get_value, get_all=get_all,
                                          exists=exists, count=count, sql=sql,
                                          escape=lambda value: f"'{value}'")
        frappe.get_doc = get_doc
        frappe.get_all = get_all
        # Native frappe.get_list enforces per-document permission query hooks.
        # The isolated harness mirrors permitted synthetic rows here; separate
        # live-site tests validate the actual role-and-branch boundary.
        frappe.get_list = get_all
        frappe.get_roles = self.roles_of
        frappe.get_value = get_value
        frappe.has_permission = lambda *args, **kwargs: True
        frappe.utils = types.SimpleNamespace(
            today=lambda: harness.today,
            now_datetime=lambda: f"{harness.today} 12:00:00",
            add_days=lambda date, days: date)
        sys.modules["frappe"] = frappe
        sys.modules["frappe.utils"] = frappe.utils

        document_module = types.ModuleType("frappe.model.document")
        document_module.Document = type("Document", (), {})
        sys.modules["frappe.model"] = types.ModuleType("frappe.model")
        sys.modules["frappe.model.document"] = document_module
        self.frappe = frappe

        package = types.ModuleType("toefl_house")
        package.__path__ = [str(APP / "toefl_house")]
        sys.modules["toefl_house"] = package
        for name in ("configuration", "academic"):
            module = types.ModuleType(f"toefl_house.{name}")
            module.__path__ = [str(APP / "toefl_house" / name)]
            sys.modules[f"toefl_house.{name}"] = module

        from toefl_house import policy
        self.policy = policy
        from toefl_house import security
        self.security = security
        from toefl_house.configuration import rules as configuration_rules
        self.configuration_rules = configuration_rules
        from toefl_house.academic import rules as academic_rules
        self.rules = academic_rules
        from toefl_house.academic import grading
        self.grading = grading

        api = types.ModuleType("toefl_house.api")

        def _execute(kind, request_key, payload, work):
            """Mirror api._execute's gate: role authorization + command context.

            Operation receipts and the hash-chained audit are the shared api
            layer's own tested behaviour; the gate itself is what matters here.
            """
            self.security.authorize(self.security.KIND_ROLES[kind])
            actor = self.frappe.session.user
            harness.receipts.append((kind, request_key))
            with self.security.command(kind, actor):
                return work(actor)[0]

        api._execute = _execute
        sys.modules["toefl_house.api"] = api

        from toefl_house.academic import assessment, progression
        self.assessment = assessment
        self.progression = progression

    def close(self):
        """Drop the stub modules so no later suite inherits this store.

        The stub package is deliberately thin (``toefl_house.api`` here has no
        receipts/audit layer), so leaving it cached would poison a suite that
        imports the real module afterwards. Every academic case closes its
        harness in teardown.
        """
        for name in [name for name in sys.modules
                     if name == "frappe" or name.startswith(("frappe.", "toefl_house"))]:
            del sys.modules[name]

    def instructor_groups(self, query):
        """Resolve the instructor read scope: the classes this login teaches."""
        import re

        match = re.search(r"emp\.user_id = '([^']+)'", query)
        if not match:
            raise AssertionError(f"unexpected instructor scope query: {query}")
        user = match.group(1)
        employees = {name for name, values in
                     self.store.docs.get("Employee", {}).items()
                     if values.get("user_id") == user}
        instructors = {name for name, values in
                       self.store.docs.get("Instructor", {}).items()
                       if values.get("employee") in employees}
        return [{"student_group": values.get("student_group")}
                for values in self.store.docs.get("TH Teaching Assignment", {}).values()
                if values.get("instructor") in instructors]

    # --- common fixtures ------------------------------------------------
    def seed_world(self, *, scale="SYN-SCALE", policy_code="SYN-GEN-ENG",
                   include_next_level=True, attendance_status="Present"):
        """A minimal, realistic synthetic institute around one class."""
        allow = self.store.allow
        for doctype in ("TH Assessment Policy", "TH Assessment Policy Version",
                        "TH Program Level", "Student Group", "Student Group Student",
                        "Grading Scale", "Grading Scale Interval", "Student",
                        "TH Teaching Assignment", "Employee", "Instructor",
                        "Assessment Plan", "Assessment Group", "Program Enrollment",
                        "Assessment Criteria", "Assessment Result", "User",
                        "User Permission", "TH Assessment Book",
                        "TH Academic Result", "TH Progression Decision"):
            allow(doctype)
        for user, roles in (("academic.manager@example.test", ["Academic Manager"]),
                            ("instructor.one@example.test", ["Instructor"]),
                            ("instructor.two@example.test", ["Instructor"]),
                            ("general.manager@example.test", ["General Manager"]),
                            ("enrollment.officer@example.test", ["Enrollment Officer"]),
                            ("outsider@example.test", []),
                            ("unlinked@example.test", ["Instructor"]),
                            ("dual.role@example.test", ["Instructor", "Academic Manager"])):
            self.grant(user, roles)
        for user in list(self.users):
            self.store.seed("User", {"email": user, "enabled": 1}, name=user)
        # Native grading scale: the ONLY source of grade codes.
        self.store.seed("Grading Scale", {"grading_scale_name": scale}, name=scale)
        for code, threshold in (("A", 85), ("B", 70), ("C", 55)):
            self.store.seed("Grading Scale Interval",
                            {"parent": scale, "grade_code": code,
                             "threshold": threshold},
                            name=f"{scale}-{code}")
        # Catalog: level A1 -> A2.
        self.store.seed("Program", {"program_name": "SYN General English"},
                        name="SYN-GEN-ENG")
        self.store.seed("Program", {"program_name": "SYN General English 2"},
                        name="SYN-GEN-ENG-2")
        self.store.seed("TH Program Level",
                        {"code": "SYN-GE-1", "title": "General English 1",
                         "sequence": 1, "native_program": "SYN-GEN-ENG",
                         "next_level": "SYN-GE-2" if include_next_level else ""},
                        name="SYN-GE-1")
        self.store.seed("TH Program Level",
                        {"code": "SYN-GE-2", "title": "General English 2",
                         "sequence": 2, "native_program": "SYN-GEN-ENG-2",
                         "next_level": ""},
                        name="SYN-GE-2")
        # One class with three students.
        self.store.seed("Student Group",
                        {"student_group_name": "SYN-GRP-1",
                         "program": "SYN-GEN-ENG", "academic_year": "SYN-AY-2026",
                         "th_class_status": "Active"},
                        name="SYN-GRP-1")
        self.students = ["SYN-STU-1", "SYN-STU-2", "SYN-STU-3"]
        for student in self.students:
            self.store.seed("Student", {"first_name": student}, name=student)
            self.store.seed("Student Group Student",
                            {"parent": "SYN-GRP-1", "student": student, "active": 1},
                            name=f"SYN-GRP-1-{student}",
                            )
        # Instructors: `one` teaches this class, `two` does not.
        for user, instructor, employee in (
                ("instructor.one@example.test", "INS-1", "EMP-1"),
                ("instructor.two@example.test", "INS-2", "EMP-2")):
            self.store.seed("Employee", {"user_id": user, "status": "Active"},
                            name=employee)
            self.store.seed("Instructor", {"employee": employee}, name=instructor)
        self.store.seed("TH Teaching Assignment",
                        {"student_group": "SYN-GRP-1", "instructor": "INS-1",
                         "skill": "SL", "effective_start": "2026-01-01"},
                        name="ASSIGN-1")
        # Attendance for student 1 (all present) and student 2 (one absent).
        for index, status in enumerate((attendance_status, attendance_status,
                                        attendance_status)):
            self.store.seed("Student Attendance",
                            {"student": "SYN-STU-1", "student_group": "SYN-GRP-1",
                             "status": status, "docstatus": 1},
                            name=f"ATT-1-{index}")
        self.store.seed("Student Attendance",
                        {"student": "SYN-STU-2", "student_group": "SYN-GRP-1",
                         "status": "Present", "docstatus": 1}, name="ATT-2-0")
        self.store.seed("Student Attendance",
                        {"student": "SYN-STU-2", "student_group": "SYN-GRP-1",
                         "status": "Absent", "docstatus": 1}, name="ATT-2-1")
        return self

    def seed_policy(self, code="SYN-GEN-ENG", effective_from="2026-09-01",
                    components=None, weights=None, pass_rules=None,
                    progression=None, retakes=None, levels=("SYN-GE-1",),
                    scale="SYN-SCALE", status="Active", facets_override=None):
        """One assessment policy version with the given Owner-configured facets."""
        import json

        def dump(value):
            return "" if value is None else json.dumps(
                value, sort_keys=True, separators=(",", ":"))

        facets = {
            "components": components if components is not None else [
                {"code": "LISTENING", "title": "Listening", "maximum_score": 30},
                {"code": "READING", "title": "Reading", "maximum_score": 20},
            ],
            "weights": weights if weights is not None else [
                {"component": "LISTENING", "weight": 60},
                {"component": "READING", "weight": 40},
            ],
            "pass_rules": pass_rules if pass_rules is not None else {
                "components": [],
                "overall": {"kind": "percent", "value": 60},
            },
            "progression": progression if progression is not None else {
                "target": "next",
                "requires": [
                    {"kind": "assessment_pass", "policy": code},
                    {"kind": "attendance", "minimum_percent": 75},
                    {"kind": "approval", "role": "Academic Manager"},
                ],
            },
            "retakes": retakes if retakes is not None else {
                "max_attempts": 2, "wait_days": 14, "scope": "full",
                "governing": "latest",
            },
            "level_mapping": {"levels": list(levels)},
            "rubrics": None,
        }
        if facets_override:
            facets.update(facets_override)
        existing = self.store.docs.get("TH Assessment Policy", {}).get(code)
        if existing is None:
            name = self.store.seed("TH Assessment Policy",
                                   {"code": code, "title": code, "status": status,
                                    "family": "SYN-GEN-ENG", "versions": []},
                                   name=code)
        else:
            name = code
        policy = self.store.load("TH Assessment Policy", name)
        policy.versions = list(policy.get("versions") or [])
        policy.versions.append(Child({
            "parent": name, "effective_from": effective_from,
            "grading_scale": scale,
            "reason": "SYN owner configures assessment",
            "set_by": "course.owner@example.test",
            "set_on": "2026-09-01 00:00:00",
            "superseded_on": "",
            **{facet: dump(value) for facet, value in facets.items()
               if facet != "rubrics"},
        }))
        policy.status = status
        self.store.save(policy)
        return name

    def seed_native_plan(self, name="SYN-PLAN-1"):
        self.store.seed("Assessment Plan", {
            "student_group": "SYN-GRP-1",
            "program": "SYN-GEN-ENG",
            "course": "SYN-COURSE",
            "academic_year": "SYN-AY-2026",
            "academic_term": "",
            "assessment_group": "SYN-AG",
            "grading_scale": "SYN-SCALE",
            "maximum_assessment_score": 50,
            "assessment_criteria": [
                {"assessment_criteria": "Listening", "maximum_score": 30},
                {"assessment_criteria": "Reading", "maximum_score": 20},
            ],
        }, name=name)
        return name

    # --- convenience ----------------------------------------------------
    def open_book(self, *, policy="SYN-GEN-ENG", plan="", key=None,
                  actor="academic.manager@example.test", effective_from="2026-09-01",
                  retake_student=""):
        self.acting_as(actor)
        return self.assessment.open_assessment_book(
            key or f"key-open-{policy}", "SYN-GRP-1", policy,
            effective_from=effective_from, assessment_plan=plan,
            retake_student=retake_student)

    def record(self, book, marks, *, actor="instructor.one@example.test", key=None):
        self.acting_as(actor)
        return self.assessment.record_assessment_marks(
            key or f"key-marks-{len(self.receipts)}", book, marks)

    def full_marks(self, listening=24.0, reading=16.0, students=None):
        return [{"student": student, "component": "LISTENING", "mark": listening}
                for student in (students or self.students)] + \
               [{"student": student, "component": "READING", "mark": reading}
                for student in (students or self.students)]

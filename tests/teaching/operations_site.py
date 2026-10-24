"""In-memory Frappe stand-in for the Mission 3 class-operations suite.

The class-operations modules (policy, calendars, timetables, scheduling,
capacity, suspensions, transfers) are loaded as REAL source files against this
stub, so the tests exercise the shipped code rather than a paraphrase of it.

What the stub provides:

* a document store with insert/save/append semantics for owned DocTypes and
  native Student Group / Course Schedule / Student Attendance rows;
* ``db.get_value`` / ``exists`` / ``count`` / ``get_all`` with Frappe's filter
  language for the operators the modules use;
* a small, explicit SQL dispatcher for the handful of raw queries the modules
  issue (row locks, roster lookups, session overlap joins). An unknown query
  raises, so a new query cannot silently pass the suite untested;
* governance seams: the REAL ``toefl_house.configuration.rules`` module (it is
  Frappe-free) and a scripted ``configuration.audit.execute`` that mimics the
  one-request command transaction without a database.

Nothing here is a parallel implementation of a business rule: the tests assert
what the production modules do to this fake site.
"""
from copy import deepcopy
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"
ACTOR = "teaching.scheduler@example.test"
APPROVER = "academic.manager@example.test"
COURSE_OWNER = "course.owner@example.test"
RECEPTION = "receptionist@example.test"

AUTONAME = {
    "TH Class Operations Policy": "code",
    "TH Academic Calendar": "code",
    "TH Timetable Template": "code",
}

DEFAULT_ROLES = {
    ACTOR: ["Teaching Scheduler", "Teaching Auditor"],
    APPROVER: ["Academic Manager", "Teaching Scheduler"],
    COURSE_OWNER: ["Course Owner"],
    RECEPTION: ["Reception"],
}


class ValidationError(Exception):
    pass


class PermissionError_(Exception):
    pass


class DuplicateEntryError(Exception):
    pass


class DoesNotExistError(Exception):
    pass


class Row(dict):
    """A child-table row with attribute access, like a Frappe Document."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value

    def as_dict(self):
        return deepcopy(dict(self))


class Document(dict):
    """A stored document: dict semantics, attribute access, save/insert."""

    def __init__(self, site, doctype, data=None, name=None):
        dict.__init__(self)
        object.__setattr__(self, "_site", site)
        object.__setattr__(self, "doctype", doctype)
        object.__setattr__(self, "flags",
                           SimpleNamespace(ignore_permissions=False,
                                           ignore_links=False))
        self.update(_hydrate(data or {}))
        if name:
            self["name"] = name

    # -- attribute access -------------------------------------------------
    def __getattr__(self, name):
        # Frappe returns None for unset fields on a normal Document; mirror
        # that so a partially-populated fixture row behaves like a real one.
        return self.get(name)

    def __setattr__(self, name, value):
        if name in ("_site", "doctype", "flags"):
            object.__setattr__(self, name, value)
        else:
            self[name] = value

    def append(self, table, row):
        rows = self.setdefault(table, [])
        fresh = Row(row) if not isinstance(row, Row) else row
        rows.append(fresh)
        return fresh

    def set(self, table, rows):
        self[table] = [Row(row) for row in rows]

    def as_dict(self):
        return deepcopy(dict(self))

    # -- persistence ------------------------------------------------------
    def insert(self, ignore_permissions=False):
        site = self._site
        if not self.get("name"):
            field = AUTONAME.get(self.doctype)
            if field and self.get(field):
                self["name"] = str(self[field])
            else:
                self["name"] = site.next_name(self.doctype)
        table = site.table(self.doctype)
        if self["name"] in table:
            raise DuplicateEntryError(self["name"])
        table[self["name"]] = _snapshot(self)
        self._sync_children()
        site.inserted.append((self.doctype, self["name"]))
        return self

    def submit(self):
        self["docstatus"] = 1
        self.save()
        return self

    def cancel(self):
        self["docstatus"] = 2
        self.save()
        return self

    def save(self, ignore_permissions=False):
        site = self._site
        if not self.get("name") or self["name"] not in site.table(self.doctype):
            raise DoesNotExistError(self.get("name") or self.doctype)
        site.table(self.doctype)[self["name"]] = _snapshot(self)
        self._sync_children()
        site.saved.append((self.doctype, self["name"]))
        return self

    def _sync_children(self):
        """Mirror a native child table (Student Group.students) into its table."""
        if self.doctype != "Student Group" or "students" not in self:
            return
        child = self._site.table("Student Group Student")
        for name in [name for name, row in child.items()
                     if row.get("parent") == self["name"]]:
            del child[name]
        for index, row in enumerate(self["students"], 1):
            stored = dict(row)
            stored.update(parent=self["name"], parenttype="Student Group",
                          parentfield="students", idx=index)
            child[f"{self['name']}-R{index:03d}"] = _snapshot(stored)

    def db_set(self, field, value):
        self[field] = value
        return self.save()


def _hydrate(data):
    """Convert child lists to Row objects so ``.as_dict`` works as in Frappe."""
    hydrated = {}
    for key, value in data.items():
        if isinstance(value, list):
            hydrated[key] = [Row(row) if isinstance(row, dict) else row
                             for row in value]
        else:
            hydrated[key] = value
    return hydrated


def _snapshot(doc):
    stored = {}
    for key, value in doc.items():
        if isinstance(value, list):
            stored[key] = [Row(deepcopy(dict(row))) if isinstance(row, dict)
                           else deepcopy(row) for row in value]
        else:
            stored[key] = deepcopy(value)
    return stored


def _match(row, filters):
    for key, expected in (filters or {}).items():
        actual = row.get(key)
        if isinstance(expected, tuple) and len(expected) == 2:
            op, operand = expected
            if op == "in":
                if actual not in operand:
                    return False
            elif op == "not in":
                if actual in operand:
                    return False
            elif op == "!=":
                if actual == operand:
                    return False
            elif op == ">":
                if not (actual is not None and str(actual) > str(operand)):
                    return False
            elif op == ">=":
                if not (actual is not None and str(actual) >= str(operand)):
                    return False
            elif op == "<":
                if not (actual is not None and str(actual) < str(operand)):
                    return False
            elif op == "<=":
                if not (actual is not None and str(actual) <= str(operand)):
                    return False
            else:  # pragma: no cover - unknown operator is a test bug
                raise AssertionError(f"unsupported filter operator {op}")
        elif isinstance(expected, (list, set)):
            if actual not in expected:
                return False
        else:
            if actual != expected:
                return False
    return True


class Site:
    """One synthetic site: documents, roles, clock and an operation log."""

    def __init__(self, today="2026-09-22", now="2026-09-22 08:00:00"):
        self.today = today
        self.now = now
        self.rows = {}
        self.counters = {}
        self.roles = {user: list(roles) for user, roles in DEFAULT_ROLES.items()}
        self.inserted = []
        self.saved = []
        self.sql_log = []
        self.commands = []
        self.audit = []
        self.user = ACTOR
        self.conf = {"encryption_key": "unit-test-key"}

    # -- data -------------------------------------------------------------
    def table(self, doctype):
        return self.rows.setdefault(doctype, {})

    def add(self, doctype, **fields):
        """Seed one row (name honoured, then the DocType autoname, else auto)."""
        explicit = fields.pop("name", None)
        field = AUTONAME.get(doctype)
        name = explicit or (fields.get(field) if field else None) or \
            self.next_name(doctype)
        row = dict(fields)
        row["name"] = name
        row.setdefault("doctype", doctype)
        self.table(doctype)[name] = _snapshot(row)
        return name

    def next_name(self, doctype):
        index = self.counters.get(doctype, 0) + 1
        self.counters[doctype] = index
        slug = "".join(word[0] for word in doctype.split())[:3].upper()
        return f"{slug}-{index:04d}"

    def get(self, doctype, name):
        return self.table(doctype).get(name)

    def all(self, doctype):
        return list(self.table(doctype).values())

    def set_roles(self, user, roles):
        self.roles[user] = list(roles)

    # -- query helpers ----------------------------------------------------
    def select(self, doctype, filters=None, order_by=None, limit=None):
        rows = [row for row in self.table(doctype).values() if _match(row, filters)]
        if order_by:
            field, _, direction = order_by.partition(" ")
            rows.sort(key=lambda row: str(row.get(field) or ""),
                      reverse=direction.strip().lower().startswith("desc"))
        if limit:
            rows = rows[: int(limit)]
        return rows


def _query(sql):
    return " ".join(str(sql).split())


def _time_overlap(start, end, other_start, other_end):
    """Frappe stores times as timedelta/strings; compare as normalized text."""
    def norm(value):
        if hasattr(value, "total_seconds"):
            seconds = int(value.total_seconds())
            return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
        return str(value)[:8]
    return norm(start) < norm(other_end) and norm(end) > norm(other_start)


def build_frappe(site):
    frappe = types.ModuleType("frappe")
    frappe.ValidationError = ValidationError
    frappe.PermissionError = PermissionError_
    frappe.DuplicateEntryError = DuplicateEntryError
    frappe.DoesNotExistError = DoesNotExistError
    frappe.session = SimpleNamespace(user=site.user)
    frappe.conf = site.conf
    frappe._dict = dict
    frappe.whitelist = lambda *args, **kwargs: (lambda func: func)
    frappe.throw = lambda message, *a, **k: (_ for _ in ()).throw(ValidationError(message))

    def today():
        return site.today

    def now_datetime():
        return site.now

    frappe.utils = SimpleNamespace(today=today, now_datetime=now_datetime,
                                   get_date_str=lambda value: str(value))

    def get_roles(user=None):
        return list(site.roles.get(user or frappe.session.user, []))

    frappe.get_roles = get_roles

    # -- db ---------------------------------------------------------------
    def get_value(doctype, name_or_filters, fieldname=None, as_dict=False,
                  for_update=False, **kwargs):
        if isinstance(name_or_filters, dict):
            rows = site.select(doctype, name_or_filters)
            row = rows[0] if rows else None
        else:
            row = site.get(doctype, name_or_filters)
        if row is None:
            return None
        if fieldname is None:
            return row.get("name")
        if isinstance(fieldname, (list, tuple)):
            if as_dict:
                # frappe._dict: usable both as an object and a mapping.
                return Row({field: row.get(field) for field in fieldname})
            return tuple(row.get(field) for field in fieldname)
        return row.get(fieldname)

    def exists(doctype, name=None):
        if isinstance(name, dict):
            rows = site.select(doctype, name)
            return rows[0]["name"] if rows else False
        if name is None:
            if isinstance(doctype, dict):
                return False
            return bool(site.table(doctype))
        return name if name in site.table(doctype) else False

    def count(doctype, filters=None):
        return len(site.select(doctype, filters))

    def get_all(doctype, filters=None, fields=None, limit_page_length=None,
                limit=None, order_by=None):
        rows = site.select(doctype, filters, order_by=order_by,
                           limit=limit or limit_page_length)
        if fields is None:
            return [deepcopy(row) for row in rows]
        return [{field: row.get(field) for field in fields} for row in rows]

    def sql(query, values=(), as_dict=False, **kwargs):
        text = _query(query)
        site.sql_log.append((text, tuple(values)))
        values = tuple(values)

        # Row locks on owned/native documents (exactly `where name=%s`).
        if (text.startswith("select name from `tab")
                and text.endswith("where name=%s for update")):
            doctype = text.split("`tab", 1)[1].split("`", 1)[0]
            return [(values[0],)] if values[0] in site.table(doctype) else []

        if "select count(*) from `tabStudent Group Student` where parent=%s" in text:
            return [(len([row for row in site.all("Student Group Student")
                          if row.get("parent") == values[0]]),)]

        if "from `tabProgram Enrollment`" in text:
            rows = [row for row in site.all("Program Enrollment")
                    if row.get("student") == values[0]
                    and row.get("program") == values[1]
                    and row.get("academic_year") == values[2]
                    and int(row.get("docstatus") or 0) == 1]
            if "academic_term=%s" in text:
                rows = [row for row in rows if row.get("academic_term") == values[3]]
            return [{"name": row["name"]} for row in rows] if as_dict else \
                [(row["name"],) for row in rows]

        if (text.startswith("select student from `tabStudent Group Student`")
                and " in (select" not in text):
            return [Row({"student": row.get("student"),
                         "student_name": row.get("student_name")})
                    for row in site.all("Student Group Student")
                    if row.get("parent") == values[0]]

        if "from `tabStudent Attendance` where student=%s and course_schedule=%s" in text:
            return [(row["name"],) for row in site.all("Student Attendance")
                    if row.get("student") == values[0]
                    and row.get("course_schedule") == values[1]
                    and int(row.get("docstatus") or 0) != 2]

        if "select student, active from `tabStudent Group Student` where parent=%s and student=%s for update" in text:
            rows = [row for row in site.all("Student Group Student")
                    if row.get("parent") == values[0] and row.get("student") == values[1]]
            return [Row({"student": row.get("student"),
                         "active": row.get("active")}) for row in rows]

        if "select active from `tabStudent Group Student` where parent=%s and student=%s" in text:
            rows = [row for row in site.all("Student Group Student")
                    if row.get("parent") == values[0] and row.get("student") == values[1]]
            return rows if as_dict else [(row.get("active"),) for row in rows]

        if "from `tabStudent Attendance` a" in text:
            # The transfer preservation sample: attendance in one class.
            rows = []
            for record in site.all("Student Attendance"):
                session = site.get("Course Schedule", record.get("course_schedule"))
                if record.get("student") != values[0]:
                    continue
                if int(record.get("docstatus") or 0) != 1:
                    continue
                if session and session.get("student_group") == values[1]:
                    rows.append({"name": record["name"]})
            return rows[: int(values[2])]

        if "from `tabCourse Schedule`" in text:
            if "where rs.student=%s and s.student_group!=%s" in text:
                # Transfer timetable collision: the learner's other classes.
                student, target_group, from_day = values
                groups = {row.get("parent") for row in site.all("Student Group Student")
                          if row.get("student") == student
                          and int(row.get("active") or 0) == 1}
                hits = []
                for session in site.all("Course Schedule"):
                    if session.get("student_group") not in groups:
                        continue
                    if session.get("student_group") == target_group:
                        continue
                    if str(session.get("schedule_date")) < str(from_day):
                        continue
                    if str(session.get("th_session_status") or "Scheduled") != "Scheduled":
                        continue
                    hits.append({
                        "name": session["name"],
                        "schedule_date": str(session.get("schedule_date")),
                        "from_time": str(session.get("from_time")),
                        "to_time": str(session.get("to_time")),
                        "student_group": session.get("student_group"),
                    })
                return hits
            if "join `tabStudent Group Student` rs on rs.parent = s.student_group" in text:
                # Student double-booking: another class's session on the same day.
                day, excluded, end, start, group_name, roster_group = values
                roster = {row.get("student") for row in site.all("Student Group Student")
                          if row.get("parent") == roster_group
                          and int(row.get("active") or 0) == 1}
                hits = []
                for session in site.all("Course Schedule"):
                    if str(session.get("schedule_date")) != str(day):
                        continue
                    if session["name"] == excluded:
                        continue
                    if session.get("student_group") == group_name:
                        continue
                    if str(session.get("th_session_status") or "Scheduled") != "Scheduled":
                        continue
                    if not _time_overlap(session.get("from_time"), session.get("to_time"),
                                         start, end):
                        continue
                    for member in site.all("Student Group Student"):
                        if member.get("parent") != session.get("student_group"):
                            continue
                        if int(member.get("active") or 0) != 1:
                            continue
                        if member.get("student") in roster:
                            hits.append({
                                "name": session["name"],
                                "student_group": session.get("student_group"),
                                "from_time": str(session.get("from_time")),
                                "to_time": str(session.get("to_time")),
                                "student": member.get("student"),
                            })
                return hits
            if "where schedule_date=%s for update" in text:
                rows = [session for session in site.all("Course Schedule")
                        if str(session.get("schedule_date")) == str(values[0])]
                return [dict(row) for row in rows]
            if "where student_group=%s and schedule_date=%s" in text:
                rows = [session for session in site.all("Course Schedule")
                        if session.get("student_group") == values[0]
                        and str(session.get("schedule_date")) == str(values[1])
                        and str(session.get("th_session_status") or "Scheduled") == "Scheduled"]
                return [(row["name"],) for row in rows]
            if "where student_group=%s and schedule_date>=%s" in text:
                group_name, from_day = values[0], values[1]
                limit = int(values[2]) if len(values) > 2 else 200
                rows = [session for session in site.all("Course Schedule")
                        if session.get("student_group") == group_name
                        and str(session.get("schedule_date")) >= str(from_day)
                        and str(session.get("th_session_status") or "Scheduled") == "Scheduled"]
                rows.sort(key=lambda row: str(row.get("schedule_date")))
                return [dict(row) for row in rows[:limit]]

        raise AssertionError(f"unstubbed SQL: {text[:160]}")

    frappe.db = SimpleNamespace(get_value=get_value, exists=exists, count=count,
                                get_all=get_all, sql=sql,
                                set_value=lambda doctype, name, values, **k: site.table(
                                    doctype)[name].update(values),
                                commit=lambda *a, **k: None,
                                rollback=lambda *a, **k: None)
    frappe.get_all = get_all
    frappe.db.get_all = get_all

    # -- documents --------------------------------------------------------
    def get_doc(arg, name=None, **kwargs):
        if isinstance(arg, dict):
            data = dict(arg)
            doctype = data.pop("doctype")
            explicit = data.pop("name", None)
            return Document(site, doctype, data=data, name=explicit)
        if isinstance(name, dict):
            rows = site.select(arg, name)
            if not rows:
                raise DoesNotExistError(str(name))
            stored = rows[0]
        else:
            stored = site.get(arg, name)
            if stored is None:
                raise DoesNotExistError(f"{arg} {name}")
        document = Document(site, arg, data=deepcopy(stored), name=stored["name"])
        if arg == "Student Group":
            document["students"] = [
                Row(deepcopy(row)) for row in site.all("Student Group Student")
                if row.get("parent") == stored["name"]]
        return document

    frappe.get_doc = get_doc
    frappe.new_doc = lambda doctype: Document(site, doctype)
    frappe.delete_doc = lambda doctype, name, **k: site.table(doctype).pop(name, None)
    frappe.exists = exists
    return frappe


def load_real(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class OperationsSite:
    """Owns the stub + the real modules the Mission 3 commands live in."""

    def __init__(self, today="2026-09-22"):
        self.site = Site(today=today)
        self._previous = dict(sys.modules)
        self.frappe = build_frappe(self.site)
        sys.modules["frappe"] = self.frappe
        sys.modules["frappe.utils"] = self.frappe.utils

        package = types.ModuleType("toefl_house")
        package.__path__ = [str(APP)]
        sys.modules["toefl_house"] = package

        self.policy = load_real("toefl_house.policy", APP / "policy.py")

        # Governance seams: the real (Frappe-free) foundation rules and a
        # scripted command executor with the real "work returns (result,
        # event)" contract.
        config = types.ModuleType("toefl_house.configuration")
        config.__path__ = [str(APP / "configuration")]
        sys.modules["toefl_house.configuration"] = config
        self.foundation = load_real("toefl_house.configuration.rules",
                                    APP / "configuration" / "rules.py")
        audit = types.ModuleType("toefl_house.configuration.audit")
        audit.latest_after_hash = lambda target: ""

        def execute(kind, request_key, payload, work):
            site = self.site
            site.commands.append((kind, request_key, payload))
            result, event = work(COURSE_OWNER)
            site.audit.append((kind, event))
            return result

        audit.execute = execute
        sys.modules["toefl_house.configuration.audit"] = audit
        config.audit = audit
        config.rules = self.foundation

        security = types.ModuleType("toefl_house.security")
        security.active_command_kind = lambda: None
        security.is_production = lambda: False
        security.require_operational = lambda: None
        security.record_synthetic_flag = lambda: 1
        security.teaching_command_active = lambda doctype: True
        sys.modules["toefl_house.security"] = security

        api = types.ModuleType("toefl_house.api")

        def _execute(kind, request_key, payload, work):
            self.site.commands.append((kind, request_key, payload))
            return work(self.site.user)[0]

        api._execute = _execute
        sys.modules["toefl_house.api"] = api

        academic = types.ModuleType("toefl_house.academic")
        academic.__path__ = [str(APP / "academic")]
        sys.modules["toefl_house.academic"] = academic
        rules = types.ModuleType("toefl_house.academic.rules")
        rules.parse_date = _parse_date
        rules.validate_code = lambda value: _require(
            value, "code", 140).upper()
        rules.validate_title = lambda value, what="Title": _require(value, what, 200)
        rules.validate_reason = lambda value: _optional(value, 500)
        rules.resolve_duration = lambda *a, **k: None
        sys.modules["toefl_house.academic.rules"] = rules
        academic.rules = rules

        # The attendance command patches the native Education roster helper;
        # provide the import target without installing the whole native app.
        for name in ("education", "education.education",
                     "education.education.doctype",
                     "education.education.doctype.student_attendance"):
            sys.modules.setdefault(name, types.ModuleType(name))
        native_attendance = types.ModuleType(
            "education.education.doctype.student_attendance.student_attendance")
        native_attendance.get_student_group_students = lambda *a, **k: []
        sys.modules["education.education.doctype.student_attendance.student_attendance"] = \
            native_attendance

        teaching = types.ModuleType("toefl_house.teaching")
        teaching.__path__ = [str(APP / "teaching")]
        sys.modules["toefl_house.teaching"] = teaching

        self.class_operations = load_real(
            "toefl_house.teaching.class_operations",
            APP / "teaching" / "class_operations.py")
        self.calendars = load_real("toefl_house.teaching.calendars",
                                   APP / "teaching" / "calendars.py")
        self.timetables = load_real("toefl_house.teaching.timetables",
                                    APP / "teaching" / "timetables.py")
        self.scheduling = load_real("toefl_house.teaching.scheduling",
                                    APP / "teaching" / "scheduling.py")
        self.capacity = load_real("toefl_house.teaching.capacity",
                                  APP / "teaching" / "capacity.py")
        self.suspensions = load_real("toefl_house.teaching.suspensions",
                                     APP / "teaching" / "suspensions.py")
        self.transfers = load_real("toefl_house.teaching.transfers",
                                   APP / "teaching" / "transfers.py")
        self.roster_policies = types.ModuleType("toefl_house.teaching.policies")
        self.roster_policies.governing_cutoff_date = lambda on_date=None: self.site.cutoff
        sys.modules["toefl_house.teaching.policies"] = self.roster_policies
        self.site.cutoff = "2026-10-15"
        self.teaching = load_real("toefl_house.teaching",
                                  APP / "teaching" / "__init__.py")
        for role in ("Teaching Scheduler", "Teaching Auditor", "Academic Manager",
                     "Course Owner", "Reception", "Finance Officer",
                     "Attendance Recorder", "General Manager"):
            self.site.add("Role", name=role, role_name=role)

    # -- lifecycle --------------------------------------------------------
    def close(self):
        sys.modules.clear()
        sys.modules.update(self._previous)

    def login(self, user):
        self.site.user = user
        self.frappe.session.user = user
        return user

    # -- conveniences -----------------------------------------------------
    def policy_terms(self, **overrides):
        terms = {
            "teaching_days": ["Mon", "Tue", "Wed", "Thu"],
            "default_session_minutes": 60,
            "min_session_minutes": 30,
            "max_session_minutes": 120,
            "max_sessions_per_day": 2,
            "timetable_horizon_days": 60,
            "allow_postponement": 1,
            "postpone_max_days": 14,
            "allow_session_cancellation": 1,
            "allow_replacement_sessions": 1,
            "replacement_approver_role": "Teaching Scheduler",
            "replacement_window_days": 21,
            "allow_class_suspension": 1,
            "class_suspension_max_days": 14,
            "allow_student_suspension": 1,
            "student_suspension_max_days": 14,
            "waiting_list_enabled": 1,
            "waiting_offer_valid_days": 7,
            "capacity_override_role": "Academic Manager",
            "capacity_override_max_seats": 5,
            "capacity_override_expiry_days": 14,
            "allow_transfers": 1,
            "allow_program_transfers": 1,
            "allow_branch_transfers": 1,
            "transfer_approver_role": "Academic Manager",
            "transfer_window_days": 60,
            "remove_member_allowed": 1,
            "direct_moves_allowed": 0,
        }
        terms.update(overrides)
        return terms

    def seed_policy(self, effective_from="2026-09-01", **overrides):
        """Create the single policy row and one governing version."""
        site = self.site
        site.add("TH Class Operations Policy", code="TH-CLASS-OPS",
                 title="Class operations", status="Active", description="")
        self.class_operations.set_class_operations_policy_version(
            "seed-policy-version-0001", "TH-CLASS-OPS", effective_from,
            "Configure class operations", self.policy_terms(**overrides))
        return self.class_operations.governing_operations()

    def append_policy(self, day="2026-09-02", **overrides):
        """Append a governing version effective on ``day`` (must be later)."""
        self.class_operations.set_class_operations_policy_version(
            f"policy-version-{day.replace('-', '')}", "TH-CLASS-OPS", day,
            f"Change class operations on {day}",
            self.policy_terms(**overrides))
        return self.class_operations.governing_operations()

    def seed_class(self, name="GRP-A", capacity=2, status="Active",
                   program="TH-PROG", year="2026-27", term="Fall",
                   branch=None, delivery_mode="On-site",
                   start="2026-09-01", end="2026-12-20", members=()):
        scenario = {
            "student_group_name": name, "program": program,
            "academic_year": year, "academic_term": term,
            "max_strength": capacity, "disabled": 0,
            "th_class_status": status, "th_delivery_mode": delivery_mode,
            "th_branch": branch, "th_class_start_date": start,
            "th_class_end_date": end,
        }
        self.site.add("Student Group", name=name, **scenario)
        for index, student in enumerate(members, 1):
            self.site.add("Student Group Student", parent=name,
                          student=student, active=1, idx=index)
        return name

    def seed_student(self, name="STU-1", student_name="Probe Learner",
                     enabled=1):
        self.site.add("Student", name=name, student_name=student_name,
                      enabled=enabled)
        return name

    def seed_enrollment(self, student, program="TH-PROG", year="2026-27",
                        term="Fall", docstatus=1):
        return self.site.add("Program Enrollment", student=student,
                             program=program, academic_year=year,
                             academic_term=term, docstatus=docstatus)

    def seed_room(self, name="ROOM-1", seating=30):
        return self.site.add("Room", name=name, room_name=name,
                             seating_capacity=seating)

    def seed_instructor(self, name="INS-1"):
        return self.site.add("Instructor", name=name, instructor_name=name)

    def seed_session(self, name=None, group="GRP-A", date="2026-09-21",
                     start="09:00:00", end="10:00:00", instructor=None,
                     room=None, course="ENG-101", status="Scheduled",
                     kind="Regular", replaces=None):
        fields = dict(student_group=group, schedule_date=date, from_time=start,
                      to_time=end, instructor=instructor, room=room,
                      course=course, th_session_status=status,
                      th_session_kind=kind, th_replaces=replaces)
        if name:
            return self.site.add("Course Schedule", name=name, **fields)
        return self.site.add("Course Schedule", **fields)

    def seed_calendar(self, code="CAL-2026", year="2026-27", branch=None,
                      days=()):
        site = self.site
        site.add("TH Academic Calendar", code=code, title=code, status="Active",
                 academic_year=year, branch=branch, description="",
                 days=[dict(day) for day in days])
        return code

    def seed_template(self, code="TT-1", program="TH-PROG", branch=None,
                      delivery_mode="On-site", slots=(), status="Active"):
        site = self.site
        site.add("TH Timetable Template", code=code, title=code,
                 status=status, program=program, branch=branch,
                 delivery_mode=delivery_mode, description="",
                 slots=[dict(slot) for slot in slots])
        return code

    def seed_waiting(self, group, student, status="Waiting",
                     priority=0, expires=None, requested_on="2026-09-20 09:00:00",
                     requested_by=ACTOR):
        return self.site.add(
            "TH Class Waiting List", student_group=group, student=student,
            status=status, priority=priority, requested_on=requested_on,
            requested_by=requested_by, offer_expires_on=expires,
            synthetic=1, policy_effective_from="2026-09-01")

    def seed_override(self, group, student, seats=1, status="Approved",
                      expires="2026-10-01", approved_by=APPROVER):
        return self.site.add(
            "TH Capacity Override", student_group=group, student=student,
            seats=seats, status=status, reason="approved extra seat",
            approved_by=approved_by, approved_on="2026-09-21 10:00:00",
            expires_on=expires, synthetic=1,
            policy_effective_from="2026-09-01")

    def roster(self, group):
        return [(row.get("student"), int(row.get("active") or 0))
                for row in self.site.all("Student Group Student")
                if row.get("parent") == group]


def _require(value, what, limit):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f"{what} is required (at most {limit} characters)")
    return value.strip()


def _optional(value, limit):
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise ValueError("Value is too long")
    return value.strip()


def _parse_date(value, what="date"):
    import datetime
    try:
        return datetime.date.fromisoformat(str(value or "")).isoformat()
    except ValueError as exc:
        raise ValueError(f"{what} must be a date (YYYY-MM-DD)") from exc

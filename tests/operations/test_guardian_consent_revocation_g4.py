"""Group 4 (C-04): guardian revocation must end the live authorization.

Regression for the newest-row trap: an Active consent followed by a newer
Pending row (fresh evidence lodged) previously made revoke mark only the
Pending row Revoked while the Active row survived — and _get_consent kept
returning the newest row. Now _get_consent selects the Active row, and
revoke revokes every non-Revoked row for (guardian, student).
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"


class _ValidationError(Exception):
    pass


class _PermissionError(Exception):
    pass


class _Doc(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value

    def save(self, ignore_permissions=False):
        self._store[self["name"]] = dict(self)
        return self


class RevocationTests(unittest.TestCase):
    def setUp(self):
        # Newest-first, as a creation-desc read returns them: Pending on
        # top, the still-Active authorization underneath.
        self.consents = [
            {"name": "CONSENT-PENDING", "guardian": "GUARD-1",
             "student": "STU-1", "status": "Pending",
             "consent_date": "2026-10-02", "expiry_date": "2027-10-02",
             "evidence_type": "Both", "revoked_at": None,
             "approved_by": "", "approved_on": ""},
            {"name": "CONSENT-ACTIVE", "guardian": "GUARD-1",
             "student": "STU-1", "status": "Active",
             "consent_date": "2026-10-01", "expiry_date": "2027-10-02",
             "evidence_type": "Both", "revoked_at": None,
             "approved_by": "staff@example.com",
             "approved_on": "2026-10-01 10:00:00"},
        ]
        self.store = {row["name"]: dict(row) for row in self.consents}
        fake = self

        def get_all(doctype, filters=None, fields=None, order_by=None,
                    limit_page_length=None, limit=None, limit_start=None,
                    **kwargs):
            if doctype != "TH Guardian Consent":
                return []
            rows = [dict(self.store[name]) for name in
                    ("CONSENT-PENDING", "CONSENT-ACTIVE")]
            for key, value in (filters or {}).items():
                if isinstance(value, tuple) and value[0] == "!=":
                    rows = [r for r in rows if r.get(key) != value[1]]
                else:
                    rows = [r for r in rows if r.get(key) == value]
            if fields:
                rows = [{f: r.get(f) for f in fields} for r in rows]
            start = int(limit_start or 0)
            page = limit_page_length if limit_page_length is not None else limit
            rows = rows[start:]
            return rows[:page] if page else rows

        def get_value(doctype, name_or_filters, fieldname=None, as_dict=False,
                      for_update=False, **kwargs):
            # Current-row read under the row lock (approve pattern).
            if doctype != "TH Guardian Consent":
                return None
            if isinstance(name_or_filters, dict):
                rows = get_all(doctype, filters=name_or_filters)
                row = rows[0] if rows else None
            else:
                row = self.store.get(name_or_filters)
            if row is None:
                return None
            if isinstance(fieldname, (list, tuple)):
                picked = {f: row.get(f) for f in fieldname}
                return _Doc(picked) if as_dict else tuple(
                    picked[f] for f in fieldname)
            if fieldname:
                return row.get(fieldname)
            return _Doc(dict(row)) if as_dict else row

        def get_doc(doctype, name=None, **kwargs):
            doc = _Doc(self.store[name])
            doc._store = fake.store
            return doc

        stub = types.ModuleType("frappe")
        stub.PermissionError = _PermissionError
        stub.ValidationError = _ValidationError
        stub.session = SimpleNamespace(user="guardian@example.com")
        stub.utils = SimpleNamespace(today=lambda: "2026-10-24",
                                     now_datetime=lambda: "2026-10-24 12:00:00")
        stub.db = SimpleNamespace(get_all=get_all, get_value=get_value)
        stub.get_doc = get_doc
        stub.whitelist = lambda **kwargs: (lambda func: func)
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(),
                                 sys.modules.update(previous)))
        sys.modules["frappe"] = stub
        sys.modules["frappe.utils"] = stub.utils
        package = types.ModuleType("toefl_house")
        package.__path__ = [str(APP)]
        sys.modules["toefl_house"] = package
        ops_pkg = types.ModuleType("toefl_house.operations")
        ops_pkg.__path__ = [str(APP / "operations")]
        sys.modules["toefl_house.operations"] = ops_pkg
        policy = types.ModuleType("toefl_house.operations.portal_policy")
        policy.is_portal_enabled = lambda name: True
        sys.modules["toefl_house.operations.portal_policy"] = policy
        dates = types.ModuleType("toefl_house.operations.portal_dates")
        dates.with_solar_date = lambda row, *a, **k: row
        sys.modules["toefl_house.operations.portal_dates"] = dates
        spec = importlib.util.spec_from_file_location(
            "toefl_house.operations.guardian_portal",
            APP / "operations/guardian_portal.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["toefl_house.operations.guardian_portal"] = module
        spec.loader.exec_module(module)
        module._require_portal_enabled = lambda: None
        module._get_guardian_for_user = lambda user: "GUARD-1"
        module._get_verified_children = lambda guardian: ["STU-1"]
        self.portal = module

    def test_get_consent_selects_the_active_row_not_the_newest(self):
        row = self.portal._get_consent("GUARD-1", "STU-1")
        self.assertEqual(row["name"], "CONSENT-ACTIVE")
        self.assertTrue(
            self.portal._is_consent_valid("GUARD-1", "STU-1", {}))

    def test_revoke_revokes_every_non_revoked_row(self):
        result = self.portal.revoke_consent(student="STU-1",
                                            reason="No longer need")
        self.assertEqual(result["status"], "Revoked")
        self.assertEqual(self.store["CONSENT-ACTIVE"]["status"], "Revoked")
        self.assertEqual(self.store["CONSENT-PENDING"]["status"], "Revoked")
        self.assertFalse(
            self.portal._is_consent_valid("GUARD-1", "STU-1", {}))

    def test_revoke_with_nothing_live_is_refused(self):
        for row in self.store.values():
            row["status"] = "Revoked"
        with self.assertRaises(_ValidationError):
            self.portal.revoke_consent(student="STU-1")


if __name__ == "__main__":
    unittest.main()

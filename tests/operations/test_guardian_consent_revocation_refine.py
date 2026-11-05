"""Refinement of Group 4 (C-04): guardian revocation must be total.

The prior fix revoked every non-Revoked row it could SEE — but it only
ever saw the first 50 rows (`limit_page_length=50` in both `_get_consent`
and `revoke_consent`), and it never re-read after revoking. These tests
reproduce what that leaves behind:

* an Active consent older than 50 newer rows is invisible to
  `_get_consent` and survives `revoke_consent`;
* a consent created (lodged + approved) while a revocation is running
  survives it, because revocation never re-checks;
* two concurrent revocations still leave the 51st row alive.

The stub honours `limit_start` (real Frappe `get_all` does) and models
`get_value(..., for_update=True)` as a current-row read, so pagination
and the per-row lock re-read are exercised, not assumed.
"""
import importlib.util
import sys
import threading
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
        hook = self._hooks.get("on_save") if hasattr(self, "_hooks") else None
        if hook is not None:
            hook(self)
        with self._lock:
            self._store[self["name"]] = dict(self)
        return self


def _row(name, status, creation, approved=True):
    return {
        "name": name, "guardian": "GUARD-1", "student": "STU-1",
        "status": status, "consent_date": "2026-10-01",
        "expiry_date": "2027-10-02", "evidence_type": "Both",
        "revoked_at": None, "revoked_by": None, "revocation_reason": None,
        "approved_by": "staff@example.com" if approved else "",
        "approved_on": "2026-10-01 10:00:00" if approved else "",
        "creation": creation,
    }


class RevocationRefinementTests(unittest.TestCase):
    def setUp(self):
        self.store = {}
        self.lock = threading.RLock()
        self.hooks = {}  # e.g. {"on_save": callable}
        self.barrier = None
        self._barrier_seen = set()
        fake = self

        def get_all(doctype, filters=None, fields=None, order_by=None,
                    limit_page_length=None, limit=None, limit_start=None,
                    **kwargs):
            if doctype != "TH Guardian Consent":
                return []
            with self.lock:
                rows = [dict(r) for r in self.store.values()]
            for key, value in (filters or {}).items():
                if isinstance(value, tuple) and value[0] == "!=":
                    rows = [r for r in rows if r.get(key) != value[1]]
                else:
                    rows = [r for r in rows if r.get(key) == value]
            if order_by and "creation desc" in order_by:
                rows.sort(key=lambda r: r.get("creation") or 0, reverse=True)
            elif order_by and "creation asc" in order_by:
                rows.sort(key=lambda r: r.get("creation") or 0)
            start = int(limit_start or 0)
            page = limit_page_length if limit_page_length is not None else limit
            rows = rows[start:]
            if page:
                rows = rows[: int(page)]
            if fields:
                rows = [{f: r.get(f) for f in fields} for r in rows]
            if self.barrier is not None:
                # Rendezvous AFTER the page is read, not before it: both
                # revoking threads must hold their first-page snapshot
                # before either one starts mutating, or the faster thread
                # can finish the whole revocation before the slower
                # thread's initial read sees a single live row. Worker
                # threads only — the main thread's later assertions must
                # never wait here.
                tid = threading.get_ident()
                if (threading.current_thread() is not threading.main_thread()
                        and tid not in self._barrier_seen):
                    self._barrier_seen.add(tid)
                    self.barrier.wait(timeout=10)
            return rows

        def get_value(doctype, name_or_filters, fieldname=None, as_dict=False,
                      for_update=False, **kwargs):
            # Current-row read under the row lock (approve pattern).
            if doctype != "TH Guardian Consent":
                return None
            if isinstance(name_or_filters, dict):
                rows = get_all(doctype, filters=name_or_filters)
                row = rows[0] if rows else None
            else:
                with self.lock:
                    row = self.store.get(name_or_filters)
                    row = dict(row) if row is not None else None
            if row is None:
                return None
            if isinstance(fieldname, (list, tuple)):
                picked = {f: row.get(f) for f in fieldname}
                return _Doc(picked) if as_dict else tuple(
                    picked[f] for f in fieldname)
            if fieldname:
                return row.get(fieldname)
            return _Doc(row) if as_dict else row

        def get_doc(doctype, name=None, **kwargs):
            with self.lock:
                stored = self.store[name]
                data = dict(stored)
            doc = _Doc(data)
            doc._store = fake.store
            doc._lock = fake.lock
            doc._hooks = fake.hooks
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

    # -- helpers ---------------------------------------------------------
    def _seed_many(self, count=51, active_name="CONSENT-ACTIVE"):
        """50 newer Pending rows on top of one older Active row."""
        with self.lock:
            self.store.clear()
            self.store[active_name] = _row(active_name, "Active", 1)
            for i in range(2, count + 1):
                name = f"CONSENT-P{i:03d}"
                self.store[name] = _row(name, "Pending", i, approved=False)

    def _live_statuses(self):
        with self.lock:
            return sorted(r["status"] for r in self.store.values()
                          if r["status"] != "Revoked")

    # -- the 50-row cap ---------------------------------------------------
    def test_get_consent_finds_active_row_beyond_first_50(self):
        self._seed_many(51)
        row = self.portal._get_consent("GUARD-1", "STU-1")
        self.assertEqual(row["name"], "CONSENT-ACTIVE")
        self.assertTrue(
            self.portal._is_consent_valid("GUARD-1", "STU-1", {}))

    def test_revoke_revokes_all_51_rows_not_just_the_first_50(self):
        self._seed_many(51)
        result = self.portal.revoke_consent(student="STU-1",
                                            reason="No longer need")
        self.assertEqual(result["status"], "Revoked")
        self.assertEqual(self._live_statuses(), [])
        self.assertEqual(self.store["CONSENT-ACTIVE"]["status"], "Revoked")
        self.assertFalse(
            self.portal._is_consent_valid("GUARD-1", "STU-1", {}))

    # -- mid-revocation changes -------------------------------------------
    def test_revoke_catches_consent_created_mid_revocation(self):
        with self.lock:
            self.store.clear()
            self.store["CONSENT-ACTIVE"] = _row("CONSENT-ACTIVE", "Active", 1)
            self.store["CONSENT-PENDING"] = _row(
                "CONSENT-PENDING", "Pending", 2, approved=False)
        injected = []

        def inject_once(doc):
            if injected:
                return
            injected.append(True)
            with self.lock:
                # Another request lodges evidence and staff approve it
                # while this revocation is still running.
                self.store["CONSENT-INJECTED"] = _row(
                    "CONSENT-INJECTED", "Active", 999)

        self.hooks["on_save"] = inject_once
        result = self.portal.revoke_consent(student="STU-1")
        self.assertEqual(result["status"], "Revoked")
        self.assertEqual(self.store["CONSENT-INJECTED"]["status"], "Revoked")
        self.assertEqual(self._live_statuses(), [])
        self.assertFalse(
            self.portal._is_consent_valid("GUARD-1", "STU-1", {}))

    def test_revoke_refuses_when_new_consents_keep_appearing(self):
        with self.lock:
            self.store.clear()
            self.store["CONSENT-ACTIVE"] = _row("CONSENT-ACTIVE", "Active", 1)
        counter = [0]

        def inject_always(doc):
            counter[0] += 1
            with self.lock:
                self.store[f"CONSENT-RACE-{counter[0]:03d}"] = _row(
                    f"CONSENT-RACE-{counter[0]:03d}", "Active",
                    1000 + counter[0])

        self.hooks["on_save"] = inject_always
        with self.assertRaises(_ValidationError) as ctx:
            self.portal.revoke_consent(student="STU-1")
        self.assertIn("Revocation incomplete", str(ctx.exception))

    # -- concurrent revocations -------------------------------------------
    def test_two_concurrent_revocations_leave_nothing_valid(self):
        self._seed_many(51)
        self.barrier = threading.Barrier(2)
        errors = []

        def run():
            try:
                self.portal.revoke_consent(student="STU-1")
            except Exception as exc:  # noqa: BLE001 - collected, asserted below
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        self.barrier = None
        self.assertFalse(any(t.is_alive() for t in threads),
                         "revocation threads did not finish")
        self.assertEqual(errors, [])
        self.assertEqual(self._live_statuses(), [])
        self.assertFalse(
            self.portal._is_consent_valid("GUARD-1", "STU-1", {}))

    # -- behaviour that must not change ------------------------------------
    def test_revoke_with_nothing_live_is_still_refused(self):
        with self.lock:
            self.store.clear()
            self.store["CONSENT-OLD"] = _row("CONSENT-OLD", "Revoked", 1)
        with self.assertRaises(_ValidationError):
            self.portal.revoke_consent(student="STU-1")


if __name__ == "__main__":
    unittest.main()

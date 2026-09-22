"""S3 regression: install skill seeding fails loudly (BUG-INST-01).

Only the concurrent-create DuplicateEntryError is swallowed; any other
seed failure must propagate so the migrate fails instead of reporting
success with missing masters.
"""
import importlib.util
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"


class _DuplicateEntryError(Exception):
    pass


class _ValidationError(Exception):
    pass


class InstallSeedTests(unittest.TestCase):
    def _load(self, insert_effect):
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
        calls = {"rollback": 0}

        class Doc:
            flags = SimpleNamespace()

            def insert(self, ignore_permissions=False):
                if isinstance(insert_effect, type) and issubclass(insert_effect, Exception):
                    raise insert_effect("seed failure")
                return self

        stub = types.ModuleType("frappe")
        stub.DuplicateEntryError = _DuplicateEntryError
        stub.ValidationError = _ValidationError
        stub.utils = SimpleNamespace(now_datetime=lambda: datetime(2026, 9, 22, 12, 0, 0))
        stub.get_doc = lambda payload: Doc()
        stub.db = SimpleNamespace(exists=lambda doctype, name: False,
                                  rollback=lambda: calls.__setitem__("rollback", calls["rollback"] + 1))
        sys.modules["frappe"] = stub
        spec = importlib.util.spec_from_file_location("toefl_house_install_seed", APP / "install.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["toefl_house_install_seed"] = module
        spec.loader.exec_module(module)
        return module, calls

    def test_concurrent_create_is_swallowed(self):
        module, calls = self._load(_DuplicateEntryError)
        module._seed_skills()
        self.assertEqual(calls["rollback"], 3)

    def test_real_seed_failure_propagates(self):
        module, calls = self._load(_ValidationError)
        with self.assertRaises(_ValidationError):
            module._seed_skills()

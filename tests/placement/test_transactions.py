"""Retry unit controls only; SQL/concurrency still require hosted native tests."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class Deadlock(Exception): pass
class Timeout(Exception): pass


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.db = SimpleNamespace(db_type='mariadb', transaction_writes=0,
                                  _disable_transaction_control=False,
                                  sql=Mock(return_value=[(50,)]), rollback=Mock())
        native = SimpleNamespace(db=self.db, QueryDeadlockError=Deadlock,
                                 QueryTimeoutError=Timeout, ValidationError=ValueError)
        path = Path(__file__).resolve().parents[2] / 'apps/toefl_house/toefl_house/transactions.py'
        spec = importlib.util.spec_from_file_location('placement_transaction_unit', path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, frappe=native):spec.loader.exec_module(self.module)
        self.sleep = patch.object(self.module.time, 'sleep');self.sleep.start();self.addCleanup(self.sleep.stop)

    def test_success_does_not_commit_or_rollback(self):
        work=Mock(return_value={'ok':1})
        self.assertEqual(self.module.run_with_retry(work), {'ok':1})
        self.db.rollback.assert_not_called();work.assert_called_once()
        self.db.sql.assert_any_call('SET SESSION innodb_lock_wait_timeout = %s', (5,))
        self.assertEqual(self.db.sql.call_args.args, ('SET SESSION innodb_lock_wait_timeout = %s', (50,)))

    def test_whole_command_retried_after_each_transient(self):
        work=Mock(side_effect=[Deadlock(), Timeout(), 'same-operation-result'])
        self.assertEqual(self.module.run_with_retry(work), 'same-operation-result')
        self.assertEqual(work.call_count,3);self.assertEqual(self.db.rollback.call_count,2)

    def test_three_retries_then_fail_closed(self):
        work=Mock(side_effect=Deadlock())
        with self.assertRaises(Deadlock):self.module.run_with_retry(work)
        self.assertEqual(work.call_count,4);self.assertEqual(self.db.rollback.call_count,4)
        self.assertEqual(self.db.sql.call_args.args[-1], (50,))

    def test_never_replay_or_rollback_unrelated_prior_writes(self):
        self.db.transaction_writes=1;work=Mock(side_effect=Deadlock())
        with self.assertRaises(Deadlock):self.module.run_with_retry(work)
        work.assert_called_once();self.db.rollback.assert_not_called()

    def test_disabled_transaction_control_is_not_retried(self):
        self.db._disable_transaction_control=True;work=Mock(side_effect=Timeout())
        with self.assertRaises(Timeout):self.module.run_with_retry(work)
        work.assert_called_once();self.db.rollback.assert_not_called()

    def test_nontransient_error_is_not_retried(self):
        work=Mock(side_effect=ValueError('conflict'))
        with self.assertRaises(ValueError):self.module.run_with_retry(work)
        work.assert_called_once();self.db.rollback.assert_not_called()

    def test_other_database_fails_closed(self):
        self.db.db_type='postgres';work=Mock()
        with self.assertRaises(ValueError):self.module.run_with_retry(work)
        work.assert_not_called();self.db.sql.assert_not_called()

"""Execute pinned ERPNext accounting methods, without a site or database.

Only framework metadata/document storage are doubles. Allocation conversion,
party/bank GL generation, negative normalization and balance validation are
verbatim pinned source; see fixtures/erpnext-4048fb70/manifest.json.
"""
import hashlib
import json
from pathlib import Path
import sys
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.native.native_checks import seed_native_party_types


FIXTURES = Path(__file__).parent / 'fixtures' / 'erpnext-4048fb70'
MANIFEST = json.loads((FIXTURES / 'manifest.json').read_text())


class Record(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__

    def copy(self):
        return Record(self)


def flt(value, precision=None):
    value = float(value or 0)
    return round(value, precision) if precision is not None else value


class NativeValidationError(Exception):
    pass


def throw(message):
    raise NativeValidationError(message)


def load_source(name, namespace):
    data = (FIXTURES / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != MANIFEST['sources'][name]['excerpt_sha256']:
        raise AssertionError(f'Pinned source changed: {name}')
    exec(compile(textwrap.dedent(data.decode()), str(FIXTURES / name), 'exec'), namespace)


class NativeRefundAccountingTests(unittest.TestCase):
    def setUp(self):
        self.records = {}
        self.inserted = []

        def get_value(doctype, name, field):
            self.assertEqual((doctype, field), ('Party Type', 'account_type'))
            return self.records.get(name, {}).get(field)

        def get_doc(record):
            def insert():
                self.assertEqual(record['doctype'], 'Party Type')
                self.assertNotIn(record['party_type'], self.records)
                self.records[record['party_type']] = dict(record)
                self.inserted.append(dict(record))
            return SimpleNamespace(insert=insert)

        self.frappe = SimpleNamespace(
            db=SimpleNamespace(
                exists=lambda doctype, name: doctype == 'Party Type' and name in self.records,
                get_value=get_value),
            get_doc=get_doc, throw=throw,
            get_meta=lambda doctype: SimpleNamespace(get_field=lambda field: None),
            get_cached_value=lambda doctype, name, field: 'AFN',
        )
        self.ns = {
            'frappe': self.frappe, 'flt': flt, '_': lambda value: value,
            'get_advance_payment_doctypes': lambda: ('Sales Order', 'Purchase Order'),
            'get_root_of': lambda doctype: None,
            'get_field_precision': lambda *args, **kwargs: 2,
        }
        for filename in MANIFEST['sources']:
            load_source(filename, self.ns)

    def seed(self):
        module = SimpleNamespace(get_preset_records=self.ns['get_preset_records'])
        with patch.dict(sys.modules, {
            'erpnext.setup.setup_wizard.operations.install_fixtures': module,
        }):
            seed_native_party_types(self.frappe)

    def payment(self, party_type='Customer', payment_type='Pay', allocations=(-600,), amount=600):
        pay = payment_type == 'Pay'
        party_account = 'Debtors - TH' if party_type == 'Customer' else 'Creditors - TH'
        doc = Record(
            doctype='Payment Entry', name='SYN-REFUND', company='TOEFL House',
            payment_type=payment_type, party_type=party_type, party='SYN-PARTY',
            party_account=party_account, party_account_currency='AFN',
            paid_from='Cash - TH' if pay else party_account,
            paid_to=party_account if pay else 'Cash - TH',
            paid_from_account_currency='AFN', paid_to_account_currency='AFN',
            paid_amount=amount, received_amount=amount,
            base_paid_amount=amount, base_received_amount=amount,
            source_exchange_rate=1, target_exchange_rate=1,
            transaction_currency='AFN', transaction_exchange_rate=1,
            cost_center='Main - TH', unallocated_amount=0,
            book_advance_payments_in_separate_party_account=0,
            references=[Record(
                reference_doctype='Sales Invoice' if party_type == 'Customer' else 'Purchase Invoice',
                reference_name=f'SYN-INVOICE-{i}', allocated_amount=value,
                outstanding_amount=value, exchange_rate=1,
            ) for i, value in enumerate(allocations)],
        )
        # Supply only GL metadata/default fields; no debit/credit arithmetic.
        def get_gl_dict(args, item=None):
            row = Record(company=doc.company, voucher_type=doc.doctype, voucher_no=doc.name,
                         debit=0, credit=0, debit_in_account_currency=0, credit_in_account_currency=0,
                         debit_in_transaction_currency=0, credit_in_transaction_currency=0)
            row.update(args)
            return row
        doc.get_gl_dict = get_gl_dict
        doc.precision = lambda field: 2
        doc.calculate_base_allocated_amount_for_reference = lambda row: self.ns[
            'calculate_base_allocated_amount_for_reference'](doc, row)
        return doc

    def ledger(self, doc):
        entries = []
        self.ns['add_party_gl_entries'](doc, entries)
        self.ns['add_bank_gl_entries'](doc, entries)
        return self.ns['toggle_debit_credit_if_negative'](entries)

    def test_missing_wizard_fixture_reproduces_exact_minus_1200_failure(self):
        entries = self.ledger(self.payment())
        self.assertEqual([(row.account, row.debit, row.credit) for row in entries],
                         [('Debtors - TH', 0, 600), ('Cash - TH', 0, 600)])
        self.assertEqual(self.ns['get_debit_credit_difference'](entries, 2), (-1200, -1200))
        with self.assertRaisesRegex(NativeValidationError, r'Difference is -1200'):
            self.ns['process_debit_credit_difference'](entries)

    def test_wizard_fixture_fixes_full_and_partial_customer_refunds(self):
        self.seed()
        for amount in (600, 250):
            with self.subTest(amount=amount):
                doc = self.payment(allocations=(-amount,), amount=amount)
                entries = self.ledger(doc)
                self.ns['process_debit_credit_difference'](entries)
                for suffix in ('', '_in_account_currency', '_in_transaction_currency'):
                    self.assertEqual([(row['debit' + suffix], row['credit' + suffix]) for row in entries],
                                     [(amount, 0), (0, amount)])
                party = entries[0]
                self.assertEqual((party.party_type, party.party, party.against_voucher_type, party.against_voucher),
                                 ('Customer', 'SYN-PARTY', 'Sales Invoice', 'SYN-INVOICE-0'))
                self.assertEqual(doc.references[0].allocated_amount, -amount)
                self.assertEqual(doc.references[0].outstanding_amount + party.debit - party.credit, 0)

    def test_native_balance_validation_still_rejects_wrong_cash_amount(self):
        self.seed()
        entries = self.ledger(self.payment(amount=599))
        with self.assertRaisesRegex(NativeValidationError, r'Difference is 1.0'):
            self.ns['process_debit_credit_difference'](entries)

    def test_receipts_supplier_payments_and_supplier_refunds_balance(self):
        self.seed()
        for party, kind, allocations in (
            ('Customer', 'Receive', (600,)),
            ('Customer', 'Receive', (1000, -400)),
            ('Supplier', 'Pay', (600,)),
            ('Supplier', 'Receive', (-600,)),
        ):
            with self.subTest(party=party, kind=kind, allocations=allocations):
                entries = self.ledger(self.payment(party, kind, allocations))
                self.ns['process_debit_credit_difference'](entries)
                self.assertEqual(self.ns['get_debit_credit_difference'](entries, 2), (0, 0))

    def test_only_native_party_types_are_seeded_and_replay_does_not_write(self):
        self.seed()
        self.assertEqual({name: row['account_type'] for name, row in self.records.items()},
                         dict(Customer='Receivable', Supplier='Payable', Employee='Payable', Shareholder='Payable'))
        self.seed()
        self.assertEqual(len(self.inserted), 4)

    def test_existing_incorrect_mapping_fails_without_overwriting_it(self):
        self.records['Customer'] = dict(doctype='Party Type', party_type='Customer', account_type='Payable')
        with self.assertRaisesRegex(ValueError, 'Customer: expected Receivable, got Payable'):
            self.seed()
        self.assertEqual(self.records['Customer']['account_type'], 'Payable')
        self.assertEqual(self.inserted, [])


if __name__ == '__main__':
    unittest.main()

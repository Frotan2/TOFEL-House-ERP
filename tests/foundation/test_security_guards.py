"""Unit policy checks; real permission proof remains the hosted probes."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import patch


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.settings = True
        self.shared = False
        self.students = [Obj(name='student-a', customer='customer-a')]
        self.rules = {'Student': [Obj(for_value='student-a', apply_to_all_doctypes=1)],
                      'Customer': [Obj(for_value='customer-a', apply_to_all_doctypes=1)]}
        def get_all(doctype, **kwargs):
            return self.students if doctype=='Student' else self.rules[kwargs['filters']['allow']]
        self.frappe = Obj(session=Obj(user='student@example.test'), get_roles=lambda user:['Student'],
                          PermissionError=PermissionError, conf={'disable_website_cache':1},
                          get_all=get_all, db=Obj(get_single_value=lambda *args:self.settings, exists=lambda *args:self.shared))
        path=Path(__file__).resolve().parents[2]/'apps/foundation_security/foundation_security/guards.py'
        spec=importlib.util.spec_from_file_location('guard_under_test',path)
        self.guard=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe':self.frappe}): spec.loader.exec_module(self.guard)

    def test_exact_native_scope_allowed(self):
        self.guard.validate_student_scope()

    def test_missing_rules_denied(self):
        self.rules['Student']=[]
        with self.assertRaises(PermissionError): self.guard.validate_student_scope()

    def test_broadened_scope_denied(self):
        self.rules['Student'].append(Obj(for_value='student-b', apply_to_all_doctypes=1))
        with self.assertRaises(PermissionError): self.guard.validate_student_scope()

    def test_wrong_customer_denied(self):
        self.rules['Customer'][0].for_value='customer-b'
        with self.assertRaises(PermissionError): self.guard.validate_student_scope()

    def test_ambiguous_student_link_denied(self):
        self.students.append(Obj(name='student-b', customer='customer-b'))
        with self.assertRaises(PermissionError): self.guard.validate_student_scope()

    def test_unsafe_settings_denied(self):
        self.settings=False
        with self.assertRaises(PermissionError): self.guard.validate_student_scope()

    def test_page_cache_enabled_denied(self):
        self.frappe.conf={}
        with self.assertRaises(PermissionError): self.guard.validate_student_scope()

    def test_existing_share_denied(self):
        self.shared=True
        with self.assertRaises(PermissionError): self.guard.validate_student_scope()

    def test_guest_and_trusted_admin_are_not_student_scoped(self):
        self.students=[]
        for user in ('Guest','Administrator'):
            self.frappe.session.user=user
            self.guard.validate_student_scope()

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
        self.shares = []
        self.students = [Obj(name='student-a', customer='customer-a')]
        self.rules = {'Student': [Obj(for_value='student-a', apply_to_all_doctypes=1)],
                      'Customer': [Obj(for_value='customer-a', apply_to_all_doctypes=1)]}
        def get_all(doctype, **kwargs):
            if doctype=='DocShare': return self.shares
            return self.students if doctype=='Student' else self.rules[kwargs['filters']['allow']]
        self.frappe = Obj(session=Obj(user='student@example.test'), get_roles=lambda user:['Student'],
                          PermissionError=PermissionError, conf={'disable_website_cache':1},
                          get_all=get_all, db=Obj(get_single_value=lambda *args:self.settings, exists=lambda *args:False))
        path=Path(__file__).resolve().parents[2]/'apps/foundation_security/foundation_security/guards.py'
        spec=importlib.util.spec_from_file_location('guard_under_test',path)
        self.guard=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe':self.frappe}): spec.loader.exec_module(self.guard)

    def test_app_contains_bench_discovery_files(self):
        root=Path(__file__).resolve().parents[2]/'apps/foundation_security/foundation_security'
        for name in ('hooks.py','modules.txt','patches.txt'):
            self.assertTrue((root/name).is_file(), name)

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
        self.shares=[Obj(share_doctype='Student', share_name='student-b', everyone=0)]
        with self.assertRaises(PermissionError): self.guard.validate_student_scope()

    def test_guest_and_trusted_admin_are_not_student_scoped(self):
        self.students=[]
        for user in ('Guest','Administrator'):
            self.frappe.session.user=user
            self.guard.validate_student_scope()

    def test_native_user_self_share_allowed(self):
        self.shares=[Obj(share_doctype='User', share_name='student@example.test', everyone=0)]
        self.guard.validate_student_scope()

    def test_global_share_denied(self):
        self.shares=[Obj(share_doctype='User', share_name='student@example.test', everyone=1)]
        with self.assertRaises(PermissionError): self.guard.validate_student_scope()

    def configure_csrf(self, method, path):
        self.frappe.session.sid='synthetic-session'
        self.frappe.session.data=Obj(csrf_token=None)
        self.frappe.request=Obj(method=method, path=path)
        self.frappe.form_dict={}
        self.frappe.CSRFTokenError=ValueError
        def mint(): self.frappe.session.data.csrf_token='synthetic-token'
        return patch.dict(sys.modules, {'frappe':self.frappe, 'frappe.sessions':Obj(get_csrf_token=mint)})

    def test_login_token_initialized_only_after_native_request_validation(self):
        with self.configure_csrf('POST','/api/method/login'):
            self.guard.on_session_creation()
            self.assertIsNone(self.frappe.session.data.csrf_token)
            self.guard.validate_request()
            self.assertEqual(self.frappe.session.data.csrf_token,'synthetic-token')

    def test_legacy_unsafe_request_without_token_denied(self):
        with self.configure_csrf('POST','/api/method/frappe.client.set_value'):
            with self.assertRaises(ValueError): self.guard.validate_request()

    def test_safe_page_initializes_legacy_session_token(self):
        with self.configure_csrf('GET','/edu-portal'):
            self.guard.validate_request()
            self.assertEqual(self.frappe.session.data.csrf_token,'synthetic-token')

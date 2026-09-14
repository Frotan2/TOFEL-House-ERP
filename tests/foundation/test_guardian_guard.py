import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as O
import unittest
from unittest.mock import patch

class GuardianGuardTests(unittest.TestCase):
    def setUp(self):
        self.guardians=[O(name='guardian')];self.links=['a','b'];self.students=[O(name='a',customer='ca'),O(name='b',customer='cb')]
        self.rules={k:[O(for_value=v,apply_to_all_doctypes=1) for v in values] for k,values in {'Guardian':['guardian'],'Student':['a','b'],'Customer':['ca','cb']}.items()}
        self.shares=[]
        def all_(dt,**kw):
            return {'Guardian':self.guardians,'Student Guardian':self.links,'Student':self.students,'DocShare':self.shares}.get(dt) if dt!='User Permission' else self.rules[kw['filters']['allow']]
        self.f=O(session=O(user='guardian-user'),get_roles=lambda u:['Guardian'],get_all=all_,PermissionError=PermissionError,db=O(get_single_value=lambda *a:1),conf={'disable_website_cache':1})
        path=Path(__file__).resolve().parents[2]/'apps/foundation_security/foundation_security/guards.py'
        spec=importlib.util.spec_from_file_location('guardian_test',path);self.g=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':self.f}):spec.loader.exec_module(self.g)
    def test_multiple_canonical_children_allowed(self):self.g.validate_student_scope()
    def test_missing_child_scope_denied(self):
        self.rules['Student'].pop()
        with self.assertRaises(PermissionError):self.g.validate_student_scope()
    def test_expanded_child_scope_denied(self):
        self.rules['Student'].append(O(for_value='other',apply_to_all_doctypes=1))
        with self.assertRaises(PermissionError):self.g.validate_guardian_scope()
    def test_relinked_child_denied(self):
        self.links=['b'];self.students=self.students[1:]
        with self.assertRaises(PermissionError):self.g.validate_guardian_scope()
    def test_ambiguous_identity_denied(self):
        self.guardians.append(O(name='second'))
        with self.assertRaises(PermissionError):self.g.validate_guardian_scope()
    def test_no_children_denied(self):
        self.links=[]
        with self.assertRaises(PermissionError):self.g.validate_guardian_scope()
    def test_other_share_denied(self):
        self.shares=[O(share_doctype='Student',share_name='other',everyone=0)]
        with self.assertRaises(PermissionError):self.g.validate_guardian_scope()
    def test_native_self_user_share_allowed(self):
        self.shares=[O(share_doctype='User',share_name='guardian-user',everyone=0)]
        self.g.validate_guardian_scope()
    def test_scoped_rule_must_apply_to_all_doctypes(self):
        self.rules['Guardian'][0].apply_to_all_doctypes=0
        with self.assertRaises(PermissionError):self.g.validate_guardian_scope()

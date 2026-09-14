import importlib.util
from pathlib import Path
from types import SimpleNamespace as O
import sys
import unittest
from unittest.mock import patch

class FileParentGuardTests(unittest.TestCase):
    def setUp(self):
        self.allowed=False;self.calls=[]
        def permission(*a,**kw):self.calls.append(kw);return self.allowed
        f=O(session=O(user='guardian'),get_roles=lambda u:['Guardian'],has_permission=permission)
        path=Path(__file__).resolve().parents[2]/'apps/foundation_security/foundation_security/files.py'
        spec=importlib.util.spec_from_file_location('file_guard_test',path);self.g=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':f}):spec.loader.exec_module(self.g)
        self.doc=O(is_private=1,attached_to_doctype='Student',attached_to_name='other',owner='guardian')
    def test_owner_cannot_bypass_parent(self):self.assertFalse(self.g.parent_permission(self.doc,'read'))
    def test_allowed_parent_only_defers_to_native_acl(self):
        self.allowed=True;self.assertTrue(self.g.parent_permission(self.doc,'read'));self.assertEqual(self.calls[0]['ptype'],'read')
    def test_file_write_requires_parent_write(self):
        self.g.parent_permission(self.doc,'write');self.assertEqual(self.calls[0]['ptype'],'write')
    def test_cycles_fail_closed(self):
        self.doc.attached_to_doctype='File';self.assertFalse(self.g.parent_permission(self.doc,'read'))
    def test_public_files_still_use_native_policy(self):
        self.doc.is_private=0;self.assertTrue(self.g.parent_permission(self.doc,'read'));self.assertFalse(self.calls)

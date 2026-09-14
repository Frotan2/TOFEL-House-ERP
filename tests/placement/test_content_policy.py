"""Pure local unit checks only; these do NOT qualify native Frappe behavior."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import can_read, canonical, digest, request_digest, validate_content, validate_family, validate_request_key


def content():
    return dict(skill="Grammar", difficulty="Entry", question_type="Single Choice", prompt="SYNTHETIC: choose a test option.",
                options=[{"id":"a", "text":"Test A"}, {"id":"b", "text":"Test B"}], answer="a")


class PolicyTests(unittest.TestCase):
    def test_receipt_fingerprint_is_keyed(self):
        self.assertNotEqual(request_digest(content(), "test-key-a"), digest(content()))
        self.assertNotEqual(request_digest(content(), "test-key-a"), request_digest(content(), "test-key-b"))
        self.assertEqual(request_digest(content(), "test-key-a"), request_digest(content(), "test-key-a"))
        with self.assertRaises(ValueError):request_digest(content(), None)

    def test_valid_single_choice(self): self.assertEqual(validate_content(content()), content())
    def test_canonical_order(self): self.assertEqual(digest({'b':2,'a':1}), digest({'a':1,'b':2}))
    def test_safe_ascii_serialization(self): self.assertEqual(json.loads(canonical({'x':'\u2028'})), {'x':'\u2028'})
    def test_extra_privileged_fields_rejected(self):
        for field in ['owner','status','flags','doctype','ignore_permissions','content_hash']:
            with self.subTest(field=field), self.assertRaises(ValueError):validate_content(dict(content(), **{field:'x'}))
    def test_missing_fields(self):
        for field in content():
            c=content();c.pop(field)
            with self.subTest(field=field),self.assertRaises(ValueError):validate_content(c)
    def test_bad_categories_and_types(self):
        for field,value in [('skill','TOEFL'),('skill','Speaking'),('skill','Writing'),('difficulty','B2'),('question_type','Code'),('prompt','Real response')]:
            c=content();c[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_content(c)
    def test_size_limits(self):
        for field,value in [('prompt','SYNTHETIC: '+'a'*4000),('options',[]),('options',[{'id':'a','text':'a'}]*7)]:
            c=content();c[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_content(c)
    def test_duplicate_and_unknown_keys(self):
        c=content();c['options'][1]['id']='a'
        with self.assertRaises(ValueError):validate_content(c)
        c=content();c['answer']='missing'
        with self.assertRaises(ValueError):validate_content(c)
    def test_option_payloads(self):
        for option in [{'id':'a;drop','text':'x'},{'id':'b','text':''},{'id':'b','text':'a'*1001},{'id':'b','text':'ok','key':True}]:
            c=content();c['options'][1]=option
            with self.subTest(option=option),self.assertRaises(ValueError):validate_content(c)
    def test_true_false_canonical(self):
        c=content();c.update(question_type='True False',options=[{'id':'true','text':'True'},{'id':'false','text':'False'}],answer='true')
        validate_content(c)
        c['options'].reverse()
        with self.assertRaises(ValueError):validate_content(c)
    def test_family_namespace_shape(self):
        validate_family('SYN-123ABC-FAMILY',1)
        for family,rev in [('REAL-X',1),('SYN-X',True),('SYN-X','1'),('SYN-X',0),('SYN-X',100001)]:
            with self.subTest(family=family,revision=rev),self.assertRaises(ValueError):validate_family(family,rev)
    def test_request_keys(self):
        validate_request_key('idempotent_key_001')
        for key in ['', 'x', ' '*20,'x'*97,42]:
            with self.subTest(key=key),self.assertRaises(ValueError):validate_request_key(key)
    def test_author_read_boundaries(self):
        self.assertTrue(can_read('item',['Placement Author'],'a','a','Draft'))
        self.assertFalse(can_read('item',['Placement Author'],'a','b','Draft'))
        self.assertTrue(can_read('item',['Placement Author'],'a','b','Published'))
        self.assertFalse(can_read('key',['Placement Author'],'a','b','Published'))
    def test_no_candidate_or_unrelated_access(self):
        for kind in ['item','key','audit','operation']:
            self.assertFalse(can_read(kind,['Student','Guest'],'a','a','Published'))
    def test_auditor_not_key_owner(self):
        self.assertTrue(can_read('audit',['Placement Auditor'],'a','b'))
        self.assertFalse(can_read('key',['Placement Auditor'],'a','b'))
        self.assertFalse(can_read('item',['Placement Auditor'],'a','b','Draft'))
    def test_publisher_reads_review_content(self):
        self.assertTrue(can_read('key',['Placement Publisher'],'p','a'))
        self.assertFalse(can_read('operation',['Placement Publisher'],'p','a'))
    def test_public_content_digest_does_not_encode_answer(self):
        a=content();b=copy.deepcopy(a);b['answer']='b'
        self.assertEqual(digest({k:v for k,v in a.items() if k!='answer'}),digest({k:v for k,v in b.items() if k!='answer'}))


if __name__ == '__main__': unittest.main()

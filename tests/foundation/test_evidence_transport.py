"""Exercise the actual publisher boundary without contacting GitHub."""
import base64
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

path=Path(__file__).resolve().parents[2]/'tools/foundation/publish_evidence.py'
spec=importlib.util.spec_from_file_location('publisher',path)
publisher=importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

class Response:
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self):return b'{"id":123}'

class EvidenceTransportTests(unittest.TestCase):
    def publish(self,report):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'report.json';source.write_text(json.dumps(report))
            env={'GITHUB_REF':'refs/heads/arena/01a0a942-tofel-house-erp','GITHUB_SHA':'synthetic-sha','GITHUB_REPOSITORY':'owned/example','GITHUB_TOKEN':'synthetic-test-token'}
            with patch.dict(os.environ,env),patch('sys.argv',['publish',str(source)]),patch.object(publisher,'urlopen',return_value=Response()) as send:
                publisher.main()
                return json.loads(send.call_args.args[0].data)
    def test_small_failure_preserved(self):
        report={'status':'fail','checks':[{'status':'fail','reason':'retained'}]}
        payload=self.publish(report)
        self.assertEqual(payload['conclusion'],'failure')
        self.assertEqual(json.loads(payload['output']['text'][8:-4]),report)
    def test_large_failure_round_trip_and_digest(self):
        report={'status':'fail','checks':[{'status':'fail','reason':'retained','index':i} for i in range(4000)]}
        payload=self.publish(report)
        envelope=json.loads(payload['output']['text'][8:-4])
        self.assertEqual(envelope['encoding'],'gzip+base64')
        raw=gzip.decompress(base64.b64decode(envelope['data']))
        self.assertEqual(json.loads(raw),report)
        digest=hashlib.sha256(raw).hexdigest()
        self.assertEqual(digest,envelope['report_sha256'])
        self.assertIn(digest,payload['output']['summary'])
        self.assertLess(len(payload['output']['text']),58020)
    def test_wrong_branch_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'r.json';p.write_text('{}')
            with patch.dict(os.environ,{'GITHUB_REF':'refs/heads/main'}),patch('sys.argv',['publish',str(p)]),patch.object(publisher,'urlopen') as send:
                with self.assertRaises(SystemExit):publisher.main()
                send.assert_not_called()

"""Test probe failure accounting, not application authorization.

HTTP is simulated here; real security findings require hosted runtime evidence.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.foundation import runtime_http


class Response:
    def __init__(self, status=200, data=None, content=b"", text=""):
        self.status_code = status
        self.data = data
        self.content = content
        self.text = text

    def json(self):
        return self.data


class HttpProbeAccountingTests(unittest.TestCase):
    def run_probe(self, disclosure):
        content = b"synthetic attachment"

        class Session:
            def __init__(self):
                self.headers = {}
                self.user = None

            def post(self, url, data, timeout):
                self.user = data["usr"]
                return Response()

            def get(self, url, timeout, **kwargs):
                if url.endswith("get_logged_user"):
                    return Response(data={"message": self.user})
                if "/api/resource/Student/" in url:
                    name = url.rsplit("/", 1)[1]
                    other = self.user == "validation-alpha@example.test" and name == "beta"
                    return Response(200 if disclosure or not other else 403, {"data": {"name": name}})
                if url.endswith("get_student_context"):
                    return Response(403)
                if "/private/files/" in url:
                    other = self.user == "validation-beta@example.test"
                    return Response(200 if disclosure or not other else 403, content=content)
                raise AssertionError("Unexpected probe URL")

        def get(url, **kwargs):
            if url.endswith("/login"):
                return Response()
            return Response(text='0{"sid":"synthetic","upgrades":["websocket"]}')

        fake_requests = SimpleNamespace(Session=Session, get=get, RequestException=ConnectionError)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            business = root / "business.json"
            report = root / "http.json"
            business.write_text(json.dumps({"records": {"students": ["alpha", "beta"],
                "private_file_url": "/private/files/proof.txt",
                "private_file_sha256": hashlib.sha256(content).hexdigest()}}))
            env = {"GITHUB_ACTIONS": "true", "FOUNDATION_BUSINESS_REPORT": str(business),
                   "FOUNDATION_HTTP_REPORT": str(report), "FOUNDATION_ADMIN_PASSWORD": "unit-test-placeholder",
                   "FOUNDATION_TEST_PASSWORD": "unit-test-placeholder"}
            with patch.dict(os.environ, env), patch.dict(sys.modules, {"requests": fake_requests}):
                code = runtime_http.main()
            raw = report.read_text()
            self.assertNotIn("unit-test-placeholder", raw)
            return code, json.loads(raw)

    def test_disclosure_fails_both_negative_checks_and_process(self):
        code, report = self.run_probe(disclosure=True)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "fail")
        self.assertEqual({c["name"] for c in report["checks"] if c["status"] == "fail"},
                         {"student-other-record-denied", "student-other-private-file-denied"})
        self.assertTrue(report["other_student_record_disclosed"])
        self.assertTrue(report["other_student_private_file_disclosed"])
        self.assertFalse(report["phase2_gate_passed"])

    def test_denials_with_positive_controls_pass_probe_not_foundation(self):
        code, report = self.run_probe(disclosure=False)
        self.assertEqual(code, 0)
        self.assertEqual(len(report["checks"]), 10)
        self.assertTrue(all(c["status"] == "pass" for c in report["checks"]))
        self.assertFalse(report["phase2_gate_passed"])


if __name__ == "__main__":
    unittest.main()

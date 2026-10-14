"""Contract for the Course Owner acceptance block of the encrypted restore rehearsal.

The first-boot step of .github/workflows/product-image.yml now proves three things on
synthetic CI data:

* the disposable Course Owner (backup-owner@toeflhouse.localhost) has a login secret
  that is generated, masked, passed to docker by name only, and never printed;
* the account identity, roles and effective Owner backup policy have the same
  fingerprint before the encrypted backup, after the restore, and after a
  restart-plus-migrate repair (the CI equivalent of the Windows repair command);
* the Course Owner logs in over HTTP after the restore and after the repair.

The behaviour tests execute the workflow's own probe and login bodies: the probe
against a stub `frappe` and a stub Owner policy module, and the login helper
against a local stub HTTP server. Nothing here contacts a real site, database,
backup, credential or runtime data.
"""
from __future__ import annotations

import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/product-image.yml"
YAML_INDENT = " " * 10
OWNER = "backup-owner@toeflhouse.localhost"
SITES = "/home/frappe/bench/sites"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _heredoc_body(text: str, opener: str) -> str:
    lines = text.splitlines()
    index = next(n for n, line in enumerate(lines) if line.strip() == opener)
    body: list[str] = []
    for line in lines[index + 1:]:
        if line == YAML_INDENT + "PY":
            break
        body.append(line[len(YAML_INDENT):] if line.startswith(YAML_INDENT) else line.lstrip())
    else:
        raise AssertionError(f"terminator for {opener!r} not found")
    return "\n".join(body) + "\n"


def _first_boot_block(text: str) -> str:
    start = text.index("First boot, encrypted backup/restore and guarded site-mode activation")
    return text[start:text.index("      - name: Browser UI acceptance", start)]


STUB_FRAPPE = '''\
import json
import os

_STATE = os.environ["STUB_STATE"]
_FAIL = os.environ.get("STUB_FAIL", "")


def _load():
    with open(_STATE) as handle:
        return json.load(handle)


def _save(state):
    with open(_STATE, "w") as handle:
        json.dump(state, handle)


def init(site=None, sites_path=None):
    if _FAIL == "init":
        raise RuntimeError("stub init failure")


def connect():
    if _FAIL == "connect":
        raise RuntimeError("stub connect failure")


def destroy():
    pass


class _Db:
    def commit(self):
        pass


db = _Db()


class _Role:
    def __init__(self, role):
        self.role = role


class _User:
    def __init__(self, state):
        self.email = state["email"]
        self.full_name = state["full_name"]
        self.enabled = state["enabled"]
        self.user_type = state["user_type"]
        self.roles = [_Role(role) for role in state["roles"]]


def get_doc(doctype, name):
    state = _load()
    if doctype != "User" or name != state["email"]:
        raise RuntimeError("no such user")
    return _User(state)
'''

STUB_PASSWORD = '''\
import os

from frappe_state import mark_password_set


def update_password(user, pwd, doctype="User", fieldname="password", logout_all_sessions=False):
    if not pwd or len(pwd) < 16:
        raise ValueError("password too short for the stub")
    mark_password_set(user)
'''

STUB_STATE_HELPER = '''\
import json
import os


def mark_password_set(user):
    path = os.environ["STUB_STATE"]
    with open(path) as handle:
        state = json.load(handle)
    state["password_set_for"] = user
    with open(path, "w") as handle:
        json.dump(state, handle)
'''

STUB_OWNER_CONFIG = '''\
import json
import os


def current_backup_policy(on_date=None):
    with open(os.environ["STUB_STATE"]) as handle:
        policy = json.load(handle)["policy"]
    return policy
'''


class _LoginHandler(http.server.BaseHTTPRequestHandler):
    owner = OWNER
    password = ""
    session = "stub-session-token"

    def log_message(self, *args):
        pass

    def _send(self, status, payload, cookie=None):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        form = dict(item.split("=", 1) for item in self.rfile.read(length).decode().split("&") if "=" in item)
        if self.path == "/api/method/login" and form.get("usr") == self.owner.replace("@", "%40") \
                and form.get("pwd") == self.password.replace("@", "%40"):
            self._send(200, {"message": "Logged In"}, cookie=f"sid={self.session}; Path=/")
        else:
            self._send(401, {"message": "Invalid Login. Try again."})

    def do_GET(self):
        cookie = self.headers.get("Cookie", "")
        if self.path == "/api/method/frappe.auth.get_logged_user" and f"sid={self.session}" in cookie:
            self._send(200, {"message": self.owner})
        else:
            self._send(403, {"message": "not logged in"})


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = _workflow()
        cls.block = _first_boot_block(cls.text)

    def test_password_is_masked_passed_by_name_and_never_echoed(self):
        self.assertIn('echo "::add-mask::$owner_password"', self.block)
        self.assertIn("-e CI_OWNER_PASSWORD ", self.block)
        for line in self.block.splitlines():
            if "docker compose" in line:
                self.assertNotIn("CI_OWNER_PASSWORD=", line)
                self.assertNotIn("$owner_password", line)
            if re.search(r"\b(echo|printf)\b.*\$owner_password", line) and "::add-mask::" not in line:
                self.fail(f"owner password printed: {line.strip()}")

    def test_fingerprint_precedes_backup_and_is_checked_after_restore_and_repair(self):
        pre = self.block.index('owner-pre.txt 2>&1')
        backup = self.block.index("/product/backup.py")
        restore = self.block.index("/product/restore.py")
        post_restore = self.block.index("owner-post-restore.txt 2>&1")
        restart = self.block.index("docker compose restart web worker scheduler socketio")
        migrate = self.block.index("bench --site toeflhouse.localhost migrate")
        post_repair = self.block.index("owner-post-repair.txt 2>&1")
        activation = self.block.index('checkpoint="site-mode activation, refusals and deactivation"')
        self.assertLess(pre, backup)
        self.assertLess(backup, restore)
        self.assertLess(restore, post_restore)
        self.assertLess(post_restore, restart)
        self.assertLess(restart, migrate)
        self.assertLess(migrate, post_repair)
        self.assertLess(post_repair, activation)

    def test_every_comparison_fails_closed(self):
        for marker in ("owner_pre_rc", "owner_restore_rc", "owner_repair_rc",
                       "owner_login_rc"):
            self.assertIn(f'"${marker}" -ne 0', self.block, marker)
        self.assertIn('"$owner_restored" != "$owner_pre"', self.block)
        self.assertIn('"$owner_repaired" != "$owner_pre"', self.block)
        self.assertGreaterEqual(self.block.count("tail -n 40"), 3)

    def test_repair_is_the_windows_repair_equivalent(self):
        self.assertIn("product/windows/Repair TOEFL House ERP.cmd", self.block)
        self.assertIn("reruns migrations", self.block)


class BehaviourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = _workflow()
        cls.probe = _heredoc_body(text, "cat > owner-probe.py <<'PY'")
        cls.login = _heredoc_body(text, "cat > owner-login-check.py <<'PY'")
        cls.tmp = Path(tempfile.mkdtemp(prefix="owner-accept-"))
        stubs = cls.tmp / "stubs"
        (stubs / "frappe" / "utils").mkdir(parents=True)
        (stubs / "toefl_house" / "operations").mkdir(parents=True)
        (stubs / "frappe" / "__init__.py").write_text(STUB_FRAPPE, encoding="utf-8")
        (stubs / "frappe" / "utils" / "__init__.py").write_text("", encoding="utf-8")
        (stubs / "frappe" / "utils" / "password.py").write_text(STUB_PASSWORD, encoding="utf-8")
        (stubs / "frappe_state.py").write_text(STUB_STATE_HELPER, encoding="utf-8")
        (stubs / "toefl_house" / "__init__.py").write_text("", encoding="utf-8")
        (stubs / "toefl_house" / "operations" / "__init__.py").write_text("", encoding="utf-8")
        (stubs / "toefl_house" / "operations" / "owner_configuration.py").write_text(
            STUB_OWNER_CONFIG, encoding="utf-8")
        cls.stubs = stubs
        cls.sites = cls.tmp / "sites"
        cls.sites.mkdir()
        cls.probe_script = cls.probe.replace(SITES, str(cls.sites))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.state = self.tmp / f"state-{self._testMethodName}.json"
        self.state.write_text(json.dumps({
            "email": OWNER,
            "full_name": "Backup Owner",
            "enabled": 1,
            "user_type": "System User",
            "roles": ["Course Owner", "Desk User"],
            "policy": {"configured": True, "retention_versions": 3,
                       "retention_behavior": "Preserve all valid backup sets",
                       "recovery_key_sha256": "ab" * 32},
        }), encoding="utf-8")

    def _probe(self, *, set_password: bool, fail: str = "", password: str = "") -> tuple[int, str]:
        env = {**os.environ, "PYTHONPATH": str(self.stubs), "STUB_STATE": str(self.state),
               "STUB_FAIL": fail, "CI_OWNER_PASSWORD": password}
        if set_password:
            env["CI_SET_OWNER_PASSWORD"] = "1"
        else:
            env.pop("CI_SET_OWNER_PASSWORD", None)
        done = subprocess.run([sys.executable, "-"], input=self.probe_script, text=True,
                              capture_output=True, env=env, cwd=str(self.sites), check=False)
        return done.returncode, done.stdout + done.stderr

    def test_probe_fingerprint_is_stable_across_pre_restore_and_post_repair_and_secret_free(self):
        secret = "stub-owner-secret-0123456789abcdef"
        rc, pre = self._probe(set_password=True, password=secret)
        self.assertEqual(rc, 0, pre)
        self.assertNotIn(secret, pre)
        rc, post = self._probe(set_password=False, password=secret)
        self.assertEqual(rc, 0, post)
        digest = re.search(r"^RESULT owner_fingerprint=([0-9a-f]{64})$", pre, re.M)
        self.assertIsNotNone(digest, pre)
        self.assertEqual(re.findall(r"^RESULT owner_fingerprint=([0-9a-f]+)$", post, re.M), [digest.group(1)])
        self.assertEqual(json.loads(self.state.read_text())["password_set_for"], OWNER)

    def test_fingerprint_changes_when_a_role_or_the_policy_changes(self):
        _, before = self._probe(set_password=False)
        state = json.loads(self.state.read_text())
        state["roles"] = ["Desk User"]
        self.state.write_text(json.dumps(state), encoding="utf-8")
        _, after = self._probe(set_password=False)
        self.assertNotEqual(re.search(r"owner_fingerprint=(\w+)", before).group(1),
                            re.search(r"owner_fingerprint=(\w+)", after).group(1))

    def test_probe_fails_closed_with_a_result_line_when_frappe_raises(self):
        rc, out = self._probe(set_password=False, fail="connect")
        self.assertNotEqual(rc, 0)
        self.assertIn("RESULT owner_fingerprint=error RuntimeError: stub connect failure", out)
        self.assertIsNone(re.search(r"^RESULT owner_fingerprint=[0-9a-f]{64}$", out, re.M))

    def _login(self, password: str, server_password: str) -> tuple[int, str]:
        handler = type("Handler", (_LoginHandler,), {"password": server_password})
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = {**os.environ, "CI_OWNER_PASSWORD": password,
                   "CI_BASE_URL": f"http://127.0.0.1:{server.server_address[1]}"}
            done = subprocess.run([sys.executable, "-"], input=self.login, text=True,
                                  capture_output=True, env=env, check=False)
            return done.returncode, done.stdout + done.stderr
        finally:
            server.shutdown()
            server.server_close()

    def test_login_check_reports_ok_for_the_course_owner_session(self):
        rc, out = self._login("stub-owner-secret-0123456789abcdef", "stub-owner-secret-0123456789abcdef")
        self.assertEqual(rc, 0, out)
        self.assertIn(f"RESULT owner_login=ok user={OWNER}", out)

    def test_login_check_fails_closed_on_refused_credentials(self):
        rc, out = self._login("wrong-secret-0123456789abcdef", "stub-owner-secret-0123456789abcdef")
        self.assertNotEqual(rc, 0)
        self.assertIn("RESULT owner_login=refused", out)
        self.assertNotIn("wrong-secret", out)


if __name__ == "__main__":
    unittest.main()

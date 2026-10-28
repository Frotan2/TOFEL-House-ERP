"""State-replay checks for the Microsoft (Office 365) callback (2026-10-18).

Scope and limits. The callback in `apps/toefl_house/toefl_house/social_login.py` is driven
through a fake `frappe` module. The state cache mirrors the pinned Frappe revision
`988e54f3c4c2`, `frappe/utils/oauth.py` lines 98-118 (`create_oauth_state` and
`consume_oauth_state`: cache get, then delete, single use, 600 s TTL). The TTL is not
modelled. This proves the callback's own wiring: the state is passed through unchanged,
it is consumed by the only place that consumes it, and a replayed state never establishes
a login. It does not run Frappe. The real-site replay (HTTP 417 on the second request) is
still an owner or CI check on a live bench.

Replay is still blocked without state reuse: Microsoft codes are single use, so a replayed
callback also fails at the token exchange. Both layers are asserted separately below.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "apps/toefl_house/toefl_house/social_login.py"
TENANT = "11111111-2222-3333-4444-555555555555"
PREFIX = "frappe_oauth_login"


class _Cache:
    """In-memory stand-in for frappe.cache (get_value / set_value / delete_value)."""

    def __init__(self):
        self.values = {}
        self.writes = []

    def set_value(self, key, value, expires_in_sec=None):
        self.writes.append(key)
        self.values[key] = value

    def get_value(self, key):
        return self.values.get(key)

    def delete_value(self, key):
        self.values.pop(key, None)


def _create_state(cache, redirect_to):
    # Mirror of frappe/utils/oauth.py create_oauth_state (988e54f3c4c2).
    state = "state-" + str(len(cache.writes))
    cache.set_value(f"{PREFIX}:{state}", redirect_to or "", expires_in_sec=600)
    return state


def _consume_state(cache, state):
    # Mirror of frappe/utils/oauth.py consume_oauth_state (988e54f3c4c2): get, then delete.
    if not state:
        return None
    key = f"{PREFIX}:{state}"
    redirect_to = cache.get_value(key)
    cache.delete_value(key)
    return redirect_to


class _Harness:
    """Loads social_login with a fake frappe and a Frappe-mirroring login_oauth_user."""

    def __init__(self, cache, exchange_ok=True):
        self.cache = cache
        self.logins = []
        self.refusals = []
        self.exchange_ok = exchange_ok
        self.frappe = types.ModuleType("frappe")
        self.frappe.whitelist = lambda **kwargs: (lambda fn: fn)
        self.frappe._ = lambda text, *args: text
        self.frappe.local = types.SimpleNamespace(form_dict={})
        self.frappe.conf = {"office_365_tenant_id": TENANT}
        self.frappe.PermissionError = PermissionError

        def throw(message, exc=None):
            raise (exc or Exception)(message)

        self.frappe.throw = throw
        self.frappe.logger = lambda name: types.SimpleNamespace(warning=lambda *a, **k: None)
        self.frappe.get_all = lambda *a, **k: [{"parent": "owner@example.test"}]
        self.frappe.get_doc = lambda *a, **k: types.SimpleNamespace(
            name="owner@example.test", enabled=1,
            get_social_login_userid=lambda provider: "synthetic-subject")
        self.frappe.cache = cache

        harness = self

        def get_auth_session(**kwargs):
            if not harness.exchange_ok:
                raise ValueError("invalid_grant: authorization code already used")
            return types.SimpleNamespace(access_token_response=types.SimpleNamespace(
                text='{"id_token": "token"}'))

        def login_oauth_user(data, *, provider=None, state=None, **_):
            # Mirror of frappe/utils/oauth.py login_oauth_user: the state is consumed first.
            redirect_to = _consume_state(harness.cache, state)
            if redirect_to is None:
                harness.refusals.append(state)
                return
            harness.logins.append((data["sub"], provider, state, redirect_to))

        self.oauth = types.ModuleType("frappe.utils.oauth")
        self.oauth.get_oauth2_flow = lambda provider: types.SimpleNamespace(get_auth_session=get_auth_session)
        self.oauth.get_redirect_uri = lambda provider: "https://example.test/callback"
        self.oauth.get_oauth_keys = lambda provider: {"client_id": "app-client"}
        self.oauth.get_email = lambda info: info.get("email")
        self.oauth.login_oauth_user = login_oauth_user
        utils = types.ModuleType("frappe.utils")
        utils.oauth = self.oauth
        integrations = types.ModuleType("frappe.integrations")
        handlers = types.ModuleType("frappe.integrations.oauth2_logins")
        handlers.decoder_compat = lambda data: data

        spec = importlib.util.spec_from_file_location("social_login_replay_under_test", MODULE)
        self.module = importlib.util.module_from_spec(spec)
        self._modules = {"frappe": self.frappe, "frappe.utils": utils, "frappe.utils.oauth": self.oauth,
                         "frappe.integrations": integrations,
                         "frappe.integrations.oauth2_logins": handlers}
        with patch.dict(sys.modules, self._modules):
            spec.loader.exec_module(self.module)

    def callback(self, code, state, verified_sub="synthetic-subject"):
        """Run the real login_via_office365 with the ID-token verification stubbed to succeed."""
        with patch.dict(sys.modules, self._modules), patch.object(
            self.module, "verify_office365_id_token",
            return_value={"sub": verified_sub, "email": "untrusted@example.test"},
        ):
            return self.module.login_via_office365(code, state)


class MicrosoftCallbackStateReplayTests(unittest.TestCase):
    def setUp(self):
        self.cache = _Cache()

    def test_first_callback_logs_in_once_and_consumes_state(self):
        state = _create_state(self.cache, "/app")
        h = _Harness(self.cache)
        h.callback("code-1", state)
        self.assertEqual(h.logins, [("synthetic-subject", "office_365", state, "/app")])
        self.assertNotIn(f"{PREFIX}:{state}", self.cache.values)

    def test_replayed_state_with_same_code_does_not_log_in_again(self):
        # Worst case for the callback: the exchange still succeeds. Frappe's state check must refuse.
        state = _create_state(self.cache, "/app")
        h = _Harness(self.cache)
        h.callback("code-1", state)
        h.callback("code-1", state)
        self.assertEqual(len(h.logins), 1, "a replayed state must not establish a second login")
        self.assertEqual(h.refusals, [state])

    def test_replayed_state_with_reused_code_is_refused_at_token_exchange(self):
        state = _create_state(self.cache, "/app")
        _Harness(self.cache).callback("code-1", state)
        h = _Harness(self.cache, exchange_ok=False)
        with self.assertRaisesRegex(PermissionError, "identity verification failed"):
            h.callback("code-1", state)
        self.assertEqual(h.logins, [])

    def test_unknown_state_is_refused(self):
        h = _Harness(self.cache)
        h.callback("code-1", "never-issued")
        self.assertEqual(h.logins, [])
        self.assertEqual(h.refusals, ["never-issued"])

    def test_empty_state_is_refused(self):
        h = _Harness(self.cache)
        h.callback("code-1", "")
        self.assertEqual(h.logins, [])

    def test_each_state_is_bound_to_its_own_attempt(self):
        first = _create_state(self.cache, "/first")
        second = _create_state(self.cache, "/second")
        h = _Harness(self.cache)
        h.callback("code-1", second)
        h.callback("code-2", first)
        self.assertEqual([(login[2], login[3]) for login in h.logins],
                         [(second, "/second"), (first, "/first")])

    def test_callback_never_mints_or_extends_state(self):
        state = _create_state(self.cache, "/app")
        writes_before = len(self.cache.writes)
        h = _Harness(self.cache)
        h.callback("code-1", state)
        self.assertEqual(len(self.cache.writes), writes_before, "the callback must not write login state")


if __name__ == "__main__":
    unittest.main()

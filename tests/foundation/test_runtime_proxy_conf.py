"""Contract for the lab reverse proxy that fronts the realtime edge.

Frappe's realtime server builds every URL it calls back into the site with
from the socket's Origin header (frappe ``realtime/utils.js`` ``get_url``).
If the proxy forwards an Origin that does not resolve to a live desk edge,
``get_user_info`` fails, the authenticate middleware rejects the socket, and
no app realtime handler ever runs. That failure mode is silent from the
outside -- the gate simply reports "exit 1" -- so the invariant is pinned
here rather than discovered again in a 20-minute hosted run.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from runtime_install import build_proxy_conf  # noqa: E402


def get_hostname(url):
    """Mirror of frappe realtime/middlewares/authenticate.js get_hostname."""
    if not url:
        return None
    if "://" in url:
        url = url.split("/")[2]
    return url[: url.index(":")] if ":" in url else url


def socketio_block(conf):
    start = conf.index("listen 127.0.0.1:9000;")
    end = conf.index("\n }\n", start)
    return conf[start:end]


def desk_block(conf):
    start = conf.index("listen 127.0.0.1:8080;")
    end = conf.index("\n }\n", start)
    return conf[start:end]


class RuntimeProxyConfTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conf = build_proxy_conf(Path("/tmp/foundation-lab"), Path("/tmp/foundation-bench"))

    def test_socketio_edge_pins_reachable_callback_origin(self):
        block = socketio_block(self.conf)
        self.assertIn("proxy_set_header Origin $scheme://$host:8080;", block)
        # A bare $http_host drops the port and resolves to :80, where the lab
        # serves nothing.
        self.assertNotIn("proxy_set_header Origin $scheme://$http_host;", block)

    def test_origin_is_never_taken_from_the_client(self):
        self.assertNotIn("$http_origin", self.conf)

    def test_site_routing_is_server_derived(self):
        for block in (desk_block(self.conf), socketio_block(self.conf)):
            self.assertIn("proxy_set_header X-Frappe-Site-Name $foundation_site;", block)
            self.assertIn("if ($foundation_site = '') { return 444; }", block)

    def test_upstreams_match_the_pinned_lab_ports(self):
        self.assertIn("proxy_pass http://127.0.0.1:8000;", desk_block(self.conf))
        self.assertIn("proxy_pass http://127.0.0.1:19000;", socketio_block(self.conf))

    def test_origin_and_host_satisfy_frappe_origin_check(self):
        """Reproduce authenticate.js's host/origin equality guard."""
        # What nginx forwards for a client hitting the 9000 edge as
        # foundation.localhost: Host $host, Origin $scheme://$host:8080.
        forwarded_host = "foundation.localhost"
        forwarded_origin = "http://foundation.localhost:8080"
        self.assertEqual(get_hostname(forwarded_host), get_hostname(forwarded_origin))

    def test_braces_balance(self):
        self.assertEqual(self.conf.count("{"), self.conf.count("}"))

    def test_lab_specific_paths_are_interpolated(self):
        self.assertIn("pid /tmp/foundation-lab/nginx.pid;", self.conf)
        self.assertIn("alias /tmp/foundation-bench/sites/assets/;", self.conf)


if __name__ == "__main__":
    unittest.main()

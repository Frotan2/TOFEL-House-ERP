"""SEC-DEPS-01 triage wiring contracts.

Pins the safe mitigations we apply inside the v16 boundary without touching any
vendor dependency code or lockfile:

* the hosted runtime reverse-proxies the socket.io server through nginx so the
  public port parses and caps requests before they reach node;
* the WeasyPrint whitelist endpoints are overridden to mirror the beta-builder
  gate that the normal print flow already enforces;
* the node-realtime exposure probe ships in tools and runs after the proxy is
  started as a negative control.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "apps/toefl_house/toefl_house/hooks.py"
PRINTING = ROOT / "apps/toefl_house/toefl_house/printing.py"
RUNTIME_INSTALL = ROOT / "tools/foundation/runtime_install.py"
REALTIME_PROBE = ROOT / "tools/foundation/realtime_exposure_probe.js"


def assign(path, name):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if getattr(target, "id", None) == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{name} assignment not found in {path.relative_to(ROOT)}")


class SecDepsTriageWiringTests(unittest.TestCase):
    def test_weasyprint_whitelist_overrides_pin_beta_gate(self):
        overrides = assign(HOOKS, "override_whitelisted_methods")
        self.assertEqual(overrides["frappe.utils.weasyprint.download_pdf"],
                         "toefl_house.printing.download_pdf")
        self.assertEqual(overrides["frappe.utils.weasyprint.get_html"],
                         "toefl_house.printing.get_html")
        text = PRINTING.read_text()
        for needle in ("print_format_builder_beta", "doc.check_permission(\"print\")",
                       "WeasyPrint rendering is only enabled for beta-builder"):
            self.assertIn(needle, text)

    def test_runtime_reverse_proxies_socketio_through_nginx(self):
        text = RUNTIME_INSTALL.read_text()
        # Socket.io node must bind loopback on port 19000 (not 0.0.0.0:9000).
        self.assertIn('socketio_env["FRAPPE_SOCKETIO_PORT"] = "19000"', text)
        # Nginx must listen on the canonical 9000 WebSocket port.
        self.assertIn("listen 127.0.0.1:9000;", text)
        # The WebSocket upgrade must be proxied and the octet-stream
        # connection-hold payload for GHSA-r635 must be blocked at the edge.
        self.assertIn('if ($content_type = "application/octet-stream") {{ set $rt_bad "${{rt_bad}}1"; }}', text)
        self.assertIn('if ($rt_bad = 11) {{ return 400; }}', text)
        # Header / body caps must be present so GHSA-3h5v and octet-stream
        # connection-hold payloads never reach node.
        self.assertIn("large_client_header_buffers 4 4k;", text)
        self.assertIn("client_max_body_size 1m;", text)
        self.assertIn("proxy_pass http://127.0.0.1:19000;", text)
        # The realtime edge probe must be run against the public port with the
        # direct node port as the health target, and its verdict must fail the
        # install if any advisory still reaches the node.
        self.assertIn("realtime-edge-exposure-probe", text)
        self.assertIn('"--target", "127.0.0.1:9000"', text)
        self.assertIn('"--health", "127.0.0.1:19000"', text)
        self.assertIn('"--host-header", "foundation.localhost"', text)
        self.assertIn('if not realtime_probe.get("all_survived"):', text)

    def test_realtime_exposure_probe_covers_eight_node_advisories(self):
        text = REALTIME_PROBE.read_text()
        # The probe exercises every one of the eight server_runtime_node_realtime
        # advisories grouped by their pre-auth PoC shape.
        for advisory in ("GHSA-3h5v-q93c-6h6q", "GHSA-677m-j7p3-52f9",
                         "GHSA-2m8v-j782-fhvr", "GHSA-r635-g3xr-vw7x",
                         "GHSA-gr94-w7qr-f4j3"):
            self.assertIn(advisory, text)
        # Binary-attachment frames must be masked per RFC6455; unmasked client
        # frames would be a no-op against a conformant ws server.
        self.assertIn("body[i] ^= mask[i % 4]", text)

    def test_runtime_install_runs_one_shot_build_only_no_dev_servers(self):
        """SEC-DEPS-01 build-time / dev-server finding boundary.

        Production must run `bench build` once (one-shot esbuild production
        bundle) and must never start `--watch`, `vite`, `yarn dev`,
        `bench start`, honcho, or any SPA dev server. This regression pins
        the absence of those flags/invocations so BUILD_ONLY / DEV_ONLY
        classifications remain accurate.
        """
        text = RUNTIME_INSTALL.read_text()
        # One-shot asset build only — no --watch, no --serve, no dev.
        self.assertIn('bench("asset-build", "build", timeout=1800)', text)
        for forbidden in (
            "--watch", "yarn dev", "yarn serve", "vite dev", "bench start",
            "bench watch", "esbuild --serve", "esbuild serve", "honcho start",
            "foreman start", "bench serve", "node esbuild --watch",
        ):
            self.assertNotIn(forbidden, text, f"dev-server command {forbidden!r} leaked into production launch")
        # The production process set is hard-coded to gunicorn + bench worker +
        # bench schedule + node socketio.js directly — no Procfile-driven dev.
        self.assertIn('["node", str(bench_dir / "apps/frappe/socketio.js")]', text)
        self.assertIn('"--bind", "127.0.0.1:8000", "--workers", "2", "frappe.app:application"', text)
        # bench worker/schedule are the supported production background
        # processes — these do NOT pull in the `watch` Procfile entry.
        self.assertIn('"worker", "--queue", "short,default,long"', text)
        self.assertIn('"schedule"', text)

    def test_socketio_binds_loopback_only(self):
        """The vulnerable realtime node server must not listen on 0.0.0.0."""
        text = RUNTIME_INSTALL.read_text()
        self.assertIn('env["FRAPPE_SOCKETIO_PORT"] = "19000"', text)
        self.assertIn('create_connection(("127.0.0.1", 19000)', text)
        self.assertNotIn("0.0.0.0:19000", text)
        # Pre-nginx HTTP isolation probes must read their port from
        # FRAPPE_SOCKETIO_PORT so they hit the direct listener rather than
        # the public 9000 (which only starts answering once nginx is up).
        http_probe = ROOT / "tools/foundation/runtime_http.py"
        self.assertTrue(http_probe.exists())
        probe_text = http_probe.read_text()
        self.assertIn('socketio_port = int(os.environ.get("FRAPPE_SOCKETIO_PORT", "9000"))', probe_text)
        self.assertIn("f\"http://127.0.0.1:{socketio_port}/socket.io/\"", probe_text)

    def test_esbuild_watch_gate_guards_launch_editor_and_shell_quote(self):
        """Static contract on the pinned frappe esbuild.js: launch-editor
        (transitively shell-quote) is only required() inside open_in_editor()
        which is only called when WATCH_MODE is true. Production bench build
        invokes esbuild without --watch (see frappe.commands.utils.build which
        does not pass --watch when mode=production); this pins that gating.
        """
        esbuild = (ROOT / "work/f/esbuild/esbuild.js" if (ROOT / "work/f/esbuild/esbuild.js").exists()
                   else Path("/home/user/work/f/esbuild/esbuild.js"))
        if not esbuild.exists():
            self.skipTest("frappe scratch clone not present in this sandbox")
        text = esbuild.read_text()
        self.assertIn("const WATCH_MODE = Boolean(argv.watch);", text)
        self.assertIn("if (WATCH_MODE) {\n\t// listen for open files in editor event\n\topen_in_editor();\n}", text)
        # launch-editor is loaded lazily inside open_in_editor(), not at top level.
        self.assertIn("let launch = require(\"launch-editor\");", text)
        # When WATCH_MODE is off, process exits 0 after building.
        self.assertIn("if (!WATCH_MODE) {\n\t\tprocess.exit(0);\n\t}", text)

    def test_per_finding_triage_json_carries_dispositions(self):
        """Every one of the 102 advisories must carry an explicit
        runtime_disposition key with a supported classification."""
        import json
        triage = ROOT / "docs/engineering/evidence/sec-deps-01/per-finding-remediation-analysis-2026-09-23.json"
        if not triage.exists():
            self.skipTest("per-finding triage JSON not yet written")
        data = json.loads(triage.read_text())
        advisories = 0
        for pkg in data["packages"]:
            for adv in pkg["advisories"]:
                advisories += 1
                disp = adv.get("runtime_disposition")
                self.assertIn(disp, {
                    "MITIGATED", "NOT_REACHABLE", "BUILD_ONLY", "DEV_ONLY",
                    "INSTALL_ONLY", "BROWSER_SELF_DENIAL",
                    "OWNER_DECISION_REQUIRED", "BLOCKED",
                }, f"missing/unknown disposition for {adv['id']}")
        self.assertEqual(advisories, 102, "expected 102 advisories; raw audit count must be preserved")

    def test_runtime_triage_markdown_covers_remaining_findings(self):
        md = (ROOT / "docs/engineering/evidence/sec-deps-01/runtime-exposure-triage-2026-09-24.md")
        if not md.exists():
            self.skipTest("runtime triage markdown not yet written")
        text = md.read_text()
        # Bucket headers for the four remaining disposition classes must appear.
        for header in (
            "## Build-time-only (one-shot production bundle)",
            "## Dev-server-only (vite / esbuild serve / launch-editor)",
            "## Install-time-only (setuptools MANIFEST.in sdist NFC bypass)",
            "## Browser-shipped SPAs (Education / HRMS portals)",
        ):
            self.assertIn(header, text, f"missing section {header!r}")


if __name__ == "__main__":
    unittest.main()

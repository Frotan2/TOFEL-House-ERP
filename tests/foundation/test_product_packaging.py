"""Contract for the one-click desktop product layer under product/.

The layer has one job: wrap the already-reviewed, matrix-pinned runtime into a
zero-CLI Windows launch experience. These tests fail closed whenever the
wrapper drifts from that job: pins must equal the foundation version matrix
(single source of truth), exposures must stay loopback-only, no literal secret
may appear in any shipped script, and the first-run bootstrap logic must stay
idempotent against the proven hosted app order. The image build / Windows run
itself is NOT EXECUTED in this engineering environment (no Docker daemon, no
Windows) and is labelled as such in the README; these tests are the in-sandbox
verified slice.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

import bootstrap  # noqa: E402


def matrix_parts():
    matrix = json.loads((ROOT / "docs/engineering/foundation-version-matrix.json").read_text())
    return {c["name"]: c for c in matrix["components"]}


COMPOSE = PRODUCT / "docker-compose.yml"
DOCKERFILE = PRODUCT / "app.Dockerfile"
SCRIPTS = sorted((PRODUCT / "windows").glob("*.cmd"))


class PinParityContract(unittest.TestCase):
    def test_compose_service_images_match_matrix_digests(self):
        parts = matrix_parts()
        text = COMPOSE.read_text()
        self.assertIn(parts["mariadb"]["image_digest"], text)
        self.assertEqual(text.count(parts["redis"]["image_digest"]), 2)

    def test_dockerfile_arg_defaults_match_matrix(self):
        parts = matrix_parts()
        text = DOCKERFILE.read_text()

        def arg(name):
            match = re.search(rf"^ARG {name}=(\S+)$", text, flags=re.M)
            self.assertIsNotNone(match, f"missing ARG {name}")
            return match.group(1)

        self.assertEqual(arg("PYTHON_VERSION"), parts["python"]["selected_version"])
        self.assertEqual(arg("NODE_VERSION"), parts["node"]["selected_version"])
        self.assertEqual(arg("YARN_VERSION"), parts["yarn"]["selected_version"])
        self.assertEqual(arg("BENCH_VERSION"), parts["bench"]["selected_version"])
        self.assertEqual(arg("UV_VERSION"), parts["uv"]["selected_version"])
        self.assertEqual(arg("FRAPPE_COMMIT"), parts["frappe"]["commit"])
        self.assertEqual(arg("ERPNEXT_COMMIT"), parts["erpnext"]["commit"])
        self.assertEqual(arg("EDUCATION_COMMIT"), parts["education"]["commit"])
        self.assertEqual(arg("PAYMENTS_COMMIT"), parts["payments"]["commit"])
        self.assertEqual(arg("HRMS_COMMIT"), parts["hrms"]["commit"])

    def test_dockerfile_verifies_every_pinned_commit_after_checkout(self):
        text = DOCKERFILE.read_text()
        self.assertIn("rev-parse HEAD", text)
        self.assertIn("checkout --detach FETCH_HEAD", text)


class DesktopContract(unittest.TestCase):
    def test_host_exposure_is_loopback_only(self):
        text = COMPOSE.read_text()
        ports_block = re.findall(r'ports:\n((?:\s+- .+\n)+)', text)
        self.assertTrue(ports_block, "compose has no ports to validate")
        for block in ports_block:
            for published in re.findall(r'"(.+?:\d+:\d+)"', block):
                self.assertTrue(published.startswith("127.0.0.1:"), published)

    def test_no_published_database_port(self):
        # MariaDB must never be reachable from the Windows host network.
        text = COMPOSE.read_text()
        match = re.search(r'^  db:\n(.*?)(?=^  \S)', text, flags=re.M | re.S)
        self.assertIsNotNone(match)
        self.assertNotIn("ports:", match.group(1))

    def test_no_literal_secrets_anywhere_in_product_layer(self):
        # Sensitive keys (db/admin/root passwords) must never carry a literal
        # value: scripts must use variables (%DBPW%, $ENV{...}) and the runtime
        # secret file is generated on the owner's PC, never shipped.
        sensitive = re.compile(r'(?i)(MARIADB_ROOT_PASSWORD|MYSQL_ROOT_PASSWORD'
                               r'|DB_ROOT_PASSWORD|ADMIN_PASSWORD|DB_PASSWORD)\s*[:=]\s*([^\s&|>]+)')
        for path in PRODUCT.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in (".cmd", ".yml", ".yaml", ".env", ".sh") and "Dockerfile" not in path.name:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in sensitive.finditer(text):
                value = match.group(2).strip("'\"")
                self.assertTrue(
                    value.startswith(("%", "$")) or value.upper().startswith(("[", "{")),
                    f"literal-looking secret value in {path.name}: {match.group(0)[:60]}")
        self.assertFalse((PRODUCT / "data").exists(), "runtime data must be generated on the owner's PC")
        self.assertFalse((PRODUCT / "secrets").exists())
        self.assertFalse(list(PRODUCT.rglob("db.env")))

    def test_install_generates_password_as_variable_not_literal(self):
        install = (PRODUCT / "windows" / "Install TOEFL House ERP.cmd").read_text()
        self.assertIn("NewGuid", install)  # generated on the owner's PC at install time
        self.assertIn("MARIADB_ROOT_PASSWORD=%DBPW%", install)

    def test_windows_scripts_are_zero_typing_and_self_locating(self):
        names = {p.name for p in SCRIPTS}
        self.assertEqual(names, {"Install TOEFL House ERP.cmd", "Start TOEFL House ERP.cmd",
                                 "Stop TOEFL House ERP.cmd", "Backup TOEFL House ERP.cmd",
                                 "Repair TOEFL House ERP.cmd"})
        for path in SCRIPTS:
            text = path.read_text()
            self.assertIn('cd /d "%~dp0.."', text, path.name)
            self.assertNotIn("wsl ", text, path.name)  # Docker Desktop owns WSL2, users never touch it
        install = (PRODUCT / "windows" / "Install TOEFL House ERP.cmd").read_text()
        self.assertIn("docker compose build", install)
        self.assertIn("docker compose up -d", install)
        self.assertIn("first-run-credentials.txt", install.lower())

    def test_entrypoint_running_sequence_is_bootstrap_then_gunicorn(self):
        text = (PRODUCT / "entrypoint.sh").read_text()
        self.assertLess(text.index("python3 /product/bootstrap.py"),
                        text.index("exec /home/frappe/bench/env/bin/gunicorn"))


class BootstrapLogicContract(unittest.TestCase):
    def test_missing_apps_keeps_proven_hosted_order(self):
        self.assertEqual(list(bootstrap.APP_ORDER),
                         ["erpnext", "education", "payments", "hrms", "foundation_security", "toefl_house"])
        installed = ["erpnext", "foundation_security"]
        self.assertEqual(bootstrap.missing_apps(installed),
                         ["education", "payments", "hrms", "toefl_house"])
        self.assertEqual(bootstrap.missing_apps(list(bootstrap.APP_ORDER)), [])

    def test_parse_installed_apps_tolerates_bench_output_shapes(self):
        self.assertEqual(bootstrap.parse_installed_apps(""), [])
        self.assertEqual(bootstrap.parse_installed_apps("{}"), [])
        self.assertEqual(bootstrap.parse_installed_apps('["frappe", "erpnext"]'), ["frappe", "erpnext"])
        self.assertEqual(bootstrap.parse_installed_apps('{"albania.localhost": ["frappe", "erpnext"]}'),
                         ["frappe", "erpnext"])

    def test_idempotency_markers(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            sites = Path(tmp)
            self.assertFalse(bootstrap.site_exists("x.localhost", sites))
            (sites / "x.localhost").mkdir(parents=True)
            (sites / "x.localhost" / "site_config.json").write_text("{}")
            self.assertTrue(bootstrap.site_exists("x.localhost", sites))
            self.assertFalse(bootstrap.assets_present(sites))
            (sites / "assets" / "js").mkdir(parents=True)
            self.assertTrue(bootstrap.assets_present(sites))

    def test_credentials_written_once_with_owner_permissions(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            sites = Path(tmp)
            first = bootstrap.write_credentials("x.localhost", "pw-one", sites)
            second = bootstrap.write_credentials("x.localhost", "pw-two", sites)
            self.assertEqual(first, second)
            body = first.read_text()
            self.assertIn("pw-one", body)
            self.assertNotIn("pw-two", body)  # never rotates silently
            self.assertEqual(oct(first.stat().st_mode & 0o777), "0o600")

    def test_root_password_parsing_requires_key_and_value(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            secrets_dir = Path(tmp)
            with self.assertRaises(RuntimeError):
                bootstrap.read_root_password(secrets_dir)
            (secrets_dir / "db.env").write_text("MARQB_ROOT_PASSWORD=no\n")
            with self.assertRaises(RuntimeError):
                bootstrap.read_root_password(secrets_dir)
            (secrets_dir / "db.env").write_text("MARIADB_ROOT_PASSWORD=rootpw\nOTHER=1\n")
            self.assertEqual(bootstrap.read_root_password(secrets_dir), "rootpw")


if __name__ == "__main__":
    unittest.main()

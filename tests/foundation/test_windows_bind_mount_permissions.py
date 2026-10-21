#!/usr/bin/env python3
"""Regression tests for the Docker Desktop on Windows bind-mount permission fix.

Root cause (production failure of record):
  All app containers run as the `frappe` user (UID 1000 via `USER frappe`
  in product/app.Dockerfile), but `./data/sites` and `./data/logs` are
  bind-mounted from the Windows host. Docker Desktop on Windows does not
  map host file ownership to Linux container UIDs, so those directories
  appear inside the container with ownership that UID 1000 cannot write to.
  Site creation, bench migrations, asset builds, log writes, and every
  frappe operation that touches the sites volume fail with "Permission
  denied".

Fix (root-init + privilege drop):
  All app services run as `user: root` in docker-compose.yml. The universal
  entrypoint (product/entrypoint.sh) chowns the bind-mounted directories to
  frappe:frappe as root, then drops to the frappe user via `su -s /bin/sh
  frappe -c` for all service work (bench, gunicorn, node). No chmod 0777.

These tests are in-sandbox verified: they parse the entrypoint script and
docker-compose.yml, and exercise bootstrap.py's path-handling against
temporary directories. Docker itself is not available in this environment.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
COMPOSE = PRODUCT / "docker-compose.yml"
ENTRYPOINT = PRODUCT / "entrypoint.sh"

sys_path_inserted = False
if str(PRODUCT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PRODUCT))
import bootstrap  # noqa: E402


class WindowsBindMountPermissionContract(unittest.TestCase):
    """The entrypoint must fix Windows bind-mount ownership as root,
    then drop to frappe for all service work."""

    def setUp(self):
        self.compose = COMPOSE.read_text()
        self.entrypoint = ENTRYPOINT.read_text()

    def test_all_app_services_run_as_root_for_bind_mount_chown(self):
        """Every app service must have user: root so it can chown
        Windows bind mounts before dropping to frappe."""
        for svc in ("bootstrap", "web", "worker", "scheduler", "socketio"):
            block = re.search(
                rf"^  {svc}:\n(.*?)(?=^  [^ \n]+:\n)", self.compose,
                flags=re.M | re.S,
            )
            self.assertIsNotNone(block, f"compose block for {svc}")
            self.assertIn("user: root", block.group(1),
                          f"{svc} must run as root to chown bind mounts")

    def test_entrypoint_chowns_bind_mounts_as_root(self):
        """The entrypoint must chown sites and logs directories to frappe."""
        self.assertIn(
            "chown -R frappe:frappe /home/frappe/bench/sites /home/frappe/bench/logs",
            self.entrypoint,
            "entrypoint must chown Windows bind-mounted directories to frappe",
        )

    def test_entrypoint_never_uses_chmod_0777(self):
        """World-writable directories expose customer data on the Windows host."""
        # Comments explaining why not are fine; only flag actual commands.
        self.assertNotRegex(self.entrypoint, r"(?m)^[^#\n]*chmod\s+0?777")

    def test_entrypoint_drops_to_frappe_for_all_service_work(self):
        """After chown, the entrypoint must drop to frappe via su."""
        self.assertIn("su -s /bin/sh frappe -c", self.entrypoint)
        # bench/gunicorn/node are never invoked as root
        self.assertIn("exec su -s /bin/sh frappe -c 'python3 /product/bootstrap.py'", self.entrypoint)
        self.assertNotIn("exec run_frappe '", self.entrypoint)
        self.assertIn("exec /home/frappe/bench/env/bin/gunicorn", self.entrypoint)

    def test_entrypoint_passes_service_name_argument(self):
        """Each service passes its name to the universal entrypoint."""
        for svc in ("bootstrap", "web", "worker", "scheduler", "socketio"):
            block = re.search(
                rf"^  {svc}:\n(.*?)(?=^  [^ \n]+:\n)", self.compose,
                flags=re.M | re.S,
            )
            self.assertIn(
                f'entrypoint: ["/product/entrypoint.sh", "{svc}"]',
                block.group(1),
                f"{svc} must pass its service name to the entrypoint",
            )

    def test_bootstrap_stays_one_shot_with_isolated_db_secret(self):
        """Bootstrap is restart: "no", mounts db.env read-only only to itself."""
        block = re.search(
            r"^  bootstrap:\n(.*?)(?=^  [^ \n]+:\n)", self.compose, flags=re.M | re.S
        ).group(1)
        self.assertIn('restart: "no"', block)
        self.assertIn("source: ./data/secrets/db.env", block)
        self.assertIn("read_only: true", block)
        # Other services never see db.env
        for other in ("web", "worker", "scheduler", "socketio"):
            other_block = re.search(
                rf"^  {other}:\n(.*?)(?=^  [^ \n]+:\n)", self.compose,
                flags=re.M | re.S,
            ).group(1)
            self.assertNotIn("source: ./data/secrets/db.env", other_block)
            self.assertNotIn("/run/secrets", other_block)


class BootstrapPathPermissionContract(unittest.TestCase):
    """bootstrap.py must handle paths correctly on bind-mounted volumes."""

    def test_site_exists_detects_previous_installation(self):
        """On repeat boots, site_exists() must find site_config.json."""
        with tempfile.TemporaryDirectory() as tmp:
            sites = Path(tmp)
            self.assertFalse(bootstrap.site_exists("x.localhost", sites))
            (sites / "x.localhost").mkdir(parents=True)
            (sites / "x.localhost" / "site_config.json").write_text("{}")
            self.assertTrue(bootstrap.site_exists("x.localhost", sites))

    def test_credentials_are_written_once_and_not_rotated(self):
        """The first-run Administrator password is written atomically once."""
        with tempfile.TemporaryDirectory() as tmp:
            sites = Path(tmp)
            first = bootstrap.write_credentials("x.localhost", "pw-one", sites)
            second = bootstrap.write_credentials("x.localhost", "pw-two", sites)
            self.assertEqual(first, second)
            body = first.read_text()
            self.assertIn("pw-one", body)
            self.assertNotIn("pw-two", body)
            if os.name != "nt":
                self.assertEqual(oct(first.stat().st_mode & 0o777), "0o600")

    def test_create_site_input_validation_rejects_bad_site_names(self):
        """Malformed site names must fail before any filesystem write."""
        with self.assertRaises(RuntimeError):
            bootstrap.create_site("", "rootpw", "adminpw", "dbpw")
        with self.assertRaises(RuntimeError):
            bootstrap.create_site("../etc", "rootpw", "adminpw", "dbpw")
        with self.assertRaises(RuntimeError):
            bootstrap.create_site("x.localhost", "rootpw", "adminpw", "dbpw",
                                  db_type="postgres")  # only mariadb supported

    def test_seed_sites_restores_files_hidden_by_bind_mount(self):
        """An empty host bind mount hides sites/apps.txt; seed_sites restores it."""
        with tempfile.TemporaryDirectory() as tmp:
            seed = Path(tmp) / "seed"
            sites = Path(tmp) / "sites"
            seed.mkdir()
            sites.mkdir()
            for name in ("apps.txt", "apps.json", "common_site_config.json"):
                (seed / name).write_text(f"image {name}")
            written = sorted(bootstrap.seed_sites(sites, seed))
            self.assertEqual(written, ["apps.json", "apps.txt", "common_site_config.json"])
            # common_site_config.json is seeded only once (owner runtime settings)
            (sites / "common_site_config.json").write_text("owner runtime settings")
            (seed / "apps.txt").write_text("updated image apps")
            written = sorted(bootstrap.seed_sites(sites, seed))
            self.assertEqual(written, ["apps.json", "apps.txt"])
            self.assertEqual((sites / "common_site_config.json").read_text(),
                             "owner runtime settings")
            self.assertEqual((sites / "apps.txt").read_text(), "updated image apps")


if __name__ == "__main__":
    unittest.main()
